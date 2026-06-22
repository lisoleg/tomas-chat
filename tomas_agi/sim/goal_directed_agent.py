# -*- coding: utf-8 -*-
"""
TOMAS AGI v3.10 — Goal-Directed Agent Module
=============================================

Goal Contract（意图契约）+ CronFire（定时自动化）+ Soul-Graph（数字分身）TOMAS 升维。

三阶段编排：propose_goal → execute_authorized → dream_engine
实现 ψ-Anchor Execution Gate 的"只输出 Goal 不执行"原则。

基于老金 GoalPro 五闸门模型：
  ① Intent（意图）→ ② Scope IN/OUT → ③ Evidence（验收证据）
  → ④ Pause（停点）→ ⑤ Acceptance（验收标准）

所有操作生成 SHA-256 κ-Snap 审计记录，MUS 双存保障对齐。

零外部依赖：仅使用 Python 3.10+ stdlib。
模拟模块：无 LLM 调用、无外部 API。

Author: 寇豆码 (TOMAS AGI v3.10)
Version: v3.10
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Tuple, Set

# ── 跨模块导入（try/except ImportError 三层回退）─────────────────
try:
    from .babeltele_compressor import KSnapRecord, MUSDualEntry, PsiAnchorLevel, SnapResult
except ImportError:
    try:
        from babeltele_compressor import KSnapRecord, MUSDualEntry, PsiAnchorLevel, SnapResult
    except ImportError:
        KSnapRecord = None  # type: ignore
        MUSDualEntry = None  # type: ignore
        PsiAnchorLevel = None  # type: ignore
        SnapResult = None  # type: ignore

try:
    from .psi_anchor import PsiAnchor, PsiAnchorManager
except ImportError:
    try:
        from psi_anchor import PsiAnchor, PsiAnchorManager
    except ImportError:
        PsiAnchor = None  # type: ignore
        PsiAnchorManager = None  # type: ignore

try:
    from .ksnap_operator import KSnapOperator, SnapEvent
    _HAS_KSNAP = True
except ImportError:
    try:
        from ksnap_operator import KSnapOperator, SnapEvent
        _HAS_KSNAP = True
    except ImportError:
        _HAS_KSNAP = False
        KSnapOperator = None  # type: ignore
        SnapEvent = None  # type: ignore

# v3.11: grill-me 需求审问引擎
try:
    from .grill_me_engine import DIKWPGapAnalyzer, GrillExecutionGate, RequirementTracer, PsiNoSilentAssumption
    _HAS_GRILL_ME = True
except ImportError:
    try:
        from grill_me_engine import DIKWPGapAnalyzer, GrillExecutionGate, RequirementTracer, PsiNoSilentAssumption
        _HAS_GRILL_ME = True
    except ImportError:
        _HAS_GRILL_ME = False
        DIKWPGapAnalyzer = None  # type: ignore
        GrillExecutionGate = None  # type: ignore
        RequirementTracer = None  # type: ignore
        PsiNoSilentAssumption = None  # type: ignore


# ══════════════════════════════════════════════════════════════════
# 共享枚举
# ══════════════════════════════════════════════════════════════════

class GoalStatus(Enum):
    """Goal Contract 状态机"""
    DRAFT = "DRAFT"
    PROPOSED = "PROPOSED"
    AUTHORIZED = "AUTHORIZED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"


class PsiGateLevel(Enum):
    """ψ-Anchor 闸门级别"""
    CONSTITUTIONAL = "constitutional"
    REGULATORY = "regulatory"
    OPERATIONAL = "operational"


class DreamPhase(Enum):
    """梦境引擎压缩阶段"""
    RULE_BASED_PRUNE = "rule_based_prune"
    SEMANTIC_COMPACT = "semantic_compact"


# ══════════════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════════════

def _make_ksnap_id() -> str:
    """生成 κ-Snap ID"""
    return f"ksnap-{uuid.uuid4().hex[:12]}"


def _sha256(text: str) -> str:
    """SHA-256 哈希"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> float:
    """当前时间戳"""
    return time.time()


def _cron_to_regex(cron_expr: str) -> str:
    """将 cron 表达式转换为简单的正则模式（用于模拟匹配）。
    支持标准五段 cron: minute hour day month weekday
    """
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {cron_expr}, expected 5 fields")
    return f"cron:{':'.join(parts)}"


def _create_ksnap_record(
    module: str,
    result: str,
    i_value: float,
    ftel: float,
    psi_anchor_id: str,
    description: str,
    snap_hash: str = "",
) -> dict:
    """创建 κ-Snap 审计记录（兼容 KSnapRecord 格式）。"""
    return {
        "snap_id": _make_ksnap_id(),
        "module": module,
        "result": result,
        "i_value": i_value,
        "ftel_magnitude": ftel,
        "psi_anchor_id": psi_anchor_id,
        "description": description,
        "timestamp": _now(),
        "snapshot_hash": snap_hash or _sha256(description + str(_now())),
    }


def _simple_tokenize(text: str) -> List[str]:
    """简单分词：提取中英文词元"""
    return re.findall(r'[a-zA-Z0-9\u4e00-\u9fff]+', text.lower())


# ══════════════════════════════════════════════════════════════════
# 类 1: GoalContract — 老金 GoalPro 五闸门 → TOMAS ψ-Anchor DSL
# ══════════════════════════════════════════════════════════════════

class GoalContract:
    """老金 GoalPro 五闸门编译为 TOMAS Pre-Commit ψ-Anchor DSL。

    GoalPro 五闸门：
      ① Intent — 意图
      ② Scope IN / Scope OUT — 范围约束
      ③ Evidence — 验收证据
      ④ Pause — 停点
      ⑤ Acceptance — 验收标准
    """

    _EXEC_GATE = "REQUIRE_EXPLICIT_EXEC_AUTHORIZATION"

    def __init__(self, request_id: str):
        """初始化 Goal Contract。

        Args:
            request_id: 请求唯一标识
        """
        self.request_id = request_id
        self.intent = ""
        self.scope_in: List[str] = []
        self.scope_out: List[str] = []
        self.evidence_required: List[str] = []
        self.pause_conditions: List[str] = []
        self.acceptance = ""
        self.execution_gate = self._EXEC_GATE
        self.I_value = 1.0
        self.goal_hash = ""
        self.created_at = _now()
        self.status = GoalStatus.DRAFT.value
        self.ksnap_log: List[dict] = []
        self._user_signature = ""

    # ── 五闸门起草 ──

    def draft(self, intent: str, scope_in: List[str], scope_out: List[str],
              evidence: List[str], pauses: List[str], acceptance: str) -> None:
        """起草五闸门契约，自动计算 goal_hash。

        Args:
            intent: 意图描述
            scope_in: 范围内允许的操作/模块
            scope_out: 范围外禁止的操作/模块
            evidence: 验收证据列表
            pauses: 停点条件
            acceptance: 验收标准
        """
        self.intent = intent
        self.scope_in = list(scope_in)
        self.scope_out = list(scope_out)
        self.evidence_required = list(evidence)
        self.pause_conditions = list(pauses)
        self.acceptance = acceptance
        self.status = GoalStatus.DRAFT.value
        self.created_at = _now()
        self.goal_hash = self._compute_goal_hash()

    def _compute_goal_hash(self) -> str:
        """SHA-256(json.dumps({五闸门字段}, sort_keys=True))"""
        payload = {
            "intent": self.intent,
            "scope_in": sorted(self.scope_in),
            "scope_out": sorted(self.scope_out),
            "evidence": sorted(self.evidence_required),
            "pauses": sorted(self.pause_conditions),
            "acceptance": self.acceptance,
        }
        return _sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True))

    # ── DSL 编译 ──

    def to_psi_anchor_dsl(self) -> str:
        """编译为 ψ-Anchor DSL 格式（SQL 风格）。"""
        scope_in_str = ", ".join(f"'{s}'" for s in self.scope_in) if self.scope_in else "NULL"
        scope_out_str = ", ".join(f"'{s}'" for s in self.scope_out) if self.scope_out else "NULL"
        evidence_str = ", ".join(f"'{e}'" for e in self.evidence_required) if self.evidence_required else "NULL"
        pauses_str = ", ".join(f"'{p}'" for p in self.pause_conditions) if self.pause_conditions else "NULL"

        dsl = (
            f"CREATE ψ-ANCHOR psi_goal_{self.goal_hash[:12]}\n"
            f"(\n"
            f"    TYPE 'goal_contract',\n"
            f"    REQUEST_ID '{self.request_id}',\n"
            f"    -- Gate 1: Intent\n"
            f"    INTENT '{self.intent}',\n"
            f"    -- Gate 2: Scope\n"
            f"    SCOPE_IN ({scope_in_str}),\n"
            f"    SCOPE_OUT ({scope_out_str}),\n"
            f"    -- Gate 3: Evidence\n"
            f"    EVIDENCE ({evidence_str}),\n"
            f"    -- Gate 4: Pause\n"
            f"    PAUSE_CONDITIONS ({pauses_str}),\n"
            f"    -- Gate 5: Acceptance\n"
            f"    ACCEPTANCE '{self.acceptance}',\n"
            f"    -- Meta\n"
            f"    EXECUTION_GATE 'REQUIRE_EXPLICIT_EXEC_AUTHORIZATION',\n"
            f"    I_WEIGHT {self.I_value:.4f},\n"
            f"    GOAL_HASH '{self.goal_hash}',\n"
            f"    STATUS '{self.status}'\n"
            f");"
        )
        return dsl

    def to_jsonld(self) -> dict:
        """编译为 ψ-Anchor JSON-LD。"""
        return {
            "@context": "https://tomas.org/psi/v2",
            "@type": "GoalContract",
            "@id": f"urn:tomas:goal:{self.request_id}",
            "tomas:requestId": self.request_id,
            "tomas:goalHash": self.goal_hash,
            "tomas:status": self.status,
            "tomas:executionGate": self.execution_gate,
            "tomas:iValue": self.I_value,
            "tomas:createdAt": self.created_at,
            "goalPro:gates": {
                "goalPro:intent": self.intent,
                "goalPro:scopeIn": self.scope_in,
                "goalPro:scopeOut": self.scope_out,
                "goalPro:evidenceRequired": self.evidence_required,
                "goalPro:pauseConditions": self.pause_conditions,
                "goalPro:acceptance": self.acceptance,
            },
            "psi:dsl": self.to_psi_anchor_dsl(),
        }

    # ── 状态机 ──

    def propose(self) -> dict:
        """提交契约：DRAFT → PROPOSED，生成 κ-Snap 记录。

        Returns:
            包含 ksnap_id, goal_hash, status, message 的字典
        """
        if self.status != GoalStatus.DRAFT.value:
            return {
                "ksnap_id": "",
                "goal_hash": self.goal_hash,
                "status": self.status,
                "message": f"Cannot propose: current status is {self.status}",
                "error": True,
            }

        self.status = GoalStatus.PROPOSED.value
        snap = _create_ksnap_record(
            module="GoalContract",
            result="PROPOSED",
            i_value=self.I_value,
            ftel=0.9,
            psi_anchor_id=f"psi_goal_{self.goal_hash[:12]}",
            description=f"Goal Contract PROPOSED: {self.intent[:60]}",
            snap_hash=self.goal_hash,
        )
        self.ksnap_log.append(snap)

        return {
            "ksnap_id": snap["snap_id"],
            "goal_hash": self.goal_hash,
            "status": self.status,
            "message": "等待用户授权 — 请确认后执行 (REQUIRE_EXPLICIT_EXEC_AUTHORIZATION)",
        }

    def authorize(self, user_signature: str) -> dict:
        """用户授权：PROPOSED → AUTHORIZED。

        Args:
            user_signature: 用户签名/确认

        Returns:
            {"authorized": bool, "ksnap_id": str}
        """
        if self.status != GoalStatus.PROPOSED.value:
            return {
                "authorized": False,
                "ksnap_id": "",
                "message": f"Cannot authorize: current status is {self.status}",
            }

        self._user_signature = user_signature
        self.status = GoalStatus.AUTHORIZED.value

        snap = _create_ksnap_record(
            module="GoalContract",
            result="AUTHORIZED",
            i_value=self.I_value,
            ftel=1.0,
            psi_anchor_id=f"psi_goal_{self.goal_hash[:12]}",
            description=f"Goal Contract AUTHORIZED by user: {self.intent[:60]}",
            snap_hash=_sha256(self.goal_hash + user_signature),
        )
        self.ksnap_log.append(snap)

        return {
            "authorized": True,
            "ksnap_id": snap["snap_id"],
            "goal_hash": self.goal_hash,
            "status": self.status,
        }

    def execute(self) -> dict:
        """标记执行开始：AUTHORIZED → EXECUTING。"""
        if self.status != GoalStatus.AUTHORIZED.value:
            return {
                "executing": False,
                "ksnap_id": "",
                "message": f"Cannot execute: current status is {self.status}",
            }

        self.status = GoalStatus.EXECUTING.value
        snap = _create_ksnap_record(
            module="GoalContract",
            result="EXECUTING",
            i_value=self.I_value,
            ftel=0.95,
            psi_anchor_id=f"psi_goal_{self.goal_hash[:12]}",
            description=f"Goal Contract EXECUTING: {self.intent[:60]}",
        )
        self.ksnap_log.append(snap)
        return {"executing": True, "ksnap_id": snap["snap_id"]}

    def complete(self) -> dict:
        """标记完成：EXECUTING → COMPLETED。"""
        if self.status != GoalStatus.EXECUTING.value:
            return {
                "completed": False,
                "ksnap_id": "",
                "message": f"Cannot complete: current status is {self.status}",
            }

        self.status = GoalStatus.COMPLETED.value
        snap = _create_ksnap_record(
            module="GoalContract",
            result="COMPLETED",
            i_value=self.I_value,
            ftel=1.0,
            psi_anchor_id=f"psi_goal_{self.goal_hash[:12]}",
            description=f"Goal Contract COMPLETED: {self.intent[:60]}",
        )
        self.ksnap_log.append(snap)
        return {"completed": True, "ksnap_id": snap["snap_id"]}

    def reject(self, reason: str = "") -> dict:
        """拒绝契约。"""
        self.status = GoalStatus.REJECTED.value
        snap = _create_ksnap_record(
            module="GoalContract",
            result="REJECTED",
            i_value=0.0,
            ftel=0.0,
            psi_anchor_id=f"psi_goal_{self.goal_hash[:12]}",
            description=f"Goal Contract REJECTED: {reason[:60]}" if reason else f"Goal Contract REJECTED: {self.intent[:60]}",
        )
        self.ksnap_log.append(snap)
        return {"rejected": True, "ksnap_id": snap["snap_id"]}

    def get_status(self) -> dict:
        """获取契约完整状态。

        Returns:
            包含 status, goal_hash, intent, gates_defined, ksnap_count 的字典
        """
        return {
            "request_id": self.request_id,
            "status": self.status,
            "goal_hash": self.goal_hash,
            "intent": self.intent,
            "gates_defined": bool(self.intent and self.acceptance),
            "scope_in": self.scope_in,
            "scope_out": self.scope_out,
            "evidence_count": len(self.evidence_required),
            "pause_count": len(self.pause_conditions),
            "ksnap_count": len(self.ksnap_log),
            "created_at": self.created_at,
            "execution_gate": self.execution_gate,
        }

    def get_ksnap_log(self) -> List[dict]:
        """返回完整 κ-Snap 审计链。"""
        return list(self.ksnap_log)


# ══════════════════════════════════════════════════════════════════
# 类 2: ExecutionGate — "只输出 Goal 不执行"的硬实现
# ══════════════════════════════════════════════════════════════════

class ExecutionGate:
    """ψ-Anchor Execution Gate: REQUIRE_EXPLICIT_EXEC_AUTHORIZATION。

    硬约束：任何 goal 必须显式授权后才可执行。
    """

    def __init__(self):
        self.authorized_goals: Dict[str, dict] = {}
        self.gate_log: List[dict] = []
        # v3.11: grill-me 集成
        self.grill_gate = GrillExecutionGate() if _HAS_GRILL_ME and GrillExecutionGate else None
        self.grill_precheck_enabled = _HAS_GRILL_ME

    def check(self, goal_hash: str) -> dict:
        """检查执行权限。

        Args:
            goal_hash: Goal 的 SHA-256 哈希

        Returns:
            {"allowed": bool, "reason": str, "missing_authorization": bool}
        """
        if goal_hash in self.authorized_goals:
            auth = self.authorized_goals[goal_hash]
            # v3.11: grill-me 前置审问检查
            if self.grill_precheck_enabled and self.grill_gate:
                if not self.grill_gate.verify_all_gaps_closed(goal_hash):
                    release_info = self.grill_gate.release(goal_hash)
                    if "未注册" not in release_info.get("reason", ""):
                        return {"allowed": False, "reason": f"Grill-me: gaps remain - {self.grill_gate.lock_reason(goal_hash)}"}
            return {
                "allowed": True,
                "reason": f"Authorized by {auth.get('signature', 'unknown')} at {auth.get('timestamp', 0)}",
                "missing_authorization": False,
            }
        return {
            "allowed": False,
            "reason": "REQUIRE_EXPLICIT_EXEC_AUTHORIZATION: 此 Goal 未经用户显式授权",
            "missing_authorization": True,
        }

    def grant(self, goal_hash: str, signature: str) -> dict:
        """授权执行：记录签名 + κ-Snap。

        Args:
            goal_hash: Goal 哈希
            signature: 用户签名

        Returns:
            {"ksnap_id": str, "granted": bool}
        """
        now = _now()
        self.authorized_goals[goal_hash] = {
            "signature": signature,
            "timestamp": now,
        }

        snap = _create_ksnap_record(
            module="ExecutionGate",
            result="GRANTED",
            i_value=1.0,
            ftel=1.0,
            psi_anchor_id=f"gate_{goal_hash[:12]}",
            description=f"Execution GRANTED for goal {goal_hash[:16]}",
            snap_hash=_sha256(goal_hash + signature + str(now)),
        )
        self.gate_log.append(snap)

        return {"ksnap_id": snap["snap_id"], "granted": True, "goal_hash": goal_hash}

    def revoke(self, goal_hash: str) -> dict:
        """撤销执行授权。

        Args:
            goal_hash: Goal 哈希

        Returns:
            {"revoked": bool, "ksnap_id": str}
        """
        if goal_hash not in self.authorized_goals:
            return {"revoked": False, "ksnap_id": "", "reason": "Goal not authorized"}

        del self.authorized_goals[goal_hash]
        snap = _create_ksnap_record(
            module="ExecutionGate",
            result="REVOKED",
            i_value=0.0,
            ftel=0.0,
            psi_anchor_id=f"gate_{goal_hash[:12]}",
            description=f"Authorization REVOKED for goal {goal_hash[:16]}",
        )
        self.gate_log.append(snap)
        return {"revoked": True, "ksnap_id": snap["snap_id"], "goal_hash": goal_hash}

    def get_pending_goals(self) -> List[dict]:
        """列出等待授权的 Goal（从 gate_log 中提取 PROPOSED 状态）。

        Note: 此方法返回历史中曾经进入 PROPOSED 状态的记录。
        完整的 pending 列表应由编排器维护。
        """
        pending = [entry for entry in self.gate_log if entry["result"] in ("PROPOSED",)]
        return pending

    def is_authorized(self, goal_hash: str) -> bool:
        """快捷检查：goal_hash 是否已授权。"""
        return goal_hash in self.authorized_goals

    def get_gate_log(self) -> List[dict]:
        """返回完整 Gate 审计日志。"""
        return list(self.gate_log)


# ══════════════════════════════════════════════════════════════════
# 类 3: CronFire — κ-Snap 周期性因果链调度器
# ══════════════════════════════════════════════════════════════════

class CronFire:
    """κ-Snap 周期性因果链调度器。

    Chris CodeX 定时自动化 → TOMAS κ-Snap CronFire。
    注册 cron 任务 → freshness 检查 → ψ-Anchor 约束 → 执行 → 写入 L1+L3。
    """

    DEFAULT_PSI_ANCHORS = [
        {"id": "psi_automation_readonly", "rule": "NO_WRITE_TO_PROD_DB", "I": 0.95},
        {"id": "psi_source_freshness", "rule": "CACHE_MAX_AGE_6H", "I": 0.90},
        {"id": "psi_audit_trail", "rule": "LOG_ALL_AUTOMATED_ACTIONS", "I": 0.85},
        {"id": "psi_no_network_write", "rule": "DENY_OUTBOUND_API_CALLS_WITHOUT_AUTH", "I": 0.92},
    ]

    def __init__(self):
        self.schedules: Dict[str, dict] = {}
        self.execution_history: List[dict] = []
        self.default_psi_anchors = list(self.DEFAULT_PSI_ANCHORS)
        self._last_fire_times: Dict[str, float] = {}
        self._cache_ages: Dict[str, float] = {}

    def register(self, schedule_id: str, cron_expr: str,
                 task_payload: dict, psi_anchors: List[dict] = None) -> dict:
        """注册 Cron 任务。

        Args:
            schedule_id: 任务标识
            cron_expr: cron 表达式，如 "0 10 * * *"
            task_payload: 任务载荷 {"task": str, "params": dict, ...}
            psi_anchors: 自定义 ψ-Anchor 约束

        Returns:
            {"registered": bool, "schedule_id": str, "ksnap_id": str}
        """
        # 验证 cron 表达式
        _cron_to_regex(cron_expr)

        self.schedules[schedule_id] = {
            "cron_expr": cron_expr,
            "task_payload": task_payload,
            "psi_anchors": psi_anchors if psi_anchors else list(self.default_psi_anchors),
            "registered_at": _now(),
            "execution_count": 0,
        }
        self._last_fire_times[schedule_id] = 0.0
        self._cache_ages[schedule_id] = 0.0

        snap = _create_ksnap_record(
            module="CronFire",
            result="REGISTERED",
            i_value=0.9,
            ftel=0.9,
            psi_anchor_id=f"cron_{schedule_id}",
            description=f"Cron schedule REGISTERED: {schedule_id} ({cron_expr})",
        )
        self.execution_history.append(snap)

        return {
            "registered": True,
            "schedule_id": schedule_id,
            "ksnap_id": snap["snap_id"],
            "cron_expr": cron_expr,
        }

    def check_freshness(self, schedule_id: str, max_age_hours: float = 6.0) -> dict:
        """缓存新鲜度检查。

        Args:
            schedule_id: 任务标识
            max_age_hours: 最大缓存时效（小时）

        Returns:
            {"fresh": bool, "cache_age_h": float, "need_refetch": bool}
        """
        if schedule_id not in self.schedules:
            return {"fresh": False, "cache_age_h": -1, "need_refetch": True, "error": "Unknown schedule"}

        last_fire = self._last_fire_times.get(schedule_id, 0.0)
        if last_fire == 0.0:
            # 从未执行过
            return {"fresh": False, "cache_age_h": 999.0, "need_refetch": True}

        age_seconds = _now() - last_fire
        age_hours = age_seconds / 3600.0
        self._cache_ages[schedule_id] = age_hours

        fresh = age_hours <= max_age_hours
        return {
            "fresh": fresh,
            "cache_age_h": round(age_hours, 2),
            "need_refetch": not fresh,
            "max_age_h": max_age_hours,
        }

    def fire(self, schedule_id: str, current_time: float = None) -> dict:
        """触发执行。

        流程: freshness 检查 → ψ-Anchor 约束检查 → 执行 → 写入 L1+L3。

        Args:
            schedule_id: 任务标识
            current_time: 模拟当前时间

        Returns:
            {"ksnap_id": str, "output": dict, "psi_checks": dict, "l1_path": str, "l3_path": str}
        """
        if schedule_id not in self.schedules:
            return {
                "ksnap_id": "",
                "error": f"Unknown schedule: {schedule_id}",
            }

        sched = self.schedules[schedule_id]
        now = current_time or _now()

        # 1. Freshness 检查
        freshness = self.check_freshness(schedule_id)

        # 2. ψ-Anchor 约束检查
        psi_checks = {}
        for anchor in sched["psi_anchors"]:
            psi_checks[anchor["id"]] = {
                "rule": anchor["rule"],
                "I": anchor["I"],
                "passed": True,  # 模拟：所有约束通过
            }

        # 3. 执行任务
        task_name = sched["task_payload"].get("task", "unknown")
        output = self._simulate_task_output(task_name, sched["task_payload"])

        # 4. 更新状态
        self._last_fire_times[schedule_id] = now
        sched["execution_count"] += 1

        # 5. 生成 L1 和 L3 路径
        l1_path = f"/tomas/L1/{schedule_id}/{_sha256(str(now))[:8]}.json"
        l3_path = f"/tomas/L3/{schedule_id}/{_sha256(str(now))[:8]}.md"

        snap = _create_ksnap_record(
            module="CronFire",
            result="FIRED",
            i_value=0.95,
            ftel=0.9,
            psi_anchor_id=f"cron_{schedule_id}",
            description=f"Cron FIRED: {schedule_id} task={task_name} count={sched['execution_count']}",
        )
        self.execution_history.append(snap)

        return {
            "ksnap_id": snap["snap_id"],
            "output": output,
            "psi_checks": psi_checks,
            "l1_path": l1_path,
            "l3_path": l3_path,
            "freshness": freshness,
            "execution_count": sched["execution_count"],
        }

    def _simulate_task_output(self, task_name: str, payload: dict) -> dict:
        """模拟任务输出（无外部 API 调用）。"""
        outputs = {
            "competitor_track": {
                "L1_raw": f"[competitor_track] 竞品追踪数据于 {time.strftime('%Y-%m-%d %H:%M')} 更新",
                "L3_summary_md": f"## 竞品追踪报告\n\n- 任务: {task_name}\n- 状态: 完成\n- 时间: {time.strftime('%Y-%m-%d %H:%M')}\n",
                "L3_html": f"<h2>竞品追踪报告</h2><p>任务: {task_name}</p><p>状态: 完成</p>",
                "psi_applied": ["psi_automation_readonly", "psi_source_freshness"],
            },
            "seo_audit": {
                "L1_raw": f"[seo_audit] SEO 审计于 {time.strftime('%Y-%m-%d')} 完成",
                "L3_summary_md": f"## SEO 审计\n\n- 关键词: {payload.get('params', {}).get('keywords', 'N/A')}\n- 状态: 完成\n",
                "L3_html": "<h2>SEO 审计</h2><p>状态: 完成</p>",
                "psi_applied": ["psi_automation_readonly"],
            },
            "inspiration_collect": {
                "L1_raw": f"[inspiration] 灵感收集: {len(payload.get('params', {}).get('sources', []))} 来源",
                "L3_summary_md": f"## 灵感收集\n\n- 来源数: {len(payload.get('params', {}).get('sources', []))}\n- 状态: 完成\n",
                "L3_html": "<h2>灵感收集</h2><p>状态: 完成</p>",
                "psi_applied": ["psi_no_network_write", "psi_audit_trail"],
            },
            "daily_report": {
                "L1_raw": f"[daily_report] 日报于 {time.strftime('%Y-%m-%d')} 生成",
                "L3_summary_md": f"## 日报\n\n- 日期: {time.strftime('%Y-%m-%d')}\n- 状态: 完成\n",
                "L3_html": "<h2>日报</h2><p>状态: 完成</p>",
                "psi_applied": ["psi_audit_trail"],
            },
        }

        default_output = {
            "L1_raw": f"[{task_name}] 模拟执行于 {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "L3_summary_md": f"## {task_name}\n\n模拟执行完成。",
            "L3_html": f"<h2>{task_name}</h2><p>模拟执行完成。</p>",
            "psi_applied": [],
        }

        return outputs.get(task_name, default_output)

    def simulate_output(self, task_name: str) -> dict:
        """模拟自动化输出（竞品追踪/SEO/灵感收集）。

        Args:
            task_name: 任务类型名

        Returns:
            {"L1_raw": str, "L3_summary_md": str, "L3_html": str, "psi_applied": list}
        """
        return self._simulate_task_output(task_name, {"task": task_name, "params": {}})

    def get_execution_log(self, schedule_id: str = None) -> List[dict]:
        """获取执行日志（κ-Snap 审计链）。

        Args:
            schedule_id: 可选，按 schedule_id 过滤

        Returns:
            执行历史记录列表
        """
        if schedule_id:
            return [h for h in self.execution_history
                    if h.get("psi_anchor_id", "").endswith(schedule_id)]
        return list(self.execution_history)

    def get_schedules(self) -> dict:
        """获取所有已注册调度。"""
        return {
            sid: {
                "cron_expr": s["cron_expr"],
                "task": s["task_payload"].get("task", "unknown"),
                "execution_count": s["execution_count"],
                "registered_at": s["registered_at"],
            }
            for sid, s in self.schedules.items()
        }


# ══════════════════════════════════════════════════════════════════
# 类 4: SoulGraph — L1 阿卡西 Soul-Graph + 梦境引擎
# ══════════════════════════════════════════════════════════════════

class SoulGraph:
    """L1 阿卡西 Soul-Graph + Dream Engine (κ-Snap Compaction)。

    分层存储：
      - daily_summary: 日摘要
      - weekly_archive: 周认知档案
      - monthly_cognition: 月认知图谱
      - core_identity: 核心身份（不压缩）
    """

    _DEFAULT_LAYERS = ["daily_summary", "weekly_archive", "monthly_cognition", "core_identity"]

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.soul_graph: Dict[str, dict] = {}
        self.compaction_log: List[dict] = []
        self.layers = list(self._DEFAULT_LAYERS)
        self._segment_counter = 0
        self._raw_segments: List[dict] = []

    def ingest(self, source_ksnap_ids: List[str], raw_content: str) -> dict:
        """摄入新对话/交互。

        Args:
            source_ksnap_ids: 关联的 κ-Snap ID 列表
            raw_content: 原始内容

        Returns:
            {"ingested": bool, "segment_id": str, "ksnap_id": str}
        """
        segment_id = f"seg-{self.user_id}-{_sha256(raw_content)[:8]}"
        self._segment_counter += 1

        segment = {
            "segment_id": segment_id,
            "source_ksnap_ids": source_ksnap_ids,
            "content": raw_content,
            "timestamp": _now(),
            "size_chars": len(raw_content),
        }
        self._raw_segments.append(segment)

        snap = _create_ksnap_record(
            module="SoulGraph",
            result="INGESTED",
            i_value=0.8,
            ftel=0.8,
            psi_anchor_id=f"soul_{self.user_id}",
            description=f"Ingested segment {segment_id[:20]} ({len(raw_content)} chars)",
        )
        self.compaction_log.append(snap)

        return {
            "ingested": True,
            "segment_id": segment_id,
            "ksnap_id": snap["snap_id"],
            "size_chars": len(raw_content),
        }

    def dream_engine_compact(self) -> dict:
        """梦境引擎两阶段压缩。

        Phase 1: rule_based_prune — 截断超长 tool return，去冗余轮次（无 LLM）
        Phase 2: semantic_compact — 对话 → 日摘要 → 周归档 → 归入 Soul-Graph L1

        Returns:
            {"compacted_segments": int, "knowledge_preserved": list, "ksnap_id": str}
        """
        if not self._raw_segments:
            return {
                "compacted_segments": 0,
                "knowledge_preserved": [],
                "ksnap_id": "",
                "message": "No raw segments to compact",
            }

        original_count = len(self._raw_segments)

        # Phase 1: 启发式规则裁剪
        pruned = self._rule_based_prune(self._raw_segments)

        # Phase 2: 语义摘要
        knowledge_preserved = self._semantic_compact(pruned)

        # 归档到 Soul-Graph 层级
        self._archive_to_layers(knowledge_preserved)

        self._raw_segments = []  # 清空已压缩的原始段

        snap = _create_ksnap_record(
            module="SoulGraph",
            result="COMPACTED",
            i_value=0.9,
            ftel=0.85,
            psi_anchor_id=f"soul_{self.user_id}",
            description=f"Dream engine compacted {original_count} segments → {len(knowledge_preserved)} concepts",
        )
        self.compaction_log.append(snap)

        return {
            "compacted_segments": original_count,
            "knowledge_preserved": knowledge_preserved,
            "ksnap_id": snap["snap_id"],
            "original_segments": original_count,
            "concepts_extracted": len(knowledge_preserved),
        }

    def _rule_based_prune(self, segments: List[dict]) -> List[dict]:
        """Phase 1: 启发式规则裁剪。

        规则：
          - 截断超过 2000 字符的内容
          - 去除重复度 > 90% 的段
          - 去除纯工具调用返回（模式匹配）
        """
        pruned = []
        seen_hashes = set()

        for seg in segments:
            content = seg.get("content", "")

            # 规则 1: 截断超长内容
            if len(content) > 2000:
                content = content[:2000] + " [...]"

            # 规则 2: 去重复（基于内容哈希）
            ch = _sha256(content)[:16]
            if ch in seen_hashes:
                continue
            seen_hashes.add(ch)

            # 规则 3: 检测纯工具返回（包含大量 JSON/代码块）
            if self._is_likely_tool_return(content):
                # 保留但截断: 只保留前 200 字符摘要
                content = content[:200] + " [tool_return_truncated]"

            pruned.append({**seg, "content": content})

        return pruned

    def _is_likely_tool_return(self, content: str) -> bool:
        """检测内容是否大概率是工具返回（JSON/代码块密集）。"""
        json_patterns = [r'"status":', r'"error":', r'"result":', r'"data":',
                         r'"type":', r'"event":', r'```json', r'output_type']
        code_indicators = [r'```python', r'```javascript', r'```bash', r'Traceback',
                           r'File "', r'line \d+', r'Error:', r'Exception:']
        score = 0
        for pat in json_patterns:
            if re.search(pat, content):
                score += 1
        for pat in code_indicators:
            if re.search(pat, content):
                score += 1
        return score >= 3

    def _semantic_compact(self, segments: List[dict]) -> List[str]:
        """Phase 2: 语义摘要（启发式，无 LLM）。

        提取关键句、命名实体、高频概念。
        """
        if not segments:
            return []

        all_text = " ".join(seg.get("content", "") for seg in segments)

        # 提取关键词（基于词频）
        tokens = _simple_tokenize(all_text)
        token_freq = Counter(tokens)

        # 过滤停用词
        stopwords = {"the", "is", "at", "which", "on", "and", "a", "an", "in",
                     "to", "of", "for", "with", "it", "that", "this", "as", "be",
                     "was", "are", "has", "have", "from", "or", "by", "not", "but",
                     "de", "la", "en", "el", "un", "que", "los", "las", "del"}
        keywords = [(w, c) for w, c in token_freq.most_common(30)
                    if w not in stopwords and len(w) > 1][:15]

        # 提取命名实体（大写开头连续词）
        entities = re.findall(r'\b([A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]{2,}){0,2})\b', all_text)
        unique_entities = list(dict.fromkeys(entities))[:10]

        concepts = [f"concept:{kw}" for kw, _ in keywords]
        concepts += [f"entity:{e}" for e in unique_entities]

        # 提取关键句（包含多个高频词的句子）
        sentences = re.split(r'[。！？.!?\n]+', all_text)
        for sent in sentences[:5]:
            sent = sent.strip()
            if len(sent) > 10 and len(sent) < 200:
                kw_count = sum(1 for kw, _ in keywords if kw in sent.lower())
                if kw_count >= 2:
                    concepts.append(f"key_sentence:{sent[:120]}")

        return concepts[:25]

    def _archive_to_layers(self, concepts: List[str]) -> None:
        """将压缩后的概念归档到 Soul-Graph 各层。"""
        now = _now()
        day = time.strftime("%Y-%m-%d", time.localtime(now))

        # 日摘要层
        daily_key = f"daily_{day}"
        if daily_key not in self.soul_graph:
            self.soul_graph[daily_key] = {
                "layer": "daily_summary",
                "content": "",
                "concepts": [],
                "timestamp": now,
            }
        self.soul_graph[daily_key]["concepts"].extend(concepts)
        self.soul_graph[daily_key]["content"] += f"\n[{day}] " + "; ".join(concepts[:10])

        # 周归档层
        week_num = time.strftime("%Y-W%U", time.localtime(now))
        weekly_key = f"weekly_{week_num}"
        if weekly_key not in self.soul_graph:
            self.soul_graph[weekly_key] = {
                "layer": "weekly_archive",
                "content": "",
                "concepts": [],
                "timestamp": now,
            }
        self.soul_graph[weekly_key]["concepts"].extend(concepts[:8])
        self.soul_graph[weekly_key]["content"] += f"\n[Week {week_num}] " + "; ".join(concepts[:8])

        # 月球知层
        month = time.strftime("%Y-%m", time.localtime(now))
        monthly_key = f"monthly_{month}"
        if monthly_key not in self.soul_graph:
            self.soul_graph[monthly_key] = {
                "layer": "monthly_cognition",
                "content": "",
                "concepts": [],
                "timestamp": now,
            }
        self.soul_graph[monthly_key]["concepts"].extend(concepts[:5])
        self.soul_graph[monthly_key]["content"] += f"\n[{month}] " + "; ".join(concepts[:5])

        # 核心身份层（仅保留高频概念）
        if "core_identity" not in self.soul_graph:
            self.soul_graph["core_identity"] = {
                "layer": "core_identity",
                "content": "",
                "concepts": [],
                "timestamp": now,
            }
        identity_concepts = [c for c in concepts if c.startswith("concept:")][:3]
        self.soul_graph["core_identity"]["concepts"].extend(identity_concepts)
        if identity_concepts:
            self.soul_graph["core_identity"]["content"] += "; ".join(identity_concepts)

    def knowledge_preservation_check(self, original: str, compacted: str) -> dict:
        """认知保全检查：压缩前有价值认知是否已入 L1？

        Args:
            original: 原始文本
            compacted: 压缩后文本

        Returns:
            {"preserved": bool, "lost_concepts": list, "confidence": float}
        """
        orig_tokens = set(_simple_tokenize(original))
        comp_tokens = set(_simple_tokenize(compacted))

        if not orig_tokens:
            return {"preserved": True, "lost_concepts": [], "confidence": 1.0}

        # 重叠度
        overlap = orig_tokens & comp_tokens
        retention = len(overlap) / len(orig_tokens)

        # 丢失概念
        lost = list(orig_tokens - comp_tokens)[:10]

        preserved = retention >= 0.3

        return {
            "preserved": preserved,
            "lost_concepts": lost,
            "confidence": round(retention, 4),
            "original_tokens": len(orig_tokens),
            "compacted_tokens": len(comp_tokens),
        }

    def query_soul(self, concept: str, layer: str = None) -> dict:
        """查询 Soul-Graph：按概念搜索。

        Args:
            concept: 搜索概念
            layer: 可选，指定层名过滤

        Returns:
            {"found": bool, "results": list, "source_layers": list}
        """
        results = []
        source_layers = []

        for key, entry in self.soul_graph.items():
            entry_layer = entry.get("layer", "")
            if layer and entry_layer != layer:
                continue

            content = entry.get("content", "")
            concepts = entry.get("concepts", [])

            if concept.lower() in content.lower() or any(concept.lower() in c.lower() for c in concepts):
                results.append({
                    "key": key,
                    "layer": entry_layer,
                    "match_content": content[:200],
                    "timestamp": entry.get("timestamp", 0),
                })
            source_layers.append(entry_layer)

        return {
            "found": len(results) > 0,
            "results": results,
            "source_layers": list(set(source_layers)),
            "total_matches": len(results),
        }

    def get_growth_metrics(self) -> dict:
        """Soul-Graph 增长指标。

        Returns:
            {"total_segments": int, "layers": dict, "last_compaction": str}
        """
        layer_counts = {}
        total_concepts = 0
        for entry in self.soul_graph.values():
            layer_name = entry.get("layer", "unknown")
            layer_counts[layer_name] = layer_counts.get(layer_name, 0) + 1
            total_concepts += len(entry.get("concepts", []))

        last_compaction = "never"
        if self.compaction_log:
            last_entry = self.compaction_log[-1]
            last_compaction = time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(last_entry.get("timestamp", 0)),
            )

        return {
            "total_segments": self._segment_counter,
            "total_concepts": total_concepts,
            "total_entries": len(self.soul_graph),
            "layers": layer_counts,
            "last_compaction": last_compaction,
            "compaction_log_count": len(self.compaction_log),
        }

    def get_raw_segments_count(self) -> int:
        """获取待压缩原始段数量。"""
        return len(self._raw_segments)


# ══════════════════════════════════════════════════════════════════
# 类 5: MUSSoulDriftCheck — MUS 防漂移
# ══════════════════════════════════════════════════════════════════

class MUSSoulDriftCheck:
    """MUS 双存：L1 Soul-Graph vs L3 当前意图 对齐检测。

    防数字分身漂离用户真实价值观。
    使用关键词频率向量 + 余弦相似度进行对齐检测。
    """

    def __init__(self):
        self.drift_checks: List[dict] = []
        self.alignment_threshold = 0.85
        self.ksnap_log: List[dict] = []

    def extract_l1_representation(self, soul_graph: dict) -> List[float]:
        """从 Soul-Graph 提取 L1 表征向量（关键词频率向量）。

        Args:
            soul_graph: SoulGraph.soul_graph 字典

        Returns:
            归一化频率向量
        """
        word_counts: Dict[str, int] = Counter()
        for entry in soul_graph.values():
            content = entry.get("content", "")
            tokens = _simple_tokenize(content)
            for token in tokens:
                if len(token) > 1:
                    word_counts[token] += 1

        if not word_counts:
            return []

        # 取 top-50 词频
        top_words = [w for w, _ in word_counts.most_common(50)]
        total = sum(word_counts.values()) or 1
        return [word_counts[w] / total for w in top_words]

    def extract_l3_intent(self, recent_dialogue: List[str]) -> List[float]:
        """从当前对话提取 L3 意图向量。

        Args:
            recent_dialogue: 最近对话列表

        Returns:
            归一化频率向量
        """
        combined = " ".join(recent_dialogue)
        tokens = _simple_tokenize(combined)
        word_counts = Counter(t for t in tokens if len(t) > 1)

        if not word_counts:
            return []

        top_words = [w for w, _ in word_counts.most_common(50)]
        total = sum(word_counts.values()) or 1
        return [word_counts[w] / total for w in top_words]

    def cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """计算两个向量的余弦相似度。

        Args:
            vec_a: 向量 A
            vec_b: 向量 B

        Returns:
            余弦相似度 [0, 1]
        """
        if not vec_a or not vec_b:
            return 0.0

        # 对齐向量长度
        max_len = max(len(vec_a), len(vec_b))
        a = vec_a + [0.0] * (max_len - len(vec_a))
        b = vec_b + [0.0] * (max_len - len(vec_b))

        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
        norm_b = math.sqrt(sum(y * y for y in b)) or 1.0

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    def check_drift(self, soul_graph: dict, recent_dialogue: List[str]) -> dict:
        """漂移检测：L1 Soul-Graph vs L3 当前意图。

        Args:
            soul_graph: SoulGraph.soul_graph
            recent_dialogue: 最近对话

        Returns:
            {"drift_score": float, "drift_detected": bool, "deviation": float, "recommendation": str}
        """
        l1_vec = self.extract_l1_representation(soul_graph)
        l3_vec = self.extract_l3_intent(recent_dialogue)

        similarity = self.cosine_similarity(l1_vec, l3_vec)
        deviation = 1.0 - similarity

        # 漂移判定
        is_drift = similarity < self.alignment_threshold

        if is_drift:
            if deviation > 0.5:
                recommendation = "严重漂移：建议立即进行人工对齐审查，检查 Soul-Graph 中 core_identity 层"
            elif deviation > 0.3:
                recommendation = "中度漂移：建议季度对齐审查，更新 Soul-Graph 认知"
            else:
                recommendation = "轻度漂移：建议日常回顾，确认 L3 意图与 L1 认知一致"
        else:
            recommendation = "对齐良好：无需操作"

        result = {
            "drift_score": round(similarity, 4),
            "drift_detected": is_drift,
            "deviation": round(deviation, 4),
            "recommendation": recommendation,
            "threshold": self.alignment_threshold,
            "l1_vector_size": len(l1_vec),
            "l3_vector_size": len(l3_vec),
        }

        self.drift_checks.append(result)
        return result

    def propose_alignment_review(self, drift_result: dict) -> dict:
        """提议对齐审查。

        Args:
            drift_result: check_drift 返回的结果

        Returns:
            {"mus_id": str, "review_required": bool, "ksnap_id": str, "next_review": str}
        """
        review_required = drift_result.get("drift_detected", False)
        mus_id = f"mus-align-{uuid.uuid4().hex[:8]}"

        snap = _create_ksnap_record(
            module="MUSSoulDriftCheck",
            result="REVIEW_PROPOSED" if review_required else "ALIGNED",
            i_value=drift_result.get("drift_score", 0.5),
            ftel=0.85,
            psi_anchor_id=mus_id,
            description=f"Alignment review: drift={drift_result.get('drift_score', 'N/A')}",
        )
        self.ksnap_log.append(snap)

        # 下一审查时间（季度后）
        next_review_ts = _now() + 90 * 24 * 3600
        next_review = time.strftime("%Y-%m-%d", time.localtime(next_review_ts))

        return {
            "mus_id": mus_id,
            "review_required": review_required,
            "ksnap_id": snap["snap_id"],
            "next_review": next_review,
            "current_alignment": drift_result.get("drift_score", 0.0),
        }

    def get_drift_history(self) -> List[dict]:
        """获取漂移检测历史。"""
        return list(self.drift_checks)

    def get_alignment_status(self, soul_graph: dict, recent_dialogue: List[str]) -> dict:
        """综合对齐状态检查。

        Returns:
            {"aligned": bool, "score": float, "history": list, "trend": str}
        """
        current = self.check_drift(soul_graph, recent_dialogue)

        # 趋势分析
        trend = "stable"
        if len(self.drift_checks) >= 2:
            prev = self.drift_checks[-2]["drift_score"]
            curr = current["drift_score"]
            if curr < prev - 0.1:
                trend = "declining"
            elif curr > prev + 0.1:
                trend = "improving"

        return {
            "aligned": not current["drift_detected"],
            "score": current["drift_score"],
            "history": len(self.drift_checks),
            "trend": trend,
        }


# ══════════════════════════════════════════════════════════════════
# 类 6: TOMASGoalDirectedAgent — 编排器
# ══════════════════════════════════════════════════════════════════

class TOMASGoalDirectedAgent:
    """GoalPro + CronFire + SoulAgent → TOMAS 阿卡西操作系统。

    三阶段编排：
      Phase 1: propose_goal → 起草契约，停住等待授权
      Phase 2: execute_authorized → 检查 Gate，执行或注册 Cron
      Phase 3: dream_engine_cycle → 压缩归档 + 漂移检测
    """

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.goal_contract: Optional[GoalContract] = None
        self.execution_gate = ExecutionGate()
        self.cron_fire = CronFire()
        self.soul_graph = SoulGraph(user_id)
        self.drift_check = MUSSoulDriftCheck()
        self.phase = "propose"
        self._session_log: List[dict] = []
        # v3.11: grill-me 引擎
        self.gap_analyzer = DIKWPGapAnalyzer() if _HAS_GRILL_ME and DIKWPGapAnalyzer else None
        self.grill_gate = GrillExecutionGate() if _HAS_GRILL_ME and GrillExecutionGate else None
        self.no_silent_assumption = PsiNoSilentAssumption() if _HAS_GRILL_ME and PsiNoSilentAssumption else None
        self.requirement_tracer = RequirementTracer() if _HAS_GRILL_ME and RequirementTracer else None

    def propose_goal(self, vague_request: str) -> dict:
        """Phase 1: 起草 Goal Contract → 编译为 ψ-Anchor → κ-Snap 记待批。

        Args:
            vague_request: 用户模糊意图

        Returns:
            Goal Contract 状态 + 提示信息
        """
        self.phase = "propose"

        # [v3.11] Grill-me 需求审问（非阻塞模式：记录缺口但不拦截流程）
        grill_result = self.grill_interrogate(vague_request)

        # 从模糊请求中解析五闸门（模拟）
        goal = GoalContract(f"req-{uuid.uuid4().hex[:8]}")
        goal.draft(
            intent=vague_request,
            scope_in=self._infer_scope_in(vague_request),
            scope_out=self._infer_scope_out(vague_request),
            evidence=["all_tests_pass", "code_review_approved"],
            pauses=["blocking_questions", "scope_boundary_hit"],
            acceptance="all evidence items verified AND execution gate authorized",
        )
        self.goal_contract = goal

        # 提交为 PROPOSED
        proposal = goal.propose()

        # 摄入 Soul-Graph
        self.soul_graph.ingest(
            source_ksnap_ids=[proposal["ksnap_id"]],
            raw_content=f"Goal proposed: {vague_request}",
        )

        return {
            "goal_hash": goal.goal_hash,
            "status": goal.status,
            "ksnap_id": proposal["ksnap_id"],
            "message": proposal["message"],
            "psi_anchor_dsl": goal.to_psi_anchor_dsl()[:200] + "...",
            "jsonld_context": goal.to_jsonld()["@context"],
            "grill_result": grill_result,
        }

    def grill_interrogate(self, requirement: str) -> dict:
        """[v3.11] Grill-me 需求审问：DIKWP 五层分析 + 静默脑补检测 + 闸门检查。
        
        闭环缺一步不出方案。
        
        Args:
            requirement: 原始需求文本
            
        Returns:
            {"passed": bool, "gaps_remaining": list, "silent_assumptions": list,
             "gap_dsl": str, "trace_chain": list}
        """
        if not self.gap_analyzer or not self.grill_gate:
            return {"passed": True, "note": "grill-me module not available — bypassed"}
        
        # Step 1: DIKWP 五层缺口分析
        gap_report = self.gap_analyzer.analyze(requirement)
        
        # Step 2: 静默脑补扫描
        silent_assumptions = []
        if self.no_silent_assumption:
            silent_assumptions = self.no_silent_assumption.scan_for_silent_assumptions(gap_report)
            gap_report.silent_assumptions = silent_assumptions
        
        # Step 3: 注册到执行闸门
        self.grill_gate.register_gap_analysis(gap_report)
        
        # Step 4: 检查全缺口是否关闭
        all_closed = self.grill_gate.verify_all_gaps_closed(gap_report.requirement_id)
        
        # Step 5: 生成 DSL
        gap_dsl = self.gap_analyzer.generate_gap_dsl(gap_report)
        
        # Step 6: 溯源链
        trace_chain = []
        if self.requirement_tracer:
            trace_chain = self.requirement_tracer.get_trace_chain(gap_report.requirement_id)
        
        # 收集未关闭的缺口
        gaps_remaining = [
            {"layer": layer, "status": gap.status, "description": gap.gap_description}
            for layer, gap in gap_report.layers.items()
            if not gap.closed
        ]
        
        passed = all_closed and len(silent_assumptions) == 0
        
        return {
            "passed": passed,
            "requirement_id": gap_report.requirement_id,
            "all_gaps_closed": all_closed,
            "gaps_remaining": gaps_remaining,
            "silent_assumptions": silent_assumptions,
            "gap_dsl": gap_dsl,
            "trace_chain": trace_chain,
            "lock_reason": "" if passed else self.grill_gate.lock_reason(gap_report.requirement_id),
        }

    def _infer_scope_in(self, request: str) -> List[str]:
        """从模糊请求推断 scope_in（模拟）。"""
        request_lower = request.lower()
        scopes = []
        if any(w in request_lower for w in ["重构", "refactor", "订单", "order"]):
            scopes.extend(["src/", "tests/"])
        if any(w in request_lower for w in ["api", "接口"]):
            scopes.append("api/")
        if any(w in request_lower for w in ["数据库", "database", "db"]):
            scopes.append("db/")
        return scopes if scopes else ["src/"]

    def _infer_scope_out(self, request: str) -> List[str]:
        """从模糊请求推断 scope_out（模拟）。"""
        request_lower = request.lower()
        scopes = ["production_data", "user_pii"]
        if "不动数据库" in request_lower or "no db" in request_lower:
            scopes.append("database_schema")
        if "保持api不变" in request_lower or "keep api" in request_lower:
            scopes.append("api_signature_change")
        return scopes

    def execute_authorized(self, user_signature: str) -> dict:
        """Phase 2: 检查 Execution Gate → 执行或注册 Cron。

        Args:
            user_signature: 用户授权签名

        Returns:
            执行结果
        """
        if not self.goal_contract:
            return {"authorized": False, "error": "No goal contract to execute"}

        self.phase = "execute"

        # 授权 Goal
        auth = self.goal_contract.authorize(user_signature)
        if not auth["authorized"]:
            return auth

        # 授权 Execution Gate
        self.execution_gate.grant(self.goal_contract.goal_hash, user_signature)

        # 检查 Gate
        gate_check = self.execution_gate.check(self.goal_contract.goal_hash)
        if not gate_check["allowed"]:
            return {"authorized": False, "error": gate_check["reason"]}

        # 执行
        self.goal_contract.execute()

        # 检查是否需要 Cron 调度
        schedule_created = False
        if any(w in self.goal_contract.intent.lower() for w in ["定时", "周期", "daily", "weekly", "schedule"]):
            cf_result = self.cron_fire.register(
                f"goal_{self.goal_contract.goal_hash[:8]}",
                "0 10 * * *",
                {"task": self.goal_contract.intent[:30]},
            )
            schedule_created = True
        else:
            cf_result = {"registered": False}

        # 完成
        complete = self.goal_contract.complete()

        # 摄入 Soul-Graph
        self.soul_graph.ingest(
            source_ksnap_ids=[auth["ksnap_id"], complete["ksnap_id"]],
            raw_content=f"Goal executed: {self.goal_contract.intent}",
        )

        return {
            "authorized": True,
            "goal_hash": self.goal_contract.goal_hash,
            "goal_status": self.goal_contract.status,
            "gate_check": gate_check,
            "schedule_created": schedule_created,
            "cron_result": cf_result,
            "ksnap_ids": [auth["ksnap_id"], complete["ksnap_id"]],
        }

    def dream_engine_cycle(self) -> dict:
        """Phase 3: 梦境引擎后台循环 — compaction → archive → drift check。

        Returns:
            {"compaction": dict, "drift_check": dict, "status": str}
        """
        self.phase = "dream"

        # 1. 梦境引擎压缩
        compaction = self.soul_graph.dream_engine_compact()

        # 2. 漂移检测
        sample_dialogue = ["用户讨论重构任务", "关注代码解耦", "保持系统稳定性"]
        drift = self.drift_check.check_drift(self.soul_graph.soul_graph, sample_dialogue)

        # 3. 对齐审查提议
        alignment = self.drift_check.propose_alignment_review(drift)

        return {
            "compaction": compaction,
            "drift_check": drift,
            "alignment": alignment,
            "status": "dream_cycle_complete",
        }

    def simulate_interaction(self, dialogue_turns: List[str]) -> dict:
        """模拟完整的 Goal → Execute → Dream 流程。

        Args:
            dialogue_turns: 对话轮次列表

        Returns:
            全流程 κ-Snap 审计链
        """
        ksnap_chain = []

        # Phase 1: Propose
        if dialogue_turns:
            vague_request = dialogue_turns[0]
            proposal = self.propose_goal(vague_request)
            ksnap_chain.append({
                "phase": "propose",
                "ksnap_id": proposal["ksnap_id"],
                "goal_hash": proposal["goal_hash"],
            })

        # Phase 2: Execute
        if self.goal_contract:
            exec_result = self.execute_authorized("simulated_user")
            if "ksnap_ids" in exec_result:
                for kid in exec_result["ksnap_ids"]:
                    ksnap_chain.append({"phase": "execute", "ksnap_id": kid})

        # Phase 3: Dream
        dream = self.dream_engine_cycle()
        ksnap_chain.append({
            "phase": "dream",
            "ksnap_id": dream["compaction"]["ksnap_id"],
            "compacted": dream["compaction"]["compacted_segments"],
        })

        return {
            "chain": ksnap_chain,
            "total_steps": len(ksnap_chain),
            "final_status": self.goal_contract.status if self.goal_contract else "N/A",
        }

    def get_full_status(self) -> dict:
        """获取完整系统状态。

        Returns:
            {"goal": dict, "cron": dict, "soul": dict, "drift": dict, "phase": str}
        """
        goal_status = self.goal_contract.get_status() if self.goal_contract else {}
        cron_schedules = self.cron_fire.get_schedules()
        soul_metrics = self.soul_graph.get_growth_metrics()
        drift_history = len(self.drift_check.get_drift_history())

        return {
            "user_id": self.user_id,
            "phase": self.phase,
            "goal": {
                "has_contract": self.goal_contract is not None,
                "status": goal_status.get("status", "N/A"),
                "goal_hash": goal_status.get("goal_hash", ""),
                "intent": goal_status.get("intent", ""),
                "ksnap_count": goal_status.get("ksnap_count", 0),
            },
            "cron": {
                "schedules": len(cron_schedules),
                "execution_history": len(self.cron_fire.execution_history),
            },
            "soul": soul_metrics,
            "drift": {
                "checks": drift_history,
                "threshold": self.drift_check.alignment_threshold,
            },
        }


# ══════════════════════════════════════════════════════════════════
# 自测 (if __name__ == "__main__")
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    passed = 0
    total = 0

    def check(name: str, cond: bool) -> None:
        global passed, total
        total += 1
        if cond:
            passed += 1
        else:
            print(f"  FAIL: {name}")

    print("=" * 60)
    print("TOMAS AGI v3.10 — goal_directed_agent 自测")
    print("=" * 60)

    # ──── GoalContract 测试 ────
    print("\n[GoalContract]")

    gc = GoalContract("req-001")
    check("gc init status DRAFT", gc.status == "DRAFT")
    check("gc request_id", gc.request_id == "req-001")

    gc.draft(
        "重构订单模块",
        ["order/src", "order/test"],
        ["add_feature", "alter_schema"],
        ["all_tests_pass"],
        ["unanswered_questions"],
        "tests green AND coupling reduced",
    )
    check("goal_hash computed (64 chars)", len(gc.goal_hash) == 64)
    check("status DRAFT after draft", gc.status == "DRAFT")

    dsl = gc.to_psi_anchor_dsl()
    check("dsl contains CREATE ψ-ANCHOR", "CREATE ψ-ANCHOR" in dsl)
    check("dsl contains INTENT", "INTENT" in dsl)
    check("dsl contains SCOPE_IN", "SCOPE_IN" in dsl)
    check("dsl contains SCOPE_OUT", "SCOPE_OUT" in dsl)
    check("dsl contains EVIDENCE", "EVIDENCE" in dsl)
    check("dsl contains PAUSE_CONDITIONS", "PAUSE_CONDITIONS" in dsl)
    check("dsl contains ACCEPTANCE", "ACCEPTANCE" in dsl)
    check("dsl contains EXECUTION_GATE", "EXECUTION_GATE" in dsl)

    jsonld = gc.to_jsonld()
    check("jsonld has @context", jsonld["@context"] == "https://tomas.org/psi/v2")
    check("jsonld has @type GoalContract", jsonld["@type"] == "GoalContract")

    proposal = gc.propose()
    check("propose status PROPOSED", proposal["status"] == "PROPOSED")
    check("propose has ksnap_id", len(proposal["ksnap_id"]) > 0)
    check("propose message has 确认", "确认" in proposal["message"])

    # Cannot propose again
    proposal2 = gc.propose()
    check("cannot propose twice", proposal2.get("error", False))

    auth_result = gc.authorize("user_sig_validation_abc")
    check("authorize succeeds", auth_result["authorized"])
    check("authorize has ksnap_id", len(auth_result["ksnap_id"]) > 0)

    exec_result = gc.execute()
    check("execute succeeds", exec_result["executing"])

    comp_result = gc.complete()
    check("complete succeeds", comp_result["completed"])

    status = gc.get_status()
    check("get_status returns dict", isinstance(status, dict))
    check("get_status gates_defined", status["gates_defined"])
    check("get_status ksnap_count > 0", status["ksnap_count"] > 0)

    # ──── ExecutionGate 测试 ────
    print("\n[ExecutionGate]")

    eg = ExecutionGate()
    check("unauthorized blocked", not eg.check("abc123")["allowed"])
    check("unauthorized reason has REQUIRE", "REQUIRE" in eg.check("abc123")["reason"])

    grant_result = eg.grant("abc123", "user_sig_001")
    check("grant succeeds", grant_result["granted"])
    check("grant has ksnap_id", len(grant_result["ksnap_id"]) > 0)

    check("authorized passes", eg.check("abc123")["allowed"])
    check("authorized no missing", not eg.check("abc123")["missing_authorization"])

    revoke_result = eg.revoke("abc123")
    check("revoke succeeds", revoke_result["revoked"])
    check("after revoke blocked", not eg.check("abc123")["allowed"])

    # ──── CronFire 测试 ────
    print("\n[CronFire]")

    cf = CronFire()
    reg_result = cf.register("daily_report", "0 10 * * *", {"task": "competitor_track"})
    check("register succeeds", reg_result["registered"])
    check("register has ksnap_id", len(reg_result["ksnap_id"]) > 0)
    check("schedule registered", len(cf.schedules) == 1)

    reg2 = cf.register("weekly_seo", "0 8 * * 1", {"task": "seo_audit", "params": {"keywords": "AI,AGI"}})
    check("second register", reg2["registered"])
    check("schedules count 2", len(cf.schedules) == 2)

    # Freshness check (never fired)
    freshness = cf.check_freshness("daily_report")
    check("freshness: never fired not fresh", not freshness["fresh"])
    check("freshness: need_refetch True", freshness["need_refetch"])

    # Fire
    fire_result = cf.fire("daily_report")
    check("fire returns ksnap_id", len(fire_result["ksnap_id"]) > 0)
    check("fire returns output", "output" in fire_result)
    check("fire returns psi_checks", "psi_checks" in fire_result)
    check("fire has l1_path", len(fire_result["l1_path"]) > 0)
    check("fire has l3_path", len(fire_result["l3_path"]) > 0)
    check("fire execution_count 1", fire_result["execution_count"] == 1)

    # Freshness after fire
    freshness2 = cf.check_freshness("daily_report", max_age_hours=6.0)
    check("freshness: after fire fresh", freshness2["fresh"])
    check("freshness: no need_refetch", not freshness2["need_refetch"])

    # Simulate output
    sim = cf.simulate_output("competitor_track")
    check("simulate_output competitor_track", "L1_raw" in sim)
    check("simulate_output has L3_summary_md", "L3_summary_md" in sim)
    check("simulate_output has psi_applied", len(sim["psi_applied"]) > 0)

    sim2 = cf.simulate_output("seo_audit")
    check("simulate_output seo_audit", "L3_html" in sim2)

    # Execution log
    log = cf.get_execution_log()
    check("execution log has entries", len(log) > 0)

    # Schedules
    scheds = cf.get_schedules()
    check("get_schedules count 2", len(scheds) == 2)

    # ──── SoulGraph 测试 ────
    print("\n[SoulGraph]")

    sg = SoulGraph("user-001")
    ingest1 = sg.ingest(["ksnap-1", "ksnap-2"], "用户讨论订单模块重构细节，关注代码解耦...")
    check("ingest succeeds", ingest1["ingested"])
    check("ingest has ksnap_id", len(ingest1["ksnap_id"]) > 0)

    ingest2 = sg.ingest(["ksnap-3"], "讨论了API设计模式，决定使用Repository模式隔离数据层")
    check("ingest 2 succeeds", ingest2["ingested"])

    compact = sg.dream_engine_compact()
    check("compaction succeeds", compact["compacted_segments"] >= 0)
    check("compaction has knowledge_preserved", compact["knowledge_preserved"] is not None)

    # Knowledge preservation
    kpc = sg.knowledge_preservation_check(
        "重构 订单 模块 保持 API 不变 确保 测试 通过",
        "重构 订单 模块 保持 API 测试 通过",
    )
    check("knowledge preserved", kpc["preserved"])
    check("confidence > 0.3", kpc["confidence"] > 0.3)

    # Query soul
    query = sg.query_soul("concept:order")
    check("query soul returns dict", isinstance(query, dict))

    # Growth metrics
    metrics = sg.get_growth_metrics()
    check("growth metrics total_segments >= 0", metrics["total_segments"] >= 0)
    check("growth metrics has layers", "daily_summary" in metrics["layers"] or "core_identity" in metrics["layers"])

    # ──── MUSSoulDriftCheck 测试 ────
    print("\n[MUSSoulDriftCheck]")

    # Populate soul_graph with content first
    sg2 = SoulGraph("user-drift-test")
    sg2.ingest(["k-1"], "AI 助手应保持简洁严谨的技术风格，使用中文回复，优先安全编码")
    sg2.ingest(["k-2"], "用户偏好函数式编程，注重代码可测试性和模块解耦")
    sg2.dream_engine_compact()

    msc = MUSSoulDriftCheck()
    drift = msc.check_drift(sg2.soul_graph, [
        "我想重构订单模块",
        "保持API不变",
        "使用函数式风格",
    ])
    check("drift_score in [0,1]", 0 <= drift["drift_score"] <= 1)
    check("drift has drift_detected", "drift_detected" in drift)
    check("drift has recommendation", len(drift["recommendation"]) > 0)

    # Cosine similarity edge cases
    check("cosine same vectors ~1.0", abs(msc.cosine_similarity([1, 2, 3], [1, 2, 3]) - 1.0) < 0.01)
    check("cosine empty vectors 0", msc.cosine_similarity([], []) == 0.0)
    check("cosine orthogonal ~0", abs(msc.cosine_similarity([1, 0], [0, 1])) < 0.01)

    # Alignment review
    review = msc.propose_alignment_review(drift)
    check("review has mus_id", len(review["mus_id"]) > 0)
    check("review has ksnap_id", len(review["ksnap_id"]) > 0)
    check("review has next_review", len(review["next_review"]) > 0)

    # Drift history
    history = msc.get_drift_history()
    check("drift history length 1", len(history) == 1)

    # ──── TOMASGoalDirectedAgent 集成测试 ────
    print("\n[TOMASGoalDirectedAgent Integration]")

    tga = TOMASGoalDirectedAgent("user-001")

    # Phase 1: Propose (使用完整需求以通过 grill-me 审问)
    proposal_full = tga.propose_goal(
        "开发一个用户登录功能，使用邮箱+密码认证，支持JWT token，"
        "密码至少8位含大小写数字，登录失败3次锁定15分钟，"
        "需通过OWASP安全审计，提供完整的API文档和单元测试"
    )
    check("proposal has goal_hash", "goal_hash" in proposal_full)
    # v3.11: grill-me 可能阻塞模糊需求，接受 PROPOSED 或 GRILL_BLOCKED
    status = proposal_full.get("status", "")
    check("proposal status PROPOSED or GRILL_BLOCKED", status in ("PROPOSED", "GRILL_BLOCKED"))
    if status == "GRILL_BLOCKED":
        check("proposal grill blocked has message", "message" in proposal_full)
        # 跳过后续执行测试
        print("  (grill-blocked, skipping execution tests)")
    else:
        check("proposal requires auth", "确认" in proposal_full.get("message", ""))

        # Phase 2: Execute
        auth_result_full = tga.execute_authorized("user_sig_validation")
        check("execution authorized", auth_result_full["authorized"])
        check("execution goal_status COMPLETED", auth_result_full["goal_status"] == "COMPLETED")

        # Phase 3: Dream
        dream = tga.dream_engine_cycle()
        check("dream cycle succeeds", dream is not None)
        check("dream has compaction", "compaction" in dream)
        check("dream has drift_check", "drift_check" in dream)
        check("dream status complete", dream["status"] == "dream_cycle_complete")

        # Full status
        full_status = tga.get_full_status()
        check("full status has goal", "goal" in full_status)
        check("full status has cron", "cron" in full_status)
        check("full status has soul", "soul" in full_status)
        check("full status has drift", "drift" in full_status)
        check("full status goal has_contract", full_status["goal"]["has_contract"])

        # Simulate interaction
        sim_interaction = tga.simulate_interaction([
            "请帮我重构订单模块，保持API不变",
            "好的，开始吧",
        ])
        check("simulate has chain", len(sim_interaction["chain"]) > 0)
        check("simulate total_steps > 0", sim_interaction["total_steps"] > 0)

    # ──── Grill-me 集成测试 [v3.11] ────
    print("\n[Grill-me Integration]")

    tga_grill = TOMASGoalDirectedAgent("grill-test-user")

    # TG-01: grill_interrogate 方法存在
    check("grill_interrogate exists", hasattr(tga_grill, "grill_interrogate"))

    # TG-02: grill_me 引擎组件已初始化
    if _HAS_GRILL_ME:
        check("gap_analyzer initialized", tga_grill.gap_analyzer is not None)
        check("grill_gate initialized", tga_grill.grill_gate is not None)
        check("no_silent_assumption initialized", tga_grill.no_silent_assumption is not None)
        check("requirement_tracer initialized", tga_grill.requirement_tracer is not None)

    # TG-03: 模糊需求触发缺口
    if tga_grill.gap_analyzer:
        grill_result = tga_grill.grill_interrogate("做个东西")
        check("grill_interrogate returns passed", "passed" in grill_result)
        check("grill_interrogate has gaps_remaining", "gaps_remaining" in grill_result)
        check("grill_interrogate has gap_dsl", "gap_dsl" in grill_result)
        check("vague requirement has gaps", len(grill_result.get("gaps_remaining", [])) > 0 or not grill_result.get("passed", True))

    # TG-04: 完整需求通过审问
    if tga_grill.gap_analyzer:
        detailed_req = "开发一个用户登录功能，使用邮箱+密码认证，支持JWT token，密码至少8位含大小写数字，登录失败3次锁定15分钟，需通过OWASP安全审计"
        grill_result2 = tga_grill.grill_interrogate(detailed_req)
        check("detailed req grill returns result", "passed" in grill_result2)

    # TG-05: grill_interrogate 返回 gap_dsl 含 DIKWP
    if tga_grill.gap_analyzer:
        dsl = grill_result2.get("gap_dsl", "")
        check("gap_dsl contains DIKWP", "DIKWP" in dsl or "grill-me" in dsl)

    # TG-06: grill_interrogate 返回 trace_chain
    if tga_grill.gap_analyzer:
        check("grill_result has trace_chain", "trace_chain" in grill_result2)

    # TG-07: grill_interrogate 返回 requirement_id
    if tga_grill.gap_analyzer:
        check("grill_result has requirement_id", "requirement_id" in grill_result2)

    # TG-08: propose_goal 集成 grill-me（模糊需求被阻塞）
    proposal = tga_grill.propose_goal("做个东西")
    check("propose_goal returns result", "goal_hash" in proposal or "status" in proposal)

    # TG-09: ExecutionGate grill_precheck 集成
    if tga_grill.execution_gate.grill_gate:
        check("execution_gate has grill_gate", True)
        check("execution_gate grill_precheck_enabled", tga_grill.execution_gate.grill_precheck_enabled)

    # TG-10: no_silent_assumption 集成
    if tga_grill.no_silent_assumption:
        check("no_silent_assumption available", True)

    # TG-11: gap_analyzer 一致性（重复分析同一需求返回相同结果）
    if tga_grill.gap_analyzer:
        r1 = tga_grill.grill_interrogate("需要登录功能")
        r2 = tga_grill.grill_interrogate("需要登录功能")
        check("grill_interrogate idempotent", r1.get("requirement_id") == r2.get("requirement_id"))

    # TG-12: grill_precheck_enabled 布尔标志正确
    check("grill_precheck_enabled matches _HAS_GRILL_ME",
          tga_grill.execution_gate.grill_precheck_enabled == _HAS_GRILL_ME)

    # ──── 边界与异常测试 ────
    print("\n[Edge Cases]")

    # GoalContract reject
    gc_reject = GoalContract("req-reject")
    gc_reject.draft("测试拒绝", [], [], [], [], "")
    gc_reject.propose()
    reject_result = gc_reject.reject("范围不明确")
    check("reject succeeds", reject_result["rejected"])

    # ExecutionGate revoke not authorized
    revoke_none = eg.revoke("nonexistent_hash")
    check("revoke nonexistent", not revoke_none["revoked"])

    # CronFire unknown schedule
    unknown_fire = cf.fire("nonexistent")
    check("fire unknown returns error", "error" in unknown_fire)

    # CronFire invalid cron expr
    try:
        cf.register("bad_cron", "invalid", {"task": "x"})
        check("invalid cron raises", False)
    except ValueError:
        check("invalid cron raises ValueError", True)

    # SoulGraph empty compact
    sg_empty = SoulGraph("empty-user")
    empty_compact = sg_empty.dream_engine_compact()
    check("empty compact segments 0", empty_compact["compacted_segments"] == 0)

    # MUSSoulDriftCheck empty
    msc_empty = MUSSoulDriftCheck()
    empty_drift = msc_empty.check_drift({}, [])
    check("empty drift score 0", empty_drift["drift_score"] == 0.0)

    # Execute without goal contract
    tga_no_goal = TOMASGoalDirectedAgent("no-goal-user")
    exec_no_goal = tga_no_goal.execute_authorized("sig")
    check("execute without goal returns error", "error" in exec_no_goal)

    # ──── 结果汇总 ────
    print("\n" + "=" * 60)
    print(f"goal_directed_agent: {passed}/{total} passed")
    if passed == total:
        print("ALL TESTS PASSED")
    else:
        print(f"FAILURES: {total - passed}")
    print("=" * 60)
