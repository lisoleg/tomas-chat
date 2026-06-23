# -*- coding: utf-8 -*-
"""
叠加态几何 — 从叠加态到几何涌现
Superposition Geometry — From Superposition to Geometric Emergence

基于文章1《从叠加态到几何涌现》：
- Anthropic叠加态玩具模型的TOMAS-IDO解释
- Thomson问题（球面电子排布）与特征几何
- E8格最优堆积与干扰最小化
- 相变检测与特权基分析
- 对抗脆弱性与MDL最优编码

Author: TOMAS Team (Kou / 寇豆码·工程师)
Version: v3.14
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


# ════════════════════════════════════════════════════════════════╗
# ║               SuperpositionConfig — 配置参数                       ║
# ╚═══════════════════════════════════════════════════════════════╝

@dataclass
class SuperpositionConfig:
    """叠加态几何配置参数

    Attributes:
        n_features: 特征数量
        n_dims: 嵌入空间维度
        sparsity: 特征稀疏度 (0=完全稀疏, 1=完全密集)
        feature_importance: 各特征重要性权重
        learning_rate: 梯度下降学习率
        n_sphere_dims: 球面维度（默认3）
    """

    n_features: int = 10
    n_dims: int = 8
    sparsity: float = 0.5
    feature_importance: np.ndarray = field(default_factory=lambda: np.ones(10))
    learning_rate: float = 0.01
    n_sphere_dims: int = 3

    def __post_init__(self) -> None:
        """初始化后校验"""
        if self.n_features <= 0:
            raise ValueError(f"n_features 必须 > 0，实际: {self.n_features}")
        if not 0.0 <= self.sparsity <= 1.0:
            raise ValueError(f"sparsity 必须在 [0, 1]，实际: {self.sparsity}")
        if len(self.feature_importance) < self.n_features:
            padded = np.ones(self.n_features)
            padded[:len(self.feature_importance)] = self.feature_importance
            self.feature_importance = padded

    def effective_density(self) -> float:
        """有效特征密度 = n_features * (1 - sparsity) / n_dims"""
        return self.n_features * (1.0 - self.sparsity) / max(self.n_dims, 1)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "n_features": self.n_features,
            "n_dims": self.n_dims,
            "sparsity": self.sparsity,
            "feature_importance": self.feature_importance.tolist(),
            "learning_rate": self.learning_rate,
            "n_sphere_dims": self.n_sphere_dims,
            "effective_density": self.effective_density(),
        }


# ════════════════════════════════════════════════════════════════╗
# ║               ThomsonProblemSolver — 球面电子排布求解器             ║
# ╚═══════════════════════════════════════════════════════════════╝

class ThomsonProblemSolver:
    """Thomson问题求解器 — 在单位球面上均匀分布点

    通过梯度下降最小化斥力能 E = Σ_{i<j} 1/|r_i - r_j|，
    使n个点在球面上达到能量最优构型。
    对应叠加态中特征在表征空间中的几何排布。
    """

    # 已知的几何类型映射
    _GEOMETRY_TYPES: Dict[int, str] = {
        2: "antipodal_pair",
        3: "triangle",
        4: "tetrahedron",
        5: "triangular_bipyramid",
        6: "octahedron",
        7: "pentagonal_bipyramid",
        8: "square_antiprism",
        12: "icosahedron",
    }

    def __init__(self, learning_rate: float = 0.01, seed: int = 42) -> None:
        """初始化求解器

        Args:
            learning_rate: 梯度下降步长
            seed: 随机种子（保证可复现性）
        """
        self.learning_rate = learning_rate
        self.seed = seed
        self._rng = np.random.default_rng(seed)
        self.history: List[float] = []

    def energy(self, positions: np.ndarray) -> float:
        """计算总斥力能

        E = Σ_{i<j} 1 / |r_i - r_j|

        Args:
            positions: (n, 3) 球面上的点坐标

        Returns:
            总斥力能
        """
        n = positions.shape[0]
        total = 0.0
        for i in range(n):
            diffs = positions[i] - positions
            dists = np.linalg.norm(diffs, axis=1)
            dists[i] = float("inf")  # 排除自身
            inv_dists = 1.0 / dists
            total += np.sum(inv_dists)
        return total / 2.0  # 每对计算了两次

    def _compute_gradient(self, positions: np.ndarray) -> np.ndarray:
        """计算斥力能关于位置的梯度（修正符号）

        E = Σ_{i<j} 1/|r_i - r_j|
        ∂E/∂r_i = -Σ_{j≠i} (r_i - r_j) / |r_i - r_j|^3

        注意：梯度指向能量增加方向，梯度下降时用 positions -= lr * gradient。
        """
        n = positions.shape[0]
        gradient = np.zeros_like(positions)
        for i in range(n):
            diffs = positions[i] - positions  # (n, 3)
            dists = np.linalg.norm(diffs, axis=1)  # (n,)
            dists[i] = 1.0  # 避免除零
            inv_d3 = 1.0 / (dists ** 3)
            inv_d3[i] = 0.0
            # 正确的梯度 = -Σ (r_i - r_j) / |r_i - r_j|^3
            gradient[i] = -np.sum(diffs * inv_d3[:, np.newaxis], axis=0)
        return gradient

    def _fibonacci_sphere_init(self, n_points: int) -> np.ndarray:
        """斐波那契球面初始化 — 均匀分布的优良起点

        使用黄金角螺旋在球面上生成近似均匀分布的点，
        作为梯度下降的起点，大幅加速收敛并避免局部最优。

        Args:
            n_points: 点的数量

        Returns:
            (n_points, 3) 单位球面上的初始位置
        """
        positions = np.zeros((n_points, 3))
        golden_angle: float = math.pi * (3.0 - math.sqrt(5.0))
        for i in range(n_points):
            y = 1.0 - 2.0 * i / max(n_points - 1, 1)
            radius = math.sqrt(max(1.0 - y * y, 0.0))
            theta = golden_angle * i
            positions[i] = [
                math.cos(theta) * radius,
                y,
                math.sin(theta) * radius,
            ]
        return self._project_to_sphere(positions)

    def _project_to_sphere(self, positions: np.ndarray) -> np.ndarray:
        """将点投影回单位球面"""
        norms = np.linalg.norm(positions, axis=1, keepdims=True)
        norms = np.where(norms < 1e-12, 1e-12, norms)
        return positions / norms

    def solve(self, n_points: int, max_iter: int = 1000) -> np.ndarray:
        """在单位球面上均匀分布 n_points 个点

        Args:
            n_points: 点的数量
            max_iter: 最大迭代次数

        Returns:
            (n_points, 3) 最优位置矩阵
        """
        if n_points <= 0:
            raise ValueError(f"n_points 必须 > 0，实际: {n_points}")
        if n_points == 1:
            return np.array([[1.0, 0.0, 0.0]])

        # 斐波那契球面初始化（比随机初始化更均匀，加速收敛）
        positions = self._fibonacci_sphere_init(n_points)

        self.history = []
        # 动量加速梯度下降
        momentum = np.zeros_like(positions)
        momentum_coeff: float = 0.9

        for iteration in range(max_iter):
            grad = self._compute_gradient(positions)
            # 梯度裁剪：防止梯度爆炸
            grad_norm = float(np.linalg.norm(grad))
            if grad_norm > 10.0:
                grad = grad * (10.0 / grad_norm)
            # 动量更新（最小化能量）
            momentum = momentum_coeff * momentum - self.learning_rate * grad
            positions += momentum
            # 投影回球面
            positions = self._project_to_sphere(positions)

            e = self.energy(positions)
            self.history.append(e)

            # 收敛判断
            if len(self.history) > 10:
                recent = self.history[-10:]
                if max(recent) - min(recent) < 1e-10:
                    break

        return positions

    def get_geometry_type(self, n: int) -> str:
        """返回 n 个点的几何类型名称

        Args:
            n: 点的数量

        Returns:
            几何类型字符串
        """
        return self._GEOMETRY_TYPES.get(n, f"unknown_n{n}")

    def symmetry_group(self, n: int) -> str:
        """返回 n 个点的对称群名称"""
        sym_map: Dict[int, str] = {
            2: "D_inf_h",
            3: "D_3h",
            4: "T_d",
            6: "O_h",
            12: "I_h",
        }
        return sym_map.get(n, f"C_{n}")


# ════════════════════════════════════════════════════════════════╗
# ║               E8LatticePacker — E8格堆积器                        ║
# ╚═══════════════════════════════════════════════════════════════╝

class E8LatticePacker:
    """E8格堆积器 — 8维最优球面堆积

    E8格是8维空间中密度最高的格堆积，堆积密度为 π⁴/384 ≈ 0.2537。
    在叠加态中，将特征嵌入E8格结构可最小化特征间干扰。
    """

    # E8格的堆积密度
    _PACKING_DENSITY: float = math.pi ** 4 / 384.0

    # E8格的8个基向量（D8格的规范基）
    _E8_BASIS: np.ndarray = np.array([
        [2, 0, 0, 0, 0, 0, 0, 0],
        [-1, 1, 0, 0, 0, 0, 0, 0],
        [0, -1, 1, 0, 0, 0, 0, 0],
        [0, 0, -1, 1, 0, 0, 0, 0],
        [0, 0, 0, -1, 1, 0, 0, 0],
        [0, 0, 0, 0, -1, 1, 0, 0],
        [0, 0, 0, 0, 0, -1, 1, 0],
        [1, 1, 1, 1, 1, 1, 1, 1],
    ], dtype=float) / 2.0

    def __init__(self) -> None:
        """初始化E8格堆积器"""
        self.basis = self._E8_BASIS.copy()
        self.dim = 8

    def packing_density(self) -> float:
        """返回E8格的堆积密度 π⁴/384"""
        return self._PACKING_DENSITY

    def _quantize_to_e8(self, vector: np.ndarray) -> np.ndarray:
        """将向量量化到最近的E8格点

        E8格 = {x ∈ Z^8 ∪ (Z+1/2)^8 : Σx_i ≡ 0 (mod 2)}

        Args:
            vector: 8维实向量

        Returns:
            最近的E8格点
        """
        # 尝试整数格点
        int_round = np.round(vector).astype(float)
        if int_round.sum() % 2 == 0:
            return int_round

        # 尝试半整数格点
        half_round = np.floor(vector + 0.5).astype(float) - 0.5
        if half_round.sum() % 2 == 0:
            return half_round

        # 取距离更近的
        dist_int = np.linalg.norm(vector - int_round)
        dist_half = np.linalg.norm(vector - half_round)

        # 微调使和为偶数
        if dist_int <= dist_half:
            result = int_round.copy()
            # 找到最近的可调整位置
            min_dist = float("inf")
            best = result
            for i in range(len(result)):
                candidate = result.copy()
                candidate[i] += 1 if vector[i] - result[i] > 0 else -1
                if candidate.sum() % 2 == 0:
                    d = np.linalg.norm(vector - candidate)
                    if d < min_dist:
                        min_dist = d
                        best = candidate
            return best
        else:
            result = half_round.copy()
            min_dist = float("inf")
            best = result
            for i in range(len(result)):
                candidate = result.copy()
                candidate[i] += 1 if vector[i] - result[i] > 0 else -1
                if candidate.sum() % 2 == 0:
                    d = np.linalg.norm(vector - candidate)
                    if d < min_dist:
                        min_dist = d
                        best = candidate
            return best

    def pack(self, features: np.ndarray, n_dims: int = 8) -> np.ndarray:
        """将特征嵌入E8格结构

        Args:
            features: (n_features, feature_dim) 特征矩阵
            n_dims: 嵌入维度（默认8）

        Returns:
            (n_features, n_dims) E8格嵌入矩阵
        """
        features = np.asarray(features, dtype=float)
        if features.ndim == 1:
            features = features.reshape(1, -1)

        n_features = features.shape[0]
        feat_dim = features.shape[1]

        # 将特征映射到n_dims维空间
        if feat_dim < n_dims:
            padded = np.zeros((n_features, n_dims))
            padded[:, :feat_dim] = features
        elif feat_dim > n_dims:
            padded = features[:, :n_dims]
        else:
            padded = features.copy()

        # 量化到E8格
        embedding = np.zeros((n_features, n_dims))
        for i in range(n_features):
            embedding[i] = self._quantize_to_e8(padded[i])

        return embedding

    def interference_matrix(self, embedding: np.ndarray) -> np.ndarray:
        """计算特征间干扰矩阵

        干扰矩阵 = 特征间归一化内积的绝对值
        对角线为1（自干扰），非对角线为特征间干扰。

        Args:
            embedding: (n_features, n_dims) 嵌入矩阵

        Returns:
            (n_features, n_features) 干扰矩阵
        """
        n = embedding.shape[0]
        norms = np.linalg.norm(embedding, axis=1, keepdims=True)
        norms = np.where(norms < 1e-12, 1e-12, norms)
        normalized = embedding / norms
        interference = np.abs(normalized @ normalized.T)
        return interference

    def kissing_number(self) -> int:
        """返回E8格的接吻数（240）"""
        return 240

    def minimal_norm(self) -> float:
        """返回E8格的最短向量长度（√2）"""
        return math.sqrt(2.0)


# ════════════════════════════════════════════════════════════════╗
# ║               PhaseTransitionDetector — 相变检测器                  ║
# ╚═══════════════════════════════════════════════════════════════╝

class PhaseTransitionDetector:
    """相变检测器 — 检测叠加态-正交态相变

    在特征稀疏度变化时，表征策略会发生一级相变：
    - 高稀疏度 → 叠加态（特征共享神经元）
    - 低稀疏度 → 正交态（每个特征独占神经元）
    - 极低重要性 → 被忽略
    """

    def __init__(self, derivative_threshold: float = 0.5) -> None:
        """初始化相变检测器

        Args:
            derivative_threshold: 导数跳变阈值
        """
        self.derivative_threshold = derivative_threshold

    def detect(self, sparsity_series: np.ndarray,
               error_series: np.ndarray) -> Dict[str, Any]:
        """检测一级相变点（导数不连续）

        Args:
            sparsity_series: 稀疏度序列
            error_series: 对应的重构误差序列

        Returns:
            包含相变点信息的字典
        """
        sparsity_series = np.asarray(sparsity_series, dtype=float)
        error_series = np.asarray(error_series, dtype=float)

        if len(sparsity_series) < 3:
            return {
                "phase_transition_found": False,
                "transition_index": -1,
                "transition_sparsity": None,
                "max_derivative_jump": 0.0,
                "message": "序列太短，无法检测相变",
            }

        # 计算误差关于稀疏度的导数
        derivs = np.zeros(len(sparsity_series) - 1)
        for i in range(len(derivs)):
            ds = sparsity_series[i + 1] - sparsity_series[i]
            if abs(ds) < 1e-12:
                derivs[i] = 0.0
            else:
                derivs[i] = (error_series[i + 1] - error_series[i]) / ds

        # 检测导数跳变
        second_derivs = np.diff(derivs)
        max_jump_idx = int(np.argmax(np.abs(second_derivs)))
        max_jump = float(np.abs(second_derivs[max_jump_idx]))

        transition_found = max_jump > self.derivative_threshold

        return {
            "phase_transition_found": transition_found,
            "transition_index": max_jump_idx + 1,
            "transition_sparsity": float(sparsity_series[max_jump_idx + 1]),
            "max_derivative_jump": max_jump,
            "derivatives": derivs.tolist(),
            "second_derivatives": second_derivs.tolist(),
            "message": "相变检测完成",
        }

    def classify_phase(self, sparsity: float, importance: float) -> str:
        """分类当前相态

        Args:
            sparsity: 特征稀疏度 [0, 1]
            importance: 特征重要性 [0, 1]

        Returns:
            "ignored" / "superposition" / "orthogonal"
        """
        if importance < 0.1:
            return "ignored"
        if sparsity > 0.5:
            return "superposition"
        return "orthogonal"

    def critical_sparsity(self, n_features: int, n_neurons: int) -> float:
        """计算临界稀疏度

        临界稀疏度 ≈ n_features / (2 * n_neurons)
        当稀疏度超过此值时，叠加态成为最优策略。

        Args:
            n_features: 特征数
            n_neurons: 神经元数

        Returns:
            临界稀疏度
        """
        if n_neurons <= 0:
            return 1.0
        return min(1.0, n_features / (2.0 * n_neurons))


# ════════════════════════════════════════════════════════════════╗
# ║               PrivilegedBasisAnalyzer — 特权基分析器                ║
# ╚═══════════════════════════════════════════════════════════════╝

class PrivilegedBasisAnalyzer:
    """特权基分析器 — 分析ReLU引入的对称性破缺

    ReLU激活函数打破了表征空间的旋转对称性，
    产生"特权基"（privileged basis），使得神经元倾向于表示单一特征。
    """

    def __init__(self, monosemantic_threshold: float = 0.7) -> None:
        """初始化特权基分析器

        Args:
            monosemantic_threshold: 单语义判定阈值
        """
        self.monosemantic_threshold = monosemantic_threshold

    def analyze(self, activations: np.ndarray,
                has_relu: bool) -> Dict[str, Any]:
        """分析ReLU引入的对称性破缺

        Args:
            activations: (n_samples, n_neurons) 激活值矩阵
            has_relu: 是否使用ReLU激活

        Returns:
            分析结果字典
        """
        activations = np.asarray(activations, dtype=float)
        n_neurons = activations.shape[1]

        # 计算每个神经元的激活分布偏度
        skewness = np.zeros(n_neurons)
        for j in range(n_neurons):
            col = activations[:, j]
            mean = np.mean(col)
            std = np.std(col)
            if std > 1e-12:
                skewness[j] = np.mean(((col - mean) / std) ** 3)
            else:
                skewness[j] = 0.0

        # ReLU引入正偏度（激活集中在正值侧）
        if has_relu:
            symmetry_broken = np.mean(skewness > 0.5)
        else:
            symmetry_broken = np.mean(np.abs(skewness) > 0.5) * 0.3

        mono_ratio = self.monosemantic_ratio(activations)

        return {
            "has_relu": has_relu,
            "n_neurons": n_neurons,
            "mean_skewness": float(np.mean(skewness)),
            "skewness": skewness.tolist(),
            "symmetry_broken_ratio": float(symmetry_broken),
            "monosemantic_ratio": mono_ratio,
            "privileged_basis_detected": bool(symmetry_broken > 0.5 and has_relu),
        }

    def monosemantic_ratio(self, activations: np.ndarray) -> float:
        """计算单语义神经元比例

        单语义神经元 = 对单一特征响应强烈、对其他特征响应弱的神经元。
        通过激活模式的最大载荷占比来判定。

        Args:
            activations: (n_samples, n_neurons) 激活值矩阵

        Returns:
            单语义神经元比例 [0, 1]
        """
        activations = np.asarray(activations, dtype=float)
        n_neurons = activations.shape[1]
        if n_neurons == 0:
            return 0.0

        # 对每个神经元，计算其激活值的稀疏度
        # 稀疏激活 → 单语义
        monosemantic_count = 0
        for j in range(n_neurons):
            col = activations[:, j]
            col_abs = np.abs(col)
            total = np.sum(col_abs)
            if total < 1e-12:
                continue
            # 最大载荷占比
            max_ratio = np.max(col_abs) / total
            if max_ratio > self.monosemantic_threshold:
                monosemantic_count += 1

        return monosemantic_count / n_neurons

    def basis_alignment(self, activations: np.ndarray,
                        feature_matrix: np.ndarray) -> float:
        """计算激活基与特征基的对齐度

        Args:
            activations: (n_samples, n_neurons) 激活值
            feature_matrix: (n_samples, n_features) 特征矩阵

        Returns:
            对齐度 [0, 1]
        """
        # SVD分解激活矩阵
        U, S, Vt = np.linalg.svd(activations, full_matrices=False)
        # SVD分解特征矩阵
        Uf, Sf, Vtf = np.linalg.svd(feature_matrix, full_matrices=False)

        # 计算主成分间的余弦相似度
        k = min(Vt.shape[0], Vtf.shape[0])
        alignment = 0.0
        for i in range(k):
            cos_sim = np.abs(np.dot(Vt[i], Vtf[i]))
            alignment += cos_sim
        return float(alignment / k) if k > 0 else 0.0


# ════════════════════════════════════════════════════════════════╗
# ║               AdversarialVulnerabilityMetric — 对抗脆弱性度量      ║
# ╚═══════════════════════════════════════════════════════════════╝

class AdversarialVulnerabilityMetric:
    """对抗脆弱性度量 — 叠加态引入的对抗脆弱性

    在叠加态中，特征间非对角耦合（干扰）导致对抗扰动可以通过
    一个特征的通道影响其他特征，增加对抗脆弱性。
    """

    def __init__(self) -> None:
        """初始化对抗脆弱性度量器"""
        self.packer = E8LatticePacker()

    def interference_coupling(self, embedding: np.ndarray) -> float:
        """计算非对角耦合项

        非对角耦合 = 干扰矩阵非对角元素的平均绝对值。
        干扰越大，对抗脆弱性越高。

        Args:
            embedding: (n_features, n_dims) 嵌入矩阵

        Returns:
            非对角耦合强度
        """
        interference = self.packer.interference_matrix(embedding)
        n = interference.shape[0]
        if n <= 1:
            return 0.0
        # 取非对角元素
        mask = ~np.eye(n, dtype=bool)
        off_diag = interference[mask]
        return float(np.mean(off_diag))

    def vulnerability_score(self, embedding: np.ndarray) -> float:
        """返回0-1的脆弱性评分

        脆弱性 = sigmoid(α * 干扰耦合 + β * 条件数)

        Args:
            embedding: (n_features, n_dims) 嵌入矩阵

        Returns:
            脆弱性评分 [0, 1]
        """
        coupling = self.interference_coupling(embedding)

        # 条件数（衡量嵌入矩阵的数值稳定性）
        try:
            svd_vals = np.linalg.svd(embedding, compute_uv=False)
            if svd_vals[0] > 1e-12:
                cond_number = float(svd_vals[0] / (svd_vals[-1] + 1e-12))
            else:
                cond_number = 1.0
        except np.linalg.LinAlgError:
            cond_number = 1.0

        # sigmoid组合
        alpha = 3.0
        beta = 0.1
        score = 1.0 / (1.0 + math.exp(-(alpha * coupling + beta * math.log(max(cond_number, 1.0)))))
        return float(min(max(score, 0.0), 1.0))

    def perturbation_sensitivity(self, embedding: np.ndarray,
                                  epsilon: float = 0.01) -> float:
        """计算扰动敏感度

        对嵌入施加epsilon级扰动后，干扰耦合的变化量。

        Args:
            embedding: (n_features, n_dims) 嵌入矩阵
            epsilon: 扰动幅度

        Returns:
            扰动敏感度
        """
        original_coupling = self.interference_coupling(embedding)

        # 施加随机扰动
        rng = np.random.default_rng(42)
        perturbed = embedding + epsilon * rng.standard_normal(embedding.shape)

        perturbed_coupling = self.interference_coupling(perturbed)

        sensitivity = abs(perturbed_coupling - original_coupling) / max(epsilon, 1e-12)
        return float(sensitivity)


# ════════════════════════════════════════════════════════════════╗
# ║               SuperpositionTheorem — 理论定理容器                   ║
# ╚═══════════════════════════════════════════════════════════════╝

class SuperpositionTheorem:
    """叠加态理论定理容器 — 可证伪的理论预言

    包含叠加态几何的核心理论定理和可证伪预言。
    """

    @staticmethod
    def mdl_optimal_strategy(sparsity: float) -> str:
        """稀疏时叠加态是MDL最优编码

        MDL原则：最小描述长度。
        当特征稀疏度 > 临界值时，叠加态编码（特征共享神经元）
        比正交编码（每个特征独占神经元）的MDL更短。

        Args:
            sparsity: 特征稀疏度 [0, 1]

        Returns:
            "superposition" 或 "orthogonal"
        """
        # 临界稀疏度约为0.5
        critical = 0.5
        if sparsity > critical:
            return "superposition"
        return "orthogonal"

    @staticmethod
    def falsifiable_predictions() -> List[Dict[str, str]]:
        """返回可证伪预言列表

        每条预言都是可以通过实验验证或否证的。

        Returns:
            可证伪预言列表
        """
        return [
            {
                "id": "SP-01",
                "prediction": "稀疏特征训练的模型中，叠加态编码的MDL比正交编码短",
                "falsification": "在sparsity>0.5时，正交编码MDL更短则证伪",
            },
            {
                "id": "SP-02",
                "prediction": "叠加态模型的对抗脆弱性与特征间干扰耦合正相关",
                "falsification": "干扰耦合高但对抗鲁棒性也高则证伪",
            },
            {
                "id": "SP-03",
                "prediction": "ReLU激活引入特权基，导致单语义神经元比例上升",
                "falsification": "ReLU模型与无ReLU模型单语义比例无差异则证伪",
            },
            {
                "id": "SP-04",
                "prediction": "在临界稀疏度处存在一级相变（导数不连续）",
                "falsification": "稀疏度-误差曲线在临界点平滑过渡则证伪",
            },
            {
                "id": "SP-05",
                "prediction": "E8格嵌入的干扰低于随机嵌入",
                "falsification": "E8格嵌入干扰 ≥ 随机嵌入则证伪",
            },
        ]


# ════════════════════════════════════════════════════════════════╗
# ║               自测 (≥25 测试)                                      ║
# ╚═══════════════════════════════════════════════════════════════╝

def _self_test() -> Tuple[int, int, List[str]]:
    """模块自测 — superposition_geometry v3.14

    Returns:
        (passed, failed, details) 元组
    """
    print("=" * 64)
    print("Superposition Geometry v3.14 Self-Test (TOMAS AGI)")
    print("=" * 64)

    passed = 0
    failed = 0
    details: List[str] = []

    def check(name: str, condition: bool, detail: str = ""):
        nonlocal passed, failed
        if condition:
            passed += 1
            status = "PASS"
        else:
            failed += 1
            status = "FAIL"
            details.append(f"{name}: {detail}")
        print(f"  [{status}] {name}{' — ' + detail if detail and not condition else ''}")

    # ── Test 01-05: SuperpositionConfig ──
    cfg = SuperpositionConfig(n_features=5, n_dims=8, sparsity=0.7)
    check("T01: Config n_features", cfg.n_features == 5)
    check("T02: Config n_dims", cfg.n_dims == 8)
    check("T03: Config sparsity", cfg.sparsity == 0.7)
    check("T04: Config effective_density > 0", cfg.effective_density() > 0)
    check("T05: Config to_dict 含字段", "effective_density" in cfg.to_dict())

    # ── Test 06-07: Config 异常 ──
    try:
        SuperpositionConfig(n_features=0)
        check("T06: n_features=0 异常", False)
    except ValueError:
        check("T06: n_features=0 异常", True)

    try:
        SuperpositionConfig(sparsity=1.5)
        check("T07: sparsity=1.5 异常", False)
    except ValueError:
        check("T07: sparsity=1.5 异常", True)

    # ── Test 08-14: ThomsonProblemSolver ──
    solver = ThomsonProblemSolver(learning_rate=0.005, seed=42)
    pos2 = solver.solve(2, max_iter=200)
    check("T08: solve(2) 形状", pos2.shape == (2, 3))

    # 2个点应在球面对径位置
    dist2 = np.linalg.norm(pos2[0] - pos2[1])
    check("T09: solve(2) 对径距离≈2", abs(dist2 - 2.0) < 0.3, f"dist={dist2:.4f}")

    # 点在单位球面上
    norms = np.linalg.norm(pos2, axis=1)
    check("T10: solve(2) 在球面上", np.allclose(norms, 1.0, atol=0.01))

    energy_val = solver.energy(pos2)
    check("T11: energy(2点) ≈ 0.5", abs(energy_val - 0.5) < 0.1, f"E={energy_val:.4f}")

    pos4 = solver.solve(4, max_iter=300)
    check("T12: solve(4) 形状", pos4.shape == (4, 3))

    # 四面体应有6条等长边
    dists_4 = []
    for i in range(4):
        for j in range(i + 1, 4):
            dists_4.append(np.linalg.norm(pos4[i] - pos4[j]))
    check("T13: solve(4) 近似四面体", np.std(dists_4) < 0.2, f"std={np.std(dists_4):.4f}")

    check("T14: geometry_type(4)=tetrahedron",
          solver.get_geometry_type(4) == "tetrahedron")

    # ── Test 15-17: 几何类型 ──
    check("T15: geometry_type(2)=antipodal_pair",
          solver.get_geometry_type(2) == "antipodal_pair")
    check("T16: geometry_type(6)=octahedron",
          solver.get_geometry_type(6) == "octahedron")
    check("T17: symmetry_group(4)=T_d",
          solver.symmetry_group(4) == "T_d")

    # ── Test 18-22: E8LatticePacker ──
    packer = E8LatticePacker()
    density = packer.packing_density()
    expected_density = math.pi ** 4 / 384.0
    check("T18: E8密度=π⁴/384", abs(density - expected_density) < 1e-10)
    check("T19: E8密度≈0.2537", abs(density - 0.2537) < 0.001, f"d={density:.6f}")
    check("T20: E8接吻数=240", packer.kissing_number() == 240)
    check("T21: E8最短向量=√2", abs(packer.minimal_norm() - math.sqrt(2)) < 1e-10)

    features = np.array([[1.0, 0.5, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0]])
    emb = packer.pack(features, n_dims=8)
    check("T22: pack 形状正确", emb.shape == (1, 8))

    # ── Test 23-24: 干扰矩阵 ──
    multi_features = np.random.default_rng(42).standard_normal((5, 8))
    emb_multi = packer.pack(multi_features, n_dims=8)
    interf = packer.interference_matrix(emb_multi)
    check("T23: 干扰矩阵形状", interf.shape == (5, 5))
    check("T24: 干扰矩阵对角线=1", np.allclose(np.diag(interf), 1.0, atol=0.1))

    # ── Test 25-27: PhaseTransitionDetector ──
    detector = PhaseTransitionDetector(derivative_threshold=0.3)
    sparsity_vals = np.linspace(0.1, 0.9, 20)
    # 模拟相变：在sparsity=0.5处误差突然下降
    error_vals = np.where(sparsity_vals < 0.5,
                          1.0 - sparsity_vals,
                          0.3 * (1.0 - sparsity_vals))
    result = detector.detect(sparsity_vals, error_vals)
    check("T25: 检测到相变", result["phase_transition_found"] is True)
    check("T26: 相变点索引在范围内", 0 <= result["transition_index"] < 20)

    check("T27: classify_phase(0.8, 0.5)=superposition",
          detector.classify_phase(0.8, 0.5) == "superposition")

    # ── Test 28-29: 相态分类 ──
    check("T28: classify_phase(0.2, 0.5)=orthogonal",
          detector.classify_phase(0.2, 0.5) == "orthogonal")
    check("T29: classify_phase(0.8, 0.05)=ignored",
          detector.classify_phase(0.8, 0.05) == "ignored")

    # ── Test 30: 临界稀疏度 ──
    crit = detector.critical_sparsity(10, 20)
    check("T30: critical_sparsity(10,20)=0.25", abs(crit - 0.25) < 1e-10)

    # ── Test 31-34: PrivilegedBasisAnalyzer ──
    analyzer = PrivilegedBasisAnalyzer(monosemantic_threshold=0.6)
    # 模拟ReLU激活（稀疏、非负）
    rng = np.random.default_rng(42)
    relu_activations = np.maximum(rng.standard_normal((100, 10)), 0)
    result_relu = analyzer.analyze(relu_activations, has_relu=True)
    check("T31: analyze 返回字典", isinstance(result_relu, dict))
    check("T32: analyze 含 monosemantic_ratio", "monosemantic_ratio" in result_relu)
    check("T33: analyze 含 symmetry_broken_ratio", "symmetry_broken_ratio" in result_relu)

    mono_ratio = analyzer.monosemantic_ratio(relu_activations)
    check("T34: monosemantic_ratio 在 [0,1]", 0.0 <= mono_ratio <= 1.0)

    # ── Test 35-37: 对抗脆弱性 ──
    vuln = AdversarialVulnerabilityMetric()
    emb_test = np.random.default_rng(42).standard_normal((5, 8))
    coupling = vuln.interference_coupling(emb_test)
    check("T35: interference_coupling ≥ 0", coupling >= 0.0)

    score = vuln.vulnerability_score(emb_test)
    check("T36: vulnerability_score 在 [0,1]", 0.0 <= score <= 1.0)

    sens = vuln.perturbation_sensitivity(emb_test, epsilon=0.01)
    check("T37: perturbation_sensitivity ≥ 0", sens >= 0.0)

    # ── Test 38-40: SuperpositionTheorem ──
    check("T38: mdl_optimal(0.8)=superposition",
          SuperpositionTheorem.mdl_optimal_strategy(0.8) == "superposition")
    check("T39: mdl_optimal(0.2)=orthogonal",
          SuperpositionTheorem.mdl_optimal_strategy(0.2) == "orthogonal")

    predictions = SuperpositionTheorem.falsifiable_predictions()
    check("T40: ≥5条可证伪预言", len(predictions) >= 5)
    check("T40b: 预言含id字段", all("id" in p for p in predictions))

    print(f"\n{'=' * 64}")
    print(f"Self-Test Complete: {passed} passed, {failed} failed")
    print(f"{'=' * 64}")
    return passed, failed, details


if __name__ == "__main__":
    _self_test()
