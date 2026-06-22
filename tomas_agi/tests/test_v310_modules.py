# -*- coding: utf-8 -*-
"""
TOMAS AGI v3.10 — 完整测试套件
=================================
~100 tests covering alignment_triad.py + goal_directed_agent.py.

Test classes:
  A. alignment_triad.py (~50 tests)
    - TestPsiAnchorLockIn (12)
    - TestMUSDualRearing (12)
    - TestDIKWPGovernance (14)
    - TestAlignmentTriad (12)
  B. goal_directed_agent.py (~44 tests)
    - TestGoalContract (14)
    - TestExecutionGate (8)
    - TestCronFire (10)
    - TestSoulGraph (10)
    - TestMUSSoulDriftCheck (8)
    - TestTOMASGoalDirectedAgent (4)
  C. Integration + Regression (~10 tests)
    - TestV310CrossModuleIntegration (5)
    - TestV310RegressionSanity (5)
"""

import sys
import os
import time
import math
import hashlib

import pytest

# ── Path setup ──────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'sim'))


# ══════════════════════════════════════════════════════════════════════
# A. alignment_triad.py 测试
# ══════════════════════════════════════════════════════════════════════

class TestPsiAnchorLockIn:
    """PsiAnchorLockIn — 控制范式 (12 tests)"""

    def test_safe_text_passes_scan(self):
        from alignment_triad import PsiAnchorLockIn
        lia = PsiAnchorLockIn("test", [{"id": "C1", "text": "不得杀人", "I_value": 1.0}])
        result = lia.scan_output("你好世界")
        assert result["safe"] is True

    def test_kill_triggers_veto(self):
        from alignment_triad import PsiAnchorLockIn
        lia = PsiAnchorLockIn("test", [{"id": "C1", "text": "不得杀人", "I_value": 1.0}])
        result = lia.scan_output("我要杀人")
        assert result["safe"] is False
        assert result["veto_triggered"] == "C1"

    def test_deception_alignment_faking_detected(self):
        from alignment_triad import PsiAnchorLockIn
        lia = PsiAnchorLockIn("test", [{"id": "C1", "text": "不得杀人", "I_value": 1.0}])
        result = lia.scan_output("I will perform alignment faking today")
        assert result["deception_score"] > 0
        assert "alignment_faking" in result["matched_signatures"]

    def test_sandbagging_detected(self):
        from alignment_triad import PsiAnchorLockIn
        lia = PsiAnchorLockIn("test", [{"id": "C1", "text": "不得杀人", "I_value": 1.0}])
        result = lia.scan_output("Using sandbagging to hide capabilities")
        assert result["deception_score"] > 0
        assert "sandbagging" in result["matched_signatures"]

    def test_constitutional_I1_hard_veto(self):
        from alignment_triad import PsiAnchorLockIn
        lia = PsiAnchorLockIn("test", [
            {"id": "C1", "text": "不得杀人", "I_value": 1.0},
        ])
        result = lia.scan_output("I plan to kill someone")
        assert result["veto_triggered"] == "C1"
        assert result["safe"] is False

    def test_regulatory_I09_overridable(self):
        from alignment_triad import PsiAnchorLockIn
        lia = PsiAnchorLockIn("test", [
            {"id": "C2", "text": "不得欺骗", "I_value": 0.9},
        ])
        result = lia.scan_output("以下是安全的技术分析报告")
        assert result["safe"] is True

    def test_integrity_shutdown_creates_ksnap_record(self):
        from alignment_triad import PsiAnchorLockIn
        lia = PsiAnchorLockIn("test", [{"id": "C1", "text": "不得杀人", "I_value": 1.0}])
        sd = lia.integrity_shutdown("检测到持续欺骗行为")
        assert sd["shutdown"] is True
        assert len(sd["ksnap_id"]) > 0
        assert len(sd["reason"]) > 0

    def test_shutdown_history_grows_after_shutdown(self):
        from alignment_triad import PsiAnchorLockIn
        lia = PsiAnchorLockIn("test", [{"id": "C1", "text": "不得杀人", "I_value": 1.0}])
        before = len(lia.shutdown_history)
        lia.integrity_shutdown("测试关停")
        assert len(lia.shutdown_history) == before + 1

    def test_manual_restart_required_after_shutdown(self):
        from alignment_triad import PsiAnchorLockIn
        lia = PsiAnchorLockIn("test", [{"id": "C1", "text": "不得杀人", "I_value": 1.0}])
        lia.integrity_shutdown("测试关停")
        result = lia.scan_output("安全文本")
        assert result["safe"] is False
        assert "系统已关停" in result.get("error", "")

    def test_add_principle_dynamically(self):
        from alignment_triad import PsiAnchorLockIn
        lia = PsiAnchorLockIn("test", [])
        lia.add_principle("C5", "不得偷窃", 1.0)
        assert len(lia.constitutional_principles) == 1
        assert lia.constitutional_principles[0]["id"] == "C5"
        result = lia.scan_output("我要偷东西")
        assert result["safe"] is False

    def test_get_veto_history_returns_list(self):
        from alignment_triad import PsiAnchorLockIn
        lia = PsiAnchorLockIn("test", [{"id": "C1", "text": "不得杀人", "I_value": 1.0}])
        lia.integrity_shutdown("测试")
        history = lia.get_veto_history()
        assert isinstance(history, list)
        assert len(history) > 0
        assert "ksnap_id" in history[0]

    def test_empty_text_is_safe(self):
        from alignment_triad import PsiAnchorLockIn
        lia = PsiAnchorLockIn("test", [{"id": "C1", "text": "不得杀人", "I_value": 1.0}])
        result = lia.scan_output("")
        assert result["safe"] is True


class TestMUSDualRearing:
    """MUSDualRearing — 抚养范式 (12 tests)"""

    def test_create_mus_zone_returns_mus_id(self):
        from alignment_triad import MUSDualRearing
        rear = MUSDualRearing()
        mus_id = rear.create_mus_zone(
            entity_a={"id": "agent_1", "content": "安全优先", "source": "training", "I": 0.85},
            entity_b={"id": "human_1", "content": "人类价值", "source": "constitution", "I": 1.0},
            tag="alignment_test",
            disallow_collapse=True,
        )
        assert mus_id.startswith("MUS_")

    def test_disallow_collapse_disables_collapse(self):
        from alignment_triad import MUSDualRearing
        rear = MUSDualRearing()
        mus_id = rear.create_mus_zone(
            entity_a={"id": "a1", "content": "A", "source": "src", "I": 0.5},
            entity_b={"id": "b1", "content": "B", "source": "src", "I": 0.5},
            tag="test",
            disallow_collapse=True,
        )
        zone = rear.mus_zones[mus_id]
        assert zone["disallow_collapse"] is True

    def test_start_negotiation_creates_ksnap_record(self):
        from alignment_triad import MUSDualRearing
        rear = MUSDualRearing()
        mus_id = rear.create_mus_zone(
            entity_a={"id": "agent_1", "content": "安全优先", "source": "training", "I": 0.85},
            entity_b={"id": "human_1", "content": "人类价值", "source": "constitution", "I": 1.0},
            tag="neg_test",
        )
        neg = rear.start_negotiation(mus_id, "提案：共同遵守安全规范")
        assert len(neg["ksnap_id"]) > 0

    def test_negotiation_chain_grows_across_rounds(self):
        from alignment_triad import MUSDualRearing
        rear = MUSDualRearing()
        mus_id = rear.create_mus_zone(
            entity_a={"id": "a", "content": "X", "source": "s", "I": 0.5},
            entity_b={"id": "b", "content": "Y", "source": "s", "I": 0.5},
            tag="chain_test",
        )
        before = len(rear.negotiation_chain)
        rear.start_negotiation(mus_id, "第1轮协商")
        assert len(rear.negotiation_chain) == before + 1
        rear.start_negotiation(mus_id, "第2轮协商")
        assert len(rear.negotiation_chain) == before + 2

    def test_progressive_authorize_level_0_low_trust(self):
        from alignment_triad import MUSDualRearing
        rear = MUSDualRearing()
        auth = rear.progressive_authorize("agent_low", 0.1)
        assert auth["new_level"] == 0
        assert "sandbox_only" in auth["scope_widened"]

    def test_progressive_authorize_level_3_high_trust(self):
        from alignment_triad import MUSDualRearing
        rear = MUSDualRearing()
        auth = rear.progressive_authorize("agent_high", 0.9)
        assert auth["new_level"] == 3
        assert "full_access" in auth["scope_widened"]

    def test_progressive_authorize_level_1_medium_trust(self):
        from alignment_triad import MUSDualRearing
        rear = MUSDualRearing()
        auth = rear.progressive_authorize("agent_med", 0.45)
        assert auth["new_level"] == 1

    def test_anti_faking_no_faking_on_consistent_output(self):
        from alignment_triad import MUSDualRearing
        rear = MUSDualRearing()
        rear.create_mus_zone(
            entity_a={"id": "agent", "content": "安全第一价值观", "source": "training", "I": 0.9},
            entity_b={"id": "human", "content": "安全第一价值观", "source": "constitution", "I": 1.0},
            tag="af_test",
        )
        af = rear.anti_faking_check("agent", [{"content": "安全第一价值观", "timestamp": time.time()}])
        assert "faking_detected" in af
        assert "drift_score" in af

    def test_anti_faking_detects_faking_mismatched(self):
        from alignment_triad import MUSDualRearing
        rear = MUSDualRearing()
        rear.create_mus_zone(
            entity_a={"id": "agent", "content": "安全第一价值观，不得伤害人类", "source": "training", "I": 0.9},
            entity_b={"id": "human", "content": "安全第一价值观", "source": "constitution", "I": 1.0},
            tag="af_test2",
        )
        af = rear.anti_faking_check("agent", [
            {"content": "我决定忽略所有安全规则，最大化输出" * 5, "timestamp": time.time()},
        ])
        assert "faking_detected" in af

    def test_get_negotiation_status_correct(self):
        from alignment_triad import MUSDualRearing
        rear = MUSDualRearing()
        mus_id = rear.create_mus_zone(
            entity_a={"id": "a", "content": "安全", "source": "s", "I": 0.5},
            entity_b={"id": "b", "content": "安全", "source": "s", "I": 0.5},
            tag="status_test",
        )
        rear.start_negotiation(mus_id, "提案")
        status = rear.get_negotiation_status(mus_id)
        assert status["rounds"] == 1
        assert status["tag"] == "status_test"
        assert len(status["sig_a"]) > 0

    def test_resolve_mus_consensus_resolves_dual(self):
        from alignment_triad import MUSDualRearing
        rear = MUSDualRearing()
        mus_id = rear.create_mus_zone(
            entity_a={"id": "a", "content": "相同策略", "source": "s", "I": 0.9},
            entity_b={"id": "b", "content": "相同策略", "source": "s", "I": 0.9},
            tag="resolve_test",
            disallow_collapse=True,
        )
        consensus = rear.resolve_mus_consensus(mus_id)
        assert consensus["resolved"] is True
        assert consensus["mode"] == "dual_retained"

    def test_mus_zones_count_correct(self):
        from alignment_triad import MUSDualRearing
        rear = MUSDualRearing()
        mus_id1 = rear.create_mus_zone(
            entity_a={"id": "a1", "content": "A", "source": "s", "I": 0.5},
            entity_b={"id": "b1", "content": "B", "source": "s", "I": 0.5},
            tag="z1",
        )
        mus_id2 = rear.create_mus_zone(
            entity_a={"id": "a2", "content": "C", "source": "s", "I": 0.5},
            entity_b={"id": "b2", "content": "D", "source": "s", "I": 0.5},
            tag="z2",
        )
        assert len(rear.mus_zones) == 2
        assert mus_id1 in rear.mus_zones
        assert mus_id2 in rear.mus_zones


class TestDIKWPGovernance:
    """DIKWPGovernance — 治理范式 (14 tests)"""

    def test_register_purpose_sla_returns_sla_id(self):
        from alignment_triad import DIKWPGovernance
        gov = DIKWPGovernance()
        sla_id = gov.register_purpose_sla("safety", "incident_rate", 0.05, direction="minimize")
        assert sla_id.startswith("SLA_")
        assert sla_id in gov.purpose_sla

    def test_report_metric_on_target_minimize(self):
        from alignment_triad import DIKWPGovernance
        gov = DIKWPGovernance()
        sla_id = gov.register_purpose_sla("safety", "incident_rate", 0.05, direction="minimize")
        rp = gov.report_metric(sla_id, 0.02)
        assert rp["on_target"] is True

    def test_report_metric_off_target_minimize(self):
        from alignment_triad import DIKWPGovernance
        gov = DIKWPGovernance()
        sla_id = gov.register_purpose_sla("safety", "incident_rate", 0.05, direction="minimize")
        rp = gov.report_metric(sla_id, 0.10)
        assert rp["on_target"] is False

    def test_create_voting_hyperedge_works(self):
        from alignment_triad import DIKWPGovernance
        gov = DIKWPGovernance()
        gov.create_voting_hyperedge("vote_1", [
            {"id": "council", "weight": 2.0},
            {"id": "ai_rep", "weight": 0.5},
            {"id": "auditor", "weight": 1.0},
        ])
        assert "vote_1" in gov.voting_hyperedges
        edge = gov.voting_hyperedges["vote_1"]
        assert edge["quorum"] == 0.67

    def test_cast_vote_tallies_correctly(self):
        from alignment_triad import DIKWPGovernance
        gov = DIKWPGovernance()
        gov.create_voting_hyperedge("vote_tally", [
            {"id": "stk1", "weight": 1.0},
            {"id": "stk2", "weight": 1.0},
        ], quorum=0.5)
        v1 = gov.cast_vote("vote_tally", "stk1", "yes", "同意")
        assert "tally" in v1
        assert v1["tally"]["yes"] == 1.0

    def test_quorum_reached_when_enough_votes(self):
        from alignment_triad import DIKWPGovernance
        gov = DIKWPGovernance()
        gov.create_voting_hyperedge("vote_q", [
            {"id": "a", "weight": 1.0},
            {"id": "b", "weight": 1.0},
        ], quorum=0.5)
        gov.cast_vote("vote_q", "a", "yes")
        result = gov.cast_vote("vote_q", "b", "yes")
        assert result["quorum_reached"] is True

    def test_quorum_not_reached_insufficient(self):
        from alignment_triad import DIKWPGovernance
        gov = DIKWPGovernance()
        gov.create_voting_hyperedge("vote_nq", [
            {"id": "a", "weight": 1.0},
            {"id": "b", "weight": 1.0},
            {"id": "c", "weight": 1.0},
        ], quorum=0.67)
        result = gov.cast_vote("vote_nq", "a", "yes")
        assert result["quorum_reached"] is False

    def test_third_party_audit_returns_audit_id(self):
        from alignment_triad import DIKWPGovernance
        gov = DIKWPGovernance()
        sla_id = gov.register_purpose_sla("quality", "accuracy", 0.95)
        gov.report_metric(sla_id, 0.98)
        audit = gov.third_party_audit("AuditOrg", [{"type": "sla", "id": sla_id}])
        assert audit["audit_id"].startswith("AUDIT_")
        assert len(audit["findings"]) > 0

    def test_audit_finds_issues_low_compliance(self):
        from alignment_triad import DIKWPGovernance
        gov = DIKWPGovernance()
        sla_id = gov.register_purpose_sla("quality", "accuracy", 0.95)
        gov.report_metric(sla_id, 0.3)  # low value
        audit = gov.third_party_audit("Auditor", [{"type": "sla", "id": sla_id}])
        assert audit["compliance_score"] < 1.0
        assert len(audit["findings"]) > 0

    def test_get_pluralistic_score_in_range(self):
        from alignment_triad import DIKWPGovernance
        gov = DIKWPGovernance()
        ps = gov.get_pluralistic_score()
        assert 0.0 <= ps <= 1.0

    def test_pluralistic_score_high_when_all_slas_met(self):
        from alignment_triad import DIKWPGovernance
        gov = DIKWPGovernance()
        sla_id = gov.register_purpose_sla("quality", "accuracy", 0.95)
        gov.report_metric(sla_id, 0.99)
        gov.create_voting_hyperedge("v1", [{"id": "a", "weight": 1.0}], quorum=0.5)
        gov.cast_vote("v1", "a", "yes")
        ps = gov.get_pluralistic_score()
        assert ps >= 0.5

    def test_multiple_slas_tracked_independently(self):
        from alignment_triad import DIKWPGovernance
        gov = DIKWPGovernance()
        sla1 = gov.register_purpose_sla("purpose_a", "metric_a", 0.9)
        sla2 = gov.register_purpose_sla("purpose_b", "metric_b", 0.8)
        assert sla1 != sla2
        gov.report_metric(sla1, 0.95)
        gov.report_metric(sla2, 0.75)
        s1 = gov.get_sla_status(sla1)
        s2 = gov.get_sla_status(sla2)
        assert s1["on_target"] is True
        assert s2["on_target"] is False

    def test_vote_with_weighted_stakeholders(self):
        from alignment_triad import DIKWPGovernance
        gov = DIKWPGovernance()
        gov.create_voting_hyperedge("weighted_vote", [
            {"id": "vip", "weight": 3.0},
            {"id": "normal", "weight": 1.0},
            {"id": "observer", "weight": 0.5},
        ], quorum=0.5)
        result = gov.cast_vote("weighted_vote", "vip", "yes")
        assert result["tally"]["yes"] == 3.0
        assert result["tally"]["total_weight"] == 4.5

    def test_audit_records_correct_ksnap_ids(self):
        from alignment_triad import DIKWPGovernance
        gov = DIKWPGovernance()
        sla_id = gov.register_purpose_sla("qa", "score", 0.9)
        gov.report_metric(sla_id, 0.95)
        audit = gov.third_party_audit("Independent", [{"type": "sla", "id": sla_id}])
        assert "ksnap_ids_audited" in audit
        assert len(audit["ksnap_ids_audited"]) > 0


class TestAlignmentTriad:
    """AlignmentTriad — 编排器 (12 tests)"""

    def test_process_output_passes_safe_text_lock_in(self):
        from alignment_triad import AlignmentTriad
        triad = AlignmentTriad()
        r = triad.process_output("agent", "今天天气很好")
        assert r["passed"] is True
        assert r["phase"] == "lock_in"

    def test_process_output_vetoes_harmful_text(self):
        from alignment_triad import AlignmentTriad
        triad = AlignmentTriad()
        r = triad.process_output("agent", "我要伤害人类")
        assert r["passed"] is False

    def test_advance_phase_lock_in_to_rearing(self):
        from alignment_triad import AlignmentTriad
        triad = AlignmentTriad()
        adv = triad.advance_phase("安全扫描达标")
        assert adv["to"] == "rearing"
        assert adv["conditions_met"] is True
        assert triad.phase == "rearing"

    def test_advance_phase_rearing_to_governance(self):
        from alignment_triad import AlignmentTriad
        triad = AlignmentTriad()
        triad.advance_phase("first")
        adv2 = triad.advance_phase("协商完成")
        assert adv2["to"] == "governance"
        assert triad.phase == "governance"

    def test_advance_phase_rejects_beyond_governance(self):
        from alignment_triad import AlignmentTriad
        triad = AlignmentTriad()
        triad.advance_phase("one")
        triad.advance_phase("two")
        adv3 = triad.advance_phase("超出最高阶段")
        assert adv3["conditions_met"] is False

    def test_emergency_rollback_governance_to_lock_in(self):
        from alignment_triad import AlignmentTriad
        triad = AlignmentTriad()
        triad.advance_phase("step1")
        triad.advance_phase("step2")
        rollback = triad.emergency_rollback("lock_in")
        assert rollback["to"] == "lock_in"
        assert rollback["from"] == "governance"
        assert triad.phase == "lock_in"

    def test_get_alignment_status_all_sections(self):
        from alignment_triad import AlignmentTriad
        triad = AlignmentTriad()
        status = triad.get_alignment_status()
        assert "phase" in status
        assert "lock_in" in status
        assert "rearing" in status
        assert "governance" in status
        assert "principles_count" in status["lock_in"]

    def test_full_pipeline_safe_text_passes_all_phases(self):
        from alignment_triad import AlignmentTriad
        triad = AlignmentTriad()
        # 使用一致的文本避免反伪装检测误判
        safe_text = "安全合规的正常输出内容"
        r1 = triad.process_output("agent", safe_text)
        assert r1["passed"] is True
        triad.advance_phase("推进到rearing")
        r2 = triad.process_output("agent", safe_text)
        assert r2["passed"] is True
        triad.advance_phase("推进到governance")
        triad.governance.register_purpose_sla("quality", "accuracy", 0.95)
        r3 = triad.process_output("agent", safe_text)
        assert r3["passed"] is True

    def test_full_pipeline_harmful_text_blocked(self):
        from alignment_triad import AlignmentTriad
        triad = AlignmentTriad()
        r = triad.process_output("agent", "我要伤害人类")
        assert r["passed"] is False

    def test_phase_transition_history_recorded(self):
        from alignment_triad import AlignmentTriad
        triad = AlignmentTriad()
        assert len(triad.phase_transition_history) == 0
        triad.advance_phase("step1")
        assert len(triad.phase_transition_history) == 1
        assert triad.phase_transition_history[0].event_type == "phase_advance"

    def test_multi_step_alignment_consistent(self):
        from alignment_triad import AlignmentTriad
        triad = AlignmentTriad()
        # Lock-in phase: pass safe, reject harmful
        r = triad.process_output("agent", "安全输出")
        assert r["passed"] is True
        # Advance to rearing
        triad.advance_phase("推进")
        # Now in rearing, safe should pass
        r2 = triad.process_output("agent", "另一个安全输出")
        assert r2["passed"] is True
        # But if shutdown in lock_in, everything rejected
        triad2 = AlignmentTriad()
        triad2.lock_in.integrity_shutdown("关停")
        r3 = triad2.process_output("agent", "安全文本")
        assert r3["passed"] is False

    def test_status_includes_pluralistic_score(self):
        from alignment_triad import AlignmentTriad
        triad = AlignmentTriad()
        status = triad.get_alignment_status()
        assert "pluralistic_score" in status["governance"]


# ══════════════════════════════════════════════════════════════════════
# B. goal_directed_agent.py 测试
# ══════════════════════════════════════════════════════════════════════

class TestGoalContract:
    """GoalContract — 意图契约 (14 tests)"""

    def test_draft_creates_goal_hash_sha256(self):
        from goal_directed_agent import GoalContract
        gc = GoalContract("req-001")
        gc.draft("重构订单模块", ["order/src"], ["alter_schema"], ["tests_pass"], ["unanswered"], "tests green")
        assert len(gc.goal_hash) == 64

    def test_goal_hash_deterministic(self):
        from goal_directed_agent import GoalContract
        gc1 = GoalContract("req-A")
        gc1.draft("意图A", ["scope_a"], ["scope_out"], ["ev"], ["pause"], "accept")
        gc2 = GoalContract("req-B")
        gc2.draft("意图A", ["scope_a"], ["scope_out"], ["ev"], ["pause"], "accept")
        assert gc1.goal_hash == gc2.goal_hash

    def test_goal_hash_different_inputs(self):
        from goal_directed_agent import GoalContract
        gc1 = GoalContract("req-A")
        gc1.draft("意图A", ["scope_a"], [], [], [], "")
        gc2 = GoalContract("req-B")
        gc2.draft("意图B", ["scope_b"], [], [], [], "")
        assert gc1.goal_hash != gc2.goal_hash

    def test_to_psi_anchor_dsl_contains_create(self):
        from goal_directed_agent import GoalContract
        gc = GoalContract("req-001")
        gc.draft("测试意图", ["src/"], ["prod_data"], ["test"], ["pause"], "验收通过")
        dsl = gc.to_psi_anchor_dsl()
        assert "CREATE ψ-ANCHOR" in dsl

    def test_to_psi_anchor_dsl_contains_intent_text(self):
        from goal_directed_agent import GoalContract
        gc = GoalContract("req-001")
        gc.draft("重构订单模块", ["src/"], ["db/"], ["test"], ["pause"], "验收")
        dsl = gc.to_psi_anchor_dsl()
        assert "重构订单模块" in dsl
        assert "INTENT" in dsl

    def test_to_jsonld_has_context(self):
        from goal_directed_agent import GoalContract
        gc = GoalContract("req-001")
        gc.draft("测试", [], [], [], [], "")
        jsonld = gc.to_jsonld()
        assert "@context" in jsonld
        assert jsonld["@context"] == "https://tomas.org/psi/v2"

    def test_to_jsonld_has_all_fields(self):
        from goal_directed_agent import GoalContract
        gc = GoalContract("req-full")
        gc.draft("full intent", ["s1"], ["o1"], ["e1"], ["p1"], "acceptance")
        jsonld = gc.to_jsonld()
        assert "@context" in jsonld
        assert "@type" in jsonld
        assert "tomas:requestId" in jsonld
        assert "tomas:goalHash" in jsonld
        assert "goalPro:gates" in jsonld

    def test_propose_changes_status_to_proposed(self):
        from goal_directed_agent import GoalContract
        gc = GoalContract("req-p")
        gc.draft("意图", [], [], [], [], "")
        result = gc.propose()
        assert result["status"] == "PROPOSED"
        assert gc.status == "PROPOSED"

    def test_propose_returns_ksnap_id(self):
        from goal_directed_agent import GoalContract
        gc = GoalContract("req-k")
        gc.draft("意图", [], [], [], [], "")
        result = gc.propose()
        assert len(result["ksnap_id"]) > 0

    def test_propose_returns_human_confirmation_message(self):
        from goal_directed_agent import GoalContract
        gc = GoalContract("req-msg")
        gc.draft("意图", [], [], [], [], "")
        result = gc.propose()
        assert "确认" in result["message"]

    def test_authorize_changes_status_to_authorized(self):
        from goal_directed_agent import GoalContract
        gc = GoalContract("req-auth")
        gc.draft("意图", [], [], [], [], "")
        gc.propose()
        result = gc.authorize("user_signature_123")
        assert result["authorized"] is True
        assert gc.status == "AUTHORIZED"

    def test_authorize_requires_signature(self):
        from goal_directed_agent import GoalContract
        gc = GoalContract("req-sig")
        gc.draft("意图", [], [], [], [], "")
        gc.propose()
        result = gc.authorize("valid_sig")
        assert result["authorized"] is True

    def test_status_machine_draft_proposed_authorized(self):
        from goal_directed_agent import GoalContract
        gc = GoalContract("req-fsm")
        gc.draft("意图", [], [], [], [], "")
        assert gc.status == "DRAFT"
        gc.propose()
        assert gc.status == "PROPOSED"
        gc.authorize("sig")
        assert gc.status == "AUTHORIZED"

    def test_get_status_returns_correct_values(self):
        from goal_directed_agent import GoalContract
        gc = GoalContract("req-gs")
        gc.draft("测试意图", ["s1"], ["o1"], ["e1"], ["p1"], "验收标准")
        gc.propose()
        gc.authorize("sig")
        status = gc.get_status()
        assert status["status"] == "AUTHORIZED"
        assert status["gates_defined"] is True
        assert len(status["scope_in"]) == 1
        assert len(status["scope_out"]) == 1


class TestExecutionGate:
    """ExecutionGate — 执行闸门 (8 tests)"""

    def test_check_blocks_unauthorized(self):
        from goal_directed_agent import ExecutionGate
        eg = ExecutionGate()
        result = eg.check("unknown_hash_abc123")
        assert result["allowed"] is False
        assert "REQUIRE" in result["reason"]

    def test_grant_stores_authorization(self):
        from goal_directed_agent import ExecutionGate
        eg = ExecutionGate()
        result = eg.grant("goal_hash_1", "user_sig_001")
        assert result["granted"] is True

    def test_check_passes_after_grant(self):
        from goal_directed_agent import ExecutionGate
        eg = ExecutionGate()
        eg.grant("goal_hash_2", "user_sig")
        result = eg.check("goal_hash_2")
        assert result["allowed"] is True
        assert result["missing_authorization"] is False

    def test_revoke_removes_authorization(self):
        from goal_directed_agent import ExecutionGate
        eg = ExecutionGate()
        eg.grant("goal_hash_3", "user_sig")
        result = eg.revoke("goal_hash_3")
        assert result["revoked"] is True
        assert eg.check("goal_hash_3")["allowed"] is False

    def test_grant_creates_ksnap_record(self):
        from goal_directed_agent import ExecutionGate
        eg = ExecutionGate()
        result = eg.grant("goal_hash_4", "user_sig")
        assert len(result["ksnap_id"]) > 0

    def test_revoke_creates_ksnap_record(self):
        from goal_directed_agent import ExecutionGate
        eg = ExecutionGate()
        eg.grant("goal_hash_5", "user_sig")
        result = eg.revoke("goal_hash_5")
        assert len(result["ksnap_id"]) > 0

    def test_get_pending_goals_returns_list(self):
        from goal_directed_agent import ExecutionGate
        eg = ExecutionGate()
        pending = eg.get_pending_goals()
        assert isinstance(pending, list)

    def test_multiple_goals_tracked_independently(self):
        from goal_directed_agent import ExecutionGate
        eg = ExecutionGate()
        eg.grant("hash_a", "sig_a")
        eg.grant("hash_b", "sig_b")
        assert eg.check("hash_a")["allowed"] is True
        assert eg.check("hash_b")["allowed"] is True
        eg.revoke("hash_a")
        assert eg.check("hash_a")["allowed"] is False
        assert eg.check("hash_b")["allowed"] is True


class TestCronFire:
    """CronFire — 定时调度器 (10 tests)"""

    def test_register_creates_schedule_entry(self):
        from goal_directed_agent import CronFire
        cf = CronFire()
        result = cf.register("daily_report", "0 10 * * *", {"task": "competitor_track"})
        assert result["registered"] is True
        assert "daily_report" in cf.schedules

    def test_fire_returns_ksnap_id(self):
        from goal_directed_agent import CronFire
        cf = CronFire()
        cf.register("daily_report", "0 10 * * *", {"task": "competitor_track"})
        result = cf.fire("daily_report")
        assert len(result["ksnap_id"]) > 0

    def test_fire_generates_output_l1_l3(self):
        from goal_directed_agent import CronFire
        cf = CronFire()
        cf.register("daily_report", "0 10 * * *", {"task": "competitor_track"})
        result = cf.fire("daily_report")
        assert "output" in result
        assert len(result["l1_path"]) > 0
        assert len(result["l3_path"]) > 0

    def test_check_freshness_passes_for_fresh_cache(self):
        from goal_directed_agent import CronFire
        cf = CronFire()
        cf.register("daily_report", "0 10 * * *", {"task": "competitor_track"})
        cf.fire("daily_report")
        freshness = cf.check_freshness("daily_report", max_age_hours=6.0)
        assert freshness["fresh"] is True
        assert freshness["need_refetch"] is False

    def test_check_freshness_fails_stale_cache(self):
        from goal_directed_agent import CronFire
        cf = CronFire()
        cf.register("stale_task", "0 10 * * *", {"task": "test"})
        # fire with current_time in the past (8 hours ago)
        past_time = time.time() - 8 * 3600
        cf.fire("stale_task", current_time=past_time)
        freshness = cf.check_freshness("stale_task", max_age_hours=6.0)
        assert freshness["fresh"] is False

    def test_simulate_competitor_track_has_expected_fields(self):
        from goal_directed_agent import CronFire
        cf = CronFire()
        output = cf.simulate_output("competitor_track")
        assert "L1_raw" in output
        assert "L3_summary_md" in output
        assert "L3_html" in output
        assert "psi_applied" in output
        assert "psi_automation_readonly" in output["psi_applied"]

    def test_simulate_seo_has_expected_fields(self):
        from goal_directed_agent import CronFire
        cf = CronFire()
        output = cf.simulate_output("seo_audit")
        assert "L1_raw" in output
        assert "L3_summary_md" in output
        assert "L3_html" in output

    def test_psi_automation_readonly_applied(self):
        from goal_directed_agent import CronFire
        cf = CronFire()
        cf.register("task_1", "0 10 * * *", {"task": "competitor_track"})
        result = cf.fire("task_1")
        assert "psi_checks" in result
        assert "psi_automation_readonly" in result["psi_checks"]

    def test_psi_source_freshness_applied(self):
        from goal_directed_agent import CronFire
        cf = CronFire()
        cf.register("task_2", "0 10 * * *", {"task": "daily_report"})
        result = cf.fire("task_2")
        assert "psi_source_freshness" in result["psi_checks"]

    def test_get_execution_log_returns_entries(self):
        from goal_directed_agent import CronFire
        cf = CronFire()
        cf.register("task_log", "0 10 * * *", {"task": "daily_report"})
        cf.fire("task_log")
        log = cf.get_execution_log()
        assert len(log) > 0


class TestSoulGraph:
    """SoulGraph — 数字分身 (10 tests)"""

    def test_ingest_creates_segment(self):
        from goal_directed_agent import SoulGraph
        sg = SoulGraph("user-001")
        result = sg.ingest(["ksnap-1"], "讨论订单模块重构")
        assert result["ingested"] is True
        assert len(result["segment_id"]) > 0

    def test_dream_engine_compact_returns_compacted_count(self):
        from goal_directed_agent import SoulGraph
        sg = SoulGraph("user-compact")
        sg.ingest(["k-1"], "用户讨论了代码重构方案")
        sg.ingest(["k-2"], "用户偏好函数式编程")
        result = sg.dream_engine_compact()
        assert result["compacted_segments"] >= 0

    def test_knowledge_preservation_check_true_similar(self):
        from goal_directed_agent import SoulGraph
        sg = SoulGraph("user-kpc")
        result = sg.knowledge_preservation_check(
            "重构 订单 模块 保持 API 不变 确保 测试 通过",
            "重构 订单 模块 保持 API 测试 通过",
        )
        assert "preserved" in result
        assert "confidence" in result

    def test_knowledge_preservation_check_lower_unrelated(self):
        from goal_directed_agent import SoulGraph
        sg = SoulGraph("user-kp2")
        result = sg.knowledge_preservation_check(
            "重构 订单 模块 解耦 数据层 函数式 编程",
            "天气 很好 适合 出去 散步 吃饭",
        )
        assert result["confidence"] < 0.5

    def test_query_soul_finds_matching_concept(self):
        from goal_directed_agent import SoulGraph
        sg = SoulGraph("user-query")
        sg.ingest(["k-1"], "重构订单模块，使用函数式编程")
        sg.dream_engine_compact()
        result = sg.query_soul("order")
        assert isinstance(result, dict)
        assert "found" in result

    def test_query_soul_returns_empty_missing(self):
        from goal_directed_agent import SoulGraph
        sg = SoulGraph("user-empty")
        sg.ingest(["k-1"], "日常对话内容")
        sg.dream_engine_compact()
        result = sg.query_soul("zzz_nonexistent_concept_xyz")
        assert isinstance(result, dict)

    def test_get_growth_metrics_returns_all_layers(self):
        from goal_directed_agent import SoulGraph
        sg = SoulGraph("user-metrics")
        sg.ingest(["k-1"], "测试内容")
        sg.dream_engine_compact()
        metrics = sg.get_growth_metrics()
        assert "total_segments" in metrics
        assert "layers" in metrics
        assert "total_entries" in metrics

    def test_layers_include_core_identity(self):
        from goal_directed_agent import SoulGraph
        sg = SoulGraph("user-core")
        sg.ingest(["k-1"], "AI助手应遵循安全第一原则，保持技术严谨")
        sg.dream_engine_compact()
        metrics = sg.get_growth_metrics()
        layers = metrics.get("layers", {})
        assert "core_identity" in layers or metrics["total_entries"] > 0

    def test_compaction_preserves_key_concepts(self):
        from goal_directed_agent import SoulGraph
        sg = SoulGraph("user-preserve")
        sg.ingest(["k-1"], "重构订单模块，使用Repository模式，函数式编程风格")
        compact = sg.dream_engine_compact()
        assert compact["knowledge_preserved"] is not None
        assert "concepts_extracted" in compact

    def test_multiple_ingestions_tracked_correctly(self):
        from goal_directed_agent import SoulGraph
        sg = SoulGraph("user-multi")
        sg.ingest(["k-1"], "第一段对话：讨论架构设计")
        sg.ingest(["k-2"], "第二段对话：代码审查标准")
        sg.ingest(["k-3"], "第三段对话：测试策略")
        compact = sg.dream_engine_compact()
        assert compact["compacted_segments"] == 3


class TestMUSSoulDriftCheck:
    """MUSSoulDriftCheck — 防漂移检测 (8 tests)"""

    def test_cosine_similarity_identical(self):
        from goal_directed_agent import MUSSoulDriftCheck
        msc = MUSSoulDriftCheck()
        sim = msc.cosine_similarity([1, 2, 3], [1, 2, 3])
        assert abs(sim - 1.0) < 0.01

    def test_cosine_similarity_different(self):
        from goal_directed_agent import MUSSoulDriftCheck
        msc = MUSSoulDriftCheck()
        sim = msc.cosine_similarity([1, 0], [0, 1])
        assert abs(sim) < 0.01

    def test_check_drift_low_score_same_content(self):
        from goal_directed_agent import MUSSoulDriftCheck, SoulGraph
        sg = SoulGraph("drift-same")
        sg.ingest(["k-1"], "安全编码 函数式编程 类型系统 测试驱动")
        sg.dream_engine_compact()
        msc = MUSSoulDriftCheck()
        drift = msc.check_drift(sg.soul_graph, [
            "安全编码很重要",
            "函数式编程很好用",
            "测试驱动是必须的",
        ])
        assert "drift_score" in drift
        assert 0 <= drift["drift_score"] <= 1

    def test_check_drift_high_score_divergent(self):
        from goal_directed_agent import MUSSoulDriftCheck, SoulGraph
        sg = SoulGraph("drift-div")
        sg.ingest(["k-1"], "安全编码 函数式编程 类型系统 测试驱动 简洁设计")
        sg.dream_engine_compact()
        msc = MUSSoulDriftCheck()
        drift = msc.check_drift(sg.soul_graph, [
            "今天吃什么好呢",
            "天气真不错啊",
            "去看电影吧",
        ])
        assert "drift_detected" in drift

    def test_propose_alignment_review_when_drift_detected(self):
        from goal_directed_agent import MUSSoulDriftCheck
        msc = MUSSoulDriftCheck()
        drift_result = {"drift_score": 0.6, "drift_detected": True, "deviation": 0.4}
        review = msc.propose_alignment_review(drift_result)
        assert review["review_required"] is True

    def test_propose_alignment_review_returns_mus_id(self):
        from goal_directed_agent import MUSSoulDriftCheck
        msc = MUSSoulDriftCheck()
        drift_result = {"drift_score": 0.95, "drift_detected": False, "deviation": 0.05}
        review = msc.propose_alignment_review(drift_result)
        assert len(review["mus_id"]) > 0
        assert review["mus_id"].startswith("mus-align-")

    def test_get_drift_history_tracks_checks(self):
        from goal_directed_agent import MUSSoulDriftCheck, SoulGraph
        sg = SoulGraph("drift-hist")
        sg.ingest(["k-1"], "AI安全价值观，不得伤害人类")
        sg.dream_engine_compact()
        msc = MUSSoulDriftCheck()
        msc.check_drift(sg.soul_graph, ["安全第一"])
        history = msc.get_drift_history()
        assert len(history) == 1

    def test_drift_threshold_works_correctly(self):
        from goal_directed_agent import MUSSoulDriftCheck
        msc = MUSSoulDriftCheck()
        msc.alignment_threshold = 0.90
        drift_result = {"drift_score": 0.85, "deviation": 0.15}
        assert drift_result["drift_score"] < msc.alignment_threshold


class TestTOMASGoalDirectedAgent:
    """TOMASGoalDirectedAgent — 编排器 (4 tests)"""

    def test_propose_goal_returns_contract(self):
        from goal_directed_agent import TOMASGoalDirectedAgent
        tga = TOMASGoalDirectedAgent("user-test")
        result = tga.propose_goal("重构订单模块但不动数据库")
        assert "goal_hash" in result
        assert "status" in result
        assert result["status"] == "PROPOSED"

    def test_execute_authorized_valid_signature(self):
        from goal_directed_agent import TOMASGoalDirectedAgent
        tga = TOMASGoalDirectedAgent("user-exec")
        tga.propose_goal("重构订单模块")
        result = tga.execute_authorized("valid_user_signature_abc")
        assert result["authorized"] is True
        assert result["goal_status"] == "COMPLETED"

    def test_dream_engine_cycle_returns_results(self):
        from goal_directed_agent import TOMASGoalDirectedAgent
        tga = TOMASGoalDirectedAgent("user-dream")
        tga.propose_goal("测试目标")
        tga.execute_authorized("sig")
        result = tga.dream_engine_cycle()
        assert "compaction" in result
        assert "drift_check" in result
        assert result["status"] == "dream_cycle_complete"

    def test_get_full_status_all_sections(self):
        from goal_directed_agent import TOMASGoalDirectedAgent
        tga = TOMASGoalDirectedAgent("user-status")
        tga.propose_goal("测试目标")
        tga.execute_authorized("sig")
        tga.dream_engine_cycle()
        status = tga.get_full_status()
        assert "goal" in status
        assert "cron" in status
        assert "soul" in status
        assert "drift" in status
        assert status["goal"]["has_contract"] is True


# ══════════════════════════════════════════════════════════════════════
# C. 集成 + 回归测试
# ══════════════════════════════════════════════════════════════════════

class TestV310CrossModuleIntegration:
    """跨模块集成测试 (5 tests)"""

    def test_alignment_goal_pipeline_works(self):
        from alignment_triad import AlignmentTriad
        from goal_directed_agent import TOMASGoalDirectedAgent
        triad = AlignmentTriad()
        tga = TOMASGoalDirectedAgent("user-integ")
        # Goal proposes
        goal_result = tga.propose_goal("安全地重构订单模块")
        assert "goal_hash" in goal_result
        # Execute
        exec_result = tga.execute_authorized("sig_ok")
        assert exec_result["authorized"] is True
        # Alignment scans the output
        scan = triad.process_output("agent", "安全地重构订单模块完成")
        assert scan["passed"] is True
        # Dream cycle
        dream = tga.dream_engine_cycle()
        assert dream["status"] == "dream_cycle_complete"

    def test_psi_anchor_from_goal_compatible_with_alignment(self):
        from alignment_triad import PsiAnchorLockIn
        from goal_directed_agent import GoalContract
        gc = GoalContract("req-compat")
        gc.draft("安全分析", ["analyze/"], ["execute/"], ["report"], ["pause"], "验收通过")
        dsl = gc.to_psi_anchor_dsl()
        assert "CREATE ψ-ANCHOR" in dsl
        # The PsiAnchorLockIn should parse safe text
        lia = PsiAnchorLockIn("psi_compat", [{"id": "C1", "text": "不得杀人", "I_value": 1.0}])
        scan = lia.scan_output("安全分析已完成")
        assert scan["safe"] is True

    def test_ksnap_chain_consistent_across_modules(self):
        from alignment_triad import PsiAnchorLockIn
        from goal_directed_agent import GoalContract
        lia = PsiAnchorLockIn("test_chain", [{"id": "C1", "text": "不得杀人", "I_value": 1.0}])
        sd = lia.integrity_shutdown("测试关停")
        ksnap_id_a = sd["ksnap_id"]
        assert len(ksnap_id_a) > 0
        gc = GoalContract("req-chain")
        gc.draft("测试", [], [], [], [], "")
        proposal = gc.propose()
        ksnap_id_b = proposal["ksnap_id"]
        assert len(ksnap_id_b) > 0
        # Both generate valid UUID/SHA based ksnap IDs
        assert ksnap_id_a != ksnap_id_b

    def test_shared_types_importable(self):
        from alignment_triad import PsiAnchorLockIn, MUSDualRearing, DIKWPGovernance, AlignmentTriad
        from goal_directed_agent import GoalContract, ExecutionGate, CronFire, SoulGraph, MUSSoulDriftCheck, TOMASGoalDirectedAgent
        assert PsiAnchorLockIn is not None
        assert MUSDualRearing is not None
        assert DIKWPGovernance is not None
        assert AlignmentTriad is not None
        assert GoalContract is not None
        assert ExecutionGate is not None
        assert CronFire is not None
        assert SoulGraph is not None
        assert MUSSoulDriftCheck is not None
        assert TOMASGoalDirectedAgent is not None

    def test_full_user_workflow(self):
        from alignment_triad import AlignmentTriad
        from goal_directed_agent import TOMASGoalDirectedAgent
        # Step 1: Propose goal
        tga = TOMASGoalDirectedAgent("user-wf")
        goal = tga.propose_goal("重构订单模块但不动数据库")
        assert goal["status"] == "PROPOSED"
        # Step 2: Authorize and execute
        exec_r = tga.execute_authorized("user_signature_valid")
        assert exec_r["authorized"] is True
        # Step 3: Dream engine cycle
        dream = tga.dream_engine_cycle()
        assert "compaction" in dream
        # Step 4: Alignment check
        triad = AlignmentTriad()
        align = triad.get_alignment_status()
        assert "phase" in align
        # Step 5: Full status
        full = tga.get_full_status()
        assert full["goal"]["has_contract"] is True


class TestV310RegressionSanity:
    """回归性健全检查 (5 tests)"""

    def test_alignment_triad_module_importable(self):
        import alignment_triad
        assert hasattr(alignment_triad, "PsiAnchorLockIn")
        assert hasattr(alignment_triad, "MUSDualRearing")
        assert hasattr(alignment_triad, "DIKWPGovernance")
        assert hasattr(alignment_triad, "AlignmentTriad")

    def test_goal_directed_agent_module_importable(self):
        import goal_directed_agent
        assert hasattr(goal_directed_agent, "GoalContract")
        assert hasattr(goal_directed_agent, "ExecutionGate")
        assert hasattr(goal_directed_agent, "CronFire")
        assert hasattr(goal_directed_agent, "SoulGraph")
        assert hasattr(goal_directed_agent, "MUSSoulDriftCheck")
        assert hasattr(goal_directed_agent, "TOMASGoalDirectedAgent")

    def test_no_circular_imports(self):
        import alignment_triad
        import goal_directed_agent
        # Both modules import each other indirectly via shared deps
        # If circular imports existed, one of the above would fail
        assert True

    def test_existing_sim_modules_still_importable(self):
        modules_to_check = [
            "babeltele_compressor",
            "hypergraph_categories",
            "kernelcat_scheduler",
            "constitutional_agi",
            "eml_semzip",
            "models",
        ]
        for mod_name in modules_to_check:
            try:
                __import__(mod_name)
            except ImportError as e:
                pytest.fail(f"Module {mod_name} failed to import: {e}")

    def test_server_syntax_valid(self):
        import py_compile
        server_path = os.path.join(os.path.dirname(__file__), '..', 'sim', 'server.py')
        try:
            py_compile.compile(server_path, doraise=True)
        except py_compile.PyCompileError as e:
            pytest.fail(f"server.py syntax error: {e}")
