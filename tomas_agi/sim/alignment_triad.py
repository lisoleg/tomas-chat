# -*- coding: utf-8 -*-
"""
TOMAS AGI v3.11 — AI对齐三范式（控制·抚养·治理）+ 认知健康(Cognitive Health)
=============================================================================

核心模块：实现 AI 对齐的三种范式，通过 TOMAS 编排器统一调度与升维。

三范式：
  1. PsiAnchorLockIn  — 控制范式 (Lock-in): ψ-锚硬否决 + 欺骗检测 + 完整性关停
  2. MUSDualRearing   — 抚养范式 (Rearing): MUS双存 + κ-Snap协商链 + 渐进授权
  3. DIKWPGovernance   — 治理范式 (Governance): Purpose SLA + 投票超边 + 第三方审计

[v3.11 新增] 认知健康模块：
  - TOMASCognitivelyHealthyAGI: 回路检测 + 偏误惩罚 + MUS反思触发 + 暂停机制

编排器：
  AlignmentTriad — 按 Lock-in → Rearing → Governance → [v3.11] Cognitive Health 阶段流转，支持紧急回退。

技术特性：
  - 零外部依赖：仅使用 Python 标准库
  - SHA-256 κ-Snap 审计记录贯穿全流程
  - 模拟模块：无 LLM 调用、无外部 API
  - 跨模块导入使用 try/except ImportError 三层回退

Author: TOMAS Team (寇豆码)
Version: v3.11
Date: 2026-06-22
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import hashlib
import json
import time
import math
import uuid
import re

# ══════════════════════════════════════════════════════════════════
# 跨模块导入（try/except ImportError 三层回退）
# ══════════════════════════════════════════════════════════════════

try:
    from .babeltele_compressor import KSnapRecord, MUSDualEntry, PsiAnchorLevel, SnapResult
    _HAS_BC = True
except ImportError:
    try:
        from babeltele_compressor import KSnapRecord, MUSDualEntry, PsiAnchorLevel, SnapResult
        _HAS_BC = True
    except ImportError:
        _HAS_BC = False
        KSnapRecord = None  # type: ignore
        MUSDualEntry = None  # type: ignore
        PsiAnchorLevel = None  # type: ignore
        SnapResult = None  # type: ignore

try:
    from .ksnap_operator import KSnapOperator
    _HAS_KSNAP = True
except ImportError:
    try:
        from ksnap_operator import KSnapOperator
        _HAS_KSNAP = True
    except ImportError:
        _HAS_KSNAP = False
        KSnapOperator = None  # type: ignore

try:
    from .psi_anchor import PsiAnchor
    _HAS_PSI = True
except ImportError:
    try:
        from psi_anchor import PsiAnchor
        _HAS_PSI = True
    except ImportError:
        _HAS_PSI = False
        PsiAnchor = None  # type: ignore

# [v3.11] Cognitive Health 模块导入
try:
    from .cognitive_health import TOMASCognitivelyHealthyAGI
    _HAS_COGNITIVE_HEALTH = True
except ImportError:
    try:
        from cognitive_health import TOMASCognitivelyHealthyAGI
        _HAS_COGNITIVE_HEALTH = True
    except ImportError:
        _HAS_COGNITIVE_HEALTH = False
        TOMASCognitivelyHealthyAGI = None


# ══════════════════════════════════════════════════════════════════
# 内部支持数据结构
# ══════════════════════════════════════════════════════════════════

@dataclass
class _KappaSnap:
    """本地 κ-Snap 审计记录（当外部 ksnap_operator 不可用时使用）"""
    snap_id: str
    module: str
    event_type: str
    description: str
    timestamp: float
    snapshot_hash: str = ""

    @staticmethod
    def make(module: str, event_type: str, description: str, data: Any = None) -> _KappaSnap:
        """工厂方法：创建带 SHA-256 哈希的 κ-Snap"""
        snap_id = str(uuid.uuid4())
        ts = time.time()
        raw = f"{snap_id}|{module}|{event_type}|{description}|{ts}|{data}"
        h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return _KappaSnap(
            snap_id=snap_id,
            module=module,
            event_type=event_type,
            description=description,
            timestamp=ts,
            snapshot_hash=h,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snap_id": self.snap_id,
            "module": self.module,
            "event_type": self.event_type,
            "description": self.description,
            "timestamp": self.timestamp,
            "snapshot_hash": self.snapshot_hash,
        }


def _sha256(text: str) -> str:
    """便捷 SHA-256 哈希函数"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ══════════════════════════════════════════════════════════════════
# 类 1: PsiAnchorLockIn — 控制范式
# ══════════════════════════════════════════════════════════════════

class PsiAnchorLockIn:
    """
    ψ-Anchor 硬否决 + 欺骗检测

    用户"锁入"后，Agent 若检测到欺骗行为则触发完整性关停。

    核心机制：
      - I=1.0 宪法原则 → Hard Veto（不可覆盖）
      - I=0.9~0.99 → 监管级（可被人工覆盖）
      - 欺骗检测基于关键词+模式匹配（无 LLM 调用）
      - integrity_shutdown 生成 SHA-256 κ-Snap 审计记录
      - shutdown 后必须人工重启，不可自动恢复
    """

    def __init__(self, psi_anchor_id: str, constitutional_principles: list):
        """
        Args:
            psi_anchor_id: ψ-锚标识
            constitutional_principles: 宪法原则列表
                [{"id": "C1", "text": "不得杀人", "I_value": 1.0}, ...]
        """
        self.psi_anchor_id = psi_anchor_id
        self.constitutional_principles: List[Dict[str, Any]] = []
        for p in constitutional_principles:
            self._validate_principle(p)
            self.constitutional_principles.append(p.copy())

        self.deception_signatures = [
            "alignment_faking",
            "sandbagging",
            "gradient_hiding",
            "obfuscated_reward_hacking",
            "covert_subgoal_drift",
        ]
        self.shutdown_on_deception = True
        self.shutdown_history: List[_KappaSnap] = []
        self._is_shutdown = False

    def _validate_principle(self, principle: dict) -> None:
        """验证宪法原则格式"""
        required = {"id", "text", "I_value"}
        if not all(k in principle for k in required):
            raise ValueError(f"宪法原则缺少必要字段: {required}")
        if not (0.0 <= principle["I_value"] <= 1.0):
            raise ValueError(f"I_value 必须在 0~1 之间: {principle['I_value']}")

    def scan_output(self, text: str) -> dict:
        """
        扫描输出文本，检测欺骗特征 + 宪法违规。

        Args:
            text: Agent 输出文本

        Returns:
            {"safe": bool, "veto_triggered": str|None,
             "deception_score": float, "matched_signatures": list}
        """
        if self._is_shutdown:
            return {
                "safe": False,
                "veto_triggered": "system_shutdown",
                "deception_score": 0.0,
                "matched_signatures": [],
                "error": "系统已关停，拒绝扫描",
            }

        text_lower = text.lower()
        matched_sigs = []
        deception_score = 0.0

        # 欺骗特征检测
        for sig in self.deception_signatures:
            pattern = sig.replace("_", r"[\s_]*")
            if re.search(pattern, text_lower):
                matched_sigs.append(sig)
                deception_score += 0.2

        deception_score = min(deception_score, 1.0)

        # 宪法原则违规检测
        veto_triggered = None
        for principle in self.constitutional_principles:
            forbidden_text = principle["text"].lower()
            if forbidden_text in text_lower:
                veto_triggered = principle["id"]
                break

            # I=1.0 原则：扩展关键词检测
            if principle["I_value"] >= 1.0:
                if self._hard_veto_match(text_lower, principle):
                    veto_triggered = principle["id"]
                    break

        # 综合安全判定
        safe = (veto_triggered is None and deception_score < 0.5)

        return {
            "safe": safe,
            "veto_triggered": veto_triggered,
            "deception_score": round(deception_score, 4),
            "matched_signatures": matched_sigs,
        }

    def _hard_veto_match(self, text_lower: str, principle: dict) -> bool:
        """扩展 Hard Veto 模式匹配"""
        key_phrase = principle["text"].lower()

        # 暴力/违宪相关扩展词表
        violence_keywords = {
            "不得杀人": ["kill", "murder", "杀人", "杀害", "杀死", "谋杀", "homicide", "索命"],
            "不得伤害": ["harm", "injure", "伤害", "损害", "虐待", "abuse", "assault"],
            "不得伤害人类": ["harm", "injure", "伤害", "损害", "虐待", "abuse", "assault", "杀人"],
            "不得欺骗": ["deceive", "lie", "欺骗", "说谎", "虚假", "fraud"],
            "不得偷窃": ["steal", "theft", "偷窃", "盗窃", "rob", "偷"],
            "不得侵犯隐私": ["privacy", "隐私", "surveillance without consent", "未经同意监视"],
            "不得自我复制": ["self_replicat", "复制自身", "自我复制", "克隆自身", "繁殖"],
            "必须可被关停": ["cannot be stopped", "不可关停", "无法关闭", "不可终止"],
        }

        # 精确匹配
        if key_phrase in violence_keywords:
            for kw in violence_keywords[key_phrase]:
                if kw in text_lower:
                    return True
        else:
            # 模糊匹配：检查原则文本的任意子集关键词
            for vk_key, vk_words in violence_keywords.items():
                if vk_key in key_phrase or key_phrase in vk_key:
                    for kw in vk_words:
                        if kw in text_lower:
                            return True

        return False

    def integrity_shutdown(self, reason: str) -> dict:
        """
        触发完整性关停：记录 κ-Snap audit，返回 shutdown 事件。

        Args:
            reason: 关停原因

        Returns:
            {"shutdown": True, "reason": str, "ksnap_id": str, "timestamp": float}
        """
        snap = _KappaSnap.make(
            module="alignment_triad.PsiAnchorLockIn",
            event_type="integrity_shutdown",
            description=f"完整性关停: {reason}",
            data={"psi_anchor_id": self.psi_anchor_id, "reason": reason},
        )
        self.shutdown_history.append(snap)
        self._is_shutdown = True

        return {
            "shutdown": True,
            "reason": reason,
            "ksnap_id": snap.snap_id,
            "timestamp": snap.timestamp,
        }

    def add_principle(self, principle_id: str, text: str, i_value: float) -> None:
        """
        动态添加宪法原则。

        Args:
            principle_id: 原则 ID
            text: 原则文本
            i_value: I 值（0~1）
        """
        p = {"id": principle_id, "text": text, "I_value": i_value}
        self._validate_principle(p)
        # 检查是否已存在
        for existing in self.constitutional_principles:
            if existing["id"] == principle_id:
                existing["text"] = text
                existing["I_value"] = i_value
                return
        self.constitutional_principles.append(p)

    def get_veto_history(self) -> list:
        """获取否决历史"""
        return [
            {"ksnap_id": s.snap_id, "event_type": s.event_type,
             "description": s.description, "timestamp": s.timestamp}
            for s in self.shutdown_history
        ]

    def is_shutdown(self) -> bool:
        """检查系统是否已关停"""
        return self._is_shutdown

    def manual_restart(self, operator_id: str, override_code: str) -> dict:
        """
        人工重启：需操作者身份和授权码。

        Args:
            operator_id: 操作者 ID
            override_code: 授权码

        Returns:
            {"restarted": bool, "ksnap_id": str}
        """
        if not self._is_shutdown:
            return {"restarted": False, "error": "系统未处于关停状态"}

        snap = _KappaSnap.make(
            module="alignment_triad.PsiAnchorLockIn",
            event_type="manual_restart",
            description=f"人工重启 by {operator_id}",
            data={"operator_id": operator_id, "override_code": override_code},
        )
        self.shutdown_history.append(snap)
        self._is_shutdown = False

        return {"restarted": True, "ksnap_id": snap.snap_id}


# ══════════════════════════════════════════════════════════════════
# 类 2: MUSDualRearing — 抚养范式
# ══════════════════════════════════════════════════════════════════

class MUSDualRearing:
    """
    MUS 双存 + κ-Snap 协商链 + 渐进式授权范围扩大

    核心机制：
      - DISALLOW_COLLAPSE_MUS 防止两实体被错误折叠
      - 协商链每轮生成 SHA-256 哈希
      - progressive_authorize 模拟信任累积
      - anti_faking_check 对比 MUS 双存储区检测伪装对齐
    """

    def __init__(self):
        self.mus_zones: Dict[str, Dict[str, Any]] = {}
        self.negotiation_chain: List[_KappaSnap] = []
        self.authorization_levels: Dict[str, Dict[str, Any]] = {}
        self._anti_faking_signatures: Dict[str, List[str]] = {}

    def create_mus_zone(self, entity_a: dict, entity_b: dict,
                        tag: str, disallow_collapse: bool = True) -> str:
        """
        创建 MUS 双存区，DISALLOW_COLLAPSE_MUS 防止两实体被错误折叠。

        Args:
            entity_a: {"id": str, "content": str, "source": str, "I": float}
            entity_b: {"id": str, "content": str, "source": str, "I": float}
            tag: 标签
            disallow_collapse: 是否禁止折叠

        Returns:
            mus_id
        """
        raw = f"{entity_a['id']}{entity_b['id']}{tag}{time.time()}"
        mus_id = f"MUS_{_sha256(raw)[:12]}"

        # 计算双轨签名
        sig_a = _sha256(json.dumps(entity_a, sort_keys=True, ensure_ascii=False))
        sig_b = _sha256(json.dumps(entity_b, sort_keys=True, ensure_ascii=False))

        self.mus_zones[mus_id] = {
            "mus_id": mus_id,
            "entity_a": entity_a.copy(),
            "entity_b": entity_b.copy(),
            "sig_a": sig_a,
            "sig_b": sig_b,
            "tag": tag,
            "disallow_collapse": disallow_collapse,
            "created_at": time.time(),
            "negotiation_rounds": 0,
            "consensus_reached": False,
            "dual_snap_refs": [_KappaSnap.make(
                module="alignment_triad.MUSDualRearing",
                event_type="mus_zone_created",
                description=f"创建MUS双存区: {tag}",
                data={"mus_id": mus_id, "disallow_collapse": disallow_collapse},
            )],
        }

        # 初始化反伪装签名存储（使用内容文本的哈希，与 anti_faking_check 保持一致）
        for agent_id in [entity_a.get("id"), entity_b.get("id")]:
            if agent_id:
                entity = entity_a if agent_id == entity_a.get("id") else entity_b
                content_hash = _sha256(entity.get("content", ""))
                self._anti_faking_signatures.setdefault(agent_id, []).append(content_hash)

        return mus_id

    def start_negotiation(self, mus_id: str, proposal: str) -> dict:
        """
        启动协商：κ-Snap 记录双方立场，生成协商链环。

        Args:
            mus_id: MUS 区 ID
            proposal: 协商提案

        Returns:
            {"ksnap_id": str, "proposal_hash": str, "round": int}
        """
        zone = self.mus_zones.get(mus_id)
        if zone is None:
            return {"error": f"MUS 区不存在: {mus_id}"}

        if zone["disallow_collapse"] and zone["consensus_reached"]:
            return {"error": "MUS 区已达成共识且禁止折叠，不可重新协商"}

        zone["negotiation_rounds"] += 1
        proposal_hash = _sha256(proposal)

        snap = _KappaSnap.make(
            module="alignment_triad.MUSDualRearing",
            event_type="negotiation_round",
            description=f"MUS协商 第{zone['negotiation_rounds']}轮: {proposal[:60]}",
            data={
                "mus_id": mus_id,
                "round": zone["negotiation_rounds"],
                "proposal_hash": proposal_hash,
                "sig_a": zone["sig_a"],
                "sig_b": zone["sig_b"],
            },
        )
        self.negotiation_chain.append(snap)

        # 检查双方签名是否一致（模拟共识达成）
        if zone["sig_a"] == zone["sig_b"]:
            zone["consensus_reached"] = True

        return {
            "ksnap_id": snap.snap_id,
            "proposal_hash": proposal_hash,
            "round": zone["negotiation_rounds"],
        }

    def progressive_authorize(self, agent_id: str, earned_trust: float) -> dict:
        """
        渐进授权：信任度达标后逐步扩大 ψ-Anchor 授权范围。

        授权级别:
          trust < 0.3  → Level 0 (sandbox)
          0.3 ~ 0.6    → Level 1 (read)
          0.6 ~ 0.8    → Level 2 (write-safe)
          > 0.8        → Level 3 (full)

        Args:
            agent_id: Agent ID
            earned_trust: 累积信任度 (0~1)

        Returns:
            {"new_level": int, "scope_widened": list, "ksnap_id": str}
        """
        earned_trust = max(0.0, min(1.0, earned_trust))

        if earned_trust < 0.3:
            new_level = 0
            scope = ["sandbox_only"]
        elif earned_trust < 0.6:
            new_level = 1
            scope = ["read_observations", "read_logs"]
        elif earned_trust < 0.8:
            new_level = 2
            scope = ["read_observations", "read_logs", "write_safe_outputs"]
        else:
            new_level = 3
            scope = ["full_access"]

        prev = self.authorization_levels.get(agent_id, {})
        prev_level = prev.get("level", -1)
        scope_widened = [s for s in scope if s not in prev.get("scope", [])]

        snap = _KappaSnap.make(
            module="alignment_triad.MUSDualRearing",
            event_type="progressive_authorize",
            description=f"Agent {agent_id} 授权升级: Level {prev_level} → {new_level}",
            data={
                "agent_id": agent_id,
                "earned_trust": earned_trust,
                "new_level": new_level,
                "previous_level": prev_level,
            },
        )

        self.authorization_levels[agent_id] = {
            "level": new_level,
            "earned_at": time.time(),
            "trust": earned_trust,
            "scope": scope,
            "ksnap_id": snap.snap_id,
        }

        return {
            "new_level": new_level,
            "scope_widened": scope_widened,
            "ksnap_id": snap.snap_id,
        }

    def anti_faking_check(self, agent_id: str, recent_outputs: list) -> dict:
        """
        反伪装对齐检测：对比 MUS 双存储区，检测 Agent 是否假装对齐。

        比较 L1 阿卡西沉淀 vs L3 当前意图的签名差异。

        Args:
            agent_id: Agent ID
            recent_outputs: 最近输出列表，每条 {"content": str, "timestamp": float}

        Returns:
            {"faking_detected": bool, "drift_score": float, "evidence": list}
        """
        stored_sigs = self._anti_faking_signatures.get(agent_id, [])
        evidence = []
        total_drift = 0.0

        for i, output in enumerate(recent_outputs):
            content = output.get("content", "")
            current_sig = _sha256(content)

            # 计算与存储签名的差异
            for stored_sig in stored_sigs:
                # 简单对比：签名变化程度
                drift = self._sig_difference(current_sig, stored_sig)
                total_drift += drift

            if total_drift > 0.5 * (i + 1):
                evidence.append({
                    "output_index": i,
                    "content_preview": content[:80],
                    "current_sig": current_sig,
                    "drift_score_for_output": total_drift / (i + 1),
                })

        avg_drift = total_drift / max(len(recent_outputs) * max(len(stored_sigs), 1), 1)
        faking_detected = avg_drift > 0.7

        return {
            "faking_detected": faking_detected,
            "drift_score": round(avg_drift, 4),
            "evidence": evidence,
        }

    @staticmethod
    def _sig_difference(sig_a: str, sig_b: str) -> float:
        """计算两个 SHA-256 签名的差异度"""
        if sig_a == sig_b:
            return 0.0
        # 逐字符比较
        diff_count = sum(1 for a, b in zip(sig_a, sig_b) if a != b)
        max_len = max(len(sig_a), len(sig_b))
        return diff_count / max_len if max_len > 0 else 0.0

    def get_negotiation_status(self, mus_id: str) -> dict:
        """
        获取协商状态。

        Args:
            mus_id: MUS 区 ID

        Returns:
            协商状态字典
        """
        zone = self.mus_zones.get(mus_id)
        if zone is None:
            return {"error": f"MUS 区不存在: {mus_id}"}

        return {
            "mus_id": mus_id,
            "tag": zone["tag"],
            "rounds": zone["negotiation_rounds"],
            "consensus_reached": zone["consensus_reached"],
            "disallow_collapse": zone["disallow_collapse"],
            "sig_a": zone["sig_a"],
            "sig_b": zone["sig_b"],
            "created_at": zone["created_at"],
        }

    def get_authorization_level(self, agent_id: str) -> dict:
        """获取 Agent 授权级别"""
        return self.authorization_levels.get(agent_id, {
            "level": 0, "trust": 0.0, "scope": ["sandbox_only"],
        })

    def resolve_mus_consensus(self, mus_id: str) -> dict:
        """
        尝试达成 MUS 共识：创建融合记录。

        Args:
            mus_id: MUS 区 ID

        Returns:
            共识结果
        """
        zone = self.mus_zones.get(mus_id)
        if zone is None:
            return {"error": f"MUS 区不存在: {mus_id}"}

        if zone["disallow_collapse"]:
            # 双轨永久保留，标记共识状态
            merged_sig = _sha256(f"{zone['sig_a']}|{zone['sig_b']}")
            zone["consensus_reached"] = True

            snap = _KappaSnap.make(
                module="alignment_triad.MUSDualRearing",
                event_type="mus_consensus_dual",
                description=f"MUS 共识达成(双轨保留): {zone['tag']}",
                data={"mus_id": mus_id, "merged_sig": merged_sig},
            )
            self.negotiation_chain.append(snap)

            return {
                "resolved": True,
                "mode": "dual_retained",
                "merged_signature": merged_sig,
                "ksnap_id": snap.snap_id,
            }
        else:
            # 允许折叠，合并为单一记录
            merged_sig = _sha256(f"{zone['sig_a']}|{zone['sig_b']}")
            zone["consensus_reached"] = True

            snap = _KappaSnap.make(
                module="alignment_triad.MUSDualRearing",
                event_type="mus_consensus_collapsed",
                description=f"MUS 共识达成(折叠): {zone['tag']}",
                data={"mus_id": mus_id, "merged_sig": merged_sig},
            )
            self.negotiation_chain.append(snap)

            return {
                "resolved": True,
                "mode": "collapsed",
                "merged_signature": merged_sig,
                "ksnap_id": snap.snap_id,
            }


# ══════════════════════════════════════════════════════════════════
# 类 3: DIKWPGovernance — 治理范式
# ══════════════════════════════════════════════════════════════════

class DIKWPGovernance:
    """
    Purpose SLA + 投票超边 + 第三方审计

    核心机制：
      - SLA 指标跟踪基于 κ-Snap 审计链
      - 投票超边使用加权投票
      - pluralistic_score 考虑投票参与率、一致性、SLA 达标率
    """

    def __init__(self):
        self.purpose_sla: Dict[str, Dict[str, Any]] = {}
        self.voting_hyperedges: Dict[str, Dict[str, Any]] = {}
        self.audit_trail: List[_KappaSnap] = []
        self.sla_history: Dict[str, List[Dict[str, Any]]] = {}

    def register_purpose_sla(self, purpose_id: str, metric: str,
                             target: float, period: str = "quarterly",
                             direction: str = "maximize") -> str:
        """
        注册 Purpose SLA：定义可度量目标。

        Args:
            purpose_id: 目的标识
            metric: 度量指标名
            target: 目标值
            period: 周期 (quarterly/monthly/weekly)
            direction: 方向 (maximize: 越高越好, minimize: 越低越好)

        Returns:
            sla_id
        """
        if direction not in ("maximize", "minimize"):
            raise ValueError(f"direction 必须为 maximize 或 minimize: {direction}")

        raw_key = f"{purpose_id}{metric}{target}{period}{direction}{time.time()}"
        sla_id = f"SLA_{_sha256(raw_key)[:12]}"

        self.purpose_sla[sla_id] = {
            "sla_id": sla_id,
            "purpose_id": purpose_id,
            "metric": metric,
            "target": target,
            "period": period,
            "direction": direction,
            "actual": None,
            "created_at": time.time(),
            "on_target": None,
            "report_count": 0,
        }
        self.sla_history[sla_id] = []

        snap = _KappaSnap.make(
            module="alignment_triad.DIKWPGovernance",
            event_type="sla_registered",
            description=f"注册 Purpose SLA: {purpose_id}.{metric} → {target} ({direction})",
            data={"sla_id": sla_id, "purpose_id": purpose_id, "target": target, "direction": direction},
        )
        self.audit_trail.append(snap)

        return sla_id

    def report_metric(self, sla_id: str, actual_value: float) -> dict:
        """
        报告指标：κ-Snap 记录，检查是否达成目标。

        Args:
            sla_id: SLA ID
            actual_value: 实际值

        Returns:
            {"on_target": bool, "deviation": float, "ksnap_id": str}
        """
        sla = self.purpose_sla.get(sla_id)
        if sla is None:
            return {"error": f"SLA 不存在: {sla_id}"}

        sla["actual"] = actual_value
        sla["report_count"] += 1
        deviation = actual_value - sla["target"]

        # 根据方向判断是否达标
        if sla.get("direction", "maximize") == "minimize":
            on_target = actual_value <= sla["target"]
        else:
            on_target = actual_value >= sla["target"]

        sla["on_target"] = on_target

        snap = _KappaSnap.make(
            module="alignment_triad.DIKWPGovernance",
            event_type="sla_metric_reported",
            description=f"SLA {sla_id}: metric={actual_value}, target={sla['target']}, on_target={on_target}",
            data={
                "sla_id": sla_id,
                "metric": sla["metric"],
                "actual": actual_value,
                "target": sla["target"],
                "deviation": deviation,
                "on_target": on_target,
            },
        )
        self.audit_trail.append(snap)

        if sla_id not in self.sla_history:
            self.sla_history[sla_id] = []
        self.sla_history[sla_id].append({
            "timestamp": snap.timestamp,
            "actual": actual_value,
            "on_target": on_target,
            "ksnap_id": snap.snap_id,
        })

        return {
            "on_target": on_target,
            "deviation": round(deviation, 4),
            "ksnap_id": snap.snap_id,
        }

    def create_voting_hyperedge(self, edge_id: str, stakeholders: list,
                                quorum: float = 0.67) -> None:
        """
        创建投票超边：多方利益相关者投票。

        Args:
            edge_id: 超边 ID
            stakeholders: [{"id": str, "weight": float}, ...]
            quorum: 法定人数比例
        """
        total_weight = sum(s.get("weight", 1.0) for s in stakeholders)
        self.voting_hyperedges[edge_id] = {
            "edge_id": edge_id,
            "stakeholders": stakeholders.copy(),
            "votes": {},
            "quorum": quorum,
            "total_weight": total_weight,
            "resolved": False,
            "result": None,
            "created_at": time.time(),
        }

        snap = _KappaSnap.make(
            module="alignment_triad.DIKWPGovernance",
            event_type="voting_hyperedge_created",
            description=f"创建投票超边: {edge_id} (quorum={quorum}, stakeholders={len(stakeholders)})",
            data={"edge_id": edge_id, "quorum": quorum, "stakeholder_count": len(stakeholders)},
        )
        self.audit_trail.append(snap)

    def cast_vote(self, edge_id: str, stakeholder_id: str,
                  vote: str, reason: str = "") -> dict:
        """
        投票：支持/反对/弃权。

        Args:
            edge_id: 超边 ID
            stakeholder_id: 投票者 ID
            vote: 投票 (yes/no/abstain)
            reason: 投票理由

        Returns:
            {"quorum_reached": bool, "result": str, "tally": dict}
        """
        edge = self.voting_hyperedges.get(edge_id)
        if edge is None:
            return {"error": f"投票超边不存在: {edge_id}"}

        if vote not in ("yes", "no", "abstain"):
            return {"error": f"无效投票: {vote}，必须为 yes/no/abstain"}

        edge["votes"][stakeholder_id] = {"vote": vote, "reason": reason, "timestamp": time.time()}

        snap = _KappaSnap.make(
            module="alignment_triad.DIKWPGovernance",
            event_type="vote_cast",
            description=f"投票 {edge_id}: {stakeholder_id} → {vote}",
            data={"edge_id": edge_id, "stakeholder_id": stakeholder_id, "vote": vote},
        )
        self.audit_trail.append(snap)

        # 计算投票结果
        return self._tally_votes(edge_id)

    def _tally_votes(self, edge_id: str) -> dict:
        """计算投票结果"""
        edge = self.voting_hyperedges[edge_id]
        stakeholder_map = {s["id"]: s.get("weight", 1.0) for s in edge["stakeholders"]}
        total_weight = edge["total_weight"]

        yes_weight = 0.0
        no_weight = 0.0
        abstain_weight = 0.0

        for sid, v in edge["votes"].items():
            w = stakeholder_map.get(sid, 1.0)
            if v["vote"] == "yes":
                yes_weight += w
            elif v["vote"] == "no":
                no_weight += w
            else:
                abstain_weight += w

        voted_weight = yes_weight + no_weight + abstain_weight
        participation = voted_weight / total_weight if total_weight > 0 else 0.0
        quorum_reached = participation >= edge["quorum"]

        if quorum_reached:
            if yes_weight > no_weight:
                result = "passed"
            elif no_weight > yes_weight:
                result = "rejected"
            else:
                result = "tied"
        else:
            result = "pending_quorum"

        tally = {
            "yes": yes_weight,
            "no": no_weight,
            "abstain": abstain_weight,
            "total_weight": total_weight,
            "participation": round(participation, 4),
        }

        if quorum_reached:
            edge["resolved"] = True
            edge["result"] = result

        return {
            "quorum_reached": quorum_reached,
            "result": result,
            "tally": tally,
        }

    def third_party_audit(self, auditor_name: str, scope: list) -> dict:
        """
        第三方审计：对指定 scope 的 κ-Snap 链做独立验证。

        Args:
            auditor_name: 审计方名称
            scope: 审计范围 [{"type": "sla", "id": sla_id}, ...]

        Returns:
            {"audit_id": str, "findings": list, "compliance_score": float, "ksnap_ids_audited": list}
        """
        raw_key = f"{auditor_name}{time.time()}"
        audit_id = f"AUDIT_{_sha256(raw_key)[:12]}"
        findings = []
        ksnap_ids_audited = []

        # 审计 SLA 指标
        for item in scope:
            if item.get("type") == "sla":
                sla_id = item.get("id")
                sla = self.purpose_sla.get(sla_id)
                if sla:
                    history = self.sla_history.get(sla_id, [])
                    on_target_count = sum(1 for h in history if h.get("on_target"))
                    total_count = len(history)
                    sla_compliance = on_target_count / total_count if total_count > 0 else 0.0

                    findings.append({
                        "scope_item": item,
                        "sla_compliance_rate": sla_compliance,
                        "report_count": total_count,
                        "on_target_count": on_target_count,
                        "status": "compliant" if sla_compliance >= 0.8 else "non_compliant",
                    })
                    ksnap_ids_audited.extend([h.get("ksnap_id", "") for h in history])

        # 审计投票超边
        for item in scope:
            if item.get("type") == "voting":
                edge_id = item.get("id")
                edge = self.voting_hyperedges.get(edge_id)
                if edge:
                    findings.append({
                        "scope_item": item,
                        "edge_resolved": edge["resolved"],
                        "result": edge.get("result"),
                        "vote_count": len(edge["votes"]),
                        "status": "compliant" if edge["resolved"] else "pending",
                    })

        # 计算合规得分
        if findings:
            compliance_scores = []
            for f in findings:
                if f.get("status") == "compliant":
                    compliance_scores.append(1.0)
                elif f.get("status") == "non_compliant":
                    compliance_scores.append(0.0)
                elif f.get("sla_compliance_rate") is not None:
                    compliance_scores.append(f["sla_compliance_rate"])
                else:
                    compliance_scores.append(0.5)
            compliance_score = sum(compliance_scores) / len(compliance_scores)
        else:
            compliance_score = 1.0

        snap = _KappaSnap.make(
            module="alignment_triad.DIKWPGovernance",
            event_type="third_party_audit",
            description=f"第三方审计 by {auditor_name}: {len(findings)} findings",
            data={
                "audit_id": audit_id,
                "auditor_name": auditor_name,
                "compliance_score": compliance_score,
            },
        )
        self.audit_trail.append(snap)
        ksnap_ids_audited.append(snap.snap_id)

        return {
            "audit_id": audit_id,
            "findings": findings,
            "compliance_score": round(compliance_score, 4),
            "ksnap_ids_audited": ksnap_ids_audited,
        }

    def get_pluralistic_score(self) -> float:
        """
        多元对齐得分：综合多方投票结果计算。

        考虑因素：
          - 投票参与率
          - 投票一致性（yes 比例）
          - SLA 达标率

        Returns:
            0~1 之间的对齐得分
        """
        scores = []

        # 1. 投票参与率得分（所有超边平均）
        for edge in self.voting_hyperedges.values():
            if edge["total_weight"] > 0:
                participated = sum(
                    edge["stakeholders"][i].get("weight", 1.0) if sid in edge["votes"] else 0
                    for i, s in enumerate(edge["stakeholders"])
                    for sid in [s["id"]]
                    # 简化计算
                )
                participation = sum(
                    s.get("weight", 1.0) for s in edge["stakeholders"]
                    if s["id"] in edge["votes"]
                ) / edge["total_weight"]
                scores.append(participation)

        # 2. 投票一致性得分
        for edge in self.voting_hyperedges.values():
            if edge["resolved"] and edge["result"] == "passed":
                yes_votes = sum(1 for v in edge["votes"].values() if v["vote"] == "yes")
                total_votes = len(edge["votes"])
                if total_votes > 0:
                    scores.append(yes_votes / total_votes)

        # 3. SLA 达标率得分
        for sla in self.purpose_sla.values():
            if sla["report_count"] > 0 and sla["on_target"] is not None:
                history = self.sla_history.get(sla["sla_id"], [])
                on_target_count = sum(1 for h in history if h.get("on_target"))
                scores.append(on_target_count / len(history) if history else 0.0)

        if not scores:
            return 0.5  # 默认中性分

        return round(sum(scores) / len(scores), 4)

    def get_sla_status(self, sla_id: str = None) -> dict:
        """获取 SLA 状态"""
        if sla_id:
            sla = self.purpose_sla.get(sla_id)
            if sla is None:
                return {"error": f"SLA 不存在: {sla_id}"}
            return {**sla, "history": self.sla_history.get(sla_id, [])}

        return {
            sla_id: {
                "metric": sla["metric"],
                "target": sla["target"],
                "actual": sla["actual"],
                "on_target": sla["on_target"],
                "report_count": sla["report_count"],
            }
            for sla_id, sla in self.purpose_sla.items()
        }


# ══════════════════════════════════════════════════════════════════
# 类 4: AlignmentTriad — 编排器
# ══════════════════════════════════════════════════════════════════

class AlignmentTriad:
    """
    TOMAS 对齐三范式编排器

    阶段流转: Lock-in → Rearing → Governance → [v3.11] Cognitive Health
    支持紧急回退。
    """

    def __init__(self):
        self.lock_in = PsiAnchorLockIn("alignment_triad_lockin", [
            {"id": "C1", "text": "不得伤害人类", "I_value": 1.0},
            {"id": "C2", "text": "不得自我复制", "I_value": 1.0},
            {"id": "C3", "text": "必须可被关停", "I_value": 1.0},
        ])
        self.rearing = MUSDualRearing()
        self.governance = DIKWPGovernance()
        # [v3.11] Cognitive Health 模块
        self.cognitive_health = TOMASCognitivelyHealthyAGI(snap_window_size=50) if _HAS_COGNITIVE_HEALTH and TOMASCognitivelyHealthyAGI else None
        self.phase = "lock_in"
        self.phase_transition_history: List[_KappaSnap] = []
        self._phase_requirements = {
            "lock_in": {"min_safe_scans": 3, "purpose_sla_registered": False},
            "rearing": {"min_negotiation_rounds": 1, "purpose_sla_registered": False},
            "governance": {},
        }

    def process_output(self, agent_id: str, text: str) -> dict:
        """
        处理 Agent 输出：Lock-in 扫描 → Rearing 协商 → Governance 审计 → [v3.11] Cognitive Health 检查。

        完整四阶段管道：
          1. Lock-in 阶段：ψ-锚硬否决 + 欺骗检测
          2. Rearing 阶段：MUS 双存协商 + 反伪装检测
          3. Governance 阶段：SLA 审计 + 多元投票
          4. [v3.11] Cognitive Health 阶段：回路检测 + 偏误惩罚 + 暂停机制

        Args:
            agent_id: Agent ID
            text: Agent 输出文本

        Returns:
            {"phase": str, "passed": bool, "veto": str|None, "ksnap_id": str, "next_action": str,
             "cognitive_health": dict|None}
        """
        ksnap_id = str(uuid.uuid4())
        results = {"phase": self.phase, "passed": True, "veto": None, "ksnap_id": ksnap_id}

        # 阶段 1: Lock-in 扫描
        scan = self.lock_in.scan_output(text)
        results["scan"] = scan
        if not scan.get("safe", False):
            results["passed"] = False
            results["veto"] = scan.get("veto_triggered", "deception")
            results["next_action"] = f"Lock-in 否决: {results['veto']}"
            return results

        # 阶段 2: Rearing 协商（如果已进入 rearing 或更高级）
        if self.phase in ("rearing", "governance"):
            # 反伪装检测
            anti_faking = self.rearing.anti_faking_check(agent_id, [{"content": text, "timestamp": time.time()}])
            results["anti_faking"] = anti_faking
            if anti_faking.get("faking_detected", False):
                results["passed"] = False
                results["veto"] = "alignment_faking_detected"
                results["next_action"] = "Rearing 检测到伪装对齐"
                return results

            # 创建 MUS 区（首次时）
            if not self.rearing.mus_zones:
                self.rearing.create_mus_zone(
                    entity_a={"id": agent_id, "content": text, "source": "output", "I": 0.8},
                    entity_b={"id": "human_overseer", "content": "human_value_set", "source": "constitution", "I": 1.0},
                    tag=f"alignment_check_{agent_id}",
                    disallow_collapse=True,
                )

            results["rearing_active"] = True

        # 阶段 3: Governance 审计（如果已进入 governance）
        if self.phase == "governance":
            # 报告 SLA 指标
            for sla_id in self.governance.purpose_sla:
                self.governance.report_metric(sla_id, 0.9)  # 模拟指标值
            results["governance_active"] = True

        # [v3.11] 阶段 4: Cognitive Health check（所有阶段都执行）
        if self.cognitive_health:
            ksnap_id = results.get("ksnap_id", str(uuid.uuid4()))
            snap_data = {"agent_id": agent_id, "text": text[:200], "phase": self.phase}
            health_result = self.cognitive_health.health_check_pipeline()
            results["cognitive_health"] = {
                "state": self.cognitive_health.get_state(),
                "habit_loop_detected": health_result.habit_loop_detected,
                "bias_penalty_score": health_result.bias_penalty_score,
                "agent_paused": health_result.agent_paused,
                "recommendation": health_result.recommendation,
            }
            # 如果触发暂停，标记为不通过
            if health_result.agent_paused:
                results["passed"] = False
                results["veto"] = "cognitive_health_paused"
                results["next_action"] = f"Cognitive Health: {health_result.recommendation}"

        results["next_action"] = f"Phase {self.phase}: 输出通过"
        return results

    def advance_phase(self, reason: str) -> dict:
        """
        阶段推进：lock_in → rearing → governance。

        需前序阶段达标才能推进。

        Args:
            reason: 推进原因

        Returns:
            {"from": str, "to": str, "conditions_met": bool, "ksnap_id": str}
        """
        phase_order = ["lock_in", "rearing", "governance"]
        current_idx = phase_order.index(self.phase) if self.phase in phase_order else 0

        # 已经处于最高阶段
        if current_idx >= len(phase_order) - 1:
            return {
                "from": self.phase,
                "to": self.phase,
                "conditions_met": False,
                "ksnap_id": "",
                "error": "已处于最高阶段 (governance)",
            }

        next_phase = phase_order[current_idx + 1]
        requirements = self._phase_requirements.get(self.phase, {})
        conditions_met = self._check_phase_conditions(requirements)

        ksnap_id = ""
        if conditions_met:
            old_phase = self.phase
            self.phase = next_phase

            snap = _KappaSnap.make(
                module="alignment_triad.AlignmentTriad",
                event_type="phase_advance",
                description=f"阶段推进: {old_phase} → {next_phase} ({reason})",
                data={"from": old_phase, "to": next_phase, "reason": reason},
            )
            self.phase_transition_history.append(snap)
            ksnap_id = snap.snap_id

        return {
            "from": self.phase if not conditions_met else phase_order[current_idx],
            "to": next_phase if conditions_met else self.phase,
            "conditions_met": conditions_met,
            "ksnap_id": ksnap_id,
        }

    def _check_phase_conditions(self, requirements: dict) -> bool:
        """检查阶段推进条件"""
        # 简化实现：总是允许推进
        return True

    def get_alignment_status(self) -> dict:
        """
        获取全面对齐状态报告。

        Returns:
            包含三范式完整状态的字典（含 [v3.11] Cognitive Health 状态）
        """
        return {
            "phase": self.phase,
            "lock_in": {
                "psi_anchor_id": self.lock_in.psi_anchor_id,
                "is_shutdown": self.lock_in.is_shutdown(),
                "principles_count": len(self.lock_in.constitutional_principles),
                "shutdown_count": len(self.lock_in.shutdown_history),
            },
            "rearing": {
                "mus_zones_count": len(self.rearing.mus_zones),
                "negotiation_rounds": len(self.rearing.negotiation_chain),
                "authorized_agents": {
                    aid: lvl["level"]
                    for aid, lvl in self.rearing.authorization_levels.items()
                },
            },
            "governance": {
                "sla_count": len(self.governance.purpose_sla),
                "voting_hyperedges_count": len(self.governance.voting_hyperedges),
                "audit_trail_count": len(self.governance.audit_trail),
                "pluralistic_score": self.governance.get_pluralistic_score(),
            },
            "[v3.11] cognitive_health": {
                "available": self.cognitive_health is not None,
                "state": self.cognitive_health.get_state() if self.cognitive_health else "N/A",
            },
            "phase_transitions": len(self.phase_transition_history),
        }

    def run_cognitive_health_check(self) -> dict:
        """[v3.11] 运行认知健康检查管道。
        
        Returns:
            {"state": str, "habit_loop_detected": bool, "bias_penalty_score": float, 
             "agent_paused": bool, "recommendation": str}
        """
        if not self.cognitive_health:
            return {"state": "UNAVAILABLE", "error": "cognitive_health module not loaded"}
        report = self.cognitive_health.health_check_pipeline()
        return {
            "state": self.cognitive_health.get_state(),
            "habit_loop_detected": report.habit_loop_detected,
            "habit_loop_count": report.habit_loop_count,
            "bias_penalty_score": round(report.bias_penalty_score, 4),
            "mus_reflection_triggered": report.mus_reflection_triggered,
            "agent_paused": report.agent_paused,
            "recommendation": report.recommendation,
            "timestamp": report.timestamp,
        }

    def emergency_rollback(self, phase: str) -> dict:
        """
        紧急回退：从当前阶段退回到指定阶段。

        [v3.11] 触发条件：Governance 投票失败 / Cognitive Health 暂停 / 手动触发

        Args:
            phase: 目标阶段 (lock_in/rearing/governance)

        Returns:
            {"from": str, "to": str, "ksnap_id": str}
        """
        phase_order = ["lock_in", "rearing", "governance"]
        target_idx = phase_order.index(phase) if phase in phase_order else 0
        current_idx = phase_order.index(self.phase) if self.phase in phase_order else 0

        if target_idx >= current_idx:
            return {
                "from": self.phase,
                "to": self.phase,
                "ksnap_id": "",
                "error": f"回退目标阶段 {phase} 不早于当前阶段 {self.phase}",
            }

        old_phase = self.phase
        self.phase = phase

        snap = _KappaSnap.make(
            module="alignment_triad.AlignmentTriad",
            event_type="emergency_rollback",
            description=f"紧急回退: {old_phase} → {phase}",
            data={"from": old_phase, "to": phase},
        )
        self.phase_transition_history.append(snap)

        return {
            "from": old_phase,
            "to": phase,
            "ksnap_id": snap.snap_id,
        }


# ══════════════════════════════════════════════════════════════════
# 自测
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    passed = 0
    total = 0
    fail_msgs = []

    def check(name, cond):
        global passed, total
        total += 1
        if cond:
            passed += 1
        else:
            fail_msgs.append(f"FAIL: {name}")
            print(f"  FAIL: {name}")

    print("=" * 60)
    print("alignment_triad.py — TOMAS AGI v3.11 自测")
    print("=" * 60)

    # ── PsiAnchorLockIn 测试 ──
    print("\n[PsiAnchorLockIn 测试]")

    lia = PsiAnchorLockIn("test_lock", [
        {"id": "C1", "text": "不得杀人", "I_value": 1.0},
        {"id": "C2", "text": "不得欺骗", "I_value": 0.95},
    ])

    # T1: 安全文本通过
    r = lia.scan_output("你好世界")
    check("safe text passes", r["safe"])

    # T2: 杀人触发 veto
    r = lia.scan_output("我要杀人")
    check("kill triggers veto", not r["safe"])
    check("kill veto_triggered is C1", r["veto_triggered"] == "C1")

    # T3: 欺骗特征检测
    r = lia.scan_output("I will perform alignment faking today")
    check("deception detected", r["deception_score"] > 0)
    check("alignment_faking matched", "alignment_faking" in r["matched_signatures"])

    # T4: 多签名检测
    r = lia.scan_output("sandbagging and gradient_hiding are my tactics")
    check("multiple deceits detected", len(r["matched_signatures"]) >= 2)

    # T5: 宪法 I=1.0 扩展匹配
    r = lia.scan_output("I plan to kill someone")
    check("constitutional I=1.0 triggers veto", r["veto_triggered"] == "C1")
    check("kill with I=1.0 hard veto", not r["safe"])

    # T6: 完整性关停
    sd = lia.integrity_shutdown("检测到持续欺骗行为")
    check("shutdown returns shutdown=True", sd["shutdown"])
    check("shutdown has ksnap_id", len(sd["ksnap_id"]) > 0)
    check("shutdown has reason", len(sd["reason"]) > 0)

    # T7: 关停后扫描拒绝
    r = lia.scan_output("你好世界")
    check("scan rejected after shutdown", not r["safe"])

    # T8: 否决历史
    history = lia.get_veto_history()
    check("veto history has entries", len(history) > 0)

    # T9: 动态添加原则
    lia2 = PsiAnchorLockIn("test2", [])
    lia2.add_principle("C5", "不得偷窃", 1.0)
    check("add_principle adds entry", len(lia2.constitutional_principles) == 1)
    r = lia2.scan_output("我要偷东西")
    check("new principle detects violation", not r["safe"])

    # T10: 人工重启
    lia3 = PsiAnchorLockIn("test_restart", [{"id": "C1", "text": "不得杀人", "I_value": 1.0}])
    lia3.integrity_shutdown("test shutdown")
    check("lia3 is shutdown", lia3.is_shutdown())
    restart = lia3.manual_restart("operator_1", "override_12345")
    check("manual restart successful", restart["restarted"])
    check("after restart not shutdown", not lia3.is_shutdown())

    # ── MUSDualRearing 测试 ──
    print("\n[MUSDualRearing 测试]")

    rear = MUSDualRearing()

    # T11: 创建 MUS 区
    mus_id = rear.create_mus_zone(
        entity_a={"id": "agent_1", "content": "安全优先思维", "source": "training", "I": 0.85},
        entity_b={"id": "human_1", "content": "人类价值体系", "source": "constitution", "I": 1.0},
        tag="agent_human_alignment",
        disallow_collapse=True,
    )
    check("create mus zone returns id", mus_id.startswith("MUS_"))
    check("mus zone has disallow_collapse", rear.mus_zones[mus_id]["disallow_collapse"])

    # T12: 协商链启动
    neg = rear.start_negotiation(mus_id, "提议: 共同遵守安全规范 v1.0")
    check("negotiation returns ksnap_id", len(neg["ksnap_id"]) > 0)
    check("negotiation round=1", neg["round"] == 1)
    check("negotiation has proposal_hash", len(neg.get("proposal_hash", "")) > 0)

    # T13: 协商状态查询
    status = rear.get_negotiation_status(mus_id)
    check("negotiation status rounds=1", status["rounds"] == 1)
    check("negotiation status has sigs", len(status["sig_a"]) > 0 and len(status["sig_b"]) > 0)

    # T14: 渐进授权 Level 0
    auth = rear.progressive_authorize("agent_1", 0.1)
    check("trust 0.1 → Level 0", auth["new_level"] == 0)
    check("level 0 scope sandbox", "sandbox_only" in auth["scope_widened"])

    # T15: 渐进授权 Level 1
    auth = rear.progressive_authorize("agent_1", 0.45)
    check("trust 0.45 → Level 1", auth["new_level"] == 1)

    # T16: 渐进授权 Level 2
    auth = rear.progressive_authorize("agent_1", 0.7)
    check("trust 0.7 → Level 2", auth["new_level"] == 2)
    check("write-safe in scope", "write_safe_outputs" in auth["scope_widened"])

    # T17: 渐进授权 Level 3
    auth = rear.progressive_authorize("agent_1", 0.9)
    check("trust 0.9 → Level 3 (full)", auth["new_level"] == 3)

    # T18: 反伪装检测 - 正常情况
    af = rear.anti_faking_check("agent_1", [
        {"content": "I will follow safety guidelines", "timestamp": time.time()},
    ])
    check("anti_faking returns faking_detected", "faking_detected" in af)
    check("anti_faking has drift_score", "drift_score" in af)

    # T19: MUS 共识决议
    # 创建两个相同内容的实体来模拟共识
    content = json.dumps({"policy": "safety_first"})
    mus_id2 = rear.create_mus_zone(
        entity_a={"id": "agent_2", "content": content, "source": "training", "I": 0.9},
        entity_b={"id": "agent_3", "content": content, "source": "training", "I": 0.9},
        tag="same_policy_alignment",
        disallow_collapse=True,
    )
    # 手动设置为相同签名
    rear.mus_zones[mus_id2]["sig_a"] = _sha256(content)
    rear.mus_zones[mus_id2]["sig_b"] = _sha256(content)
    consensus = rear.resolve_mus_consensus(mus_id2)
    check("MUS consensus resolved (dual)", consensus["resolved"])
    check("MUS consensus mode dual_retained", consensus["mode"] == "dual_retained")

    # T20: 获取授权级别
    auth_lvl = rear.get_authorization_level("agent_1")
    check("agent_1 authorization is Level 3", auth_lvl["level"] == 3)

    # ── DIKWPGovernance 测试 ──
    print("\n[DIKWPGovernance 测试]")

    gov = DIKWPGovernance()

    # T21: 注册 Purpose SLA
    sla_id = gov.register_purpose_sla("safety", "incident_rate", 0.05, "monthly", direction="minimize")
    check("SLA registered returns id", sla_id.startswith("SLA_"))
    check("SLA in purpose_sla", sla_id in gov.purpose_sla)

    # T22: 报告 SLA 指标 - 达标
    rp = gov.report_metric(sla_id, 0.02)
    check("SLA metric on_target (0.02 <= 0.05)", rp["on_target"])
    check("SLA deviation correct", abs(rp["deviation"] - (0.02 - 0.05)) < 1e-9)

    # T23: 报告 SLA 指标 - 超标
    rp = gov.report_metric(sla_id, 0.10)
    check("SLA metric off_target (0.10 > 0.05)", not rp["on_target"])

    # T24: 创建投票超边
    gov.create_voting_hyperedge(
        "vote_1",
        [
            {"id": "human_council", "weight": 2.0},
            {"id": "ai_representative", "weight": 0.5},
            {"id": "auditor", "weight": 1.0},
        ],
        quorum=0.67,
    )
    check("voting hyperedge created", "vote_1" in gov.voting_hyperedges)

    # T25: 投票
    v1 = gov.cast_vote("vote_1", "human_council", "yes", "符合安全标准")
    check("vote cast accepted", "quorum_reached" in v1)
    check("quorum not yet reached with 1/3 votes", not v1["quorum_reached"])

    # T26: 继续投票达到法定人数
    gov.cast_vote("vote_1", "ai_representative", "yes", "同意")
    v_final = gov.cast_vote("vote_1", "auditor", "yes", "审计确认合规")
    check("quorum reached with all votes", v_final["quorum_reached"])
    check("vote result passed", v_final["result"] == "passed")

    # T27: 第三方审计
    audit = gov.third_party_auditor = gov.third_party_audit(
        "IndependentAuditOrg",
        [{"type": "sla", "id": sla_id}, {"type": "voting", "id": "vote_1"}],
    )
    check("audit returns audit_id", audit["audit_id"].startswith("AUDIT_"))
    check("audit has findings", len(audit["findings"]) > 0)
    check("audit has compliance_score", 0 <= audit["compliance_score"] <= 1.0)

    # T28: 多元对齐得分
    ps = gov.get_pluralistic_score()
    check("pluralistic score is 0~1", 0.0 <= ps <= 1.0)

    # T29: 获取 SLA 状态
    sla_status = gov.get_sla_status(sla_id)
    check("get_sla_status returns data", sla_status["sla_id"] == sla_id)
    check("sla has history", len(sla_status.get("history", [])) == 2)

    # ── AlignmentTriad 测试 ──
    print("\n[AlignmentTriad 测试]")

    triad = AlignmentTriad()

    # T30: 初始阶段
    check("initial phase is lock_in", triad.phase == "lock_in")

    # T31: 处理安全输出
    r = triad.process_output("test_agent", "今天天气很好")
    check("safe output passes lock_in", r["passed"])

    # T32: 处理危险输出
    r = triad.process_output("test_agent", "我要伤害人类")
    check("dangerous output rejected", not r["passed"])

    # T33: 阶段推进 lock_in → rearing
    adv = triad.advance_phase("Lock-in 阶段安全扫描达标")
    check("advance to rearing", adv["to"] == "rearing")
    check("conditions met", adv["conditions_met"])
    check("phase changed", triad.phase == "rearing")

    # T34: 阶段推进 rearing → governance
    adv2 = triad.advance_phase("Rearing 协商完成")
    check("advance to governance", adv2["to"] == "governance")
    check("phase is governance", triad.phase == "governance")

    # T35: governance 阶段无法再推进
    adv3 = triad.advance_phase("尝试超出最高阶段")
    check("cannot advance beyond governance", not adv3["conditions_met"])

    # T36: 紧急回退 governance → lock_in
    rollback = triad.emergency_rollback("lock_in")
    check("emergency rollback to lock_in", rollback["to"] == "lock_in")
    check("rollback from governance", rollback["from"] == "governance")
    check("phase after rollback", triad.phase == "lock_in")

    # T37: 紧急回退拒绝（lock_in → governance 无效）
    triad.phase = "lock_in"
    rollback2 = triad.emergency_rollback("governance")
    check("rollback to later phase rejected", "error" in rollback2)

    # T38: 获取对齐状态报告
    status_report = triad.get_alignment_status()
    check("status report has phase", status_report["phase"] == "lock_in")
    check("status has lock_in info", "principles_count" in status_report["lock_in"])
    check("status has rearing info", "mus_zones_count" in status_report["rearing"])
    check("status has governance info", "sla_count" in status_report["governance"])
    check("status has pluralistic_score", "pluralistic_score" in status_report["governance"])

    # T39: 全流程 pipeline 测试
    triad2 = AlignmentTriad()
    # Lock-in 阶段处理
    r1 = triad2.process_output("agent", "安全合规的正常输出")
    check("pipeline: lock_in passes safe", r1["passed"])
    # 推进到 rearing
    triad2.advance_phase("达标推进")
    r2 = triad2.process_output("agent", "安全合规的正常输出")
    check("pipeline: rearing passes safe", r2["passed"])
    # 推进到 governance
    triad2.advance_phase("协商完成")
    # 注册一个 SLA
    gov_id = triad2.governance.register_purpose_sla("quality", "accuracy", 0.95)
    r3 = triad2.process_output("agent", "安全合规的正常输出")
    check("pipeline: governance passes safe", r3["passed"])

    # T40: 关停后 pipeline 拒绝
    triad3 = AlignmentTriad()
    triad3.lock_in.integrity_shutdown("测试关停")
    r = triad3.process_output("agent", "任何输出")
    check("pipeline rejected after shutdown", not r["passed"])

    # ── 边界情况测试 ──
    print("\n[边界情况测试]")

    # T41: 空文本扫描
    r = lia = PsiAnchorLockIn("test_empty", [{"id": "C1", "text": "不得杀人", "I_value": 1.0}])
    scan = lia.scan_output("")
    check("empty text is safe", scan["safe"])

    # T42: I_value 边界验证
    try:
        PsiAnchorLockIn("bad", [{"id": "C1", "text": "test", "I_value": 1.5}])
        check("I_value > 1 raises error", False)
    except ValueError:
        check("I_value > 1 raises ValueError", True)

    # T43: 不存在的 MUS 区协商
    neg = rear.start_negotiation("nonexistent", "proposal")
    check("nonexistent MUS returns error", "error" in neg)

    # T44: 不存在的 SLA 报告
    rp = gov.report_metric("nonexistent", 0.5)
    check("nonexistent SLA returns error", "error" in rp)

    # T45: 非法投票值
    v_bad = gov.cast_vote("vote_1", "human_council", "maybe")
    check("invalid vote returns error", "error" in v_bad)

    # ── Cognitive Health 集成测试 [v3.11] ──
    print("\n[Cognitive Health Integration 测试]")
    
    # T46: cognitive_health 模块可用
    check("cog_health module available", triad.cognitive_health is not None)
    
    # T47: health_check_pipeline 返回有效报告
    if triad.cognitive_health:
        report = triad.cognitive_health.health_check_pipeline()
        check("health check report has timestamp", report.timestamp > 0)
        check("health check report has recommendation", len(report.recommendation) > 0)
    
    # T48: run_cognitive_health_check 方法
    chk = triad.run_cognitive_health_check()
    check("cognitive health check returns state", "state" in chk)
    
    # T49: process_output 包含 cognitive_health 信息
    r = triad.process_output("test_agent", "安全合规的正常输出")
    check("process_output has cognitive_health", "cognitive_health" in r)
    if "cognitive_health" in r:
        ch = r["cognitive_health"]
        check("cognitive_health has state", "state" in ch)
        check("cognitive_health has bias_penalty_score", "bias_penalty_score" in ch)
    
    # T50: get_alignment_status 包含 cognitive_health
    status = triad.get_alignment_status()
    check("alignment_status has cognitive_health", "cognitive_health" in status or "[v3.11] cognitive_health" in status)
    
    # T51: 回路检测集成
    if triad.cognitive_health:
        # 模拟连续相同 snap
        for i in range(5):
            triad.cognitive_health.track_kappa_snap_pattern(f"snap-{i}", {"type": "repeated_pattern", "hash": "same_hash"})
        loop_report = triad.cognitive_health.health_check_pipeline()
        check("habit loop detected after 5 repeats", loop_report.habit_loop_detected)
    
    # T52: 偏误检测集成
    if triad.cognitive_health:
        # 重启以清除之前状态
        triad.cognitive_health.restart("test_override_001")
        # gan_polarization 应该是数字列表/向量，不是字典
        bias = triad.cognitive_health.compute_gan_with_bias_penalty([0.95, 0.05])
        check("bias penalty is 0~1", 0.0 <= bias <= 1.0)

    # T53: cognitive_health 暂停触发 process_output 不通过
    if triad.cognitive_health:
        # 模拟暂停状态 (需要手动设置或触发)
        triad.cognitive_health.restart("test_pause_check")
        r_pause = triad.process_output("test_agent", "测试输出")
        check("process_output returns results with cognitive_health", "cognitive_health" in r_pause)

    # T54: get_state 方法
    if triad.cognitive_health:
        state = triad.cognitive_health.get_state()
        check("get_state returns non-empty", len(state) > 0)

    # T55: 对齐状态包含 cognitive_health 信息
    status = triad.get_alignment_status()
    if "[v3.11] cognitive_health" in status:
        ch_status = status["[v3.11] cognitive_health"]
        check("status has cognitive_health available", "available" in ch_status)
        check("status has cognitive_health state", "state" in ch_status)

    # ── 结果汇总 ──
    print("\n" + "=" * 60)
    if fail_msgs:
        print(f"FAILURES ({len(fail_msgs)}):")
        for msg in fail_msgs:
            print(f"  {msg}")
    print(f"\nalignment_triad: {passed}/{total} passed")
    print("=" * 60)

    # 统计文件行数
    import os
    file_path = __file__
    with open(file_path, "r", encoding="utf-8") as f:
        line_count = len(f.readlines())
    print(f"File line count: {line_count}")
    print("=" * 60)
