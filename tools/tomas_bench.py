#!/usr/bin/env python3
"""
tomas_bench.py — TOMAS-AGI v2.0 性能基准对比工具

M6 用户态工具 (T038)

功能：
  - CPU 基准：八元数乘法、非结合 Laplacian、δ-mem 融合
  - GPU 预期延迟估算（基于 CUDA 核心数和带宽）
  - FPGA 预期延迟估算（基于时钟频率和流水线深度）
  - 对比报告生成

用法：
  python tomas_bench.py --trials 1000
  python tomas_bench.py --quick
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from typing import List, Dict

# 添加 sim 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'sim'))

try:
    import numpy as np
except ImportError:
    print("需要 numpy: pip install numpy")
    sys.exit(1)

try:
    from octonion_py import Octonion, multiply, associator, associator_norm
    from nasga_core import compute_xi_c, compute_delta
    from fold_depth_py import compute_fold_depth, classify_delta_regime
    HAS_SIM = True
except ImportError:
    HAS_SIM = False
    print("[WARN] 无法导入仿真模块，仅运行估算模式")


@dataclass
class BenchResult:
    """基准测试结果"""
    name: str
    trials: int
    total_ms: float
    per_op_us: float
    ops_per_sec: float
    details: Dict = None


# ============================================================
# CPU 基准
# ============================================================
def bench_octonion_multiply(trials: int = 1000) -> BenchResult:
    """CPU 八元数乘法基准"""
    if not HAS_SIM:
        return _estimate_cpu("八元数乘法", trials, 2.5)

    # 预生成随机八元数
    np.random.seed(42)
    octs_a = [Octonion.random() for _ in range(trials)]
    octs_b = [Octonion.random() for _ in range(trials)]

    t0 = time.perf_counter()
    for i in range(trials):
        multiply(octs_a[i], octs_b[i])
    elapsed = (time.perf_counter() - t0) * 1000  # ms

    per_op = elapsed * 1000 / trials  # μs
    ops_sec = trials / (elapsed / 1000)

    return BenchResult(
        name="CPU 八元数乘法",
        trials=trials,
        total_ms=elapsed,
        per_op_us=per_op,
        ops_per_sec=ops_sec,
    )


def bench_associator(trials: int = 1000) -> BenchResult:
    """CPU associator 计算（含两次八元数乘法）"""
    if not HAS_SIM:
        return _estimate_cpu("associator", trials, 6.0)

    np.random.seed(43)
    octs_a = [Octonion.random() for _ in range(trials)]
    octs_b = [Octonion.random() for _ in range(trials)]
    octs_c = [Octonion.random() for _ in range(trials)]

    t0 = time.perf_counter()
    for i in range(trials):
        associator(octs_a[i], octs_b[i], octs_c[i])
    elapsed = (time.perf_counter() - t0) * 1000

    per_op = elapsed * 1000 / trials
    ops_sec = trials / (elapsed / 1000)

    return BenchResult(
        name="CPU associator",
        trials=trials,
        total_ms=elapsed,
        per_op_us=per_op,
        ops_per_sec=ops_sec,
    )


def bench_delta_compute(trials: int = 1000) -> BenchResult:
    """CPU δ 计算基准"""
    if not HAS_SIM:
        return _estimate_cpu("δ 计算", trials, 8.0)

    np.random.seed(44)
    octs_a = [Octonion.random() for _ in range(trials)]
    octs_b = [Octonion.random() for _ in range(trials)]
    octs_c = [Octonion.random() for _ in range(trials)]

    t0 = time.perf_counter()
    for i in range(trials):
        a_norm = octs_a[i].normalize()
        b_norm = octs_b[i].normalize()
        c_norm = octs_c[i].normalize()
        assoc = associator(a_norm, b_norm, c_norm)
        delta = compute_fold_depth(assoc.abs())
    elapsed = (time.perf_counter() - t0) * 1000

    per_op = elapsed * 1000 / trials
    ops_sec = trials / (elapsed / 1000)

    return BenchResult(
        name="CPU δ 计算",
        trials=trials,
        total_ms=elapsed,
        per_op_us=per_op,
        ops_per_sec=ops_sec,
    )


def bench_laplacian(trials: int = 100) -> BenchResult:
    """CPU 非结合 Laplacian 基准"""
    if not HAS_SIM:
        return _estimate_cpu("非结合 Laplacian", trials, 200.0)

    from spectral_laplacian_py import EmlGraph, compute_spectral_laplacian

    np.random.seed(45)
    times = []
    for _ in range(trials):
        g = EmlGraph(8)
        # 添加随机边
        for i in range(8):
            for j in range(i + 1, 8):
                if np.random.random() < 0.4:
                    g.add_edge(i, j, np.random.random())

        t0 = time.perf_counter()
        lap = compute_spectral_laplacian(g, alpha=0.2)
        times.append(time.perf_counter() - t0)

    elapsed = sum(times) * 1000
    per_op = elapsed * 1000 / trials
    ops_sec = trials / (elapsed / 1000)

    return BenchResult(
        name="CPU 非结合 Laplacian",
        trials=trials,
        total_ms=elapsed,
        per_op_us=per_op,
        ops_per_sec=ops_sec,
    )


# ============================================================
# GPU/FPGA 估算
# ============================================================
def estimate_gpu(cpu_results: List[BenchResult]) -> List[BenchResult]:
    """GPU 预期延迟估算"""
    # 典型 RTX 3080 参数
    gpu_cuda_cores = 8704
    gpu_clock_mhz = 1440
    gpu_bandwidth_gbps = 760

    # 加速比估算：
    # - 八元数乘法：~50x（数据并行，8 分量独立）
    # - associator：~80x（4 次乘法可流水线）
    # - δ 计算：~30x（含归约操作）
    # - Laplacian：~100x（SpMV 天然并行）

    speedups = {
        "CPU 八元数乘法": 50,
        "CPU associator": 80,
        "CPU δ 计算": 30,
        "CPU 非结合 Laplacian": 100,
    }

    gpu_results = []
    for r in cpu_results:
        su = speedups.get(r.name, 20)  # 默认 20x
        gpu_per_op = r.per_op_us / su
        gpu_results.append(BenchResult(
            name=r.name.replace("CPU", "GPU (估计)"),
            trials=r.trials,
            total_ms=r.total_ms / su,
            per_op_us=gpu_per_op,
            ops_per_sec=r.ops_per_sec * su,
            details={"speedup": f"{su}x", "platform": "RTX 3080"},
        ))
    return gpu_results


def estimate_fpga(cpu_results: List[BenchResult]) -> List[BenchResult]:
    """FPGA 预期延迟估算"""
    # Xilinx Artix-7 参数
    fpga_clock_mhz = 200      # 200 MHz
    fpga_lut = 33280           # Artix-7 XC7A100T
    fpga_dsp = 240             # DSP48E1

    # 流水线加速估算：
    # - 八元数乘法：3 周期延迟 @ 200MHz = 15ns/op（流水线满吞吐 1/cycle）
    # - associator：9 周期 @ 200MHz = 45ns/op
    # - δ 计算：5 周期 @ 200MHz = 25ns/op
    # - Laplacian：N*nnz 周期（取决于图大小）

    fpga_latencies = {
        "CPU 八元数乘法": 0.015,     # 15 ns → 0.015 μs
        "CPU associator": 0.045,     # 45 ns → 0.045 μs
        "CPU δ 计算": 0.025,        # 25 ns → 0.025 μs
        "CPU 非结合 Laplacian": 0.5,  # 500 ns（8 节点图）
    }

    fpga_results = []
    for r in cpu_results:
        fpga_per = fpga_latencies.get(r.name, 0.1)
        fpga_ops = 1e6 / fpga_per  # ops/sec
        fpga_results.append(BenchResult(
            name=r.name.replace("CPU", "FPGA (估计)"),
            trials=r.trials,
            total_ms=r.trials * fpga_per / 1000,
            per_op_us=fpga_per,
            ops_per_sec=fpga_ops,
            details={"clock": "200 MHz", "platform": "Artix-7 XC7A100T"},
        ))
    return fpga_results


def _estimate_cpu(name: str, trials: int, per_op_us: float) -> BenchResult:
    """无仿真模块时的 CPU 估算"""
    return BenchResult(
        name=f"CPU {name} (估计)",
        trials=trials,
        total_ms=trials * per_op_us / 1000,
        per_op_us=per_op_us,
        ops_per_sec=1e6 / per_op_us,
    )


# ============================================================
# 报告生成
# ============================================================
def generate_report(cpu: List[BenchResult], gpu: List[BenchResult], fpga: List[BenchResult]):
    """生成对比报告"""
    print("=" * 70)
    print("TOMAS-AGI v2.0 性能基准对比报告")
    print("=" * 70)
    print()

    # 表头
    header = f"{'操作':<28} {'每操作(μs)':<14} {'ops/sec':<14} {'加速比':<10}"
    print(header)
    print("-" * 70)

    # 按 CPU 结果对齐
    for i, c in enumerate(cpu):
        # CPU 行
        print(f"{c.name:<28} {c.per_op_us:<14.3f} {c.ops_per_sec:<14.0f} {'1.0x':<10}")
        # GPU 行
        if i < len(gpu):
            g = gpu[i]
            su = c.per_op_us / g.per_op_us if g.per_op_us > 0 else 0
            print(f"{g.name:<28} {g.per_op_us:<14.4f} {g.ops_per_sec:<14.0f} {su:<10.1f}x")
        # FPGA 行
        if i < len(fpga):
            f = fpga[i]
            su = c.per_op_us / f.per_op_us if f.per_op_us > 0 else 0
            print(f"{f.name:<28} {f.per_op_us:<14.4f} {f.ops_per_sec:<14.0f} {su:<10.0f}x")
        print()

    print("=" * 70)
    print("注：GPU 和 FPGA 数据为基于架构参数的理论估算")
    print("    实际性能需在对应硬件上验证")


# ============================================================
# 主入口
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        prog="tomas_bench",
        description="TOMAS-AGI v2.0 性能基准对比工具"
    )
    parser.add_argument("--trials", type=int, default=1000, help="基准测试轮数")
    parser.add_argument("--quick", action="store_true", help="快速模式（100轮）")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    args = parser.parse_args()

    trials = 100 if args.quick else args.trials
    lap_trials = max(trials // 10, 10)

    print(f"运行基准测试（trials={trials}, lap_trials={lap_trials}）...\n")

    # CPU 基准
    cpu_results = [
        bench_octonion_multiply(trials),
        bench_associator(trials),
        bench_delta_compute(trials),
        bench_laplacian(lap_trials),
    ]

    # GPU 估算
    gpu_results = estimate_gpu(cpu_results)

    # FPGA 估算
    fpga_results = estimate_fpga(cpu_results)

    if args.json:
        data = {
            "cpu": [asdict(r) for r in cpu_results],
            "gpu": [asdict(r) for r in gpu_results],
            "fpga": [asdict(r) for r in fpga_results],
        }
        print(json.dumps(data, indent=2, default=str))
    else:
        generate_report(cpu_results, gpu_results, fpga_results)

    return 0


if __name__ == "__main__":
    sys.exit(main())
