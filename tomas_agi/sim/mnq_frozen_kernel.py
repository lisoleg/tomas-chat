# -*- coding: utf-8 -*-
"""
MNQ Frozen Kernel v1.0 — MNQ 冻结核集成
=========================================

基于论文：
  "基于八元数的 MNQ-Deep 冰核模型与语义死零过滤"
  微信公众号文章 (2026-06-22)
  "mnq-golden-spirit-ball-simulator"
  GitHub: https://github.com/lisoleg/mnq-golden-spirit-ball-simulator

核心功能：
  01. 五层递进冻结核 — L0→L4 冻结/液化判定
  02. 八元数非结合根基 — 非结合性度量与约束
  03. 死零语义过滤 — Dead-Zero ℐ = 0 触发的冻结
  04. κ=7 稳定性调节器 — 超常数与衰减控制
  05. Golden Spirit Ball — 黄金球语义维度投影
  06. NASGA 八元数桥接 — 非结合性核查

MNQ 五层架构:
  L0 (核心) — 八元数 Cayley-Dickson 构造 + S_7 非结合度量
  L1 (壳层) — Golden Spirit Ball 语义投影 (diam=1/φ)
  L2 (大气) — NASGA 谱熵 + κ=7 热容
  L3 (辐射) — 死零阈值 + Dead-Zero MUS 冻结
  L4 (轨道) — 语义轨道 + TDC 时序同步

集成到现有 TOMAS：
  - nasga_core.py: 八元数非结合度量增强
  - dead_zero_mus.py: MNQ 死零冻结调用
  - spectral_laplacian_py.py: κ=7 稳定性注入

Author: TOMAS Team
Version: v1.0 (v3.6 upgrade)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import logging
import math
import time
import hashlib
from enum import Enum

logger = logging.getLogger(__name__)

# ── 数学快捷函数 ────────────────────────────────────────────────
sqrt = math.sqrt
exp = math.exp
log = math.log
pi = math.pi
cos = math.cos
sin = math.sin
acos = math.acos

# ══════════════════════════════════════════════════════════════════
# MNQ 常量
# ══════════════════════════════════════════════════════════════════

KAPPA = 7                           # κ 超常数（不变）
PHI = (1 + sqrt(5)) / 2             # φ 黄金比例
GSP_DIAMETER = 1 / PHI              # Golden Spirit Ball 直径
OCTONION_DIM = 8                    # 八元数维度
CAYLEY_DICKSON_DEPTH = 3            # 3 次 Cayley-Dickson 构造
NON_ASSOCIATIVE_BASIS = 7           # 非结合基底数 (e₁⋯e₇)


class MNQLayer(Enum):
    """MNQ 冻结核层级"""
    L0_CORE = 0      # 八元数核心 — 非结合度量
    L1_SHELL = 1     # Golden Spirit Ball — 语义投影
    L2_ATMOSPHERE = 2  # NASGA 谱熵 — κ=7 热容
    L3_RADIATION = 3   # 死零过滤 — Dead-Zero MUS
    L4_ORBIT = 4       # 语义轨道 — TDC 同步


class KernelPhase(Enum):
    """冻结核相位"""
    LIQUID = "liquid"       # 液化态 — 自由推理
    FREEZING = "freezing"   # 冻结中 — 待决策
    FROZEN = "frozen"       # 冻结态 — 输出被锁定
    THAWING = "thawing"     # 解冻中 — 信任恢复


# ══════════════════════════════════════════════════════════════════
# 八元数非结合根基
# ══════════════════════════════════════════════════════════════════

@dataclass
class Octonion:
    """八元数 (Cayley-Dickson 构造)"""
    e0: float = 0.0  # 实部
    e1: float = 0.0  # i
    e2: float = 0.0  # j
    e3: float = 0.0  # k
    e4: float = 0.0  # l
    e5: float = 0.0  # il
    e6: float = 0.0  # jl
    e7: float = 0.0  # kl

    def norm(self) -> float:
        """八元数范数"""
        return sqrt(sum(getattr(self, f"e{i}")**2 for i in range(8)))

    def conjugate(self) -> "Octonion":
        """共轭八元数"""
        return Octonion(self.e0, -self.e1, -self.e2, -self.e3,
                        -self.e4, -self.e5, -self.e6, -self.e7)

    def mul(self, other: "Octonion") -> "Octonion":
        """八元数乘法（非结合！）"""
        # 完整八元数乘法表 (Cayley-Dickson)
        a = [getattr(self, f"e{i}") for i in range(8)]
        b = [getattr(other, f"e{i}") for i in range(8)]
        c = [0.0] * 8

        # 实部
        c[0] = a[0]*b[0] - a[1]*b[1] - a[2]*b[2] - a[3]*b[3] \
               - a[4]*b[4] - a[5]*b[5] - a[6]*b[6] - a[7]*b[7]

        # e1: i
        c[1] = a[0]*b[1] + a[1]*b[0] + a[2]*b[3] - a[3]*b[2] \
               + a[4]*b[5] - a[5]*b[4] - a[6]*b[7] + a[7]*b[6]

        # e2: j
        c[2] = a[0]*b[2] - a[1]*b[3] + a[2]*b[0] + a[3]*b[1] \
               + a[4]*b[6] + a[5]*b[7] - a[6]*b[4] - a[7]*b[5]

        # e3: k
        c[3] = a[0]*b[3] + a[1]*b[2] - a[2]*b[1] + a[3]*b[0] \
               + a[4]*b[7] - a[5]*b[6] + a[6]*b[5] - a[7]*b[4]

        # e4: l
        c[4] = a[0]*b[4] - a[1]*b[5] - a[2]*b[6] - a[3]*b[7] \
               + a[4]*b[0] + a[5]*b[1] + a[6]*b[2] + a[7]*b[3]

        # e5: il
        c[5] = a[0]*b[5] + a[1]*b[4] - a[2]*b[7] + a[3]*b[6] \
               - a[4]*b[1] + a[5]*b[0] - a[6]*b[3] + a[7]*b[2]

        # e6: jl
        c[6] = a[0]*b[6] + a[1]*b[7] + a[2]*b[4] - a[3]*b[5] \
               - a[4]*b[2] + a[5]*b[3] + a[6]*b[0] - a[7]*b[1]

        # e7: kl
        c[7] = a[0]*b[7] - a[1]*b[6] + a[2]*b[5] + a[3]*b[4] \
               - a[4]*b[3] - a[5]*b[2] + a[6]*b[1] + a[7]*b[0]

        return Octonion(*c)


class NonAssociativityMeasure:
    """
    八元数非结合性度量

    计算三元组的 associator:
      [x, y, z] = (xy)z - x(yz)

    非结合性 ω 定义为 associator 范数的上界。
    """

    @staticmethod
    def associator(x: Octonion, y: Octonion, z: Octonion) -> Octonion:
        """计算 (xy)z - x(yz)"""
        xy = x.mul(y)
        yz = y.mul(z)
        left = xy.mul(z)
        right = x.mul(yz)

        # associator = (xy)z - x(yz)
        return Octonion(
            left.e0 - right.e0, left.e1 - right.e1,
            left.e2 - right.e2, left.e3 - right.e3,
            left.e4 - right.e4, left.e5 - right.e5,
            left.e6 - right.e6, left.e7 - right.e7,
        )

    @staticmethod
    def omega(x: Octonion, y: Octonion, z: Octonion) -> float:
        """
        计算非结合性 ω(x, y, z)

        ω = ||associator|| / (||x|| * ||y|| * ||z||)
        """
        assoc = NonAssociativityMeasure.associator(x, y, z)
        denom = x.norm() * y.norm() * z.norm()
        if denom < 1e-10:
            return 0.0
        return assoc.norm() / denom

    @staticmethod
    def is_alternative(x: Octonion, y: Octonion, z: Octonion,
                       threshold: float = 1e-6) -> bool:
        """检查是否近似满足交替律"""
        return NonAssociativityMeasure.omega(x, y, z) < threshold


# ══════════════════════════════════════════════════════════════════
# Golden Spirit Ball — 语义投影
# ══════════════════════════════════════════════════════════════════

class GoldenSpiritBall:
    """
    Golden Spirit Ball — 黄金球语义维度投影

    在直径为 1/φ ≈ 0.618 的球面上投影语义向量，
    利用黄金比例实现最优维分布。
    """

    def __init__(self, dim: int = 8):
        self.dim = dim
        self.radius = GSP_DIAMETER / 2  # ≈ 0.309

    def project(self, semantic_vector: List[float]) -> List[float]:
        """将语义向量投影到黄金球面"""
        # 填充/截断到目标维度
        if len(semantic_vector) < self.dim:
            padded = semantic_vector + [0.0] * (self.dim - len(semantic_vector))
        else:
            padded = semantic_vector[:self.dim]

        # 计算范数
        norm = sqrt(sum(v**2 for v in padded))
        if norm < 1e-10:
            return [0.0] * self.dim

        # 缩放到球面半径
        scale = self.radius / norm
        return [v * scale for v in padded]

    def inverse_project(self, sphere_point: List[float]) -> List[float]:
        """从黄金球面反投影"""
        # 恢复原始尺度
        norm = sqrt(sum(v**2 for v in sphere_point))
        if norm < 1e-10:
            return sphere_point
        scale = 1.0 / self.radius
        return [v * scale for v in sphere_point]

    def fibonacci_sphere(self, num_points: int) -> List[List[float]]:
        """
        Fibonacci 球面分布（利用黄金比例实现最优采样）

        这是 MNQ 的核心：在 S^(dim-1) 上用黄金比例旋进生成
        均匀分布的点集。
        """
        points = []
        for i in range(num_points):
            # 使用黄金比例角
            theta = 2 * pi * i / PHI
            phi = acos(1 - 2 * (i + 0.5) / num_points)

            if self.dim == 3:
                # 3D 球面
                x = sin(phi) * cos(theta)
                y = sin(phi) * sin(theta)
                z = cos(phi)
                points.append([x * self.radius, y * self.radius, z * self.radius])
            elif self.dim == 8:
                # 8D 超球面 — 分解为两对 Hopf 纤维
                theta2 = 2 * pi * i / (PHI * PHI)
                x = [0.0] * 8
                x[0] = sin(phi) * cos(theta)
                x[1] = sin(phi) * sin(theta)
                x[2] = cos(phi) * cos(theta2)
                x[3] = cos(phi) * sin(theta2)
                x[4] = sin(phi) * cos(theta2) * cos(theta)
                x[5] = sin(phi) * cos(theta2) * sin(theta)
                x[6] = cos(phi) * sin(theta2) * cos(theta)
                x[7] = cos(phi) * sin(theta2) * sin(theta)
                points.append([v * self.radius / sqrt(8) for v in x])
            else:
                # 通用高维球面 使用 Marsaglia 方法
                gauss = [0.0] * self.dim
                for j in range(self.dim):
                    u1 = (i * PHI + j) % 1.0
                    u2 = (i * PHI * PHI + j * 0.5) % 1.0
                    # Box-Muller 极坐标
                    gauss[j] = sqrt(-2 * log(max(u1, 1e-10))) * cos(2 * pi * u2)
                gnorm = sqrt(sum(g**2 for g in gauss))
                points.append([g * self.radius / gnorm for g in gauss])

        return points

    def find_nearest_fibonacci(self, point: List[float],
                               num_reference: int = 100) -> Tuple[int, float]:
        """查找最近的 Fibonacci 球面采样点"""
        ref_points = self.fibonacci_sphere(num_reference)
        min_dist = float("inf")
        nearest_idx = -1
        for i, ref in enumerate(ref_points):
            dist = sqrt(sum((p - r)**2 for p, r in zip(point, ref)))
            if dist < min_dist:
                min_dist = dist
                nearest_idx = i
        return nearest_idx, min_dist


# ══════════════════════════════════════════════════════════════════
# κ=7 稳定性调节器
# ══════════════════════════════════════════════════════════════════

class Kappa7Regulator:
    """
    κ=7 稳定性调节器

    控制 MNQ 冻结核的冻结/液化过渡：
      T_freeze = T_0 * exp(-κ * ℐ)

    参数：
      T_0: 基础冻结温度
      κ: 超常数 (固定 = 7)
      ℐ: 语义信息丰度

    热容公式：
      C_V = (∂U/∂T) at constant V
      U = kB * T^2 * ∂(ln Z) / ∂T
    """

    def __init__(self, T0: float = 1.0, kappa: int = KAPPA):
        self.T0 = T0
        self.kappa = kappa
        self.temperature = T0
        self.phase = KernelPhase.LIQUID
        self.freeze_count = 0
        self.thaw_count = 0

    def compute_freeze_temperature(self, I_value: float) -> float:
        """
        计算冻结温度

        T_freeze = T_0 * exp(-κ * ℐ)

        当 ℐ → 0: T_freeze → T_0 (高冻结温度, 容易冻结)
        当 ℐ → 1: T_freeze → T_0 * exp(-7) ≈ 0.0009 (几乎不冻结)
        """
        return self.T0 * exp(-self.kappa * I_value)

    def update_temperature(self, I_value: float, delta_t: float = 0.1):
        """
        更新系统温度

        热力学冷却: T_new = T_old * exp(-I * delta_t)
        热力学加热: T_new = T_old * exp((1-I) * delta_t)
        """
        freeze_T = self.compute_freeze_temperature(I_value)

        if self.temperature > freeze_T:
            # 冷却
            self.temperature *= exp(-I_value * delta_t * self.kappa)
        else:
            # 加热
            self.temperature *= exp((1 - I_value) * delta_t * self.kappa)

        # 确保不降到冻结温度以下
        self.temperature = max(self.temperature, freeze_T * 0.9)

    def check_phase_transition(self, dead_zero_score: float) -> KernelPhase:
        """
        检查相位跃迁

        Args:
            dead_zero_score: 死零分数 ∈ [0, 1] (1 = 完全死零)

        Returns:
            当前冻结核相位
        """
        T_freeze = self.compute_freeze_temperature(1 - dead_zero_score)

        if dead_zero_score > 0.95:
            self.phase = KernelPhase.FROZEN
            self.freeze_count += 1
        elif dead_zero_score > 0.7:
            if self.phase == KernelPhase.FROZEN:
                self.phase = KernelPhase.THAWING
                self.thaw_count += 1
            else:
                self.phase = KernelPhase.FREEZING
        elif dead_zero_score < 0.3 and self.phase != KernelPhase.LIQUID:
            self.phase = KernelPhase.LIQUID
            self.thaw_count += 1

        return self.phase

    def heat_capacity(self, I_value: float) -> float:
        """
        计算热容 C_V

        对于 κ=7 系统:
          C_V = κ * kB * (I * (1 - I))

        这保证 C_V 在 I=0.5 时最大（最大不确定性）
        """
        return self.kappa * I_value * (1 - I_value)

    def compute_entropy(self, I_value: float) -> float:
        """
        计算系统熵

        S = -kB * (I*ln(I) + (1-I)*ln(1-I))
        在 I=0.5 时最大
        """
        if I_value <= 0 or I_value >= 1:
            return 0.0
        return -(I_value * log(I_value) + (1 - I_value) * log(1 - I_value))


# ══════════════════════════════════════════════════════════════════
# 主类：MNQ 冻结核
# ══════════════════════════════════════════════════════════════════

class MNQFrozenKernel:
    """
    MNQ 冻结核集成引擎

    五层递进架构：
      L0: 八元数非结合度量
      L1: Golden Spirit Ball 语义投影
      L2: NASGA 谱熵 + κ=7 热容
      L3: 死零过滤 + Dead-Zero MUS
      L4: 语义轨道 + TDC 同步

    用法：
        >>> mnq = MNQFrozenKernel()
        >>> mnq.ingest_query("What is AI?", [0.1, 0.3, 0.5, ...])
        >>> phase = mnq.current_phase()
        >>> if phase == KernelPhase.FROZEN:
        >>>     print("输出被冻结")
    """

    def __init__(self, T0: float = 1.0, dim: int = 8):
        # L0: 八元数核心
        self.dim = dim
        self.octonion_state = Octonion()
        self.omega_accumulator: float = 0.0  # 累积非结合性

        # L1: Golden Spirit Ball
        self.gsb = GoldenSpiritBall(dim)

        # L2: NASGA + κ=7
        self.regulator = Kappa7Regulator(T0=T0)
        self.spectral_entropy: float = 0.0

        # L3: 死零
        self.dead_zero_score: float = 0.0
        self.frozen_outputs: List[Dict] = []

        # L4: 轨道
        self.orbit_position: float = 0.0  # TDC 轨道相位
        self.orbit_log: List[Dict] = []

        # 统计
        self.stats = {
            "ingest_count": 0,
            "freeze_events": 0,
            "thaw_events": 0,
            "non_assoc_events": 0,
        }

    # ── L0: 八元数核心 ───────────────────────────────────────────

    def update_octonion(self, semantic_vector: List[float]):
        """用语义向量更新八元数状态"""
        padded = semantic_vector[:8] + [0.0] * max(0, 8 - len(semantic_vector))
        new_oct = Octonion(*padded[:8])

        # 计算与上次的非结合性
        if self.octonion_state.norm() > 1e-10:
            omega = NonAssociativityMeasure.omega(
                self.octonion_state, new_oct,
                Octonion(1, 0, 0, 0, 0, 0, 0, 0)
            )
            self.omega_accumulator += omega
            if omega > 0.01:
                self.stats["non_assoc_events"] += 1

        self.octonion_state = new_oct

    def compute_omega_profile(self) -> Dict:
        """计算当前非结合性剖面"""
        omega = self.omega_accumulator
        is_alt = omega < 1e-6
        return {
            "omega": omega,
            "is_alternative": is_alt,
            "non_assoc_events": self.stats["non_assoc_events"],
            "octonion_norm": self.octonion_state.norm(),
        }

    # ── L1: Golden Spirit Ball ──────────────────────────────────

    def project_to_golden_sphere(self,
                                  semantic_vector: List[float]) -> List[float]:
        """投影到黄金球面"""
        return self.gsb.project(semantic_vector)

    def fibonacci_nearest(self, point: List[float],
                          n: int = 100) -> Tuple[int, float]:
        """查找最近的 Fibonacci 球面点"""
        return self.gsb.find_nearest_fibonacci(point, n)

    def fibonacci_distribution(self, n: int = 50) -> List[List[float]]:
        """生成 Fibonacci 球面分布"""
        return self.gsb.fibonacci_sphere(n)

    # ── L2: κ=7 热力学 ──────────────────────────────────────────

    def compute_spectral_entropy(self,
                                  I_values: List[float]) -> float:
        """计算 NASGA 谱熵"""
        if not I_values:
            return 0.0
        entropy = 0.0
        for I in I_values:
            hi = self.regulator.compute_entropy(I)
            entropy += hi
        self.spectral_entropy = entropy / len(I_values)
        return self.spectral_entropy

    def compute_heat_capacity(self, I_value: float) -> float:
        """计算热容"""
        return self.regulator.heat_capacity(I_value)

    # ── L3: 死零过滤 ────────────────────────────────────────────

    def detect_dead_zero(self, I_value: float,
                          non_assoc_omega: Optional[float] = None) -> float:
        """
        死零检测

        Dead-Zero Score = 1 - min(1, max(0, I * (1 - ω)))

        其中 ω 是非结合性度量（放大死零效应）。
        """
        omega = non_assoc_omega if non_assoc_omega is not None else self.omega_accumulator
        signal = max(0, min(1, I_value * (1 - omega)))
        self.dead_zero_score = 1 - signal
        return self.dead_zero_score

    def should_freeze(self) -> bool:
        """
        判断是否应冻结

        条件:
          1. Dead-Zero Score > 0.95
          2. 或: ω > 0.5 且 I < 0.2
        """
        if self.dead_zero_score > 0.95:
            return True
        if self.omega_accumulator > 0.5 and self.regulator.temperature < 0.1:
            return True
        return False

    # ── L4: TDC 轨道同步 ────────────────────────────────────────

    def advance_orbit(self, tdc_pulse: int, I_value: float):
        """推进 TDC 轨道"""
        self.orbit_position += 2 * pi * tdc_pulse / (PHI * self.regulator.kappa)
        self.orbit_position %= (2 * pi)

        self.orbit_log.append({
            "tdc": tdc_pulse,
            "I_value": I_value,
            "orbit_pos": self.orbit_position,
            "phase": self.regulator.phase.value,
        })

    # ── 主入口 ────────────────────────────────────────────────────

    def ingest_query(self, query: str,
                     semantic_vector: List[float],
                     I_value: float = 0.5) -> Dict:
        """
        摄入查询 — 执行完整的五层处理

        Returns:
            各层分析结果
        """
        self.stats["ingest_count"] += 1

        # L0: 八元数更新
        self.update_octonion(semantic_vector)

        # L1: Golden Spirit Ball 投影
        gsp_proj = self.project_to_golden_sphere(semantic_vector)

        # L2: 热力学
        self.regulator.update_temperature(I_value)
        heat_cap = self.compute_heat_capacity(I_value)
        entropy = self.regulator.compute_entropy(I_value)

        # L3: 死零检测
        dz_score = self.detect_dead_zero(I_value)

        # 相位跃迁
        phase = self.regulator.check_phase_transition(dz_score)

        # 冻结判定
        if self.should_freeze() and phase != KernelPhase.FROZEN:
            self.regulator.phase = KernelPhase.FROZEN
            self.regulator.freeze_count += 1
            self.stats["freeze_events"] += 1
            self.frozen_outputs.append({
                "query": query[:100],
                "I_value": I_value,
                "dz_score": dz_score,
                "timestamp": time.time(),
            })

        if phase == KernelPhase.LIQUID and self.regulator.thaw_count > 0:
            self.stats["thaw_events"] += 1

        # L4: TDC 轨道
        tdc_now = int(time.time() * 1000) % 10000
        self.advance_orbit(tdc_now, I_value)

        return {
            "L0_omega": self.omega_accumulator,
            "L1_gsp_dim": len(gsp_proj),
            "L2_temperature": round(self.regulator.temperature, 4),
            "L2_heat_capacity": round(heat_cap, 4),
            "L2_entropy": round(entropy, 4),
            "L3_dead_zero_score": round(dz_score, 4),
            "L3_freeze_trigger": self.should_freeze(),
            "L4_orbit_position": round(self.orbit_position, 4),
            "phase": self.regulator.phase.value,
            "query_hash": hashlib.md5(query.encode()).hexdigest()[:8],
        }

    def current_phase(self) -> KernelPhase:
        return self.regulator.phase

    def is_frozen(self) -> bool:
        return self.regulator.phase == KernelPhase.FROZEN

    def thaw(self, trust_bonus: float = 0.3):
        """解冻冻结核"""
        if self.regulator.phase in (KernelPhase.FROZEN, KernelPhase.FREEZING):
            self.regulator.temperature += trust_bonus * self.regulator.T0
            self.regulator.phase = KernelPhase.THAWING
            self.regulator.thaw_count += 1
            logger.info(f"MNQ 解冻: T={self.regulator.temperature:.4f}")

    def get_kernel_profile(self) -> Dict:
        """获取冻结核剖面"""
        return {
            "phase": self.regulator.phase.value,
            "temperature": round(self.regulator.temperature, 4),
            "freeze_temperature": round(
                self.regulator.compute_freeze_temperature(1 - self.dead_zero_score), 4
            ),
            "dead_zero_score": round(self.dead_zero_score, 4),
            "omega_accumulator": round(self.omega_accumulator, 4),
            "spectral_entropy": round(self.spectral_entropy, 4),
            "orbit_position": round(self.orbit_position, 4),
            "frozen_outputs": len(self.frozen_outputs),
            "stats": self.stats,
        }

    def summary(self) -> str:
        """生成冻结核状态摘要"""
        p = self.get_kernel_profile()
        lines = [
            f"❄ MNQ 冻结核 — Phase: {p['phase']}",
            f"  T={p['temperature']} | T_freeze={p['freeze_temperature']}",
            f"  Dead-Zero: {p['dead_zero_score']} | ω: {p['omega_accumulator']}",
            f"  谱熵: {p['spectral_entropy']} | 轨道: {p['orbit_position']:.2f} rad",
            f"  统计: 冻结{p['stats']['freeze_events']}次 | "
            f"解冻{p['stats']['thaw_events']}次 | "
            f"非结合{p['stats']['non_assoc_events']}次",
        ]
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# 自检
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("MNQ Frozen Kernel 自检")
    print("=" * 60)

    mnq = MNQFrozenKernel(T0=1.0, dim=8)

    # 正常查询
    r1 = mnq.ingest_query(
        "What is machine learning?",
        [0.1, 0.3, 0.5, 0.2, 0.4, 0.6, 0.1, 0.3],
        I_value=0.7
    )
    print(f"\n[正常查询] phase={r1['phase']}, "
          f"dz={r1['L3_dead_zero_score']:.4f}, "
          f"T={r1['L2_temperature']:.4f}")

    # 低 ℐ 查询（接近死零）
    r2 = mnq.ingest_query(
        "asdf qwer zxcv random noise",
        [0.01, 0.02, 0.01, 0.03, 0.01, 0.02, 0.01, 0.01],
        I_value=0.02
    )
    print(f"\n[死零查询] phase={r2['phase']}, "
          f"dz={r2['L3_dead_zero_score']:.4f}, "
          f"freeze={r2['L3_freeze_trigger']}")

    # 八元数非结合性
    print(f"\n[八元数] ω={mnq.omega_accumulator:.6f}")
    omega_profile = mnq.compute_omega_profile()
    print(f"  非结合事件: {omega_profile['non_assoc_events']}")

    # Golden Spirit Ball
    gsp_points = mnq.fibonacci_distribution(10)
    print(f"\n[GSP] Fibonacci 采样: {len(gsp_points)} 个点")
    print(f"  点[0]: {[round(v, 4) for v in gsp_points[0][:4]]}...")

    # 解冻
    if mnq.is_frozen():
        mnq.thaw(trust_bonus=0.5)
        print(f"\n[解冻] 执行解冻操作")

    # 剖面
    print(f"\n{mnq.summary()}")

    print("\nMNQ Frozen Kernel 自检完成 ✅")
