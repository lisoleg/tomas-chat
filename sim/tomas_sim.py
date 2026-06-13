"""
tomas_sim.py — TOMAS-AGI 主模拟器 v2.0
==============================================
M1 里程碑 Phase 4 最终交付文件

用法:
  python tomas_sim.py --mode full        # 全量诊断（默认）
  python tomas_sim.py --mode benchmark    # 仅 A6-BS 基准
  python tomas_sim.py --mode measure -n 500  # ξ_c 批量测量
"""
import sys, os, time, json, argparse, random
from datetime import datetime

_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

# ── 模块导入 ──
mods = {}
for name in ["octonion_py", "spectral_laplacian_py", "nasga_core",
             "a6_bs_benchmark", "xi_c_measure", "fold_depth_py",
             "drift_detector", "delta_mem_py"]:
    try:
        mod = __import__(name)
        mods[name] = mod
        print(f"[OK] {name}")
    except Exception as e:
        print(f"[FAIL] {name}: {e}")
        mods[name] = None

Octonion = None
if mods.get("octonion_py"):
    try:
        from octonion_py import Octonion
    except:
        pass

def _safe(obj, fn, *a, **kw):
    """安全调用，返回 (成功:bool, 结果)"""
    try:
        return True, fn(*a, **kw)
    except Exception as e:
        return False, str(e)

# ── 各模块测试 ──

def test_octonion(verbose=True):
    m = mods.get("octonion_py")
    if not m: return False, {}
    if verbose:
        print("\n" + "="*60 + "\n[测试] Octonion（八元数）" + "\n" + "="*60)
    # 测试1: Fano 乘法表
    errs = m.test_fano_table()
    fano_ok = len(errs) == 0
    # 测试2: 范数乘积
    r2 = m.test_norm_product()
    norm_ok = r2.get("pass", False) if isinstance(r2, dict) else False
    # 测试3: 非结合性（演示，不判 pass/fail）
    m.test_non_associativity()
    ok = fano_ok and norm_ok
    if verbose:
        print(f"  Fano 乘法表: [{'PASS' if fano_ok else 'FAIL'}]")
        print(f"  范数乘积: [{'PASS' if norm_ok else 'FAIL'}]")
        print(f"\n  [{'PASS' if ok else 'FAIL'}] Octonion 模块")
    return ok, {"fano": fano_ok, "norm": norm_ok}

def test_spectral(verbose=True):
    m = mods.get("spectral_laplacian_py")
    if not m: return False, {}
    if verbose:
        print("\n" + "="*60 + "\n[测试] EML 谱图 Laplacian" + "\n" + "="*60)
    r = [
        m.test_laplacian_triangle(),
        m.test_laplacian_verify_networkx(),
        m.test_laplacian_spectrum(),
        m.test_eml_graph_build(),
    ]
    ok = all(r)
    if verbose:
        names = ["三角形", "NetworkX验证", "谱计算", "构建API"]
        for n, v in zip(names, r):
            print(f"  {n}: [{'PASS' if v else 'FAIL'}]")
        print(f"\n  [{'PASS' if ok else 'FAIL'}] Spectral Laplacian 模块")
    return ok, {"details": r}

def test_nasga(verbose=True):
    m = mods.get("nasga_core")
    if not m: return False, {}
    if verbose:
        print("\n" + "="*60 + "\n[测试] NASGA 核心代数运算" + "\n" + "="*60)
    try:
        a = Octonion.random(seed=100) if Octonion else None
        b = Octonion.random(seed=200) if Octonion else None
        c = Octonion.random(seed=300) if Octonion else None
        if not a: raise RuntimeError("Octonion 不可用")
        xi = m.compute_xi_c(a, b, c)
        # check_moufang_all 返回 dict
        r = m.check_moufang_all(a, b)
        mf_ok = r.get("all_pass", False) if isinstance(r, dict) else False
        ok = (0 <= xi <= 2.0) and mf_ok
        if verbose:
            print(f"  xi_c = {xi:.6f}")
            print(f"  Moufang all_pass: {mf_ok}")
            print(f"\n  [{'PASS' if ok else 'FAIL'}] NASGA 核心模块")
        return ok, {"xi_c": xi, "moufang": mf_ok}
    except Exception as e:
        if verbose:
            print(f"\n  [FAIL] NASGA 核心模块: {e}")
        return False, {"error": str(e)}

def test_a6bs(verbose=True):
    """运行 A6-BS 五级基准测试（直接运行，不抛异常即 PASS）"""
    m = mods.get("a6_bs_benchmark")
    if not m: return False, {}
    if verbose:
        print("\n" + "="*60 + "\n[测试] A6-BS 五级基准" + "\n" + "="*60)
    try:
        import io, contextlib
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            m.run_all_levels(verbose=verbose)
        report_str = out.getvalue()
        # 简单判断：输出中含 "5/5" 即 PASS
        ok = "5/5" in report_str
        if verbose:
            print(f"\n  A6-BS 基准: [{'PASS' if ok else 'FAIL'}]")
        return ok, {"raw": report_str[-200:]}
    except Exception as e:
        if verbose:
            print(f"\n  [FAIL] A6-BS 基准测试: {e}")
        return False, {"error": str(e)}

def test_xi_c(verbose=True):
    m = mods.get("xi_c_measure")
    if not m: return False, {}
    if verbose:
        print("\n" + "="*60 + "\n[测试] ξ_c 效能指标测量" + "\n" + "="*60)
    try:
        r1 = m.test_xi_c_measurement()
        r2 = m.test_csv_write_read()
        r3 = m.test_fano_line_zero()
        r4 = m.test_random_distribution()
        ok = all([r1, r2, r3, r4])
        if verbose:
            for n, v in zip(["基本测量","CSV读写","Fano直线","随机分布"], [r1,r2,r3,r4]):
                print(f"  {n}: [{'PASS' if v else 'FAIL'}]")
            print(f"\n  [{'PASS' if ok else 'FAIL'}] ξ_c 测量模块")
        return ok, {"details": [r1,r2,r3,r4]}
    except Exception as e:
        if verbose:
            print(f"\n  [FAIL] ξ_c 测量模块: {e}")
        return False, {"error": str(e)}

def test_fold_depth(verbose=True):
    """v2.0 δ 参数（谱折叠深度）测试"""
    m = mods.get("fold_depth_py")
    if not m: return False, {}
    if verbose:
        print("\n" + "="*60 + "\n[测试] δ 谱折叠深度（v2.0 核心序参量）" + "\n" + "="*60)
    try:
        # 测试 1: δ 基本计算
        delta = m.compute_fold_depth(0.05)
        ok1 = 0 <= delta <= 2.0

        # 测试 2: A1 公理（δ 守恒）
        ok2, msg2 = m.check_a1_axiom(0.5, 0.5001, tolerance=1e-3)

        # 测试 3: δ_threshold
        ok3, msg3 = m.check_delta_threshold(0.8)

        # 测试 4: δ 域分类
        regimes = [m.classify_delta_regime(d) for d in [0.0, 0.35, 7.0, 15.0]]
        expected = ['classical', 'quantum', 'stable', 'deep_quantum']
        ok4 = regimes == expected

        ok = ok1 and ok2 and ok3 and ok4
        if verbose:
            print(f"  δ 基本计算: [{'PASS' if ok1 else 'FAIL'}] delta={delta:.4f}")
            print(f"  A1 公理 (0.5≈0.5001): [{'PASS' if ok2 else 'FAIL'}] {msg2}")
            print(f"  δ_threshold (0.8≥0.5): [{'PASS' if ok3 else 'FAIL'}] {msg3}")
            print(f"  δ 域分类: [{'PASS' if ok4 else 'FAIL'}] {regimes}")
            print(f"\n  [{'PASS' if ok else 'FAIL'}] fold_depth 模块")
        return ok, {"delta": delta, "regimes": regimes, "a1": ok2, "threshold": ok3}
    except Exception as e:
        if verbose:
            print(f"\n  [FAIL] fold_depth 模块: {e}")
        return False, {"error": str(e)}

def test_drift_detector(verbose=True):
    """v2.0 ψ 语义漂移检测器测试"""
    m = mods.get("drift_detector")
    if not m: return False, {}
    if verbose:
        print("\n" + "="*60 + "\n[测试] DriftDetector ψ 漂移检测" + "\n" + "="*60)
    try:
        r = m.test_drift_detector()
        ok = r.get("all_pass", False) if isinstance(r, dict) else False
        if verbose:
            for k, v in r.items():
                if k == "all_pass":
                    continue
                status = "PASS" if v.get("pass") else "FAIL"
                print(f"  {k}: [{status}]")
            print(f"\n  [{'PASS' if ok else 'FAIL'}] DriftDetector 模块")
        return ok, {"all_pass": ok}
    except Exception as e:
        if verbose:
            print(f"\n  [FAIL] DriftDetector 模块: {e}")
        return False, {"error": str(e)}

def test_delta_mem(verbose=True):
    """v2.0 δ-mem (DeltaMemLayer) 测试"""
    m = mods.get("delta_mem_py")
    if not m: return False, {}
    if verbose:
        print("\n" + "="*60 + "\n[测试] δ-mem (DeltaMemLayer)" + "\n" + "="*60)
    try:
        r = m.test_delta_mem()
        ok = r.get("all_pass", False) if isinstance(r, dict) else False
        if verbose:
            for k, v in r.items():
                if k == "all_pass":
                    continue
                status = "PASS" if v.get("pass") else "FAIL"
                print(f"  {k}: [{status}]")
            print(f"\n  [{'PASS' if ok else 'FAIL'}] δ-mem 模块")
        return ok, {"all_pass": ok}
    except Exception as e:
        if verbose:
            print(f"\n  [FAIL] δ-mem 模块: {e}")
        return False, {"error": str(e)}

# ── 主入口 ──

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", "-m", default="full", choices=["full","benchmark","measure","interactive"])
    ap.add_argument("--num-samples", "-n", type=int, default=200)
    ap.add_argument("--output", "-o", default=None)
    args = ap.parse_args()

    print("="*60)
    print("  太乙互搏 AGI（TOMAS-AGI）— 主模拟器 v2.0")
    print("="*60)

    if args.mode == "full":
        results = {}
        results["octonion"] = test_octonion()
        results["spectral"] = test_spectral()
        results["nasga"] = test_nasga()
        results["fold_depth"] = test_fold_depth()
        results["a6bs"] = test_a6bs()
        results["xi_c"] = test_xi_c()
        results["drift_detector"] = test_drift_detector()
        results["delta_mem"] = test_delta_mem()
        print("\n" + "="*60 + "\n全量诊断总结" + "\n" + "="*60)
        n = 0
        for k, (ok, _) in results.items():
            print(f"  {k:20s}: [{'PASS' if ok else 'FAIL'}]")
            n += 1 if ok else 0
        print(f"\n总体: [{n}/{len(results)} 通过]")
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                report = {}
                for k, (ok, d) in results.items():
                    report[k] = {"pass": ok, "detail": d}
                json.dump(report, f, indent=2, ensure_ascii=False)
            print(f"\n报告已保存: {args.output}")

    elif args.mode == "benchmark":
        test_a6bs()

    elif args.mode == "measure":
        m = mods.get("xi_c_measure")
        if m:
            results = m.measure_random_batch(num_samples=args.num_samples, seed=42)
            vals = [r["xi_c"] for r in results]
            import statistics
            print(f"xi_c 均值: {statistics.mean(vals):.6f}")
            print(f"xi_c 标准差: {statistics.stdev(vals):.6f}")
            if args.output:
                m.write_csv(results, args.output)
                print(f"结果已保存: {args.output}")
        else:
            print("[FAIL] xi_c_measure 未导入")

    elif args.mode == "interactive":
        print("交互模式：输入 Python 表达式（如 Octonion(1,0,0,0,0,0,0,0) * Octonion(0,1,0,0,0,0,0,0)）")
        print("输入 'quit' 退出")
        while True:
            try:
                line = input("TOMAS> ")
            except (EOFError, KeyboardInterrupt):
                break
            if line.strip() in ("quit","exit","q"):
                break
            try:
                result = eval(line, {"__builtins__": {}}, mods)
                print(f"  => {result}")
            except Exception as e:
                print(f"  [错误] {e}")

if __name__ == "__main__":
    main()
