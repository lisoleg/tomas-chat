# -*- coding: utf-8 -*-
"""
World Model Hyperedge v1.0 — 结构化世界模型超边引擎
=====================================================

基于论文：
  "太乙互搏的结构化世界模型超边引擎"
  "MW & Ω Philosophy of Physics — 从SDF/Affordance/Kinematic到
   太乙神机（TOMAS' Tetrad Joint: π/Φ/Ω/℧）"
  微信公众号文章 (2026-06-22)

核心功能：
  01. SDF 超边 — Signed Distance Function 空间建模
  02. Affordance 超边 — Gibson 可供性（环境→行动映射）
  03. Kinematic 超边 — 运动学约束（TDC 时序因果链）
  04. Ω-Gate — 世界模型一致性校验
  05. Tetrad Joint — π/Φ/Ω/℧ 四维接合
  06. 世界状态快照 — κ-Snap 因果链世界态

集成到现有 TOMAS：
  - eml_semzip.py: 超边结构化增强
  - taiji_cycle_v2.py: 世界态驱动太乙循环
  - causet_bridge.py: SDF ↔ Causet 映射

Author: TOMAS Team
Version: v1.0 (v3.6 upgrade)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Set
import logging
import math
import time
import hashlib
import json
from enum import Enum

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# 四维接合常量
# ══════════════════════════════════════════════════════════════════

PI = math.pi
PHI = (1 + math.sqrt(5)) / 2  # 黄金比例 ≈ 1.618
OMEGA = 0.5671432904  # Ω 常数 (Lambert W)
MHOO = 0.6180339887  # ℧ = φ - 1 (反黄金比例)

TETRAD = {"π": PI, "Φ": PHI, "Ω": OMEGA, "℧": MHOO}


class TetradJoint:
    """TOMAS 四维接合: π/Φ/Ω/℧"""

    @staticmethod
    def pi_coupling(x: float) -> float:
        """π 接合：周期性映射"""
        return math.sin(PI * x) * 0.5 + 0.5

    @staticmethod
    def phi_joint(x: float) -> float:
        """Φ 接合：黄金比例缩放"""
        return 1.0 / (1.0 + math.exp(-PHI * (x - 0.5)))

    @staticmethod
    def omega_gate(x: float) -> float:
        """Ω 接合：世界模型一致性门控"""
        return math.exp(-OMEGA * abs(x - 0.5))

    @staticmethod
    def mhoo_anchor(x: float) -> float:
        """℧ 接合：反黄金锚定"""
        return MHOO + (1 - MHOO) * x

    @staticmethod
    def joint_score(pi_val: float, phi_val: float,
                    omega_val: float, mhoo_val: float) -> float:
        """四维综合接合分数"""
        return (pi_val * phi_val * omega_val * mhoo_val) ** 0.25


# ══════════════════════════════════════════════════════════════════
# 超边类型
# ══════════════════════════════════════════════════════════════════

class HyperedgeType(Enum):
    """结构化世界模型超边类型"""
    SDF = "sdf"               # Signed Distance Function
    AFFORDANCE = "affordance" # Gibson 可供性
    KINEMATIC = "kinematic"   # 运动学约束
    TOPOLOGICAL = "topological"  # 拓扑关系
    CAUSAL_CHAIN = "causal_chain"  # 因果链


class OmegaGateVerdict(Enum):
    """Ω-Gate 裁决"""
    CONSISTENT = "consistent"
    INCONSISTENT = "inconsistent"
    UNVERIFIED = "unverified"
    TETRAD_PASS = "tetrad_pass"


# ══════════════════════════════════════════════════════════════════
# 数据结构
# ══════════════════════════════════════════════════════════════════

@dataclass
class SDFHyperedge:
    """
    Signed Distance Function 超边

    空间建模超边，计算顶点到隐含曲面的符号距离。
    """
    edge_id: str
    surface_type: str  # "plane", "sphere", "implicit"
    vertices: List[Tuple[float, float, float]]  # (x, y, z) 坐标
    signed_distances: List[float] = field(default_factory=list)
    surface_params: Dict[str, float] = field(default_factory=dict)
    I_value: float = 1.0

    def compute_sdf(self, query_point: Tuple[float, float, float]) -> float:
        """计算查询点的 SDF 值"""
        if self.surface_type == "sphere":
            cx, cy, cz = (self.surface_params.get(k, 0)
                          for k in ["cx", "cy", "cz"])
            r = self.surface_params.get("r", 1.0)
            qx, qy, qz = query_point
            dist = math.sqrt((qx - cx)**2 + (qy - cy)**2 + (qz - cz)**2)
            return dist - r

        elif self.surface_type == "plane":
            a, b, c, d = (self.surface_params.get(k, 0)
                          for k in ["a", "b", "c", "d"])
            qx, qy, qz = query_point
            return (a * qx + b * qy + c * qz + d) / math.sqrt(a**2 + b**2 + c**2 + 1e-10)

        # implicit: 默认返回到最近顶点的距离
        if self.vertices:
            return min(
                math.sqrt(
                    (query_point[0] - v[0])**2 +
                    (query_point[1] - v[1])**2 +
                    (query_point[2] - v[2])**2
                )
                for v in self.vertices
            )
        return 0.0

    def gradient(self, point: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """计算 SDF 梯度 (数值微分)"""
        eps = 1e-5
        dx = (self.compute_sdf((point[0] + eps, point[1], point[2])) -
              self.compute_sdf((point[0] - eps, point[1], point[2]))) / (2 * eps)
        dy = (self.compute_sdf((point[0], point[1] + eps, point[2])) -
              self.compute_sdf((point[0], point[1] - eps, point[2]))) / (2 * eps)
        dz = (self.compute_sdf((point[0], point[1], point[2] + eps)) -
              self.compute_sdf((point[0], point[1], point[2] - eps))) / (2 * eps)
        return (dx, dy, dz)


@dataclass
class AffordanceHyperedge:
    """
    Gibson 可供性超边

    环境→行动映射：给定环境状态，预测可执行的动作集合。
    """
    edge_id: str
    environment_state: Dict[str, Any]  # 环境状态向量
    available_actions: List[str]        # 可供行动集合
    action_probabilities: List[float] = field(default_factory=list)  # ℐ 权重
    preconditions: List[str] = field(default_factory=list)
    side_effects: List[str] = field(default_factory=list)
    I_value: float = 1.0

    def get_best_action(self) -> Tuple[str, float]:
        """获取最优可供行动"""
        if not self.available_actions:
            return ("noop", 0.0)
        probs = self.action_probabilities or [1.0 / len(self.available_actions)] * len(self.available_actions)
        best_idx = max(range(len(probs)), key=lambda i: probs[i])
        return (self.available_actions[best_idx], probs[best_idx])

    def filter_by_preconditions(self, satisfied: List[str]) -> List[str]:
        """按前置条件过滤可供行动"""
        satisfied_set = set(satisfied)
        return [a for a, pre in zip(self.available_actions, self.preconditions)
                if pre in satisfied_set]


@dataclass
class KinematicHyperedge:
    """
    运动学约束超边

    时序因果链：描述状态空间中的运动学变换。
    """
    edge_id: str
    source_state: Dict[str, Any]
    target_state: Dict[str, Any]
    transformation: str  # "translate", "rotate", "scale", "custom"
    params: Dict[str, float] = field(default_factory=dict)
    tdc_start: Optional[int] = None
    tdc_end: Optional[int] = None
    velocity: Optional[float] = None
    acceleration: Optional[float] = None
    I_value: float = 1.0

    def apply(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """应用运动学变换"""
        result = dict(state)
        if self.transformation == "translate":
            dx = self.params.get("dx", 0)
            dy = self.params.get("dy", 0)
            dz = self.params.get("dz", 0)
            result["x"] = state.get("x", 0) + dx
            result["y"] = state.get("y", 0) + dy
            result["z"] = state.get("z", 0) + dz
        elif self.transformation == "rotate":
            angle = self.params.get("angle", 0)
            axis = self.params.get("axis", "z")
            # 绕轴旋转的简化实现
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            if axis == "z":
                x, y = state.get("x", 0), state.get("y", 0)
                result["x"] = x * cos_a - y * sin_a
                result["y"] = x * sin_a + y * cos_a
            elif axis == "y":
                x, z = state.get("x", 0), state.get("z", 0)
                result["x"] = x * cos_a + z * sin_a
                result["z"] = -x * sin_a + z * cos_a
            elif axis == "x":
                y, z = state.get("y", 0), state.get("z", 0)
                result["y"] = y * cos_a - z * sin_a
                result["z"] = y * sin_a + z * cos_a
        elif self.transformation == "scale":
            sx = self.params.get("sx", 1)
            sy = self.params.get("sy", 1)
            sz = self.params.get("sz", 1)
            for key, scale in [("x", sx), ("y", sy), ("z", sz)]:
                if key in result:
                    result[key] *= scale
        return result


@dataclass
class WorldSnapshot:
    """世界状态快照"""
    snap_id: str
    timestamp: float
    hyperedges: List[str]  # 超边 ID 列表
    state_vector: Dict[str, Any] = field(default_factory=dict)
    ksnap_hash: Optional[str] = None
    prev_snap_hash: Optional[str] = None
    tetrad_score: float = 0.0
    omega_verdict: OmegaGateVerdict = OmegaGateVerdict.UNVERIFIED

    def compute_ksnap_hash(self) -> str:
        """计算 κ-Snap 哈希"""
        content = json.dumps(sorted(self.state_vector.items()), sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


# ══════════════════════════════════════════════════════════════════
# Ω-Gate 世界模型一致性校验器
# ══════════════════════════════════════════════════════════════════

class OmegaGate:
    """Ω-Gate — 世界模型一致性校验"""

    def __init__(self, consistency_threshold: float = 0.7):
        self.threshold = consistency_threshold
        self.joint = TetradJoint()

    def verify_snapshot(self, snap: WorldSnapshot) -> OmegaGateVerdict:
        """验证世界快照的一致性"""
        # π 接合: 周期性一致性
        pi_score = self.joint.pi_coupling(
            len(snap.hyperedges) / max(len(snap.hyperedges) + 1, 1)
        )

        # Φ 接合: 黄金比例校验
        phi_score = self.joint.phi_joint(
            sum(1 for _ in snap.state_vector.values()) / max(len(snap.state_vector), 1)
        )

        # Ω 接合: 一致性门控
        state_values = [float(v) if isinstance(v, (int, float)) else 0.0
                        for v in snap.state_vector.values()]
        if state_values:
            variance = sum((v - sum(state_values)/len(state_values))**2
                          for v in state_values) / len(state_values)
            omega_score = self.joint.omega_gate(
                min(variance / max(abs(sum(state_values)), 1), 1.0)
            )
        else:
            omega_score = 0.5

        # ℧ 接合: 反黄金锚定
        mhoo_score = self.joint.mhoo_anchor(
            snap.tetrad_score if snap.tetrad_score > 0 else 0.5
        )

        # 综合 Tetrad 分数
        tetrad = self.joint.joint_score(pi_score, phi_score,
                                        omega_score, mhoo_score)
        snap.tetrad_score = tetrad

        if tetrad >= self.threshold:
            snap.omega_verdict = OmegaGateVerdict.TETRAD_PASS
        elif tetrad >= self.threshold * 0.5:
            snap.omega_verdict = OmegaGateVerdict.CONSISTENT
        else:
            snap.omega_verdict = OmegaGateVerdict.INCONSISTENT

        return snap.omega_verdict

    def cross_verify(self, snap_a: WorldSnapshot,
                     snap_b: WorldSnapshot) -> float:
        """
        交叉验证两个世界快照的一致性

        返回一致性分数 ∈ [0, 1]
        """
        # 比较状态向量交集
        common_keys = set(snap_a.state_vector.keys()) & set(snap_b.state_vector.keys())
        if not common_keys:
            return 0.5

        diffs = []
        for key in common_keys:
            va = snap_a.state_vector[key]
            vb = snap_b.state_vector[key]
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                max_val = max(abs(va), abs(vb), 1)
                diffs.append(abs(va - vb) / max_val)

        mean_diff = sum(diffs) / len(diffs) if diffs else 0
        consistency = math.exp(-mean_diff * OMEGA)
        return consistency


# ══════════════════════════════════════════════════════════════════
# 主类：结构化世界模型
# ══════════════════════════════════════════════════════════════════

class StructuredWorldModel:
    """
    结构化世界模型

    管理三类超边 (SDF/Affordance/Kinematic) 和世界状态快照：
    1. SDF 超边 — 空间建模（距离场）
    2. Affordance 超边 — 环境→行动映射
    3. Kinematic 超边 — 运动学因果链
    4. Ω-Gate — 四维接合一致性校验
    5. 世界快照 — κ-Snap 因果链世界态

    用法：
        >>> wm = StructuredWorldModel()
        >>> sdf = wm.create_sdf_edge("surface_sphere", ...)
        >>> afford = wm.create_affordance("env_01", ...)
        >>> snap = wm.take_snapshot()
    """

    def __init__(self, agent_id: str = "default"):
        self.agent_id = agent_id

        # 三类超边注册表
        self.sdf_edges: Dict[str, SDFHyperedge] = {}
        self.affordance_edges: Dict[str, AffordanceHyperedge] = {}
        self.kinematic_edges: Dict[str, KinematicHyperedge] = {}

        # Ω-Gate
        self.omega_gate = OmegaGate()

        # 世界快照链
        self.snapshot_chain: List[WorldSnapshot] = []

        # 统计
        self.stats = {
            "sdf_count": 0,
            "affordance_count": 0,
            "kinematic_count": 0,
            "snapshot_count": 0,
        }

    # ── SDF 超边 ─────────────────────────────────────────────────

    def create_sdf_edge(self, surface_type: str,
                        vertices: List[Tuple[float, float, float]],
                        surface_params: Optional[Dict[str, float]] = None,
                        edge_id: Optional[str] = None) -> SDFHyperedge:
        """创建 SDF 超边"""
        eid = edge_id or f"sdf_{self.stats['sdf_count']}_{int(time.time())}"
        edge = SDFHyperedge(
            edge_id=eid,
            surface_type=surface_type,
            vertices=vertices,
            surface_params=surface_params or {},
        )
        self.sdf_edges[eid] = edge
        self.stats["sdf_count"] += 1
        return edge

    def query_sdf(self, edge_id: str,
                  point: Tuple[float, float, float]) -> float:
        """查询 SDF 值"""
        edge = self.sdf_edges.get(edge_id)
        if edge is None:
            raise KeyError(f"SDF 超边不存在: {edge_id}")
        return edge.compute_sdf(point)

    # ── Affordance 超边 ──────────────────────────────────────────

    def create_affordance(self, env_state: Dict[str, Any],
                          actions: List[str],
                          probabilities: Optional[List[float]] = None,
                          edge_id: Optional[str] = None) -> AffordanceHyperedge:
        """创建 Affordance 超边"""
        eid = edge_id or f"aff_{self.stats['affordance_count']}_{int(time.time())}"
        edge = AffordanceHyperedge(
            edge_id=eid,
            environment_state=env_state,
            available_actions=actions,
            action_probabilities=probabilities or [1.0 / len(actions)] * len(actions),
        )
        self.affordance_edges[eid] = edge
        self.stats["affordance_count"] += 1
        return edge

    def get_affordance(self, edge_id: str) -> Optional[AffordanceHyperedge]:
        """获取 Affordance"""
        return self.affordance_edges.get(edge_id)

    def best_action(self, edge_id: str) -> Tuple[str, float]:
        """获取最优可供行动"""
        edge = self.affordance_edges.get(edge_id)
        if edge is None:
            return ("noop", 0.0)
        return edge.get_best_action()

    # ── Kinematic 超边 ───────────────────────────────────────────

    def create_kinematic(self, source: Dict[str, Any],
                         target: Dict[str, Any],
                         transformation: str,
                         params: Optional[Dict[str, float]] = None,
                         edge_id: Optional[str] = None) -> KinematicHyperedge:
        """创建运动学超边"""
        eid = edge_id or f"kin_{self.stats['kinematic_count']}_{int(time.time())}"
        edge = KinematicHyperedge(
            edge_id=eid,
            source_state=source,
            target_state=target,
            transformation=transformation,
            params=params or {},
        )
        self.kinematic_edges[eid] = edge
        self.stats["kinematic_count"] += 1
        return edge

    def predict_state(self, edge_id: str,
                      current_state: Dict[str, Any]) -> Dict[str, Any]:
        """基于运动学超边预测下一个状态"""
        edge = self.kinematic_edges.get(edge_id)
        if edge is None:
            raise KeyError(f"运动学超边不存在: {edge_id}")
        return edge.apply(current_state)

    # ── 世界快照 ─────────────────────────────────────────────────

    def take_snapshot(self, state_vector: Optional[Dict[str, Any]] = None) -> WorldSnapshot:
        """拍摄世界状态快照"""
        snap_id = f"snap_{self.stats['snapshot_count']}_{int(time.time())}"
        all_edges = (list(self.sdf_edges.keys()) +
                     list(self.affordance_edges.keys()) +
                     list(self.kinematic_edges.keys()))

        snap = WorldSnapshot(
            snap_id=snap_id,
            timestamp=time.time(),
            hyperedges=all_edges,
            state_vector=state_vector or self._collect_state(),
        )

        # 计算 κ-Snap 哈希
        snap.ksnap_hash = snap.compute_ksnap_hash()

        # 链接前序快照
        if self.snapshot_chain:
            snap.prev_snap_hash = self.snapshot_chain[-1].ksnap_hash

        # Ω-Gate 校验
        self.omega_gate.verify_snapshot(snap)

        self.snapshot_chain.append(snap)
        self.stats["snapshot_count"] += 1

        if snap.omega_verdict == OmegaGateVerdict.INCONSISTENT:
            logger.warning(f"世界快照 {snap_id} 不一致 (Tetrad={snap.tetrad_score:.4f})")

        return snap

    def _collect_state(self) -> Dict[str, Any]:
        """收集当前世界状态"""
        return {
            "agent_id": self.agent_id,
            "sdf_edges": len(self.sdf_edges),
            "affordance_edges": len(self.affordance_edges),
            "kinematic_edges": len(self.kinematic_edges),
            "snapshot_index": len(self.snapshot_chain),
            "timestamp": time.time(),
        }

    def get_latest_snapshot(self) -> Optional[WorldSnapshot]:
        """获取最近的世界快照"""
        if not self.snapshot_chain:
            return None
        return self.snapshot_chain[-1]

    def cross_verify_last_two(self) -> float:
        """交叉验证最后两个快照"""
        if len(self.snapshot_chain) < 2:
            return 1.0
        return self.omega_gate.cross_verify(
            self.snapshot_chain[-2],
            self.snapshot_chain[-1]
        )

    # ── Tetrad 分析 ──────────────────────────────────────────────

    def compute_tetrad_profile(self) -> Dict:
        """
        计算当前世界模型的四维接合剖面

        Returns:
            {π, Φ, Ω, ℧} 四维分数
        """
        total_edges = max(
            len(self.sdf_edges) +
            len(self.affordance_edges) +
            len(self.kinematic_edges),
            1
        )

        joint = TetradJoint()
        pi_score = joint.pi_coupling(len(self.sdf_edges) / total_edges)
        phi_score = joint.phi_joint(len(self.affordance_edges) / total_edges)
        omega_score = joint.omega_gate(len(self.kinematic_edges) / total_edges)
        mhoo_score = joint.mhoo_anchor(
            len(self.snapshot_chain) / max(len(self.snapshot_chain) + 1, 1)
        )
        composite = joint.joint_score(pi_score, phi_score, omega_score, mhoo_score)

        return {
            "π (periodic)": round(pi_score, 4),
            "Φ (golden ratio)": round(phi_score, 4),
            "Ω (omega gate)": round(omega_score, 4),
            "℧ (anchor)": round(mhoo_score, 4),
            "Tetrad Composite": round(composite, 4),
        }

    def get_stats(self) -> Dict:
        """获取世界模型统计"""
        return {
            **self.stats,
            "tetrad_profile": self.compute_tetrad_profile(),
            "latest_snapshot_tetrad": (
                self.snapshot_chain[-1].tetrad_score
                if self.snapshot_chain else None
            ),
            "consistency": self.cross_verify_last_two(),
        }


# ══════════════════════════════════════════════════════════════════
# 自检
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Structured World Model 自检")
    print("=" * 60)

    wm = StructuredWorldModel(agent_id="TestWM")

    # SDF
    sdf = wm.create_sdf_edge(
        "sphere",
        [(0, 0, 0), (1, 1, 1)],
        {"cx": 0, "cy": 0, "cz": 0, "r": 5.0}
    )
    dist = wm.query_sdf(sdf.edge_id, (3, 4, 0))
    print(f"\n[SDF] 球体表面: point(3,4,0) → distance={dist:.2f}")

    # Affordance
    aff = wm.create_affordance(
        {"pos": (0, 0), "has_key": True},
        ["open_door", "walk_forward", "pick_up"],
    )
    best_action, prob = wm.best_action(aff.edge_id)
    print(f"[Affordance] 最优行动: {best_action} (p={prob:.2f})")

    # Kinematic
    kin = wm.create_kinematic(
        {"x": 0, "y": 0},
        {"x": 1, "y": 1},
        "translate",
        {"dx": 5, "dy": -3}
    )
    new_state = wm.predict_state(kin.edge_id, {"x": 2, "y": 2})
    print(f"[Kinematic] translate(2,2) → {new_state}")

    # Snapshot
    snap1 = wm.take_snapshot({"temperature": 25.0, "light_level": 0.8})
    print(f"\n[Snapshot 1] id={snap1.snap_id}, tetrad={snap1.tetrad_score:.4f}, "
          f"verdict={snap1.omega_verdict.value}")

    snap2 = wm.take_snapshot({"temperature": 25.2, "light_level": 0.78})
    print(f"[Snapshot 2] id={snap2.snap_id}, tetrad={snap2.tetrad_score:.4f}, "
          f"verdict={snap2.omega_verdict.value}")

    consistency = wm.cross_verify_last_two()
    print(f"[Cross-Verify] 快照1↔快照2 一致性: {consistency:.4f}")

    # Tetrad profile
    profile = wm.compute_tetrad_profile()
    print(f"\n[Tetrad Profile]")
    for k, v in profile.items():
        print(f"  {k}: {v}")

    print(f"\n📊 统计: {wm.get_stats()}")
    print("\nStructured World Model 自检完成 ✅")
