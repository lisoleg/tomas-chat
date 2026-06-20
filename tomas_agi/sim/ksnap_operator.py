# -*- coding: utf-8 -*-
"""
KSnapOperator — κ-Snap 显影算符 (TOMAS Axiom A2)
===================================================

Theory Source:
    "κ-Snap（κ-显影）作为时间与因果的本体论基石"
    (微信公众号文章, 章锋, 2026-06-18)

Core Concepts:
    1. κ-Snap 是投影算符 Π_κ，作用于 EML 超图的候选超边集
    2. 未 κ-Snap：超边仅作为候选关系（Candidate），处于叠加态
    3. κ-Snap：在观测基 Π 下投影为经典事实（Classical Fact）
    4. 时间 = κ-Snap 序列的偏序集（Partial Order）
    5. 与量子坍缩的区别：有载体(EML超边)、有动力(Ftel)、有裁判(MUS/G_ego)

Trigger Conditions:
    1. Ftel 阈值: |Ftel(e)| >= θ_ftel
    2. 无 MUS 冲突: e 未被标记为互斥稳态双存
    3. 观测基就绪: Π 已选定（由 G_ego 或物理环境决定）

Results:
    - Manifest: 超边成为经典事实，写入因果日志
    - Reject: Dead-Zero 或 MUS 激活且未裁决，信息耗散入未显影仓
    - Suspend: MUS 激活，挂起等待 G_ego 裁决

Author: TOMAS Team
Version: v1.0
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ============================================================
# 枚举与常量
# ============================================================

class SnapResult(Enum):
    """κ-Snap 执行结果"""
    MANIFESTED = "manifested"      # 显影成功
    REJECT_DZ = "reject_dz"        # Dead-Zero 拒绝
    SUSPEND_MUS = "suspend_mus"    # MUS 挂起
    REJECT_FTEL = "reject_ftel"    # Ftel 不足


class ObservationBase(Enum):
    """观测基类型"""
    SENSOR = "sensor"        # 感知基（空间位置/传感器触发）
    ACTUATOR = "actuator"    # 执行基（物理指令）
    ETHICAL = "ethical"      # 伦理决策基
    COGNITIVE = "cognitive"  # 认知基（推理/记忆）


# ============================================================
# 数据结构
# ============================================================

@dataclass
class CandidateEdge:
    """候选超边（未 κ-Snap）"""
    edge_id: str
    source: str
    target: str
    relation: str
    i_value: float                           # ℐ 信息存在度
    ftel_magnitude: float                    # |Ftel| 流贯强度
    features: Dict[str, Any] = field(default_factory=dict)
    mus_active: bool = False                 # 是否 MUS 激活
    std_ref: Optional[str] = None            # 标准引用
    timestamp: float = field(default_factory=time.time)


@dataclass
class ManifestedEdge:
    """显影超边（经典事实）"""
    edge_id: str
    source: str
    target: str
    relation: str
    i_value: float
    observation_base: ObservationBase
    snap_timestamp: float
    psi_anchor: str                          # ψ-锚（因果链标识）
    features: Dict[str, Any] = field(default_factory=dict)
    std_ref: Optional[str] = None


@dataclass
class SnapEvent:
    """κ-Snap 事件（因果日志条目）"""
    event_id: str
    candidate_id: str
    result: SnapResult
    observation_base: ObservationBase
    timestamp: float
    reason: str = ""
    manifested_edge: Optional[ManifestedEdge] = None

    # v2.0 代码演化扩展字段
    new_code_hash: Optional[str] = None      # 新代码的哈希值
    trigger_obs_id: Optional[str] = None     # 触发此次修改的观测ID
    llm_version: Optional[str] = None        # 生成代码的LLM版本

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "candidate_id": self.candidate_id,
            "result": self.result.value,
            "observation_base": self.observation_base.value,
            "timestamp": self.timestamp,
            "reason": self.reason,
            "manifested": self.manifested_edge is not None,
            "new_code_hash": self.new_code_hash,
            "trigger_obs_id": self.trigger_obs_id,
            "llm_version": self.llm_version,
        }


# ============================================================
# κ-Snap 算子
# ============================================================

class KSnapOperator:
    """
    κ-Snap 显影算符 (Axiom A2)

    将候选超边投影为经典事实，构建时间箭头（偏序集）。

    Algorithm (Article 1, Appendix B):
        1. Dead-Zero Check
        2. MUS Check
        3. Perform Snap (Projection)
        4. Write to Classical KB
        5. Log causality
    """

    def __init__(
        self,
        theta_ftel: float = 0.1,
        theta_dead: float = 0.01,
        dead_zero_checker=None,
        mus_arbiter=None,
    ):
        self.theta_ftel = theta_ftel
        self.theta_dead = theta_dead
        self.dead_zero_checker = dead_zero_checker
        self.mus_arbiter = mus_arbiter

        # 因果日志（偏序集 T）
        self.causal_log: List[SnapEvent] = []
        # 显影事实库
        self.manifested_kb: Dict[str, ManifestedEdge] = {}
        # 未显影仓（耗散信息）
        self.latent_pool: List[CandidateEdge] = []

    def execute(
        self,
        candidate: CandidateEdge,
        obs_base: ObservationBase = ObservationBase.COGNITIVE,
    ) -> SnapEvent:
        """
        执行 κ-Snap 投影算符

        Returns:
            SnapEvent: 包含结果和（如有）显影超边
        """
        event_id = f"snap_{uuid.uuid4().hex[:8]}"
        timestamp = time.time()

        # 1. Ftel 阈值检查
        if candidate.ftel_magnitude < self.theta_ftel:
            event = SnapEvent(
                event_id=event_id,
                candidate_id=candidate.edge_id,
                result=SnapResult.REJECT_FTEL,
                observation_base=obs_base,
                timestamp=timestamp,
                reason=f"Ftel insufficient: {candidate.ftel_magnitude:.4f} < {self.theta_ftel}",
            )
            self.latent_pool.append(candidate)
            self.causal_log.append(event)
            logger.debug("κ-Snap REJECT_FTEL: %s (ftel=%.4f)", candidate.edge_id, candidate.ftel_magnitude)
            return event

        # 2. Dead-Zero 检查
        is_dead = False
        dz_reason = ""
        if self.dead_zero_checker is not None:
            try:
                is_dead, dz_reason = self.dead_zero_checker.check_dead_zero_dikwp(
                    candidate.i_value, "data"
                )
            except Exception:
                is_dead = candidate.i_value < self.theta_dead
                dz_reason = f"ℐ={candidate.i_value:.4f} < θ_dead={self.theta_dead}"
        else:
            is_dead = candidate.i_value < self.theta_dead
            dz_reason = f"ℐ={candidate.i_value:.4f} < θ_dead={self.theta_dead}"

        if is_dead:
            event = SnapEvent(
                event_id=event_id,
                candidate_id=candidate.edge_id,
                result=SnapResult.REJECT_DZ,
                observation_base=obs_base,
                timestamp=timestamp,
                reason=f"Dead-Zero: {dz_reason}",
            )
            self.latent_pool.append(candidate)
            self.causal_log.append(event)
            logger.info("κ-Snap REJECT_DZ: %s (%s)", candidate.edge_id, dz_reason)
            return event

        # 3. MUS 检查
        mus_active = candidate.mus_active
        if not mus_active and self.mus_arbiter is not None:
            try:
                mus_result = self.mus_arbiter.check_mus(candidate.edge_id, candidate)
                mus_active = mus_result.is_mus_active if hasattr(mus_result, "is_mus_active") else False
            except Exception:
                pass

        if mus_active:
            event = SnapEvent(
                event_id=event_id,
                candidate_id=candidate.edge_id,
                result=SnapResult.SUSPEND_MUS,
                observation_base=obs_base,
                timestamp=timestamp,
                reason="MUS active: dual-state suspended, awaiting G_ego adjudication",
            )
            # 不写入 latent_pool，挂起等待裁决
            self.causal_log.append(event)
            logger.info("κ-Snap SUSPEND_MUS: %s (awaiting adjudication)", candidate.edge_id)
            return event

        # 4. 执行投影（显影）
        psi_anchor = f"ψ_{uuid.uuid4().hex[:12]}"
        manifested = ManifestedEdge(
            edge_id=candidate.edge_id,
            source=candidate.source,
            target=candidate.target,
            relation=candidate.relation,
            i_value=candidate.i_value,
            observation_base=obs_base,
            snap_timestamp=timestamp,
            psi_anchor=psi_anchor,
            features=candidate.features.copy(),
            std_ref=candidate.std_ref,
        )

        # 5. 写入经典事实库
        self.manifested_kb[manifested.edge_id] = manifested

        # 6. 记录因果日志
        event = SnapEvent(
            event_id=event_id,
            candidate_id=candidate.edge_id,
            result=SnapResult.MANIFESTED,
            observation_base=obs_base,
            timestamp=timestamp,
            reason="Manifested successfully",
            manifested_edge=manifested,
        )
        self.causal_log.append(event)
        logger.info("κ-Snap MANIFESTED: %s → ψ=%s (ℐ=%.4f)", candidate.edge_id, psi_anchor, candidate.i_value)
        return event

    def get_causal_chain(self, edge_id: str) -> List[SnapEvent]:
        """获取某超边的因果链（偏序集前驱）"""
        return [e for e in self.causal_log if e.candidate_id == edge_id]

    def get_time_order(self) -> List[Tuple[str, str, float]]:
        """
        获取时间偏序集 T = (events, ≤)
        返回 [(event_id, candidate_id, timestamp), ...] 按时间排序
        """
        return [(e.event_id, e.candidate_id, e.timestamp) for e in sorted(self.causal_log, key=lambda x: x.timestamp)]

    def un_snap(self, edge_id: str) -> bool:
        """
        Un-Snap 操作（需要访问全 EML 超图，物理不可达）

        Article 1, Theorem 4.1:
            "Un-Snap 需访问全 EML 超图，物理不可达"
            此方法始终返回 False，证明 κ-Snap 不可逆性。
        """
        logger.warning("Un-Snap attempted for %s — physically unreachable (Theorem 4.1)", edge_id)
        return False

    @staticmethod
    def batch_merkle_root(events: List["SnapEvent"]) -> str:
        """计算一批 SnapEvent 的 Merkle Root（用于 Mina/Celo 上链存证）。

        将每个 event 的 event_id + timestamp + new_code_hash 拼接后 SHA-256，
        然后两两配对计算父节点哈希，直到只剩一个根哈希。
        如果事件数为奇数，最后一个节点直接晋升。

        Args:
            events: SnapEvent 列表

        Returns:
            十六进制 Merkle Root 字符串。空列表返回 "0" * 64。
        """
        import hashlib

        # 1. 空列表 → 返回全零
        if not events:
            return "0" * 64

        # 2. 计算每个 event 的叶子哈希
        leaves: List[str] = []
        for event in events:
            data = f"{event.event_id}{event.timestamp}{event.new_code_hash or ''}"
            leaf_hash = hashlib.sha256(data.encode("utf-8")).hexdigest()
            leaves.append(leaf_hash)

        # 3. 两两配对构建 Merkle 树
        while len(leaves) > 1:
            next_level: List[str] = []
            i = 0
            while i < len(leaves):
                if i + 1 < len(leaves):
                    # 配对：parent = SHA-256(left + right)
                    parent = hashlib.sha256(
                        (leaves[i] + leaves[i + 1]).encode("utf-8")
                    ).hexdigest()
                    next_level.append(parent)
                    i += 2
                else:
                    # 奇数个：最后一个直接晋升
                    next_level.append(leaves[i])
                    i += 1
            leaves = next_level

        # 6. 返回根哈希
        return leaves[0]

    def create_code_evolution_snap(
        self,
        candidate_id: str,
        new_code_hash: str,
        trigger_obs_id: str,
        llm_version: str,
        reason: str = "",
    ) -> "SnapEvent":
        """创建代码演化 SnapEvent。

        记录哥德尔智能体的代码自改事件。

        Args:
            candidate_id: 候选代码ID
            new_code_hash: 新代码的SHA-256哈希
            trigger_obs_id: 触发此次修改的观测事件ID
            llm_version: 生成代码的LLM版本标识
            reason: 修改原因描述

        Returns:
            SnapEvent 实例
        """
        event_id = f"evo_{uuid.uuid4().hex[:8]}"
        timestamp = time.time()

        # 1. 创建 SnapEvent，result=MANIFESTED, observation_base=ACTUATOR
        event = SnapEvent(
            event_id=event_id,
            candidate_id=candidate_id,
            result=SnapResult.MANIFESTED,
            observation_base=ObservationBase.ACTUATOR,
            timestamp=timestamp,
            reason=reason or f"Code evolution: candidate={candidate_id}, llm={llm_version}",
            manifested_edge=None,
            # 2. 设置 v2.0 扩展字段
            new_code_hash=new_code_hash,
            trigger_obs_id=trigger_obs_id,
            llm_version=llm_version,
        )

        # 3. 记录到因果日志
        self.causal_log.append(event)

        logger.info(
            "κ-Snap CODE_EVOLUTION: %s (hash=%s, llm=%s, trigger=%s)",
            candidate_id,
            new_code_hash[:8] if new_code_hash else "N/A",
            llm_version,
            trigger_obs_id,
        )
        return event

    def stats(self) -> dict:
        """统计信息"""
        total = len(self.causal_log)
        manifested = sum(1 for e in self.causal_log if e.result == SnapResult.MANIFESTED)
        rejected = sum(1 for e in self.causal_log if e.result == SnapResult.REJECT_DZ)
        suspended = sum(1 for e in self.causal_log if e.result == SnapResult.SUSPEND_MUS)
        ftel_rejected = sum(1 for e in self.causal_log if e.result == SnapResult.REJECT_FTEL)
        return {
            "total_snaps": total,
            "manifested": manifested,
            "rejected_dz": rejected,
            "suspended_mus": suspended,
            "rejected_ftel": ftel_rejected,
            "manifest_rate": manifested / total if total > 0 else 0.0,
            "latent_pool_size": len(self.latent_pool),
            "kb_size": len(self.manifested_kb),
        }


# ============================================================
# 感知上行 / 执行下行 便捷函数
# ============================================================

def perception_k_snap(
    sensor_data: Dict[str, Any],
    ksnap: KSnapOperator,
    i_value: float = 0.5,
    ftel: float = 0.5,
) -> SnapEvent:
    """
    感知上行：sensor_data → 候选超边 → κ-Snap

    Article 1, Section 6.1:
        1. 生成候选超边
        2. T_Shield 校验（Dead-Zero）
        3. κ-Snap 触发
        4. 显影：写入 EML KB
    """
    candidate = CandidateEdge(
        edge_id=f"perc_{uuid.uuid4().hex[:8]}",
        source=sensor_data.get("source", "sensor"),
        target=sensor_data.get("target", "eml_graph"),
        relation=sensor_data.get("relation", "perceives"),
        i_value=i_value,
        ftel_magnitude=ftel,
        features=sensor_data,
    )
    return ksnap.execute(candidate, ObservationBase.SENSOR)


def actuation_k_snap(
    decision: Dict[str, Any],
    ksnap: KSnapOperator,
    i_value: float = 0.7,
    ftel: float = 0.7,
) -> SnapEvent:
    """
    执行下行：decision → 候选决策超边 → κ-Snap → 物理指令

    Article 1, Section 6.2:
        1. 候选决策超边
        2. 检查 MUS
        3. 显影为物理指令
        4. 记录因果链
    """
    candidate = CandidateEdge(
        edge_id=f"act_{uuid.uuid4().hex[:8]}",
        source=decision.get("source", "g_ego"),
        target=decision.get("target", "actuator"),
        relation=decision.get("relation", "executes"),
        i_value=i_value,
        ftel_magnitude=ftel,
        mus_active=decision.get("mus_active", False),
        features=decision,
    )
    return ksnap.execute(candidate, ObservationBase.ACTUATOR)


# ============================================================
# Self-Test
# ============================================================
if __name__ == "__main__":
    import hashlib

    print("=" * 64)
    print("  KSnapOperator — Self-Test Suite")
    print("=" * 64)

    ksnap = KSnapOperator(theta_ftel=0.1, theta_dead=0.01)

    # ── 1. 基本 κ-Snap 流程 ──
    print("\n[1] Testing basic κ-Snap flow...")
    candidate = CandidateEdge(
        edge_id="cand_001",
        source="sensor_A",
        target="eml_node_1",
        relation="perceives",
        i_value=0.8,
        ftel_magnitude=0.5,
    )
    event = ksnap.execute(candidate, ObservationBase.SENSOR)
    assert event.result == SnapResult.MANIFESTED, f"Expected MANIFESTED, got {event.result}"
    assert event.manifested_edge is not None
    print(f"  [PASS] Basic snap: result={event.result.value}, edge_id={event.candidate_id}")

    # ── 2. SnapEvent 新字段序列化 ──
    print("\n[2] Testing SnapEvent v2.0 new fields serialization...")
    evo_event = SnapEvent(
        event_id="evo_test_001",
        candidate_id="cand_code_001",
        result=SnapResult.MANIFESTED,
        observation_base=ObservationBase.ACTUATOR,
        timestamp=1234567890.0,
        reason="Test code evolution",
        new_code_hash="abc123def456",
        trigger_obs_id="obs_trigger_001",
        llm_version="gpt-4-turbo-2024",
    )
    evo_dict = evo_event.to_dict()
    assert evo_dict["new_code_hash"] == "abc123def456", "new_code_hash mismatch"
    assert evo_dict["trigger_obs_id"] == "obs_trigger_001", "trigger_obs_id mismatch"
    assert evo_dict["llm_version"] == "gpt-4-turbo-2024", "llm_version mismatch"
    print(f"  [PASS] to_dict() includes v2.0 fields: "
          f"new_code_hash={evo_dict['new_code_hash']}, "
          f"trigger_obs_id={evo_dict['trigger_obs_id']}, "
          f"llm_version={evo_dict['llm_version']}")

    # 验证旧事件（无新字段）也能正常序列化
    legacy_event = SnapEvent(
        event_id="legacy_001",
        candidate_id="cand_old",
        result=SnapResult.REJECT_DZ,
        observation_base=ObservationBase.COGNITIVE,
        timestamp=1234567891.0,
        reason="Legacy event",
    )
    legacy_dict = legacy_event.to_dict()
    assert legacy_dict["new_code_hash"] is None, "Legacy new_code_hash should be None"
    assert legacy_dict["trigger_obs_id"] is None, "Legacy trigger_obs_id should be None"
    assert legacy_dict["llm_version"] is None, "Legacy llm_version should be None"
    print(f"  [PASS] Legacy event backward-compatible: new_code_hash={legacy_dict['new_code_hash']}")

    # ── 3. batch_merkle_root — 空列表 ──
    print("\n[3] Testing batch_merkle_root() with empty list...")
    empty_root = KSnapOperator.batch_merkle_root([])
    assert empty_root == "0" * 64, f"Expected all-zeros, got {empty_root}"
    assert len(empty_root) == 64, f"Expected 64-char hex, got len={len(empty_root)}"
    print(f"  [PASS] Empty list root: {empty_root}")

    # ── 4. batch_merkle_root — 1个事件 ──
    print("\n[4] Testing batch_merkle_root() with 1 event...")
    single_event = SnapEvent(
        event_id="single_001",
        candidate_id="cand_single",
        result=SnapResult.MANIFESTED,
        observation_base=ObservationBase.COGNITIVE,
        timestamp=1000.0,
        new_code_hash="hash_001",
    )
    single_root = KSnapOperator.batch_merkle_root([single_event])
    expected_single = hashlib.sha256(
        f"single_001{1000.0}hash_001".encode("utf-8")
    ).hexdigest()
    assert single_root == expected_single, (
        f"Single event root mismatch: {single_root} != {expected_single}"
    )
    print(f"  [PASS] Single event root: {single_root}")

    # ── 5. batch_merkle_root — 2个事件 ──
    print("\n[5] Testing batch_merkle_root() with 2 events...")
    ev1 = SnapEvent(
        event_id="ev_001", candidate_id="c1", result=SnapResult.MANIFESTED,
        observation_base=ObservationBase.COGNITIVE, timestamp=1000.0,
        new_code_hash="hash_A",
    )
    ev2 = SnapEvent(
        event_id="ev_002", candidate_id="c2", result=SnapResult.MANIFESTED,
        observation_base=ObservationBase.COGNITIVE, timestamp=2000.0,
        new_code_hash="hash_B",
    )
    two_root = KSnapOperator.batch_merkle_root([ev1, ev2])
    leaf1 = hashlib.sha256(f"ev_001{1000.0}hash_A".encode("utf-8")).hexdigest()
    leaf2 = hashlib.sha256(f"ev_002{2000.0}hash_B".encode("utf-8")).hexdigest()
    expected_two = hashlib.sha256((leaf1 + leaf2).encode("utf-8")).hexdigest()
    assert two_root == expected_two, (
        f"Two-event root mismatch: {two_root} != {expected_two}"
    )
    print(f"  [PASS] Two events root: {two_root}")

    # ── 6. batch_merkle_root — 3个事件（奇数晋升）──
    print("\n[6] Testing batch_merkle_root() with 3 events (odd promotion)...")
    ev3 = SnapEvent(
        event_id="ev_003", candidate_id="c3", result=SnapResult.MANIFESTED,
        observation_base=ObservationBase.COGNITIVE, timestamp=3000.0,
        new_code_hash="hash_C",
    )
    three_root = KSnapOperator.batch_merkle_root([ev1, ev2, ev3])
    # Level 0: leaf1, leaf2, leaf3
    leaf3 = hashlib.sha256(f"ev_003{3000.0}hash_C".encode("utf-8")).hexdigest()
    # Level 1: parent01 = SHA256(leaf1+leaf2), leaf3 promoted
    parent01 = hashlib.sha256((leaf1 + leaf2).encode("utf-8")).hexdigest()
    # Level 2: root = SHA256(parent01 + leaf3)
    expected_three = hashlib.sha256((parent01 + leaf3).encode("utf-8")).hexdigest()
    assert three_root == expected_three, (
        f"Three-event root mismatch: {three_root} != {expected_three}"
    )
    print(f"  [PASS] Three events root (odd promotion): {three_root}")

    # ── 7. batch_merkle_root — new_code_hash 为 None ──
    print("\n[7] Testing batch_merkle_root() with None new_code_hash...")
    ev_no_hash = SnapEvent(
        event_id="ev_no_hash", candidate_id="c4", result=SnapResult.MANIFESTED,
        observation_base=ObservationBase.COGNITIVE, timestamp=4000.0,
        new_code_hash=None,
    )
    no_hash_root = KSnapOperator.batch_merkle_root([ev_no_hash])
    expected_no_hash = hashlib.sha256(
        f"ev_no_hash{4000.0}".encode("utf-8")
    ).hexdigest()
    assert no_hash_root == expected_no_hash, (
        f"None-hash root mismatch: {no_hash_root} != {expected_no_hash}"
    )
    print(f"  [PASS] None new_code_hash root: {no_hash_root}")

    # ── 8. create_code_evolution_snap ──
    print("\n[8] Testing create_code_evolution_snap()...")
    evo_ksnap = KSnapOperator(theta_ftel=0.1, theta_dead=0.01)
    code_hash = hashlib.sha256(b"def new_func(): pass").hexdigest()
    snap_event = evo_ksnap.create_code_evolution_snap(
        candidate_id="cand_code_v2",
        new_code_hash=code_hash,
        trigger_obs_id="obs_20260613_001",
        llm_version="claude-3.5-sonnet",
        reason="Optimize G_ego ψ-alignment check",
    )
    assert snap_event.result == SnapResult.MANIFESTED, "Expected MANIFESTED"
    assert snap_event.observation_base == ObservationBase.ACTUATOR, "Expected ACTUATOR"
    assert snap_event.new_code_hash == code_hash, "new_code_hash mismatch"
    assert snap_event.trigger_obs_id == "obs_20260613_001", "trigger_obs_id mismatch"
    assert snap_event.llm_version == "claude-3.5-sonnet", "llm_version mismatch"
    assert snap_event in evo_ksnap.causal_log, "Event not recorded in causal_log"
    print(f"  [PASS] Code evolution snap: event_id={snap_event.event_id}, "
          f"result={snap_event.result.value}, llm={snap_event.llm_version}")

    # ── 9. create_code_evolution_snap 默认 reason ──
    print("\n[9] Testing create_code_evolution_snap() with default reason...")
    snap_default = evo_ksnap.create_code_evolution_snap(
        candidate_id="cand_code_v3",
        new_code_hash=hashlib.sha256(b"v3").hexdigest(),
        trigger_obs_id="obs_002",
        llm_version="gpt-4o",
    )
    assert snap_default.reason != "", "Default reason should not be empty"
    assert "cand_code_v3" in snap_default.reason or "gpt-4o" in snap_default.reason
    print(f"  [PASS] Default reason: {snap_default.reason}")

    # ── 10. 多个 code evolution 事件的 Merkle root ──
    print("\n[10] Testing Merkle root across multiple code evolution events...")
    evo_events = evo_ksnap.causal_log  # 包含 snap_event 和 snap_default
    multi_root = KSnapOperator.batch_merkle_root(evo_events)
    assert len(multi_root) == 64, f"Expected 64-char root, got len={len(multi_root)}"
    assert multi_root != "0" * 64, "Non-empty list should not return all-zeros"
    print(f"  [PASS] Multi-event Merkle root ({len(evo_events)} events): {multi_root}")

    # ── 11. stats 包含 code evolution 事件 ──
    print("\n[11] Testing stats() includes code evolution events...")
    s = evo_ksnap.stats()
    assert s["total_snaps"] == 2, f"Expected 2 total snaps, got {s['total_snaps']}"
    assert s["manifested"] == 2, f"Expected 2 manifested, got {s['manifested']}"
    print(f"  [PASS] Stats: total={s['total_snaps']}, manifested={s['manifested']}")

    print("\n" + "=" * 64)
    print("  KSnapOperator — All Self-Tests Passed")
    print("=" * 64)
