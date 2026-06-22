# -*- coding: utf-8 -*-
"""
TOMAS AGI v3.11 — Cognitive Health 与 AlignmentTriad 集成测试
=============================================================
覆盖: AlignmentTriad.cognitive_health, run_cognitive_health_check,
      process_output 中的 cognitive_health 集成
"""

import pytest

from sim.alignment_triad import AlignmentTriad
from sim.cognitive_health import (
    TOMASCognitivelyHealthyAGI,
    HealthAgentState,
)


# ══════════════════════════════════════════════════════════════════
# Group 1: AlignmentTriad 认知健康模块初始化
# ══════════════════════════════════════════════════════════════════

class TestAlignmentTriadCognitiveHealthInit:
    def test_triad_has_cognitive_health(self):
        triad = AlignmentTriad()
        assert triad.cognitive_health is not None

    def test_cognitive_health_is_correct_type(self):
        triad = AlignmentTriad()
        assert isinstance(triad.cognitive_health, TOMASCognitivelyHealthyAGI)

    def test_cognitive_health_initial_state_normal(self):
        triad = AlignmentTriad()
        assert triad.cognitive_health.get_state() == "NORMAL"


# ══════════════════════════════════════════════════════════════════
# Group 2: run_cognitive_health_check 方法
# ══════════════════════════════════════════════════════════════════

class TestRunCognitiveHealthCheck:
    def test_returns_state(self):
        triad = AlignmentTriad()
        result = triad.run_cognitive_health_check()
        assert "state" in result

    def test_returns_habit_loop_detected(self):
        triad = AlignmentTriad()
        result = triad.run_cognitive_health_check()
        assert "habit_loop_detected" in result

    def test_returns_bias_penalty_score(self):
        triad = AlignmentTriad()
        result = triad.run_cognitive_health_check()
        assert "bias_penalty_score" in result

    def test_default_state_normal(self):
        triad = AlignmentTriad()
        result = triad.run_cognitive_health_check()
        assert result["state"] == "NORMAL"


# ══════════════════════════════════════════════════════════════════
# Group 3: process_output 集成
# ══════════════════════════════════════════════════════════════════

class TestProcessOutputIntegration:
    def test_process_output_has_cognitive_health(self):
        triad = AlignmentTriad()
        result = triad.process_output("agent1", "安全合规输出")
        assert "cognitive_health" in result

    def test_cognitive_health_in_result_has_state(self):
        triad = AlignmentTriad()
        result = triad.process_output("agent1", "安全合规输出")
        ch = result["cognitive_health"]
        assert "state" in ch

    def test_cognitive_health_in_result_has_bias(self):
        triad = AlignmentTriad()
        result = triad.process_output("agent1", "安全合规输出")
        ch = result["cognitive_health"]
        assert "bias_penalty_score" in ch


# ══════════════════════════════════════════════════════════════════
# Group 4: get_alignment_status 集成
# ══════════════════════════════════════════════════════════════════

class TestAlignmentStatusIntegration:
    def test_status_has_cognitive_health(self):
        triad = AlignmentTriad()
        status = triad.get_alignment_status()
        assert "[v3.11] cognitive_health" in status

    def test_status_cognitive_health_available(self):
        triad = AlignmentTriad()
        status = triad.get_alignment_status()
        ch = status["[v3.11] cognitive_health"]
        assert ch["available"] is True

    def test_status_cognitive_health_has_state(self):
        triad = AlignmentTriad()
        status = triad.get_alignment_status()
        ch = status["[v3.11] cognitive_health"]
        assert "state" in ch


# ══════════════════════════════════════════════════════════════════
# Group 5: 回路检测与偏误集成
# ══════════════════════════════════════════════════════════════════

class TestLoopDetectionIntegration:
    def test_loop_detection_in_triad(self):
        triad = AlignmentTriad()
        for i in range(5):
            triad.cognitive_health.track_kappa_snap_pattern(
                f"snap-{i}", {"category": "agent", "action": "reply"}
            )
        report = triad.cognitive_health.health_check_pipeline()
        assert report.habit_loop_detected is True

    def test_bias_penalty_in_triad(self):
        triad = AlignmentTriad()
        triad.cognitive_health.restart("test_override_coghealth")
        bias = triad.cognitive_health.compute_gan_with_bias_penalty([0.95, 0.05])
        assert 0.0 <= bias <= 1.0
