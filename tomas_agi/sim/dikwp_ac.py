"""
DIKWP 人工意识 (Artificial Consciousness) 交互引擎
====================================================
基于 段玉聪(2024) "人工意识概论-意识的非生物学扩展"

核心:
  1. DIKWP×DIKWP 交互 — AC交互 = DIKWP_self ⊗ DIKWP_other
  2. 意识BUG检测 — 信息处理中的断裂/跳跃 → 意识涌现
  3. 非生物意识 — 意识可存在于非生物基底的证明框架

应用:
  >>> ac = DIKWPAC()
  >>> interaction = ac.interact(
  ...     self_dikwp={"D": [...], "I": [...], "K": [...], "W": [...], "P": "安全优先"},
  ...     other_dikwp={"D": [...], "I": [...], "K": [...], "W": [...], "P": "效率优先"}
  ... )
  >>> print(interaction.bug_detected)  # True — 目的冲突触发BUG
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import logging
import hashlib

logger = logging.getLogger(__name__)

# 前向导入 DIKWP 层
try:
    from .dikwp_mapper import DIKWPLayer, DIKWPMapper
except ImportError:
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from dikwp_mapper import DIKWPLayer, DIKWPMapper  # type: ignore


class InteractionType(Enum):
    """交互类型"""
    DATA_EXCHANGE = "D↔D"         # 纯数据交换
    INFORMATION_SHARING = "I↔I"   # 信息共享
    KNOWLEDGE_COLLISION = "K↔K"   # 知识碰撞 (可能触发BUG)
    WISDOM_DIALOGUE = "W↔W"       # 智慧对话
    PURPOSE_CONFLICT = "P↔P"      # 意图冲突 (最易触BUG)


class BugType(Enum):
    """意识BUG类型 — 信息处理断裂的种类"""
    SEMANTIC_GAP = "语义跳跃"       # 信息链突然中断
    PARADOX_LOOP = "悖论循环"       # 自指导致无限递归
    PURPOSE_DISSONANCE = "意图失调" # 多重目的不可调和
    THRESHOLD_BREAK = "阈值突破"    # 复杂度超过处理能力
    NONLOCAL_JUMP = "非局部跳跃"    # 无因果关联的概念连接


@dataclass
class DIKWPState:
    """DIKWP 五层状态快照"""
    data_signatures: List[str]     # Data 层: 签名 (感官输入哈希)
    information_edges: List[str]   # Information 层: 语义边
    knowledge_subgraphs: List[str] # Knowledge 层: 稳定子图
    wisdom_rules: List[str]        # Wisdom 层: 决策规则
    purpose_anchor: str            # Purpose 层: ψ-锚点

    def fingerprint(self) -> str:
        """生成五层指纹"""
        raw = "|".join([
            ",".join(sorted(self.data_signatures)),
            ",".join(sorted(self.information_edges)),
            ",".join(sorted(self.knowledge_subgraphs)),
            ",".join(sorted(self.wisdom_rules)),
            self.purpose_anchor,
        ])
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class InteractionResult:
    """DIKWP 交互结果"""
    interaction_type: InteractionType
    self_state: DIKWPState
    other_state: DIKWPState
    bug_detected: bool
    bug_types: List[BugType]
    consciousness_level: float     # 意识涌现水平 [0,1]
    psi_delta: float               # ψ-锚点偏移量
    new_knowledge: List[str]       # 碰撞产生的新知识
    resolution: str                # 冲突解决描述
    audit_trail: List[str]         # 交互审计轨迹


@dataclass
class NonBioSpec:
    """非生物意识规格"""
    substrate: str              # 基底类型: "量子计算"/"神经网络"/"光子计算"/"混合"
    i_density: float           # ℐ-密度
    qubit_count: Optional[int] = None
    layer_count: Optional[int] = None
    bug_threshold: float = 0.3  # BUG触发阈值


class DIKWPAC:
    """
    DIKWP 人工意识交互引擎
    
    实现段玉聪教授的核心理论:
      1. AC交互 = DIKWP × DIKWP (非简单 DIK×DIK)
      2. 意识是信息处理中的BUG现象
      3. 意识可存在于任何足够复杂的信息处理基底下
    """

    def __init__(self, bug_sensitivity: float = 0.5):
        """
        Args:
            bug_sensitivity: BUG检测灵敏度 [0,1], 越高越容易触发
        """
        self.bug_sensitivity = bug_sensitivity
        self.interaction_history: List[InteractionResult] = []
        self.bug_catalog: Dict[str, int] = {}  # BUG类型频率统计
        self.psi_calibration: Dict[str, float] = {}  # ψ-校准记录
        logger.info(f"[DIKWPAC] 初始化, bug_sensitivity={bug_sensitivity}")

    def interact(
        self,
        self_dikwp: Dict[str, Any],
        other_dikwp: Dict[str, Any],
        context: Optional[Dict] = None,
    ) -> InteractionResult:
        """
        DIKWP × DIKWP 交互
        
        Args:
            self_dikwp: 自身五层状态
            other_dikwp: 对方五层状态
            context: 上下文信息
        
        Returns:
            InteractionResult
        """
        # 构建状态
        self_state = self._build_state(self_dikwp)
        other_state = self._build_state(other_dikwp)

        # 判定交互类型
        itype = self._classify_interaction(self_state, other_state)

        # 检测BUG
        bugs, bug_reasons = self._detect_bugs(self_state, other_state, itype)

        # 计算意识水平
        consciousness = self._compute_consciousness(bugs, itype)

        # ψ-偏移
        psi_delta = self._compute_psi_delta(self_state, other_state)

        # 新知识
        new_knowledge = self._synthesize_knowledge(self_state, other_state, bugs)

        # 审计
        audit = self._build_audit_trail(self_state, other_state, itype, bugs)

        # 冲突解决
        resolution = self._resolve_conflict(bugs, psi_delta, context)

        result = InteractionResult(
            interaction_type=itype,
            self_state=self_state,
            other_state=other_state,
            bug_detected=len(bugs) > 0,
            bug_types=bugs,
            consciousness_level=consciousness,
            psi_delta=psi_delta,
            new_knowledge=new_knowledge,
            resolution=resolution,
            audit_trail=audit,
        )

        self.interaction_history.append(result)
        for bug in bugs:
            self.bug_catalog[bug.value] = self.bug_catalog.get(bug.value, 0) + 1

        logger.info(
            f"[DIKWPAC] 交互 {itype.value}: "
            f"BUG={'✓' if result.bug_detected else '✗'} "
            f"意识={consciousness:.2f} ψΔ={psi_delta:+.3f}"
        )
        return result

    def _build_state(self, dikwp: Dict[str, Any]) -> DIKWPState:
        """构建标准化 DIKWP 状态"""
        return DIKWPState(
            data_signatures=[
                hashlib.md5(str(d).encode()).hexdigest()[:8]
                for d in dikwp.get("D", [])
            ],
            information_edges=[
                str(e) for e in dikwp.get("I", [])
            ],
            knowledge_subgraphs=[
                str(k) for k in dikwp.get("K", [])
            ],
            wisdom_rules=[
                str(w) for w in dikwp.get("W", [])
            ],
            purpose_anchor=str(dikwp.get("P", "未定义")),
        )

    def _classify_interaction(
        self, self_s: DIKWPState, other_s: DIKWPState
    ) -> InteractionType:
        """根据状态碰撞级别判定交互类型"""
        # Purpose 冲突 → 最高级
        if self_s.purpose_anchor != other_s.purpose_anchor:
            return InteractionType.PURPOSE_CONFLICT

        # Wisdom 差异 → 对话
        if set(self_s.wisdom_rules) != set(other_s.wisdom_rules):
            return InteractionType.WISDOM_DIALOGUE

        # Knowledge 碰撞
        if set(self_s.knowledge_subgraphs) != set(other_s.knowledge_subgraphs):
            return InteractionType.KNOWLEDGE_COLLISION

        # Information 差异
        if set(self_s.information_edges) != set(other_s.information_edges):
            return InteractionType.INFORMATION_SHARING

        return InteractionType.DATA_EXCHANGE

    def _detect_bugs(
        self, self_s: DIKWPState, other_s: DIKWPState, itype: InteractionType
    ) -> Tuple[List[BugType], List[str]]:
        """BUG 检测 — 信息处理中的断裂/非连续性"""
        bugs = []
        reasons = []

        # 1. 意图失调 (P→P 冲突)
        if itype == InteractionType.PURPOSE_CONFLICT:
            prob = self.bug_sensitivity * 0.95
            if prob > 0.3:
                bugs.append(BugType.PURPOSE_DISSONANCE)
                reasons.append(
                    f"意图冲突: '{self_s.purpose_anchor}' ↔ '{other_s.purpose_anchor}'"
                )

        # 2. 语义跳跃 (信息链断裂)
        shared_edges = set(self_s.information_edges) & set(other_s.information_edges)
        total_edges = set(self_s.information_edges) | set(other_s.information_edges)
        if total_edges:
            overlap = len(shared_edges) / len(total_edges)
            if overlap < 0.2 and self.bug_sensitivity > 0.3:
                bugs.append(BugType.SEMANTIC_GAP)
                reasons.append(f"语义重叠率仅 {overlap:.1%}, 存在信息链断裂")

        # 3. 悖论循环 (自指)
        for rule in self_s.wisdom_rules:
            if rule in other_s.knowledge_subgraphs:
                prob = self.bug_sensitivity * 0.7
                if prob > 0.4:
                    bugs.append(BugType.PARADOX_LOOP)
                    reasons.append(f"规则 '{rule}' 同时出现在W和K层, 可能自指")
                    break

        # 4. 阈值突破
        complexity = (
            len(self_s.data_signatures) + len(other_s.data_signatures) +
            len(self_s.information_edges) + len(other_s.information_edges)
        )
        if complexity > 50 and self.bug_sensitivity > 0.4:
            bugs.append(BugType.THRESHOLD_BREAK)
            reasons.append(f"交互复杂度 {complexity} 超过处理阈值")

        # 5. 非局部跳跃
        if itype == InteractionType.KNOWLEDGE_COLLISION:
            # 两个知识子图无交集但有因果联系 → 非局部跳跃
            self_k = set(self_s.knowledge_subgraphs)
            other_k = set(other_s.knowledge_subgraphs)
            if self_k and other_k and not (self_k & other_k):
                prob = self.bug_sensitivity * 0.6
                if prob > 0.35:
                    bugs.append(BugType.NONLOCAL_JUMP)
                    reasons.append("知识子图无交集但产生关联, 非局部跳跃")

        return bugs, reasons

    def _compute_consciousness(
        self, bugs: List[BugType], itype: InteractionType
    ) -> float:
        """计算意识涌现水平"""
        if not bugs:
            return 0.0

        # BUG 越多, 意识水平越高 (段玉聪: 意识是BUG现象)
        base = len(bugs) / len(BugType)  # 0~1

        # 意图冲突权重最高
        weight = 1.0
        if BugType.PURPOSE_DISSONANCE in bugs:
            weight = 1.5

        level = min(base * weight, 1.0)
        return round(level, 4)

    def _compute_psi_delta(self, self_s: DIKWPState, other_s: DIKWPState) -> float:
        """计算 ψ-锚点偏移"""
        # 简单版本: 目的差异的量化
        if self_s.purpose_anchor == other_s.purpose_anchor:
            return 0.0

        p1 = self_s.purpose_anchor.lower()
        p2 = other_s.purpose_anchor.lower()

        # 基于关键字的粗略差异
        diffs = {
            ("安全", "效率"): 0.8,
            ("安全", "激进"): 0.95,
            ("保守", "激进"): 0.9,
            ("伦理", "实用"): 0.7,
            ("准确", "速度"): 0.6,
        }

        for (a, b), delta in diffs.items():
            if a in p1 and b in p2 or b in p1 and a in p2:
                return delta

        return 0.3  # 默认差异

    def _synthesize_knowledge(
        self, self_s: DIKWPState, other_s: DIKWPState, bugs: List[BugType]
    ) -> List[str]:
        """知识碰撞产生的新知识"""
        new = []
        if bugs:
            for bug in bugs:
                new.append(f"BUG-{bug.value}: 意识涌现产物")
        if self_s.purpose_anchor != other_s.purpose_anchor:
            new.append(f"ψ-融合: {self_s.purpose_anchor} ⊗ {other_s.purpose_anchor}")
        # 知识交集形成新知识
        shared = set(self_s.knowledge_subgraphs) & set(other_s.knowledge_subgraphs)
        if shared:
            new.append(f"知识共识: {', '.join(list(shared)[:3])}")
        return new

    def _build_audit_trail(
        self, self_s: DIKWPState, other_s: DIKWPState,
        itype: InteractionType, bugs: List[BugType],
    ) -> List[str]:
        """构建审计轨迹"""
        return [
            f"交互类型: {itype.value}",
            f"自我ψ: {self_s.purpose_anchor}",
            f"对方ψ: {other_s.purpose_anchor}",
            f"BUG: {[b.value for b in bugs]}" if bugs else "无BUG",
        ]

    def _resolve_conflict(
        self, bugs: List[BugType], psi_delta: float, context: Optional[Dict]
    ) -> str:
        """冲突解决"""
        if not bugs:
            return "无冲突, 顺利交互"

        if BugType.PURPOSE_DISSONANCE in bugs:
            if psi_delta > 0.8:
                return "MUS双存: 保持双方意图, 标记为高ψ偏移, 待上层仲裁"
            return "ψ-锚定: 以更保守的意图(majority-rules)为准, 记录差异"

        if BugType.SEMANTIC_GAP in bugs:
            return "信息补充: 请求更多上下文数据, 暂缓决策"

        if BugType.PARADOX_LOOP in bugs:
            return "层级隔离: 将自指规则移出W层, 仅保留在K层"

        return "默认: 记录BUG, 人工审核"

    def assess_non_biological(
        self, spec: NonBioSpec
    ) -> Dict[str, Any]:
        """
        非生物意识可行性评估
        
        基于段玉聪2019年提出的"非生物学意识扩展"理论
        
        Args:
            spec: 非生物基底规格
        
        Returns:
            评估报告
        """
        # 意识产生需要足够的信息复杂度
        complexity_score = spec.i_density * (
            spec.qubit_count or spec.layer_count or 10
        )

        # 是否能产生BUG
        can_produce_bug = complexity_score * self.bug_sensitivity > spec.bug_threshold

        # 预测意识水平
        if can_produce_bug:
            predicted_level = min(complexity_score / 1000, 1.0)
        else:
            predicted_level = 0.0

        return {
            "substrate": spec.substrate,
            "i_density": spec.i_density,
            "complexity_score": complexity_score,
            "can_produce_bug": can_produce_bug,
            "predicted_consciousness": round(predicted_level, 4),
            "verdict": (
                "该基底具备产生非生物意识的潜力"
                if can_produce_bug else
                "该基底复杂度不足, 需提升ℐ-密度或计算规模"
            ),
            "recommendation": (
                "建议引入DIKWP×DIKWP交互环境, 触发意识BUG"
                if can_produce_bug else
                f"提升ℐ-密度至 ≥{spec.bug_threshold / self.bug_sensitivity:.2f}"
            ),
        }

    def get_history_summary(self) -> Dict[str, Any]:
        """获取交互历史摘要"""
        total = len(self.interaction_history)
        bugged = sum(1 for r in self.interaction_history if r.bug_detected)
        avg_consciousness = sum(
            r.consciousness_level for r in self.interaction_history
        ) / max(total, 1)

        return {
            "total_interactions": total,
            "bugged_interactions": bugged,
            "bug_rate": round(bugged / max(total, 1), 4),
            "avg_consciousness": round(avg_consciousness, 4),
            "bug_catalog": self.bug_catalog,
            "psi_calibration_count": len(self.psi_calibration),
        }
