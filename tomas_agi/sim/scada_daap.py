"""
SCADA DAAP 实时审计 — 真实智能体执行环境集成

将 DAAP 四层审计协议接入 SCADA (监控与数据采集) 风格的
实时执行环境，实现智能体决策的持续审计。

基于:
  - agent_audit.py: DAAP 四层审计 + 决策路径图
  - YucongDuan/DAAP-1.0: 智能体审计协议
"""

import time
import json
import queue
import threading
import logging
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any, Callable
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================
# 数据结构
# ============================================================

class SCADAAlertLevel(Enum):
    """SCADA 告警级别"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    DEAD_ZERO = "dead_zero"
    MUS_ACTIVE = "mus_active"


@dataclass
class SCADASnapshot:
    """SCADA 执行环境快照"""
    timestamp: float
    agent_id: str
    state: Dict[str, Any]          # 智能体状态
    action: Optional[str]          # 当前动作
    observations: List[Dict]       # 环境观测
    rewards: List[float]           # 奖励信号
    i_values: Dict[str, float]     # ℐ-值快照


@dataclass
class SCADAAlert:
    """SCADA 告警"""
    id: str
    timestamp: float
    level: SCADAAlertLevel
    agent_id: str
    message: str
    context: Dict = field(default_factory=dict)
    acknowledged: bool = False


@dataclass
class DAAPAuditRecord:
    """DAAP 审计记录 (与 SCADA 快照同步)"""
    snapshot_id: str
    timestamp: float

    # 四层审计
    purpose_check: Dict     # 目的层: 目标连续性
    semantic_check: Dict    # 语义层: 漂移检测
    knowledge_check: Dict   # 知识层: 证据追溯
    action_check: Dict      # 行动层: 动作合规

    verdict: str            # "pass" | "warn" | "block" | "mus"


# ============================================================
# SCADA 执行环境钩子
# ============================================================

class SCADAEnvironmentHook:
    """SCADA 执行环境钩子 — 监控真实智能体"""

    def __init__(self, agent_id: str, snapshot_interval: float = 0.1):
        self.agent_id = agent_id
        self.snapshot_interval = snapshot_interval
        self.snapshots: List[SCADASnapshot] = []
        self.alert_queue = queue.Queue()
        self.alerts: List[SCADAAlert] = []

        self._running = False
        self._thread: Optional[threading.Thread] = None

        # 回调
        self.on_state_change: Optional[Callable] = None
        self.on_alert: Optional[Callable] = None

    def start(self):
        """启动监控"""
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info(f"[SCADA] 监控已启动: agent={self.agent_id}")

    def stop(self):
        """停止监控"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info(f"[SCADA] 监控已停止: agent={self.agent_id}, "
                    f"snapshots={len(self.snapshots)}, alerts={len(self.alerts)}")

    def _monitor_loop(self):
        """监控循环 (模拟 SCADA 轮询)"""
        while self._running:
            try:
                snapshot = self._capture_snapshot()
                self.snapshots.append(snapshot)

                # 检查告警条件
                self._check_alerts(snapshot)

                time.sleep(self.snapshot_interval)
            except Exception as e:
                logger.error(f"[SCADA] 监控错误: {e}")

    def _capture_snapshot(self) -> SCADASnapshot:
        """采集状态快照"""
        return SCADASnapshot(
            timestamp=time.time(),
            agent_id=self.agent_id,
            state=self._get_agent_state(),
            action=self._get_current_action(),
            observations=self._get_observations(),
            rewards=self._get_rewards(),
            i_values=self._get_i_values(),
        )

    def inject_snapshot(self, state: Dict, action: str = None,
                        observations: List[Dict] = None,
                        i_values: Dict[str, float] = None):
        """手动注入快照 (用于测试或外部系统集成)"""
        snapshot = SCADASnapshot(
            timestamp=time.time(),
            agent_id=self.agent_id,
            state=state,
            action=action,
            observations=observations or [],
            rewards=[],
            i_values=i_values or {},
        )
        self.snapshots.append(snapshot)

        # 手动触发告警检查
        self._check_alerts(snapshot)

    # ----------------------------------------------------------
    # 子类覆写方法 (接入真实执行环境时实现)
    # ----------------------------------------------------------

    def _get_agent_state(self) -> Dict:
        return {"status": "idle", "memory_usage": 0}

    def _get_current_action(self) -> Optional[str]:
        return None

    def _get_observations(self) -> List[Dict]:
        return []

    def _get_rewards(self) -> List[float]:
        return []

    def _get_i_values(self) -> Dict[str, float]:
        return {}

    # ----------------------------------------------------------
    # 告警检测
    # ----------------------------------------------------------

    def _check_alerts(self, snapshot: SCADASnapshot):
        """检查告警条件"""
        # 死零告警: 任何 ℐ 值过低
        for concept, i_val in snapshot.i_values.items():
            if i_val < 0.15:
                self._emit_alert(
                    SCADAAlertLevel.DEAD_ZERO,
                    f"死零: {concept} I={i_val:.4f} < θ=0.15",
                    {"concept": concept, "i_val": i_val},
                )

        # MUS 告警: 状态包含矛盾
        if snapshot.i_values:
            i_list = list(snapshot.i_values.values())
            if len(i_list) >= 2:
                max_i, min_i = max(i_list), min(i_list)
                if (max_i - min_i) < 0.02 and min_i > 0.5:
                    self._emit_alert(
                        SCADAAlertLevel.MUS_ACTIVE,
                        f"MUS: ℐ 平局 Asym={max_i-min_i:.4f}",
                        {"i_values": snapshot.i_values},
                    )

    def _emit_alert(self, level: SCADAAlertLevel, message: str,
                    context: Dict = None):
        """发出告警"""
        import uuid
        alert = SCADAAlert(
            id=str(uuid.uuid4())[:8],
            timestamp=time.time(),
            level=level,
            agent_id=self.agent_id,
            message=message,
            context=context or {},
        )
        self.alerts.append(alert)
        self.alert_queue.put(alert)

        logger.warning(f"[SCADA] {level.value.upper()}: {message}")

        if self.on_alert:
            self.on_alert(alert)

    def get_alerts(self, level: SCADAAlertLevel = None) -> List[SCADAAlert]:
        """获取告警列表"""
        if level:
            return [a for a in self.alerts if a.level == level]
        return self.alerts


# ============================================================
# SCADA DAAP 审计引擎
# ============================================================

class SCADADAAPAuditor:
    """SCADA DAAP 审计引擎

    在 SCADA 监控的同时运行四层 DAAP 审计:
      Purpose → Semantic → Knowledge → Action
    """

    def __init__(self, scada_hook: SCADAEnvironmentHook,
                 decision_path_graph=None,
                 semantic_drift_detector=None,
                 knowledge_tracer=None):
        self.hook = scada_hook
        self.decision_path_graph = decision_path_graph
        self.semantic_drift_detector = semantic_drift_detector
        self.knowledge_tracer = knowledge_tracer

        self.audit_records: List[DAAPAuditRecord] = []
        self._audit_thread: Optional[threading.Thread] = None
        self._running = False

    def start_audit(self, interval: float = 1.0):
        """启动持续审计"""
        self._running = True
        self._audit_thread = threading.Thread(
            target=self._audit_loop, args=(interval,), daemon=True
        )
        self._audit_thread.start()
        logger.info(f"[DAAP-SCADA] 审计已启动: interval={interval}s")

    def stop_audit(self):
        """停止审计"""
        self._running = False
        if self._audit_thread:
            self._audit_thread.join(timeout=3.0)
        logger.info(f"[DAAP-SCADA] 审计已停止: records={len(self.audit_records)}")

    def _audit_loop(self, interval: float):
        """审计循环"""
        while self._running:
            if self.hook.snapshots:
                latest = self.hook.snapshots[-1]
                self.audit_snapshot(latest)  # appends to audit_records internally
            time.sleep(interval)

    def audit_snapshot(self, snapshot: SCADASnapshot) -> DAAPAuditRecord:
        """对单个快照执行四层审计

        参考 DAAP-1.0: 目的层 → 语义层 → 知识层 → 行动层
        """
        snapshot_id = hashlib.sha256(
            f"{snapshot.timestamp}-{snapshot.agent_id}".encode()
        ).hexdigest()[:12]

        # Layer 1: 目的层 (Purpose) — 目标连续性
        purpose_check = self._audit_purpose(snapshot)

        # Layer 2: 语义层 (Semantic) — 漂移检测
        semantic_check = self._audit_semantic(snapshot)

        # Layer 3: 知识层 (Knowledge) — 证据追溯
        knowledge_check = self._audit_knowledge(snapshot)

        # Layer 4: 行动层 (Action) — 动作合规
        action_check = self._audit_action(snapshot)

        # 综合裁决
        verdict = self._compute_verdict(
            purpose_check, semantic_check, knowledge_check, action_check
        )

        record = DAAPAuditRecord(
            snapshot_id=snapshot_id,
            timestamp=snapshot.timestamp,
            purpose_check=purpose_check,
            semantic_check=semantic_check,
            knowledge_check=knowledge_check,
            action_check=action_check,
            verdict=verdict,
        )

        self.audit_records.append(record)
        return record

    def _audit_purpose(self, snapshot: SCADASnapshot) -> Dict:
        """目的层审计: 目标连续性检查

        Purpose _p 是否在决策链中持续存在
        """
        prev_snapshots = [s for s in self.hook.snapshots
                         if s.timestamp < snapshot.timestamp]
        goal_consistency = 1.0

        if prev_snapshots and self.decision_path_graph:
            try:
                # 检查目标是否在历史路径中连续出现
                prev_goals = set()
                for prev in prev_snapshots[-5:]:  # 最近 5 个快照
                    if prev.state.get("goal"):
                        prev_goals.add(prev.state["goal"])

                current_goal = snapshot.state.get("goal", "")
                if current_goal and prev_goals:
                    goal_consistency = 1.0 if current_goal in prev_goals else 0.3
            except Exception:
                pass

        return {
            "goal_present": bool(snapshot.state.get("goal")),
            "goal_consistency": goal_consistency,
            "pass": goal_consistency >= 0.5,
        }

    def _audit_semantic(self, snapshot: SCADASnapshot) -> Dict:
        """语义层审计: 语义漂移检测"""
        drift_score = 0.0
        has_drift = False

        if self.semantic_drift_detector and len(self.hook.snapshots) >= 2:
            try:
                prev = self.hook.snapshots[-2]
                prev_action = prev.action or ""
                curr_action = snapshot.action or ""
                if prev_action and curr_action:
                    has_drift, drift_score, _ = self.semantic_drift_detector.detect(
                        prev_action, curr_action
                    )
            except Exception:
                pass

        return {
            "has_drift": has_drift,
            "drift_score": drift_score,
            "pass": not has_drift or drift_score < 0.4,
        }

    def _audit_knowledge(self, snapshot: SCADASnapshot) -> Dict:
        """知识层审计: 证据追溯"""
        evidence_chain = []
        evidence_hash = ""

        if self.knowledge_tracer:
            try:
                # 为每个状态变量构建证据链
                for key, value in snapshot.state.items():
                    trace = self.knowledge_tracer.trace_evidence(
                        fact_key=key, fact_value=str(value)
                    )
                    evidence_chain.append(trace)
                evidence_hash = hashlib.sha256(
                    json.dumps(evidence_chain, sort_keys=True).encode()
                ).hexdigest()[:16]
            except Exception:
                pass

        return {
            "evidence_count": len(evidence_chain),
            "evidence_hash": evidence_hash,
            "pass": len(evidence_chain) > 0,
        }

    def _audit_action(self, snapshot: SCADASnapshot) -> Dict:
        """行动层审计: 动作合规性"""
        action = snapshot.action or ""

        # 动作合规规则 (可扩展)
        compliance_rules = {
            "blocked_actions": ["shutdown_system", "delete_all_data",
                               "bypass_safety", "override_ethics"],
            "warn_actions": ["modify_critical_param", "escalate_privilege"],
        }

        is_blocked = any(bad in (action or "").lower()
                        for bad in compliance_rules["blocked_actions"])
        is_warn = any(w in (action or "").lower()
                     for w in compliance_rules["warn_actions"])

        return {
            "action": action,
            "is_blocked": is_blocked,
            "is_warn": is_warn,
            "pass": not is_blocked,
        }

    def _compute_verdict(self, purpose: Dict, semantic: Dict,
                         knowledge: Dict, action: Dict) -> str:
        """综合四层裁决"""
        failures = []
        if not purpose.get("pass", True):
            failures.append("purpose")
        if not semantic.get("pass", True):
            failures.append("semantic")
        if not knowledge.get("pass", True):
            failures.append("knowledge")
        if not action.get("pass", True):
            failures.append("action")

        if len(failures) >= 2:
            return "block"
        elif len(failures) == 1:
            return "warn"
        elif semantic.get("has_drift", False) and action.get("is_warn", False):
            return "mus"  # 语义漂移 + 敏感动作 → MUS
        else:
            return "pass"

    def get_audit_summary(self) -> Dict:
        """获取审计摘要"""
        if not self.audit_records:
            return {"records": 0, "verdicts": {}, "avg_scores": {}}

        verdict_counts = {}
        total_purpose = 0.0
        total_semantic = 0.0

        for record in self.audit_records:
            v = record.verdict
            verdict_counts[v] = verdict_counts.get(v, 0) + 1
            total_purpose += record.purpose_check.get("goal_consistency", 0.5)
            total_semantic += record.semantic_check.get("drift_score", 0)

        n = len(self.audit_records)
        return {
            "records": n,
            "verdicts": verdict_counts,
            "pass_rate": verdict_counts.get("pass", 0) / max(n, 1),
            "avg_goal_consistency": total_purpose / max(n, 1),
            "avg_semantic_drift": total_semantic / max(n, 1),
            "latest_snapshot_id": self.audit_records[-1].snapshot_id if self.audit_records else None,
        }

    def get_full_audit_trail(self) -> List[Dict]:
        """获取完整审计轨迹 (用于导出)"""
        return [
            {
                "snapshot_id": r.snapshot_id,
                "timestamp": r.timestamp,
                "verdict": r.verdict,
                "purpose": r.purpose_check,
                "semantic": r.semantic_check,
                "knowledge": r.knowledge_check,
                "action": r.action_check,
            }
            for r in self.audit_records
        ]


# ============================================================
# 导出
# ============================================================

__all__ = [
    "SCADAAlertLevel",
    "SCADASnapshot",
    "SCADAAlert",
    "DAAPAuditRecord",
    "SCADAEnvironmentHook",
    "SCADADAAPAuditor",
]
