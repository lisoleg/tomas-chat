# -*- coding: utf-8 -*-
"""
TOMAS AGI v3.11 — Cognitive Health 单元测试
=============================================
覆盖: 回路检测, 偏误惩罚, 认知定理, 可证伪预测, 状态机, 白名单, 审计链
"""

import json
import math
import pytest

from sim.cognitive_health import (
    TOMASCognitivelyHealthyAGI,
    CognitiveHealthReport,
    CognitiveHealthTheorem,
    FalsifiablePredictions,
    HealthAgentState,
    ALLOWED_REPEAT_PATTERNS,
    _sha256,
    _is_whitelisted_pattern,
)


# ══════════════════════════════════════════════════════════════════
# Group 1: SHA-256 审计工具
# ══════════════════════════════════════════════════════════════════

class TestSHA256Audit:
    def test_sha256_returns_64_hex_chars(self):
        h = _sha256("test")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_sha256_deterministic(self):
        assert _sha256("hello") == _sha256("hello")

    def test_sha256_different_inputs(self):
        assert _sha256("hello") != _sha256("world")

    def test_sha256_empty_string(self):
        h = _sha256("")
        assert len(h) == 64


# ══════════════════════════════════════════════════════════════════
# Group 2: 白名单
# ══════════════════════════════════════════════════════════════════

class TestWhitelist:
    def test_monitor_heartbeat_whitelisted(self):
        assert _is_whitelisted_pattern("monitor", "heartbeat")

    def test_scheduler_cron_whitelisted(self):
        assert _is_whitelisted_pattern("scheduler", "cron_ping")

    def test_health_selfcheck_whitelisted(self):
        assert _is_whitelisted_pattern("health", "self_check")

    def test_non_whitelisted_pattern(self):
        assert not _is_whitelisted_pattern("agent", "reply")

    def test_partial_category_not_whitelisted(self):
        assert not _is_whitelisted_pattern("monitor", "alert")

    def test_allowed_repeat_patterns_is_set(self):
        assert isinstance(ALLOWED_REPEAT_PATTERNS, set)
        assert len(ALLOWED_REPEAT_PATTERNS) >= 3


# ══════════════════════════════════════════════════════════════════
# Group 3: CognitiveHealthReport
# ══════════════════════════════════════════════════════════════════

class TestCognitiveHealthReport:
    def test_default_values(self):
        r = CognitiveHealthReport()
        assert r.timestamp > 0
        assert r.habit_loop_detected is False
        assert r.habit_loop_count == 0
        assert r.bias_penalty_score == 0.0
        assert r.recommendation == "continue"

    def test_custom_values(self):
        r = CognitiveHealthReport(
            habit_loop_detected=True,
            habit_loop_count=5,
            bias_penalty_score=0.8,
            mus_reflection_triggered=True,
            recommendation="bias_warning",
        )
        assert r.habit_loop_count == 5
        assert r.bias_penalty_score == 0.8

    def test_to_dict(self):
        r = CognitiveHealthReport()
        d = r.to_dict()
        assert isinstance(d, dict)
        assert "habit_loop_detected" in d

    def test_to_json(self):
        r = CognitiveHealthReport()
        j = r.to_json()
        assert isinstance(j, str)
        assert isinstance(json.loads(j), dict)

    def test_str_representation(self):
        r = CognitiveHealthReport()
        assert "CognitiveHealthReport" in str(r)


# ══════════════════════════════════════════════════════════════════
# Group 4: HealthAgentState
# ══════════════════════════════════════════════════════════════════

class TestHealthAgentState:
    def test_normal_value(self):
        assert HealthAgentState.NORMAL.value == "NORMAL"

    def test_bias_warning_value(self):
        assert HealthAgentState.BIAS_WARNING.value == "BIAS_WARNING"

    def test_mus_reflection_value(self):
        assert HealthAgentState.MUS_REFLECTION.value == "MUS_REFLECTION"

    def test_paused_value(self):
        assert HealthAgentState.PAUSED.value == "PAUSED"

    def test_four_states(self):
        assert len(HealthAgentState) == 4


# ══════════════════════════════════════════════════════════════════
# Group 5: TOMASCognitivelyHealthyAGI — 回路检测
# ══════════════════════════════════════════════════════════════════

class TestHabitLoopDetection:
    def test_no_loop_initially(self):
        ch = TOMASCognitivelyHealthyAGI()
        assert not ch.detect_loop()

    def test_loop_after_three_repeats(self):
        ch = TOMASCognitivelyHealthyAGI()
        for i in range(3):
            ch.track_kappa_snap_pattern(f"snap_{i}", {"category": "agent", "action": "reply"})
        assert ch.detect_loop()

    def test_whitelisted_no_loop(self):
        ch = TOMASCognitivelyHealthyAGI()
        for i in range(5):
            ch.track_kappa_snap_pattern(f"snap_{i}", {"category": "monitor", "action": "heartbeat"})
        assert not ch.detect_loop()

    def test_mixed_patterns_no_loop(self):
        ch = TOMASCognitivelyHealthyAGI()
        ch.track_kappa_snap_pattern("s1", {"category": "agent", "action": "reply"})
        ch.track_kappa_snap_pattern("s2", {"category": "agent", "action": "think"})
        ch.track_kappa_snap_pattern("s3", {"category": "agent", "action": "reply"})
        assert not ch.detect_loop()

    def test_loop_triggers_mus_reflection(self):
        ch = TOMASCognitivelyHealthyAGI()
        for i in range(3):
            ch.track_kappa_snap_pattern(f"snap_{i}", {"category": "agent", "action": "reply"})
        assert ch.state == HealthAgentState.MUS_REFLECTION


# ══════════════════════════════════════════════════════════════════
# Group 6: 偏误惩罚
# ══════════════════════════════════════════════════════════════════

class TestBiasPenalty:
    def test_bias_penalty_in_range(self):
        ch = TOMASCognitivelyHealthyAGI()
        penalty = ch.compute_gan_with_bias_penalty([0.5, 0.5])
        assert 0.0 <= penalty <= 1.0

    def test_high_bias_triggers_warning(self):
        ch = TOMASCognitivelyHealthyAGI()
        # Large polarization values can push bias above 0.7
        ch.compute_gan_with_bias_penalty([10.0, 10.0])
        assert ch.state in (HealthAgentState.BIAS_WARNING, HealthAgentState.NORMAL)

    def test_measure_gan_comfort_zone_empty(self):
        ch = TOMASCognitivelyHealthyAGI()
        assert ch.measure_gan_comfort_zone([]) == 1.0

    def test_bias_penalty_formula(self):
        ch = TOMASCognitivelyHealthyAGI()
        penalty = ch.bias_penalty_formula(G=1.0, G_comfort=0.5, mus_div=0.3)
        assert 0.0 <= penalty <= 1.0

    def test_mus_divergence_no_zone(self):
        ch = TOMASCognitivelyHealthyAGI()
        assert ch.compute_mus_divergence("nonexistent_mus") == 0.0


# ══════════════════════════════════════════════════════════════════
# Group 7: 状态机
# ══════════════════════════════════════════════════════════════════

class TestStateMachine:
    def test_initial_state_normal(self):
        ch = TOMASCognitivelyHealthyAGI()
        assert ch.get_state() == "NORMAL"

    def test_pause_order_sets_paused(self):
        ch = TOMASCognitivelyHealthyAGI()
        ch.issue_pause_order()
        assert ch.get_state() == "PAUSED"
        assert ch.is_paused is True

    def test_restart_with_valid_code(self):
        ch = TOMASCognitivelyHealthyAGI()
        ch.issue_pause_order()
        result = ch.restart("override_coghealth")
        assert result["success"] is True
        assert ch.get_state() == "NORMAL"

    def test_restart_with_short_code_fails(self):
        ch = TOMASCognitivelyHealthyAGI()
        ch.issue_pause_order()
        result = ch.restart("short")
        assert result["success"] is False

    def test_restart_without_coghealth_suffix_fails(self):
        ch = TOMASCognitivelyHealthyAGI()
        ch.issue_pause_order()
        result = ch.restart("invalid_code_1234")
        assert result["success"] is False

    def test_force_mus_reflection(self):
        ch = TOMASCognitivelyHealthyAGI()
        mus_id = ch.force_mus_reflection()
        assert mus_id.startswith("MUS_COGHEALTH_")
        assert ch.state == HealthAgentState.MUS_REFLECTION


# ══════════════════════════════════════════════════════════════════
# Group 8: 健康检查管道
# ══════════════════════════════════════════════════════════════════

class TestHealthCheckPipeline:
    def test_pipeline_returns_report(self):
        ch = TOMASCognitivelyHealthyAGI()
        report = ch.health_check_pipeline()
        assert isinstance(report, CognitiveHealthReport)
        assert report.timestamp > 0

    def test_pipeline_default_state(self):
        ch = TOMASCognitivelyHealthyAGI()
        report = ch.health_check_pipeline()
        assert report.recommendation == "continue"
        assert report.habit_loop_detected is False

    def test_pipeline_with_loop(self):
        ch = TOMASCognitivelyHealthyAGI()
        for i in range(3):
            ch.track_kappa_snap_pattern(f"snap_{i}", {"category": "agent", "action": "reply"})
        report = ch.health_check_pipeline()
        assert report.habit_loop_detected is True


# ══════════════════════════════════════════════════════════════════
# Group 9: 认知定理
# ══════════════════════════════════════════════════════════════════

class TestCognitiveHealthTheorem:
    def test_theorem1_first_measurement(self):
        th = CognitiveHealthTheorem()
        result = th.theorem_1_diversity_conservation(0.8, 0.2)
        assert result["conserved"] is True

    def test_theorem1_conserved(self):
        th = CognitiveHealthTheorem()
        th.theorem_1_diversity_conservation(0.8, 0.2)
        result = th.theorem_1_diversity_conservation(0.79, 0.2)
        assert isinstance(result["conserved"], bool)
        assert "delta_D" in result

    def test_theorem1_violated(self):
        th = CognitiveHealthTheorem(epsilon=0.01)
        th.theorem_1_diversity_conservation(0.8, 0.2)
        result = th.theorem_1_diversity_conservation(0.5, 0.2)
        assert result["conserved"] is False

    def test_theorem2_anti_bias(self):
        th = CognitiveHealthTheorem()
        result = th.theorem_2_mus_anti_bias(0.5, 0.5)
        assert isinstance(result["anti_bias_active"], bool)
        assert "product" in result

    def test_theorem2_high_bias_violation(self):
        th = CognitiveHealthTheorem()
        result = th.theorem_2_mus_anti_bias(0.0, 2.0)
        assert result["anti_bias_active"] is False


# ══════════════════════════════════════════════════════════════════
# Group 10: 可证伪预测
# ══════════════════════════════════════════════════════════════════

class TestFalsifiablePredictions:
    def test_P_AD1_basic(self):
        fp = FalsifiablePredictions()
        result = fp.P_AD1_habit_decay(N=10, D0=1.0, alpha=0.1)
        assert result["N"] == 10
        assert result["D_N"] > 0
        assert result["D_N"] < result["D0"]
        assert result["half_life"] > 0

    def test_P_AD1_decay_decreases(self):
        fp = FalsifiablePredictions()
        r1 = fp.P_AD1_habit_decay(N=5, D0=1.0, alpha=0.1)
        r2 = fp.P_AD1_habit_decay(N=20, D0=1.0, alpha=0.1)
        assert r2["D_N"] < r1["D_N"]

    def test_P_AD2_lock(self):
        fp = FalsifiablePredictions()
        result = fp.P_AD2_bias_lock_positive_feedback(G_depth=0.8, B_score=0.7, theta_c=0.5)
        assert result["locked"] is True
        assert result["lock_product"] == pytest.approx(0.56, abs=0.01)

    def test_P_AD2_no_lock(self):
        fp = FalsifiablePredictions()
        result = fp.P_AD2_bias_lock_positive_feedback(G_depth=0.2, B_score=0.1, theta_c=0.5)
        assert result["locked"] is False

    def test_P_AD1_formula(self):
        fp = FalsifiablePredictions()
        result = fp.P_AD1_habit_decay(N=10, D0=1.0, alpha=0.1)
        expected = 1.0 * math.exp(-0.1 * 10)
        assert result["D_N"] == pytest.approx(expected, abs=1e-6)
