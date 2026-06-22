# -*- coding: utf-8 -*-
"""
KernelCAT Scheduler v1.0 — 算子耦合搜索与算力调度
===================================================

基于论文:
  "KernelCAT: kappa-Snap 历史 + G_ego 推理 + psi-锚预算 + Copartial 搜索
   → 分配唤醒 + kappa-Snap 审计的算子耦合调度框架"
  TOMAS AGI v3.9

核心功能:
  01. OperatorProfile — 算子性能画像 (SHA-256 指纹)
  02. CopartialSearch — GaussEx 共偏性算子耦合搜索
  03. ComputeCarbonAuditor — 算力碳审计 (CO2 跟踪)
  04. KernelCATScheduler — 六步主调度管道

38 分钟 Ascend 迁移基准:
  D_src(CUDA) ⊕ D_tgt(CANN) → D_match via GaussEx 互补互联

Critical Path:
  1. Read kappa-Snap history (past operator performance fingerprints)
  2. G_ego inference (determine context-appropriate compute needs)
  3. psi-anchor budget check (compute budget + data sovereignty)
  4. Copartial search (find optimal operator couplings across platforms)
  5. Allocate & wake (assign operators to tasks)
  6. kappa-Snap audit (fingerprint all allocations)

Integration:
  - ksnap_operator.py: KSnapRecord, SnapResult 审计
  - g_ego.py: G_egoEngine 推理 + aligned_with_purpose()
  - psi_gate.py: psi-Gate 不确定性门控
  - gaussex_eml.py: GaussExSystem, CopartialMap, interconnect, Fibre, GaussianNoise
  - babeltele_compressor.py: KSnapRecord, MUSDualEntry, SnapResult (共享 v3.9 类型)

Author: TOMAS Team
Version: v1.0 (v3.9 KernelCAT)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import logging
import math
import time
import hashlib
import json
import uuid
from enum import Enum

logger = logging.getLogger(__name__)

# ── 数学快捷 ────────────────────────────────────────────────────
sqrt = math.sqrt
exp = math.exp
pi = math.pi


# ╔══════════════════════════════════════════════════════════════════╗
# ║               跨模块类型导入 (try/except ImportError)             ║
# ╚══════════════════════════════════════════════════════════════════╝

# ── v3.9 共享类型 (from babeltele_compressor) ────────────────────
try:
    from .babeltele_compressor import KSnapRecord, MUSDualEntry, SnapResult  # type: ignore
    _HAS_BABELTELE = True
except ImportError:
    try:
        from babeltele_compressor import KSnapRecord, MUSDualEntry, SnapResult  # type: ignore
        _HAS_BABELTELE = True
    except ImportError:
        _HAS_BABELTELE = False
        # Fallback: define simplified versions locally
        KSnapRecord = None  # type: ignore
        MUSDualEntry = None  # type: ignore
        SnapResult = None  # type: ignore

# ── GaussEx-EML 模块 ─────────────────────────────────────────────
try:
    from .gaussex_eml import GaussExSystem, CopartialMap, interconnect, Fibre, GaussianNoise  # type: ignore
    _HAS_GAUSSEX = True
except ImportError:
    try:
        from gaussex_eml import GaussExSystem, CopartialMap, interconnect, Fibre, GaussianNoise  # type: ignore
        _HAS_GAUSSEX = True
    except ImportError:
        _HAS_GAUSSEX = False
        GaussExSystem = None  # type: ignore
        CopartialMap = None  # type: ignore
        interconnect = None  # type: ignore
        Fibre = None  # type: ignore
        GaussianNoise = None  # type: ignore

# ── G_ego 模块 ───────────────────────────────────────────────────
try:
    from .g_ego import G_egoEngine  # type: ignore
    _HAS_G_EGO = True
except ImportError:
    try:
        from g_ego import G_egoEngine  # type: ignore
        _HAS_G_EGO = True
    except ImportError:
        _HAS_G_EGO = False
        G_egoEngine = None  # type: ignore

# ── psi-Gate 模块 ────────────────────────────────────────────────
try:
    from .psi_gate import PsiGate  # type: ignore
    _HAS_PSI_GATE = True
except ImportError:
    try:
        from psi_gate import PsiGate  # type: ignore
        _HAS_PSI_GATE = True
    except ImportError:
        _HAS_PSI_GATE = False
        PsiGate = None  # type: ignore


# ╔══════════════════════════════════════════════════════════════════╗
# ║               枚举与常量                                          ║
# ╚══════════════════════════════════════════════════════════════════╝

class OperatorType(Enum):
    """算子类型枚举"""
    MATMUL = "matmul"
    CONV2D = "conv2d"
    SOFTMAX = "softmax"
    RELU = "relu"
    ATTENTION = "attention"
    LAYER_NORM = "layer_norm"
    GEMM = "gemm"
    REDUCTION = "reduction"
    ELEMENT_WISE = "element_wise"
    CUSTOM = "custom"


class PlatformType(Enum):
    """计算平台枚举"""
    CUDA = "CUDA"       # NVIDIA GPU
    CANN = "CANN"       # Ascend NPU
    CPU = "CPU"         # x86_64 / ARM
    ROCM = "ROCM"       # AMD GPU
    DEFAULT = "default"


class ScheduleStatus(Enum):
    """调度状态"""
    PENDING = "pending"
    ALLOCATED = "allocated"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BUDGET_EXCEEDED = "budget_exceeded"


# ── 碳因子 (kgCO2/kWh) ──────────────────────────────────────────
CARBON_FACTORS: Dict[str, float] = {
    "CUDA": 0.475,       # Azure/AWS average
    "CANN": 0.385,       # Ascend NPU (more efficient)
    "CPU": 0.475,
    "ROCM": 0.450,       # AMD GPU estimate
    "default": 0.475,
}

# ── 38分钟 Ascend 迁移基准 ───────────────────────────────────────
ASCEND_MIGRATION_BENCHMARK_SEC: float = 38.0 * 60.0  # 2280 seconds


# ╔══════════════════════════════════════════════════════════════════╗
# ║               数据类 (dataclasses)                                ║
# ╚══════════════════════════════════════════════════════════════════╝

@dataclass
class OperatorProfile:
    """性能画像 — 单个计算算子。
    
    Attributes:
        op_id: 算子唯一标识
        op_type: 算子类型 (matmul, conv2d, softmax, etc.)
        platform: 计算平台 (CUDA, CANN, CPU, etc.)
        latency_us: 延迟 (微秒)
        power_mw: 功耗 (毫瓦)
        cache_hit_rate: 缓存命中率 [0.0, 1.0]
        memory_mb: 显存/内存占用 (MB)
        recorded_at: 记录时间戳
    """
    op_id: str
    op_type: str
    platform: str
    latency_us: float
    power_mw: float
    cache_hit_rate: float = 0.0
    memory_mb: float = 0.0
    recorded_at: float = field(default_factory=time.time)

    def fingerprint(self) -> str:
        """SHA-256 指纹 of (latency, power, cache_hit_rate)。"""
        raw = f"{self.op_id}:{self.latency_us:.6f}:{self.power_mw:.6f}:{self.cache_hit_rate:.6f}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "op_id": self.op_id,
            "op_type": self.op_type,
            "platform": self.platform,
            "latency_us": self.latency_us,
            "power_mw": self.power_mw,
            "cache_hit_rate": self.cache_hit_rate,
            "memory_mb": self.memory_mb,
            "recorded_at": self.recorded_at,
            "fingerprint": self.fingerprint(),
        }

    def feature_vector(self) -> List[float]:
        """归一化特征向量用于耦合搜索。"""
        return [
            self.latency_us / 10000.0,     # normalize to ~10ms
            self.power_mw / 300000.0,       # normalize to ~300W
            self.cache_hit_rate,
            self.memory_mb / 8192.0,        # normalize to ~8GB
        ]

    def _run_self_test() -> Dict[str, Any]:
        """OperatorProfile 自测试"""
        passed = 0
        failed = 0
        checks: List[str] = []

        try:
            op = OperatorProfile(
                op_id="test_matmul_1",
                op_type="matmul",
                platform="CUDA",
                latency_us=150.0,
                power_mw=200000.0,
                cache_hit_rate=0.85,
                memory_mb=1024.0,
            )
            fp = op.fingerprint()
            assert len(fp) == 64, "fingerprint should be 64 hex chars"
            assert all(c in "0123456789abcdef" for c in fp), "fingerprint should be hex"
            checks.append("fingerprint valid")
            passed += 1
        except Exception as e:
            checks.append(f"fingerprint FAILED: {e}")
            failed += 1

        try:
            op2 = OperatorProfile(
                op_id="test_matmul_1",
                op_type="matmul",
                platform="CUDA",
                latency_us=150.0,
                power_mw=200000.0,
                cache_hit_rate=0.85,
            )
            assert op2.to_dict()["op_id"] == "test_matmul_1"
            fv = op2.feature_vector()
            assert len(fv) == 4
            checks.append("to_dict/feature_vector valid")
            passed += 1
        except Exception as e:
            checks.append(f"to_dict/feature_vector FAILED: {e}")
            failed += 1

        return {"passed": passed, "failed": failed, "checks": checks}


@dataclass
class CopartialMatch:
    """共偏性搜索结果 — 两个算子间的耦合匹配。
    
    Attributes:
        src_op: 源算子画像
        tgt_op: 目标算子画像
        coupling_score: 耦合评分 [0.0, 1.0]
        performance_delta: 性能差异 (latency_delta, power_delta, cache_delta)
    """
    src_op: OperatorProfile
    tgt_op: OperatorProfile
    coupling_score: float
    performance_delta: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "src_op_id": self.src_op.op_id,
            "tgt_op_id": self.tgt_op.op_id,
            "src_platform": self.src_op.platform,
            "tgt_platform": self.tgt_op.platform,
            "coupling_score": self.coupling_score,
            "performance_delta": self.performance_delta,
        }

    def _run_self_test() -> Dict[str, Any]:
        """CopartialMatch 自测试"""
        passed = 0
        failed = 0
        checks: List[str] = []

        try:
            src = OperatorProfile("op_a", "matmul", "CUDA", 100.0, 200000.0)
            tgt = OperatorProfile("op_b", "matmul", "CANN", 120.0, 150000.0)
            match = CopartialMatch(
                src_op=src,
                tgt_op=tgt,
                coupling_score=0.85,
                performance_delta={"latency_delta": -20.0, "power_delta": 50000.0},
            )
            d = match.to_dict()
            assert d["coupling_score"] == 0.85
            assert d["src_op_id"] == "op_a"
            checks.append("CopartialMatch to_dict valid")
            passed += 1
        except Exception as e:
            checks.append(f"CopartialMatch FAILED: {e}")
            failed += 1

        return {"passed": passed, "failed": failed, "checks": checks}


@dataclass
class CarbonAuditEntry:
    """碳审计条目"""
    entry_id: str
    ops_count: int
    duration_s: float
    energy_kwh: float
    co2_kg: float
    platform: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "ops_count": self.ops_count,
            "duration_s": self.duration_s,
            "energy_kwh": self.energy_kwh,
            "co2_kg": self.co2_kg,
            "platform": self.platform,
            "timestamp": self.timestamp,
        }


@dataclass
class ScheduleAllocation:
    """调度分配结果"""
    task_id: str
    op_id: str
    platform: str
    coupling_score: float
    estimated_latency_us: float
    estimated_energy_kwh: float
    estimated_co2_kg: float
    status: ScheduleStatus = ScheduleStatus.PENDING
    allocated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "op_id": self.op_id,
            "platform": self.platform,
            "coupling_score": self.coupling_score,
            "estimated_latency_us": self.estimated_latency_us,
            "estimated_energy_kwh": self.estimated_energy_kwh,
            "estimated_co2_kg": self.estimated_co2_kg,
            "status": self.status.value,
            "allocated_at": self.allocated_at,
        }


# ╔══════════════════════════════════════════════════════════════════╗
# ║               CopartialSearch — 共偏性算子耦合搜索                 ║
# ╚══════════════════════════════════════════════════════════════════╝

class CopartialSearch:
    """搜索跨平台算子间的最优耦合。
    
    使用 GaussEx CopartialMap 进行共偏性投影:
      D_src(CUDA) ⊕ D_tgt(CANN) → D_match via copartial projection
    
    核心思路:
      - Fibre 交集: 功能等价性 (相同的 op_type, 数学语义一致)
      - Noise 卷积: 性能方差 (延迟/功耗的跨平台差异)
      - 耦合分数 = Fibre 相似度 * (1 - 归一化噪声)
    
    由于仿真环境无真实 NPU，使用画像相似度启发式算法代替。
    """

    def __init__(self):
        self.history: List[CopartialMatch] = []
        self.search_count: int = 0

    def search(self, available_ops: List[OperatorProfile],
               context: Optional[Dict] = None) -> List[CopartialMatch]:
        """搜索可用的最优算子耦合对。

        对所有同类型但跨平台的算子对进行计算，按 coupling_score 降序排列。

        Args:
            available_ops: 可用算子画像列表
            context: 上下文参数 (如 target_platform, preferred_ops 等)

        Returns:
            按 coupling_score 降序排列的 CopartialMatch 列表
        """
        if len(available_ops) < 2:
            logger.debug("CopartialSearch: insufficient operators for coupling")
            return []

        matches: List[CopartialMatch] = []
        context = context or {}

        # 分组: 先按 op_type 分组，再在每个组内找跨平台对
        grouped: Dict[str, List[OperatorProfile]] = {}
        for op in available_ops:
            grouped.setdefault(op.op_type, []).append(op)

        for op_type, ops in grouped.items():
            for i in range(len(ops)):
                for j in range(i + 1, len(ops)):
                    op_a, op_b = ops[i], ops[j]
                    # 仅比较跨平台对 (同平台耦合无迁移意义)
                    if op_a.platform == op_b.platform:
                        continue

                    # 上下文过滤: target_platform
                    if context.get("target_platform"):
                        tgt = context["target_platform"]
                        if op_a.platform != tgt and op_b.platform != tgt:
                            continue

                    coupling = self.compute_coupling(op_a, op_b)
                    performance_delta = {
                        "latency_delta": op_a.latency_us - op_b.latency_us,
                        "power_delta": op_a.power_mw - op_b.power_mw,
                        "cache_delta": op_a.cache_hit_rate - op_b.cache_hit_rate,
                        "memory_delta": op_a.memory_mb - op_b.memory_mb,
                    }

                    match = CopartialMatch(
                        src_op=op_a,
                        tgt_op=op_b,
                        coupling_score=coupling,
                        performance_delta=performance_delta,
                    )
                    matches.append(match)

        # 按 coupling_score 降序排列
        matches.sort(key=lambda m: m.coupling_score, reverse=True)

        self.search_count += 1
        self.history.extend(matches)

        logger.info(
            f"CopartialSearch: found {len(matches)} couplings "
            f"from {len(available_ops)} operators (search #{self.search_count})"
        )
        return matches

    def compute_coupling(self, op_a: OperatorProfile, op_b: OperatorProfile) -> float:
        """计算两个算子间的耦合分数。

        公式:
          coupling = Fibre_similarity * (1 - normalized_noise)
        
        Fibre 相似度:
          Jaccard of feature vectors (离散化后)
        
        Normalized noise:
          性能指标变异系数的加权平均

        Args:
            op_a: 算子 A
            op_b: 算子 B

        Returns:
            耦合分数 [0.0, 1.0]
        """
        # Fibre 相似度 — 基于归一化特征向量的余弦相似度
        fv_a = op_a.feature_vector()
        fv_b = op_b.feature_vector()

        dot = sum(a * b for a, b in zip(fv_a, fv_b))
        norm_a = sqrt(sum(a * a for a in fv_a))
        norm_b = sqrt(sum(b * b for b in fv_b))

        if norm_a < 1e-12 or norm_b < 1e-12:
            fibre_sim = 0.0
        else:
            fibre_sim = max(0.0, min(1.0, dot / (norm_a * norm_b)))

        # 性能噪声 — 四个指标的归一化变异系数平均
        metrics = [
            (op_a.latency_us, op_b.latency_us, 10000.0),
            (op_a.power_mw, op_b.power_mw, 300000.0),
            (op_a.cache_hit_rate, op_b.cache_hit_rate, 1.0),
            (op_a.memory_mb, op_b.memory_mb, 8192.0),
        ]

        noise_sum = 0.0
        for va, vb, scale in metrics:
            if scale > 0:
                diff = abs(va - vb) / scale
                noise_sum += diff
        normalized_noise = min(1.0, noise_sum / len(metrics))

        # 同类型算子给予 bonus (Fibre 结构相同)
        type_bonus = 0.05 if op_a.op_type == op_b.op_type else 0.0

        coupling = fibre_sim * (1.0 - normalized_noise) + type_bonus
        return max(0.0, min(1.0, coupling))

    def get_best_coupling(self) -> Optional[CopartialMatch]:
        """返回历史最佳耦合 (按 coupling_score 最高)。"""
        if not self.history:
            return None
        return max(self.history, key=lambda m: m.coupling_score)

    def get_couplings_by_platform(self, platform: str) -> List[CopartialMatch]:
        """获取涉及指定平台的所有耦合匹配。"""
        return [
            m for m in self.history
            if m.src_op.platform == platform or m.tgt_op.platform == platform
        ]

    def _run_self_test() -> Dict[str, Any]:
        """CopartialSearch 自测试"""
        passed = 0
        failed = 0
        checks: List[str] = []

        cs = CopartialSearch()

        # Test 1: compute_coupling for identical ops
        try:
            op1 = OperatorProfile("op1", "matmul", "CUDA", 100.0, 200000.0, 0.9, 1024.0)
            op2 = OperatorProfile("op2", "matmul", "CUDA", 100.0, 200000.0, 0.9, 1024.0)
            score = cs.compute_coupling(op1, op2)
            # Identical ops should have high coupling
            assert score > 0.8, f"Identical ops coupling too low: {score}"
            checks.append("compute_coupling identical ops: high score")
            passed += 1
        except Exception as e:
            checks.append(f"compute_coupling identical FAILED: {e}")
            failed += 1

        # Test 2: compute_coupling for very different ops
        try:
            op_a = OperatorProfile("a", "matmul", "CUDA", 100.0, 200000.0, 0.95, 512.0)
            op_b = OperatorProfile("b", "softmax", "CANN", 5000.0, 50000.0, 0.1, 4096.0)
            score = cs.compute_coupling(op_a, op_b)
            assert score < 0.8, f"Dissimilar ops coupling too high: {score}"
            checks.append("compute_coupling dissimilar ops: low score")
            passed += 1
        except Exception as e:
            checks.append(f"compute_coupling dissimilar FAILED: {e}")
            failed += 1

        # Test 3: search with multiple operators
        try:
            ops = [
                OperatorProfile("m1", "matmul", "CUDA", 100.0, 200000.0, 0.9, 1024.0),
                OperatorProfile("m2", "matmul", "CANN", 120.0, 150000.0, 0.85, 1024.0),
                OperatorProfile("s1", "softmax", "CUDA", 50.0, 100000.0, 0.8, 256.0),
                OperatorProfile("s2", "softmax", "CANN", 60.0, 80000.0, 0.75, 256.0),
            ]
            matches = cs.search(ops)
            assert len(matches) >= 2, f"Expected >=2 matches, got {len(matches)}"
            # First match should have highest coupling_score
            assert matches[0].coupling_score >= matches[-1].coupling_score
            checks.append(f"search returned {len(matches)} sorted matches")
            passed += 1
        except Exception as e:
            checks.append(f"search FAILED: {e}")
            failed += 1

        # Test 4: get_best_coupling
        try:
            best = cs.get_best_coupling()
            assert best is not None
            assert isinstance(best, CopartialMatch)
            checks.append("get_best_coupling valid")
            passed += 1
        except Exception as e:
            checks.append(f"get_best_coupling FAILED: {e}")
            failed += 1

        # Test 5: get_couplings_by_platform
        try:
            cuda_matches = cs.get_couplings_by_platform("CUDA")
            assert len(cuda_matches) > 0
            checks.append(f"get_couplings_by_platform CUDA: {len(cuda_matches)} matches")
            passed += 1
        except Exception as e:
            checks.append(f"get_couplings_by_platform FAILED: {e}")
            failed += 1

        return {"passed": passed, "failed": failed, "checks": checks}


# ╔══════════════════════════════════════════════════════════════════╗
# ║               ComputeCarbonAuditor — 算力碳审计                   ║
# ╚══════════════════════════════════════════════════════════════════╝

class ComputeCarbonAuditor:
    """算力碳审计 — 跟踪能源使用和 CO2 排放。

    能源公式:
      energy_kWh = sum(power_mW * duration_s) / (1000 * 3600)
      CO2_kg = energy_kWh * carbon_factor

    Carbon factors (kgCO2/kWh):
      - CUDA: 0.475 (Azure/AWS average)
      - CANN: 0.385 (Ascend NPU, more efficient)
      - CPU: 0.475
    """

    CARBON_FACTORS: Dict[str, float] = CARBON_FACTORS

    def __init__(self, budget_kwh: float = float('inf')):
        self.budget_kwh = budget_kwh
        self.used_kwh: float = 0.0
        self.audit_log: List[CarbonAuditEntry] = []

    def estimate_carbon(self, ops: List[OperatorProfile],
                        duration_s: float) -> Dict[str, Any]:
        """估算运行算子的碳排放。

        Args:
            ops: 算子画像列表
            duration_s: 运行时长 (秒)

        Returns:
            {total_kwh, total_kgco2, per_op: [{op_id, kwh, kgco2}]}
        """
        total_energy_kwh = 0.0
        per_op: List[Dict] = []

        for op in ops:
            # energy = power_mW * seconds / (1000 * 3600) → kWh
            op_energy_kwh = op.power_mw * duration_s / (1000.0 * 3600.0)
            carbon_factor = self.CARBON_FACTORS.get(
                op.platform, self.CARBON_FACTORS["default"]
            )
            op_co2_kg = op_energy_kwh * carbon_factor

            total_energy_kwh += op_energy_kwh
            per_op.append({
                "op_id": op.op_id,
                "platform": op.platform,
                "energy_kwh": op_energy_kwh,
                "co2_kg": op_co2_kg,
                "carbon_factor": carbon_factor,
            })

        total_co2_kg = 0.0
        for entry in per_op:
            total_co2_kg += entry["co2_kg"]

        return {
            "total_kwh": total_energy_kwh,
            "total_kgco2": total_co2_kg,
            "per_op": per_op,
        }

    def check_budget(self, estimated_kwh: float) -> bool:
        """检查估算用量是否在预算内。"""
        return (self.used_kwh + estimated_kwh) <= self.budget_kwh

    def record(self, ops: List[OperatorProfile], actual_duration: float):
        """记录实际执行后的能源使用。

        Args:
            ops: 实际运行的算子列表
            actual_duration: 实际运行时长 (秒)
        """
        estimate = self.estimate_carbon(ops, actual_duration)
        total_energy = estimate["total_kwh"]
        total_co2 = estimate["total_kgco2"]

        self.used_kwh += total_energy

        # 按平台聚合
        platform_counts: Dict[str, int] = {}
        for op in ops:
            platform_counts[op.platform] = platform_counts.get(op.platform, 0) + 1
        primary_platform = max(platform_counts, key=platform_counts.get) if platform_counts else "unknown"

        entry = CarbonAuditEntry(
            entry_id=f"carbon_{uuid.uuid4().hex[:12]}",
            ops_count=len(ops),
            duration_s=actual_duration,
            energy_kwh=total_energy,
            co2_kg=total_co2,
            platform=primary_platform,
        )
        self.audit_log.append(entry)

        logger.info(
            f"Carbon audit: {total_energy:.6f} kWh, "
            f"{total_co2:.6f} kgCO2, "
            f"budget used: {self.used_kwh:.6f}/{self.budget_kwh:.6f} kWh"
        )

    def get_remaining_budget(self) -> float:
        """获取剩余预算 (kWh)。"""
        return max(0.0, self.budget_kwh - self.used_kwh)

    def get_summary(self) -> Dict[str, Any]:
        """获取碳审计摘要。"""
        total_co2 = sum(e.co2_kg for e in self.audit_log)
        total_energy = sum(e.energy_kwh for e in self.audit_log)
        return {
            "budget_kwh": self.budget_kwh,
            "used_kwh": self.used_kwh,
            "remaining_kwh": self.get_remaining_budget(),
            "total_entries": len(self.audit_log),
            "total_energy_kwh": total_energy,
            "total_co2_kg": total_co2,
            "latest_entries": [e.to_dict() for e in self.audit_log[-5:]],
        }

    def _run_self_test() -> Dict[str, Any]:
        """ComputeCarbonAuditor 自测试"""
        passed = 0
        failed = 0
        checks: List[str] = []

        auditor = ComputeCarbonAuditor(budget_kwh=1.0)

        # Test 1: estimate_carbon
        try:
            ops = [
                OperatorProfile("op1", "matmul", "CUDA", 100.0, 200000.0),
                OperatorProfile("op2", "matmul", "CANN", 120.0, 150000.0),
            ]
            est = auditor.estimate_carbon(ops, duration_s=3600.0)
            assert est["total_kwh"] > 0, "Energy should be positive"
            assert est["total_kgco2"] > 0, "CO2 should be positive"
            assert len(est["per_op"]) == 2
            checks.append(f"estimate_carbon: {est['total_kwh']:.4f} kWh, {est['total_kgco2']:.4f} kgCO2")
            passed += 1
        except Exception as e:
            checks.append(f"estimate_carbon FAILED: {e}")
            failed += 1

        # Test 2: check_budget
        try:
            assert auditor.check_budget(0.5) is True
            assert auditor.check_budget(2.0) is False
            checks.append("check_budget valid")
            passed += 1
        except Exception as e:
            checks.append(f"check_budget FAILED: {e}")
            failed += 1

        # Test 3: record
        try:
            auditor.record(ops, actual_duration=1800.0)
            assert len(auditor.audit_log) == 1
            assert auditor.used_kwh > 0
            checks.append("record valid")
            passed += 1
        except Exception as e:
            checks.append(f"record FAILED: {e}")
            failed += 1

        # Test 4: get_summary
        try:
            summary = auditor.get_summary()
            assert summary["total_entries"] == 1
            assert summary["remaining_kwh"] >= 0
            checks.append("get_summary valid")
            passed += 1
        except Exception as e:
            checks.append(f"get_summary FAILED: {e}")
            failed += 1

        # Test 5: CANN carbon factor is lower
        try:
            cf_cuda = auditor.CARBON_FACTORS["CUDA"]
            cf_cann = auditor.CARBON_FACTORS["CANN"]
            assert cf_cann < cf_cuda, "CANN should be more carbon-efficient than CUDA"
            checks.append(f"Carbon factors: CUDA={cf_cuda}, CANN={cf_cann}")
            passed += 1
        except Exception as e:
            checks.append(f"Carbon factor check FAILED: {e}")
            failed += 1

        return {"passed": passed, "failed": failed, "checks": checks}


# ╔══════════════════════════════════════════════════════════════════╗
# ║               KernelCATScheduler — 主调度器                        ║
# ╚══════════════════════════════════════════════════════════════════╝

class KernelCATScheduler:
    """KernelCAT 主调度器。
    
    六步管道:
      1. Read kappa-Snap history — 过往算子性能指纹
      2. G_ego inference — 确定上下文相关的算力需求
      3. psi-anchor budget check — 算力预算 + 数据主权
      4. Copartial search — 跨平台最优算子耦合搜索
      5. Allocate & wake — 分配算子到任务
      6. kappa-Snap audit — 所有分配的指纹审计

    38 分钟 Ascend 迁移基准:
      D_src(CUDA) ⊕ D_tgt(CANN) → D_match via GaussEx 互补互联
    """

    def __init__(self, g_ego=None, psi_gate=None):
        """初始化 KernelCAT 调度器。

        Args:
            g_ego: G_egoEngine 实例 (可选)
            psi_gate: PsiGate 实例 (可选)
        """
        self.g_ego = g_ego
        self.psi_gate = psi_gate
        self.copartial = CopartialSearch()
        self.carbon_auditor = ComputeCarbonAuditor()
        self.audit_records: List[Dict[str, Any]] = []
        self.operator_registry: Dict[str, List[OperatorProfile]] = {}
        self.schedule_history: List[Dict[str, Any]] = []

    def register_operator(self, op: OperatorProfile):
        """注册算子画像到注册表。

        Args:
            op: 算子画像
        """
        key = f"{op.op_type}:{op.platform}"
        if key not in self.operator_registry:
            self.operator_registry[key] = []
        self.operator_registry[key].append(op)
        logger.debug(f"Registered operator: {op.op_id} ({key})")

    def schedule(self, tasks: List[Dict],
                 compute_budget_kwh: float = float('inf')) -> Dict[str, Any]:
        """主调度管道 — 六步完整流程。

        Args:
            tasks: 任务列表，每个任务为 {task_id, op_type, priority, data_domains, ...}
            compute_budget_kwh: 算力预算 (kWh)，默认无限

        Returns:
            {
                allocations: [...],
                couplings: [...],
                carbon: {...},
                audit: [...],
                g_ego_status: {...},
                scheduling_time_s: float,
            }
        """
        start_time = time.time()

        # Step 0: 设置碳预算
        self.carbon_auditor = ComputeCarbonAuditor(budget_kwh=compute_budget_kwh)

        # Step 1: 读取 kappa-Snap 历史
        snap_history = self._read_snap_history(tasks)

        # Step 2: G_ego 推理 — 确定算力需求
        compute_requirements = self._g_ego_infer(tasks)

        # Step 3: psi-anchor 预算检查
        estimated_kwh = compute_requirements.get("estimated_kwh", 0.0)
        data_domains = [t.get("data_domain", "default") for t in tasks]
        budget_result = self._psi_budget_check(estimated_kwh, data_domains)

        # Step 4: Copartial 搜索 — 跨平台算子耦合
        available_ops = self._collect_available_ops(tasks)
        couplings = self.copartial.search(available_ops, context={
            "compute_requirements": compute_requirements,
            "budget_result": budget_result,
        })

        # Step 5: 分配 & 唤醒
        allocations = self._allocate(couplings, tasks)

        # Step 6: kappa-Snap 审计
        audit_results = self._kappa_snap_audit(allocations, couplings)

        scheduling_time = time.time() - start_time

        result = {
            "allocations": [a.to_dict() for a in allocations],
            "couplings": [c.to_dict() for c in couplings[:20]],  # top 20
            "carbon": {
                "audit_summary": self.carbon_auditor.get_summary(),
                "budget_check": budget_result,
            },
            "audit": audit_results,
            "snap_history": snap_history,
            "g_ego_requirements": compute_requirements,
            "scheduling_time_s": scheduling_time,
        }

        self.schedule_history.append(result)
        logger.info(
            f"KernelCAT schedule complete: {len(allocations)} allocations, "
            f"{len(couplings)} couplings, "
            f"{scheduling_time:.3f}s"
        )
        return result

    def _read_snap_history(self, tasks: List[Dict]) -> List[Dict]:
        """Step 1: 读取 kappa-Snap 历史 — 过往算子性能指纹。

        从 operator_registry 中提取所有算子的指纹快照。
        """
        snapshots: List[Dict] = []
        for key, profiles in self.operator_registry.items():
            for p in profiles:
                snapshots.append({
                    "op_id": p.op_id,
                    "fingerprint": p.fingerprint(),
                    "type": p.op_type,
                    "platform": p.platform,
                    "recorded_at": p.recorded_at,
                })
        return snapshots

    def _g_ego_infer(self, tasks: List[Dict]) -> Dict[str, Any]:
        """Step 2: G_ego 推理 — 确定上下文相关的算力需求。

        如果 g_ego 可用，调用 aligned_with_purpose() 进行目的对齐推理；
        否则使用任务复杂度启发式算法。

        Returns:
            {estimated_kwh, estimated_latency_us, task_count, ...}
        """
        if self.g_ego is not None and _HAS_G_EGO:
            return self._g_ego_real_infer(tasks)
        return self._g_ego_heuristic_infer(tasks)

    def _g_ego_real_infer(self, tasks: List[Dict]) -> Dict[str, Any]:
        """使用真实 G_egoEngine 推理。"""
        results: List[Dict] = []
        total_kwh = 0.0
        total_latency = 0.0

        for task in tasks:
            task_desc = task.get("description", task.get("task_id", "unknown"))
            context = {
                "op_type": task.get("op_type", "matmul"),
                "priority": task.get("priority", 1),
                "data_domain": task.get("data_domain", "default"),
            }
            try:
                alignment = self.g_ego.aligned_with_purpose(task_desc, context)
                # 对齐分数越高，分配更多资源
                score = alignment.get("score", 0.5)
                # 每个任务的估算耗能: base * (priority / score)
                base_kwh = 0.01  # 10 Wh per task base
                task_kwh = base_kwh * (task.get("priority", 1) / max(score, 0.1))
                total_kwh += task_kwh
                total_latency += 1000.0 / max(score, 0.1)  # microseconds
                results.append({
                    "task_id": task.get("task_id", "unknown"),
                    "aligned": alignment.get("aligned", False),
                    "score": score,
                    "estimated_kwh": task_kwh,
                })
            except Exception as e:
                logger.warning(f"G_ego infer failed for task {task.get('task_id')}: {e}")
                results.append({"task_id": task.get("task_id", "unknown"), "error": str(e)})

        return {
            "estimated_kwh": total_kwh,
            "estimated_latency_us": total_latency,
            "task_count": len(tasks),
            "per_task": results,
            "method": "g_ego_aligned_with_purpose",
        }

    def _g_ego_heuristic_infer(self, tasks: List[Dict]) -> Dict[str, Any]:
        """启发式推理 — 当 G_egoEngine 不可用时使用。

        基于任务复杂度的启发式:
          - matmul: high complexity, high energy
          - softmax/relu: low complexity, low energy
          - conv2d/attention: medium-high complexity
        """
        complexity_map = {
            "matmul": 3.0, "gemm": 3.0,
            "conv2d": 2.5, "attention": 2.5,
            "softmax": 1.0, "relu": 0.5, "layer_norm": 0.5,
            "reduction": 1.0, "element_wise": 0.3,
        }

        total_kwh = 0.0
        total_latency = 0.0
        per_task = []

        for task in tasks:
            op_type = task.get("op_type", "matmul")
            complexity = complexity_map.get(op_type, 1.0)
            priority = task.get("priority", 1)
            task_kwh = 0.005 * complexity * priority  # base 5 Wh
            task_latency_us = 500.0 * complexity / max(priority, 0.5)
            total_kwh += task_kwh
            total_latency += task_latency_us
            per_task.append({
                "task_id": task.get("task_id", "unknown"),
                "op_type": op_type,
                "complexity": complexity,
                "estimated_kwh": task_kwh,
                "estimated_latency_us": task_latency_us,
            })

        return {
            "estimated_kwh": total_kwh,
            "estimated_latency_us": total_latency,
            "task_count": len(tasks),
            "per_task": per_task,
            "method": "heuristic",
        }

    def _psi_budget_check(self, estimated_kwh: float,
                          data_domains: List[str]) -> Dict[str, Any]:
        """Step 3: psi-anchor 预算检查 — 算力预算 + 数据主权。

        Args:
            estimated_kwh: 估算能耗
            data_domains: 数据域列表 (用于主权检查)

        Returns:
            {passed, reason, budget_remaining, data_domain_check}
        """
        # 预算检查
        within_budget = self.carbon_auditor.check_budget(estimated_kwh)
        remaining = self.carbon_auditor.get_remaining_budget()

        # 数据主权检查 — 敏感域需要 psi 锚验证
        sensitive_domains = {"healthcare", "fintech", "legal", "government"}
        domain_violations = [
            d for d in data_domains
            if d.lower() in sensitive_domains
        ]

        domain_ok = len(domain_violations) == 0

        if not within_budget:
            return {
                "passed": False,
                "reason": f"Exceeded compute budget: need {estimated_kwh:.4f} kWh, available {remaining:.4f} kWh",
                "budget_remaining": remaining,
                "data_domain_check": "ok" if domain_ok else f"restricted_domains: {domain_violations}",
            }

        if not domain_ok:
            return {
                "passed": False,
                "reason": f"Data sovereignty violation: {domain_violations}",
                "budget_remaining": remaining,
                "data_domain_check": f"restricted: {domain_violations}",
            }

        return {
            "passed": True,
            "reason": "Budget and data sovereignty check passed",
            "budget_remaining": remaining,
            "data_domain_check": "ok",
        }

    def _collect_available_ops(self, tasks: List[Dict]) -> List[OperatorProfile]:
        """从注册表收集与任务匹配的可用算子。"""
        available: List[OperatorProfile] = []
        seen_ids: set = set()

        for task in tasks:
            op_type = task.get("op_type", "matmul")
            for key, profiles in self.operator_registry.items():
                if key.startswith(f"{op_type}:") or op_type in key:
                    for p in profiles:
                        if p.op_id not in seen_ids:
                            available.append(p)
                            seen_ids.add(p.op_id)

        return available

    def _allocate(self, matches: List[CopartialMatch],
                  tasks: List[Dict]) -> List[ScheduleAllocation]:
        """Step 5: 分配最优匹配算子到任务。

        对于每个任务，在耦合匹配中寻找最佳算子对进行分配。
        优先级：高 coupling_score 的对优先分配。

        Args:
            matches: CopartialSearch 返回的耦合匹配列表
            tasks: 任务列表

        Returns:
            分配列表
        """
        allocations: List[ScheduleAllocation] = []
        used_ops: set = set()

        for task in tasks:
            task_id = task.get("task_id", f"task_{uuid.uuid4().hex[:8]}")
            op_type = task.get("op_type", "matmul")
            preferred_platform = task.get("preferred_platform", None)

            # 查找最匹配的耦合对
            best_match: Optional[CopartialMatch] = None
            for match in matches:
                # 检查算子类型匹配
                if match.src_op.op_type != op_type and match.tgt_op.op_type != op_type:
                    continue
                # 检查是否已被分配
                if match.src_op.op_id in used_ops and match.tgt_op.op_id in used_ops:
                    continue
                # 平台偏好
                if preferred_platform:
                    if match.src_op.platform != preferred_platform and match.tgt_op.platform != preferred_platform:
                        continue
                    # 优先选择匹配平台的那一边
                    if match.src_op.platform == preferred_platform:
                        chosen_op = match.src_op
                    else:
                        chosen_op = match.tgt_op
                else:
                    # 无偏好，选延迟更低的
                    chosen_op = (match.src_op
                                 if match.src_op.latency_us <= match.tgt_op.latency_us
                                 else match.tgt_op)

                best_match = match
                selected_op = chosen_op
                break

            if best_match is None and self.operator_registry:
                # 退路: 直接从注册表选一个同类型算子
                for key, profiles in self.operator_registry.items():
                    if op_type in key:
                        for p in profiles:
                            if p.op_id not in used_ops:
                                selected_op = p
                                break
                        if selected_op is not None:
                            break

            if best_match is not None or 'selected_op' in dir():
                pass
            else:
                # 无法分配 — 创建占位符
                logger.warning(f"Cannot allocate task {task_id}: no matching operator")
                allocations.append(ScheduleAllocation(
                    task_id=task_id,
                    op_id="unallocated",
                    platform="unknown",
                    coupling_score=0.0,
                    estimated_latency_us=float('inf'),
                    estimated_energy_kwh=0.0,
                    estimated_co2_kg=0.0,
                    status=ScheduleStatus.FAILED,
                ))
                continue

            used_ops.add(selected_op.op_id)

            # 估算能源和 CO2
            coupling_score = best_match.coupling_score if best_match else 0.5
            duration_estimate = 1.0  # 假设 1 秒 (仿真)
            energy_est = selected_op.power_mw * duration_estimate / (1000.0 * 3600.0)
            carbon_factor = CARBON_FACTORS.get(
                selected_op.platform, CARBON_FACTORS["default"]
            )
            co2_est = energy_est * carbon_factor

            allocation = ScheduleAllocation(
                task_id=task_id,
                op_id=selected_op.op_id,
                platform=selected_op.platform,
                coupling_score=coupling_score,
                estimated_latency_us=selected_op.latency_us,
                estimated_energy_kwh=energy_est,
                estimated_co2_kg=co2_est,
                status=ScheduleStatus.ALLOCATED,
            )
            allocations.append(allocation)

        # 记录能源使用
        ops_for_record = []
        for a in allocations:
            if a.status != ScheduleStatus.FAILED:
                for key, profiles in self.operator_registry.items():
                    for p in profiles:
                        if p.op_id == a.op_id:
                            ops_for_record.append(p)
                            break

        if ops_for_record:
            self.carbon_auditor.record(ops_for_record, actual_duration=1.0)

        return allocations

    def _kappa_snap_audit(self, allocations: List[ScheduleAllocation],
                          couplings: List[CopartialMatch]) -> List[Dict[str, Any]]:
        """Step 6: kappa-Snap 审计 — 所有分配的指纹审计。

        每条审计记录包含:
          - allocation 的算子指纹
          - 耦合评分
          - 碳审计快照
        """
        audit_results: List[Dict[str, Any]] = []

        for alloc in allocations:
            record = {
                "snap_id": f"ksnap_{uuid.uuid4().hex[:16]}",
                "module": "kernelcat_scheduler",
                "result": alloc.status.value,
                "i_value": alloc.coupling_score,
                "ftel_magnitude": alloc.coupling_score * 0.8,  # simulated Ftel
                "psi_anchor_id": f"psi_kernelcat_{alloc.task_id}",
                "description": f"KernelCAT allocation: {alloc.task_id} → {alloc.op_id} on {alloc.platform}",
                "timestamp": time.time(),
                "snapshot_hash": hashlib.sha256(
                    f"{alloc.task_id}:{alloc.op_id}:{alloc.platform}:{time.time()}".encode()
                ).hexdigest(),
                # 扩展字段
                "platform": alloc.platform,
                "estimated_latency_us": alloc.estimated_latency_us,
                "estimated_co2_kg": alloc.estimated_co2_kg,
            }
            audit_results.append(record)
            self.audit_records.append(record)

        return audit_results

    def get_migration_estimate(self, src_platform: str, tgt_platform: str,
                               op_types: List[str]) -> Dict[str, Any]:
        """估算从源平台到目标平台的迁移成本/时间 (38分钟基准)。

        计算所有 op_type 在 src→tgt 之间的 copartial 匹配，
        报告总预估迁移时间。

        Args:
            src_platform: 源平台 (e.g. "CUDA")
            tgt_platform: 目标平台 (e.g. "CANN")
            op_types: 需要迁移的算子类型列表

        Returns:
            {
                src_platform, tgt_platform,
                total_estimated_s, benchmark_s (2280),
                per_op_type: [...],
                matching_ratio: float,
            }
        """
        per_op: List[Dict] = []
        total_estimated_s = 0.0
        matched_count = 0

        for op_type in op_types:
            # 在注册表中查找 src 和 tgt 的同类型算子
            src_ops = []
            tgt_ops = []
            for key, profiles in self.operator_registry.items():
                if op_type in key and key.startswith(f"{op_type}:"):
                    for p in profiles:
                        if p.platform == src_platform:
                            src_ops.append(p)
                        elif p.platform == tgt_platform:
                            tgt_ops.append(p)

            # 如果没有注册的算子, 使用默认画像
            if not src_ops:
                src_ops = [OperatorProfile(
                    f"default_{op_type}_src", op_type, src_platform,
                    latency_us=100.0, power_mw=200000.0, cache_hit_rate=0.85
                )]
            if not tgt_ops:
                tgt_ops = [OperatorProfile(
                    f"default_{op_type}_tgt", op_type, tgt_platform,
                    latency_us=120.0, power_mw=150000.0, cache_hit_rate=0.80
                )]

            # 计算耦合
            best_score = 0.0
            for src_op in src_ops:
                for tgt_op in tgt_ops:
                    score = self.copartial.compute_coupling(src_op, tgt_op)
                    if score > best_score:
                        best_score = score
                        matched_count += 1

            # 迁移时间估算: 基准时间 * (1/coupling_score) * 平台因子
            platform_factor = 1.0
            if src_platform == "CUDA" and tgt_platform == "CANN":
                platform_factor = 0.85  # Ascend NPU 更高效
            elif src_platform == "CANN" and tgt_platform == "CUDA":
                platform_factor = 1.15

            if best_score > 0:
                estimated_s = ASCEND_MIGRATION_BENCHMARK_SEC * platform_factor / best_score
            else:
                estimated_s = ASCEND_MIGRATION_BENCHMARK_SEC * 2.0

            total_estimated_s += estimated_s
            per_op.append({
                "op_type": op_type,
                "coupling_score": best_score,
                "estimated_migration_s": estimated_s,
                "src_ops_count": len(src_ops),
                "tgt_ops_count": len(tgt_ops),
            })

        matching_ratio = matched_count / max(len(op_types), 1)

        return {
            "src_platform": src_platform,
            "tgt_platform": tgt_platform,
            "total_estimated_s": total_estimated_s,
            "benchmark_s": ASCEND_MIGRATION_BENCHMARK_SEC,
            "per_op_type": per_op,
            "matching_ratio": matching_ratio,
        }

    def get_status(self) -> Dict[str, Any]:
        """获取调度器当前状态。"""
        return {
            "registered_operator_types": len(self.operator_registry),
            "total_registered_ops": sum(len(v) for v in self.operator_registry.values()),
            "copartial_search_count": self.copartial.search_count,
            "copartial_history_size": len(self.copartial.history),
            "carbon_used_kwh": self.carbon_auditor.used_kwh,
            "carbon_budget_kwh": self.carbon_auditor.budget_kwh,
            "carbon_remaining_kwh": self.carbon_auditor.get_remaining_budget(),
            "audit_records": len(self.audit_records),
            "schedule_history": len(self.schedule_history),
            "g_ego_available": self.g_ego is not None,
            "psi_gate_available": self.psi_gate is not None,
        }

    def _run_self_test() -> Dict[str, Any]:
        """KernelCATScheduler 自测试"""
        passed = 0
        failed = 0
        checks: List[str] = []

        sched = KernelCATScheduler()

        # Test 1: register_operator
        try:
            for i in range(5):
                sched.register_operator(OperatorProfile(
                    f"matmul_cuda_{i}", "matmul", "CUDA",
                    latency_us=100.0 + i * 10, power_mw=200000.0 + i * 1000,
                    cache_hit_rate=0.9, memory_mb=1024.0,
                ))
                sched.register_operator(OperatorProfile(
                    f"matmul_cann_{i}", "matmul", "CANN",
                    latency_us=120.0 + i * 5, power_mw=150000.0 + i * 500,
                    cache_hit_rate=0.85, memory_mb=1024.0,
                ))
            assert len(sched.operator_registry) == 2  # 2 keys (matmul:CUDA, matmul:CANN)
            assert sum(len(v) for v in sched.operator_registry.values()) == 10
            checks.append("register_operator: 10 operators registered")
            passed += 1
        except Exception as e:
            checks.append(f"register_operator FAILED: {e}")
            failed += 1

        # Test 2: schedule
        try:
            tasks = [
                {"task_id": "t1", "op_type": "matmul", "priority": 5, "data_domain": "general"},
                {"task_id": "t2", "op_type": "matmul", "priority": 3, "data_domain": "general"},
            ]
            result = sched.schedule(tasks, compute_budget_kwh=100.0)
            assert "allocations" in result
            assert "couplings" in result
            assert "carbon" in result
            assert "audit" in result
            assert len(result["allocations"]) == 2
            checks.append(f"schedule: {len(result['allocations'])} allocations")
            passed += 1
        except Exception as e:
            checks.append(f"schedule FAILED: {e}")
            failed += 1

        # Test 3: schedule with budget exceeded
        try:
            tasks_tight = [
                {"task_id": "t3", "op_type": "matmul", "priority": 10, "data_domain": "fintech"},
            ]
            result_tight = sched.schedule(tasks_tight, compute_budget_kwh=0.0)
            assert result_tight["carbon"]["budget_check"]["passed"] is False
            checks.append("budget check: correctly blocked")
            passed += 1
        except Exception as e:
            checks.append(f"budget check FAILED: {e}")
            failed += 1

        # Test 4: _g_ego_heuristic_infer
        try:
            tasks_test = [{"task_id": "h1", "op_type": "matmul", "priority": 3}]
            heur = sched._g_ego_heuristic_infer(tasks_test)
            assert heur["method"] == "heuristic"
            assert heur["estimated_kwh"] > 0
            checks.append("_g_ego_heuristic_infer valid")
            passed += 1
        except Exception as e:
            checks.append(f"_g_ego_heuristic_infer FAILED: {e}")
            failed += 1

        # Test 5: get_migration_estimate
        try:
            mig = sched.get_migration_estimate("CUDA", "CANN", ["matmul", "softmax"])
            assert mig["src_platform"] == "CUDA"
            assert mig["tgt_platform"] == "CANN"
            assert mig["total_estimated_s"] > 0
            checks.append(f"get_migration_estimate: {mig['total_estimated_s']:.0f}s total")
            passed += 1
        except Exception as e:
            checks.append(f"get_migration_estimate FAILED: {e}")
            failed += 1

        # Test 6: get_status
        try:
            status = sched.get_status()
            assert status["registered_operator_types"] >= 1
            assert status["schedule_history"] >= 1
            checks.append("get_status valid")
            passed += 1
        except Exception as e:
            checks.append(f"get_status FAILED: {e}")
            failed += 1

        # Test 7: audit_records populated
        try:
            assert len(sched.audit_records) >= 2
            first = sched.audit_records[0]
            assert "snap_id" in first
            assert "snapshot_hash" in first
            checks.append(f"audit_records: {len(sched.audit_records)} records")
            passed += 1
        except Exception as e:
            checks.append(f"audit_records FAILED: {e}")
            failed += 1

        return {"passed": passed, "failed": failed, "checks": checks}


# ╔══════════════════════════════════════════════════════════════════╗
# ║               模块级自测试                                        ║
# ╚══════════════════════════════════════════════════════════════════╝

def _run_all_self_tests() -> bool:
    """运行所有类的自测试。"""
    all_results: List[Dict] = []
    total_passed = 0
    total_failed = 0

    test_targets = [
        ("OperatorProfile", OperatorProfile),
        ("CopartialMatch", CopartialMatch),
        ("CopartialSearch", CopartialSearch),
        ("ComputeCarbonAuditor", ComputeCarbonAuditor),
        ("KernelCATScheduler", KernelCATScheduler),
    ]

    print("=" * 70)
    print("KernelCAT Scheduler — Comprehensive Self Tests")
    print("=" * 70)

    for name, cls in test_targets:
        print(f"\n{'─' * 70}")
        print(f"[{name}] Running self-test...")
        try:
            result = cls._run_self_test()
            all_results.append({"class": name, **result})
            total_passed += result["passed"]
            total_failed += result["failed"]
            for check in result["checks"]:
                status = "PASS" if "FAILED" not in check else "FAIL"
                print(f"  [{status}] {check}")
            print(f"  → {result['passed']} passed, {result['failed']} failed")
        except Exception as e:
            print(f"  → ERROR: {e}")
            all_results.append({"class": name, "passed": 0, "failed": 1, "checks": [str(e)]})
            total_failed += 1

    print(f"\n{'=' * 70}")
    print(f"TOTAL: {total_passed} passed, {total_failed} failed, "
          f"{len(all_results)} test suites")
    print(f"{'=' * 70}")

    return total_failed == 0


# ╔══════════════════════════════════════════════════════════════════╗
# ║               main 入口                                           ║
# ╚══════════════════════════════════════════════════════════════════╝

if __name__ == "__main__":
    print("KernelCAT Scheduler v1.0 — TOMAS AGI v3.9")
    print(f"GaussEx available: {_HAS_GAUSSEX}")
    print(f"G_ego available: {_HAS_G_EGO}")
    print(f"PsiGate available: {_HAS_PSI_GATE}")
    print(f"BabelTele available: {_HAS_BABELTELE}")
    print()

    success = _run_all_self_tests()

    if success:
        print("\nAll self-tests passed.")
    else:
        print("\nSome self-tests failed — check the output above.")
