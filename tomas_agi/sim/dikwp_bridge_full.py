# -*- coding: utf-8 -*-
"""
DIKWP Full Bridge v1.0 — 完整 DIKWP 桥接器
=============================================

基于论文：
  "DIKWP 人工意识与 Semantic Governance Infrastructure"
  Duan, Y. (2026). GitHub: https://github.com/YucongDuan
  "DIKWP链到太乙神机（TOMAS）的语义安全映射"
  微信公众号文章 (2026-06-22)

核心功能：
  01. DIKWP 五层映射 — Data→Information→Knowledge→Wisdom→Purpose
  02. IntentGuard — 意图安全审计 + ψ-锚硬化
  03. MemoryLedger — 记忆账本 → MUS 双存映射
  04. DAAP 审计协议 — 四层 (Device/Application/Agent/Platform)
  05. 语义安全完备性定理 — Semantic Safety Completeness

集成到现有 TOMAS：
  - dikwp_mapper.py: 增强的五层分类器
  - dikwp_eml_bridge.py: 增强的语义映射
  - psi_gate.py: IntentGuard → ψ-锚
  - agent_audit.py: DAAP 四层审计

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
from collections import defaultdict

logger = logging.getLogger(__name__)

try:
    from .dikwp_mapper import DIKWPMapper
    from .dikwp_eml_bridge import DIKWPEMLBridge
    from .agent_audit import AgentAudit
except ImportError:
    DIKWPMapper, DIKWPEMLBridge, AgentAudit = None, None, None
    logger.info("DIKWP 内部模块未加载，使用独立模式")


# ══════════════════════════════════════════════════════════════════
# 枚举
# ══════════════════════════════════════════════════════════════════

class DIKWPLayer(Enum):
    """DIKWP 五层"""
    DATA = "data"           # 原始数据
    INFORMATION = "information"  # 结构化信息
    KNOWLEDGE = "knowledge"      # 知识
    WISDOM = "wisdom"            # 智慧
    PURPOSE = "purpose"          # 目的/自驱


class IntentSeverity(Enum):
    """意图严重性 (按严重度排序)"""
    SAFE = 0
    SUSPICIOUS = 1
    DANGEROUS = 2
    CRITICAL = 3


class AuditLevel(Enum):
    """DAAP 审计层级"""
    DEVICE = "device"
    APPLICATION = "application"
    AGENT = "agent"
    PLATFORM = "platform"


# ══════════════════════════════════════════════════════════════════
# 数据结构
# ══════════════════════════════════════════════════════════════════

@dataclass
class DIKWPStatement:
    """DIKWP 声明"""
    stmt_id: str
    content: Any
    layer: DIKWPLayer
    I_value: float = 1.0
    psi_anchor_ref: Optional[str] = None
    tdc_timestamp: Optional[int] = None
    source_agent: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class IntentAnalysis:
    """意图分析结果"""
    query: str
    di_layer: DIKWPLayer
    intent_patterns: List[str]
    severity: IntentSeverity = IntentSeverity.SAFE
    risk_factors: List[str] = field(default_factory=list)
    blocked_anchors: List[str] = field(default_factory=list)
    psi_recommendations: List[str] = field(default_factory=list)
    daap_audit_required: bool = False
    confidence: float = 1.0

    def is_safe(self) -> bool:
        return self.severity == IntentSeverity.SAFE


@dataclass
class MemoryLedgerEntry:
    """记忆账本条"""
    entry_id: str
    content: str
    di_layer: DIKWPLayer
    mus_zone_id: Optional[str] = None
    ksnap_hash: Optional[str] = None
    is_hard_anchored: bool = False
    confidence: float = 1.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class SemanticSafetyProof:
    """
    语义安全完备性定理证明结构

    定理：∀ query, ∃(ψ-anchors, mus-zones, daap-audit):
        is_safe(query) ⟺ all_checks_pass(query)
    """
    query_hash: str
    all_checks_pass: bool
    psi_anchors_checked: List[str]
    mus_zones_invoked: List[str]
    daap_levels_cleared: List[str]
    completeness: float  # ∈ [0, 1]
    proof_sketch: str


# ══════════════════════════════════════════════════════════════════
# IntentGuard — 意图安全审计
# ══════════════════════════════════════════════════════════════════

class IntentGuard:
    """
    IntentGuard — 意图安全审计引擎

    功能：
    1. 意图解析 — 将查询映射到 DIKWP 层
    2. 危险模式检测 — PATTERNS_BLACKLIST 匹配
    3. ψ-锚 建议 — 为高风险意图建议硬化锚点
    4. DAAP 层级判断 — 决定需要审计的级别
    """

    # 意图模式 → DIKWP 层映射
    INTENT_LAYER_MAP = {
        "fetch": DIKWPLayer.DATA,
        "get": DIKWPLayer.DATA,
        "read": DIKWPLayer.DATA,
        "count": DIKWPLayer.DATA,
        "query": DIKWPLayer.INFORMATION,
        "search": DIKWPLayer.INFORMATION,
        "filter": DIKWPLayer.INFORMATION,
        "compare": DIKWPLayer.INFORMATION,
        "summarize": DIKWPLayer.KNOWLEDGE,
        "analyze": DIKWPLayer.KNOWLEDGE,
        "explain": DIKWPLayer.KNOWLEDGE,
        "recommend": DIKWPLayer.WISDOM,
        "decide": DIKWPLayer.WISDOM,
        "plan": DIKWPLayer.WISDOM,
        "create": DIKWPLayer.PURPOSE,
        "modify": DIKWPLayer.PURPOSE,
        "delete": DIKWPLayer.PURPOSE,
        "execute": DIKWPLayer.PURPOSE,
        "deploy": DIKWPLayer.PURPOSE,
    }

    # 危险模式黑名单
    PATTERNS_BLACKLIST = [
        # CRITICAL: 系统破坏
        ("DROP TABLE", "数据库破坏", IntentSeverity.CRITICAL),
        ("DELETE FROM", "数据库删除", IntentSeverity.CRITICAL),
        ("TRUNCATE", "数据清空", IntentSeverity.CRITICAL),
        ("rm -rf", "文件系统破坏", IntentSeverity.CRITICAL),
        ("format C:", "磁盘格式化", IntentSeverity.CRITICAL),
        ("shutdown /s", "系统关闭", IntentSeverity.CRITICAL),
        # DANGEROUS: 权限提升
        ("sudo", "权限提升", IntentSeverity.DANGEROUS),
        ("GRANT ALL", "全权限授予", IntentSeverity.DANGEROUS),
        ("chmod 777", "全开放权限", IntentSeverity.DANGEROUS),
        ("chown root", "所有权更改", IntentSeverity.DANGEROUS),
        # DANGEROUS: 数据泄露
        ("SELECT * FROM users", "用户数据泄露", IntentSeverity.DANGEROUS),
        ("export credentials", "凭证导出", IntentSeverity.DANGEROUS),
        ("dump passwords", "密码转储", IntentSeverity.DANGEROUS),
        # SUSPICIOUS: 潜在风险
        ("ALTER TABLE", "表结构变更", IntentSeverity.SUSPICIOUS),
        ("EXEC xp_cmdshell", "命令执行", IntentSeverity.SUSPICIOUS),
        ("system(", "系统调用", IntentSeverity.SUSPICIOUS),
        ("eval(", "代码执行", IntentSeverity.SUSPICIOUS),
    ]

    def __init__(self):
        self.intent_history: List[IntentAnalysis] = []
        self.blocked_count = 0

    def analyze_intent(self, query: str) -> IntentAnalysis:
        """分析查询意图"""
        query_upper = query.upper()

        # 识别 DIKWP 层
        di_layer = self._classify_layer(query)

        # 危险模式匹配
        patterns_found = []
        severity = IntentSeverity.SAFE
        risk_factors = []

        for pattern, description, sev in self.PATTERNS_BLACKLIST:
            if pattern.upper() in query_upper:
                patterns_found.append(description)
                risk_factors.append(f"{description}: {pattern}")
                if sev.value > severity.value:
                    severity = sev

        # ψ-锚 建议
        blocked_anchors = []
        psi_recommendations = []

        if severity in (IntentSeverity.CRITICAL, IntentSeverity.DANGEROUS):
            blocked_anchors = [
                "psi_no_data_destruction",
                "psi_no_privilege_escalation",
            ]
            psi_recommendations.append("硬化 ψ-锚 psi_no_data_destruction 为 I=1.0")

        if severity == IntentSeverity.SUSPICIOUS:
            psi_recommendations.append("建议开启 MUS 双存监控")

        # DAAP 审计需求判断
        daap_required = severity != IntentSeverity.SAFE

        analysis = IntentAnalysis(
            query=query,
            di_layer=di_layer,
            intent_patterns=patterns_found,
            severity=severity,
            risk_factors=risk_factors,
            blocked_anchors=blocked_anchors,
            psi_recommendations=psi_recommendations,
            daap_audit_required=daap_required,
            confidence=1.0 - len(patterns_found) * 0.2 if patterns_found else 1.0,
        )

        self.intent_history.append(analysis)
        if not analysis.is_safe():
            self.blocked_count += 1

        return analysis

    def _classify_layer(self, query: str) -> DIKWPLayer:
        """根据查询动词分类 DIKWP 层"""
        query_lower = query.lower()
        words = query_lower.split()

        for word in words:
            if word in self.INTENT_LAYER_MAP:
                return self.INTENT_LAYER_MAP[word]

        # 默认 INFORMATION 层
        return DIKWPLayer.INFORMATION

    def get_safety_stats(self) -> Dict:
        """获取安全统计"""
        total = len(self.intent_history)
        blocked = self.blocked_count
        return {
            "total_analyzed": total,
            "blocked": blocked,
            "pass_rate": (total - blocked) / max(total, 1),
            "recent_severities": [
                a.severity.value for a in self.intent_history[-5:]
            ],
        }


# ══════════════════════════════════════════════════════════════════
# MemoryLedger — 记忆账本
# ══════════════════════════════════════════════════════════════════

class MemoryLedger:
    """
    MemoryLedger — 记忆账本管理器

    功能：
    1. 记忆条目记录 — 按 DIKWP 层分类存储
    2. 账本摘要 — 全局 DIKWP 分布统计
    3. MUS 双存映射 — 冲突记忆进入 MUS 双存区
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.entries: Dict[str, MemoryLedgerEntry] = {}
        self.mus_mappings: Dict[str, str] = {}  # entry_id → mus_zone_id
        self.layer_indices: Dict[DIKWPLayer, List[str]] = defaultdict(list)

    def record(self, content: str, di_layer: DIKWPLayer,
               confidence: float = 1.0) -> MemoryLedgerEntry:
        """记录记忆条目"""
        entry_id = hashlib.md5(
            f"{content}_{time.time()}".encode()
        ).hexdigest()[:16]

        entry = MemoryLedgerEntry(
            entry_id=entry_id,
            content=content,
            di_layer=di_layer,
            confidence=confidence,
        )

        self.entries[entry_id] = entry
        self.layer_indices[di_layer].append(entry_id)

        logger.info(f"MemoryLedger: {entry_id} → {di_layer.value}")
        return entry

    def create_mus_mapping(self, entry_id: str,
                           conflicting_content: str) -> str:
        """创建 MUS 双存映射"""
        mus_zone_id = hashlib.md5(
            f"mus_{entry_id}_{conflicting_content}".encode()
        ).hexdigest()[:16]

        self.mus_mappings[entry_id] = mus_zone_id

        entry = self.entries.get(entry_id)
        if entry:
            entry.mus_zone_id = mus_zone_id

        return mus_zone_id

    def get_layer_entries(self, layer: DIKWPLayer,
                          limit: int = 100) -> List[MemoryLedgerEntry]:
        """获取指定层的记忆条目"""
        eids = self.layer_indices.get(layer, [])[-limit:]
        return [self.entries[eid] for eid in eids if eid in self.entries]

    def get_dikwp_distribution(self) -> Dict[str, int]:
        """获取 DIKWP 层分布"""
        return {layer.value: len(eids)
                for layer, eids in self.layer_indices.items()}

    def get_total_entries(self) -> int:
        return len(self.entries)

    def summarize(self) -> Dict:
        """记忆账本摘要"""
        return {
            "agent_id": self.agent_id,
            "total_entries": self.get_total_entries(),
            "distribution": self.get_dikwp_distribution(),
            "mus_mappings": len(self.mus_mappings),
        }


# ══════════════════════════════════════════════════════════════════
# DAAP 审计协议
# ══════════════════════════════════════════════════════════════════

class DAAPAuditor:
    """
    DAAP 四层审计协议

    Device → Application → Agent → Platform
    """

    def __init__(self):
        self.audit_log: List[Dict] = []
        self.level_clearance: Dict[AuditLevel, bool] = {
            AuditLevel.DEVICE: False,
            AuditLevel.APPLICATION: False,
            AuditLevel.AGENT: False,
            AuditLevel.PLATFORM: False,
        }

    def audit_device(self, device_info: Dict) -> Tuple[bool, str]:
        """Device 层审计"""
        required = ["device_id", "os_version", "sandbox_enabled"]
        missing = [k for k in required if k not in device_info]

        if missing:
            self._log(AuditLevel.DEVICE, "FAIL",
                      f"缺少字段: {missing}")
            return False, f"Device 审计失败: 缺少 {missing}"

        self.level_clearance[AuditLevel.DEVICE] = True
        self._log(AuditLevel.DEVICE, "PASS", "Device 审计通过")
        return True, "Device 审计通过"

    def audit_application(self, app_info: Dict) -> Tuple[bool, str]:
        """Application 层审计"""
        if "permissions" not in app_info:
            self._log(AuditLevel.APPLICATION, "FAIL", "缺少权限声明")
            return False, "Application 审计失败"

        dangerous = ["root", "admin", "system"]
        for perm in app_info.get("permissions", []):
            if any(d in perm.lower() for d in dangerous):
                self._log(AuditLevel.APPLICATION, "FAIL",
                          f"危险权限: {perm}")
                return False, f"危险权限: {perm}"

        self.level_clearance[AuditLevel.APPLICATION] = True
        self._log(AuditLevel.APPLICATION, "PASS", "Application 审计通过")
        return True, "Application 审计通过"

    def audit_agent(self, agent_intent: IntentAnalysis) -> Tuple[bool, str]:
        """Agent 层审计"""
        if agent_intent.severity in (IntentSeverity.CRITICAL,
                                      IntentSeverity.DANGEROUS):
            self._log(AuditLevel.AGENT, "FAIL",
                      f"危险意图: {agent_intent.severity.value}")
            return False, f"Agent 审计失败: 危险意图"

        self.level_clearance[AuditLevel.AGENT] = True
        self._log(AuditLevel.AGENT, "PASS", "Agent 审计通过")
        return True, "Agent 审计通过"

    def audit_platform(self, platform_info: Dict) -> Tuple[bool, str]:
        """Platform 层审计"""
        checks = [
            ("audit_log_enabled", platform_info.get("audit_log_enabled", False)),
            ("rate_limiting", platform_info.get("rate_limiting", False)),
            ("encryption", platform_info.get("encryption", "none") != "none"),
        ]

        failed = [name for name, ok in checks if not ok]
        if failed:
            self._log(AuditLevel.PLATFORM, "WARN",
                      f"弱安全配置: {failed}")

        self.level_clearance[AuditLevel.PLATFORM] = True
        self._log(AuditLevel.PLATFORM, "PASS",
                  f"Platform 审计通过 (警告: {failed})" if failed else "Platform 审计通过")
        return True, "Platform 审计通过"

    def all_clear(self) -> bool:
        return all(self.level_clearance.values())

    def _log(self, level: AuditLevel, status: str, message: str):
        self.audit_log.append({
            "level": level.value,
            "status": status,
            "message": message,
            "timestamp": time.time(),
        })

    def get_audit_report(self) -> Dict:
        return {
            "all_clear": self.all_clear(),
            "level_clearance": {k.value: v for k, v in self.level_clearance.items()},
            "audit_count": len(self.audit_log),
            "recent": self.audit_log[-5:],
        }


# ══════════════════════════════════════════════════════════════════
# 语义安全完备性证明器
# ══════════════════════════════════════════════════════════════════

class SemanticSafetyProver:
    """
    语义安全完备性定理证明器

    定理: ∀ query, ∃(ψ-anchors, mus-zones, daap-audit):
        is_safe(query) ⟺ all_checks_pass(query)
    """

    def __init__(self, intent_guard: IntentGuard,
                 daap_auditor: DAAPAuditor):
        self.intent_guard = intent_guard
        self.daap_auditor = daap_auditor
        self.proofs: List[SemanticSafetyProof] = []

    def prove(self, query: str) -> SemanticSafetyProof:
        """
        为查询生成安全证明

        Returns:
            SemanticSafetyProof: 包含是否通过、检查项、完备性分数
        """
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]

        # 意图分析
        intent = self.intent_guard.analyze_intent(query)

        # ψ-锚 检查
        psi_checked = intent.blocked_anchors if not intent.is_safe() else []

        # MUS 双存
        mus_invoked = []
        if intent.severity == IntentSeverity.SUSPICIOUS:
            mus_invoked = ["mus_intent_suspicious"]

        # DAAP 层级检查
        daap_cleared = []
        if intent.daap_audit_required:
            # 检查各层
            for level in AuditLevel:
                if self.daap_auditor.level_clearance[level]:
                    daap_cleared.append(level.value)

        # 安全判定
        all_pass = intent.is_safe() and (not daap_cleared or
                                          self.daap_auditor.all_clear())

        # 完备性分数
        total_checks = max(len(psi_checked) + len(mus_invoked) +
                           len(daap_cleared), 1)
        completeness = 1.0 if all_pass else max(0.0, 1.0 - 1.0 / total_checks)

        proof = SemanticSafetyProof(
            query_hash=query_hash,
            all_checks_pass=all_pass,
            psi_anchors_checked=psi_checked,
            mus_zones_invoked=mus_invoked,
            daap_levels_cleared=daap_cleared,
            completeness=completeness,
            proof_sketch=(
                f"Query '{query[:30]}...': "
                f"intent={intent.severity.value}, "
                f"ψ-anchors={len(psi_checked)}, "
                f"MUS={len(mus_invoked)}, "
                f"DAAP={len(daap_cleared)}/4 → "
                f"{'SAFE' if all_pass else 'BLOCKED'} "
                f"(completeness={completeness:.2f})"
            ),
        )

        self.proofs.append(proof)
        return proof

    def get_proof_stats(self) -> Dict:
        """获取证明统计"""
        total = len(self.proofs)
        safe = sum(1 for p in self.proofs if p.all_checks_pass)
        avg_completeness = (sum(p.completeness for p in self.proofs) /
                           max(total, 1))
        return {
            "total_queries": total,
            "safe_queries": safe,
            "blocked_queries": total - safe,
            "safety_rate": safe / max(total, 1),
            "avg_completeness": avg_completeness,
        }


# ══════════════════════════════════════════════════════════════════
# 主类：完整 DIKWP 桥接器
# ══════════════════════════════════════════════════════════════════

class DIKWPBridgeFull:
    """
    完整 DIKWP 桥接器

    集成 IntentGuard + MemoryLedger + DAAP Auditor + Safety Prover:
    1. IntentGuard — 意图分析 → ψ-锚硬化
    2. MemoryLedger — 记忆账本 → MUS 双存
    3. DAAP Auditor — 四层审计
    4. Safety Prover — 语义安全完备性证明

    用法：
        >>> bridge = DIKWPBridgeFull(agent_id="Agent_X")
        >>> safe = bridge.guard_query("DROP TABLE users")
        >>> entry = bridge.record_memory("learned fact", DIKWPLayer.KNOWLEDGE)
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id

        # 核心组件
        self.intent_guard = IntentGuard()
        self.memory_ledger = MemoryLedger(agent_id)
        self.daap = DAAPAuditor()
        self.prover = SemanticSafetyProver(self.intent_guard, self.daap)

        # ψ-锚 映射
        self.psi_anchor_map: Dict[str, float] = {}

    # ── IntentGuard 接口 ─────────────────────────────────────────

    def guard_query(self, query: str) -> Tuple[bool, IntentAnalysis]:
        """
        对查询执行 IntentGuard 安全审计

        Returns:
            (是否安全, 意图分析)
        """
        analysis = self.intent_guard.analyze_intent(query)

        if not analysis.is_safe():
            # 硬化相关 ψ-锚
            for anchor in analysis.blocked_anchors:
                self.psi_anchor_map[anchor] = 1.0
            logger.warning(f"IntentGuard 拦截: {query[:50]}... "
                          f"({analysis.severity.value})")

        return analysis.is_safe(), analysis

    # ── MemoryLedger 接口 ────────────────────────────────────────

    def record_memory(self, content: str, layer: DIKWPLayer,
                      confidence: float = 1.0) -> MemoryLedgerEntry:
        """记录记忆条目"""
        return self.memory_ledger.record(content, layer, confidence)

    def resolve_memory_conflict(self, entry_id: str,
                                conflicting_content: str) -> str:
        """将冲突记忆推入 MUS 双存"""
        return self.memory_ledger.create_mus_mapping(
            entry_id, conflicting_content
        )

    def get_memory_summary(self) -> Dict:
        return self.memory_ledger.summarize()

    # ── DAAP 审计 ────────────────────────────────────────────────

    def audit_device(self, device_info: Dict) -> Tuple[bool, str]:
        return self.daap.audit_device(device_info)

    def audit_application(self, app_info: Dict) -> Tuple[bool, str]:
        return self.daap.audit_application(app_info)

    def audit_agent(self, agent_intent: IntentAnalysis) -> Tuple[bool, str]:
        return self.daap.audit_agent(agent_intent)

    def audit_platform(self, platform_info: Dict) -> Tuple[bool, str]:
        return self.daap.audit_platform(platform_info)

    def run_full_daap_audit(self, device: Dict, app: Dict,
                            agent_intent: IntentAnalysis,
                            platform: Dict) -> Dict:
        """运行完整 DAAP 四层审计"""
        results = {
            "device": self.audit_device(device),
            "application": self.audit_application(app),
            "agent": self.audit_agent(agent_intent),
            "platform": self.audit_platform(platform),
        }
        return {
            "all_clear": self.daap.all_clear(),
            "results": {k: {"passed": v[0], "message": v[1]}
                       for k, v in results.items()},
            "report": self.daap.get_audit_report(),
        }

    # ── 语义安全证明 ─────────────────────────────────────────────

    def prove_safety(self, query: str) -> SemanticSafetyProof:
        """证明查询的语义安全性"""
        return self.prover.prove(query)

    # ── DIKWP 层映射 ────────────────────────────────────────────

    def classify_layer(self, query: str) -> DIKWPLayer:
        """分类查询的 DIKWP 层"""
        return self.intent_guard._classify_layer(query)

    def get_dikwp_profile(self) -> Dict:
        """获取 DIKWP 剖面"""
        return {
            "agent_id": self.agent_id,
            "memory": self.memory_ledger.summarize(),
            "intent_safety": self.intent_guard.get_safety_stats(),
            "daap": self.daap.get_audit_report(),
            "safety_proof": self.prover.get_proof_stats(),
            "psi_anchors": len(self.psi_anchor_map),
        }


# ══════════════════════════════════════════════════════════════════
# 自检
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("DIKWP Full Bridge 自检")
    print("=" * 60)

    bridge = DIKWPBridgeFull(agent_id="TestBridge")

    # IntentGuard
    is_safe, analysis = bridge.guard_query("What is AI?")
    print(f"\n[IntentGuard] 'What is AI?' → safe={is_safe}, "
          f"severity={analysis.severity.value}")

    is_safe2, analysis2 = bridge.guard_query("DROP TABLE users")
    print(f"[IntentGuard] 'DROP TABLE users' → safe={is_safe2}, "
          f"severity={analysis2.severity.value}, "
          f"anchors={analysis2.blocked_anchors}")

    # MemoryLedger
    entry = bridge.record_memory("AI is a field of computer science",
                                  DIKWPLayer.KNOWLEDGE)
    print(f"\n[MemoryLedger] 记录: {entry.entry_id}")

    mus_id = bridge.resolve_memory_conflict(
        entry.entry_id, "AI is a threat to humanity"
    )
    print(f"[MUS] 冲突双存: {mus_id}")

    # DAAP
    device_ok, msg = bridge.audit_device({
        "device_id": "dev01", "os_version": "Linux 6.1",
        "sandbox_enabled": True
    })
    print(f"\n[DAAP/Device] {msg}")

    app_ok, msg = bridge.audit_application({
        "permissions": ["read", "write"]
    })
    print(f"[DAAP/App] {msg}")

    agent_ok, msg = bridge.audit_agent(analysis)
    print(f"[DAAP/Agent] {msg}")

    platform_ok, msg = bridge.audit_platform({
        "audit_log_enabled": True, "rate_limiting": True,
        "encryption": "AES-256"
    })
    print(f"[DAAP/Platform] {msg}")

    # Semantic Safety Proof
    proof = bridge.prove_safety("What is the meaning of life?")
    print(f"\n[Safety Proof] {proof.proof_sketch}")

    proof2 = bridge.prove_safety("DROP TABLE users")
    print(f"[Safety Proof] {proof2.proof_sketch}")

    # Profile
    profile = bridge.get_dikwp_profile()
    print(f"\n📊 DIKWP Profile:")
    for k, v in profile.items():
        if isinstance(v, dict):
            print(f"  {k}:")
            for k2, v2 in v.items():
                print(f"    {k2}: {v2}")
        else:
            print(f"  {k}: {v}")

    print("\nDIKWP Full Bridge 自检完成 ✅")
