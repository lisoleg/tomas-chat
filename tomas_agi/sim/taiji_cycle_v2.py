# -*- coding: utf-8 -*-
"""
Taiji Cycle v2.0 — 增强太乙循环引擎
=====================================

基于论文：
  "太乙循环 v2.0 — 从 EML 脉冲到 T-Processor 的完整闭环"
  "太乙神机 (TOMAS' Tetrad Joint: π/Φ/Ω/℧) 与太乙循环的闭环观测"
  微信公众号文章 (2026-06-22)

核心功能：
  01. 太乙循环 v2.0 — EML 脉冲 → φ-Gate → T-Processor 闭环
  02. HyperedgeStore — 超边存储/查询/索引
  03. CycleSpinner — 循环调度器（固定频率/自适应）
  04. φ-Switch — 脉冲分流器（翻译官/作家路由增强）
  05. T-Processor 桥接 — 完整 T-Processor 调用链
  06. 循环审计 — 每轮 Tetrad 一致性校验

集成到现有 TOMAS：
  - token_bridge.py: 循环调度器替换手动调用
  - wm_hyperedge.py: HyperedgeStore 管理超边
  - psi_gate.py: φ-Gate 裁决集成

Author: TOMAS Team
Version: v2.0 (v3.6 upgrade)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Callable
import logging
import math
import time
import hashlib
import threading
from enum import Enum
from collections import deque

logger = logging.getLogger(__name__)

try:
    from .eml_semzip import EMLHypergraph, HyperEdge, EMLLiteKB
except ImportError:
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from eml_semzip import EMLHypergraph, HyperEdge, EMLLiteKB  # type: ignore


# ══════════════════════════════════════════════════════════════════
# 枚举
# ══════════════════════════════════════════════════════════════════

class CyclePhase(Enum):
    """太乙循环阶段"""
    IDLE = "idle"
    PULSE = "pulse"              # EML 脉冲发射
    PHI_GATE = "phi_gate"        # φ-Gate 裁决
    T_PROCESS = "t_process"      # T-Processor 处理
    CONSOLIDATE = "consolidate"  # 记忆巩固
    TETRAD_CHECK = "tetrad_check"  # Tetrad 校验


class SpinMode(Enum):
    """循环调度模式"""
    FIXED_RATE = "fixed_rate"      # 固定频率
    ADAPTIVE = "adaptive"          # 自适应
    EVENT_DRIVEN = "event_driven"  # 事件驱动


class PulseType(Enum):
    """脉冲类型"""
    QUERY = "query"               # 用户查询
    INTERNAL_CHECK = "internal_check"  # 内部校验
    G_EGO_SUBGOAL = "g_ego_subgoal"    # G_ego 子目标
    MEMORY_CONSOLIDATION = "memory_consolidation"
    TETRAD_AUDIT = "tetrad_audit"


# ══════════════════════════════════════════════════════════════════
# 数据结构
# ══════════════════════════════════════════════════════════════════

@dataclass
class EMPulse:
    """EML 脉冲"""
    pulse_id: str
    pulse_type: PulseType
    query: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    hypergraph_snapshot: Optional[EMLHypergraph] = None
    I_value: float = 0.5
    priority: int = 0  # 0=最低, 10=最高
    created_at: float = field(default_factory=time.time)

    def to_wire(self) -> Dict:
        return {
            "pulse_id": self.pulse_id,
            "type": self.pulse_type.value,
            "query": self.query[:100],
            "I_value": self.I_value,
            "priority": self.priority,
        }


@dataclass
class CycleResult:
    """循环结果"""
    cycle_id: str
    phase: CyclePhase
    pulse: EMPulse
    phi_verdict: Optional[str] = None
    tprocessor_output: Optional[Dict] = None
    tetrad_score: float = 0.0
    duration_ms: float = 0.0
    errors: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


@dataclass
class PhiSwitchConfig:
    """φ-Switch 配置"""
    translator_threshold: float = 0.5  # 翻译官路由阈值
    writer_threshold: float = 0.3      # 作家路由阈值
    fallback_to_writer: bool = True
    enable_multi_world: bool = True


# ══════════════════════════════════════════════════════════════════
# HyperedgeStore — 超边存储/索引
# ══════════════════════════════════════════════════════════════════

class HyperedgeStore:
    """
    HyperedgeStore — 高性能超边存储

    功能：
    1. 超边 CRUD — 存储/查询/删除/更新
    2. 多级索引 — by_type / by_I / by_tag
    3. LRU 淘汰 — 内存压力管理
    4. 批量查询 — 前缀/TDC 范围扫描
    """

    def __init__(self, max_cache_size: int = 10000):
        self.max_cache = max_cache_size
        self._edges: Dict[str, Dict[str, Any]] = {}
        self._access_order: deque = deque()

        # 索引
        self._by_type: Dict[str, List[str]] = {}
        self._by_tag: Dict[str, List[str]] = {}
        self._by_I: Dict[float, List[str]] = {}  # 精确 I 匹配

        self.stats = {"puts": 0, "gets": 0, "hits": 0, "evictions": 0}

    def put(self, edge_id: str, edge_data: Dict[str, Any],
            edge_type: str = "generic", tags: Optional[List[str]] = None):
        """存储超边"""
        if edge_id in self._edges:
            self._remove_from_indices(edge_id)

        if len(self._edges) >= self.max_cache:
            self._evict_lru()

        self._edges[edge_id] = edge_data
        self._access_order.append(edge_id)
        self.stats["puts"] += 1

        # 更新索引
        self._by_type.setdefault(edge_type, []).append(edge_id)
        for tag in (tags or []):
            self._by_tag.setdefault(tag, []).append(edge_id)

        I_val = edge_data.get("I_value", 1.0)
        self._by_I.setdefault(round(I_val, 2), []).append(edge_id)

    def get(self, edge_id: str) -> Optional[Dict[str, Any]]:
        """查询超边"""
        self.stats["gets"] += 1
        if edge_id in self._edges:
            self.stats["hits"] += 1
            # 更新 LRU
            if edge_id in self._access_order:
                self._access_order.remove(edge_id)
            self._access_order.append(edge_id)
            return self._edges[edge_id]
        return None

    def query_by_type(self, edge_type: str,
                      limit: int = 100) -> List[Dict[str, Any]]:
        """按类型查询"""
        edge_ids = self._by_type.get(edge_type, [])[-limit:]
        return [self._edges[eid] for eid in edge_ids if eid in self._edges]

    def query_by_tag(self, tag: str,
                     limit: int = 100) -> List[Dict[str, Any]]:
        """按标签查询"""
        edge_ids = self._by_tag.get(tag, [])[-limit:]
        return [self._edges[eid] for eid in edge_ids if eid in self._edges]

    def query_by_I_range(self, I_min: float, I_max: float,
                         limit: int = 100) -> List[Dict[str, Any]]:
        """按 I 值范围查询"""
        results = []
        for I_level, edge_ids in self._by_I.items():
            if I_min <= I_level <= I_max:
                results.extend(
                    self._edges[eid] for eid in edge_ids[-limit:]
                    if eid in self._edges
                )
        return results[-limit:]

    def delete(self, edge_id: str) -> bool:
        """删除超边"""
        if edge_id not in self._edges:
            return False
        self._remove_from_indices(edge_id)
        del self._edges[edge_id]
        if edge_id in self._access_order:
            self._access_order.remove(edge_id)
        return True

    def _remove_from_indices(self, edge_id: str):
        """从所有索引中移除"""
        for type_dict in [self._by_type, self._by_tag]:
            for key, ids in list(type_dict.items()):
                if edge_id in ids:
                    ids.remove(edge_id)

        for I_level, ids in list(self._by_I.items()):
            if edge_id in ids:
                ids.remove(edge_id)

    def _evict_lru(self):
        """LRU 淘汰"""
        if self._access_order:
            oldest = self._access_order.popleft()
            self.delete(oldest)
            self.stats["evictions"] += 1

    def size(self) -> int:
        return len(self._edges)

    def get_stats(self) -> Dict:
        return {
            **self.stats,
            "size": self.size(),
            "hit_rate": (self.stats["hits"] / max(self.stats["gets"], 1)),
            "indexed_types": list(self._by_type.keys()),
            "indexed_tags": list(self._by_tag.keys()),
        }


# ══════════════════════════════════════════════════════════════════
# φ-Switch — 脉冲分流器
# ══════════════════════════════════════════════════════════════════

class PhiSwitch:
    """
    φ-Switch — 脉冲分流器

    基于 ℐ 值将脉冲路由到翻译官或作家：
      ℐ ≥ 0.5 → 翻译官 (LSTM/模板, 确定性答案)
      ℐ < 0.5 → 作家 (LLM, 创造性回答)
    """

    def __init__(self, config: Optional[PhiSwitchConfig] = None):
        self.config = config or PhiSwitchConfig()
        self.routing_history: List[Dict] = []

    def route(self, pulse: EMPulse,
              hypergraph: Optional[EMLHypergraph] = None) -> Tuple[str, float]:
        """
        路由脉冲

        Returns:
            (目标引擎名称, 置信度)
        """
        I_val = pulse.I_value

        # 计算 ℐ 增强（如果有超图）
        if hypergraph:
            I_val = self._enhance_I(pulse.query, hypergraph, I_val)

        # 路由决策
        if I_val >= self.config.translator_threshold:
            engine = "translator"
        elif I_val >= self.config.writer_threshold:
            engine = "writer"
        else:
            engine = "writer" if self.config.fallback_to_writer else "translator"

        self.routing_history.append({
            "pulse_id": pulse.pulse_id,
            "engine": engine,
            "I_value": I_val,
            "timestamp": time.time(),
        })

        return engine, I_val

    def _enhance_I(self, query: str, hg: EMLHypergraph,
                   base_I: float) -> float:
        """基于超图增强 ℐ 值"""
        # 简化实现：基于超图中匹配的概念数
        if hasattr(hg, 'vertices'):
            query_terms = set(query.lower().split())
            graph_terms = set(str(v).lower() for v in hg.vertices)
            overlap = len(query_terms & graph_terms)
            if overlap > 0:
                enhancement = min(0.3, overlap * 0.05)
                base_I += enhancement
        return min(1.0, base_I)

    def get_routing_stats(self) -> Dict:
        """获取路由统计"""
        history = self.routing_history
        if not history:
            return {"total": 0, "translator": 0, "writer": 0}

        translator = sum(1 for r in history if r["engine"] == "translator")
        writer = sum(1 for r in history if r["engine"] == "writer")
        return {
            "total": len(history),
            "translator": translator,
            "writer": writer,
            "ratio": translator / max(len(history), 1),
        }


# ══════════════════════════════════════════════════════════════════
# CycleSpinner — 循环调度器
# ══════════════════════════════════════════════════════════════════

class CycleSpinner:
    """
    CycleSpinner — 太乙循环调度器

    调度 EML 脉冲 → φ-Gate → T-Processor → 巩固的完整闭环。
    """

    def __init__(self, mode: SpinMode = SpinMode.ADAPTIVE,
                 interval_ms: float = 100.0):
        self.mode = mode
        self.interval_ms = interval_ms
        self.cycle_count: int = 0
        self.current_phase: CyclePhase = CyclePhase.IDLE
        self.results: deque = deque(maxlen=1000)

        # 回调注册
        self.on_pulse: Optional[Callable] = None
        self.on_phi_gate: Optional[Callable] = None
        self.on_t_process: Optional[Callable] = None
        self.on_consolidate: Optional[Callable] = None
        self.on_tetrad_check: Optional[Callable] = None

        # 组件
        self.store = HyperedgeStore()
        self.phi_switch = PhiSwitch()

        # 自适应参数
        self.adaptive_interval = interval_ms
        self.error_rate: float = 0.0
        self.success_streak: int = 0

    def spin(self, pulse: EMPulse,
             hypergraph: Optional[EMLHypergraph] = None) -> CycleResult:
        """
        执行一个完整太乙循环

        Args:
            pulse: EML 脉冲
            hypergraph: 可选超图上下文

        Returns:
            CycleResult: 循环结果
        """
        start_time = time.time()
        self.cycle_count += 1
        cycle_id = f"cycle_{self.cycle_count}_{int(start_time)}"
        errors = []

        # Phase 1: PULSE
        self.current_phase = CyclePhase.PULSE
        self.store.put(pulse.pulse_id, pulse.to_wire(),
                       edge_type="pulse", tags=[pulse.pulse_type.value])
        if self.on_pulse:
            try:
                self.on_pulse(pulse)
            except Exception as e:
                errors.append(f"PULSE error: {e}")

        # Phase 2: PHI_GATE
        self.current_phase = CyclePhase.PHI_GATE
        engine, confidence = self.phi_switch.route(pulse, hypergraph)
        phi_verdict = f"{engine} (I={confidence:.3f})"
        if self.on_phi_gate:
            try:
                self.on_phi_gate(pulse, engine, confidence)
            except Exception as e:
                errors.append(f"PHI_GATE error: {e}")

        # Phase 3: T_PROCESS
        self.current_phase = CyclePhase.T_PROCESS
        t_output = self._run_t_process(pulse, engine, confidence)
        if self.on_t_process:
            try:
                self.on_t_process(t_output)
            except Exception as e:
                errors.append(f"T_PROCESS error: {e}")

        # Phase 4: CONSOLIDATE
        self.current_phase = CyclePhase.CONSOLIDATE
        if self.on_consolidate:
            try:
                self.on_consolidate(t_output)
            except Exception as e:
                errors.append(f"CONSOLIDATE error: {e}")

        # Phase 5: TETRAD_CHECK
        self.current_phase = CyclePhase.TETRAD_CHECK
        tetrad = self._compute_tetrad(pulse, t_output)
        if self.on_tetrad_check:
            try:
                self.on_tetrad_check(tetrad)
            except Exception as e:
                errors.append(f"TETRAD_CHECK error: {e}")

        # 完成
        duration = (time.time() - start_time) * 1000
        result = CycleResult(
            cycle_id=cycle_id,
            phase=self.current_phase,
            pulse=pulse,
            phi_verdict=phi_verdict,
            tprocessor_output=t_output,
            tetrad_score=tetrad,
            duration_ms=duration,
            errors=errors,
        )

        self.results.append(result)

        # 自适应调整
        if errors:
            self.error_rate = 0.8 * self.error_rate + 0.2
            self.success_streak = 0
            self.adaptive_interval *= 1.2  # 减速
        else:
            self.error_rate *= 0.9
            self.success_streak += 1
            if self.success_streak > 10:
                self.adaptive_interval *= 0.95  # 加速

        self.current_phase = CyclePhase.IDLE
        return result

    def _run_t_process(self, pulse: EMPulse, engine: str,
                       confidence: float) -> Dict[str, Any]:
        """执行 T-Processor 处理"""
        # 简化实现 — 实际集成会调用 tprocessor_sim.py
        return {
            "engine": engine,
            "confidence": confidence,
            "query": pulse.query[:100],
            "pulse_id": pulse.pulse_id,
            "output": f"[{engine}] Response to: {pulse.query[:50]}...",
            "timestamp": time.time(),
        }

    def _compute_tetrad(self, pulse: EMPulse,
                        t_output: Dict) -> float:
        """计算 Tetrad 一致性分数"""
        pi_factor = math.sin(math.pi * pulse.I_value) * 0.5 + 0.5
        phi_factor = 1.0 / (1.0 + math.exp(-1.618 * (t_output.get("confidence", 0.5) - 0.5)))
        omega_factor = math.exp(-0.567 * abs(pulse.I_value - 0.5))
        mhoo_factor = 0.618 + 0.382 * pulse.I_value

        # π/Φ/Ω/℧ 几何平均
        return (pi_factor * phi_factor * omega_factor * mhoo_factor) ** 0.25

    def register_callbacks(self, on_pulse=None, on_phi_gate=None,
                           on_t_process=None, on_consolidate=None,
                           on_tetrad_check=None):
        """注册回调"""
        self.on_pulse = on_pulse
        self.on_phi_gate = on_phi_gate
        self.on_t_process = on_t_process
        self.on_consolidate = on_consolidate
        self.on_tetrad_check = on_tetrad_check

    def get_cycle_stats(self) -> Dict:
        recent = list(self.results)[-10:]
        avg_duration = (sum(r.duration_ms for r in recent) /
                       max(len(recent), 1)) if recent else 0
        avg_tetrad = (sum(r.tetrad_score for r in recent) /
                     max(len(recent), 1)) if recent else 0
        error_count = sum(1 for r in recent if r.errors)

        return {
            "total_cycles": self.cycle_count,
            "current_phase": self.current_phase.value,
            "spin_mode": self.mode.value,
            "adaptive_interval_ms": round(self.adaptive_interval, 1),
            "error_rate": round(self.error_rate, 3),
            "success_streak": self.success_streak,
            "avg_duration_ms": round(avg_duration, 1),
            "avg_tetrad": round(avg_tetrad, 4),
            "recent_error_count": error_count,
            "routing": self.phi_switch.get_routing_stats(),
            "store_size": self.store.size(),
        }


# ══════════════════════════════════════════════════════════════════
# 主类：增强太乙循环
# ══════════════════════════════════════════════════════════════════

class TaijiCycleV2:
    """
    增强太乙循环 v2.0

    从 EML 脉冲到 T-Processor 的完整闭环：
    1. EMPulse — 按类型发射脉冲
    2. HyperedgeStore — 超边存储/查询
    3. φ-Switch — 翻译官/作家智能分流
    4. CycleSpinner — 自适应循环调度
    5. 循环结果审计 — Tetrad 一致性追踪

    用法：
        >>> taiji = TaijiCycleV2()
        >>> pulse = taiji.emit_query("What is AI?")
        >>> result = taiji.run_cycle(pulse)
        >>> print(f"Tetrad: {result.tetrad_score:.4f}")
    """

    def __init__(self, agent_id: str = "taiji_v2",
                 mode: SpinMode = SpinMode.ADAPTIVE):
        self.agent_id = agent_id

        # 核心组件
        self.store = HyperedgeStore()
        self.spinner = CycleSpinner(mode=mode)
        self.phi_switch = PhiSwitch()

        # 回调连接
        self.spinner.register_callbacks(
            on_pulse=self._on_pulse,
            on_phi_gate=self._on_phi_gate,
            on_t_process=self._on_t_process,
            on_consolidate=self._on_consolidate,
            on_tetrad_check=self._on_tetrad_check,
        )

        # 统计
        self.total_pulses = 0
        self.total_cycles = 0

    # ── 脉冲发射 ─────────────────────────────────────────────────

    def emit_query(self, query: str,
                   context: Optional[Dict] = None,
                   I_value: float = 0.5) -> EMPulse:
        """发射查询脉冲"""
        return self._emit(PulseType.QUERY, query, context, I_value)

    def emit_internal_check(self, check_type: str,
                            context: Optional[Dict] = None) -> EMPulse:
        """发射内部校验脉冲"""
        return self._emit(PulseType.INTERNAL_CHECK, check_type, context, 0.8)

    def emit_gego_subgoal(self, subgoal: str,
                          context: Optional[Dict] = None) -> EMPulse:
        """发射 G_ego 子目标脉冲"""
        return self._emit(PulseType.G_EGO_SUBGOAL, subgoal, context, 0.6)

    def _emit(self, pulse_type: PulseType, content: str,
              context: Optional[Dict] = None,
              I_value: float = 0.5) -> EMPulse:
        """通用脉冲发射"""
        self.total_pulses += 1
        pulse = EMPulse(
            pulse_id=f"pulse_{self.total_pulses}_{int(time.time())}",
            pulse_type=pulse_type,
            query=content,
            context=context or {},
            I_value=I_value,
            priority=self._calc_priority(pulse_type),
        )
        self.store.put(pulse.pulse_id, pulse.to_wire(),
                       edge_type="pulse", tags=[pulse_type.value])
        return pulse

    def _calc_priority(self, pulse_type: PulseType) -> int:
        """计算优先级"""
        priority_map = {
            PulseType.QUERY: 5,
            PulseType.INTERNAL_CHECK: 3,
            PulseType.G_EGO_SUBGOAL: 7,
            PulseType.MEMORY_CONSOLIDATION: 2,
            PulseType.TETRAD_AUDIT: 1,
        }
        return priority_map.get(pulse_type, 3)

    # ── 主循环 ───────────────────────────────────────────────────

    def run_cycle(self, pulse: EMPulse,
                  hypergraph: Optional[EMLHypergraph] = None) -> CycleResult:
        """运行一个完整太乙循环"""
        self.total_cycles += 1
        result = self.spinner.spin(pulse, hypergraph)
        return result

    # ── 批量循环 ─────────────────────────────────────────────────

    def run_batch(self, queries: List[str],
                  hypergraph: Optional[EMLHypergraph] = None) -> List[CycleResult]:
        """批量运行循环"""
        results = []
        for query in queries:
            pulse = self.emit_query(query)
            result = self.run_cycle(pulse, hypergraph)
            results.append(result)
        return results

    # ── 回调 ─────────────────────────────────────────────────────

    def _on_pulse(self, pulse: EMPulse):
        logger.debug(f"[Taiji] PULSE: {pulse.pulse_id} ({pulse.pulse_type.value})")

    def _on_phi_gate(self, pulse: EMPulse, engine: str, confidence: float):
        logger.debug(f"[Taiji] φ-Gate → {engine} (I={confidence:.3f})")

    def _on_t_process(self, output: Dict):
        logger.debug(f"[Taiji] T-Process → {output.get('engine', '?')}")

    def _on_consolidate(self, output: Dict):
        pass  # 记忆巩固由 memos_fusion 负责

    def _on_tetrad_check(self, score: float):
        if score < 0.3:
            logger.warning(f"[Taiji] Tetrad 低分: {score:.4f}")

    # ── 统计 ─────────────────────────────────────────────────────

    def get_full_stats(self) -> Dict:
        return {
            "agent_id": self.agent_id,
            "total_pulses_emitted": self.total_pulses,
            "total_cycles_completed": self.total_cycles,
            "cycle_stats": self.spinner.get_cycle_stats(),
            "store_stats": self.store.get_stats(),
        }

    def summary(self) -> str:
        """生成循环摘要"""
        stats = self.get_full_stats()
        cs = stats["cycle_stats"]
        lines = [
            f"☯ 太乙循环 v2.0 — {stats['agent_id']}",
            f"  脉冲: {stats['total_pulses_emitted']} | "
            f"循环: {stats['total_cycles_completed']}",
            f"  模式: {cs['spin_mode']} | "
            f"自适应间隔: {cs['adaptive_interval_ms']:.1f}ms",
            f"  错误率: {cs['error_rate']:.3f} | "
            f"连成: {cs['success_streak']}",
            f"  平均 Tetrad: {cs['avg_tetrad']:.4f}",
            f"  路由: translator={cs['routing'].get('translator', 0)}, "
            f"writer={cs['routing'].get('writer', 0)}",
        ]
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# 自检
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Taiji Cycle v2.0 自检")
    print("=" * 60)

    taiji = TaijiCycleV2(agent_id="TestTaiji",
                         mode=SpinMode.ADAPTIVE)

    # 发射查询脉冲
    pulse = taiji.emit_query("What is the capital of France?")
    print(f"\n[脉冲] {pulse.pulse_id}: {pulse.query} (I={pulse.I_value})")

    # 运行循环
    result = taiji.run_cycle(pulse)
    print(f"[循环] {result.cycle_id}")
    print(f"  φ-Gate: {result.phi_verdict}")
    print(f"  Tetrad: {result.tetrad_score:.4f}")
    print(f"  耗时: {result.duration_ms:.1f}ms")
    print(f"  错误: {result.errors if result.errors else '无'}")

    # 批量循环
    print(f"\n[批量测试] 3 个查询")
    results = taiji.run_batch([
        "What is AI?",
        "Explain quantum computing",
        "How to make pizza?",
    ])
    for r in results:
        print(f"  {r.cycle_id.split('_')[1]}: "
              f"Tetrad={r.tetrad_score:.4f}, φ={r.phi_verdict}")

    # 统计
    print(f"\n{taiji.summary()}")

    print("\nTaiji Cycle v2.0 自检完成 ✅")
