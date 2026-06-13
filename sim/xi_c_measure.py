"""
ξ_c 效能指标测量 —— TOMAS-AGI 仿真器 M1 里程碑 Phase 4
测量非结合性指标 ξ_c = ||[a,b,c]||/(||a||·||b||·||c||) 并输出 CSV
"""

import numpy as np
import csv
import os
import sys
from typing import List, Dict, Tuple, Optional

# 自动修复 sys.path，确保能导入同目录模块
_import_path = os.path.dirname(os.path.abspath(__file__))
if _import_path not in sys.path:
    sys.path.insert(0, _import_path)

from octonion_py import Octonion, fan_multiply, _mult_table
from nasga_core import associator, compute_xi_c, benchmark_associativity


# ============================================================
# ξ_c 测量核心函数
# ============================================================

def measure_xi_c_single(a: Octonion, b: Octonion, c: Octonion,
                      label: str = "") -> Dict:
    """
    测量单组 (a,b,c) 的 ξ_c 指标
    返回包含各项数值的字典
    """
    norm_a = a.abs()
    norm_b = b.abs()
    norm_c = c.abs()
    xi = compute_xi_c(a, b, c)
    res = associator(a, b, c)
    res_norm = res.abs()

    return {
        "label": label,
        "xi_c": xi,
        "res_norm": res_norm,
        "norm_a": norm_a,
        "norm_b": norm_b,
        "norm_c": norm_c,
        "a0": a.e[0],
        "a1": a.e[1],
        "b0": b.e[0],
        "b1": b.e[1],
        "c0": c.e[0],
        "c1": c.e[1],
    }


def measure_random_batch(num_samples: int = 1000, seed: int = 42,
                           normalize: bool = True) -> List[Dict]:
    """
    随机采样八元数三元组，批量测量 ξ_c
    
    参数：
        num_samples: 采样数量
        seed: 随机种子
        normalize: 是否归一化（使 ||a||=||b||=||c||=1）
    
    返回：
        List[Dict]，每个字典是一条记录
    """
    np.random.seed(seed)
    results = []

    for i in range(num_samples):
        a = Octonion.random(seed=seed + i)
        b = Octonion.random(seed=seed + i + num_samples)
        c = Octonion.random(seed=seed + i + 2 * num_samples)

        if normalize:
            a = a.normalize()
            b = b.normalize()
            c = c.normalize()

        rec = measure_xi_c_single(a, b, c, label=f"rand_{i}")
        results.append(rec)

    return results


def measure_basis_triples() -> List[Dict]:
    """
    测量所有基三元组 (ei, ej, ek) 的 ξ_c
    用于验证 Fano 平面上的结合性性质
    """
    results = []
    basis_names = ["e0", "e1", "e2", "e3", "e4", "e5", "e6", "e7"]

    for i in range(8):
        for j in range(8):
            for k in range(8):
                a = Octonion.basis(i)
                b = Octonion.basis(j)
                c = Octonion.basis(k)
                label = f"{basis_names[i]},{basis_names[j]},{basis_names[k]}"
                rec = measure_xi_c_single(a, b, c, label=label)
                results.append(rec)

    return results


def measure_fano_line_triples() -> List[Dict]:
    """
    专门测量 Fano 直线上的三元组
    根据 Moufang 恒等式，这些三元组应满足结合性（ξ_c = 0）
    """
    # Fano 直线（1-indexed）：{1,2,4}, {2,3,5}, {3,4,6}, {4,5,7}, {5,6,1}, {6,7,2}, {7,1,3}
    fano_lines = [
        (1, 2, 4), (2, 3, 5), (3, 4, 6), (4, 5, 7),
        (5, 6, 1), (6, 7, 2), (7, 1, 3),
    ]
    results = []
    basis_names = ["e0", "e1", "e2", "e3", "e4", "e5", "e6", "e7"]

    for (a_idx, b_idx, c_idx) in fano_lines:
        # 三元组 (ea, eb, ec)
        a = Octonion.basis(a_idx)
        b = Octonion.basis(b_idx)
        c = Octonion.basis(c_idx)
        label = f"fano_{basis_names[a_idx]},{basis_names[b_idx]},{basis_names[c_idx]}"
        rec = measure_xi_c_single(a, b, c, label=label)
        results.append(rec)

        # 也测试排列
        # (eb, ec, ea)
        a2 = Octonion.basis(b_idx)
        b2 = Octonion.basis(c_idx)
        c2 = Octonion.basis(a_idx)
        label2 = f"fano_{basis_names[b_idx]},{basis_names[c_idx]},{basis_names[a_idx]}"
        rec2 = measure_xi_c_single(a2, b2, c2, label=label2)
        results.append(rec2)

    return results


# ============================================================
# CSV 输出
# ============================================================

def write_csv(results: List[Dict], filepath: str, append: bool = False):
    """
    将测量结果写入 CSV 文件
    
    参数：
        results: measure_xi_c_single / measure_random_batch 的返回值
        filepath: 输出文件路径（含文件名）
        append: 是否追加到已有文件（默认覆盖）
    """
    if not results:
        print(f"[WARN] 无数据可写入 CSV：{filepath}")
        return

    fieldnames = list(results[0].keys())

    mode = "a" if append else "w"
    with open(filepath, mode, newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames)
        if not append:
            writer.writeheader()
        for rec in results:
            writer.writerow(rec)

    print(f"  [PASS] CSV {'追加' if append else '写入'} 成功：{filepath}（{len(results)} 条记录）")


def read_csv(filepath: str) -> List[Dict]:
    """
    从 CSV 文件读取测量结果
    """
    results = []
    if not os.path.exists(filepath):
        print(f"[WARN] CSV 文件不存在：{filepath}")
        return results

    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 将数值字段转回 float
            for key in row:
                try:
                    row[key] = float(row[key])
                except ValueError:
                    pass
            results.append(row)

    print(f"  [PASS] CSV 读取成功：{filepath}（{len(results)} 条记录）")
    return results


# ============================================================
# 统计分析
# ============================================================

def analyze_xi_c_distribution(results: List[Dict], verbose: bool = True) -> Dict:
    """
    分析 ξ_c 值分布，输出统计量
    """
    xi_values = np.array([r["xi_c"] for r in results])
    res_norms = np.array([r["res_norm"] for r in results])

    stats = {
        "count": len(xi_values),
        "xi_mean": float(np.mean(xi_values)),
        "xi_std": float(np.std(xi_values)),
        "xi_max": float(np.max(xi_values)),
        "xi_min": float(np.min(xi_values)),
        "xi_median": float(np.median(xi_values)),
        "res_norm_mean": float(np.mean(res_norms)),
        "res_norm_max": float(np.max(res_norms)),
        "res_norm_min": float(np.min(res_norms)),
        "frac_zero": float(np.sum(xi_values < 1e-10) / len(xi_values)),
    }

    if verbose:
        print("[ξ_c 统计分析]")
        print(f"  样本数：{stats['count']}")
        print(f"  ξ_c 均值：{stats['xi_mean']:.6f}")
        print(f"  ξ_c 标准差：{stats['xi_std']:.6f}")
        print(f"  ξ_c 最大值：{stats['xi_max']:.6f}")
        print(f"  ξ_c 最小值：{stats['xi_min']:.6f}")
        print(f"  ξ_c 中位数：{stats['xi_median']:.6f}")
        print(f"  结合子为零的比例（ξ_c < 1e-10）：{stats['frac_zero']*100:.1f}%")

    return stats


# ============================================================
# 测试套件
# ============================================================

def test_xi_c_measurement():
    """测试1：基本 ξ_c 测量"""
    print("[测试1] ξ_c 基本测量...")
    a = Octonion.random(seed=1)
    b = Octonion.random(seed=2)
    c = Octonion.random(seed=3)
    a = a.normalize()
    b = b.normalize()
    c = c.normalize()

    rec = measure_xi_c_single(a, b, c, label="test1")
    xi = rec["xi_c"]

    # ξ_c 应在 [0, 2] 范围内
    if 0.0 <= xi <= 2.0 + 1e-10:
        print(f"  [PASS] ξ_c = {xi:.6f}（在 [0, 2] 范围内）")
        return True
    else:
        print(f"  [FAIL] ξ_c = {xi:.6f}（超出 [0, 2] 范围）")
        return False


def test_csv_write_read():
    """测试2：CSV 写入与读取"""
    print("\n[测试2] CSV 写入与读取...")
    import tempfile
    tmp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv", encoding="utf-8")
    tmp.close()
    filepath = tmp.name

    try:
        # 生成随机数据
        results = measure_random_batch(num_samples=10, seed=123)
        # 写入 CSV
        write_csv(results, filepath)
        # 读取 CSV
        loaded = read_csv(filepath)
        # 验证
        if len(loaded) == len(results):
            # 检查第一条记录的字段
            if set(loaded[0].keys()) == set(results[0].keys()):
                print(f"  [PASS] CSV 写入+读取成功（{len(loaded)} 条记录）")
                return True
            else:
                print(f"  [FAIL] CSV 字段不匹配")
                return False
        else:
            print(f"  [FAIL] CSV 记录数不匹配：写入 {len(results)}，读取 {len(loaded)}")
            return False
    finally:
        os.unlink(filepath)


def test_fano_line_zero():
    """测试3：Fano 直线上的三元组 ξ_c = 0"""
    print("\n[测试3] Fano 直线结合性验证...")
    results = measure_fano_line_triples()
    stats = analyze_xi_c_distribution(results, verbose=False)

    # Fano 直线上的三元组应满足 Moufang 恒等式，ξ_c ≈ 0
    # 但注意：只有特定顺序（循环顺序）才满足，排列顺序可能不满足
    # 这里我们只检查最大值是否很小
    if stats["xi_max"] < 1e-6:
        print(f"  [PASS] Fano 直线三元组 ξ_c 最大值 = {stats['xi_max']:.2e}（接近 0）")
        return True
    else:
        print(f"  [FAIL] Fano 直线三元组 ξ_c 最大值 = {stats['xi_max']:.6f}（不接近 0）")
        # 打印前 5 条记录的 ξ_c
        for r in results[:5]:
            print(f"    {r['label']}: ξ_c = {r['xi_c']:.6f}")
        return False


def test_random_distribution():
    """测试4：随机三元组 ξ_c 分布统计"""
    print("\n[测试4] 随机三元组 ξ_c 分布统计...")
    results = measure_random_batch(num_samples=500, seed=42)
    stats = analyze_xi_c_distribution(results, verbose=True)

    # 检查分布是否合理
    reasonable = (
        stats["xi_mean"] > 0.0 and
        stats["xi_mean"] < 2.0 and
        stats["xi_std"] > 0.0 and
        stats["xi_std"] < 2.0
    )
    if reasonable:
        print(f"  [PASS] ξ_c 分布合理")
        return True
    else:
        print(f"  [FAIL] ξ_c 分布异常")
        return False


# ============================================================
# 主程序：命令行接口
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="ξ_c 效能指标测量 —— TOMAS-AGI 仿真器"
    )
    parser.add_argument("--mode", type=str, default="random",
                        choices=["random", "basis", "fano", "test"],
                        help="测量模式：random（随机）/ basis（基三元组）/ fano（Fano 直线）/ test（运行测试套件）")
    parser.add_argument("--num-samples", type=int, default=1000,
                        help="随机采样数量（仅 random 模式）")
    parser.add_argument("--seed", type=int, default=42,
                        help="随机种子")
    parser.add_argument("--output", type=str, default="xi_c_results.csv",
                        help="输出 CSV 文件路径")
    parser.add_argument("--no-normalize", action="store_true",
                        help="是否归一化八元数（默认归一化）")
    args = parser.parse_args()

    if args.mode == "test":
        print("=" * 60)
        print("ξ_c 效能指标测量 —— 测试套件")
        print("=" * 60)
        results = []
        results.append(("ξ_c 基本测量", test_xi_c_measurement()))
        results.append(("CSV 写入与读取", test_csv_write_read()))
        results.append(("Fano 直线结合性验证", test_fano_line_zero()))
        results.append(("随机三元组 ξ_c 分布统计", test_random_distribution()))
        print("\n" + "=" * 60)
        print("测试汇总：")
        for name, passed in results:
            status = "[PASS]" if passed else "[FAIL]"
            print(f"  {status} {name}")
        n_pass = sum(1 for _, p in results if p)
        n_total = len(results)
        print(f"\n总计：{n_pass}/{n_total} 通过")
        print("=" * 60)
        return

    # 测量模式
    print("=" * 60)
    print(f"ξ_c 测量模式：{args.mode}")
    print("=" * 60)

    if args.mode == "random":
        results = measure_random_batch(
            num_samples=args.num_samples,
            seed=args.seed,
            normalize=not args.no_normalize
        )
    elif args.mode == "basis":
        results = measure_basis_triples()
    elif args.mode == "fano":
        results = measure_fano_line_triples()
    else:
        print(f"[FAIL] 未知模式：{args.mode}")
        return

    # 输出统计
    stats = analyze_xi_c_distribution(results, verbose=True)

    # 写入 CSV
    write_csv(results, args.output)
    print(f"\n结果已保存至：{args.output}")


if __name__ == "__main__":
    main()
