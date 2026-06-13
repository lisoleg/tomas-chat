#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fold_depth_py.py —— 谱折叠深度 δ 参数与 A1 公理实现（TOMAS-AGI v2.0）

功能：
  1. 谱折叠深度 δ 的定义与计算
  2. A1 公理（δ 守恒）校验
  3. δ_threshold 条件（悖论耐受判断）
  4. δ 与 xi_c 的对偶关系

v2.0 核心升级：
  - v1.0 核心序参量是"非结合残联熵"
  - v2.0 核心序参量是"谱折叠深度 δ"
  - δ 控制系统的非结合谱图复杂度
  - δ 守恒（A1 公理）类比能量守恒

作者：章锋（章锋）© 2026 复合体理学研究中心（TOMAS 项目组）
"""

import math
import random
from typing import List, Tuple, Dict, Optional, Callable


# ============================================================
# 第1部分：谱折叠深度 δ 的定义与计算
# ============================================================

def compute_fold_depth(associator_norm: float, epsilon: float = 1e-10) -> float:
    """
    计算单个三元组的谱折叠深度 δ
    
    v2.0 定义：
      δ = ||[a,b,c]|| / (||a||·||b||·||c|| + ε)
      = xi_c(a,b,c)   （当 associator 非零时）
    
    含义：
      δ = 0  → 经典极限（布尔逻辑，结合代数）
      δ > 0  → 量子极限（允许矛盾共存，非结合代数）
      δ = 7  → 稳态锁定（κ=7 稳定性）
    
    参数：
      associator_norm: 结合子范数 ||[a,b,c]||
      epsilon: 防止除零的小量
    
    返回：
      δ: 谱折叠深度（无量纲，自然单位制）
    """
    return associator_norm  # 简化为 xi_c，完整定义见下文


def compute_delta_from_octonions(a: List[float], b: List[float], c: List[float],
                                e: List[float]) -> float:
    """
    从八元数值场计算 δ
    
    v2.0 定义（NASGA 框架 §2.1）：
      δ(i) = |φ(i)|_O / (|φ|_{avg} + ε)
      其中 φ: V → O 是八元数值场
    
    离散图版本：
      δ(e) = ||[a,b,c]|| / (||a||·||b||·||c||)
            = ξ_c(a,b,c)
    
    参数：
      a, b, c: 八元数（8 维实向量）
      e: Fano 平面基（8 维，e[0]=1 为实部）
    
    返回：
      δ: 谱折叠深度
    """
    # 计算结合子 [a,b,c] = (a*b)*c - a*(b*c)
    # 使用 octonion_py 的函数
    try:
        from octonion_py import Octonion, associator
        A = Octonion(a)
        B = Octonion(b)
        C = Octonion(c)
        assoc = associator(A, B, C)
        delta = assoc.norm() / (A.norm() * B.norm() * C.norm() + 1e-10)
        return delta
    except ImportError:
        # 简化计算（仅用于测试）
        return associator_norm_approx(a, b, c)


def associator_norm_approx(a: List[float], b: List[float], c: List[float]) -> float:
    """近似计算结合子范数（不依赖 octonion_py）"""
    # 使用随机八元数乘法近似
    # 实际实现应调用 octonion_py.associator()
    return 0.0  # placeholder


# ============================================================
# 第2部分：A1 公理（δ 守恒）校验
# ============================================================

def check_a1_axiom(delta_total_before: float, delta_total_after: float,
                   tolerance: float = 1e-7) -> Tuple[bool, str]:
    """
    校验 A1 公理：谱折叠深度守恒
    
    v2.0 A1 公理（§2.2）：
      对于任意封闭系统 S，其 EML 谱图的总谱折叠深度守恒：
        δ_total = constant
    
    A1' 可加正交分解：
      若系统 S 可正交分解为子系 S1, S2, ...
        δ_total = Σ_i δ_i
    
    参数：
      delta_total_before: 演化前的总 δ
      delta_total_after: 演化后的总 δ
      tolerance: 数值容差
    
    返回：
      (is_conserved, message)
    """
    diff = abs(delta_total_before - delta_total_after)
    is_conserved = diff < tolerance
    
    if is_conserved:
        msg = f"[A1 公理] δ 守恒成立: {delta_total_before:.6f} → {delta_total_after:.6f} (diff={diff:.2e})"
    else:
        msg = f"[A1 公理] ❌ δ 守恒破坏: {delta_total_before:.6f} → {delta_total_after:.6f} (diff={diff:.2e})"
    
    return is_conserved, msg


def compute_total_delta(eml_graph: Dict) -> float:
    """
    计算 EML 谱图的总谱折叠深度 δ_total
    
    参数：
      eml_graph: EML 图字典，格式：
        {
            'nodes': [{'id': 0, 'octonion': [8 维向量]}, ...],
            'edges': [{'src': 0, 'dst': 1}, ...]
        }
    
    返回：
      delta_total: 总谱折叠深度
    """
    # 简化：返回所有边的 δ 之和
    # 完整实现需要对所有三元组计算 δ
    delta_total = 0.0
    
    nodes = eml_graph.get('nodes', [])
    edges = eml_graph.get('edges', [])
    
    # 对每个边 (i,j)，计算 δ(e_i, e_j, e_k) 对所有 k
    for edge in edges:
        i = edge['src']
        j = edge['dst']
        # 获取节点 i, j 的八元数
        if i < len(nodes) and j < len(nodes):
            a = nodes[i].get('octonion', [0]*8)
            b = nodes[j].get('octonion', [0]*8)
            # 对所有其他节点 k 计算 δ(a,b,c_k)
            for k, node_k in enumerate(nodes):
                if k != i and k != j:
                    c = node_k.get('octonion', [0]*8)
                    delta = compute_delta_from_octonions(a, b, c, [])
                    delta_total += delta
    
    return delta_total


# ============================================================
# 第3部分：δ_threshold 条件（悖论耐受判断）
# ============================================================

def check_delta_threshold(delta: float, delta_critical: float = 0.5) -> Tuple[bool, str]:
    """
    检查 δ 是否满足阈值条件（悖论耐受）
    
    v2.0 推论 4.2.3（δ 阈值条件，§4.2）：
      要保持悖论耐受，EML 谱图的的有效折叠深度必须满足：
        δ ≥ δ_critical
      
      当 δ < δ_critical 时，谱结合子过小，系统退化为近似结合代数，
      丧失双分歧态保留能力（悖论不耐受）。
    
    参数：
      delta: 当前谱折叠深度
      delta_critical: 临界折叠深度（默认 0.5）
    
    返回：
      (is_paradox_tolerant, message)
    """
    is_tolerant = delta >= delta_critical
    
    if is_tolerant:
        msg = f"[δ 阈值] ✅ 悖论耐受 (δ={delta:.4f} ≥ δ_critical={delta_critical:.2f})"
    else:
        msg = f"[δ 阈值] ❌ 悖论不耐受 (δ={delta:.4f} < δ_critical={delta_critical:.2f})"
    
    return is_tolerant, msg


def classify_delta_regime(delta: float) -> str:
    """
    分类 δ 所在的 regime（经典/量子/稳态）
    
    返回：
      regime: 'classical' | 'quantum' | 'stable' | 'deep_quantum'
    """
    if delta < 0.1:
        return 'classical'      # 布尔逻辑，结合代数
    elif delta < 2.0:
        return 'quantum'        # 非结合，允许矛盾
    elif abs(delta - 7.0) < 0.5:
        return 'stable'         # κ=7 稳态锁定
    else:
        return 'deep_quantum'  # 深度非结合


# ============================================================
# 第4部分：δ 与 xi_c 的对偶关系
# ============================================================

def delta_xi_c_duality(delta: float, xi_c: float) -> Dict[str, float]:
    """
    δ 与 xi_c 的对偶关系（v2.0 升级要点）
    
    v2.0 中：
      xi_c 是 "非结合残联熵" 的替代指标
      delta 是 "谱折叠深度"，是更基本的序参量
      
    对偶关系：
      xi_c ≈ delta   （当结合子非零时）
      delta = 0  ⇔  xi_c = 0  （结合代数极限）
      delta > 0  ⇔  xi_c > 0  （非结合代数）
    
    参数：
      delta: 谱折叠深度
      xi_c: 非结合残联熵（旧指标）
    
    返回：
      duality: 对偶关系检查结果
    """
    # 理论关系：xi_c 是 delta 的单调函数
    xi_c_theory = delta  # 简化：假设 xi_c = delta
    diff = abs(xi_c - xi_c_theory)
    
    return {
        'delta': delta,
        'xi_c': xi_c,
        'xi_c_theory': xi_c_theory,
        'diff': diff,
        'is_consistent': diff < 0.1
    }


# ============================================================
# 第5部分：测试函数
# ============================================================

def test_fold_depth_basic() -> List[str]:
    """测试 δ 基本计算"""
    errors = []
    
    # 测试 1：δ = 0（结合代数）
    delta1 = compute_fold_depth(0.0)
    if abs(delta1) > 1e-10:
        errors.append(f"δ=0 失败: {delta1}")
    
    # 测试 2：δ > 0（非结合代数）
    delta2 = compute_fold_depth(1.5)
    if abs(delta2 - 1.5) > 1e-10:
        errors.append(f"δ=1.5 失败: {delta2}")
    
    return errors


def test_a1_axiom() -> List[str]:
    """测试 A1 公理（δ 守恒）"""
    errors = []
    
    # 模拟 δ 守恒
    delta_before = 3.14159
    delta_after = delta_before + 1e-8  # 微小数值误差
    is_conserved, msg = check_a1_axiom(delta_before, delta_after)
    if not is_conserved:
        errors.append(f"A1 公理误判: {msg}")
    
    # 模拟 δ 不守恒
    delta_after_bad = delta_before + 0.5
    is_conserved_bad, msg_bad = check_a1_axiom(delta_before, delta_after_bad)
    if is_conserved_bad:
        errors.append(f"A1 公理漏检: {msg_bad}")
    
    return errors


def test_delta_threshold() -> List[str]:
    """测试 δ 阈值条件"""
    errors = []
    
    # δ < δ_critical（悖论不耐受）
    is_tolerant1, _ = check_delta_threshold(0.1, 0.5)
    if is_tolerant1:
        errors.append("δ=0.1 应判为不耐受")
    
    # δ ≥ δ_critical（悖论耐受）
    is_tolerant2, _ = check_delta_threshold(0.7, 0.5)
    if not is_tolerant2:
        errors.append("δ=0.7 应判为耐受")
    
    return errors


def run_all_tests(verbose: bool = True) -> int:
    """运行所有测试，返回失败数"""
    if verbose:
        print("=" * 60)
        print("fold_depth_py.py 测试套件（TOMAS-AGI v2.0）")
        print("=" * 60)
    
    all_errors = []
    
    # 测试第1部分：δ 基本计算
    if verbose:
        print("\n[测试] 第1部分：谱折叠深度 δ 计算")
    errs1 = test_fold_depth_basic()
    all_errors.extend(errs1)
    if verbose:
        print(f"  结果: {'PASS' if not errs1 else 'FAIL'} ({len(errs1)} 错误)")
    
    # 测试第2部分：A1 公理
    if verbose:
        print("\n[测试] 第2部分：A1 公理（δ 守恒）")
    errs2 = test_a1_axiom()
    all_errors.extend(errs2)
    if verbose:
        print(f"  结果: {'PASS' if not errs2 else 'FAIL'} ({len(errs2)} 错误)")
    
    # 测试第3部分：δ 阈值
    if verbose:
        print("\n[测试] 第3部分：δ 阈值条件（悖论耐受）")
    errs3 = test_delta_threshold()
    all_errors.extend(errs3)
    if verbose:
        print(f"  结果: {'PASS' if not errs3 else 'FAIL'} ({len(errs3)} 错误)")
    
    # 总结
    if verbose:
        print(f"\n{'=' * 60}")
        print(f"总计: {len(all_errors)} 错误")
        if all_errors:
            print("\n错误详情:")
            for e in all_errors:
                print(f"  - {e}")
        print(f"{'=' * 60}")
    
    return len(all_errors)


if __name__ == "__main__":
    n_errors = run_all_tests(verbose=True)
    exit(0 if n_errors == 0 else 1)
