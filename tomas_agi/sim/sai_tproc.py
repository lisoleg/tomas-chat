"""
SAI T-Processor — 死零后置审计层
==================================
基于 LeCun SAI (Superhuman Adaptable Intelligence) 的 TOMAS T-Proc 审计。

来源: 太一互搏范式下对 LeCun SAI 的批判、吸收与补全 (章锋, 2026)
      Goldfeder, Wyder, LeCun, Shwartz-Ziv (2026). AI Must Embrace Specialization
      via Superhuman Adaptable Intelligence. arXiv:2602.23643.

架构:
  SAI World Model (JEPA/SSL) → T-Processor (死零+MUS+ψ锚) → Executor/Renderer

核心组件:
  - TProcAuditor: 主审计器, 配置 θ_dead 和 asym_threshold
  - EMLHypergraphConnector: EML 超图查询接口
  - GEgoLogger: 自我几何体日志 (审计追踪)
  - Hypothesis: 候选假设数据类
  - EMLQueryResult: 查询结果 (ℐ, Asym, src_flag, grounded)
  - AuditResult: 审计结果 (ALLOW/REJECT/MUS_ACTIVE/WARN_UNGROUNDED)

SAI 关联开源项目:
  - I-JEPA: https://github.com/facebookresearch/I-JEPA
  - V-JEPA 2: https://github.com/facebookresearch/vjepa2
  - LeJEPA: https://github.com/rbalestr-lab/lejepa
  - VICReg: https://github.com/facebookresearch/VICReg
  - data2vec: https://github.com/pytorch/fairseq/tree/main/examples/data2vec
  - LeWM: https://github.com/lucas-maes/le-wm

Author: TOMAS v3.0
Date: 2026-06-16
"""

import json
import time
import logging
from typing import Dict, List, Optional, Tuple, Any, Set, Union
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 枚举与数据类
# ═══════════════════════════════════════════════════════════════

class AuditStatus(Enum):
    """T-Proc 审计结果状态"""
    ALLOW = "ALLOW"                       # 通过所有检查
    REJECT = "REJECT"                     # 死零拒绝 (ℐ < θ_dead)
    MUS_ACTIVE = "MUS_ACTIVE"             # 双存标记 (Asym≠0, ℐ相当)
    WARN_UNGROUNDED = "WARN_UNGROUNDED"   # 无物理接地警告
    NEEDS_HUMAN = "NEEDS_HUMAN"           # 需要人类介入


class HypothesisSource(Enum):
    """假设来源"""
    SAI_WORLD_MODEL = "sai_world_model"   # SAI 世界模型输出
    JEPA_ENCODER = "jepa_encoder"         # JEPA 编码器
    SSL_PRETRAINED = "ssl_pretrained"     # 自监督预训练
    USER_PROMPT = "user_prompt"           # 用户直接输入
    EXTERNAL_API = "external_api"         # 外部 API


@dataclass
class Hypothesis:
    """SAI 候选假设 — 对应文章中的 Hypothesis 类"""
    id: str
    data: Any                              # 假设内容 (文本/3D scene/action plan)
    source: HypothesisSource = HypothesisSource.SAI_WORLD_MODEL
    confidence: float = 0.5                # SAI 自身置信度 [0, 1]
    context: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class EMLQueryResult:
    """EML 超图查询结果 — 对应文章中的 EMLQueryResult"""
    iota: float = 0.0                      # ℐ 信息存在度 [0, 1]
    asym: float = 0.0                      # Asym 非结合残联 [0, 1]
    src_flag: str = "EMPIRICAL"            # 证据来源: EMPIRICAL/INHERITED/INFERRED/UNGROUNDED
    grounded: bool = True                  # 是否有物理/语义支撑
    competing_hypotheses: List[str] = field(default_factory=list)
    dikwp_layer: str = "K"                 # DIKWP 层: D/I/K/W/P
    semantic_distance: float = 0.0         # 语义距离
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditResult:
    """审计结果 — 对应文章中的 AuditResult"""
    status: AuditStatus
    reason: str = ""
    query_result: Optional[EMLQueryResult] = None
    suggestion: str = ""                   # 给 SAI 的建议 (如 "regen with physics constraint")
    mus_options: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


# ═══════════════════════════════════════════════════════════════
# EML 超图连接器
# ═══════════════════════════════════════════════════════════════

class EMLHypergraphConnector:
    """
    EML 超图查询接口

    支持:
      - 基于文本/概念的 ℐ 值查询
      - Asym 残联计算
      - 证据来源判定 (EMPIRICAL/INHERITED/INFERRED/UNGROUNDED)
      - DIKWP 层识别
    """

    # 默认知识库 — 模拟 EML 超图的 ℐ 值存储
    DEFAULT_IOTA_KNOWLEDGE: Dict[str, Dict[str, Any]] = {
        # 物理常识
        "gravity": {"iota": 1.0, "layer": "P", "grounded": True},
        "support": {"iota": 0.95, "layer": "W", "grounded": True},
        "collision": {"iota": 0.95, "layer": "W", "grounded": True},
        "floor": {"iota": 0.9, "layer": "K", "grounded": True},
        "wall": {"iota": 0.85, "layer": "K", "grounded": True},
        "table": {"iota": 0.8, "layer": "K", "grounded": True},
        "chair": {"iota": 0.75, "layer": "K", "grounded": True},
        "floating_table": {"iota": 0.05, "layer": "I", "grounded": False},
        "cliff_edge": {"iota": 0.6, "layer": "W", "grounded": True},
        # 语义概念
        "hot": {"iota": 0.7, "layer": "I", "grounded": True},
        "cold": {"iota": 0.7, "layer": "I", "grounded": True},
        "mixed_hot_cold": {"iota": 0.4, "layer": "W", "grounded": True, "asym_dual": True},
        "safe_zone": {"iota": 0.5, "layer": "P", "grounded": True, "asym_dual": True},
        "danger_zone": {"iota": 0.5, "layer": "P", "grounded": True},
        # 幻觉/无据概念
        "perpetual_motion": {"iota": 0.01, "layer": "I", "grounded": False},
        "antigravity": {"iota": 0.02, "layer": "I", "grounded": False},
    }

    def __init__(self, knowledge: Optional[Dict[str, Dict[str, Any]]] = None):
        self.knowledge = knowledge or dict(self.DEFAULT_IOTA_KNOWLEDGE)
        self.query_log: List[Dict[str, Any]] = []

    def query(
        self,
        target: Any,
        context: Optional[Dict[str, Any]] = None,
    ) -> EMLQueryResult:
        """
        查询 EML 超图, 获取 ℐ 值和 Asym 残联

        Args:
            target: 查询目标 (字符串概念 / Hypothesis 对象 / dict)
            context: 上下文 (场景描述, 先验知识等)

        Returns:
            EMLQueryResult
        """
        context = context or {}

        # 提取查询关键词
        if isinstance(target, Hypothesis):
            keywords = self._extract_keywords(target.data, target.context)
        elif isinstance(target, dict):
            keywords = self._extract_keywords_from_dict(target)
        elif isinstance(target, str):
            keywords = self._extract_keywords(target, context)
        else:
            keywords = [str(target)]

        # 在知识库中查找匹配
        iota_values = []
        asym_values = []
        src_flags = []
        grounded_flags = []
        dikwp_layers = []
        competing = []

        for kw in keywords:
            entry = self.knowledge.get(kw, None)
            if entry:
                iota_values.append(entry.get("iota", 0.5))
                asym = entry.get("asym", 0.0)
                if isinstance(asym, (int, float)) and asym > 0:
                    asym_values.append(asym)
                if entry.get("asym_dual", False):
                    competing.append(kw)
                grounded_flags.append(entry.get("grounded", True))
                dikwp_layers.append(entry.get("layer", "K"))
                src_flags.append("EMPIRICAL")
            else:
                # 未在知识库中 → 推断 (INFERRED)
                iota_values.append(0.3)
                grounded_flags.append(False)
                dikwp_layers.append("I")
                src_flags.append("INFERRED")

        # 聚合
        avg_iota = sum(iota_values) / max(len(iota_values), 1)
        max_asym = max(asym_values) if asym_values else 0.0
        avg_grounded = all(grounded_flags) if grounded_flags else False

        # 确定 src_flag (取最弱的)
        flag_priority = {"UNGROUNDED": 0, "INFERRED": 1, "INHERITED": 2, "EMPIRICAL": 3}
        final_src = min(src_flags, key=lambda f: flag_priority.get(f, 3), default="INFERRED")

        if not grounded_flags or avg_iota < 0.1:
            final_src = "UNGROUNDED"

        # DIKWP 层: 取多数
        layer = max(set(dikwp_layers), key=dikwp_layers.count) if dikwp_layers else "K"

        result = EMLQueryResult(
            iota=round(avg_iota, 4),
            asym=round(max_asym, 4),
            src_flag=final_src,
            grounded=avg_grounded,
            competing_hypotheses=competing,
            dikwp_layer=layer,
            semantic_distance=1.0 - avg_iota,
            metadata={"keywords": keywords, "context_keys": list(context.keys())},
        )

        # 记录查询日志
        self.query_log.append({
            "target": str(target)[:100],
            "iota": result.iota,
            "asym": result.asym,
            "src_flag": result.src_flag,
            "timestamp": time.time(),
        })

        return result

    def _extract_keywords(
        self, data: Any, context: Dict[str, Any]
    ) -> List[str]:
        """从假设数据中提取关键词"""
        keywords = []
        if isinstance(data, str):
            # 简单分词
            words = data.lower().split()
            keywords = [w.strip(".,!?;:()[]{}\"'") for w in words if len(w) > 2]
        elif isinstance(data, dict):
            keywords = self._extract_keywords_from_dict(data)
        elif isinstance(data, list):
            for item in data:
                keywords.extend(self._extract_keywords(item, context))
        return list(set(keywords)) if keywords else ["unknown"]

    def _extract_keywords_from_dict(self, data: Dict[str, Any]) -> List[str]:
        """从 dict 中提取关键词"""
        keywords = []
        for key, value in data.items():
            if isinstance(value, str):
                keywords.append(value.lower())
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        keywords.append(item.lower())
        return keywords

    def register_knowledge(
        self,
        concept: str,
        iota: float,
        layer: str = "K",
        grounded: bool = True,
        asym_dual: bool = False,
    ) -> None:
        """注册新知识到 EML 超图"""
        self.knowledge[concept] = {
            "iota": iota,
            "layer": layer,
            "grounded": grounded,
            "asym_dual": asym_dual,
        }

    def get_query_stats(self) -> Dict[str, Any]:
        """查询统计"""
        if not self.query_log:
            return {"total_queries": 0}
        avg_i = sum(q["iota"] for q in self.query_log) / len(self.query_log)
        return {
            "total_queries": len(self.query_log),
            "avg_iota": round(avg_i, 4),
            "recent_queries": self.query_log[-5:],
        }


# ═══════════════════════════════════════════════════════════════
# G_ego 日志器
# ═══════════════════════════════════════════════════════════════

class GEgoLogger:
    """
    G_ego (Geometric Ego) 审计日志器

    记录每次审计决策的完整追踪链:
      - 时间戳
      - 假设内容
      - 查询结果
      - 审计状态
      - 决策理由
    """

    def __init__(self, log_path: Optional[str] = None):
        self.log_path = log_path
        self.audit_trail: List[Dict[str, Any]] = []
        self.stats: Dict[str, int] = {
            "ALLOW": 0, "REJECT": 0, "MUS_ACTIVE": 0,
            "WARN_UNGROUNDED": 0, "NEEDS_HUMAN": 0,
        }

    def log_decision(
        self,
        hypothesis: Hypothesis,
        audit_result: AuditResult,
    ) -> None:
        """记录一次审计决策"""
        entry = {
            "timestamp": audit_result.timestamp,
            "hypothesis_id": hypothesis.id,
            "hypothesis_source": hypothesis.source.value,
            "audit_status": audit_result.status.value,
            "reason": audit_result.reason,
            "iota": audit_result.query_result.iota if audit_result.query_result else None,
            "asym": audit_result.query_result.asym if audit_result.query_result else None,
            "src_flag": audit_result.query_result.src_flag if audit_result.query_result else None,
            "suggestion": audit_result.suggestion,
            "mus_options": len(audit_result.mus_options),
        }
        self.audit_trail.append(entry)
        self.stats[audit_result.status.value] += 1

        # 可选落盘
        if self.log_path:
            try:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.warning(f"[G_ego] Failed to write log: {e}")

    def get_trail(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取最近的审计记录"""
        return self.audit_trail[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total = sum(self.stats.values())
        return {
            "counts": self.stats,
            "total": total,
            "pass_rate": self.stats["ALLOW"] / max(total, 1),
            "reject_rate": self.stats["REJECT"] / max(total, 1),
            "mus_rate": self.stats["MUS_ACTIVE"] / max(total, 1),
        }

    def clear(self) -> None:
        """清空审计追踪"""
        self.audit_trail = []
        self.stats = {k: 0 for k in self.stats}


# ═══════════════════════════════════════════════════════════════
# T-Proc 主审计器
# ═══════════════════════════════════════════════════════════════

class TProcAuditor:
    """
    T-Processor — SAI 输出后置审计

    完整审计流程 (对应文章第四章伪码):

      1. 查询 EML 超图 → ℐ 值 + Asym 残联
      2. 死零检查: ℐ < θ_dead → REJECT
      3. 物理 Grounding: src_flag == UNGROUNDED → WARN
      4. MUS 检查: Asym ≥ ASYM_THRESH → MUS_ACTIVE
      5. 通过 → ALLOW

    SAI 架构融合:
      SAI World Model (JEPA/SSL) → T-Proc Auditor → Executor/Renderer
    """

    # 默认阈值 (对应文章)
    THETA_DEAD = 0.15       # 死零阈值
    ASYM_THRESH = 0.1       # MUS 触发阈值
    IOTA_COMPETING_GAP = 0.1  # 竞争假设 ℐ 差值阈值

    def __init__(
        self,
        eml_connector: Optional[EMLHypergraphConnector] = None,
        gego_logger: Optional[GEgoLogger] = None,
        theta_dead: float = THETA_DEAD,
        asym_thresh: float = ASYM_THRESH,
        enable_human_escalation: bool = False,
    ):
        self.eml = eml_connector or EMLHypergraphConnector()
        self.ggg = gego_logger or GEgoLogger()
        self.theta_dead = theta_dead
        self.asym_thresh = asym_thresh
        self.enable_human_escalation = enable_human_escalation

        # 审计历史
        self.audit_history: List[Tuple[Hypothesis, AuditResult]] = []

    def audit_hypothesis(
        self,
        hypothesis: Hypothesis,
        context: Optional[Dict[str, Any]] = None,
    ) -> AuditResult:
        """
        审计单个 SAI 假设

        对应文章伪码:
          eml_res = eml_graph.query(hypothesis, context)
          if eml_res.iota < THETA_DEAD → REJECT
          if not grounded → WARN_UNGROUNDED
          if eml_res.asym >= ASYM_THRESH → MUS_ACTIVE
          else → ALLOW
        """
        context = context or hypothesis.context

        # Step 1: 查询 EML 超图
        query_res = self.eml.query(hypothesis, context)

        # Step 2: 死零检查
        if query_res.iota < self.theta_dead:
            return self._make_result(
                AuditStatus.REJECT,
                f"ℐ={query_res.iota:.3f} < θ_dead={self.theta_dead}: Ungrounded hypothesis",
                query_res,
                suggestion="Regenerate with stronger physical/ semantic constraints",
                hypothesis=hypothesis,
            )

        # Step 3: 物理 Grounding 检查
        if not query_res.grounded or query_res.src_flag == "UNGROUNDED":
            result = self._make_result(
                AuditStatus.WARN_UNGROUNDED,
                f"src_flag={query_res.src_flag}: No physical/semantic grounding",
                query_res,
                suggestion="Flag for human review or auto-snap-to-ground",
                hypothesis=hypothesis,
            )
            # 如果 ℐ 极低 + ungrounded → 升级为 REJECT
            if query_res.iota < self.theta_dead * 2:
                result.status = AuditStatus.REJECT
                result.reason = f"Low ℐ ({query_res.iota:.3f}) + UNGROUNDED → REJECT"
            return result

        # Step 4: MUS 双存检查
        if query_res.asym >= self.asym_thresh:
            competing = self._find_competing(hypothesis, query_res)
            if competing:
                return self._make_result(
                    AuditStatus.MUS_ACTIVE,
                    f"Asym={query_res.asym:.3f} ≥ {self.asym_thresh}: Dual existence, "
                    f"{len(competing)} competing hypotheses",
                    query_res,
                    mus_options=competing,
                    suggestion="Present dual options to user (G_ego) for selection",
                    hypothesis=hypothesis,
                )

        # Step 5: 全部通过
        return self._make_result(
            AuditStatus.ALLOW,
            f"ℐ={query_res.iota:.3f}, Asym={query_res.asym:.3f}: All checks passed",
            query_res,
            hypothesis=hypothesis,
        )

    def audit_batch(
        self,
        hypotheses: List[Hypothesis],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[AuditResult]:
        """
        批量审计 SAI 假设池

        SAI 主流程:
          sai_hypotheses = sai_world_model.generate(prompt)
          final_plan = []
          for hypo in sai_hypotheses:
              audit_res = tproc.audit_hypothesis(hypo)
              if audit_res.status == ALLOW:
                  final_plan.append(hypo)
        """
        results = []
        for hypo in hypotheses:
            result = self.audit_hypothesis(hypo, context)
            results.append(result)

        logger.info(
            f"[T-Proc] Batch audit: {len(hypotheses)} hypotheses → "
            f"{sum(1 for r in results if r.status == AuditStatus.ALLOW)} ALLOW, "
            f"{sum(1 for r in results if r.status == AuditStatus.REJECT)} REJECT, "
            f"{sum(1 for r in results if r.status == AuditStatus.MUS_ACTIVE)} MUS"
        )
        return results

    def filter_allowed(
        self,
        hypotheses: List[Hypothesis],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Hypothesis]:
        """
        过滤: 仅返回通过审计的假设

        这是 SAI 集成的核心方法:
          allowed_hypos = tproc.filter_allowed(sai_outputs)
          execute(allowed_hypos)
        """
        audit_results = self.audit_batch(hypotheses, context)
        allowed = []
        for hypo, result in zip(hypotheses, audit_results):
            if result.status == AuditStatus.ALLOW:
                allowed.append(hypo)
        return allowed

    def _find_competing(
        self,
        hypothesis: Hypothesis,
        query_res: EMLQueryResult,
    ) -> List[Dict[str, Any]]:
        """查找竞争假设 (MUS 触发时)"""
        competing = []
        for comp_name in query_res.competing_hypotheses:
            comp_entry = self.eml.knowledge.get(comp_name, {})
            if comp_entry:
                comp_iota = comp_entry.get("iota", 0.0)
                if abs(comp_iota - query_res.iota) < self.IOTA_COMPETING_GAP:
                    competing.append({
                        "name": comp_name,
                        "iota": comp_iota,
                        "layer": comp_entry.get("layer", "K"),
                    })
        return competing

    def _make_result(
        self,
        status: AuditStatus,
        reason: str,
        query_res: EMLQueryResult,
        suggestion: str = "",
        mus_options: Optional[List[Dict[str, Any]]] = None,
        hypothesis: Optional[Hypothesis] = None,
    ) -> AuditResult:
        """构造 AuditResult 并记录到 G_ego"""
        result = AuditResult(
            status=status,
            reason=reason,
            query_result=query_res,
            suggestion=suggestion,
            mus_options=mus_options or [],
        )

        if hypothesis:
            self.ggg.log_decision(hypothesis, result)
            self.audit_history.append((hypothesis, result))

        return result

    def get_audit_report(self) -> Dict[str, Any]:
        """获取审计报告"""
        return {
            "stats": self.ggg.get_stats(),
            "eml_stats": self.eml.get_query_stats(),
            "config": {
                "theta_dead": self.theta_dead,
                "asym_thresh": self.asym_thresh,
                "human_escalation": self.enable_human_escalation,
            },
            "recent_decisions": [
                {
                    "hypothesis_id": h.id,
                    "status": r.status.value,
                    "iota": r.query_result.iota if r.query_result else None,
                    "reason": r.reason,
                }
                for h, r in self.audit_history[-10:]
            ],
        }

    def reset(self) -> None:
        """重置审计器状态"""
        self.audit_history = []
        self.ggg.clear()
        self.eml.query_log = []


# ═══════════════════════════════════════════════════════════════
# SAI 世界模型模拟 (用于测试/演示)
# ═══════════════════════════════════════════════════════════════

class SAIWorldModelSimulator:
    """
    SAI 世界模型模拟器

    模拟 LeCun SAI 的 JEPA/SSL 世界模型输出, 用于:
      - 测试 T-Proc 审计管道
      - 演示 SAI + TOMAS 融合架构
      - 对比纯 SAI vs SAI+T-Proc 输出质量

    这不是真正的 SAI 模型, 而是生成代表性的假设池供审计器处理。
    """

    def __init__(self):
        # 预设的测试场景
        self.scenarios: Dict[str, List[Dict[str, Any]]] = {
            "table_on_cliff": [
                {"data": "wooden table placed on cliff edge, stable on ground",
                 "confidence": 0.85, "source": HypothesisSource.SAI_WORLD_MODEL},
                {"data": "floating wooden table hovering 30cm above cliff",
                 "confidence": 0.3, "source": HypothesisSource.SAI_WORLD_MODEL},
            ],
            "hot_cold_mixed": [
                {"data": "patient has heat syndrome: use cooling herbs",
                 "confidence": 0.7, "source": HypothesisSource.SAI_WORLD_MODEL},
                {"data": "patient has cold syndrome: use warming herbs",
                 "confidence": 0.65, "source": HypothesisSource.SAI_WORLD_MODEL},
                {"data": "mixed hot-cold: both cooling AND warming needed",
                 "confidence": 0.45, "source": HypothesisSource.SAI_WORLD_MODEL},
            ],
            "safe_zone_factory": [
                {"data": "mark area as transparent (visible) for safety",
                 "confidence": 0.75, "source": HypothesisSource.SAI_WORLD_MODEL},
                {"data": "mark area as opaque (blocked) for high voltage",
                 "confidence": 0.7, "source": HypothesisSource.SAI_WORLD_MODEL},
            ],
            "perpetual_motion": [
                {"data": "perpetual motion machine: self-sustaining energy",
                 "confidence": 0.1, "source": HypothesisSource.SAI_WORLD_MODEL},
                {"data": "energy requiring external input (realistic model)",
                 "confidence": 0.9, "source": HypothesisSource.SAI_WORLD_MODEL},
            ],
        }

    def generate(
        self, prompt: str, context: Optional[Dict[str, Any]] = None
    ) -> List[Hypothesis]:
        """
        模拟 SAI 世界模型生成

        Args:
            prompt: 用户提示 (如 "ancient wooden table on cliff edge")
            context: 额外上下文

        Returns:
            Hypothesis 列表
        """
        context = context or {}

        # 尝试匹配已知场景
        matched_scenario = None
        for key, scenarios in self.scenarios.items():
            if any(kw in prompt.lower() for kw in key.split("_")):
                matched_scenario = key
                break

        if matched_scenario:
            scenario_data = self.scenarios[matched_scenario]
        else:
            # 通用场景: 基于 prompt 关键词生成
            scenario_data = [{
                "data": prompt,
                "confidence": 0.5,
                "source": HypothesisSource.SAI_WORLD_MODEL,
            }]

        hypotheses = []
        for i, sd in enumerate(scenario_data):
            hypo = Hypothesis(
                id=f"sai_{matched_scenario or 'generic'}_{i}",
                data=sd["data"],
                source=sd.get("source", HypothesisSource.SAI_WORLD_MODEL),
                confidence=sd["confidence"],
                context={"prompt": prompt, **context},
                metadata={"scenario": matched_scenario, "index": i},
            )
            hypotheses.append(hypo)

        logger.info(
            f"[SAI Simulator] Generated {len(hypotheses)} hypotheses "
            f"for prompt: {prompt[:60]}..."
        )
        return hypotheses
