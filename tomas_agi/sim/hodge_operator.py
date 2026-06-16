"""
Hodge-ℐ 耦合算子 — TOMAS-WSC 融合算子

基于 Baccini-Geraci-Bianconi (2022) 加权单纯复形 + TOMAS ℐ-守恒注入。
将死零机制、MUS 双存、ℐ-守恒编码进 Hodge 谱。

参考: TOMAS 主论文附录 P (章锋, 2026)
"""

import math
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
import hashlib

logger = logging.getLogger(__name__)


# ============================================================
# 数据结构
# ============================================================

@dataclass
class Simplex:
    """加权单纯形 — WSC 中的基本单元"""
    id: str
    dim: int                     # 维度 n (0=顶点, 1=边, 2=面, ...)
    vertices: List[str]          # 组成顶点
    i_weight: float = 1.0        # ℐ-权重 (= w_σ in WSC)
    is_dead_zero: bool = False   # ℐ < θ_dead
    is_mus: bool = False         # Asym≠0 MUS 双存标记


@dataclass
class HodgeSpectrum:
    """Hodge Laplacian 谱"""
    eigenvalues: List[float]
    eigenvectors: List[List[float]]
    spectral_entropy: float      # 高阶谱熵 S_n
    dim: int                     # 维度
    betti_number: int            # Betti 数 (= dim ker L_{[n]})


# ============================================================
# 加权单纯复形 (WSC)
# ============================================================

class WeightedSimplicialComplex:
    """加权单纯复形 — Baccini WSC 模型的 TOMAS 重实现"""

    def __init__(self, max_dim: int = 3):
        self.max_dim = max_dim
        self.simplices: Dict[int, Dict[str, Simplex]] = {
            d: {} for d in range(max_dim + 1)
        }

    def add_simplex(self, vertices: List[str], i_weight: float = 1.0,
                    simplex_id: str = None) -> Simplex:
        """添加一个单纯形并递归计算拓扑权重"""
        dim = len(vertices) - 1
        if dim > self.max_dim:
            raise ValueError(f"维度 {dim} > max_dim {self.max_dim}")

        if simplex_id is None:
            simplex_id = f"S_{dim}_" + "_".join(sorted(vertices))

        # 递归继承 ℐ-流 (WSC 核心: 权重递归定义)
        inherited_i = i_weight
        if dim > 0:
            # 面继承: 高阶单纯形的 ℐ 由其面累加
            face_i_sum = 0.0
            for face_dim in range(dim):
                for face in self.simplices[face_dim].values():
                    if set(face.vertices).issubset(set(vertices)):
                        face_i_sum += face.i_weight * 0.1  # 衰减继承
            inherited_i += face_i_sum

        simplex = Simplex(
            id=simplex_id, dim=dim, vertices=sorted(vertices),
            i_weight=inherited_i
        )
        self.simplices[dim][simplex_id] = simplex

        logger.debug(f"[WSC] +{simplex_id} dim={dim} I={inherited_i:.4f}")
        return simplex

    def get_i(self, simplex_id: str) -> float:
        """获取单纯形的 ℐ-值"""
        for dim_dict in self.simplices.values():
            if simplex_id in dim_dict:
                return dim_dict[simplex_id].i_weight
        return 0.0

    def get_simplices_by_dim(self, dim: int) -> List[Simplex]:
        return list(self.simplices.get(dim, {}).values())

    def to_eml_hypergraph(self) -> Dict:
        """将 WSC 导出为 EML 超图格式"""
        vertices = set()
        edges = []
        for dim, dim_dict in self.simplices.items():
            for spx in dim_dict.values():
                vertices.update(spx.vertices)
                if dim >= 1:
                    edges.append({
                        "id": spx.id,
                        "nodes": spx.vertices,
                        "i_val": spx.i_weight,
                        "dim": spx.dim,
                    })
        return {"vertices": list(vertices), "edges": edges}


# ============================================================
# Hodge-ℐ 耦合算子
# ============================================================

class HodgeICoupling:
    """Hodge-ℐ 耦合算子 L_{[n]}^TOMAS = L_{[n]} + λ·Π_{[n]}

    参考: 附录 P.2
    """

    def __init__(self, wsc: WeightedSimplicialComplex, lambda_i: float = 1.0,
                 epsilon: float = 1e-6, theta_dead: float = 0.15):
        self.wsc = wsc
        self.lambda_i = lambda_i   # ℐ-耦合强度
        self.epsilon = epsilon     # 除零保护
        self.theta_dead = theta_dead

    def coboundary_matrix(self, dim: int) -> List[List[float]]:
        """加权上边界算子 δ_w^n

        参考: 附录 P.1.1
        ⟨δ_w^n f, σ⟩ = Σ_{τ⊂σ, dim(τ)=n} (w_τ / w_σ) * f(τ)
        """
        simplices_n = self.wsc.get_simplices_by_dim(dim)      # n-单纯形 (cols)
        simplices_n1 = self.wsc.get_simplices_by_dim(dim + 1)  # (n+1)-单纯形 (rows)

        n_rows = len(simplices_n1)  # |C^{n+1}|
        n_cols = len(simplices_n)   # |C^n|
        if n_rows == 0 or n_cols == 0:
            return [[0.0] * n_cols for _ in range(n_rows)]

        matrix = [[0.0] * n_cols for _ in range(n_rows)]  # n_rows × n_cols

        for j, sigma in enumerate(simplices_n1):  # row: (n+1)-simplex
            w_sigma = max(sigma.i_weight, self.epsilon)
            for i, tau in enumerate(simplices_n):   # col: n-simplex
                if set(tau.vertices).issubset(set(sigma.vertices)):
                    w_tau = max(tau.i_weight, self.epsilon)
                    matrix[j][i] = w_tau / w_sigma  # δ_w^n[j][i]

        return matrix

    def hodge_laplacian(self, dim: int) -> List[List[float]]:
        """归一化 Hodge Laplacian L_{[n]}

        参考: 附录 P.1.2
        L_{[n]} = D_n^{-1/2} (δ_w^{n-1}·(δ_w^{n-1})* + (δ_w^n)*·δ_w^n) D_n^{-1/2}
        """
        simplices = self.wsc.get_simplices_by_dim(dim)
        n = len(simplices)
        if n == 0:
            return []

        # 对角线权重矩阵 D_n
        diag = [max(spx.i_weight, self.epsilon) for spx in simplices]
        D_inv_sqrt = [[0.0] * n for _ in range(n)]
        for i in range(n):
            D_inv_sqrt[i][i] = 1.0 / math.sqrt(diag[i])

        # 下边界项: δ_w^{n-1}·(δ_w^{n-1})*
        lower_term = self._zero_matrix(n)
        if dim > 0:
            delta_lower = self.coboundary_matrix(dim - 1)
            if delta_lower and delta_lower[0]:
                # δ_w^{n-1} 是 cols=(n-1)simplices × rows=n-simplices
                # (δ_w^{n-1})* 是转置
                delta_lower_t = self._transpose(delta_lower)
                lower_term = self._matmul(delta_lower, delta_lower_t, n, n)

        # 上边界项: (δ_w^n)*·δ_w^n
        upper_term = self._zero_matrix(n)
        delta_upper = self.coboundary_matrix(dim)
        if delta_upper and delta_upper[0]:
            delta_upper_t = self._transpose(delta_upper)
            upper_term = self._matmul(delta_upper_t, delta_upper, n, n)

        # L_raw = lower + upper
        raw = self._matadd(lower_term, upper_term, n)

        # 归一化: L_{[n]} = D^{-1/2} · raw · D^{-1/2}
        temp = self._matmul(D_inv_sqrt, raw, n, n)
        normed = self._matmul(temp, D_inv_sqrt, n, n)

        return normed

    def i_penalty_matrix(self, dim: int) -> List[List[float]]:
        """ℐ-守恒惩罚项 Π_{[n]} = diag(1/(I(σ)+ε))

        参考: 附录 P.2.2 定义 P.1
        """
        simplices = self.wsc.get_simplices_by_dim(dim)
        n = len(simplices)
        if n == 0:
            return []

        penalty = [[0.0] * n for _ in range(n)]
        for i, spx in enumerate(simplices):
            penalty[i][i] = 1.0 / max(spx.i_weight, self.epsilon)

        logger.debug(f"[Hodge-ℐ] dim={dim} Π_{{[n]}} max_penalty="
                     f"{max(penalty[i][i] for i in range(n)):.2f}")
        return penalty

    def tomas_wsc_operator(self, dim: int) -> List[List[float]]:
        """TOMAS-WSC 融合算子 L_{[n]}^TOMAS = L_{[n]} + λ·Π_{[n]}

        参考: 附录 P.2.2 定义 P.1
        """
        laplacian = self.hodge_laplacian(dim)
        penalty = self.i_penalty_matrix(dim)

        n = len(laplacian)
        if n == 0:
            return []

        fusion = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                fusion[i][j] = laplacian[i][j] + self.lambda_i * penalty[i][j]

        return fusion

    def apply_dead_zero_cutoff(self, dim: int) -> List[str]:
        """死零截断: 标记并返回 I < θ_dead 的单纯形 ID

        参考: 附录 P.2.3
        """
        rejected = []
        for spx in self.wsc.get_simplices_by_dim(dim):
            if spx.i_weight < self.theta_dead:
                spx.is_dead_zero = True
                rejected.append(spx.id)
                logger.info(f"[死零截断] REJECT {spx.id}: I={spx.i_weight:.4f} < θ={self.theta_dead}")

        return rejected

    def compute_spectrum(self, dim: int) -> HodgeSpectrum:
        """计算 TOMAS-WSC 融合算子的谱

        包含特征值、特征向量、谱熵、Betti 数
        """
        fusion = self.tomas_wsc_operator(dim)
        n = len(fusion)
        if n == 0:
            return HodgeSpectrum(
                eigenvalues=[], eigenvectors=[], spectral_entropy=0.0,
                dim=dim, betti_number=0
            )

        # 简单特征值分解 (幂迭代近似 — 仅用于小规模 WSC)
        eigenvalues, eigenvectors = self._eigen_decompose(fusion)

        # 谱熵 S_n = -Σ (λ_i / Σλ) * log(λ_i / Σλ)
        total = sum(abs(ev) for ev in eigenvalues) + self.epsilon
        spectral_entropy = -sum(
            (abs(ev) / total) * math.log(abs(ev) / total + self.epsilon)
            for ev in eigenvalues
        )

        # Betti 数: 零特征值计数 (ker L_{[n]})
        betti = sum(1 for ev in eigenvalues if abs(ev) < self.epsilon)

        return HodgeSpectrum(
            eigenvalues=eigenvalues,
            eigenvectors=eigenvectors,
            spectral_entropy=spectral_entropy,
            dim=dim, betti_number=betti,
        )

    def steady_state_analysis(self, dim: int) -> Dict:
        """稳态分析: 解 (L_{[n]} + λ·Π_{[n]}) X* = 0

        参考: 附录 P.3.2 推导 P.1

        返回:
          - dead_zero_channels: I<θ 被强制压制为零的通道
          - mus_channels: ker(L) 中的调和上同调 (MUS 双存态)
          - active_channels: 高 ℐ 活跃通道
        """
        simplices = self.wsc.get_simplices_by_dim(dim)
        spectrum = self.compute_spectrum(dim)

        dead_zero_channels = []
        mus_channels = []
        active_channels = []

        for i, spx in enumerate(simplices):
            if spx.i_weight < self.theta_dead:
                dead_zero_channels.append({"id": spx.id, "i_val": spx.i_weight})
            elif i < len(spectrum.eigenvalues) and abs(spectrum.eigenvalues[i]) < self.epsilon:
                # 调和上同调 → MUS 双存
                mus_channels.append({
                    "id": spx.id, "i_val": spx.i_weight,
                    "eigenvalue": spectrum.eigenvalues[i],
                })
            else:
                active_channels.append({
                    "id": spx.id, "i_val": spx.i_weight,
                    "eigenvalue": spectrum.eigenvalues[i] if i < len(spectrum.eigenvalues) else 0,
                })

        return {
            "dim": dim,
            "dead_zero_channels": dead_zero_channels,
            "mus_channels": mus_channels,
            "active_channels": active_channels,
            "spectral_entropy": spectrum.spectral_entropy,
            "betti_number": spectrum.betti_number,
        }

    # ============================================================
    # 矩阵运算辅助
    # ============================================================

    @staticmethod
    def _zero_matrix(n: int) -> List[List[float]]:
        return [[0.0] * n for _ in range(n)]

    @staticmethod
    def _transpose(m: List[List[float]]) -> List[List[float]]:
        if not m:
            return []
        rows, cols = len(m), len(m[0])
        return [[m[i][j] for i in range(rows)] for j in range(cols)]

    @staticmethod
    def _matmul(a: List[List[float]], b: List[List[float]],
                out_rows: int, out_cols: int) -> List[List[float]]:
        inner = len(a[0]) if a else 0
        result = [[0.0] * out_cols for _ in range(out_rows)]
        for i in range(out_rows):
            for j in range(out_cols):
                s = 0.0
                for k in range(inner):
                    s += a[i][k] * b[k][j]
                result[i][j] = s
        return result

    @staticmethod
    def _matadd(a: List[List[float]], b: List[List[float]],
                n: int) -> List[List[float]]:
        return [[a[i][j] + b[i][j] for j in range(n)] for i in range(n)]

    @staticmethod
    def _eigen_decompose(matrix: List[List[float]], max_iter: int = 100,
                          tol: float = 1e-6) -> Tuple[List[float], List[List[float]]]:
        """幂迭代法 + deflation 提取特征值/特征向量"""
        n = len(matrix)
        if n == 0:
            return [], []

        eigenvalues = []
        eigenvectors = []
        residual = [row[:] for row in matrix]

        for _ in range(min(n, max_iter)):
            # 幂迭代
            v = [1.0 / math.sqrt(n)] * n
            for __ in range(50):
                new_v = [0.0] * n
                for i in range(n):
                    for j in range(n):
                        new_v[i] += residual[i][j] * v[j]
                norm = math.sqrt(sum(x * x for x in new_v))
                if norm < tol:
                    break
                new_v = [x / norm for x in new_v]

                diff = math.sqrt(sum((new_v[i] - v[i]) ** 2 for i in range(n)))
                v = new_v
                if diff < tol:
                    break

            # Rayleigh quotient λ = v^T A v
            av = [0.0] * n
            for i in range(n):
                for j in range(n):
                    av[i] += residual[i][j] * v[j]
            lam = sum(v[i] * av[i] for i in range(n))

            eigenvalues.append(lam)
            eigenvectors.append(v)

            # Deflation: A ← A - λ·v·v^T
            for i in range(n):
                for j in range(n):
                    residual[i][j] -= lam * v[i] * v[j]

        return eigenvalues, eigenvectors


# ============================================================
# 拓扑信号演化
# ============================================================

class TopologicalSignalEvolution:
    """拓扑信号在 TOMAS-WSC 上的动力学演化

    参考: 附录 P.3.2
    ∂X_n/∂t = -L_{[n]}^TOMAS X_n
    """

    def __init__(self, coupling: HodgeICoupling):
        self.coupling = coupling

    def evolve(self, dim: int, x0: List[float], dt: float = 0.01,
               steps: int = 100) -> List[List[float]]:
        """向前 Euler 演化拓扑信号

        X_{t+1} = X_t - dt * L_{[n]}^TOMAS X_t
        """
        operator = self.coupling.tomas_wsc_operator(dim)
        n = len(operator)
        if n == 0 or len(x0) != n:
            return []

        trajectory = [x0[:]]
        x = x0[:]

        for _ in range(steps):
            # Lx = L_{[n]}^TOMAS · x
            lx = [0.0] * n
            for i in range(n):
                for j in range(n):
                    lx[i] += operator[i][j] * x[j]

            # Euler step
            new_x = [x[i] - dt * lx[i] for i in range(n)]
            x = new_x
            trajectory.append(x[:])

        return trajectory

    def steady_state_signal(self, dim: int, x0: List[float],
                            dt: float = 0.01, tolerance: float = 1e-6) -> List[float]:
        """演化至稳态 (‖∂X/∂t‖ < tolerance)"""
        operator = self.coupling.tomas_wsc_operator(dim)
        n = len(operator)
        if n == 0:
            return x0

        x = x0[:]
        max_steps = 10000

        for _ in range(max_steps):
            lx = [0.0] * n
            for i in range(n):
                for j in range(n):
                    lx[i] += operator[i][j] * x[j]

            # 梯度范数
            grad_norm = math.sqrt(sum(g * g for g in lx))
            if grad_norm < tolerance:
                break

            new_x = [x[i] - dt * lx[i] for i in range(n)]
            x = new_x

        return x


# ============================================================
# 导出
# ============================================================

__all__ = [
    "Simplex",
    "HodgeSpectrum",
    "WeightedSimplicialComplex",
    "HodgeICoupling",
    "TopologicalSignalEvolution",
]
