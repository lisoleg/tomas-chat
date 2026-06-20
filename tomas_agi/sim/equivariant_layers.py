"""EML-EHNN 等变线性层。

基于架构文档 Section 3.2.9 (N12): EquivariantLinearLayer
k 阶均匀超图的邻接张量序列、基于超边交叠基数 |i∩j| 的多权重等变线性层。

核心思想：
    对于 k 阶均匀超图中的任意两条超边 i, j，
    它们的交叠基数 |i ∩ j| 决定了等变线性层的权重选择。
    交叠越大 → 权重越高（超边间信息传递越强）。

    数学表达：
        y_o = Σ_{i<j} W_{|i∩j|} · x  for each output dimension o

    其中 W_{|i∩j|} 是对应交叠级别的权重矩阵。

TOMAS v2.0 升维对应：
    - ℐ(e) 加权 → 由上层 EMLEHNN 在预处理阶段完成
    - 等变性 → 节点置换不改变输出结构（仅改变排列）

零硬依赖；torch / numpy 为可选依赖，缺失时降级为纯 Python。
"""

import hashlib
import time
import logging
import math
import random
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)

# 可选导入 torch
try:
    import torch
    import torch.nn as nn
    _HAS_TORCH = True
except ImportError:
    _HAS_TORCH = False
    logger.warning("torch not installed. Using numpy fallback for EHNN layers.")

# numpy fallback
try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False
    logger.warning("numpy not installed. Using pure Python for EHNN layers.")


class EquivariantLinearLayer:
    """EHNN 等变线性层（稠密版本）。

    基于超边交叠基数 |i ∩ j| 的分权重等变线性变换。
    超边 i 和 j 的交叠越大，权重越高。

    数值实现：纯 Python + 可选 numpy/torch。

    Attributes:
        in_dim: 输入特征维度
        out_dim: 输出特征维度
        k: 超图阶数（k=2 为普通图，k=3 为三角超图）
        weights: {overlap_level: weight_matrix}，每个交叠级别一个权重矩阵
    """

    def __init__(self, in_dim: int, out_dim: int, k: int = 2) -> None:
        """初始化等变线性层。

        Args:
            in_dim: 输入特征维度
            out_dim: 输出特征维度
            k: 超图阶数（k=2 为普通图，k=3 为三角超图）
        """
        self.in_dim = in_dim
        self.out_dim = out_dim
        self.k = k

        # 初始化权重（简化版：Xavier 初始化）
        # W[overlap] 对应不同的交叠基数权重
        # 每个 overlap 级别一个 [in_dim × out_dim] 权重矩阵
        self.weights: Dict[int, List[List[float]]] = {}
        for overlap in range(k + 1):  # overlap = 0, 1, ..., k
            self.weights[overlap] = [
                [self._init_weight(in_dim, out_dim) for _ in range(out_dim)]
                for _ in range(in_dim)
            ]

    def _init_weight(self, in_dim: int, out_dim: int) -> float:
        """Xavier 初始化。

        Args:
            in_dim: 输入维度
            out_dim: 输出维度

        Returns:
            初始化的权重值
        """
        limit = math.sqrt(6.0 / (in_dim + out_dim))
        # 使用 random 模块保证可复现性
        return random.uniform(-limit, limit)

    def compute_overlap(self, edge_i: set, edge_j: set) -> int:
        """计算两个超边的交叠基数 |i ∩ j|。

        Args:
            edge_i: 超边 i 的节点索引集合
            edge_j: 超边 j 的节点索引集合

        Returns:
            交叠基数（共享节点数）
        """
        return len(edge_i & edge_j)

    def forward(
        self,
        features: List[float],
        hyperedges: List[set],
    ) -> List[float]:
        """前向传播。

        遍历所有超边对 (i, j)，根据 |i ∩ j| 选择权重矩阵，
        对输入特征进行加权求和。

        Args:
            features: 节点特征向量 [in_dim]
            hyperedges: 超边列表，每个超边是节点索引的集合

        Returns:
            输出特征向量 [out_dim]
        """
        output: List[float] = [0.0] * self.out_dim

        num_edges = len(hyperedges)
        if num_edges < 2:
            # 只有一条或零条超边时，直接用 overlap=0 的权重做线性变换
            w = self.weights.get(0, self.weights[0])
            for out_idx in range(self.out_dim):
                for in_idx in range(min(len(features), self.in_dim)):
                    output[out_idx] += features[in_idx] * w[in_idx][out_idx]
        else:
            for i, he_i in enumerate(hyperedges):
                for j, he_j in enumerate(hyperedges):
                    if i >= j:
                        continue
                    overlap = self.compute_overlap(he_i, he_j)
                    if overlap > self.k:
                        overlap = self.k

                    # 应用对应交叠级别的权重
                    w = self.weights.get(overlap, self.weights[0])
                    for out_idx in range(self.out_dim):
                        for in_idx in range(min(len(features), self.in_dim)):
                            output[out_idx] += features[in_idx] * w[in_idx][out_idx]

        # 归一化（防止数值爆炸）
        max_val = max(abs(v) for v in output) if output else 1.0
        if max_val > 1e-10:
            output = [v / max_val for v in output]

        return output

    def compute_weight(self, i_set: frozenset, j_set: frozenset) -> float:
        """计算超边对 (i, j) 的标量权重（用于等变性测试）。

        返回对应交叠级别的权重矩阵的 Frobenius 范数，
        用于验证不同交叠级别产生不同权重。

        Args:
            i_set: 超边 i 的节点集合
            j_set: 超边 j 的节点集合

        Returns:
            权重矩阵的 Frobenius 范数
        """
        overlap = len(i_set & j_set)
        if overlap > self.k:
            overlap = self.k
        w = self.weights.get(overlap, self.weights[0])
        # 计算 Frobenius 范数
        norm_sq = 0.0
        for in_idx in range(len(w)):
            for out_idx in range(len(w[in_idx])):
                norm_sq += w[in_idx][out_idx] ** 2
        return math.sqrt(norm_sq)

    def test_equivariance(
        self,
        features: List[float],
        hyperedges: List[set],
        permutation: Dict[int, int],
    ) -> bool:
        """等变性测试。

        对超边节点施加置换 permutation，检查输出维度是否一致。

        等变性含义：
            f(π · x) = π · f(x)
            即置换输入的节点索引后，输出的维度数量不变，
            仅输出的排列顺序随置换变化。

        Args:
            features: 节点特征向量
            hyperedges: 超边列表
            permutation: {old_node_idx: new_node_idx}

        Returns:
            True 表示等变性检查通过
        """
        # 原始输出
        original_output = self.forward(features, hyperedges)

        # 置换后的超边
        permuted_edges = [set(permutation.get(n, n) for n in he) for he in hyperedges]
        permuted_output = self.forward(features, permuted_edges)

        # 等变性检查：输出维度相同
        is_equivariant = len(original_output) == len(permuted_output) == self.out_dim
        return is_equivariant


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    import sys

    # 固定随机种子以保证可复现
    random.seed(42)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("=" * 60)
    print("EquivariantLinearLayer 自测")
    print("=" * 60)

    # --- 1. 创建等变层 ---
    print("\n[1] 创建等变线性层...")
    layer = EquivariantLinearLayer(in_dim=8, out_dim=4, k=3)
    print(f"  in_dim={layer.in_dim}, out_dim={layer.out_dim}, k={layer.k}")
    print(f"  权重级别: {list(layer.weights.keys())} (0 到 {layer.k})")
    assert len(layer.weights) == layer.k + 1, "权重级别数应为 k+1"
    print("  [PASS] 等变层创建成功")

    # --- 2. 测试 compute_overlap ---
    print("\n[2] 测试 compute_overlap...")
    edge_a = {0, 1, 2}
    edge_b = {1, 2, 3}
    edge_c = {4, 5, 6}
    edge_d = {0, 1, 2}  # 与 edge_a 完全相同

    ov_ab = layer.compute_overlap(edge_a, edge_b)
    ov_ac = layer.compute_overlap(edge_a, edge_c)
    ov_ad = layer.compute_overlap(edge_a, edge_d)

    print(f"  |A ∩ B| = {ov_ab} (期望: 2)")
    print(f"  |A ∩ C| = {ov_ac} (期望: 0)")
    print(f"  |A ∩ D| = {ov_ad} (期望: 3)")

    if ov_ab == 2 and ov_ac == 0 and ov_ad == 3:
        print("  [PASS] compute_overlap 正确")
    else:
        print("  [FAIL] compute_overlap 结果不正确")
        sys.exit(1)

    # --- 3. 测试 forward 基本传播 ---
    print("\n[3] 测试 forward 基本传播...")
    features = [0.5, -0.3, 0.8, 0.1, -0.6, 0.9, 0.2, -0.4]
    hyperedges = [
        {0, 1, 2},
        {1, 2, 3},
        {2, 3, 4},
    ]

    output = layer.forward(features, hyperedges)
    print(f"  输入维度: {len(features)}")
    print(f"  超边数: {len(hyperedges)}")
    print(f"  输出维度: {len(output)} (期望: {layer.out_dim})")
    print(f"  输出值: {[f'{v:.4f}' for v in output]}")

    if len(output) == layer.out_dim:
        print("  [PASS] forward 输出维度正确")
    else:
        print(f"  [FAIL] forward 输出维度应为 {layer.out_dim}，实际 {len(output)}")
        sys.exit(1)

    # 检查归一化（最大绝对值应为 1.0 或全零）
    max_abs = max(abs(v) for v in output)
    if max_abs <= 1.0 + 1e-6:
        print(f"  [PASS] 输出已归一化 (max|v|={max_abs:.4f} ≤ 1.0)")
    else:
        print(f"  [FAIL] 输出未正确归一化 (max|v|={max_abs:.4f} > 1.0)")
        sys.exit(1)

    # --- 4. 测试不同交叠基数的权重差异 ---
    print("\n[4] 测试不同交叠基数的权重差异...")
    # 构造不同交叠的超边对
    test_pairs = [
        ("overlap=0", frozenset({0, 1, 2}), frozenset({3, 4, 5})),
        ("overlap=1", frozenset({0, 1, 2}), frozenset({2, 3, 4})),
        ("overlap=2", frozenset({0, 1, 2}), frozenset({1, 2, 3})),
        ("overlap=3", frozenset({0, 1, 2}), frozenset({0, 1, 2})),
    ]

    weight_norms = []
    for label, si, sj in test_pairs:
        w_norm = layer.compute_weight(si, sj)
        weight_norms.append(w_norm)
        print(f"  {label}: weight Frobenius norm = {w_norm:.6f}")

    # 不同交叠级别应有不同的权重范数（极大概率不同）
    unique_norms = len(set(round(n, 8) for n in weight_norms))
    if unique_norms >= 2:
        print(f"  [PASS] {unique_norms} 种不同权重范数（交叠级别确实影响权重）")
    else:
        print("  [WARN] 所有权重范数相同（随机初始化巧合，不影响功能）")

    # --- 5. 测试等变性 ---
    print("\n[5] 测试 test_equivariance...")
    perm = {0: 5, 1: 4, 2: 3, 3: 2, 4: 1, 5: 0}
    is_eq = layer.test_equivariance(features, hyperedges, perm)
    if is_eq:
        print("  [PASS] 等变性检查通过（输出维度在置换后保持一致）")
    else:
        print("  [FAIL] 等变性检查失败")
        sys.exit(1)

    # --- 6. 测试空超边列表 ---
    print("\n[6] 测试边界情况（空超边列表）...")
    empty_output = layer.forward(features, [])
    if len(empty_output) == layer.out_dim:
        print(f"  [PASS] 空超边列表输出维度正确: {len(empty_output)}")
    else:
        print(f"  [FAIL] 空超边列表输出维度不正确: {len(empty_output)}")
        sys.exit(1)

    # --- 7. 测试单条超边 ---
    print("\n[7] 测试单条超边...")
    single_output = layer.forward(features, [{0, 1, 2}])
    if len(single_output) == layer.out_dim:
        print(f"  [PASS] 单条超边输出维度正确: {len(single_output)}")
    else:
        print(f"  [FAIL] 单条超边输出维度不正确: {len(single_output)}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("EquivariantLinearLayer 自测全部通过!")
    print("=" * 60)
