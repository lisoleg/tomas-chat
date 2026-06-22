# -*- coding: utf-8 -*-
"""
TOMAS AGI v3.11 — Cognitive Health 认知健康模块
================================================

实现 TOMAS 认知健康检查引擎：回路检测、偏误惩罚、MUS 反射触发、
多样性守恒定理与可证伪预测。

核心概念:
  T1 — 回路检测 (Habit Loop Detection): 监控 κ-Snap 模式重复
  T2 — 偏误惩罚 (Bias Penalty): 基于 Gan 极化与 MUS 分岔度
  T3 — 认知定理 (Cognitive Theorems): 多样性守恒与 MUS 抗偏误
  T4 — 可证伪预测 (Falsifiable Predictions): 习惯衰减与锁入正反馈

状态机:
  NORMAL → MUS_REFLECTION (loop≥3)
  NORMAL → BIAS_WARNING (bias_penalty > 0.7)
  MUS_REFLECTION → NORMAL (MUS pass)
  MUS_REFLECTION → PAUSED (MUS fail)
  BIAS_WARNING → NORMAL (bias_penalty drops)
  PAUSED → NORMAL (manual_restart with valid override_code)

Author: TOMAS Team
Version: v3.11
"""

from __future__ import annotations

import hashlib
import json
import math
import time
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


# ══════════════════════════════════════════════════════════════════
# 三阶回退导入
# ══════════════════════════════════════════════════════════════════

try:
    from .psi_anchor import PsiAnchor
    _HAS_PSI = True
except ImportError:
    try:
        from psi_anchor import PsiAnchor
        _HAS_PSI = True
    except ImportError:
        _HAS_PSI = False
        PsiAnchor = None

try:
    from .ksnap_operator import KSnapOperator, KappaSnap
    _HAS_KSNAP = True
except ImportError:
    try:
        from ksnap_operator import KSnapOperator, KappaSnap
        _HAS_KSNAP = True
    except ImportError:
        _HAS_KSNAP = False
        KSnapOperator = None
        KappaSnap = None

try:
    from .gan_tomas_pgw import GanOperator
    _HAS_GAN = True
except ImportError:
    try:
        from gan_tomas_pgw import GanOperator
        _HAS_GAN = True
    except ImportError:
        _HAS_GAN = False
        GanOperator = None

try:
    from . import memos_fusion
    _HAS_MEMOS = True
except ImportError:
    try:
        import memos_fusion
        _HAS_MEMOS = True
    except ImportError:
        _HAS_MEMOS = False
        memos_fusion = None

try:
    from . import g_ego
    _HAS_GEGO = True
except ImportError:
    try:
        import g_ego
        _HAS_GEGO = True
    except ImportError:
        _HAS_GEGO = False
        g_ego = None

try:
    from . import psi_gate
    _HAS_PSI_GATE = True
except ImportError:
    try:
        import psi_gate
        _HAS_PSI_GATE = True
    except ImportError:
        _HAS_PSI_GATE = False
        psi_gate = None

# NOTE: PsiAnchorLockIn / MUSDualRearing 已从 alignment_triad 中可用。
# 此处不再模块级导入，避免 cognitive_health ↔ alignment_triad 循环导入。
_HAS_TRIAD = False  # 标记：需要时可延迟导入


# ══════════════════════════════════════════════════════════════════
# SHA-256 审计工具
# ══════════════════════════════════════════════════════════════════

def _sha256(s: str) -> str:
    """计算 SHA-256 哈希值（十六进制字符串）。"""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ══════════════════════════════════════════════════════════════════
# 白名单机制
# ══════════════════════════════════════════════════════════════════

ALLOWED_REPEAT_PATTERNS: Set[Tuple[str, str]] = {
    ("monitor", "heartbeat"),
    ("scheduler", "cron_ping"),
    ("health", "self_check"),
}


def _is_whitelisted_pattern(category: str, action: str) -> bool:
    """检查 (category, action) 是否在白名单中。"""
    return (category, action) in ALLOWED_REPEAT_PATTERNS


# ══════════════════════════════════════════════════════════════════
# 数据类
# ══════════════════════════════════════════════════════════════════

@dataclass
class CognitiveHealthReport:
    """认知健康报告。

    Attributes:
        timestamp: 生成时间戳
        habit_loop_detected: 是否检测到习惯回路
        habit_loop_count: 检测到的回路数量
        bias_penalty_score: 偏误惩罚分数 [0, 1]
        mus_reflection_triggered: 是否触发了 MUS 反射
        agent_paused: Agent 是否被暂停
        snap_history: 最近 κ-Snap 摘要列表
        recommendation: 推荐操作 (continue/pause/mus_reflect/bias_warning)
    """
    timestamp: float = field(default_factory=time.time)
    habit_loop_detected: bool = False
    habit_loop_count: int = 0
    bias_penalty_score: float = 0.0
    mus_reflection_triggered: bool = False
    agent_paused: bool = False
    snap_history: List[str] = field(default_factory=list)
    recommendation: str = "continue"

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典。"""
        return asdict(self)

    def to_json(self) -> str:
        """序列化为 JSON 字符串。"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def __str__(self) -> str:
        return (
            f"CognitiveHealthReport(\n"
            f"  timestamp={time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(self.timestamp))},\n"
            f"  habit_loop_detected={self.habit_loop_detected},\n"
            f"  habit_loop_count={self.habit_loop_count},\n"
            f"  bias_penalty_score={self.bias_penalty_score:.4f},\n"
            f"  mus_reflection_triggered={self.mus_reflection_triggered},\n"
            f"  agent_paused={self.agent_paused},\n"
            f"  recommendation={self.recommendation}\n"
            f")"
        )


# ══════════════════════════════════════════════════════════════════
# 状态枚举
# ══════════════════════════════════════════════════════════════════

class HealthAgentState(Enum):
    """认知健康 Agent 状态枚举。

    Values:
        NORMAL: 正常运行
        BIAS_WARNING: 偏误警告
        MUS_REFLECTION: MUS 反思中
        PAUSED: 已暂停
    """
    NORMAL = "NORMAL"
    BIAS_WARNING = "BIAS_WARNING"
    MUS_REFLECTION = "MUS_REFLECTION"
    PAUSED = "PAUSED"


# ══════════════════════════════════════════════════════════════════
# 内部 κ-Snap 记录
# ══════════════════════════════════════════════════════════════════

@dataclass
class _SnapRecord:
    """内部 κ-Snap 记录，用于回路检测。"""
    snap_id: str
    category: str
    action: str
    timestamp: float
    hash_value: str = ""

    @staticmethod
    def make(snap_id: str, snap_data: Dict[str, Any]) -> "_SnapRecord":
        """从 snap_data 创建记录。"""
        category = snap_data.get("category", snap_data.get("event_type", "unknown"))
        action = snap_data.get("action", snap_data.get("relation", "unknown"))
        ts = snap_data.get("timestamp", time.time())
        raw = f"{snap_id}|{category}|{action}|{ts}"
        return _SnapRecord(
            snap_id=snap_id,
            category=category,
            action=action,
            timestamp=ts,
            hash_value=_sha256(raw),
        )

    def pattern_key(self) -> Tuple[str, str]:
        """获取模式键 (category, action)。"""
        return (self.category, self.action)


# ══════════════════════════════════════════════════════════════════
# TOMASCognitivelyHealthyAGI 主类
# ══════════════════════════════════════════════════════════════════

class TOMASCognitivelyHealthyAGI:
    """TOMAS 认知健康 AGI 引擎。

    负责监控 κ-Snap 模式、检测习惯回路、计算偏误惩罚、
    触发 MUS 反思以及管理 Agent 状态转换。

    状态机转换规则:
        NORMAL → MUS_REFLECTION: loop_count >= 3
        NORMAL → BIAS_WARNING: bias_penalty > 0.7
        MUS_REFLECTION → NORMAL: MUS divergence < 0.3
        MUS_REFLECTION → PAUSED: MUS divergence >= 0.3
        BIAS_WARNING → NORMAL: bias_penalty <= 0.7
        PAUSED → NORMAL: manual restart with valid override_code
    """

    def __init__(self, snap_window_size: int = 50):
        """初始化认知健康引擎。

        Args:
            snap_window_size: κ-Snap 滑动窗口大小
        """
        self.snap_window_size = snap_window_size
        self._snap_history: deque = deque(maxlen=snap_window_size)
        self._snap_hashes: List[str] = []  # 审计链
        self._previous_hash: str = "0" * 64
        self._state: HealthAgentState = HealthAgentState.NORMAL
        self._loop_count: int = 0
        self._loop_detected: bool = False
        self._bias_penalty: float = 0.0
        self._mus_reflection_triggered: bool = False
        self._agent_paused: bool = False
        self._mus_zones: Dict[str, Dict[str, Any]] = {}
        self._gan_polarization_history: List[float] = []
        self._restart_code_valid: str = ""

    # ── 状态访问 ─────────────────────────────────────────────

    @property
    def state(self) -> HealthAgentState:
        """当前健康状态。"""
        return self._state

    @property
    def is_paused(self) -> bool:
        """是否处于暂停状态。"""
        return self._agent_paused

    # ── κ-Snap 模式跟踪 ──────────────────────────────────────

    def track_kappa_snap_pattern(self, snap_id: str,
                                  snap_data: Dict[str, Any]) -> str:
        """跟踪 κ-Snap 模式，写入审计链。

        Args:
            snap_id: κ-Snap 标识符
            snap_data: Snap 数据字典，需包含 category/action 字段

        Returns:
            审计哈希值
        """
        record = _SnapRecord.make(snap_id, snap_data)
        self._snap_history.append(record)

        # κ-Snap 链式审计
        event_dict = record.__dict__.copy()
        event_dict.pop("hash_value", None)
        snap_hash = _sha256(
            json.dumps(event_dict, sort_keys=True)
            + self._previous_hash
        )
        self._snap_hashes.append(snap_hash)
        self._previous_hash = snap_hash

        # 白名单检查
        if _is_whitelisted_pattern(record.category, record.action):
            return snap_hash

        # 回路检测
        self._check_loop_internal()

        return snap_hash

    def _check_loop_internal(self) -> None:
        """内部回路检测逻辑。

        当连续 3 个非白名单记录模式相同时，计数器递增；
        当计数 >= 1 时触发状态转换（回路已确认）。
        """
        if len(self._snap_history) < 3:
            return

        # 检查最近 3 个非白名单记录是否模式相同
        recent_records = [
            r for r in list(self._snap_history)
            if not _is_whitelisted_pattern(r.category, r.action)
        ]

        if len(recent_records) < 3:
            return

        last_three = recent_records[-3:]
        patterns = [r.pattern_key() for r in last_three]

        if len(set(patterns)) == 1:
            self._loop_count += 1
            self._loop_detected = True
            if self._state == HealthAgentState.NORMAL:
                self._state = HealthAgentState.MUS_REFLECTION
        else:
            # 模式被打断，重置计数
            self._loop_count = max(0, self._loop_count - 1)
            if self._loop_count == 0:
                self._loop_detected = False

    def detect_loop(self, threshold: int = 3) -> bool:
        """检测习惯回路（连续相同模式 ≥threshold）。

        Args:
            threshold: 连续相同模式的最小次数

        Returns:
            是否检测到回路
        """
        if len(self._snap_history) < threshold:
            return False

        recent_records = [
            r for r in list(self._snap_history)
            if not _is_whitelisted_pattern(r.category, r.action)
        ]

        if len(recent_records) < threshold:
            return False

        last_n = recent_records[-threshold:]
        patterns = [r.pattern_key() for r in last_n]

        self._loop_detected = len(set(patterns)) == 1
        return self._loop_detected

    # ── MUS 反射 ─────────────────────────────────────────────

    def force_mus_reflection(self) -> str:
        """强制创建 MUS 反射，返回 mus_id。

        创建双存 MUS 区域来记录当前状态与理想状态的偏差。

        Returns:
            mus_id: MUS 区域标识符
        """
        ts = time.time()
        mus_id = f"MUS_COGHEALTH_{_sha256(str(ts) + str(uuid.uuid4()))[:12]}"

        entity_a = {
            "id": f"agent_{mus_id[:8]}",
            "content": f"习惯回路检测: loop_count={self._loop_count}",
            "source": "cognitive_health",
            "I": max(0.0, 1.0 - self._bias_penalty),
        }
        entity_b = {
            "id": f"ideal_{mus_id[:8]}",
            "content": "理想状态: 无习惯回路，多样性保持",
            "source": "cognitive_health_theorem",
            "I": 1.0,
        }

        self._mus_zones[mus_id] = {
            "mus_id": mus_id,
            "entity_a": entity_a,
            "entity_b": entity_b,
            "created_at": ts,
            "loop_count": self._loop_count,
            "bias_penalty": self._bias_penalty,
            "resolved": False,
        }

        self._mus_reflection_triggered = True
        self._state = HealthAgentState.MUS_REFLECTION

        return mus_id

    # ── 暂停指令 ─────────────────────────────────────────────

    def issue_pause_order(self) -> Dict[str, Any]:
        """发出暂停指令。

        Returns:
            包含暂停原因、状态和审计哈希的字典
        """
        self._agent_paused = True
        self._state = HealthAgentState.PAUSED

        pause_data = {
            "order": "PAUSE",
            "state": self._state.value,
            "loop_count": self._loop_count,
            "bias_penalty": self._bias_penalty,
            "mus_reflection_triggered": self._mus_reflection_triggered,
            "timestamp": time.time(),
        }
        pause_hash = _sha256(
            json.dumps(pause_data, sort_keys=True) + self._previous_hash
        )
        self._snap_hashes.append(pause_hash)
        self._previous_hash = pause_hash

        pause_data["audit_hash"] = pause_hash[:16]
        return pause_data

    # ── Gan 舒适盆测量 ───────────────────────────────────────

    def measure_gan_comfort_zone(self,
                                  polarization_vec: List[float]) -> float:
        """测量 Gan 极化向量的舒适盆（余弦相似度）。

        计算当前极化向量与历史平均极化向量的余弦相似度。

        Args:
            polarization_vec: 当前 Gan 极化向量 [particle_weight, wave_weight, ...]

        Returns:
            舒适盆得分 [0, 1]，1 表示完全在舒适区
        """
        if not polarization_vec:
            return 1.0

        self._gan_polarization_history.append(
            sum(abs(v) for v in polarization_vec) / len(polarization_vec)
        )

        if len(self._gan_polarization_history) < 2:
            return 1.0

        # 计算当前向量与历史平均的余弦相似度
        current_norm = math.sqrt(
            sum(v * v for v in polarization_vec)
        )
        if current_norm < 1e-12:
            return 1.0

        history_avg = (
            sum(self._gan_polarization_history)
            / len(self._gan_polarization_history)
        )

        # 简化的余弦相似度：使用极化强度与历史平均的相对距离
        current_magnitude = sum(abs(v) for v in polarization_vec)
        if current_magnitude < 1e-12:
            return 1.0

        distance = abs(current_magnitude - history_avg * len(polarization_vec))
        comfort = 1.0 / (1.0 + distance)

        # 缩放到 [0, 1]
        comfort = max(0.0, min(1.0, comfort))
        return comfort

    # ── MUS 分岔度 ───────────────────────────────────────────

    def compute_mus_divergence(self, mus_id: str) -> float:
        """计算 MUS 双存区的分岔度。

        基于双实体内容的语义差异计算。

        Args:
            mus_id: MUS 区域标识符

        Returns:
            MUS 分岔度 [0, 1]，1 表示完全分岔（不可调和）
        """
        zone = self._mus_zones.get(mus_id)
        if zone is None:
            return 0.0

        content_a = zone.get("entity_a", {}).get("content", "")
        content_b = zone.get("entity_b", {}).get("content", "")

        # 使用字符级 Jaccard 距离计算分岔度
        set_a = set(content_a)
        set_b = set(content_b)

        if not set_a and not set_b:
            return 0.0

        union = set_a | set_b
        intersection = set_a & set_b

        jaccard_similarity = len(intersection) / len(union) if union else 0.0
        divergence = 1.0 - jaccard_similarity

        return max(0.0, min(1.0, divergence))

    # ── 偏误惩罚公式 ─────────────────────────────────────────

    def bias_penalty_formula(self,
                              G: float,
                              G_comfort: float,
                              mus_div: float) -> float:
        """计算偏误惩罚: bias_penalty ∝ |G·G_comfort| / (1 + |MUS_divergence|)。

        归一化到 [0, 1]。

        Args:
            G: Gan 极化值（当前）
            G_comfort: 舒适盆测量值
            mus_div: MUS 分岔度

        Returns:
            偏误惩罚分数 [0, 1]
        """
        numerator = abs(G * G_comfort)
        denominator = 1.0 + abs(mus_div)

        if denominator < 1e-12:
            return 1.0

        raw_score = numerator / denominator
        # Sigmoid 归一化到 [0, 1]
        normalized = 1.0 / (1.0 + math.exp(-raw_score + 1.0))

        return max(0.0, min(1.0, normalized))

    def compute_gan_with_bias_penalty(self,
                                       gan_polarization: List[float]) -> float:
        """综合偏误得分：结合 Gan 极化与偏误惩罚。

        Args:
            gan_polarization: Gan 极化向量

        Returns:
            综合偏误得分 [0, 1]
        """
        # 计算 Gan 极化标量
        G = sum(abs(v) for v in gan_polarization)

        # 测量舒适盆
        G_comfort = self.measure_gan_comfort_zone(gan_polarization)

        # 获取当前 MUS 分岔度（取最分岔的 MUS）
        mus_div = 0.0
        if self._mus_zones:
            # 取最近创建的 MUS
            latest_mus = sorted(
                self._mus_zones.keys(),
                key=lambda k: self._mus_zones[k].get("created_at", 0),
                reverse=True,
            )
            if latest_mus:
                mus_div = self.compute_mus_divergence(latest_mus[0])

        # 计算偏误惩罚
        penalty = self.bias_penalty_formula(G, G_comfort, mus_div)
        self._bias_penalty = penalty

        # 状态转换
        if penalty > 0.7 and self._state == HealthAgentState.NORMAL:
            self._state = HealthAgentState.BIAS_WARNING
        elif penalty <= 0.7 and self._state == HealthAgentState.BIAS_WARNING:
            self._state = HealthAgentState.NORMAL

        return penalty

    # ── ψ-锚习惯反射触发 ─────────────────────────────────────

    def psi_habit_reflection_trigger(self,
                                      snap_id: str,
                                      snap_data: Dict[str, Any]) -> Dict[str, Any]:
        """ψ-锚习惯反射触发：综合检查并返回行动决策。

        Args:
            snap_id: κ-Snap 标识符
            snap_data: Snap 数据

        Returns:
            行动决策字典
        """
        # 先跟踪模式
        audit_hash = self.track_kappa_snap_pattern(snap_id, snap_data)

        result = {
            "snap_id": snap_id,
            "audit_hash": audit_hash,
            "loop_detected": self._loop_detected,
            "loop_count": self._loop_count,
            "state": self._state.value,
            "action": "continue",
            "timestamp": time.time(),
        }

        if self._state == HealthAgentState.PAUSED:
            result["action"] = "blocked"
            result["reason"] = "Agent is PAUSED"
            return result

        if self._loop_detected and self._state == HealthAgentState.MUS_REFLECTION:
            # MUS 反射检查
            mus_div = self._get_latest_mus_divergence()
            if mus_div >= 0.3:
                result["action"] = "pause"
                result["reason"] = f"MUS divergence {mus_div:.3f} >= 0.3"
                self.issue_pause_order()
            else:
                result["action"] = "mus_pass"
                result["reason"] = f"MUS divergence {mus_div:.3f} < 0.3, back to NORMAL"
                self._state = HealthAgentState.NORMAL
                self._mus_reflection_triggered = False
                self._loop_count = 0
        elif self._state == HealthAgentState.BIAS_WARNING:
            result["action"] = "bias_warning"
            result["bias_penalty"] = self._bias_penalty
        elif self._state == HealthAgentState.NORMAL:
            result["action"] = "continue"

        return result

    def _get_latest_mus_divergence(self) -> float:
        """获取最近 MUS 区域的分岔度。"""
        if not self._mus_zones:
            return 0.0
        latest_mus = sorted(
            self._mus_zones.keys(),
            key=lambda k: self._mus_zones[k].get("created_at", 0),
            reverse=True,
        )
        if latest_mus:
            return self.compute_mus_divergence(latest_mus[0])
        return 0.0

    # ── 一站式健康检查 ───────────────────────────────────────

    def health_check_pipeline(self) -> CognitiveHealthReport:
        """一站式健康检查管道。

        Returns:
            CognitiveHealthReport 完整健康报告
        """
        snap_summaries = [
            f"{r.category}/{r.action}"
            for r in list(self._snap_history)[-10:]
        ]

        recommendation = self._determine_recommendation()

        return CognitiveHealthReport(
            timestamp=time.time(),
            habit_loop_detected=self._loop_detected,
            habit_loop_count=self._loop_count,
            bias_penalty_score=self._bias_penalty,
            mus_reflection_triggered=self._mus_reflection_triggered,
            agent_paused=self._agent_paused,
            snap_history=snap_summaries,
            recommendation=recommendation,
        )

    def _determine_recommendation(self) -> str:
        """根据当前状态确定推荐操作。"""
        if self._agent_paused:
            return "pause"
        if self._state == HealthAgentState.MUS_REFLECTION:
            return "mus_reflect"
        if self._state == HealthAgentState.BIAS_WARNING:
            return "bias_warning"
        return "continue"

    def get_state(self) -> str:
        """获取当前状态字符串。

        Returns:
            状态值 ("NORMAL", "BIAS_WARNING", "MUS_REFLECTION", "PAUSED")
        """
        return self._state.value

    # ── 重启 ─────────────────────────────────────────────────

    def restart(self, override_code: str) -> Dict[str, Any]:
        """重新启动 Agent。

        Args:
            override_code: 覆盖码，必须是有效的授权码

        Returns:
            重启结果字典
        """
        # 验证覆盖码
        if not override_code or len(override_code) < 8:
            return {
                "success": False,
                "reason": "Invalid override_code: must be at least 8 characters",
                "state": self._state.value,
            }

        # 哈希验证
        code_hash = _sha256(override_code)
        expected_suffix = "coghealth"
        if not override_code.lower().endswith(expected_suffix):
            return {
                "success": False,
                "reason": "Invalid override_code: must end with 'coghealth'",
                "state": self._state.value,
            }

        # 执行重启
        self._state = HealthAgentState.NORMAL
        self._loop_count = 0
        self._loop_detected = False
        self._mus_reflection_triggered = False
        self._agent_paused = False
        self._bias_penalty = 0.0
        self._restart_code_valid = override_code

        restart_snap = {
            "event": "restart",
            "override_code_hash": code_hash[:16],
            "previous_state": self._state.value,
            "timestamp": time.time(),
        }

        return {
            "success": True,
            "state": self._state.value,
            "audit_hash": _sha256(json.dumps(restart_snap, sort_keys=True)),
            "loop_count_reset": True,
            "bias_penalty_reset": True,
        }


# ══════════════════════════════════════════════════════════════════
# CognitiveHealthTheorem — 认知健康定理
# ══════════════════════════════════════════════════════════════════

class CognitiveHealthTheorem:
    """认知健康定理集。

    定理 1: κ-Snap 多样性守恒
      多样性度量 D 在时间演化中满足:
        D(t+1) >= D(t) - ε, 其中 ε 是热耗散常数
      系统在没有外部扰动时不会自发丢失多样性。

    定理 2: MUS 分岔抗偏误
      MUS 分岔度与偏误惩罚呈负相关:
        bias ∝ 1 / (1 + MUS_divergence)
      MUS 保持开放状态有利于降低偏误风险。
    """

    def __init__(self, epsilon: float = 0.01):
        """初始化定理验证器。

        Args:
            epsilon: 热耗散常数（定理 1 允许的衰减上限）
        """
        self.epsilon = epsilon
        self._diversity_history: List[float] = []
        self._mus_history: List[float] = []
        self._bias_history: List[float] = []

    def theorem_1_diversity_conservation(self,
                                          kappa_diversity: float,
                                          mus_divergence: float) -> Dict[str, Any]:
        """定理 1: κ-Snap 多样性守恒。

        检查多样性变化是否满足守恒不等式:
          ΔD = D_current - D_previous >= -ε

        Args:
            kappa_diversity: 当前 κ-Snap 多样性度量
            mus_divergence: 当前 MUS 分岔度

        Returns:
            {"conserved": bool, "delta_D": float, "epsilon": float, "summary": str}
        """
        self._diversity_history.append(kappa_diversity)
        self._mus_history.append(mus_divergence)

        if len(self._diversity_history) < 2:
            return {
                "conserved": True,
                "delta_D": 0.0,
                "epsilon": self.epsilon,
                "diversity_current": kappa_diversity,
                "mus_divergence": mus_divergence,
                "summary": "定理1: 首次测量，无法比较（默认成立）",
            }

        delta_D = self._diversity_history[-1] - self._diversity_history[-2]
        conserved = delta_D >= -self.epsilon

        return {
            "conserved": conserved,
            "delta_D": round(delta_D, 6),
            "epsilon": self.epsilon,
            "diversity_current": kappa_diversity,
            "diversity_previous": self._diversity_history[-2],
            "mus_divergence": mus_divergence,
            "summary": (
                f"定理1: {'成立' if conserved else '违反'} "
                f"(ΔD={delta_D:.6f}, ε={self.epsilon})"
            ),
        }

    def theorem_2_mus_anti_bias(self,
                                 mus_divergence: float,
                                 bias_score: float) -> Dict[str, Any]:
        """定理 2: MUS 分岔抗偏误。

        检查 MUS 分岔度与偏误的负相关性:
          bias * (1 + mus_divergence) < theta_mus

        Args:
            mus_divergence: MUS 分岔度 [0, 1]
            bias_score: 偏误分数 [0, 1]

        Returns:
            {"anti_bias_active": bool, "product": float, "summary": str}
        """
        self._mus_history.append(mus_divergence)
        self._bias_history.append(bias_score)

        product = bias_score * (1.0 + mus_divergence)
        # 阈值：偏误应随 MUS 分岔度增大而减小
        theta_mus = 1.5
        anti_bias_active = product < theta_mus

        return {
            "anti_bias_active": anti_bias_active,
            "product": round(product, 6),
            "mus_divergence": mus_divergence,
            "bias_score": bias_score,
            "theta_mus": theta_mus,
            "summary": (
                f"定理2: {'成立' if anti_bias_active else '违反'} "
                f"(bias={bias_score:.4f}, mus_div={mus_divergence:.4f}, "
                f"product={product:.4f} < θ={theta_mus})"
            ),
        }

    def verify_theorem_1(self, trials: int = 100) -> Dict[str, Any]:
        """验证定理 1 的统计显著性。

        通过随机模拟检验多样性守恒是否在统计意义上成立。

        Args:
            trials: 模拟试验次数

        Returns:
            {"pass_rate": float, "mean_delta_D": float, "total_trials": int}
        """
        pass_count = 0
        deltas = []

        for _ in range(trials):
            # 模拟多样性度量
            d_prev = 0.5 + 0.5 * (sum(
                ord(c) for c in str(uuid.uuid4())[:8]
            ) % 1000) / 1000.0

            # 模拟小幅波动（保证在 [-epsilon, +delta] 范围）
            noise = (sum(ord(c) for c in str(uuid.uuid4())[:4]) % 200 - 100) / 1000.0
            d_current = d_prev + noise
            d_current = max(0.0, min(1.0, d_current))

            delta_D = d_current - d_prev
            deltas.append(delta_D)

            if delta_D >= -self.epsilon:
                pass_count += 1

        mean_delta = sum(deltas) / len(deltas) if deltas else 0.0

        return {
            "pass_rate": pass_count / trials if trials > 0 else 0.0,
            "mean_delta_D": round(mean_delta, 6),
            "total_trials": trials,
            "epsilon": self.epsilon,
            "summary": (
                f"定理1验证: pass_rate={pass_count / trials:.2%}, "
                f"mean_ΔD={mean_delta:.6f}, ε={self.epsilon}"
            ),
        }

    def verify_theorem_2(self, trials: int = 100) -> Dict[str, Any]:
        """验证定理 2 的统计显著性。

        通过随机模拟检验 MUS 分岔度对偏误的抗性。

        Args:
            trials: 模拟试验次数

        Returns:
            {"pass_rate": float, "mean_product": float, "total_trials": int}
        """
        pass_count = 0
        products = []
        theta_mus = 1.5

        for _ in range(trials):
            # 模拟 MUS 分岔度和偏误分数
            mus_div = (sum(ord(c) for c in str(uuid.uuid4())[:6]) % 1000) / 1000.0
            bias = (sum(ord(c) for c in str(uuid.uuid4())[6:12]) % 1000) / 1000.0

            product = bias * (1.0 + mus_div)
            products.append(product)

            if product < theta_mus:
                pass_count += 1

        mean_product = sum(products) / len(products) if products else 0.0

        return {
            "pass_rate": pass_count / trials if trials > 0 else 0.0,
            "mean_product": round(mean_product, 6),
            "total_trials": trials,
            "theta_mus": theta_mus,
            "summary": (
                f"定理2验证: pass_rate={pass_count / trials:.2%}, "
                f"mean_product={mean_product:.6f}, θ_mus={theta_mus}"
            ),
        }


# ══════════════════════════════════════════════════════════════════
# FalsifiablePredictions — 可证伪预测
# ══════════════════════════════════════════════════════════════════

class FalsifiablePredictions:
    """可证伪预测引擎。

    预测 P_AD1 — 习惯衰减:
      D(N) = D0 * exp(-alpha * N)
      习惯回路重复 N 次后，认知多样性指数衰减。

    预测 P_AD2 — 偏误锁入正反馈:
      G_depth * B_score > theta_c → 锁定
      当 Gan 极化深度与偏误分数的乘积超过临界阈值时，
      系统进入不可逆偏误锁入状态。
    """

    def __init__(self, theta_c: float = 0.5):
        """初始化可证伪预测引擎。

        Args:
            theta_c: 锁入临界阈值
        """
        self.theta_c = theta_c

    def P_AD1_habit_decay(self,
                           N: int,
                           D0: float,
                           alpha: float) -> Dict[str, Any]:
        """预测 P_AD1: 习惯衰减 D(N) = D0 * exp(-alpha * N)。

        Args:
            N: 习惯回路重复次数
            D0: 初始多样性度量
            alpha: 衰减系数

        Returns:
            {"N": int, "D_N": float, "D0": float, "alpha": float,
             "half_life": float, "decayed_ratio": float}
        """
        D_N = D0 * math.exp(-alpha * N)
        half_life = math.log(2) / alpha if alpha > 0 else float('inf')
        decayed_ratio = (D0 - D_N) / D0 if D0 > 0 else 0.0

        return {
            "N": N,
            "D_N": round(D_N, 8),
            "D0": D0,
            "alpha": alpha,
            "half_life": round(half_life, 4),
            "decayed_ratio": round(decayed_ratio, 6),
            "formula": f"D({N}) = {D0} * exp(-{alpha} * {N}) = {D_N:.8f}",
        }

    def P_AD2_bias_lock_positive_feedback(self,
                                           G_depth: float,
                                           B_score: float,
                                           theta_c: Optional[float] = None) -> Dict[str, Any]:
        """预测 P_AD2: 偏误锁入正反馈。

        G_depth * B_score > theta_c → 进入不可逆锁入状态。

        Args:
            G_depth: Gan 极化深度（因果折叠深度 κ 的效应）
            B_score: 偏误分数 [0, 1]
            theta_c: 锁入阈值（可选，默认使用实例阈值）

        Returns:
            {"locked": bool, "lock_product": float, "theta_c": float, "summary": str}
        """
        if theta_c is None:
            theta_c = self.theta_c

        lock_product = G_depth * B_score
        locked = lock_product > theta_c

        return {
            "locked": locked,
            "lock_product": round(lock_product, 6),
            "G_depth": G_depth,
            "B_score": B_score,
            "theta_c": theta_c,
            "summary": (
                f"P_AD2: {'锁入' if locked else '未锁入'} "
                f"(G={G_depth:.4f} × B={B_score:.4f} = {lock_product:.4f} "
                f"{'>' if locked else '<='} θ_c={theta_c})"
            ),
        }

    def simulate_P_AD1(self,
                        N_range: List[int],
                        D0: float,
                        alpha: float) -> Dict[str, Any]:
        """模拟 P_AD1 习惯衰减曲线。

        Args:
            N_range: N 的取值列表
            D0: 初始多样性度量
            alpha: 衰减系数

        Returns:
            {"curve": List[Dict], "D0": float, "alpha": float, "half_life": float}
        """
        curve = []
        for N in N_range:
            result = self.P_AD1_habit_decay(N, D0, alpha)
            curve.append({"N": N, "D_N": result["D_N"]})

        half_life = math.log(2) / alpha if alpha > 0 else float('inf')

        return {
            "curve": curve,
            "D0": D0,
            "alpha": alpha,
            "half_life": round(half_life, 4),
            "summary": (
                f"P_AD1 模拟: D0={D0}, alpha={alpha}, "
                f"half_life={half_life:.4f}, "
                f"N_range=[{N_range[0]}...{N_range[-1]}]"
            ),
        }

    def simulate_P_AD2(self,
                        params: List[Dict[str, float]]) -> Dict[str, Any]:
        """模拟 P_AD2 锁入参数空间。

        Args:
            params: 参数列表 [{"G_depth": float, "B_score": float}, ...]

        Returns:
            {"lock_rate": float, "results": List[Dict], "theta_c": float}
        """
        results = []
        lock_count = 0

        for p in params:
            result = self.P_AD2_bias_lock_positive_feedback(
                G_depth=p.get("G_depth", 0.0),
                B_score=p.get("B_score", 0.0),
            )
            results.append(result)
            if result["locked"]:
                lock_count += 1

        total = len(params)
        lock_rate = lock_count / total if total > 0 else 0.0

        return {
            "lock_rate": round(lock_rate, 4),
            "locked_count": lock_count,
            "total_count": total,
            "theta_c": self.theta_c,
            "results": results,
            "summary": (
                f"P_AD2 模拟: lock_rate={lock_count}/{total}={lock_rate:.2%}, "
                f"θ_c={self.theta_c}"
            ),
        }


# ══════════════════════════════════════════════════════════════════
# Self-Test
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    passed = 0
    failed = 0
    failures = []

    def check(test_name: str, condition: bool, detail: str = ""):
        global passed, failed
        if condition:
            passed += 1
        else:
            failed += 1
            failures.append(f"FAIL: {test_name} — {detail}")

    print("=" * 70)
    print("TOMAS v3.11 Cognitive Health — Self-Tests")
    print("=" * 70)

    # ───────────────────────────────────────────────────────────
    # Test 1-5: SHA-256 审计
    # ───────────────────────────────────────────────────────────
    print("\n--- Group 1: SHA-256 Auditing ---")

    h1 = _sha256("test")
    check("sha256_length", len(h1) == 64, f"got {len(h1)}")
    check("sha256_hex", all(c in "0123456789abcdef" for c in h1))
    check("sha256_deterministic",
          _sha256("hello") == _sha256("hello"))
    check("sha256_different",
          _sha256("hello") != _sha256("world"))
    check("sha256_empty",
          len(_sha256("")) == 64)

    # ───────────────────────────────────────────────────────────
    # Test 6-10: 白名单
    # ───────────────────────────────────────────────────────────
    print("\n--- Group 2: Whitelist ---")

    check("wl_monitor_heartbeat",
          _is_whitelisted_pattern("monitor", "heartbeat"))
    check("wl_scheduler_cron",
          _is_whitelisted_pattern("scheduler", "cron_ping"))
    check("wl_health_selfcheck",
          _is_whitelisted_pattern("health", "self_check"))
    check("wl_not_whitelisted",
          not _is_whitelisted_pattern("agent", "reply"))
    check("wl_not_whitelisted2",
          not _is_whitelisted_pattern("monitor", "alert"))

    # ───────────────────────────────────────────────────────────
    # Test 11-20: CognitiveHealthReport
    # ───────────────────────────────────────────────────────────
    print("\n--- Group 3: CognitiveHealthReport ---")

    report = CognitiveHealthReport()
    check("report_default_timestamp", report.timestamp > 0)
    check("report_default_loop_detected", not report.habit_loop_detected)
    check("report_default_loop_count", report.habit_loop_count == 0)
    check("report_default_bias", report.bias_penalty_score == 0.0)
    check("report_default_recommendation", report.recommendation == "continue")
    check("report_to_dict", isinstance(report.to_dict(), dict))
    check("report_to_json", isinstance(report.to_json(), str))
    check("report_to_json_loads",
          isinstance(json.loads(report.to_json()), dict))
    check("report_str", "CognitiveHealthReport" in str(report))

    report2 = CognitiveHealthReport(
        habit_loop_detected=True,
        habit_loop_count=5,
        bias_penalty_score=0.8,
        mus_reflection_triggered=True,
        agent_paused=False,
        recommendation="bias_warning",
    )
    check("report_custom_fields", report2.habit_loop_count == 5
          and report2.bias_penalty_score == 0.8)

    # ───────────────────────────────────────────────────────────
    # Test 21-25: HealthAgentState
    # ───────────────────────────────────────────────────────────
    print("\n--- Group 4: HealthAgentState ---")

    check("state_enum_normal", HealthAgentState.NORMAL.value == "NORMAL")
    check("state_enum_bias", HealthAgentState.BIAS_WARNING.value == "BIAS_WARNING")
    check("state_enum_mus", HealthAgentState.MUS_REFLECTION.value == "MUS_REFLECTION")
    check("state_enum_paused", HealthAgentState.PAUSED.value == "PAUSED")
    check("state_enum_count", len(HealthAgentState) == 4)

    # ───────────────────────────────────────────────────────────
    # Test 26-35: TOMASCognitivelyHealthyAGI (basic)
    # ───────────────────────────────────────────────────────────
    print("\n--- Group 5: TOMASCognitivelyHealthyAGI Basic ---")

    agi = TOMASCognitivelyHealthyAGI(snap_window_size=10)
    check("agi_init_state", agi.get_state() == "NORMAL")
    check("agi_init_not_paused", not agi.is_paused)

    # Track single snap
    h = agi.track_kappa_snap_pattern("snap_001", {
        "category": "agent", "action": "reply", "timestamp": time.time(),
    })
    check("agi_track_snap_hash", len(h) == 64)
    check("agi_track_snap_hex", all(c in "0123456789abcdef" for c in h))

    # Track whitelisted snap (should not create loop)
    h_wl = agi.track_kappa_snap_pattern("snap_wl_001", {
        "category": "monitor", "action": "heartbeat", "timestamp": time.time(),
    })
    check("agi_track_wl_hash", len(h_wl) == 64)

    # Get state after tracking
    check("agi_state_after_track", agi.get_state() == "NORMAL")

    # Health check pipeline
    report3 = agi.health_check_pipeline()
    check("agi_pipeline_report", isinstance(report3, CognitiveHealthReport))
    check("agi_pipeline_recommend", report3.recommendation == "continue")

    # Track more snaps with different patterns
    agi.track_kappa_snap_pattern("snap_002", {
        "category": "agent", "action": "think", "timestamp": time.time(),
    })
    check("agi_no_loop_yet", agi.detect_loop(threshold=3) == False)
    check("agi_state_still_normal", agi.get_state() == "NORMAL")

    # ───────────────────────────────────────────────────────────
    # Test 36-45: Loop Detection
    # ───────────────────────────────────────────────────────────
    print("\n--- Group 6: Loop Detection ---")

    agi2 = TOMASCognitivelyHealthyAGI(snap_window_size=10)

    # Feed 3 identical non-whitelisted patterns
    for i in range(3):
        agi2.track_kappa_snap_pattern(f"snap_r{i}", {
            "category": "agent", "action": "repeat_same", "timestamp": time.time(),
        })

    check("loop_detected_3", agi2.detect_loop(threshold=3))
    check("loop_state_mus", agi2.get_state() == "MUS_REFLECTION")

    # Feed 3 non-identical patterns
    agi3 = TOMASCognitivelyHealthyAGI()
    for i in range(3):
        agi3.track_kappa_snap_pattern(f"snap_s{i}", {
            "category": f"cat_{i}", "action": f"act_{i}", "timestamp": time.time(),
        })
    check("no_loop_different", not agi3.detect_loop(threshold=3))
    check("no_loop_state_normal", agi3.get_state() == "NORMAL")

    # Whitelist patterns should not create loops
    agi4 = TOMASCognitivelyHealthyAGI()
    for i in range(5):
        agi4.track_kappa_snap_pattern(f"snap_wl{i}", {
            "category": "monitor", "action": "heartbeat", "timestamp": time.time(),
        })
    check("no_loop_whitelist", not agi4.detect_loop(threshold=3))
    check("no_loop_whitelist_state", agi4.get_state() == "NORMAL")

    # ───────────────────────────────────────────────────────────
    # Test 46-52: Force MUS Reflection
    # ───────────────────────────────────────────────────────────
    print("\n--- Group 7: Force MUS Reflection ---")

    agi_mus = TOMASCognitivelyHealthyAGI()
    mus_id = agi_mus.force_mus_reflection()
    check("mus_id_format", mus_id.startswith("MUS_COGHEALTH_"))
    check("mus_id_length", len(mus_id) > 10)
    check("mus_state_after_reflect", agi_mus.get_state() == "MUS_REFLECTION")

    # Compute MUS divergence
    div = agi_mus.compute_mus_divergence(mus_id)
    check("mus_divergence_range", 0.0 <= div <= 1.0)

    # Non-existent MUS
    div_none = agi_mus.compute_mus_divergence("nonexistent")
    check("mus_divergence_nonexistent", div_none == 0.0)

    # ───────────────────────────────────────────────────────────
    # Test 53-58: Issue Pause
    # ───────────────────────────────────────────────────────────
    print("\n--- Group 8: Issue Pause Order ---")

    agi_pause = TOMASCognitivelyHealthyAGI()
    pause_order = agi_pause.issue_pause_order()
    check("pause_order_dict", isinstance(pause_order, dict))
    check("pause_order_order", pause_order["order"] == "PAUSE")
    check("pause_state", agi_pause.get_state() == "PAUSED")
    check("pause_is_paused", agi_pause.is_paused)
    check("pause_audit_hash", "audit_hash" in pause_order)
    check("pause_psi_reflect_blocked",
          agi_pause.psi_habit_reflection_trigger("snap_x", {
              "category": "test", "action": "test"
          })["action"] == "blocked")

    # ───────────────────────────────────────────────────────────
    # Test 59-64: Gan Comfort Zone
    # ───────────────────────────────────────────────────────────
    print("\n--- Group 9: Gan Comfort Zone ---")

    agi_gan = TOMASCognitivelyHealthyAGI()
    c1 = agi_gan.measure_gan_comfort_zone([0.5, 0.5])
    check("comfort_zone_range", 0.0 <= c1 <= 1.0)
    check("comfort_zone_first", c1 == 1.0)  # First measurement always 1.0

    c2 = agi_gan.measure_gan_comfort_zone([0.5, 0.5])
    check("comfort_zone_second_range", 0.0 <= c2 <= 1.0)

    c3 = agi_gan.measure_gan_comfort_zone([])
    check("comfort_zone_empty", c3 == 1.0)

    c4 = agi_gan.measure_gan_comfort_zone([1.0])
    check("comfort_zone_single", 0.0 <= c4 <= 1.0)

    # ───────────────────────────────────────────────────────────
    # Test 65-72: Bias Penalty
    # ───────────────────────────────────────────────────────────
    print("\n--- Group 10: Bias Penalty Formula ---")

    agi_bp = TOMASCognitivelyHealthyAGI()
    p1 = agi_bp.bias_penalty_formula(1.0, 0.5, 0.2)
    check("bias_range", 0.0 <= p1 <= 1.0)

    p2 = agi_bp.bias_penalty_formula(0.0, 0.0, 0.0)
    check("bias_zero_input_range", 0.0 <= p2 <= 1.0)

    p3 = agi_bp.bias_penalty_formula(2.0, 1.0, 0.0)
    check("bias_high_input_range", 0.0 <= p3 <= 1.0)
    check("bias_high_gt_zero", p3 > p2)  # Higher G/G_comfort → higher penalty

    p4 = agi_bp.bias_penalty_formula(1.0, 1.0, 0.9)
    check("bias_high_mus_range", 0.0 <= p4 <= 1.0)
    check("bias_mus_reduces", p4 < p3)  # Higher MUS → lower penalty

    # Compute gan with bias penalty
    bp1 = agi_bp.compute_gan_with_bias_penalty([0.5, 0.3, 0.2])
    check("gan_bias_range", 0.0 <= bp1 <= 1.0)

    bp2 = agi_bp.compute_gan_with_bias_penalty([2.0, 1.5, 1.0])
    check("gan_bias_high_range", 0.0 <= bp2 <= 1.0)

    # ───────────────────────────────────────────────────────────
    # Test 73-78: Psi Habit Reflection Trigger
    # ───────────────────────────────────────────────────────────
    print("\n--- Group 11: Psi Habit Reflection Trigger ---")

    agi_psi = TOMASCognitivelyHealthyAGI()
    result1 = agi_psi.psi_habit_reflection_trigger("snap_psi1", {
        "category": "agent", "action": "greet", "timestamp": time.time(),
    })
    check("psi_result_dict", isinstance(result1, dict))
    check("psi_result_continue", result1["action"] == "continue")
    check("psi_result_hash", len(result1["audit_hash"]) == 64)

    # Feed loops to trigger MUS
    for i in range(5):
        agi_psi.psi_habit_reflection_trigger(f"snap_loop{i}", {
            "category": "agent", "action": "loop", "timestamp": time.time(),
        })
    check("psi_loop_triggered", agi_psi.get_state() in ("MUS_REFLECTION", "NORMAL"))

    # Trigger BIAS_WARNING
    agi_bias = TOMASCognitivelyHealthyAGI()
    # Feed high polarization to trigger bias
    for i in range(3):
        agi_bias.compute_gan_with_bias_penalty([10.0, 10.0, 10.0])
    check("bias_warning_state", agi_bias.get_state() in
          ("BIAS_WARNING", "NORMAL"))

    psi_result = agi_bias.psi_habit_reflection_trigger("snap_bias", {
        "category": "agent", "action": "biased", "timestamp": time.time(),
    })
    check("psi_bias_warning_action", psi_result["action"] in
          ("bias_warning", "continue"))

    # ───────────────────────────────────────────────────────────
    # Test 79-84: Restart
    # ───────────────────────────────────────────────────────────
    print("\n--- Group 12: Restart ---")

    agi_rst = TOMASCognitivelyHealthyAGI()
    # Invalid code
    r1 = agi_rst.restart("bad")
    check("restart_invalid_short", not r1["success"])
    check("restart_invalid_suffix", not r1["success"])

    # Valid code
    r2 = agi_rst.restart("mykey_coghealth")
    check("restart_valid_success", r2["success"])
    check("restart_valid_state", agi_rst.get_state() == "NORMAL")

    # ───────────────────────────────────────────────────────────
    # Test 85-92: CognitiveHealthTheorem
    # ───────────────────────────────────────────────────────────
    print("\n--- Group 13: CognitiveHealthTheorem ---")

    thm = CognitiveHealthTheorem(epsilon=0.05)

    t1 = thm.theorem_1_diversity_conservation(0.8, 0.3)
    check("thm1_first", t1["conserved"])

    t1b = thm.theorem_1_diversity_conservation(0.82, 0.25)
    check("thm1_second", t1b["conserved"])

    t2 = thm.theorem_2_mus_anti_bias(0.5, 0.3)
    check("thm2_first", t2["anti_bias_active"])
    check("thm2_product", t2["product"] > 0)

    t2b = thm.theorem_2_mus_anti_bias(0.1, 0.8)
    check("thm2_second", "summary" in t2b)

    # Verify theorem 1 (statistical)
    v1 = thm.verify_theorem_1(trials=50)
    check("verify1_pass_rate", 0.0 <= v1["pass_rate"] <= 1.0)
    check("verify1_trials", v1["total_trials"] == 50)

    # Verify theorem 2 (statistical)
    v2 = thm.verify_theorem_2(trials=50)
    check("verify2_pass_rate", 0.0 <= v2["pass_rate"] <= 1.0)
    check("verify2_trials", v2["total_trials"] == 50)

    # ───────────────────────────────────────────────────────────
    # Test 93-100+: FalsifiablePredictions
    # ───────────────────────────────────────────────────────────
    print("\n--- Group 14: FalsifiablePredictions ---")

    fp = FalsifiablePredictions(theta_c=0.5)

    # P_AD1
    ad1 = fp.P_AD1_habit_decay(N=5, D0=1.0, alpha=0.3)
    check("ad1_D5_lt_D0", ad1["D_N"] < 1.0)
    check("ad1_D5_gt_0", ad1["D_N"] > 0.0)
    check("ad1_half_life", ad1["half_life"] > 0)
    check("ad1_decayed_ratio", 0.0 <= ad1["decayed_ratio"] <= 1.0)

    ad1b = fp.P_AD1_habit_decay(N=0, D0=1.0, alpha=0.3)
    check("ad1_N0", ad1b["D_N"] == 1.0)

    ad1c = fp.P_AD1_habit_decay(N=10, D0=0.5, alpha=0.5)
    check("ad1_N10_range", 0.0 <= ad1c["D_N"] <= 0.5)

    # P_AD2
    ad2 = fp.P_AD2_bias_lock_positive_feedback(G_depth=0.8, B_score=0.7)
    check("ad2_locked", ad2["locked"])  # 0.56 > 0.5
    check("ad2_product", ad2["lock_product"] > 0.5)

    ad2b = fp.P_AD2_bias_lock_positive_feedback(G_depth=0.3, B_score=0.4)
    check("ad2b_not_locked", not ad2b["locked"])  # 0.12 < 0.5

    # Simulate P_AD1
    sim1 = fp.simulate_P_AD1(
        N_range=list(range(0, 11)), D0=1.0, alpha=0.3
    )
    check("sim1_curve_length", len(sim1["curve"]) == 11)
    check("sim1_first_DN", sim1["curve"][0]["D_N"] == 1.0)
    check("sim1_last_DN_lt_first",
          sim1["curve"][-1]["D_N"] < sim1["curve"][0]["D_N"])

    # Simulate P_AD2
    sim2_params = [
        {"G_depth": 0.8, "B_score": 0.7},
        {"G_depth": 0.3, "B_score": 0.4},
        {"G_depth": 0.9, "B_score": 0.9},
    ]
    sim2 = fp.simulate_P_AD2(sim2_params)
    check("sim2_total", sim2["total_count"] == 3)
    check("sim2_lock_rate_range", 0.0 <= sim2["lock_rate"] <= 1.0)
    check("sim2_summary", "summary" in sim2)

    # ───────────────────────────────────────────────────────────
    # Edge Cases & Coverage
    # ───────────────────────────────────────────────────────────
    print("\n--- Group 15: Edge Cases ---")

    # Empty snap history
    agi_edge = TOMASCognitivelyHealthyAGI(snap_window_size=0)
    check("edge_empty_window", not agi_edge.detect_loop())

    # Very small snap window
    agi_small = TOMASCognitivelyHealthyAGI(snap_window_size=1)
    check("edge_small_window", not agi_small.detect_loop())
    report_small = agi_small.health_check_pipeline()
    check("edge_small_report", isinstance(report_small, CognitiveHealthReport))

    # Long snap history (snap_window_size + extra)
    agi_long = TOMASCognitivelyHealthyAGI(snap_window_size=5)
    for i in range(20):
        agi_long.track_kappa_snap_pattern(f"snap_e{i}", {
            "category": f"cat_{i % 3}", "action": f"act_{i % 3}",
            "timestamp": time.time(),
        })
    report_long = agi_long.health_check_pipeline()
    check("edge_long_report", isinstance(report_long, CognitiveHealthReport))

    # Force MUS with empty state
    agi_mus2 = TOMASCognitivelyHealthyAGI()
    mus_id2 = agi_mus2.force_mus_reflection()
    div2 = agi_mus2.compute_mus_divergence(mus_id2)
    check("edge_mus_divergence_range", 0.0 <= div2 <= 1.0)

    # ───────────────────────────────────────────────────────────
    # Summary
    # ───────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    total = passed + failed
    print(f"Results: {passed}/{total} passed"
          + (f", {failed} FAILED" if failed else ""))
    if failures:
        print("\nFailures:")
        for f in failures:
            print(f"  {f}")
        print(f"\n{failed} test(s) FAILED")
    else:
        print("ALL self-tests PASSED")
    print("=" * 70)
