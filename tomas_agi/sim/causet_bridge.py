"""
Causet-Wolfram → TOMAS 桥接器

将算法因果集 (Causal Set) 和 Wolfram 超图重写映射到
TOMAS EML 超图演化 + 死零 Guard + MUS 标记。

参考: 章锋 (2026) "太一互搏范式下的算法因果集与 Wolfram 超图重写"
"""

import math
import random
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================
# 数据结构
# ============================================================

class UpdateEventType(Enum):
    """Wolfram Model 更新事件类型"""
    HYPEREDGE_ACTIVATION = "hyperedge_activation"
    RULE_APPLICATION = "rule_application"
    DEAD_ZERO_REJECT = "dead_zero_reject"
    MUS_BRANCH = "mus_branch"
    K_SNAP_COLLAPSE = "k_snap_collapse"


@dataclass
class CausetEvent:
    """因果集事件 (Causet element)"""
    id: str
    spacetime_coord: Tuple[float, float, float, float]  # (t, x, y, z) 简化
    i_value: float          # ℐ-存在度
    event_type: UpdateEventType
    causes: List[str] = field(default_factory=list)      # 因果前驱 ID
    effects: List[str] = field(default_factory=list)     # 因果后继 ID


@dataclass
class WolframRule:
    """Wolfram Model 重写规则"""
    id: str
    pattern: Dict              # 子超图匹配模式
    replacement: Dict          # 替换目标
    i_threshold: float = 0.15  # TOMAS 死零阈值


@dataclass
class MultiwayBranch:
    """多路系统分支 (Multiway Branch)"""
    id: str
    states: List[str]           # 候选超图状态 ID
    asymmetry: float = 0.0      # Asym 值
    is_mus: bool = False        # 是否 MUS 双存
    collapsed_to: Optional[str] = None  # κ-Snap 坍缩结果


# ============================================================
# Causet-Wolfram → EML 桥接
# ============================================================

class CausetEMLBridge:
    """因果集→EML 超图桥接器

    映射关系 (文章1 §1.1):
      - Wolfram 空间超图 H_t ⇔ EML 超图在时刻 κ-Snap
      - 更新规则 R ⇔ NASGA (非结合谱图代数 ⊗₈) 沿超边传播
      - 因果网络 C ⇔ κ-时间轴 (因果偏序 ≺ = TOMAS 时序优先)
    """

    def __init__(self, theta_dead: float = 0.15):
        self.theta_dead = theta_dead
        self.events: Dict[str, CausetEvent] = {}
        self.branches: Dict[str, MultiwayBranch] = {}
        self.rules: Dict[str, WolframRule] = {}
        self.i_total: float = 0.0       # ℐ-总量 (用于 ℐ-守恒验证)

    def add_event(self, event_id: str, coords: Tuple[float, float, float, float],
                  i_val: float, event_type: UpdateEventType,
                  causes: List[str] = None) -> CausetEvent:
        """添加因果集事件"""
        event = CausetEvent(
            id=event_id, spacetime_coord=coords, i_value=i_val,
            event_type=event_type, causes=causes or [],
        )
        self.events[event_id] = event
        self.i_total += i_val

        # 更新因果链
        for cause_id in (causes or []):
            if cause_id in self.events:
                self.events[cause_id].effects.append(event_id)

        return event

    def add_rule(self, rule_id: str, pattern: Dict, replacement: Dict,
                 i_threshold: float = None) -> WolframRule:
        """注册 Wolfram 重写规则"""
        rule = WolframRule(
            id=rule_id, pattern=pattern, replacement=replacement,
            i_threshold=i_threshold or self.theta_dead,
        )
        self.rules[rule_id] = rule
        return rule

    # ----------------------------------------------------------
    # DPO Match 死零守卫
    # ----------------------------------------------------------

    def rule_match_allowed(self, rule_id: str, eml_hypergraph: Dict,
                           pattern_i: float = None) -> Tuple[bool, str]:
        """DPO Match 死零守卫 — rule_match_allowed 伪代码实现

        参考: 文章1 附录 D

        Args:
            rule_id: Wolfram 重写规则 ID
            eml_hypergraph: 当前 EML 超图状态 {'vertices': [...], 'edges': [...]}
            pattern_i: 匹配模式的 ℐ-值 (None 则从超图自动计算)

        Returns:
            (allowed, reason): 是否允许应用规则 + 原因
        """
        rule = self.rules.get(rule_id)
        if not rule:
            return False, f"规则 {rule_id} 未注册"

        # 计算匹配模式的总 ℐ
        if pattern_i is None:
            pattern_i = self._compute_pattern_i(rule.pattern, eml_hypergraph)

        # 死零检查: ℐ < θ_dead ⇒ Reject
        if pattern_i < rule.i_threshold:
            logger.info(f"[DPO Guard] REJECT {rule_id}: "
                        f"I={pattern_i:.4f} < θ={rule.i_threshold}")
            return False, f"REJECT_RULE_MATCH: I={pattern_i:.4f} < θ={rule.i_threshold}"

        # MUS 检查 (从 hypergraph 状态中读取)
        mus_flags = eml_hypergraph.get("_mus_flags", {})
        if mus_flags.get("active") and not mus_flags.get("allow_coarse_graining"):
            return False, "MUS_BLOCKED: 需要 ψ-锚明确决议"

        return True, f"ALLOWED: I={pattern_i:.4f} >= θ={rule.i_threshold}"

    def _compute_pattern_i(self, pattern: Dict, hypergraph: Dict) -> float:
        """计算匹配模式在超图中的 ℐ-值"""
        edges = hypergraph.get("edges", [])
        pattern_nodes = set(pattern.get("nodes", []))

        total_i = 0.0
        matched = 0
        for edge in edges:
            edge_nodes = set(edge.get("nodes", []))
            if pattern_nodes.issubset(edge_nodes) or edge_nodes.issubset(pattern_nodes):
                total_i += edge.get("i_val", 0.0)
                matched += 1

        if matched == 0:
            return 0.0
        return total_i / matched  # 归一化

    # ----------------------------------------------------------
    # ℐ-Sprinkling (替代 Poisson Sprinkling)
    # ----------------------------------------------------------

    def i_sprinkling(self, n_events: int, spacetime_volume: float,
                     i_distribution: str = "uniform") -> List[CausetEvent]:
        """ℐ-Sprinkling 生成因果集事件

        参考: 文章1 §4.3

        替代标准 Causal Set 的 Poisson Sprinkling:
        - 若 ℐ 均匀 → Poisson 是一阶近似
        - 若 ℐ 结构化 → 非-Poisson ℐ-Sprinkling

        Args:
            n_events: 事件数
            spacetime_volume: 时空体积
            i_distribution: ℐ 分布类型 ("uniform"|"clustered"|"filament")
        """
        events = []
        density = n_events / max(spacetime_volume, 1.0)

        for i in range(n_events):
            # ℐ-Sprinkling 坐标 (加权 by ℐ 分布)
            if i_distribution == "clustered":
                # 团状结构: ℐ 集中在几个区域
                cluster = random.randint(0, 3)
                coords = tuple(
                    random.gauss(cluster * 0.25, 0.05)
                    for _ in range(4)
                )
                i_val = random.uniform(0.5, 1.0)
            elif i_distribution == "filament":
                # 纤维结构: ℐ 沿一维延伸
                t = random.uniform(0, 1)
                coords = (t, random.gauss(0.5, 0.1), random.gauss(0.5, 0.1), random.gauss(0.5, 0.1))
                i_val = 0.3 + 0.4 * abs(math.sin(t * math.pi * 5))
            else:
                # 均匀 (Poisson 近似)
                coords = tuple(random.random() for _ in range(4))
                i_val = density

            event = self.add_event(
                event_id=f"spk_{i}", coords=coords, i_val=i_val,
                event_type=UpdateEventType.HYPEREDGE_ACTIVATION,
            )
            events.append(event)

        return events

    # ----------------------------------------------------------
    # 多路系统 (Multiway) MUS 标记
    # ----------------------------------------------------------

    def detect_multiway_mus(self, branches: List[MultiwayBranch],
                            asymmetry_threshold: float = 0.01) -> List[MultiwayBranch]:
        """多路系统 MUS 检测与标记

        参考: 文章1 §1.4, §4.2

        若两历史前缀引出矛盾结论但 ℐ 相当 ⇒ 标记 [MUS_ACTIVE]
        """
        mus_branches = []
        for branch in branches:
            if abs(branch.asymmetry) > asymmetry_threshold:
                branch.is_mus = True
                branch.collapsed_to = None  # 不坍缩, 保留双状态
                mus_branches.append(branch)
                logger.info(f"[Multiway] MUS_ACTIVE: {branch.id} "
                            f"Asym={branch.asymmetry:.4f} ≠ 0")

        return mus_branches

    def collapse_multiway(self, branches: List[MultiwayBranch],
                          psi_anchor: str = None) -> List[MultiwayBranch]:
        """κ-Snap 坍缩多路分支

        ψ-锚择显影: 阴阳平秘/伦理两难/六经厥阴
        """
        for branch in branches:
            if branch.is_mus:
                if psi_anchor and branch.collapsed_to is None:
                    # ψ-锚 决策
                    branch.collapsed_to = branch.states[0] if random.random() > 0.5 else branch.states[1]
                    logger.info(f"[κ-Snap] 坍缩 {branch.id} → {branch.collapsed_to} (ψ-锚: {psi_anchor})")
                # 否则保留双存
            else:
                # 非 MUS: 合流
                branch.collapsed_to = branch.states[0]

        return branches

    # ----------------------------------------------------------
    # ℐ-守恒因果不变性验证
    # ----------------------------------------------------------

    def verify_causal_invariance(self, events: List[CausetEvent] = None) -> Dict:
        """验证因果不变性 ⇔ ℐ-守恒 (Axiom A1)

        参考: 文章1 §1.2

        因果不变性 (合流) 保证不同叶层化得同构因果偏序
        ⇔ ℐ-流沿任意叶层化守恒 (Σℐ(e)=Const)
        """
        target = events or list(self.events.values())
        total_i = sum(e.i_value for e in target)

        # 因果链验证: 每个事件的前驱 ℐ 之和应 ≈ 自身 ℐ
        chain_violations = 0
        for event in target:
            cause_i = sum(
                self.events[c].i_value
                for c in event.causes if c in self.events
            )
            if cause_i > 0 and abs(cause_i - event.i_value) / max(cause_i, 0.01) > 0.5:
                chain_violations += 1

        return {
            "total_i": total_i,
            "event_count": len(target),
            "chain_violations": chain_violations,
            "causal_invariance_holds": chain_violations == 0,
            "i_conserved": abs(total_i - self.i_total) / max(self.i_total, 0.01) < 0.1,
        }

    # ----------------------------------------------------------
    # Benincasa-Dowker Action ⇔ TOMAS 宇宙学作用量
    # ----------------------------------------------------------

    def bd_action_approximation(self, simplices_by_dim: Dict[int, int]) -> float:
        """Benincasa-Dowker 作用量近似

        参考: 文章1 §1.3

        S_BD ∝ Σ(-1)^k N_k
        = TOMAS R+R² 宇宙学作用量在 κ≈7→κ≈4 的投影
        """
        action = 0.0
        for dim, count in simplices_by_dim.items():
            action += ((-1) ** dim) * count
        return action

    def tomas_cosmology_action(self, simplices_by_dim: Dict[int, int],
                               i_entropy: float = 0.0,
                               r_squared_correction: float = 0.0) -> float:
        """TOMAS 宇宙学作用量 (含 ℐ-熵 + R² 修正)

        S_TOMAS = S_BD + ∫ℐlnℐ + R² 高阶修正
        """
        bd = self.bd_action_approximation(simplices_by_dim)
        return bd + i_entropy + r_squared_correction


# ============================================================
# 导出
# ============================================================

__all__ = [
    "UpdateEventType",
    "CausetEvent",
    "WolframRule",
    "MultiwayBranch",
    "CausetEMLBridge",
]
