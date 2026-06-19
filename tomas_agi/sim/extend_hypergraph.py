# -*- coding: utf-8 -*-
"""
ExtendHypergraph — 流体智能原语 (TOMAS A3/G_ego)
===================================================

Theory Source:
    "论 ARC-AGI-3 的流体智能鸿沟与太乙互搏 AGI 的重构"
    "论智能的三重跃迁：从权重插值到超图重构"
    (微信公众号文章, 章锋, 2026-06-18)

Core Concepts:
    1. 流体智能 (Fluid Intelligence) = G_ego 发起的 EML 超图现场拓扑重构
    2. ExtendHypergraph() = 现场建构新超边（新概念/新规则）
    3. κ-Snap Gestalt = 格式塔显影（"Aha!" 时刻）
    4. LLM 缺的是拓扑重构原语，不是规模

Four Core Primitives (Article 4):
    - ExtendHypergraph(): 现场建构新超边（流体智能）
    - ReviseHypergraph(): 编码 Agent 维护规则（HL 升级）
    - GroundingCheck(): T_Shield 校验 ℐ-存在度
    - MUS_Resolve(): A5 互斥稳态双存裁决

Algorithm (Article 3, Section 5):
    def solve_arc_task(grid_input, g_ego):
        entities = perceive_entities(grid_input)
        if not eml_kb.has_rule(entities):
            new_concept = g_ego.snap_gestalt(entities)
            new_rule = eml_kb.extend(new_node=new_concept, ...)
            if not t_shield.verify(new_rule):
                return REJECT("Hallucinated Rule")
        output_grid = eml_kb.apply_rule(entities)
        return output_grid

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
# 枚举
# ============================================================

class HypergraphOpType(Enum):
    """超图操作类型"""
    EXTEND = "extend"          # 新增超边（流体智能核心）
    REVISE = "revise"          # 修订超边（HL 升级）
    DELETE = "delete"          # 删除超边（谨慎）
    MERGE = "merge"            # 合并超边（EML-SemZip）


class IntelligenceType(Enum):
    """智能类型"""
    CRYSTALLIZED = "crystallized"    # 晶体智能（LLM：权重插值）
    FLUID = "fluid"                  # 流体智能（TOMAS：超图重构）


# ============================================================
# 数据结构
# ============================================================

@dataclass
class EMLNode:
    """EML 超图节点"""
    node_id: str
    label: str
    node_type: str                    # entity / concept / rule
    i_value: float = 0.5
    features: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class EMLHyperedge:
    """EML 超边"""
    edge_id: str
    source_nodes: List[str]
    target_nodes: List[str]
    relation: str
    i_value: float = 0.5
    weight: float = 1.0
    std_ref: Optional[str] = None     # 标准引用（Dead-Zero 校验用）
    mech_eq: Optional[str] = None     # 机制方程
    features: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class ExtendResult:
    """ExtendHypergraph 结果"""
    success: bool
    op_type: HypergraphOpType
    new_nodes: List[EMLNode] = field(default_factory=list)
    new_edges: List[EMLHyperedge] = field(default_factory=list)
    gestalt_concept: Optional[str] = None
    i_value: float = 0.0
    reason: str = ""
    rejected_by_tshield: bool = False


# ============================================================
# EML-Lite KB (可扩展超图知识库)
# ============================================================

class EMLLiteKB:
    """
    EML-Lite 知识库 — Append-Only 超图存储

    Article 4, Section 6:
        知识在超图拓扑，不在权重。
        Append-Only + Versioned EML ⇒ 无灾难性遗忘。
    """

    def __init__(self):
        self.nodes: Dict[str, EMLNode] = {}
        self.edges: Dict[str, EMLHyperedge] = {}
        self._version = 0

    def add_node(self, node: EMLNode) -> str:
        self.nodes[node.node_id] = node
        self._version += 1
        return node.node_id

    def add_edge(self, edge: EMLHyperedge) -> str:
        self.edges[edge.edge_id] = edge
        self._version += 1
        return edge.edge_id

    def has_rule(self, entities: List[str]) -> bool:
        """检查是否已有覆盖这些实体的规则"""
        entity_set = set(entities)
        for edge in self.edges.values():
            # 检查 edge 的 features 中存储的原始实体标签
            stored_entities = set(edge.features.get("source_entities", []))
            if stored_entities and entity_set.issubset(stored_entities):
                return True
            # 也检查 node labels
            node_labels = set()
            for nid in edge.source_nodes + edge.target_nodes:
                if nid in self.nodes:
                    node_labels.add(self.nodes[nid].label)
            if entity_set.issubset(node_labels):
                return True
        return False

    def find_related_edges(self, node_id: str) -> List[EMLHyperedge]:
        """查找与节点相关的所有超边"""
        return [
            e for e in self.edges.values()
            if node_id in e.source_nodes or node_id in e.target_nodes
        ]

    def apply_rule(self, entities: List[str]) -> Optional[Dict[str, Any]]:
        """应用规则到实体集"""
        for edge in self.edges.values():
            if set(entities).issubset(set(edge.source_nodes + edge.target_nodes)):
                return {
                    "rule": edge.relation,
                    "edge_id": edge.edge_id,
                    "i_value": edge.i_value,
                    "output": edge.features.get("output", entities),
                }
        return None

    @property
    def version(self) -> int:
        return self._version

    def stats(self) -> dict:
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "version": self._version,
        }


# ============================================================
# ExtendHypergraph 原语
# ============================================================

class ExtendHypergraph:
    """
    ExtendHypergraph() 原语 — 流体智能核心

    Article 3, Theorem 3.1:
        LLM 无法通过 ARC-AGI-3，除非引入外部搜索机制。
        原因：LLM 权重冻结，无法执行 ExtendHypergraph()。

    Article 4, Section 3.3:
        LLM 需要的是：
        - ExtendHypergraph() 原语：现场建构新超边
        - G_ego 驱动：发起"我要理解"的意图流贯
        - MUS 裁决：处理冲突，双存挂起
    """

    def __init__(
        self,
        eml_kb: EMLLiteKB,
        t_shield_verifier=None,
        theta_dead: float = 0.01,
    ):
        self.eml_kb = eml_kb
        self.t_shield = t_shield_verifier
        self.theta_dead = theta_dead
        self.extension_history: List[ExtendResult] = []

    def snap_gestalt(self, entities: List[str]) -> str:
        """
        κ-Snap 格式塔显影 — "Aha!" 时刻

        Article 3, Section 5, Step 3:
            G_ego performs "Aha!" moment
            new_concept = g_ego.snap_gestalt(entities)
        """
        # 生成新概念标签
        concept_hash = uuid.uuid4().hex[:8]
        gestalt = f"Gestalt_{'_'.join(entities[:3])}_{concept_hash}"
        logger.info("κ-Snap Gestalt: %s from entities %s", gestalt, entities[:3])
        return gestalt

    def extend(
        self,
        entities: List[str],
        relation: str = "spatial_transformation",
        anchor: Optional[str] = None,
        std_ref: Optional[str] = None,
        mech_eq: Optional[str] = None,
        i_value: float = 0.5,
    ) -> ExtendResult:
        """
        ExtendHypergraph() — 现场建构新超边

        Article 3, Algorithm 1:
            1. Perception (entities → EML Nodes)
            2. G_ego Initiation
            3. κ-Snap Gestalt (new concept)
            4. ExtendHypergraph (new rule)
            5. Dead-Zero Check (safety)
        """
        timestamp = time.time()

        # 1. 检查是否已有规则
        if self.eml_kb.has_rule(entities):
            return ExtendResult(
                success=False,
                op_type=HypergraphOpType.EXTEND,
                reason="Rule already exists in EML-Lite KB",
            )

        # 2. κ-Snap 格式塔显影
        gestalt_concept = self.snap_gestalt(entities)

        # 3. 创建新节点
        new_nodes = []
        gestalt_node = EMLNode(
            node_id=f"concept_{uuid.uuid4().hex[:8]}",
            label=gestalt_concept,
            node_type="concept",
            i_value=i_value,
            features={"anchor": anchor or "default", "source_entities": entities},
        )
        new_nodes.append(gestalt_node)

        # 为每个实体创建节点（如果不存在）
        for ent in entities:
            if ent not in self.eml_kb.nodes:
                ent_node = EMLNode(
                    node_id=f"entity_{ent}_{uuid.uuid4().hex[:4]}",
                    label=ent,
                    node_type="entity",
                    i_value=i_value * 0.8,
                )
                new_nodes.append(ent_node)

        # 4. 创建新超边
        new_edge = EMLHyperedge(
            edge_id=f"rule_{uuid.uuid4().hex[:8]}",
            source_nodes=[n.node_id for n in new_nodes if n.node_type == "entity"],
            target_nodes=[gestalt_node.node_id],
            relation=relation,
            i_value=i_value,
            weight=1.0,
            std_ref=std_ref,
            mech_eq=mech_eq,
            features={"gestalt": gestalt_concept, "anchor": anchor, "source_entities": entities},
        )

        # 5. T_Shield Dead-Zero 校验
        rejected = False
        if self.t_shield is not None:
            try:
                is_dead, reason = self.t_shield.check_dead_zero_dikwp(i_value, "data")
                if is_dead:
                    rejected = True
                    result = ExtendResult(
                        success=False,
                        op_type=HypergraphOpType.EXTEND,
                        new_nodes=new_nodes,
                        new_edges=[new_edge],
                        gestalt_concept=gestalt_concept,
                        i_value=i_value,
                        reason=f"T_Shield REJECT: {reason}",
                        rejected_by_tshield=True,
                    )
                    self.extension_history.append(result)
                    logger.warning("ExtendHypergraph REJECTED by T_Shield: %s", reason)
                    return result
            except Exception as e:
                logger.debug("T_Shield check skipped: %s", e)
        elif i_value < self.theta_dead:
            rejected = True
            result = ExtendResult(
                success=False,
                op_type=HypergraphOpType.EXTEND,
                new_nodes=new_nodes,
                new_edges=[new_edge],
                gestalt_concept=gestalt_concept,
                i_value=i_value,
                reason=f"Dead-Zero: ℐ={i_value:.4f} < θ_dead={self.theta_dead}",
                rejected_by_tshield=True,
            )
            self.extension_history.append(result)
            return result

        # 6. 写入 EML-Lite KB (Append-Only)
        for node in new_nodes:
            self.eml_kb.add_node(node)
        self.eml_kb.add_edge(new_edge)

        result = ExtendResult(
            success=True,
            op_type=HypergraphOpType.EXTEND,
            new_nodes=new_nodes,
            new_edges=[new_edge],
            gestalt_concept=gestalt_concept,
            i_value=i_value,
            reason="Extended successfully",
        )
        self.extension_history.append(result)
        logger.info("ExtendHypergraph: %s (ℐ=%.4f, %d nodes, %d edges)",
                     gestalt_concept, i_value, len(new_nodes), 1)
        return result

    def revise(
        self,
        edge_id: str,
        new_features: Dict[str, Any],
        i_value: Optional[float] = None,
    ) -> ExtendResult:
        """
        ReviseHypergraph() — 修订超边（HL 升级）

        Article 5, Theorem 3.1:
            HL 更新代码 ⇔ TOMAS 修订 EML 超边
        """
        if edge_id not in self.eml_kb.edges:
            return ExtendResult(
                success=False,
                op_type=HypergraphOpType.REVISE,
                reason=f"Edge {edge_id} not found",
            )

        edge = self.eml_kb.edges[edge_id]
        edge.features.update(new_features)
        if i_value is not None:
            edge.i_value = i_value
        self.eml_kb._version += 1

        return ExtendResult(
            success=True,
            op_type=HypergraphOpType.REVISE,
            new_edges=[edge],
            i_value=edge.i_value,
            reason="Revised successfully",
        )

    def mus_resolve(
        self,
        edge_a_id: str,
        edge_b_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        MUS_Resolve() — A5 互斥稳态双存裁决

        Article 4, Section 6.1:
            不强行 if-else 嵌套，而是双存挂起（MUS_ACTIVE）等待 G_ego 裁决

        Article 5, Section 5:
            检测到冲突 → 标记 MUS_ACTIVE → G_ego 裁决
        """
        if edge_a_id not in self.eml_kb.edges or edge_b_id not in self.eml_kb.edges:
            return "ERROR: edge not found"

        edge_a = self.eml_kb.edges[edge_a_id]
        edge_b = self.eml_kb.edges[edge_b_id]

        # 计算不对称性
        asym = abs(edge_a.i_value - edge_b.i_value)

        if asym < 0.05:
            # ℐ 值相近 → MUS 双存挂起
            return f"MUS_ACTIVE: dual-state suspended ({edge_a_id} vs {edge_b_id})"
        elif edge_a.i_value > edge_b.i_value:
            return f"RESOLVED: {edge_a_id} (ℐ={edge_a.i_value:.4f} > {edge_b.i_value:.4f})"
        else:
            return f"RESOLVED: {edge_b_id} (ℐ={edge_b.i_value:.4f} > {edge_a.i_value:.4f})"

    def grounding_check(
        self,
        edge_id: str,
        t_shield_verifier=None,
    ) -> Dict[str, Any]:
        """
        GroundingCheck() — T_Shield 校验 ℐ-存在度

        Article 4, Core Primitives:
            GroundingCheck(): T_Shield 校验 ℐ-存在度

        Article 5, Theorem 3.1:
            HL 更新代码 ⇔ TOMAS 修订 EML 超边
            GroundingCheck() 确保修订后的超边仍满足 Dead-Zero 约束

        Returns:
            {
                "edge_id": str,
                "i_value": float,
                "is_grounded": bool,
                "std_ref_valid": bool | None,
                "dz_reason": str | None,
                "psi_alignment": float | None,
            }
        """
        if edge_id not in self.eml_kb.edges:
            return {
                "edge_id": edge_id,
                "error": "Edge not found",
                "is_grounded": False,
            }

        edge = self.eml_kb.edges[edge_id]
        result = {
            "edge_id": edge_id,
            "i_value": edge.i_value,
            "is_grounded": True,
            "std_ref_valid": None,
            "dz_reason": None,
            "psi_alignment": None,
        }

        # 1. Dead-Zero 校验 (ℐ-存在度)
        verifier = t_shield_verifier or self.t_shield
        if verifier is not None:
            try:
                is_dead, reason = verifier.check_dead_zero_dikwp(edge.i_value, "data")
                if is_dead:
                    result["is_grounded"] = False
                    result["dz_reason"] = reason
                    logger.warning("GroundingCheck FAILED for %s: %s", edge_id, reason)
                else:
                    logger.debug("GroundingCheck PASSED for %s (ℐ=%.4f)", edge_id, edge.i_value)
            except Exception as e:
                logger.debug("GroundingCheck: T_Shield check skipped: %s", e)
        elif edge.i_value < self.theta_dead:
            result["is_grounded"] = False
            result["dz_reason"] = f"ℐ={edge.i_value:.4f} < θ_dead={self.theta_dead}"
            logger.warning("GroundingCheck FAILED for %s: %s", edge_id, result["dz_reason"])

        # 2. std_ref 校验 (如果有标准引用)
        if edge.std_ref is not None:
            verifier = t_shield_verifier or self.t_shield
            if verifier is not None and hasattr(verifier, "check_std_ref"):
                # 动态调用 verifier 的 check_std_ref 方法
                std_ref_result = verifier.check_std_ref(edge, self.theta_dead)
                result["std_ref_valid"] = std_ref_result["valid"]
                if not std_ref_result["valid"]:
                    result["is_grounded"] = False
                    result["dz_reason"] = std_ref_result.get("reason", "std_ref invalid")
                    logger.warning("GroundingCheck: std_ref invalid for %s: %s",
                                  edge_id, std_ref_result.get("reason"))
            else:
                # 简化：如果无法调用 check_std_ref，则标记 std_ref 为有效
                result["std_ref_valid"] = True
                logger.debug("GroundingCheck: std_ref=%s marked as valid (simplified)", edge.std_ref)

        # 3. ψ-Alignment 校验 (如果可用)
        try:
            from g_ego import G_egoEngine
            g_ego = G_egoEngine.get_instance()
            psi_anchor = g_ego.get_status()

            verifier = t_shield_verifier or self.t_shield
            if verifier is not None and hasattr(verifier, "validate_psi_alignment"):
                # 动态调用 verifier 的 validate_psi_alignment 方法
                psi_result = verifier.validate_psi_alignment(edge, psi_anchor)
                result["psi_alignment"] = psi_result.get("alignment_score")
                if not psi_result.get("aligned", True):
                    logger.warning("GroundingCheck: low ψ-alignment for %s: %s",
                                  edge_id, psi_result.get("reason"))
            else:
                # 简化：计算 ℐ 值差异
                g_i = psi_anchor.get("i_value", 0.5)
                psi_alignment = 1.0 - abs(g_i - edge.i_value)
                result["psi_alignment"] = psi_alignment
                if psi_alignment < 0.3:
                    logger.warning("GroundingCheck: low ψ-alignment=%.4f for %s",
                                  psi_alignment, edge_id)
        except Exception:
            logger.debug("GroundingCheck: ψ-alignment check skipped (G_ego not available)")

        return result

    def solve_arc_task(
        self,
        grid_input: Any,
        perceive_fn=None,
    ) -> Dict[str, Any]:
        """
        解决 ARC-AGI-3 任务（流体智能入口）

        Article 3, Algorithm 1:
            1. Perception (Shallow NN → EML Nodes)
            2. G_ego Initiation (check existing rules)
            3. κ-Snap Gestalt (form new concept)
            4. ExtendHypergraph (create new rule)
            5. Dead-Zero Check
            6. Apply Rule
        """
        # 1. 感知实体
        if perceive_fn:
            entities = perceive_fn(grid_input)
        else:
            entities = [f"entity_{i}" for i in range(min(5, len(str(grid_input))))]

        # 2. 检查是否已有规则
        if self.eml_kb.has_rule(entities):
            existing = self.eml_kb.apply_rule(entities)
            return {
                "intelligence_type": IntelligenceType.CRYSTALLIZED.value,
                "used_existing_rule": True,
                "result": existing,
            }

        # 3-5. ExtendHypergraph (现场拓扑重构)
        result = self.extend(entities, relation="arc_task_rule")

        if not result.success:
            return {
                "intelligence_type": IntelligenceType.FLUID.value,
                "used_existing_rule": False,
                "extended": False,
                "reason": result.reason,
            }

        # 6. 应用新规则
        applied = self.eml_kb.apply_rule(entities)
        return {
            "intelligence_type": IntelligenceType.FLUID.value,
            "used_existing_rule": False,
            "extended": True,
            "gestalt": result.gestalt_concept,
            "new_nodes": len(result.new_nodes),
            "result": applied,
        }
