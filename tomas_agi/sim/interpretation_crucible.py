# -*- coding: utf-8 -*-
"""
Interpretation Crucible v1.0 — 多诠释兼容坩埚
===============================================

基于论文：
  "论太乙互搏对多诠释现象的兼容"
  微信公众号文章 (2026-06-22)

核心功能：
  01. 波粒二象解析 — Wave-Particle 诠释双路径并行
  02. 多世界诠释 — Many-Worlds 分支管理 + 贝叶斯融合
  03. MUS 双存裁决 — 互斥稳态渐进裁决
  04. 诠释切换引擎 — 基于 ℐ 权重的诠释模式切换
  05. 诠释谱系图 — 决策血统全链路追溯

集成到现有 TOMAS：
  - psi_gate.py: φ-Gate 多世界路径
  - dead_zero_mus.py: MUS 双存裁决增强
  - eml_semzip.py: EMLLiteKB 多诠释超边

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
from enum import Enum
from collections import defaultdict

logger = logging.getLogger(__name__)

try:
    from .eml_semzip import EMLHypergraph, HyperEdge
except ImportError:
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from eml_semzip import EMLHypergraph, HyperEdge  # type: ignore


# ══════════════════════════════════════════════════════════════════
# 枚举
# ══════════════════════════════════════════════════════════════════

class InterpretationParadigm(Enum):
    """诠释范式"""
    WAVE = "wave"               # 波动诠释 — 超边概率叠加态
    PARTICLE = "particle"       # 粒子诠释 — 确定性因果链
    MANY_WORLDS = "many_worlds" # 多世界诠释 — 平行分支
    COPENHAGEN = "copenhagen"   # 哥本哈根诠释 — 观测坍缩
    BOHMIAN = "bohmian"         # 玻姆诠释 — 隐变量引导
    QBISM = "qbism"             # QBism — 主观贝叶斯


class BranchStatus(Enum):
    """世界分支状态"""
    ACTIVE = "active"
    DECOHERED = "decohered"    # 退相干
    MERGED = "merged"          # 已融合
    PRUNED = "pruned"          # 已剪枝
    DOMINANT = "dominant"      # 主导分支


class CruState(Enum):
    """坩埚状态"""
    OPEN = "open"              # 开放 — 接受多诠释
    SUPERPOSITION = "superposition"  # 叠加态
    COLLAPSING = "collapsing"  # 坍缩中
    RESOLVED = "resolved"      # 已裁决


# ══════════════════════════════════════════════════════════════════
# 数据结构
# ══════════════════════════════════════════════════════════════════

@dataclass
class WaveParticleState:
    """波粒二象状态"""
    query: str
    wave_amplitude: float = 0.5  # 波动分量概率幅
    particle_amplitude: float = 0.5  # 粒子分量概率幅
    collapse_threshold: float = 0.95  # 坍缩阈值
    measurement_count: int = 0
    last_measured_at: Optional[float] = None

    @property
    def is_superposed(self) -> bool:
        """是否处于叠加态"""
        return (self.wave_amplitude > 0.05 and
                self.particle_amplitude > 0.05)

    @property
    def dominant_paradigm(self) -> InterpretationParadigm:
        """主导范式"""
        return (InterpretationParadigm.WAVE
                if self.wave_amplitude > self.particle_amplitude
                else InterpretationParadigm.PARTICLE)

    def measure(self, evidence_for_wave: float) -> Tuple[InterpretationParadigm, bool]:
        """
        执行一次测量

        Args:
            evidence_for_wave: 支持波动诠释的证据权重 ∈ [0, 1]

        Returns:
            (主导范式, 是否已坍缩)
        """
        self.measurement_count += 1
        self.last_measured_at = time.time()

        # Bayesian 更新
        likelihood_wave = evidence_for_wave
        likelihood_particle = 1 - evidence_for_wave

        self.wave_amplitude *= likelihood_wave
        self.particle_amplitude *= likelihood_particle

        # 归一化
        total = self.wave_amplitude + self.particle_amplitude
        if total > 1e-10:
            self.wave_amplitude /= total
            self.particle_amplitude /= total

        # 坍缩判定
        collapsed = (max(self.wave_amplitude, self.particle_amplitude)
                     >= self.collapse_threshold)

        return self.dominant_paradigm, collapsed


@dataclass
class WorldBranch:
    """世界分支"""
    branch_id: str
    interpretation: InterpretationParadigm
    hypothesis: str
    prior: float = 0.5
    posterior: float = 0.5
    status: BranchStatus = BranchStatus.ACTIVE
    parent_branch: Optional[str] = None
    evidence_chain: List[Dict] = field(default_factory=list)
    conflicting_branches: Set[str] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None

    def update(self, likelihood: float, evidence: Dict):
        """Bayesian 更新"""
        prior = self.posterior
        self.posterior = prior * likelihood
        norm = prior * likelihood + (1 - prior) * (1 - likelihood)
        if norm > 1e-10:
            self.posterior /= norm
        self.evidence_chain.append(evidence)

    def decohere(self):
        """退相干"""
        self.status = BranchStatus.DECOHERED
        self.resolved_at = time.time()

    def promote_dominant(self):
        """提升为主导分支"""
        self.status = BranchStatus.DOMINANT

    def prune(self):
        """剪枝"""
        self.status = BranchStatus.PRUNED
        self.resolved_at = time.time()


@dataclass
class InterpretationLineage:
    """诠释谱系"""
    lineage_id: str
    root_query: str
    branches: List[str] = field(default_factory=list)  # 分支ID序列
    resolutions: List[Dict] = field(default_factory=list)  # 裁决记录
    final_paradigm: Optional[InterpretationParadigm] = None
    created_at: float = field(default_factory=time.time)

    def add_branch(self, branch_id: str, resolution: Dict):
        """记录分支和裁决"""
        self.branches.append(branch_id)
        self.resolutions.append(resolution)

    def get_decision_path(self) -> str:
        """获取决策路径描述"""
        path = [f"Q: {self.root_query[:50]}"]
        for bid, res in zip(self.branches, self.resolutions):
            paradigm = res.get("paradigm", "unknown")
            reason = res.get("reason", "")
            path.append(f"  → [{bid}] {paradigm}: {reason[:40]}")
        if self.final_paradigm:
            path.append(f"  → 最终: {self.final_paradigm.value}")
        return "\n".join(path)


# ══════════════════════════════════════════════════════════════════
# 多世界管理器
# ══════════════════════════════════════════════════════════════════

class ManyWorldsManager:
    """多世界诠释管理器"""

    def __init__(self, max_branches: int = 16):
        self.max_branches = max_branches
        self.branches: Dict[str, WorldBranch] = {}
        self.active_count = 0
        self.branch_count = 0

    def spawn_branch(self, interpretation: InterpretationParadigm,
                     hypothesis: str, parent_id: Optional[str] = None,
                     prior: float = 0.5) -> WorldBranch:
        """生成新世界分支"""
        if self.active_count >= self.max_branches:
            self._prune_weakest()

        self.branch_count += 1
        branch_id = hashlib.md5(
            f"{hypothesis}_{self.branch_count}_{time.time()}".encode()
        ).hexdigest()[:12]
        branch = WorldBranch(
            branch_id=branch_id,
            interpretation=interpretation,
            hypothesis=hypothesis,
            prior=prior,
            parent_branch=parent_id
        )
        self.branches[branch_id] = branch
        self.active_count += 1
        logger.info(f"新分支: {branch_id} ({interpretation.value})")
        return branch

    def update_evidence(self, branch_id: str, likelihood: float,
                        evidence: Dict):
        """向分支添加证据"""
        branch = self.branches.get(branch_id)
        if branch and branch.status == BranchStatus.ACTIVE:
            branch.update(likelihood, evidence)

    def resolve_conflict(self, branch_a_id: str, branch_b_id: str,
                         resolution: str = "MUS_DUAL_STORE") -> Optional[str]:
        """解决分支冲突

        Returns:
            胜出分支 ID (or None 如果双存)
        """
        branch_a = self.branches.get(branch_a_id)
        branch_b = self.branches.get(branch_b_id)
        if not branch_a or not branch_b:
            return None

        # 注册互斥关系
        branch_a.conflicting_branches.add(branch_b_id)
        branch_b.conflicting_branches.add(branch_a_id)

        if resolution == "MUS_DUAL_STORE":
            # 双存 — 保持两个分支激活
            logger.info(f"MUS 双存: {branch_a_id} ↔ {branch_b_id}")
            return None

        # Bayesian 裁决
        if branch_a.posterior > branch_b.posterior:
            branch_b.decohere()
            branch_a.promote_dominant()
            return branch_a_id
        else:
            branch_a.decohere()
            branch_b.promote_dominant()
            return branch_b_id

    def merge_branches(self, branch_ids: List[str],
                       strategy: str = "BAYESIAN_AVERAGE") -> WorldBranch:
        """融合多个分支"""
        if not branch_ids:
            raise ValueError("至少需要一个分支")

        branches = [self.branches[bid] for bid in branch_ids
                    if bid in self.branches]

        if strategy == "BAYESIAN_AVERAGE":
            total_posterior = sum(b.posterior for b in branches)
            avg_posterior = total_posterior / len(branches) if branches else 0.5

        merged = WorldBranch(
            branch_id=f"merged_{int(time.time())}",
            interpretation=InterpretationParadigm.MANY_WORLDS,
            hypothesis="Bayesian Average",
            posterior=avg_posterior,
            status=BranchStatus.MERGED
        )
        self.branches[merged.branch_id] = merged

        # 标记源分支为已融合
        for b in branches:
            b.status = BranchStatus.MERGED
            b.resolved_at = time.time()
            if b in self.branches.values():
                self.active_count -= 1

        self.active_count += 1
        return merged

    def _prune_weakest(self):
        """剪枝最弱分支"""
        active = [b for b in self.branches.values()
                  if b.status == BranchStatus.ACTIVE]
        if not active:
            return
        weakest = min(active, key=lambda b: b.posterior)
        weakest.prune()
        self.active_count -= 1
        logger.info(f"剪枝: {weakest.branch_id} (posterior={weakest.posterior:.4f})")

    def get_dominant_branch(self) -> Optional[WorldBranch]:
        """获取主导分支"""
        active = [b for b in self.branches.values()
                  if b.status in (BranchStatus.ACTIVE, BranchStatus.DOMINANT)]
        if not active:
            return None
        return max(active, key=lambda b: b.posterior)

    def get_branch_stats(self) -> Dict:
        """获取分支统计"""
        status_counts = defaultdict(int)
        for b in self.branches.values():
            status_counts[b.status.value] += 1

        return {
            "total_branches": len(self.branches),
            "active_branches": self.active_count,
            "status_distribution": dict(status_counts),
            "dominant_posterior": (
                self.get_dominant_branch().posterior
                if self.get_dominant_branch() else 0
            ),
        }


# ══════════════════════════════════════════════════════════════════
# 主类：诠释兼容坩埚
# ══════════════════════════════════════════════════════════════════

class InterpretationCrucible:
    """
    诠释兼容坩埚

    管理多诠释范式的并行推理与融合：
    1. 波粒二象 — 波动/粒子双路径并行
    2. 多世界 — Bayesian 分支管理
    3. MUS 双存 — 互斥稳态裁决
    4. 诠释谱系 — 完整决策链路追溯

    用法：
        >>> cru = InterpretationCrucible()
        >>> cru.ask("Why is the sky blue?")
        >>> result = cru.resolve()
        >>> print(cru.decision_summary())
    """

    def __init__(self, max_branches: int = 16):
        # 波粒二象
        self.wp_state: Optional[WaveParticleState] = None

        # 多世界
        self.worlds = ManyWorldsManager(max_branches=max_branches)

        # 坩埚状态
        self.state = CruState.OPEN

        # 谱系
        self.lineages: List[InterpretationLineage] = []

        # 统计
        self.stats = {
            "total_queries": 0,
            "wave_answers": 0,
            "particle_answers": 0,
            "many_worlds_resolutions": 0,
            "mus_dual_stores": 0,
        }

    # ── 查询入口 ─────────────────────────────────────────────────

    def ask(self, query: str,
            hypergraph: Optional[EMLHypergraph] = None) -> Dict:
        """
        对查询进行多诠释分析

        Returns:
            包含波粒二象状态和多世界分支的字典
        """
        self.stats["total_queries"] += 1
        self.state = CruState.OPEN

        # 初始化波粒二象
        self.wp_state = WaveParticleState(query=query)

        # 生成默认多世界分支
        self.worlds.spawn_branch(
            InterpretationParadigm.WAVE,
            f"Wave: {query[:40]}",
            prior=0.5
        )
        self.worlds.spawn_branch(
            InterpretationParadigm.PARTICLE,
            f"Particle: {query[:40]}",
            prior=0.5
        )
        self.worlds.spawn_branch(
            InterpretationParadigm.QBISM,
            f"QBism: {query[:40]}",
            prior=0.3
        )

        # 创建谱系
        lineage = InterpretationLineage(
            lineage_id=hashlib.md5(f"{query}_{time.time()}".encode()).hexdigest()[:12],
            root_query=query,
        )
        self.lineages.append(lineage)

        return {
            "wave_amplitude": self.wp_state.wave_amplitude,
            "particle_amplitude": self.wp_state.particle_amplitude,
            "branches": len(self.worlds.branches),
            "crucible_state": self.state.value,
        }

    # ── 证据输入 ─────────────────────────────────────────────────

    def add_wave_evidence(self, likelihood: float, evidence: Dict):
        """添加支持波动诠释的证据"""
        if self.wp_state is None:
            logger.warning("未初始化波粒状态")
            return

        # 波粒测量
        paradigm, collapsed = self.wp_state.measure(likelihood)

        # 更新对应的世界分支
        for branch in self.worlds.branches.values():
            if branch.interpretation == InterpretationParadigm.WAVE:
                branch.update(likelihood, evidence)
            elif branch.interpretation == InterpretationParadigm.PARTICLE:
                branch.update(1 - likelihood, evidence)

        if collapsed:
            self.stats["wave_answers" if paradigm == InterpretationParadigm.WAVE
                       else "particle_answers"] += 1
            self.state = CruState.COLLAPSING

        logger.debug(f"波粒测量: {paradigm.value}, collapsed={collapsed}, "
                    f"wave={self.wp_state.wave_amplitude:.4f}, "
                    f"particle={self.wp_state.particle_amplitude:.4f}")

    def add_branch_evidence(self, branch_id: str, likelihood: float,
                            evidence: Dict):
        """向指定世界分支添加证据"""
        self.worlds.update_evidence(branch_id, likelihood, evidence)

    # ── 裁决 ─────────────────────────────────────────────────────

    def resolve(self, strategy: str = "AUTO") -> Dict:
        """
        裁决多诠释冲突

        Args:
            strategy: "AUTO" / "WAVE_PARTICLE" / "MUS_DUAL" / "BAYESIAN"

        Returns:
            裁决结果
        """
        if self.state == CruState.RESOLVED:
            return {"status": "already_resolved"}

        self.state = CruState.COLLAPSING

        if strategy == "MUS_DUAL" or self._should_dual_store():
            # MUS 双存 — 保留两个主导分支
            result = self._resolve_mus_dual()
        elif strategy == "BAYESIAN":
            result = self._resolve_bayesian()
        else:
            # AUTO: 检查波粒坍缩状态
            result = self._resolve_auto()

        self.state = CruState.RESOLVED
        return result

    def _should_dual_store(self) -> bool:
        """判断是否应进行 MUS 双存"""
        if self.wp_state and self.wp_state.is_superposed:
            # 波粒仍处于叠加态 → 双存
            return True

        # 如果两个主导分支后验概率接近 → 双存
        branches = [b for b in self.worlds.branches.values()
                    if b.status == BranchStatus.ACTIVE]
        if len(branches) >= 2:
            sorted_b = sorted(branches, key=lambda b: b.posterior, reverse=True)
            if abs(sorted_b[0].posterior - sorted_b[1].posterior) < 0.1:
                return True

        return False

    def _resolve_mus_dual(self) -> Dict:
        """MUS 双存裁决"""
        active = [b for b in self.worlds.branches.values()
                  if b.status == BranchStatus.ACTIVE]
        if len(active) < 2:
            return {"strategy": "MUS_DUAL", "error": "不足两个分支"}

        sorted_b = sorted(active, key=lambda b: b.posterior, reverse=True)
        top_a, top_b = sorted_b[0], sorted_b[1]

        # 双存
        resolution = self.worlds.resolve_conflict(
            top_a.branch_id, top_b.branch_id, "MUS_DUAL_STORE"
        )

        self.stats["mus_dual_stores"] += 1

        return {
            "strategy": "MUS_DUAL",
            "branch_a": {"id": top_a.branch_id, "posterior": top_a.posterior,
                         "interpretation": top_a.interpretation.value},
            "branch_b": {"id": top_b.branch_id, "posterior": top_b.posterior,
                         "interpretation": top_b.interpretation.value},
            "resolution": "dual_store",
        }

    def _resolve_bayesian(self) -> Dict:
        """Bayesian 裁决"""
        active = [b for b in self.worlds.branches.values()
                  if b.status == BranchStatus.ACTIVE]
        if not active:
            return {"strategy": "BAYESIAN", "error": "无活跃分支"}

        best = max(active, key=lambda b: b.posterior)
        self.stats["many_worlds_resolutions"] += 1

        return {
            "strategy": "BAYESIAN",
            "winner": {
                "id": best.branch_id,
                "interpretation": best.interpretation.value,
                "posterior": best.posterior,
                "hypothesis": best.hypothesis,
            },
            "evidence_count": len(best.evidence_chain),
        }

    def _resolve_auto(self) -> Dict:
        """自动裁决"""
        if self.wp_state and not self.wp_state.is_superposed:
            # 波粒已坍缩
            paradigm = self.wp_state.dominant_paradigm
            return {
                "strategy": "WAVE_PARTICLE_COLLAPSE",
                "paradigm": paradigm.value,
                "wave_amplitude": self.wp_state.wave_amplitude,
                "particle_amplitude": self.wp_state.particle_amplitude,
            }

        # 默认 Bayesian
        return self._resolve_bayesian()

    # ── 谱系追溯 ─────────────────────────────────────────────────

    def get_lineage(self, index: int = -1) -> Optional[str]:
        """获取最近的诠释谱系"""
        if not self.lineages:
            return None
        return self.lineages[index].get_decision_path()

    def decision_summary(self) -> str:
        """生成决策摘要"""
        lines = ["🔬 多诠释兼容坩埚 — 决策摘要"]
        lines.append(f"  坩埚状态: {self.state.value}")

        if self.wp_state:
            lines.append(f"  波粒二象: wave={self.wp_state.wave_amplitude:.3f}"
                        f" particle={self.wp_state.particle_amplitude:.3f}")

        stats = self.worlds.get_branch_stats()
        lines.append(f"  世界分支: total={stats['total_branches']}, "
                    f"active={stats['active_branches']}")

        dominant = self.worlds.get_dominant_branch()
        if dominant:
            lines.append(f"  主导: {dominant.interpretation.value} "
                        f"(p={dominant.posterior:.4f})")

        if self.lineages:
            lines.append(f"  谱系数量: {len(self.lineages)}")

        return "\n".join(lines)

    def get_stats(self) -> Dict:
        """获取统计"""
        return {
            **self.stats,
            "branch_stats": self.worlds.get_branch_stats(),
            "crucible_state": self.state.value,
        }


# ══════════════════════════════════════════════════════════════════
# 自检
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Interpretation Crucible 自检")
    print("=" * 60)

    cru = InterpretationCrucible(max_branches=8)

    # 查询
    result = cru.ask("What is the nature of quantum measurement?")
    print(f"\n[查询] {result}")

    # 添加波动证据
    cru.add_wave_evidence(0.8, {"source": "Double-slit", "weight": 0.8})
    cru.add_wave_evidence(0.6, {"source": "Delayed choice", "weight": 0.6})

    # 添加特定分支证据
    for bid, branch in cru.worlds.branches.items():
        if branch.interpretation == InterpretationParadigm.QBISM:
            cru.add_branch_evidence(bid, 0.7, {"source": "Bayesian"})

    # 裁决
    resolution = cru.resolve()
    print(f"\n[裁决] {resolution}")

    # 摘要
    print(f"\n{cru.decision_summary()}")

    # 谱系
    lineage = cru.get_lineage()
    if lineage:
        print(f"\n[谱系]\n{lineage}")

    stats = cru.get_stats()
    print(f"\n📊 统计: {stats}")

    print("\nInterpretation Crucible 自检完成 ✅")
