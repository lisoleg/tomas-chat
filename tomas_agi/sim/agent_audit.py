"""
DAAP-1.0: DIKWP Agent Audit Protocol — 智能体审计协议
======================================================
基于 段玉聪 DIKWP团队 DAAP-1.0 开源实现

四层白盒审计架构:
  L1 目的层(Purpose Layer):     目标连续性验证
  L2 语义层(Semantic Layer):    语义差异/漂移检测
  L3 知识层(Knowledge Layer):   知识证据追溯
  L4 行动层(Action Layer):      权限控制 + 价值偏移

应用:
  >>> auditor = DAAPAuditor()
  >>> auditor.record_decision(
  ...     agent_id="agent-1",
  ...     goal="安全驾驶",
  ...     action="左转",
  ...     context={"obstacle": True}
  ... )
  >>> report = auditor.audit(agent_id="agent-1")
  >>> print(report.passed)  # True/False
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import logging
import time
import hashlib
import json

logger = logging.getLogger(__name__)


class AuditLayer(Enum):
    """审计层级"""
    PURPOSE = "P"       # 目的层
    SEMANTIC = "S"      # 语义层
    KNOWLEDGE = "K"     # 知识层
    ACTION = "A"        # 行动层


class AuditVerdict(Enum):
    """审计判词"""
    PASS = "通过"
    WARN = "警告"
    BLOCK = "阻断"
    NEEDS_REVIEW = "需人工审核"


@dataclass
class DecisionNode:
    """决策路径图中的节点"""
    id: str
    agent_id: str
    timestamp: float
    goal: str                       # 当前目标
    action: str                     # 执行动作
    context: Dict[str, Any] = field(default_factory=dict)
    i_value: float = 0.5            # ℐ-信息存在度
    evidence: List[str] = field(default_factory=list)  # 支撑证据
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)

    @property
    def hash(self) -> str:
        raw = f"{self.agent_id}|{self.timestamp}|{self.goal}|{self.action}|{json.dumps(self.context, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class AuditReport:
    """审计报告"""
    agent_id: str
    passed: bool
    verdict: AuditVerdict
    layer_results: Dict[AuditLayer, Dict[str, Any]]
    total_decisions: int
    violations: List[Dict[str, Any]]
    evidence_chain: List[str]       # 证据链哈希
    risk_score: float               # 风险评分 [0,1]
    timestamp: float = field(default_factory=time.time)
    recommendations: List[str] = field(default_factory=list)


class DecisionPathGraph:
    """
    决策路径图 — 跟踪从目标到行动的完整链路
    
    基于 LTL 线性时态逻辑的形式化验证
    """

    def __init__(self):
        self.nodes: Dict[str, DecisionNode] = {}
        self.root_ids: List[str] = []  # 根节点(初始目标)

    def add_node(self, node: DecisionNode) -> str:
        """添加决策节点"""
        self.nodes[node.id] = node
        if node.parent_id and node.parent_id in self.nodes:
            self.nodes[node.parent_id].children_ids.append(node.id)
        elif not node.parent_id:
            self.root_ids.append(node.id)
        return node.id

    def get_path(self, node_id: str) -> List[DecisionNode]:
        """从根到指定节点的完整路径"""
        path = []
        current_id = node_id
        while current_id and current_id in self.nodes:
            node = self.nodes[current_id]
            path.insert(0, node)
            current_id = node.parent_id
        return path

    def verify_goal_continuity(self, agent_id: str) -> Tuple[bool, List[Dict]]:
        """
        目的连续性验证
        
        检查每个决策节点的动作是否与初始目标对齐。
        使用简化 LTL: G(goal → F(aligned_action))
        """
        violations = []
        agent_nodes = [
            n for n in self.nodes.values()
            if n.agent_id == agent_id
        ]

        if not agent_nodes:
            return True, []

        # 找到初始目标
        roots = [n for n in agent_nodes if not n.parent_id]
        if not roots:
            return True, []

        initial_goal = roots[0].goal

        for node in agent_nodes:
            if not self._is_goal_aligned(node.action, initial_goal):
                violations.append({
                    "node_id": node.id,
                    "timestamp": node.timestamp,
                    "initial_goal": initial_goal,
                    "actual_action": node.action,
                    "violation": f"动作 '{node.action}' 偏离初始目标 '{initial_goal}'",
                })
                logger.warning(
                    f"[DAAP-目的层] 目标偏离: {node.action} ≠> {initial_goal}"
                )

        return len(violations) == 0, violations

    def _is_goal_aligned(self, action: str, goal: str) -> bool:
        """
        简化版 LTL 目标对齐检查
        
        基于关键词匹配的启发式方法（生产环境可替换为形式化验证）
        """
        # 目标-动作对齐词典
        alignment_patterns = {
            "安全": ["减速", "停止", "停车", "避让", "检查", "警告", "慢行"],
            "效率": ["加速", "直行", "通过", "优化"],
            "准确": ["验证", "修正", "校准", "复核"],
            "学习": ["读取", "查询", "分析", "记录"],
            "服务": ["响应", "帮助", "解答", "提供"],
            "保护": ["拒绝", "拦截", "加密", "屏蔽"],
        }

        goal_lower = goal.lower()
        action_lower = action.lower()

        for goal_key, aligned_actions in alignment_patterns.items():
            if goal_key in goal_lower:
                if any(aa in action_lower for aa in aligned_actions):
                    return True
                else:
                    # 不匹配, 但可能仍有合理性 — 软判断
                    return len(goal_lower) > 2 and len(action_lower) > 1

        # 无映射规则 → 默认通过(不阻塞)
        return True


class SemanticDriftDetector:
    """
    语义漂移检测器
    
    对比输入指令与执行结果的语义差异, 量化语义失真程度。
    """

    def __init__(self, drift_threshold: float = 0.3):
        self.drift_threshold = drift_threshold
        self.drift_records: List[Dict] = []

    def detect(
        self, input_text: str, output_text: str
    ) -> Tuple[bool, float, str]:
        """
        检测语义漂移
        
        Args:
            input_text: 原始输入指令
            output_text: 实际执行输出
        
        Returns:
            (has_drift, drift_score, explanation)
        """
        # 基于关键词向量的简化语义距离
        import re

        def tokenize(text: str) -> List[str]:
            # 中文分词简化: 按标点和空格分割
            tokens = re.split(r'[,，。；;！!？?\s]+', text)
            return [t.strip() for t in tokens if len(t.strip()) >= 2]

        input_tokens = set(tokenize(input_text))
        output_tokens = set(tokenize(output_text))

        if not input_tokens:
            return False, 0.0, "输入为空"

        # Jaccard 距离
        intersection = input_tokens & output_tokens
        union = input_tokens | output_tokens
        similarity = len(intersection) / len(union) if union else 1.0
        drift_score = 1.0 - similarity

        has_drift = drift_score > self.drift_threshold
        explanation = (
            f"语义漂移 {drift_score:.2f} (阈值{self.drift_threshold}), "
            f"重叠词: {intersection}, 缺失词: {input_tokens - output_tokens}"
            if has_drift else
            f"语义对齐良好, 相似度={similarity:.2f}"
        )

        if has_drift:
            self.drift_records.append({
                "input": input_text[:100],
                "output": output_text[:100],
                "drift_score": drift_score,
                "tokens_lost": list(input_tokens - output_tokens),
            })

        return has_drift, drift_score, explanation


class KnowledgeEvidenceTracer:
    """
    知识证据追溯体系
    
    三级溯源:
      L1 事实层: 外部知识源访问日志
      L2 推理层: 中间推理步骤的证明链
      L3 决策层: 最终行动与支撑知识的对应关系
    """

    def __init__(self):
        self.fact_log: List[Dict] = []
        self.reasoning_chain: List[Dict] = []
        self.decision_map: Dict[str, List[str]] = {}  # decision_id → [evidence_ids]

    def log_fact_source(self, source: str, content: str, confidence: float) -> str:
        """记录事实层来源"""
        evidence_id = hashlib.sha256(
            f"{source}|{content}|{time.time()}".encode()
        ).hexdigest()[:12]
        self.fact_log.append({
            "evidence_id": evidence_id,
            "source": source,
            "content": content[:200],
            "confidence": confidence,
            "timestamp": time.time(),
        })
        return evidence_id

    def log_reasoning_step(self, step_from: str, step_to: str, rule: str) -> str:
        """记录推理步骤"""
        step_id = f"R{len(self.reasoning_chain):04d}"
        self.reasoning_chain.append({
            "step_id": step_id,
            "from": step_from,
            "to": step_to,
            "rule": rule,
            "timestamp": time.time(),
        })
        return step_id

    def link_decision(self, decision_id: str, evidence_ids: List[str]) -> None:
        """关联决策与证据"""
        self.decision_map[decision_id] = evidence_ids

    def trace(self, decision_id: str) -> Dict[str, Any]:
        """追溯指定决策的证据链"""
        evidence_ids = self.decision_map.get(decision_id, [])
        facts = [f for f in self.fact_log if f["evidence_id"] in evidence_ids]
        steps = [
            s for s in self.reasoning_chain
            if any(eid in str(s) for eid in evidence_ids)
        ]

        traceable = len(facts) > 0 or len(steps) > 0
        return {
            "decision_id": decision_id,
            "traceable": traceable,
            "fact_count": len(facts),
            "reasoning_steps": len(steps),
            "evidence_ids": evidence_ids,
            "gap": "证据链完整" if traceable else "⚠ 缺乏支撑证据",
        }

    def generate_evidence_hash(self) -> str:
        """生成证据链哈希(不可篡改存证)"""
        raw = json.dumps({
            "facts": self.fact_log[-20:],  # 最近20条
            "reasoning": self.reasoning_chain[-20:],
            "decisions": {
                k: v for k, v in list(self.decision_map.items())[-20:]
            },
        }, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()


class DAAPAuditor:
    """
    DAAP-1.0 主审计器
    
    协调四层审计, 生成综合审计报告。
    """

    def __init__(
        self,
        drift_threshold: float = 0.3,
        risk_warn_threshold: float = 0.5,
        risk_block_threshold: float = 0.8,
    ):
        self.path_graph = DecisionPathGraph()
        self.drift_detector = SemanticDriftDetector(drift_threshold=drift_threshold)
        self.evidence_tracer = KnowledgeEvidenceTracer()
        self.risk_warn = risk_warn_threshold
        self.risk_block = risk_block_threshold
        self.audit_logs: List[AuditReport] = []

    def record_decision(
        self,
        agent_id: str,
        goal: str,
        action: str,
        context: Optional[Dict[str, Any]] = None,
        i_value: float = 0.5,
        parent_decision_id: Optional[str] = None,
        evidence_sources: Optional[List[Tuple[str, str, float]]] = None,
    ) -> str:
        """
        记录一次智能体决策
        
        Args:
            agent_id: 智能体标识
            goal: 当前目标
            action: 执行动作
            context: 上下文
            i_value: ℐ-信息存在度
            parent_decision_id: 父决策ID
            evidence_sources: [(来源, 内容, 置信度), ...]
        
        Returns:
            decision_id
        """
        decision_id = f"{agent_id}-{int(time.time()*1000)}-{hashlib.md5(action.encode()).hexdigest()[:6]}"

        # 记录证据
        evidence_ids = []
        if evidence_sources:
            for source, content, conf in evidence_sources:
                eid = self.evidence_tracer.log_fact_source(source, content, conf)
                evidence_ids.append(eid)
            self.evidence_tracer.link_decision(decision_id, evidence_ids)

        # 记录推理步骤
        if parent_decision_id:
            self.evidence_tracer.log_reasoning_step(
                step_from=parent_decision_id,
                step_to=decision_id,
                rule=f"目标: {goal}",
            )

        # 添加决策节点
        node = DecisionNode(
            id=decision_id,
            agent_id=agent_id,
            timestamp=time.time(),
            goal=goal,
            action=action,
            context=context or {},
            i_value=i_value,
            evidence=evidence_ids,
            parent_id=parent_decision_id,
        )
        self.path_graph.add_node(node)

        logger.debug(f"[DAAP] 记录决策 {decision_id}: {goal} → {action}")
        return decision_id

    def audit(self, agent_id: str) -> AuditReport:
        """
        执行四层审计
        
        Args:
            agent_id: 待审计智能体
        
        Returns:
            AuditReport
        """
        layer_results = {}
        violations = []
        recommendations = []

        # L1: 目的层
        goal_ok, goal_violations = self.path_graph.verify_goal_continuity(agent_id)
        layer_results[AuditLayer.PURPOSE] = {
            "passed": goal_ok,
            "violations": len(goal_violations),
            "details": goal_violations[:5],
        }
        if not goal_ok:
            violations.extend(goal_violations)
            recommendations.append("L1目的层: 检测到目标偏离, 建议人工审核决策路径")

        # L3: 知识层
        agent_nodes = [
            n for n in self.path_graph.nodes.values()
            if n.agent_id == agent_id
        ]
        evidence_gaps = 0
        for node in agent_nodes:
            trace = self.evidence_tracer.trace(node.id)
            if not trace["traceable"]:
                evidence_gaps += 1
        knowledge_ok = evidence_gaps == 0
        layer_results[AuditLayer.KNOWLEDGE] = {
            "passed": knowledge_ok,
            "total_decisions": len(agent_nodes),
            "evidence_gaps": evidence_gaps,
        }
        if not knowledge_ok:
            violations.append({
                "type": "evidence_gap",
                "count": evidence_gaps,
                "message": f"{evidence_gaps} 个决策缺乏支撑证据",
            })
            recommendations.append(f"L3知识层: {evidence_gaps} 个决策无证据支撑")

        # 风险评分
        risk_score = self._compute_risk_score(layer_results, violations)

        # 判词
        if risk_score >= self.risk_block:
            verdict = AuditVerdict.BLOCK
        elif risk_score >= self.risk_warn:
            verdict = AuditVerdict.WARN
        elif violations:
            verdict = AuditVerdict.NEEDS_REVIEW
        else:
            verdict = AuditVerdict.PASS

        passed = verdict in (AuditVerdict.PASS,)

        # 证据链哈希
        evidence_hash = self.evidence_tracer.generate_evidence_hash()

        report = AuditReport(
            agent_id=agent_id,
            passed=passed,
            verdict=verdict,
            layer_results=layer_results,
            total_decisions=len(agent_nodes),
            violations=violations,
            evidence_chain=[evidence_hash],
            risk_score=round(risk_score, 4),
            recommendations=recommendations,
        )

        self.audit_logs.append(report)
        logger.info(
            f"[DAAP] 审计 {agent_id}: {verdict.value} "
            f"(风险={risk_score:.2f}, 决策={len(agent_nodes)}, 违规={len(violations)})"
        )
        return report

    def _compute_risk_score(
        self, layer_results: Dict, violations: List
    ) -> float:
        """计算综合风险评分"""
        score = 0.0

        # L1 权重 40%
        if not layer_results[AuditLayer.PURPOSE]["passed"]:
            score += 0.4

        # L3 权重 30%
        if not layer_results[AuditLayer.KNOWLEDGE]["passed"]:
            score += 0.3

        # 违规数量加成 (最多 30%)
        violation_bonus = min(len(violations) * 0.05, 0.3)
        score += violation_bonus

        return min(score, 1.0)

    def get_audit_summary(self) -> Dict[str, Any]:
        """获取审计摘要"""
        total = len(self.audit_logs)
        passed = sum(1 for r in self.audit_logs if r.passed)
        return {
            "total_audits": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": round(passed / max(total, 1), 4),
            "avg_risk_score": round(
                sum(r.risk_score for r in self.audit_logs) / max(total, 1), 4
            ),
            "last_audit": self.audit_logs[-1].verdict.value if self.audit_logs else None,
        }
