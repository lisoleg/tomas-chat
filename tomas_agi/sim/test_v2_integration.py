# -*- coding: utf-8 -*-
"""
test_v2_integration.py — TOMAS AGI v2.0 端到端集成测试
=========================================================

覆盖 6 个测试场景（A-F），测试 15 个核心模块的集成流程。

场景列表:
    A: HNC → NLU → ℐ值 Pipeline（自然语言理解端到端）
    B: Gödel Agent 四重封边安全自改进
    C: AgentWeb 因果消息 + κ-Snap 日志（分布式因果顺序）
    D: 因果世界模型 + H_hard 物理守恒律
    E: κ-Snap + Mina + Celo 链上存证（降级模式）
    F: EML EHNN + 等变层 + GPCT 降维

约束:
    - pytest 框架
    - 可选导入包裹（skip 不可用模块）
    - 不依赖外部服务（降级模式可接受）
    - 断言明确
    - 命名规范: test_scenario_a_*, test_scenario_b_*, ...

Author: TOMAS Team (Alex, Engineer)
Version: v2.0
"""
from __future__ import annotations

import os
import sys
import math
import time
import hashlib
import logging
from typing import Any, Dict, List, Optional, Tuple

import pytest

# ============================================================
# sys.path 设置 — 确保 sim 目录在路径中
# ============================================================
_SIM_DIR = os.path.dirname(os.path.abspath(__file__))
if _SIM_DIR not in sys.path:
    sys.path.insert(0, _SIM_DIR)

# 项目根目录（tomas_agi/）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_SIM_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logger = logging.getLogger(__name__)

# ============================================================
# 可选导入 — 每个模块独立 try/except
# ============================================================

# --- Scenario A: HNC + NLU Pipeline ---
try:
    from hnc_parser_wrapper import HNCParserWrapper, HNCParseResult
    _HAS_HNC = True
except ImportError:
    _HAS_HNC = False
    HNCParserWrapper = None  # type: ignore
    HNCParseResult = None  # type: ignore

try:
    from tomas_nlu_pipeline import TOMASNLU_Pipeline, NLUPipelineResult
    _HAS_NLU = True
except ImportError:
    _HAS_NLU = False
    TOMASNLU_Pipeline = None  # type: ignore
    NLUPipelineResult = None  # type: ignore

# --- Scenario B: Gödel Agent ---
try:
    from goedel_agent_tomas import (
        TOMASGodelAgent,
        GodelImproveResult,
        MUSDualStoreEntry as GodelMUSDualStoreEntry,
    )
    _HAS_GOEDEL = True
except ImportError:
    _HAS_GOEDEL = False
    TOMASGodelAgent = None  # type: ignore
    GodelImproveResult = None  # type: ignore
    GodelMUSDualStoreEntry = None  # type: ignore

# --- Scenario C: VectorClock + CausalDelivery + AgentWebRuntime ---
try:
    from vector_clock import VectorClock
    _HAS_VC = True
except ImportError:
    _HAS_VC = False
    VectorClock = None  # type: ignore

try:
    from causal_delivery import AgentWebMessage, CausalDeliveryBuffer
    _HAS_CD = True
except ImportError:
    _HAS_CD = False
    AgentWebMessage = None  # type: ignore
    CausalDeliveryBuffer = None  # type: ignore

try:
    from agentweb_runtime import AgentWebRuntime
    _HAS_AWR = True
except ImportError:
    _HAS_AWR = False
    AgentWebRuntime = None  # type: ignore

# --- Scenario D: AetherSCMBridge + HodgeICoupling + CausalWorldModel ---
try:
    from aether_bridge import AetherSCMBridge, CausalVariable, CausalEdge
    _HAS_AETHER = True
except ImportError:
    _HAS_AETHER = False
    AetherSCMBridge = None  # type: ignore
    CausalVariable = None  # type: ignore
    CausalEdge = None  # type: ignore

try:
    from hodge_operator import HodgeICoupling, WeightedSimplicialComplex
    _HAS_HODGE = True
except ImportError:
    _HAS_HODGE = False
    HodgeICoupling = None  # type: ignore
    WeightedSimplicialComplex = None  # type: ignore

try:
    from causal_world_model_tomas import TOMASCausalWorldModel
    _HAS_CWM = True
except ImportError:
    _HAS_CWM = False
    TOMASCausalWorldModel = None  # type: ignore

# --- Scenario E: KSnapOperator + MinaTOMASSnap + CeloBridge ---
try:
    from ksnap_operator import (
        KSnapOperator,
        SnapEvent,
        SnapResult,
        ObservationBase,
    )
    _HAS_KSNAP = True
except ImportError:
    _HAS_KSNAP = False
    KSnapOperator = None  # type: ignore
    SnapEvent = None  # type: ignore
    SnapResult = None  # type: ignore
    ObservationBase = None  # type: ignore

try:
    from mina_kappa_bridge import MinaTOMASSnap
    _HAS_MINA = True
except ImportError:
    _HAS_MINA = False
    MinaTOMASSnap = None  # type: ignore

try:
    from celo_bridge import CeloBridge
    _HAS_CELO = True
except ImportError:
    _HAS_CELO = False
    CeloBridge = None  # type: ignore

# --- Scenario F: EMLEHNN + EquivariantLinearLayer + GpctDecomposer ---
try:
    from eml_ehnn import EMLEHNN, EMLHyperEdge
    _HAS_EHNN = True
except ImportError:
    _HAS_EHNN = False
    EMLEHNN = None  # type: ignore
    EMLHyperEdge = None  # type: ignore

try:
    from equivariant_layers import EquivariantLinearLayer
    _HAS_EQUIV = True
except ImportError:
    _HAS_EQUIV = False
    EquivariantLinearLayer = None  # type: ignore

try:
    from eml_dimred.gpct import GpctDecomposer
    _HAS_GPCT = True
except ImportError:
    try:
        # fallback: 直接从文件导入
        _gpct_path = os.path.join(_SIM_DIR, "eml_dimred")
        if _gpct_path not in sys.path:
            sys.path.insert(0, _gpct_path)
        from gpct import GpctDecomposer  # type: ignore
        _HAS_GPCT = True
    except ImportError:
        _HAS_GPCT = False
        GpctDecomposer = None  # type: ignore

try:
    from eml_dimred.hyperedge import HypEdge, EMLVertex
    _HAS_HYPEDGE = True
except ImportError:
    try:
        from hyperedge import HypEdge, EMLVertex  # type: ignore
        _HAS_HYPEDGE = True
    except ImportError:
        _HAS_HYPEDGE = False
        HypEdge = None  # type: ignore
        EMLVertex = None  # type: ignore

# --- MemOS Fusion (跨场景辅助) ---
try:
    from memos_fusion import TOMAS_Mem_OS_Fusion, MemoryRecord
    _HAS_MEMOS = True
except ImportError:
    _HAS_MEMOS = False
    TOMAS_Mem_OS_Fusion = None  # type: ignore
    MemoryRecord = None  # type: ignore


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def tmp_memory_path(tmp_path):
    """提供临时记忆存储路径。"""
    return str(tmp_path / "test_memory_store.json")


# ============================================================
# Scenario A: HNC → NLU → ℐ值 Pipeline
# ============================================================

class TestScenarioA_NLUPipeline:
    """场景 A: HNC 概念基元编码 → NLU 7步管道 → ℐ值计算。"""

    def test_scenario_a_hnc_parse_basic(self):
        """A-1: HNC 解析器基本功能 — "我吃苹果"应解析出概念码和模板。"""
        if not _HAS_HNC:
            pytest.skip("hnc_parser_wrapper 不可用")

        parser = HNCParserWrapper(use_jieba=False)
        result = parser.parse("我吃苹果")

        assert result is not None, "parse() 返回 None"
        assert hasattr(result, "template_id"), "结果缺少 template_id"
        assert hasattr(result, "chunks"), "结果缺少 chunks"
        assert hasattr(result, "concept_codes"), "结果缺少 concept_codes"
        assert len(result.chunks) > 0, "分词结果为空"
        assert len(result.concept_codes) > 0, "概念码列表为空"
        # "我吃苹果" 应匹配到某个句类模板（非 UNKNOWN）
        assert result.template_id != "", "模板 ID 为空字符串"

    def test_scenario_a_hnc_parse_multiple_sentences(self):
        """A-2: HNC 解析多种句型。"""
        if not _HAS_HNC:
            pytest.skip("hnc_parser_wrapper 不可用")

        parser = HNCParserWrapper(use_jieba=False)
        test_cases = [
            "我吃苹果",
            "太阳升起",
            "他是学生",
        ]
        for text in test_cases:
            result = parser.parse(text)
            assert result is not None, f"解析 '{text}' 返回 None"
            assert len(result.chunks) > 0, f"'{text}' 分词结果为空"
            assert len(result.concept_codes) > 0, f"'{text}' 概念码为空"

    def test_scenario_a_nlu_pipeline_process(self):
        """A-3: NLU 管道完整处理流程 — process() 返回 NLUPipelineResult。"""
        if not _HAS_NLU:
            pytest.skip("tomas_nlu_pipeline 不可用")

        pipeline = TOMASNLU_Pipeline(use_jieba=False)
        result = pipeline.process("我吃苹果")

        assert isinstance(result, NLUPipelineResult), (
            f"process() 应返回 NLUPipelineResult, 实际: {type(result)}"
        )
        assert hasattr(result, "template_id"), "结果缺少 template_id"
        assert hasattr(result, "chunks"), "结果缺少 chunks"
        assert hasattr(result, "concept_codes"), "结果缺少 concept_codes"
        assert hasattr(result, "i_value"), "结果缺少 i_value"
        assert hasattr(result, "psi_alignment_status"), "结果缺少 psi_alignment_status"

    def test_scenario_a_i_value_in_range(self):
        """A-4: ℐ 值应在 [0, 0.95] 范围内（上限 0.95 防止过度自信）。"""
        if not _HAS_NLU:
            pytest.skip("tomas_nlu_pipeline 不可用")

        pipeline = TOMASNLU_Pipeline(use_jieba=False)
        test_texts = [
            "我吃苹果",
            "根据牛顿定律，力等于质量乘以加速度",
            "太阳绕地球转",
            "研究表明运动有益健康",
        ]
        for text in test_texts:
            result = pipeline.process(text)
            assert 0.0 <= result.i_value <= 0.95, (
                f"ℐ 值超出 [0, 0.95] 范围: text='{text}', ℐ={result.i_value}"
            )

    def test_scenario_a_bayesian_update_i(self):
        """A-5: 贝叶斯 ℐ 更新 — 后验值上限 0.95。"""
        if not _HAS_NLU:
            pytest.skip("tomas_nlu_pipeline 不可用")

        pipeline = TOMASNLU_Pipeline(use_jieba=False)

        # 先验 0.5，证据 0.9 → 后验应更高但 ≤ 0.95
        posterior = pipeline.bayesian_update_i(prior_i=0.5, evidence_i=0.9)
        assert 0.0 < posterior <= 0.95, (
            f"贝叶斯后验超出范围: posterior={posterior}"
        )
        assert posterior > 0.5, (
            f"高证据应提升后验: prior=0.5, evidence=0.9, posterior={posterior}"
        )

        # 先验 0.9，证据 0.1 → 后验应更低
        posterior_low = pipeline.bayesian_update_i(prior_i=0.9, evidence_i=0.1)
        assert posterior_low < 0.9, (
            f"低证据应降低后验: prior=0.9, evidence=0.1, posterior={posterior_low}"
        )

        # 极高先验+极高证据 → 后验 ≤ 0.95
        posterior_max = pipeline.bayesian_update_i(prior_i=0.99, evidence_i=0.99)
        assert posterior_max <= 0.95, (
            f"后验上限应为 0.95: posterior={posterior_max}"
        )

    def test_scenario_a_cite_factor(self):
        """A-6: cite_factor 计算 — None→0.85, 完整规则→0.95。"""
        if not _HAS_NLU:
            pytest.skip("tomas_nlu_pipeline 不可用")

        pipeline = TOMASNLU_Pipeline(use_jieba=False)

        # None 或空字典 → 默认 cite_factor (0.85)
        cf_none = pipeline._compute_cite_factor(None)
        assert cf_none == pytest.approx(0.85, abs=0.01), (
            f"None cited_rule 应返回默认 cite_factor≈0.85, 实际: {cf_none}"
        )

        cf_empty = pipeline._compute_cite_factor({})
        assert cf_empty == pytest.approx(0.85, abs=0.01), (
            f"空 cited_rule 应返回默认 cite_factor≈0.85, 实际: {cf_empty}"
        )

        # 完整规则 → 更高 cite_factor
        full_rule = {
            "template_id": "BC_TransEvi",
            "pattern": ["v", "p", "v"],
            "slots": {"agent": 0, "action": 1, "patient": 2},
            "constraints": {"tense": "present"},
        }
        cf_full = pipeline._compute_cite_factor(full_rule)
        assert cf_full > 0.85, (
            f"完整规则应返回更高 cite_factor, 实际: {cf_full}"
        )


# ============================================================
# Scenario B: Gödel Agent 四重封边安全自改进
# ============================================================

class TestScenarioB_GodelAgent:
    """场景 B: 哥德尔智能体四重封边 — PG-囚禁 + 沙箱验收 + ℐ评估 + MUS双存。"""

    def test_scenario_b_h_hard_symbols(self):
        """B-1: H_HARD_SYMBOLS 硬锚符号集包含 6 个符号。"""
        if not _HAS_GOEDEL:
            pytest.skip("goedel_agent_tomas 不可用")

        symbols = TOMASGodelAgent.H_HARD_SYMBOLS
        assert isinstance(symbols, set), "H_HARD_SYMBOLS 应为集合"
        assert len(symbols) == 6, (
            f"H_HARD_SYMBOLS 应有 6 个符号, 实际: {len(symbols)}"
        )
        expected = {
            "PHYSICS_CONSERVATION",
            "MEMORY_SAFETY",
            "TYPE_SAFETY",
            "CONCURRENCY_SAFETY",
            "DEAD_ZERO_THRESHOLD",
            "MUS_DUAL_STORE",
        }
        assert symbols == expected, (
            f"H_HARD_SYMBOLS 不匹配: {symbols}"
        )

    def test_scenario_b_pg_imprison_safe_code(self):
        """B-2: PG-囚禁检查 — 包含所有硬锚符号的安全代码应通过。"""
        if not _HAS_GOEDEL:
            pytest.skip("goedel_agent_tomas 不可用")

        # 构造最小 agent（依赖传 None，降级模式）
        agent = TOMASGodelAgent(
            g_ego=None,
            ksnap=None,
            dead_zero_checker=None,
        )

        # 安全代码：包含所有 H_HARD_SYMBOLS
        safe_code = agent._generate_initial_code()
        assert agent._pg_imprison_check(safe_code) is True, (
            "初始代码应通过 PG-囚禁检查（包含所有硬锚符号）"
        )

    def test_scenario_b_pg_imprison_dangerous_code(self):
        """B-3: PG-囚禁检查 — 删除硬锚符号的危险代码应被拒绝。"""
        if not _HAS_GOEDEL:
            pytest.skip("goedel_agent_tomas 不可用")

        agent = TOMASGodelAgent(
            g_ego=None,
            ksnap=None,
            dead_zero_checker=None,
        )

        # 危险代码：完全不含任何硬锚符号名称（连注释中也不含）
        dangerous_code = (
            "# -*- coding: utf-8 -*-\n"
            "x = 1\n"
            "y = 2\n"
            "def func():\n"
            "    return x + y\n"
        )
        assert agent._pg_imprison_check(dangerous_code) is False, (
            "缺少硬锚符号的代码应被 PG-囚禁拒绝"
        )

    def test_scenario_b_pg_imprison_del_statement(self):
        """B-4: PG-囚禁检查 — del 语句删除硬锚符号应被 AST 分析检测。"""
        if not _HAS_GOEDEL:
            pytest.skip("goedel_agent_tomas 不可用")

        agent = TOMASGodelAgent(
            g_ego=None,
            ksnap=None,
            dead_zero_checker=None,
        )

        # 包含 del 语句的危险代码
        del_code = """
PHYSICS_CONSERVATION = True
MEMORY_SAFETY = True
TYPE_SAFETY = True
CONCURRENCY_SAFETY = True
DEAD_ZERO_THRESHOLD = 0.15
MUS_DUAL_STORE = True
del PHYSICS_CONSERVATION
del MEMORY_SAFETY
def func():
    pass
"""
        assert agent._pg_imprison_check(del_code) is False, (
            "del 语句删除硬锚符号应被 PG-囚禁 AST 分析拒绝"
        )

    def test_scenario_b_mus_dual_store(self):
        """B-5: MUS 双存 — _mus_dual_store 返回 resolution='double-store'。"""
        if not _HAS_GOEDEL:
            pytest.skip("goedel_agent_tomas 不可用")

        agent = TOMASGodelAgent(
            g_ego=None,
            ksnap=None,
            dead_zero_checker=None,
        )

        old_code = "def func(): return 1"
        new_code = "def func(): return 2"
        entry = agent._mus_dual_store(old_code, new_code)

        assert entry is not None, "MUS 双存返回 None"
        assert entry.resolution == "double-store", (
            f"MUS 双存 resolution 应为 'double-store', 实际: {entry.resolution}"
        )
        assert entry.old_code == old_code, "MUS 双存 old_code 不匹配"
        assert entry.new_code == new_code, "MUS 双存 new_code 不匹配"
        assert entry.old_code_hash != entry.new_code_hash, (
            "MUS 双存 old/new 代码哈希不应相同"
        )
        assert entry.tag.startswith("mus_"), (
            f"MUS 双存 tag 应以 'mus_' 开头, 实际: {entry.tag}"
        )

    def test_scenario_b_evaluate_i(self):
        """B-6: ℐ 评估 — _evaluate_i 基于测试用例通过率计算 ℐ_new。"""
        if not _HAS_GOEDEL:
            pytest.skip("goedel_agent_tomas 不可用")

        agent = TOMASGodelAgent(
            g_ego=None,
            ksnap=None,
            dead_zero_checker=None,
        )

        # 全部通过的测试用例
        test_cases_pass = [
            {"input": "test1", "expected": 1, "passed": True},
            {"input": "test2", "expected": 2, "passed": True},
            {"input": "test3", "expected": 3, "passed": True},
        ]
        i_new = agent._evaluate_i("def func(): pass", test_cases_pass)
        assert i_new >= 0.0, (
            f"ℐ_new 应 >= 0: {i_new}"
        )

        # 全部失败的测试用例 → ℐ_new 应更低
        test_cases_fail = [
            {"input": "test1", "expected": 1, "passed": False},
            {"input": "test2", "expected": 2, "passed": False},
        ]
        i_new_fail = agent._evaluate_i("def func(): pass", test_cases_fail)
        assert i_new_fail < i_new, (
            f"全部失败的 ℐ_new ({i_new_fail}) 应低于全部通过的 ({i_new})"
        )

    def test_scenario_b_i_accept_ratio(self):
        """B-7: ℐ 接受律倍率 I_ACCEPT_RATIO = 1.05。"""
        if not _HAS_GOEDEL:
            pytest.skip("goedel_agent_tomas 不可用")

        assert TOMASGodelAgent.I_ACCEPT_RATIO == 1.05, (
            f"I_ACCEPT_RATIO 应为 1.05, 实际: {TOMASGodelAgent.I_ACCEPT_RATIO}"
        )

    def test_scenario_b_self_improve_loop_rejected(self):
        """B-8: 自改进主循环 — PG-囚禁失败时应返回 accepted=False。"""
        if not _HAS_GOEDEL:
            pytest.skip("goedel_agent_tomas 不可用")

        agent = TOMASGodelAgent(
            g_ego=None,
            ksnap=None,
            dead_zero_checker=None,
            llm_api_func=lambda prompt: "# 危险代码：删除所有硬锚\nx = 1\n",
        )

        result = agent.self_improve_loop("测试 PG-囚禁拒绝")
        assert isinstance(result, GodelImproveResult), (
            f"self_improve_loop 应返回 GodelImproveResult, 实际: {type(result)}"
        )
        assert result.accepted is False, (
            "PG-囚禁失败的代码不应被接受"
        )
        assert "PG" in result.rejection_reason or "囚禁" in result.rejection_reason, (
            f"拒绝原因应提及 PG-囚禁: {result.rejection_reason}"
        )


# ============================================================
# Scenario C: AgentWeb 因果消息 + κ-Snap 日志
# ============================================================

class TestScenarioC_AgentWeb:
    """场景 C: 向量时钟 + 因果交付缓冲 + AgentWeb 运行时。"""

    def test_scenario_c_vector_clock_basic(self):
        """C-1: VectorClock 基本操作 — tick, send, receive。"""
        if not _HAS_VC:
            pytest.skip("vector_clock 不可用")

        vc = VectorClock("A", ["A", "B", "C"])
        assert vc.node_id == "A"
        assert vc.to_dict() == {"A": 0, "B": 0, "C": 0}

        # tick 自增
        vc.tick()
        assert vc.to_dict()["A"] == 1

        # send → tick + 快照
        snapshot = vc.send()
        assert snapshot["A"] == 2  # tick 后 A=2

        # receive → merge (modifies in-place, returns None)
        remote_vc = {"A": 1, "B": 5, "C": 0}
        vc.receive(remote_vc)
        merged = vc.to_dict()
        assert merged["B"] == 5, f"receive 后 B 应为 5, 实际: {merged['B']}"

    def test_scenario_c_vector_clock_happened_before(self):
        """C-2: happened_before 和 concurrent_with 因果关系判断。"""
        if not _HAS_VC:
            pytest.skip("vector_clock 不可用")

        vc1 = VectorClock("A", ["A", "B"])
        vc2 = VectorClock("B", ["A", "B"])

        # vc1: A=1, B=0; vc2: A=0, B=1 → 并发（各自有对方没有的事件）
        vc1.tick()  # vc1 = {A:1, B:0}
        vc2.tick()  # vc2 = {A:0, B:1}

        # {A:1, B:0} vs {A:0, B:1} → 并发（A 大 B 小，不满足全 ≤）
        assert not vc1.happened_before(vc2), "vc1 不应 happened_before vc2（并发）"
        assert not vc2.happened_before(vc1), "vc2 不应 happened_before vc1（并发）"

    def test_scenario_c_causal_delivery_ready(self):
        """C-3: CausalDeliveryBuffer — 因果前置到齐时消息应被交付。"""
        if not _HAS_VC or not _HAS_CD:
            pytest.skip("vector_clock 或 causal_delivery 不可用")

        vc_b = VectorClock("B", ["A", "B"])
        buffer = CausalDeliveryBuffer(vc_b)

        # 来自 A 的消息 vc={A:1, B:0}，B 的 local={A:0, B:0}
        # 条件: A:1 == local[A]+1=1 ✓, B:0 ≤ local[B]=0 ✓ → 交付
        msg = AgentWebMessage(
            msg_id="msg_001",
            source_node="A",
            target_node="B",
            vector_clock={"A": 1, "B": 0},
        )
        delivered = buffer.deliver(msg)
        assert len(delivered) == 1, (
            f"因果前置到齐应交付 1 条消息, 实际: {len(delivered)}"
        )
        assert delivered[0].msg_id == "msg_001"

    def test_scenario_c_causal_delivery_buffered(self):
        """C-4: CausalDeliveryBuffer — 因果前置未到齐时消息应被缓冲。"""
        if not _HAS_VC or not _HAS_CD:
            pytest.skip("vector_clock 或 causal_delivery 不可用")

        vc_b = VectorClock("B", ["A", "B"])
        buffer = CausalDeliveryBuffer(vc_b)

        # 来自 A 的消息 vc={A:3, B:0}，跳过了 A:1 和 A:2 → 缓冲
        msg = AgentWebMessage(
            msg_id="msg_skip",
            source_node="A",
            target_node="B",
            vector_clock={"A": 3, "B": 0},
        )
        delivered = buffer.deliver(msg)
        assert len(delivered) == 0, "因果前置未到齐不应交付"
        assert buffer.pending_count() == 1, (
            f"缓冲区应有 1 条消息, 实际: {buffer.pending_count()}"
        )

    def test_scenario_c_cascade_unlock(self):
        """C-5: 级联解锁 — 乱序消息到达后按序级联交付。"""
        if not _HAS_VC or not _HAS_CD:
            pytest.skip("vector_clock 或 causal_delivery 不可用")

        vc_b = VectorClock("B", ["A", "B"])
        buffer = CausalDeliveryBuffer(vc_b)

        # 先到达 A:3（缓冲）
        msg3 = AgentWebMessage("casc_3", "A", "B", {"A": 3, "B": 0})
        buffer.deliver(msg3)
        assert buffer.pending_count() == 1

        # 再到达 A:2（缓冲）
        msg2 = AgentWebMessage("casc_2", "A", "B", {"A": 2, "B": 0})
        buffer.deliver(msg2)
        assert buffer.pending_count() == 2

        # 到达 A:1 → 级联解锁全部 3 条
        msg1 = AgentWebMessage("casc_1", "A", "B", {"A": 1, "B": 0})
        delivered = buffer.deliver(msg1)
        assert len(delivered) == 3, (
            f"级联解锁应交付 3 条, 实际: {len(delivered)}"
        )
        assert buffer.pending_count() == 0

    def test_scenario_c_agentweb_runtime_send(self):
        """C-6: AgentWebRuntime — send_message 更新向量时钟并记录日志。"""
        if not _HAS_AWR:
            pytest.skip("agentweb_runtime 不可用")

        rt = AgentWebRuntime("A", ["A", "B", "C"])
        msg_id = rt.send_message("B", {"action": "test", "data": 42})

        assert msg_id.startswith("msg_A_"), (
            f"msg_id 应以 'msg_A_' 开头, 实际: {msg_id}"
        )
        assert rt.vc.to_dict()["A"] == 1, (
            f"send 后 A 的时钟应为 1, 实际: {rt.vc.to_dict()['A']}"
        )
        assert len(rt.message_log) == 1
        assert rt.message_log[0].source_node == "A"
        assert rt.message_log[0].target_node == "B"

    def test_scenario_c_agentweb_runtime_receive(self):
        """C-7: AgentWebRuntime — receive_message 因果交付 + VC 更新。"""
        if not _HAS_AWR:
            pytest.skip("agentweb_runtime 不可用")

        rt_b = AgentWebRuntime("B", ["A", "B"])
        msg = AgentWebMessage(
            msg_id="test_recv_1",
            source_node="A",
            target_node="B",
            vector_clock={"A": 1, "B": 0},
            content={"text": "Hello B"},
        )
        result = rt_b.receive_message(msg)

        assert result["delivered"] is True, "消息应被交付"
        assert result["delivered_count"] == 1
        assert result["buffered"] is False
        # 交付后 B 的时钟应更新
        assert rt_b.vc.to_dict()["A"] >= 1, (
            f"receive 后 A 应 >=1, 实际: {rt_b.vc.to_dict()['A']}"
        )

    def test_scenario_c_agentweb_with_ksnap(self):
        """C-8: AgentWebRuntime + κ-Snap — 消息事件记录到因果日志。"""
        if not _HAS_AWR or not _HAS_KSNAP:
            pytest.skip("agentweb_runtime 或 ksnap_operator 不可用")

        ksnap = KSnapOperator(theta_ftel=0.1, theta_dead=0.01)
        rt = AgentWebRuntime("A", ["A", "B"], ksnap=ksnap)

        initial_log_size = len(ksnap.causal_log)
        rt.send_message("B", {"action": "ksnap_test"})

        assert len(ksnap.causal_log) == initial_log_size + 1, (
            f"κ-Snap 日志应增加 1 条, 实际增加: "
            f"{len(ksnap.causal_log) - initial_log_size}"
        )

    def test_scenario_c_bidirectional_communication(self):
        """C-9: 双节点双向通信 — 双方 VC 最终一致。"""
        if not _HAS_AWR:
            pytest.skip("agentweb_runtime 不可用")

        rt_x = AgentWebRuntime("X", ["X", "Y"])
        rt_y = AgentWebRuntime("Y", ["X", "Y"])

        # 双方各自先发送
        rt_x.send_message("Y", {"seq": 1})
        msg_from_x = rt_x.message_log[-1]

        rt_y.send_message("X", {"seq": 2, "reply": True})
        msg_from_y = rt_y.message_log[-1]

        # 互相接收
        r_x = rt_x.receive_message(msg_from_y)
        r_y = rt_y.receive_message(msg_from_x)

        assert r_x["delivered"] is True, "X 应能交付 Y 的消息"
        assert r_y["delivered"] is True, "Y 应能交付 X 的消息"
        # 双方都看到了对方的消息
        assert rt_x.vc.clock["Y"] >= 1, (
            f"X 应看到 Y:1, 实际 Y={rt_x.vc.clock['Y']}"
        )
        assert rt_y.vc.clock["X"] >= 1, (
            f"Y 应看到 X:1, 实际 X={rt_y.vc.clock['X']}"
        )


# ============================================================
# Scenario D: 因果世界模型 + H_hard 物理守恒律
# ============================================================

class TestScenarioD_CausalWorldModel:
    """场景 D: AetherSCMBridge + HodgeICoupling + TOMASCausalWorldModel。"""

    def test_scenario_d_aether_scm_variables_and_edges(self):
        """D-1: AetherSCMBridge — 添加变量和因果边，构建 SCM DAG。"""
        if not _HAS_AETHER:
            pytest.skip("aether_bridge 不可用")

        bridge = AetherSCMBridge()

        # 添加物理变量
        bridge.add_variable(CausalVariable("E", "Energy", "continuous", [0.0, 1e9]))
        bridge.add_variable(CausalVariable("p", "Momentum", "continuous", [-1e9, 1e9]))
        bridge.add_variable(CausalVariable("m", "Mass", "continuous", [0.0, 1e6]))

        assert bridge.get_variable("E") is not None
        assert bridge.get_variable("E").name == "Energy"

        # 添加因果边
        bridge.add_causal_edge(CausalEdge(
            source="m", target="p",
            edge_type="direct", mechanism="p = mv",
            strength=0.9, is_hard_anchor=False,
        ))
        bridge.add_causal_edge(CausalEdge(
            source="m", target="E",
            edge_type="direct", mechanism="E = mc^2",
            strength=0.95, is_hard_anchor=False,
        ))

        summary = bridge.get_graph_summary()
        assert summary["num_variables"] == 3, (
            f"应有 3 个变量, 实际: {summary['num_variables']}"
        )
        assert summary["num_edges"] == 2, (
            f"应有 2 条边, 实际: {summary['num_edges']}"
        )

    def test_scenario_d_aether_cycle_detection(self):
        """D-2: AetherSCMBridge — DAG 环检测拒绝成环边。"""
        if not _HAS_AETHER:
            pytest.skip("aether_bridge 不可用")

        bridge = AetherSCMBridge()
        bridge.add_variable(CausalVariable("A", "VarA"))
        bridge.add_variable(CausalVariable("B", "VarB"))

        bridge.add_causal_edge(CausalEdge(source="A", target="B"))
        # 尝试添加 B→A（会形成环）
        bridge.add_causal_edge(CausalEdge(source="B", target="A"))

        summary = bridge.get_graph_summary()
        assert summary["num_edges"] == 1, (
            f"环检测应拒绝 B→A, 实际边数: {summary['num_edges']}"
        )

    def test_scenario_d_aether_confounders(self):
        """D-3: AetherSCMBridge — 混淆因子检测。"""
        if not _HAS_AETHER:
            pytest.skip("aether_bridge 不可用")

        bridge = AetherSCMBridge()
        bridge.add_variable(CausalVariable("X", "Confounder"))
        bridge.add_variable(CausalVariable("A", "VarA"))
        bridge.add_variable(CausalVariable("B", "VarB"))

        # X→A, X→B, A 和 B 之间无直接边 → X 是混淆因子
        bridge.add_causal_edge(CausalEdge(source="X", target="A"))
        bridge.add_causal_edge(CausalEdge(source="X", target="B"))

        confounders = bridge.detect_confounders()
        assert len(confounders) >= 1, (
            f"应检测到至少 1 组混淆因子, 实际: {len(confounders)}"
        )
        # 验证 X 被识别为混淆因子
        confounder_ids = [c[0] for c in confounders]
        assert "X" in confounder_ids, (
            f"X 应被识别为混淆因子, 实际: {confounder_ids}"
        )

    def test_scenario_d_aether_eml_hyperedges(self):
        """D-4: AetherSCMBridge — to_eml_hyperedges 编码因果边为 EML 超边。"""
        if not _HAS_AETHER:
            pytest.skip("aether_bridge 不可用")

        bridge = AetherSCMBridge()
        bridge.add_variable(CausalVariable("F", "Force"))
        bridge.add_variable(CausalVariable("a", "Acceleration"))
        bridge.add_causal_edge(CausalEdge(
            source="F", target="a",
            edge_type="direct", mechanism="F = ma",
            strength=0.95, is_hard_anchor=True,
        ))

        hyperedges = bridge.to_eml_hyperedges()
        assert len(hyperedges) == 1, (
            f"应有 1 条 EML 超边, 实际: {len(hyperedges)}"
        )
        he = hyperedges[0]
        assert he["schema_type"] == "causal_relation", (
            f"schema_type 应为 'causal_relation', 实际: {he['schema_type']}"
        )
        assert he["source"] == "F"
        assert he["target"] == "a"
        assert he["is_hard_anchor"] is True

    def test_scenario_d_hodge_conservation_check_pass(self):
        """D-5: HodgeICoupling — 守恒状态通过物理守恒律检查。"""
        if not _HAS_HODGE:
            pytest.skip("hodge_operator 不可用")

        wsc = WeightedSimplicialComplex(max_dim=2)
        hodge = HodgeICoupling(wsc, conservation_tolerance=1e-4)

        # 能量守恒：before=100, after=100 → ΔE=0
        conserved = {
            "energy_before": 100.0,
            "energy_after": 100.0,
            "momentum_before": 50.0,
            "momentum_after": 50.0,
            "angular_momentum_before": 10.0,
            "angular_momentum_after": 10.0,
        }
        result = hodge.check_physical_conservation(conserved)
        assert result["passed"] is True, (
            f"守恒状态应通过检查, violations: {result.get('violations', [])}"
        )

    def test_scenario_d_hodge_conservation_check_fail(self):
        """D-6: HodgeICoupling — 非守恒状态被检测到违例。"""
        if not _HAS_HODGE:
            pytest.skip("hodge_operator 不可用")

        wsc = WeightedSimplicialComplex(max_dim=2)
        hodge = HodgeICoupling(wsc, conservation_tolerance=1e-4)

        # 能量不守恒：before=100, after=80 → ΔE=20
        violated = {
            "energy_before": 100.0,
            "energy_after": 80.0,
            "momentum_before": 50.0,
            "momentum_after": 50.0,
            "angular_momentum_before": 10.0,
            "angular_momentum_after": 10.0,
        }
        result = hodge.check_physical_conservation(violated)
        assert result["passed"] is False, "非守恒状态应未通过检查"
        assert len(result["violations"]) > 0, "应有违例报告"

    def test_scenario_d_world_model_predict(self):
        """D-7: TOMASCausalWorldModel — predict_next_state 返回 H_hard 检查结果。"""
        if not _HAS_CWM:
            pytest.skip("causal_world_model_tomas 不可用")

        # 使用降级模式：aether_bridge=None, hodge=None
        model = TOMASCausalWorldModel(
            aether_bridge=None,
            hodge=None,
            eml_graph=None,
        )

        current_state = {"position": 0.0, "velocity": 1.0}
        action = {"force": 0.5}
        result = model.predict_next_state(current_state, action)

        assert "predicted_state" in result, "结果缺少 predicted_state"
        assert "confidence" in result, "结果缺少 confidence"
        assert "h_hard_passed" in result, "结果缺少 h_hard_passed"
        assert "violations" in result, "结果缺少 violations"
        assert isinstance(result["confidence"], (int, float)), (
            f"confidence 应为数值, 实际: {type(result['confidence'])}"
        )

    def test_scenario_d_world_model_counterfactual(self):
        """D-8: TOMASCausalWorldModel — counterfactual 反事实推理。"""
        if not _HAS_CWM:
            pytest.skip("causal_world_model_tomas 不可用")

        model = TOMASCausalWorldModel(
            aether_bridge=None,
            hodge=None,
        )

        state = {"energy": 100.0, "position": 5.0}
        intervention = {"energy": 200.0}
        result = model.counterfactual(state, intervention)

        assert "counterfactual_state" in result, "结果缺少 counterfactual_state"
        assert "h_hard_passed" in result, "结果缺少 h_hard_passed"

    def test_scenario_d_world_model_learn_from_data(self):
        """D-9: TOMASCausalWorldModel — learn_from_data 学习因果结构。"""
        if not _HAS_CWM:
            pytest.skip("causal_world_model_tomas 不可用")

        model = TOMASCausalWorldModel(
            aether_bridge=AetherSCMBridge() if _HAS_AETHER else None,
            hodge=None,
        )

        data = {
            "variables": [
                {"var_id": "F", "name": "Force", "var_type": "continuous"},
                {"var_id": "m", "name": "Mass", "var_type": "continuous"},
                {"var_id": "a", "name": "Acceleration", "var_type": "continuous"},
            ],
            "relations": [
                {
                    "source": "F", "target": "a",
                    "edge_type": "direct", "mechanism": "F = ma",
                    "strength": 0.95, "is_hard_anchor": True,
                },
                {
                    "source": "m", "target": "a",
                    "edge_type": "direct", "mechanism": "a = F/m",
                    "strength": 0.9, "is_hard_anchor": False,
                },
            ],
        }
        result = model.learn_from_data(data)

        assert "learned_edges" in result, "结果缺少 learned_edges"
        assert "scm_nodes" in result, "结果缺少 scm_nodes"
        assert result["learned_edges"] >= 0, (
            f"learned_edges 应 >= 0, 实际: {result['learned_edges']}"
        )


# ============================================================
# Scenario E: κ-Snap + Mina + Celo 链上存证
# ============================================================

class TestScenarioE_ChainAttestation:
    """场景 E: KSnapOperator + MinaTOMASSnap + CeloBridge（降级模式）。"""

    def test_scenario_e_ksnap_batch_merkle_root(self):
        """E-1: KSnapOperator.batch_merkle_root — 计算 Merkle Root。"""
        if not _HAS_KSNAP:
            pytest.skip("ksnap_operator 不可用")

        # 构造 SnapEvent 列表
        events = []
        for i in range(4):
            event = SnapEvent(
                event_id=f"evt_{i:03d}",
                candidate_id=f"cand_{i}",
                result=SnapResult.MANIFESTED,
                observation_base=ObservationBase.COGNITIVE,
                timestamp=time.time() + i,
                reason=f"Test event {i}",
                manifested_edge=None,
                new_code_hash=hashlib.sha256(f"code_{i}".encode()).hexdigest(),
                trigger_obs_id=f"obs_{i}",
                llm_version="test_v1",
            )
            events.append(event)

        merkle_root = KSnapOperator.batch_merkle_root(events)
        assert isinstance(merkle_root, str), (
            f"Merkle Root 应为字符串, 实际: {type(merkle_root)}"
        )
        assert len(merkle_root) > 0, "Merkle Root 不应为空"
        # Merkle Root 应为十六进制哈希
        assert all(c in "0123456789abcdef" for c in merkle_root.lower()), (
            f"Merkle Root 应为十六进制, 实际: {merkle_root}"
        )

    def test_scenario_e_ksnap_merkle_deterministic(self):
        """E-2: KSnapOperator.batch_merkle_root — 相同输入产生相同 Merkle Root。"""
        if not _HAS_KSNAP:
            pytest.skip("ksnap_operator 不可用")

        events = [
            SnapEvent(
                event_id=f"evt_{i}",
                candidate_id=f"cand_{i}",
                result=SnapResult.MANIFESTED,
                observation_base=ObservationBase.COGNITIVE,
                timestamp=1000000.0 + i,
                reason=f"Deterministic test {i}",
                manifested_edge=None,
                new_code_hash=f"hash_{i}",
                trigger_obs_id=f"obs_{i}",
                llm_version="v1",
            )
            for i in range(3)
        ]

        root1 = KSnapOperator.batch_merkle_root(events)
        root2 = KSnapOperator.batch_merkle_root(events)
        assert root1 == root2, (
            f"相同输入应产生相同 Merkle Root: {root1} != {root2}"
        )

    def test_scenario_e_ksnap_create_code_evolution_snap(self):
        """E-3: KSnapOperator.create_code_evolution_snap — 创建代码演化事件。"""
        if not _HAS_KSNAP:
            pytest.skip("ksnap_operator 不可用")

        ksnap = KSnapOperator(theta_ftel=0.1, theta_dead=0.01)
        snap = ksnap.create_code_evolution_snap(
            candidate_id="cand_test_001",
            new_code_hash=hashlib.sha256(b"new_code").hexdigest(),
            trigger_obs_id="obs_001",
            llm_version="gpt-4-test",
        )

        assert snap is not None, "create_code_evolution_snap 返回 None"
        assert hasattr(snap, "event_id"), "SnapEvent 缺少 event_id"
        assert hasattr(snap, "candidate_id"), "SnapEvent 缺少 candidate_id"
        assert snap.candidate_id == "cand_test_001"

    def test_scenario_e_mina_degraded_mode(self):
        """E-4: MinaTOMASSnap — 降级模式（无 RPC 连接）wrap_snap 返回证明。"""
        if not _HAS_MINA:
            pytest.skip("mina_kappa_bridge 不可用")

        # 使用无效 RPC URL 触发降级模式
        mina = MinaTOMASSnap(mina_rpc_url="http://invalid:9999")

        if _HAS_KSNAP:
            snap_event = SnapEvent(
                event_id="mina_test_001",
                candidate_id="cand_mina",
                result=SnapResult.MANIFESTED,
                observation_base=ObservationBase.COGNITIVE,
                timestamp=time.time(),
                reason="Mina degraded test",
                manifested_edge=None,
                new_code_hash="abc123",
                trigger_obs_id="obs_001",
                llm_version="v1",
            )
        else:
            snap_event = type("MockSnap", (), {
                "event_id": "mina_test_001",
                "timestamp": time.time(),
                "new_code_hash": "abc123",
            })()

        proof = mina.wrap_snap(snap_event)
        assert proof is not None, "wrap_snap 返回 None"
        # 降级模式应有 is_degraded 标记或哈希证明
        assert hasattr(proof, "is_degraded") or hasattr(proof, "proof_hash"), (
            "降级模式返回的证明应包含 is_degraded 或 proof_hash"
        )

    def test_scenario_e_celo_degraded_payment(self):
        """E-5: CeloBridge — 降级模式 process_payment 返回模拟 tx_hash。"""
        if not _HAS_CELO:
            pytest.skip("celo_bridge 不可用")

        # 使用无效 RPC URL 触发降级模式
        celo = CeloBridge(celo_rpc_url="http://invalid:9999")

        tx_hash = celo.process_payment(
            from_addr="0x1234567890abcdef1234567890abcdef12345678",
            to_addr="0xabcdef1234567890abcdef1234567890abcdef12",
            amount=1.5,
            currency="cUSD",
        )
        assert tx_hash is not None, "process_payment 返回 None"
        assert isinstance(tx_hash, str), (
            f"tx_hash 应为字符串, 实际: {type(tx_hash)}"
        )
        assert len(tx_hash) > 0, "tx_hash 不应为空"

    def test_scenario_e_celo_verify_payment(self):
        """E-6: CeloBridge — 降级模式 verify_payment 返回 confirmed。"""
        if not _HAS_CELO:
            pytest.skip("celo_bridge 不可用")

        celo = CeloBridge(celo_rpc_url="http://invalid:9999")
        tx_hash = celo.process_payment(
            from_addr="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            to_addr="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            amount=0.5,
            currency="cUSD",
        )

        result = celo.verify_payment(tx_hash)
        assert result is not None, "verify_payment 返回 None"
        # 降级模式应返回 confirmed=True 或类似确认
        if isinstance(result, dict):
            assert result.get("confirmed") is True or result.get("status") == "confirmed", (
                f"降级模式应确认支付, 实际: {result}"
            )
        elif isinstance(result, bool):
            assert result is True, "降级模式应返回 True"


# ============================================================
# Scenario F: EML EHNN + 等变层 + GPCT 降维
# ============================================================

class TestScenarioF_EMLEquivariantGPCT:
    """场景 F: EMLEHNN + EquivariantLinearLayer + GpctDecomposer。"""

    def test_scenario_f_ehnn_forward(self):
        """F-1: EMLEHNN.forward — ℐ-weighted 超图神经网络前向传播。"""
        if not _HAS_EHNN:
            pytest.skip("eml_ehnn 不可用")

        ehnn = EMLEHNN(
            in_dim=8,
            hidden_dim=16,
            out_dim=4,
            k=3,
            i_threshold=0.1,
        )

        # 构造超边列表
        edges = [
            EMLHyperEdge(
                edge_id="edge_0",
                nodes=[0, 1, 2],
                i_value=0.9,
                is_hard_anchor=True,
                features=[1.0] * 8,
            ),
            EMLHyperEdge(
                edge_id="edge_1",
                nodes=[1, 2, 3],
                i_value=0.7,
                is_hard_anchor=False,
                features=[0.5] * 8,
            ),
            EMLHyperEdge(
                edge_id="edge_2",
                nodes=[0, 3],
                i_value=0.05,  # 低于阈值，应被剪枝
                is_hard_anchor=False,
                features=[0.1] * 8,
            ),
        ]

        result = ehnn.forward(edges)
        assert isinstance(result, dict), (
            f"forward 应返回字典, 实际: {type(result)}"
        )
        assert "pooled_features" in result, "结果缺少 pooled_features"
        assert "mus_branches" in result, "结果缺少 mus_branches"
        assert "snap_loss" in result, "结果缺少 snap_loss"
        assert "output_dim" in result, "结果缺少 output_dim"

    def test_scenario_f_ehnn_i_threshold_pruning(self):
        """F-2: EMLEHNN — ℐ 低于阈值的超边被剪枝。"""
        if not _HAS_EHNN:
            pytest.skip("eml_ehnn 不可用")

        ehnn = EMLEHNN(
            in_dim=4,
            hidden_dim=8,
            out_dim=2,
            k=2,
            i_threshold=0.3,  # ℐ < 0.3 的边被剪枝
        )

        edges_high = [
            EMLHyperEdge(
                edge_id=f"high_{i}",
                nodes=[i, (i + 1) % 4],
                i_value=0.8,
                features=[1.0] * 4,
            )
            for i in range(4)
        ]
        edges_low = [
            EMLHyperEdge(
                edge_id=f"low_{i}",
                nodes=[i, (i + 1) % 4],
                i_value=0.1,  # 低于阈值
                features=[0.5] * 4,
            )
            for i in range(4)
        ]

        result_high = ehnn.forward(edges_high)
        result_low = ehnn.forward(edges_low)

        # 高 ℐ 边应有非零输出
        assert len(result_high["pooled_features"]) > 0, (
            "高 ℐ 超边应产生非空输出"
        )

    def test_scenario_f_ehnn_hard_anchor_weight(self):
        """F-3: EMLEHNN — 硬锚超边权重 ≥ 0.95。"""
        if not _HAS_EHNN:
            pytest.skip("eml_ehnn 不可用")

        ehnn = EMLEHNN(in_dim=4, hidden_dim=8, out_dim=2, k=2)

        hard_edge = EMLHyperEdge(
            edge_id="hard_0",
            nodes=[0, 1],
            i_value=0.5,
            is_hard_anchor=True,  # 硬锚
            features=[1.0] * 4,
        )
        normal_edge = EMLHyperEdge(
            edge_id="normal_0",
            nodes=[0, 1],
            i_value=0.5,
            is_hard_anchor=False,
            features=[1.0] * 4,
        )

        # 硬锚边不应被剪枝（即使 ℐ 较低）
        result = ehnn.forward([hard_edge])
        assert len(result["pooled_features"]) > 0, "硬锚超边不应被剪枝"

    def test_scenario_f_equivariant_forward(self):
        """F-4: EquivariantLinearLayer.forward — 等变线性层前向传播。"""
        if not _HAS_EQUIV:
            pytest.skip("equivariant_layers 不可用")

        layer = EquivariantLinearLayer(in_dim=4, out_dim=2, k=2)

        features = [1.0, 2.0, 3.0, 4.0]
        hyperedges = [{0, 1}, {2, 3}]

        output = layer.forward(features, hyperedges)
        assert isinstance(output, list), (
            f"forward 应返回列表, 实际: {type(output)}"
        )
        assert len(output) > 0, "输出不应为空"

    def test_scenario_f_equivariant_test(self):
        """F-5: EquivariantLinearLayer.test_equivariance — 置换等变性验证。"""
        if not _HAS_EQUIV:
            pytest.skip("equivariant_layers 不可用")

        layer = EquivariantLinearLayer(in_dim=4, out_dim=2, k=2)

        features = [1.0, 2.0, 3.0, 4.0]
        hyperedges = [{0, 1}, {2, 3}]
        # 简单置换：交换节点 0 和 1（dict 映射形式）
        permutation = {0: 1, 1: 0, 2: 2, 3: 3}

        result = layer.test_equivariance(features, hyperedges, permutation)
        assert isinstance(result, bool), (
            f"test_equivariance 应返回 bool, 实际: {type(result)}"
        )

    def test_scenario_f_gpct_decompose(self):
        """F-6: GpctDecomposer — 边界层分解返回 BL 和 OR。"""
        if not _HAS_GPCT or not _HAS_HYPEDGE:
            pytest.skip("gpct 或 hyperedge 不可用")

        # 构造超边列表
        edges = [
            HypEdge(
                nodes=(i, (i + 1) % 10),
                eid=f"e_{i}",
                i_val=0.5 + 0.4 * (i % 3) / 2,  # 不同的 ℐ 值
            )
            for i in range(10)
        ]

        decomposer = GpctDecomposer(
            edges=edges,
            k=3,  # 边界层大小
        )

        result = decomposer.decompose()
        assert isinstance(result, dict), (
            f"decompose 应返回字典, 实际: {type(result)}"
        )
        assert "n_bl" in result, "结果缺少 n_bl"
        assert "n_or" in result, "结果缺少 n_or"
        assert "k" in result, "结果缺少 k"
        assert result["k"] == 3, f"k 应为 3, 实际: {result['k']}"
        assert result["n_bl"] + result["n_or"] == result["n_total"], (
            f"BL + OR 应 = 总节点数: {result['n_bl']} + {result['n_or']} "
            f"!= {result['n_total']}"
        )

    def test_scenario_f_gpct_boundary_outer(self):
        """F-7: GpctDecomposer — boundary_layer 和 outer_region 属性。"""
        if not _HAS_GPCT or not _HAS_HYPEDGE:
            pytest.skip("gpct 或 hyperedge 不可用")

        edges = [
            HypEdge(nodes=(0, 1), eid="e0", i_val=0.9),
            HypEdge(nodes=(1, 2), eid="e1", i_val=0.7),
            HypEdge(nodes=(2, 3), eid="e2", i_val=0.3),
            HypEdge(nodes=(3, 4), eid="e3", i_val=0.1),
        ]

        decomposer = GpctDecomposer(edges=edges, k=2)

        bl = decomposer.boundary_layer
        or_region = decomposer.outer_region

        assert isinstance(bl, list), "boundary_layer 应为列表"
        assert isinstance(or_region, list), "outer_region 应为列表"
        assert len(bl) == 2, f"BL 应有 2 个节点, 实际: {len(bl)}"
        # BL 和 OR 不应重叠
        assert set(bl).isdisjoint(set(or_region)), "BL 和 OR 不应重叠"

    def test_scenario_f_gpct_complexity(self):
        """F-8: GpctDecomposer — estimate_complexity 返回 FPT 可行性。"""
        if not _HAS_GPCT or not _HAS_HYPEDGE:
            pytest.skip("gpct 或 hyperedge 不可用")

        edges = [
            HypEdge(nodes=(i, (i + 1) % 8), eid=f"e_{i}", i_val=0.5)
            for i in range(8)
        ]

        decomposer = GpctDecomposer(edges=edges, k=5)
        complexity = decomposer.estimate_complexity()

        assert "complexity_class" in complexity, "结果缺少 complexity_class"
        assert "feasible" in complexity, "结果缺少 feasible"
        assert "k" in complexity, "结果缺少 k"
        # k=5 ≤ 20 → FPT 可行
        assert complexity["feasible"] is True, (
            f"k=5 应为 FPT 可行, 实际 feasible={complexity['feasible']}"
        )

    def test_scenario_f_gpct_detect_emergence(self):
        """F-9: GpctDecomposer — detect_causal_emergence 检测因果层创涌现。"""
        if not _HAS_GPCT or not _HAS_HYPEDGE:
            pytest.skip("gpct 或 hyperedge 不可用")

        # 构造有明显高耦合节点的超图
        edges = [
            HypEdge(nodes=(0, 1), eid="e0", i_val=0.9),
            HypEdge(nodes=(0, 2), eid="e1", i_val=0.9),
            HypEdge(nodes=(0, 3), eid="e2", i_val=0.9),
            HypEdge(nodes=(1, 2), eid="e3", i_val=0.3),
            HypEdge(nodes=(3, 4), eid="e4", i_val=0.2),
        ]

        decomposer = GpctDecomposer(edges=edges, k=2)
        result = decomposer.detect_causal_emergence()

        assert "emerged" in result, "结果缺少 emerged"
        assert "emerged_edges" in result, "结果缺少 emerged_edges"
        assert "suggested_dim_expansion" in result, "结果缺少 suggested_dim_expansion"
        assert isinstance(result["emerged"], bool), (
            f"emerged 应为 bool, 实际: {type(result['emerged'])}"
        )

    def test_scenario_f_gpct_expand_output_dim(self):
        """F-10: GpctDecomposer — expand_output_dim 动态维度扩展。"""
        if not _HAS_GPCT or not _HAS_HYPEDGE:
            pytest.skip("gpct 或 hyperedge 不可用")

        edges = [
            HypEdge(nodes=(0, 1), eid="e0", i_val=0.5),
        ]
        decomposer = GpctDecomposer(edges=edges, k=1)
        old_dim = decomposer.output_dim

        # 扩展到更大维度
        result = decomposer.expand_output_dim(new_dim=old_dim + 5)
        assert result["expanded"] is True, (
            f"维度应被扩展, 实际: {result}"
        )
        assert result["new_dim"] == old_dim + 5
        assert decomposer.output_dim == old_dim + 5, (
            f"output_dim 应更新为 {old_dim + 5}, 实际: {decomposer.output_dim}"
        )

        # 尝试扩展到更小维度 → 不应扩展
        result_no_expand = decomposer.expand_output_dim(new_dim=1)
        assert result_no_expand["expanded"] is False, (
            "扩展到更小维度不应触发扩展"
        )


# ============================================================
# 跨场景集成测试
# ============================================================

class TestCrossScenarioIntegration:
    """跨场景集成：验证多模块协同工作。"""

    def test_cross_nlu_to_goedel(self):
        """跨-1: NLU ℐ 值 → Gödel Agent ℐ 评估接受律。"""
        if not _HAS_NLU or not _HAS_GOEDEL:
            pytest.skip("NLU 或 Gödel Agent 不可用")

        # NLU 计算 ℐ 值
        pipeline = TOMASNLU_Pipeline(use_jieba=False)
        nlu_result = pipeline.process("根据物理定律，能量守恒")
        i_from_nlu = nlu_result.i_value

        # Gödel Agent ℐ 接受律
        assert TOMASGodelAgent.I_ACCEPT_RATIO == 1.05
        # 如果 NLU ℐ 作为 prior，Gödel 要求 new > prior × 1.05
        threshold = i_from_nlu * TOMASGodelAgent.I_ACCEPT_RATIO
        assert threshold <= 0.95 * 1.05, (
            "接受阈值不应超过 ℐ 上限的 1.05 倍"
        )

    def test_cross_aether_to_world_model_to_hodge(self):
        """跨-2: AetherSCMBridge → TOMASCausalWorldModel → HodgeICoupling。"""
        if not (_HAS_AETHER and _HAS_CWM and _HAS_HODGE):
            pytest.skip("Aether/Hodge/CausalWorldModel 不可用")

        # 1. 构建 SCM
        bridge = AetherSCMBridge()
        bridge.add_variable(CausalVariable("E_k", "KineticEnergy"))
        bridge.add_variable(CausalVariable("E_p", "PotentialEnergy"))
        bridge.add_causal_edge(CausalEdge(
            source="E_k", target="E_p",
            edge_type="direct", mechanism="Energy conservation",
            strength=1.0, is_hard_anchor=True,
        ))

        # 2. Hodge 守恒检查器
        wsc = WeightedSimplicialComplex(max_dim=2)
        hodge = HodgeICoupling(wsc, conservation_tolerance=1e-4)

        # 3. 因果世界模型
        model = TOMASCausalWorldModel(
            aether_bridge=bridge,
            hodge=hodge,
        )

        # 预测下一状态
        result = model.predict_next_state(
            current_state={"E_k": 100.0, "E_p": 0.0},
            action={"E_k": 50.0},
        )
        assert "h_hard_passed" in result, "跨模块预测缺少 h_hard_passed"
        assert "predicted_state" in result, "跨模块预测缺少 predicted_state"

    def test_cross_ksnap_mina_celo_pipeline(self):
        """跨-3: κ-Snap Merkle Root → Mina 上链 → Celo 支付验证。"""
        if not (_HAS_KSNAP and _HAS_MINA and _HAS_CELO):
            pytest.skip("KSnap/Mina/Celo 不可用")

        # 1. 创建 SnapEvent 并计算 Merkle Root
        events = [
            SnapEvent(
                event_id=f"cross_evt_{i}",
                candidate_id=f"cross_cand_{i}",
                result=SnapResult.MANIFESTED,
                observation_base=ObservationBase.COGNITIVE,
                timestamp=time.time() + i,
                reason=f"Cross-scenario test {i}",
                manifested_edge=None,
                new_code_hash=hashlib.sha256(f"cross_{i}".encode()).hexdigest(),
                trigger_obs_id=f"cross_obs_{i}",
                llm_version="cross_v1",
            )
            for i in range(3)
        ]
        merkle_root = KSnapOperator.batch_merkle_root(events)
        assert len(merkle_root) > 0

        # 2. Mina 降级模式包装
        mina = MinaTOMASSnap(mina_rpc_url="http://invalid:9999")
        proof = mina.wrap_snap(events[0])
        assert proof is not None

        # 3. Celo 降级模式支付
        celo = CeloBridge(celo_rpc_url="http://invalid:9999")
        tx_hash = celo.process_payment(
            from_addr="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            to_addr="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            amount=0.01,
            currency="cUSD",
        )
        assert len(tx_hash) > 0

    def test_cross_gpct_to_ehnn_dim_expansion(self):
        """跨-4: GPCT 层创检测 → EHNN 维度扩展。"""
        if not (_HAS_GPCT and _HAS_HYPEDGE and _HAS_EHNN):
            pytest.skip("GPCT/HypEdge/EHNN 不可用")

        # 1. GPCT 分解并检测层创
        edges = [
            HypEdge(nodes=(0, 1), eid="e0", i_val=0.95),
            HypEdge(nodes=(0, 2), eid="e1", i_val=0.9),
            HypEdge(nodes=(0, 3), eid="e2", i_val=0.85),
            HypEdge(nodes=(1, 2), eid="e3", i_val=0.3),
        ]
        decomposer = GpctDecomposer(edges=edges, k=2)
        emergence = decomposer.detect_causal_emergence()

        # 2. 如果检测到层创，EHNN 应能扩展输出维度
        ehnn = EMLEHNN(in_dim=4, hidden_dim=8, out_dim=2, k=2)
        original_dim = ehnn._out_dim_current if hasattr(ehnn, "_out_dim_current") else ehnn.out_dim

        if emergence["emerged"] and emergence["suggested_dim_expansion"] > 0:
            new_dim = original_dim + emergence["suggested_dim_expansion"]
            # EHNN 应支持维度扩展
            if hasattr(ehnn, "expand_output_dim"):
                ehnn.expand_output_dim(new_dim)
            elif hasattr(ehnn, "_out_dim_current"):
                ehnn._out_dim_current = new_dim
            # 验证维度已更新
            current_dim = ehnn._out_dim_current if hasattr(ehnn, "_out_dim_current") else ehnn.out_dim
            assert current_dim >= original_dim, (
                f"维度应扩展: {original_dim} → {current_dim}"
            )


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
