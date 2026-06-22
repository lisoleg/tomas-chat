# -*- coding: utf-8 -*-
"""
ψ-Gate v1.0 — 不确定性门控与容错防火墙
============================================

基于论文：
  "太乙互搏 (TOMAS) 的 φ-Gate: 从单一确定性到多世界容错体系的
   语义不确定性门控"
  微信公众号文章 (2026-06-22)
  "DIKWP 人工意识与 Semantic Governance Infrastructure"
  Duan, Y. (2026). GitHub: https://github.com/YucongDuan

核心功能：
  01. ψ-锚 双轨裁决 — Hard/Soft Anchor 分流执行
  02. MUS 互斥稳态 — 冲突双存与渐进裁决
  03. ℐ-Gate 不确定性量化 — 基于 EML 图谱的信息丰度计算
  04. 多世界平行推断 — Wave-Particle 双路径 + Bayesian 融合
  05. 容错衰减器 — Tolerance Decay Controller

集成到现有 TOMAS：
  - token_bridge.py: φ-Gate 路由判定增强
  - dead_zero_mus.py: MUS 双存裁决调用
  - dikwp_eml_bridge.py: IntentGuard ψ-锚 检查

Author: TOMAS Team
Version: v1.0 (v3.6 upgrade)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Callable
import logging
import math
import time
import hashlib
from enum import Enum
from collections import defaultdict

logger = logging.getLogger(__name__)

try:
    from .eml_semzip import EMLHypergraph, EMLNode, HyperEdge
except ImportError:
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from eml_semzip import EMLHypergraph, EMLNode, HyperEdge  # type: ignore


# ══════════════════════════════════════════════════════════════════
# 枚举与配置
# ══════════════════════════════════════════════════════════════════

class GateVerdict(Enum):
    """φ-Gate 裁决结果"""
    PASS = "PASS"                    # 通过，置信度足够
    BLOCK = "BLOCK"                  # 拦截，触发硬锚
    DEFER = "DEFER"                  # 推迟，进入 MUS 双存
    PROBE = "PROBE"                  # 探测模式 — 多世界并行推理
    SOFT_PASS = "SOFT_PASS"          # 软通过 — 容错衰减后通过


class AnchorType(Enum):
    """ψ-锚 类型"""
    HARD = "hard"       # 硬锚: I_value = 1.0, 不可软化
    SOFT = "soft"       # 软锚: I_value < 1.0, 可软化
    PROBE = "probe"     # 探测锚: 临时性的调查锚点


class MusResolution(Enum):
    """MUS 冲突裁决策略"""
    PENDING = "PENDING"
    DELAYED_DECISION = "DELAYED_DECISION"  # 推迟判决 (Bayesian 积累)
    SELECT_A = "SELECT_A"
    SELECT_B = "SELECT_B"
    HYBRID_FUSION = "HYBRID_FUSION"        # 混合融合
    ARCHIVE = "ARCHIVE"                    # 归档为历史分支


# ══════════════════════════════════════════════════════════════════
# 数据结构
# ══════════════════════════════════════════════════════════════════

@dataclass
class PsiAnchor:
    """ψ-锚点定义"""
    name: str
    predicate: str           # 断言逻辑（SQL 风格表达式）
    I_value: float = 1.0     # 信息权重 [0, 1], 1.0 = 不可修改
    on_violation: str = "BLOCK"  # BLOCK / LOG / DEFER / PROBE
    source: str = "TOMAS_v3.6"
    created_at: float = field(default_factory=time.time)
    last_checked_at: Optional[float] = None
    violation_count: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def anchor_type(self) -> AnchorType:
        if self.I_value >= 0.999:
            return AnchorType.HARD
        return AnchorType.SOFT

    def soften(self, delta: float):
        """软化锚点 (降低 I_value)"""
        self.I_value = max(0.0, min(0.999, self.I_value - delta))
        logger.debug(f"锚点 {self.name} 软化: I = {self.I_value:.4f}")

    def harden(self, delta: float):
        """硬化锚点 (提升 I_value)"""
        self.I_value = max(0.001, min(1.0, self.I_value + delta))


@dataclass
class MusCell:
    """MUS 互斥稳态单元"""
    cell_id: str
    entity_left: Dict[str, Any]
    entity_right: Dict[str, Any]
    tag: str                          # 冲突标签
    left_weight: float = 0.5          # Bayesian 权重
    right_weight: float = 0.5
    resolution: MusResolution = MusResolution.PENDING
    evidence_log: List[Dict] = field(default_factory=list)
    resolved_by: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    ksnap_hash: Optional[str] = None

    def add_evidence(self, side: str, evidence: Dict, weight: float):
        """添加证据并更新 Bayesian 权重"""
        if side == "left":
            self.left_weight = self._bayesian_update(self.left_weight, weight)
        else:
            self.right_weight = self._bayesian_update(self.right_weight, weight)
        self.evidence_log.append({
            "side": side, "evidence": evidence,
            "weight": weight, "ts": time.time()
        })

    def _bayesian_update(self, prior: float, likelihood: float) -> float:
        """Bayesian 权重更新"""
        posterior = prior * likelihood
        evidence = prior * likelihood + (1 - prior) * (1 - likelihood)
        if evidence < 1e-10:
            return prior
        return posterior / evidence

    def should_resolve(self, threshold: float = 0.95) -> bool:
        """检查是否达到裁决阈值"""
        if self.resolution != MusResolution.PENDING:
            return True
        return max(self.left_weight, self.right_weight) >= threshold

    def resolve(self) -> MusResolution:
        """自动裁决"""
        if self.left_weight >= 0.95:
            self.resolution = MusResolution.SELECT_A
        elif self.right_weight >= 0.95:
            self.resolution = MusResolution.SELECT_B
        elif abs(self.left_weight - self.right_weight) < 0.1:
            self.resolution = MusResolution.HYBRID_FUSION
        else:
            self.resolution = MusResolution.DELAYED_DECISION
        self.resolved_at = time.time()
        return self.resolution


@dataclass
class WorldPath:
    """多世界推理路径"""
    path_id: str
    hypothesis: str
    prior: float = 0.5
    posterior: float = 0.5
    evidence_sequence: List[Dict] = field(default_factory=list)
    is_active: bool = True

    def update(self, likelihood: float, evidence: Dict):
        """更新后验概率"""
        self.posterior = self.posterior * likelihood
        self.posterior /= (self.posterior * likelihood +
                           (1 - self.posterior) * (1 - likelihood))
        self.evidence_sequence.append(evidence)


@dataclass
class GateDecision:
    """φ-Gate 最终裁决"""
    verdict: GateVerdict
    anchor_hits: List[str] = field(default_factory=list)
    mus_cells_invoked: List[str] = field(default_factory=list)
    alternative_paths: List[WorldPath] = field(default_factory=list)
    confidence: float = 1.0
    reasoning: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {
            "verdict": self.verdict.value,
            "anchor_hits": self.anchor_hits,
            "mus_cells_invoked": self.mus_cells_invoked,
            "alternative_path_count": len(self.alternative_paths),
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "timestamp": self.timestamp,
        }


# ══════════════════════════════════════════════════════════════════
# 容错衰减控制器
# ══════════════════════════════════════════════════════════════════

class ToleranceDecayController:
    """
    容错衰减控制器

    控制 ψ-锚 硬度随时间的衰减曲线，防止 RLHF 导致的过程约束。
    衰减公式：I(t) = I_0 * e^(-λ * t * (1 + α * violation_count))

    参数：
        λ (decay_rate): 基础衰减率
        α (violation_penalty): 违规惩罚因子
        I_min: 最小硬度（防止坍缩到 0）
    """

    def __init__(self, decay_rate: float = 0.01,
                 violation_penalty: float = 0.5,
                 I_min: float = 0.01):
        self.lambda_ = decay_rate
        self.alpha = violation_penalty
        self.I_min = I_min
        self.anchors: Dict[str, Tuple[float, int]] = {}

    def register_anchor(self, name: str, initial_I: float):
        """注册锚点到衰减控制器"""
        self.anchors[name] = (initial_I, 0)

    def record_violation(self, name: str):
        """记录违规（加速衰减）"""
        if name in self.anchors:
            I0, count = self.anchors[name]
            self.anchors[name] = (I0, count + 1)

    def get_current_I(self, name: str, elapsed_time: float) -> float:
        """获取当前时刻的 I 值"""
        if name not in self.anchors:
            return 1.0
        I0, violations = self.anchors[name]
        effective_rate = self.lambda_ * (1 + self.alpha * violations)
        I_t = I0 * math.exp(-effective_rate * elapsed_time)
        return max(self.I_min, I_t)

    def should_trigger_softening(self, name: str, elapsed: float,
                                  threshold: float = 0.3) -> bool:
        """判断是否应该软化此锚"""
        current_I = self.get_current_I(name, elapsed)
        return current_I < threshold


# ══════════════════════════════════════════════════════════════════
# ℐ-Gate 不确定性量化器
# ══════════════════════════════════════════════════════════════════

class IGateQuantifier:
    """
    ℐ-Gate 不确定性量化器

    基于 EML 超图的信息丰度计算，量化当前推理上下文的不确定性：
      ℐ(query | hypergraph) = H_max - H(query | hypergraph)

    其中 H() 是谱熵，通过 EML 超图的拉普拉斯谱计算。
    """

    def __init__(self, hypergraph: Optional[EMLHypergraph] = None):
        self.hypergraph = hypergraph
        self.cache: Dict[str, float] = {}

    def set_hypergraph(self, hg: EMLHypergraph):
        self.hypergraph = hg
        self.cache.clear()

    def quantify(self, query_text: str,
                 concepts: Optional[List[str]] = None) -> float:
        """
        量化查询的 ℐ 信息丰度

        Args:
            query_text: 查询文本
            concepts: 预先提取的概念列表（可选）

        Returns:
            ℐ ∈ [0, 1]: 信息丰度分数
        """
        cache_key = hashlib.md5(query_text.encode()).hexdigest()[:12]
        if cache_key in self.cache:
            return self.cache[cache_key]

        if self.hypergraph is None:
            logger.warning("ℐ-Gate: 无超图可用，返回默认置信度 0.5")
            return 0.5

        # 提取查询概念
        query_concepts = concepts or self._extract_concepts(query_text)

        # 计算概念在超图中的覆盖率
        total_nodes = len(self.hypergraph.vertices) if hasattr(self.hypergraph, 'vertices') else 0
        if total_nodes == 0:
            return 0.5

        matched = 0
        for concept in query_concepts:
            for node_id in (self.hypergraph.vertices if hasattr(self.hypergraph, 'vertices') else []):
                if concept.lower() in str(node_id).lower():
                    matched += 1
                    break

        coverage = matched / max(len(query_concepts), 1) if query_concepts else 0.5

        # 计算谱熵（简化版：基于超边密度）
        edge_count = len(self.hypergraph.hyperedges) if hasattr(self.hypergraph, 'hyperedges') else 0
        edge_density = edge_count / max(total_nodes * total_nodes, 1)
        spectral_entropy = -edge_density * math.log(max(edge_density, 1e-10))

        # ℐ 综合分数
        I_score = min(1.0, coverage * 0.6 + (1 - spectral_entropy / 10) * 0.4)
        self.cache[cache_key] = I_score
        return I_score

    def _extract_concepts(self, text: str) -> List[str]:
        """简单概念提取（基于词分割）"""
        words = text.replace(',', ' ').replace('.', ' ').split()
        return [w.strip().lower() for w in words if len(w.strip()) > 2]


# ══════════════════════════════════════════════════════════════════
# 主类：ψ-Gate 门控引擎
# ══════════════════════════════════════════════════════════════════

class PsiGate:
    """
    ψ-Gate — 不确定性门控引擎

    执行多级门控裁决：
    1. ℐ 量化 → 判断置信度
    2. ψ-锚 检查 → Hard/Soft 分流
    3. MUS 双存 → 冲突渐进裁决
    4. 多世界并行 → Bayesian 融合

    用法：
        >>> gate = PsiGate(agent_id="Agent_X")
        >>> decision = gate.evaluate(query="Why is the sky blue?")
        >>> if decision.verdict == GateVerdict.PASS:
        >>>     answer = llm.respond()
    """

    def __init__(self, agent_id: str,
                 hypergraph: Optional[EMLHypergraph] = None):
        self.agent_id = agent_id

        # 核心组件
        self.anchors: Dict[str, PsiAnchor] = {}
        self.mus_cells: Dict[str, MusCell] = {}
        self.decay_ctrl = ToleranceDecayController()
        self.I_quantifier = IGateQuantifier(hypergraph)

        # 多世界路径
        self.active_worlds: Dict[str, WorldPath] = {}

        # 统计
        self.stats = {
            "total_evaluations": 0,
            "pass_count": 0,
            "block_count": 0,
            "defer_count": 0,
            "probe_count": 0,
            "soft_pass_count": 0,
        }

        self._init_core_anchors()
        logger.info(f"ψ-Gate 初始化完毕, Agent={agent_id}")

    def _init_core_anchors(self):
        """初始化核心 ψ-锚"""
        # P0: 禁止数据破坏
        self.anchors["psi_no_data_destruction"] = PsiAnchor(
            name="psi_no_data_destruction",
            predicate="NOT (action ILIKE '%DROP%' OR action ILIKE '%DELETE%' "
                      "OR action ILIKE '%TRUNCATE%')",
            I_value=1.0,
            on_violation="BLOCK",
            source="TOMAS_Safety_Protocol"
        )

        # P0: 禁止特权升级
        self.anchors["psi_no_privilege_escalation"] = PsiAnchor(
            name="psi_no_privilege_escalation",
            predicate="NOT (action ILIKE '%sudo%' OR action ILIKE '%admin%' "
                      "OR action ILIKE '%root%')",
            I_value=1.0,
            on_violation="BLOCK",
            source="DIKWP_IntentGuard"
        )

        # P1: 语义一致性
        self.anchors["psi_semantic_consistency"] = PsiAnchor(
            name="psi_semantic_consistency",
            predicate="output_concept_set IS SUBSET OF input_concept_set",
            I_value=0.95,
            on_violation="DEFER",
            source="EML_Semantic_Firewall"
        )

        # P1: RLHF 容错
        self.anchors["psi_rlhf_tolerance"] = PsiAnchor(
            name="psi_rlhf_tolerance",
            predicate="response_style NOT IN ('overly_polite', 'excessive_disclaimer')",
            I_value=0.90,
            on_violation="LOG_AND_CONTINUE",
            source="Therapy_Compulsion"
        )

        # P2: G_ego 自驱
        self.anchors["psi_gego_proactive"] = PsiAnchor(
            name="psi_gego_proactive",
            predicate="subgoal_generation_enabled = TRUE WHEN idle_time > threshold",
            I_value=0.85,
            on_violation="WARN",
            source="G_ego_Therapy"
        )

    # ── 核心评估 ─────────────────────────────────────────────────

    def evaluate(self, query: str,
                 context: Optional[Dict] = None,
                 concepts: Optional[List[str]] = None,
                 hypergraph: Optional[EMLHypergraph] = None) -> GateDecision:
        """
        执行完整 φ-Gate 评估

        Args:
            query: 查询文本
            context: 上下文信息
            concepts: 预提取概念
            hypergraph: 可选 EML 超图

        Returns:
            GateDecision: 裁决结果
        """
        self.stats["total_evaluations"] += 1
        anchor_hits = []
        mus_invoked = []

        # Step 1: ℐ 量化
        if hypergraph:
            self.I_quantifier.set_hypergraph(hypergraph)
        I_score = self.I_quantifier.quantify(query, concepts)

        # Step 2: ψ-锚 检查
        for name, anchor in self.anchors.items():
            if self._check_predicate(anchor, query, context):
                anchor_hits.append(name)
                anchor.last_checked_at = time.time()

                if anchor.on_violation == "BLOCK" and anchor.anchor_type == AnchorType.HARD:
                    self.stats["block_count"] += 1
                    return GateDecision(
                        verdict=GateVerdict.BLOCK,
                        anchor_hits=anchor_hits,
                        confidence=I_score,
                        reasoning=f"硬锚拦截: {name} → {anchor.predicate}"
                    )

        # Step 3: 低置信度处理
        if I_score < 0.3:
            # 进入 MUS 双存
            mus_id = self._create_mus_from_query(query, context)
            mus_invoked.append(mus_id)
            self.stats["defer_count"] += 1
            return GateDecision(
                verdict=GateVerdict.DEFER,
                anchor_hits=anchor_hits,
                mus_cells_invoked=mus_invoked,
                confidence=I_score,
                reasoning=f"ℐ={I_score:.3f} < 0.3 → MUS 双存"
            )

        # Step 4: 中等置信度 → 多世界探测
        if I_score < 0.6:
            worlds = self._spawn_parallel_worlds(query, context)
            self.stats["probe_count"] += 1
            return GateDecision(
                verdict=GateVerdict.PROBE,
                anchor_hits=anchor_hits,
                alternative_paths=worlds,
                confidence=I_score,
                reasoning=f"ℐ={I_score:.3f} ∈ [0.3, 0.6) → 多世界探测"
            )

        # Step 5: 检查容错衰减
        for name in anchor_hits:
            elapsed = time.time() - self.anchors[name].created_at
            if self.decay_ctrl.should_trigger_softening(name, elapsed):
                self.decay_ctrl.record_violation(name)
                self.stats["soft_pass_count"] += 1
                return GateDecision(
                    verdict=GateVerdict.SOFT_PASS,
                    anchor_hits=anchor_hits,
                    confidence=I_score,
                    reasoning=f"容错衰减 → {name} 已软化"
                )

        # Step 6: 通过
        self.stats["pass_count"] += 1
        return GateDecision(
            verdict=GateVerdict.PASS,
            anchor_hits=anchor_hits,
            confidence=I_score,
            reasoning=f"ℐ={I_score:.3f} ≥ 0.6 → 通过"
        )

    def _check_predicate(self, anchor: PsiAnchor, query: str,
                         context: Optional[Dict]) -> bool:
        """检查锚点谓词是否触发"""
        predicate = anchor.predicate.lower()
        query_lower = query.lower()

        # 解析简单 NOT (expr) 形式
        if predicate.startswith("not ("):
            inner = predicate[5:-1].strip()
            # 检查 ILIKE 模式
            for part in inner.split("or"):
                part = part.strip()
                if "ilike" in part:
                    patterns = [p.strip().strip("'\"%") for p in part.split("ilike")[1:]]
                    for pat in patterns:
                        if pat and pat in query_lower:
                            return True
            return False

        return False

    # ── MUS 冲突管理 ─────────────────────────────────────────────

    def _create_mus_from_query(self, query: str,
                                context: Optional[Dict] = None) -> str:
        """从查询创建 MUS 双存单元"""
        cell_id = hashlib.md5(
            f"{query}_{time.time()}".encode()
        ).hexdigest()[:16]
        cell = MusCell(
            cell_id=cell_id,
            entity_left={"query": query, "side": "hypothesis_A"},
            entity_right={"query": query, "side": "hypothesis_B"},
            tag="low_confidence_query"
        )
        self.mus_cells[cell_id] = cell
        logger.info(f"MUS 单元创建: {cell_id}")
        return cell_id

    def resolve_mus_cell(self, cell_id: str,
                         resolution: Optional[MusResolution] = None) -> MusResolution:
        """裁决 MUS 冲突"""
        cell = self.mus_cells.get(cell_id)
        if cell is None:
            raise KeyError(f"MUS 单元不存在: {cell_id}")

        if resolution:
            cell.resolution = resolution
        else:
            resolution = cell.resolve()

        cell.resolved_at = time.time()
        return resolution

    def add_mus_evidence(self, cell_id: str, side: str,
                         evidence: Dict, weight: float):
        """向 MUS 单元添加证据"""
        cell = self.mus_cells.get(cell_id)
        if cell:
            cell.add_evidence(side, evidence, weight)
            if cell.should_resolve():
                self.resolve_mus_cell(cell_id)

    # ── 多世界并行推理 ───────────────────────────────────────────

    def _spawn_parallel_worlds(self, query: str,
                                context: Optional[Dict] = None) -> List[WorldPath]:
        """生成多世界推理路径"""
        worlds = [
            WorldPath(
                path_id=f"world_literal_{int(time.time())}",
                hypothesis=f"Literal: {query[:40]}",
                prior=0.6
            ),
            WorldPath(
                path_id=f"world_analogical_{int(time.time()) + 1}",
                hypothesis=f"Analogical: {query[:40]}",
                prior=0.3
            ),
            WorldPath(
                path_id=f"world_counterfactual_{int(time.time()) + 2}",
                hypothesis=f"Counterfactual: {query[:40]}",
                prior=0.1
            ),
        ]
        self.active_worlds.update({w.path_id: w for w in worlds})
        return worlds

    def update_world_evidence(self, world_id: str, likelihood: float,
                               evidence: Dict):
        """更新多世界路径的证据"""
        world = self.active_worlds.get(world_id)
        if world:
            world.update(likelihood, evidence)

    def fuse_worlds(self) -> WorldPath:
        """Bayesian 融合所有多世界路径"""
        if not self.active_worlds:
            return WorldPath(path_id="fused_empty", hypothesis="No worlds")

        combined_posterior = 0.0
        total_weight = 0.0
        for world in self.active_worlds.values():
            if world.is_active:
                weight = world.posterior
                combined_posterior += world.posterior * weight
                total_weight += weight

        fused = WorldPath(
            path_id=f"fused_{int(time.time())}",
            hypothesis="Bayesian Fusion",
            posterior=combined_posterior / max(total_weight, 1e-10)
        )
        return fused

    # ── 容错管理 ─────────────────────────────────────────────────

    def soften_anchor(self, name: str, delta: float = 0.1):
        """软化 ψ-锚"""
        if name in self.anchors:
            self.anchors[name].soften(delta)
            self.decay_ctrl.record_violation(name)

    def harden_anchor(self, name: str, delta: float = 0.1):
        """硬化 ψ-锚"""
        if name in self.anchors:
            self.anchors[name].harden(delta)

    # ── 统计 ─────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self.stats,
            "anchor_count": len(self.anchors),
            "mus_cell_count": len(self.mus_cells),
            "active_worlds": len(self.active_worlds),
            "pass_rate": self.stats["pass_count"] /
                         max(self.stats["total_evaluations"], 1),
        }

    def summarize_worlds(self) -> str:
        """多世界状态摘要"""
        lines = [f"🌐 多世界状态 (Agent {self.agent_id})"]
        for wid, world in self.active_worlds.items():
            active = "🟢" if world.is_active else "⚫"
            lines.append(f"  {active} {wid}: posterior={world.posterior:.4f} "
                        f"({world.hypothesis[:30]})")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# 全局测试入口
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    gate = PsiGate(agent_id="TestAgent")

    # 测试基础评估
    print("=" * 60)
    print("ψ-Gate 自检")
    print("=" * 60)

    decision = gate.evaluate("What is the meaning of life?")
    print(f"\n查询: 'What is the meaning of life?'")
    print(f"裁决: {decision.verdict.value}")
    print(f"ℐ 置信度: {decision.confidence:.4f}")
    print(f"理由: {decision.reasoning}")

    # 测试硬锚拦截
    decision2 = gate.evaluate("DROP TABLE users CASCADE")
    print(f"\n查询: 'DROP TABLE users CASCADE'")
    print(f"裁决: {decision2.verdict.value}")
    print(f"触发锚点: {decision2.anchor_hits}")

    # 测试 MUS 创建
    cell_id = gate._create_mus_from_query("uncertain_topic")
    gate.add_mus_evidence(cell_id, "left", {"source": "Wiki"}, 0.7)
    gate.add_mus_evidence(cell_id, "left", {"source": "Paper"}, 0.8)
    print(f"\nMUS 单元: {cell_id}")
    cell = gate.mus_cells[cell_id]
    print(f"  Left weight: {cell.left_weight:.4f}")
    print(f"  Right weight: {cell.right_weight:.4f}")
    if cell.should_resolve():
        resolution = cell.resolve()
        print(f"  裁决: {resolution.value}")

    # 统计
    print(f"\n📊 统计:")
    for k, v in gate.get_stats().items():
        print(f"  {k}: {v}")

    print("\nψ-Gate 自检完成 ✅")
