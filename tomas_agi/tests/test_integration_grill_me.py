# -*- coding: utf-8 -*-
"""
TOMAS AGI v3.11 — Grill-Me 与 TOMASGoalDirectedAgent 集成测试
=============================================================
覆盖: TOMASGoalDirectedAgent.grill_interrogate, gap_analyzer, grill_gate,
      no_silent_assumption, requirement_tracer, propose_goal 集成
"""

import pytest

from sim.goal_directed_agent import TOMASGoalDirectedAgent
from sim.grill_me_engine import (
    DIKWPGapAnalyzer,
    GrillExecutionGate,
    PsiNoSilentAssumption,
    RequirementTracer,
)


# ══════════════════════════════════════════════════════════════════
# Group 1: TOMASGoalDirectedAgent Grill-Me 组件初始化
# ══════════════════════════════════════════════════════════════════

class TestGrillComponentsInit:
    def test_grill_interrogate_exists(self):
        agent = TOMASGoalDirectedAgent("test-user")
        assert hasattr(agent, "grill_interrogate")

    def test_gap_analyzer_initialized(self):
        agent = TOMASGoalDirectedAgent("test-user")
        assert agent.gap_analyzer is not None

    def test_grill_gate_initialized(self):
        agent = TOMASGoalDirectedAgent("test-user")
        assert agent.grill_gate is not None

    def test_no_silent_assumption_initialized(self):
        agent = TOMASGoalDirectedAgent("test-user")
        assert agent.no_silent_assumption is not None

    def test_requirement_tracer_initialized(self):
        agent = TOMASGoalDirectedAgent("test-user")
        assert agent.requirement_tracer is not None

    def test_component_types(self):
        agent = TOMASGoalDirectedAgent("test-user")
        assert isinstance(agent.gap_analyzer, DIKWPGapAnalyzer)
        assert isinstance(agent.grill_gate, GrillExecutionGate)
        assert isinstance(agent.no_silent_assumption, PsiNoSilentAssumption)
        assert isinstance(agent.requirement_tracer, RequirementTracer)


# ══════════════════════════════════════════════════════════════════
# Group 2: grill_interrogate 方法
# ══════════════════════════════════════════════════════════════════

class TestGrillInterrogate:
    def test_returns_passed_key(self):
        agent = TOMASGoalDirectedAgent("test-user")
        result = agent.grill_interrogate("做个东西")
        assert "passed" in result

    def test_returns_gaps_remaining(self):
        agent = TOMASGoalDirectedAgent("test-user")
        result = agent.grill_interrogate("做个东西")
        assert "gaps_remaining" in result

    def test_returns_gap_dsl(self):
        agent = TOMASGoalDirectedAgent("test-user")
        result = agent.grill_interrogate("做个东西")
        assert "gap_dsl" in result

    def test_returns_requirement_id(self):
        agent = TOMASGoalDirectedAgent("test-user")
        result = agent.grill_interrogate("做个东西")
        assert "requirement_id" in result

    def test_vague_requirement_has_gaps(self):
        agent = TOMASGoalDirectedAgent("test-user")
        result = agent.grill_interrogate("做个东西")
        assert not result["passed"] or len(result.get("gaps_remaining", [])) > 0

    def test_returns_silent_assumptions(self):
        agent = TOMASGoalDirectedAgent("test-user")
        result = agent.grill_interrogate("做个东西")
        assert "silent_assumptions" in result

    def test_returns_trace_chain(self):
        agent = TOMASGoalDirectedAgent("test-user")
        result = agent.grill_interrogate("做个东西")
        assert "trace_chain" in result

    def test_gap_dsl_contains_dikwp(self):
        agent = TOMASGoalDirectedAgent("test-user")
        result = agent.grill_interrogate("需要登录功能")
        dsl = result.get("gap_dsl", "")
        assert "DIKWP" in dsl or "grill-me" in dsl


# ══════════════════════════════════════════════════════════════════
# Group 3: propose_goal 与 grill-me 集成
# ══════════════════════════════════════════════════════════════════

class TestProposeGoalGrillIntegration:
    def test_propose_goal_returns_result(self):
        agent = TOMASGoalDirectedAgent("test-user")
        result = agent.propose_goal("做一个用户管理系统")
        assert "goal_hash" in result or "status" in result

    def test_propose_goal_vague_may_be_blocked(self):
        agent = TOMASGoalDirectedAgent("test-user")
        result = agent.propose_goal("做个东西")
        # Vague requirement might be blocked or return empty goal_hash
        assert isinstance(result, dict)


# ══════════════════════════════════════════════════════════════════
# Group 4: idempotency & consistency
# ══════════════════════════════════════════════════════════════════

class TestGrillConsistency:
    def test_same_requirement_same_id(self):
        agent = TOMASGoalDirectedAgent("test-user")
        r1 = agent.grill_interrogate("需要登录功能")
        r2 = agent.grill_interrogate("需要登录功能")
        assert r1["requirement_id"] == r2["requirement_id"]

    def test_different_requirements_different_ids(self):
        agent = TOMASGoalDirectedAgent("test-user")
        r1 = agent.grill_interrogate("需要登录功能")
        r2 = agent.grill_interrogate("需要支付功能")
        assert r1["requirement_id"] != r2["requirement_id"]

    def test_lock_reason_consistency(self):
        agent = TOMASGoalDirectedAgent("test-user")
        result = agent.grill_interrogate("做个东西")
        if not result["passed"]:
            assert "lock_reason" in result
            assert len(result["lock_reason"]) > 0


# ══════════════════════════════════════════════════════════════════
# Group 5: ExecutionGate grill_precheck
# ══════════════════════════════════════════════════════════════════

class TestExecutionGateGrillPrecheck:
    def test_execution_gate_has_grill_gate(self):
        agent = TOMASGoalDirectedAgent("test-user")
        assert agent.execution_gate.grill_gate is not None

    def test_grill_precheck_enabled(self):
        agent = TOMASGoalDirectedAgent("test-user")
        assert agent.execution_gate.grill_precheck_enabled is True
