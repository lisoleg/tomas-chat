# -*- coding: utf-8 -*-
"""
Tests for ARC-AGI-3 evaluation module.

Covers:
- RHAE scoring formula (level, environment, total)
- Environment simulator (reset, step, win conditions)
- Action parsing
- Demo environment generation
- Evaluator dry run
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add sim directory to path
sim_path = Path(__file__).parent.parent / "sim"
sys.path.insert(0, str(sim_path))

from arc_agi3_eval import (
    ARCAgi3Environment,
    ARCAGI3Evaluator,
    ActionType,
    Frame,
    GRID_SIZE,
    RHAEscorer,
    SCORE_CAP,
    SYSTEM_PROMPT,
    generate_demo_environments,
)


# ============================================================
# RHAE Scorer Tests
# ============================================================

class TestRHAEscorer:
    """Test the RHAE scoring formula."""

    def test_level_score_perfect(self):
        """AI matches human baseline → score = 1.0"""
        score = RHAEscorer.level_score(human_baseline=10, ai_actions=10)
        assert score == pytest.approx(1.0)

    def test_level_score_better_than_human(self):
        """AI beats human → score capped at 1.15"""
        score = RHAEscorer.level_score(human_baseline=20, ai_actions=10)
        assert score == SCORE_CAP  # (20/10)^2 = 4.0, capped to 1.15

    def test_level_score_worse_than_human(self):
        """AI takes 10x more actions → score = 0.01"""
        score = RHAEscorer.level_score(human_baseline=10, ai_actions=100)
        assert score == pytest.approx(0.01, rel=0.01)

    def test_level_score_zero_actions(self):
        """Zero actions → score = 0"""
        score = RHAEscorer.level_score(human_baseline=10, ai_actions=0)
        assert score == 0.0

    def test_level_score_double_actions(self):
        """AI takes 2x actions → score = 0.25"""
        score = RHAEscorer.level_score(human_baseline=10, ai_actions=20)
        assert score == pytest.approx(0.25)

    def test_environment_score_all_completed(self):
        """All 5 levels completed → cap = 1.0"""
        level_scores = [(1, 1.0), (2, 0.8), (3, 0.9), (4, 0.7), (5, 0.85)]
        result = RHAEscorer.environment_score(level_scores, total_levels=5, completed_levels=5)
        assert result.environment_cap == 1.0
        # Weighted avg = (1*1.0 + 2*0.8 + 3*0.9 + 4*0.7 + 5*0.85) / 15
        expected = (1.0 + 1.6 + 2.7 + 2.8 + 4.25) / 15
        assert result.environment_score == pytest.approx(min(1.0, expected))

    def test_environment_score_partial_completion(self):
        """3/5 levels completed → cap = 6/15 = 0.4"""
        level_scores = [(1, 1.0), (2, 0.8), (3, 0.9)]
        result = RHAEscorer.environment_score(level_scores, total_levels=5, completed_levels=3)
        assert result.environment_cap == pytest.approx(6.0 / 15.0)
        # Score should be capped at 0.4
        assert result.environment_score <= 0.4 + 1e-6

    def test_environment_score_none_completed(self):
        """0 levels completed → score = 0"""
        level_scores = []
        result = RHAEscorer.environment_score(level_scores, total_levels=5, completed_levels=0)
        assert result.environment_score == 0.0
        assert result.environment_cap == 0.0

    def test_total_score(self):
        """Mean of environment scores"""
        scores = [0.5, 0.3, 0.8]
        total = RHAEscorer.total_score(scores)
        assert total == pytest.approx(0.5333, rel=0.01)

    def test_total_score_empty(self):
        """Empty list → 0"""
        assert RHAEscorer.total_score([]) == 0.0


# ============================================================
# Environment Simulator Tests
# ============================================================

class TestARCAgi3Environment:
    """Test the environment simulator."""

    @pytest.fixture
    def simple_env(self):
        """Create a simple environment with 2 levels."""
        return ARCAgi3Environment("test", [
            {
                "initial_frame": [[0] * GRID_SIZE for _ in range(GRID_SIZE)],
                "win_condition": {"type": "reach_target", "target_pos": (50, 32)},
                "human_baseline": 40,
                "valid_actions": ["key_up", "key_down", "key_left", "key_right"],
            },
            {
                "initial_frame": [[0] * GRID_SIZE for _ in range(GRID_SIZE)],
                "win_condition": {"type": "reach_target", "target_pos": (10, 10)},
                "human_baseline": 50,
                "valid_actions": ["key_up", "key_down", "key_left", "key_right"],
            },
        ])

    def test_reset_returns_frame(self, simple_env):
        """reset() should return a Frame."""
        frame = simple_env.reset(0)
        assert isinstance(frame, Frame)
        assert len(frame.grid) == GRID_SIZE
        assert len(frame.grid[0]) == GRID_SIZE

    def test_step_returns_result(self, simple_env):
        """step() should return an ActionResult."""
        simple_env.reset(0)
        result = simple_env.step("key_right")
        assert hasattr(result, "next_frame")
        assert hasattr(result, "is_win")

    def test_action_history_tracked(self, simple_env):
        """Actions should be tracked in history."""
        simple_env.reset(0)
        simple_env.step("key_up")
        simple_env.step("key_down")
        assert len(simple_env.action_history) == 2

    def test_undo_action(self, simple_env):
        """Undo should not crash."""
        simple_env.reset(0)
        simple_env.step("key_up")
        result = simple_env.step("undo")
        assert hasattr(result, "next_frame")

    def test_invalid_action(self, simple_env):
        """Unknown action should be marked invalid."""
        simple_env.reset(0)
        result = simple_env.step("invalid_action")
        assert result.is_invalid

    def test_out_of_bounds_cell_select(self, simple_env):
        """Out of bounds cell select should be invalid."""
        simple_env.reset(0)
        result = simple_env.step("cell_select", {"x": 100, "y": 100})
        assert result.is_invalid

    def test_human_baseline(self, simple_env):
        """get_human_baseline should return correct value."""
        assert simple_env.get_human_baseline(0) == 40
        assert simple_env.get_human_baseline(1) == 50

    def test_valid_actions(self, simple_env):
        """get_valid_actions should return action list."""
        actions = simple_env.get_valid_actions(0)
        assert "key_up" in actions

    def test_frame_to_flat_string(self, simple_env):
        """Frame should serialize to compact string."""
        frame = simple_env.reset(0)
        s = frame.to_flat_string()
        assert isinstance(s, str)
        lines = s.strip().split("\n")
        assert len(lines) == GRID_SIZE


# ============================================================
# Demo Environment Tests
# ============================================================

class TestDemoEnvironments:
    """Test demo environment generation."""

    def test_generate_demo_envs(self):
        """Should generate 3 demo environments."""
        envs = generate_demo_environments()
        assert len(envs) == 3

    def test_demo_env_ids(self):
        """Demo environments should have 4-char IDs."""
        envs = generate_demo_environments()
        for env in envs:
            assert len(env["env_id"]) == 4

    def test_demo_env_has_levels(self):
        """Each demo environment should have at least 1 level."""
        envs = generate_demo_environments()
        for env in envs:
            assert len(env["levels"]) >= 1

    def test_demo_env_grid_size(self):
        """All grids should be 64x64."""
        envs = generate_demo_environments()
        for env in envs:
            for level in env["levels"]:
                grid = level["initial_frame"]
                assert len(grid) == GRID_SIZE
                assert len(grid[0]) == GRID_SIZE

    def test_demo_env_human_baseline(self):
        """All levels should have human baseline."""
        envs = generate_demo_environments()
        for env in envs:
            for level in env["levels"]:
                assert "human_baseline" in level
                assert level["human_baseline"] > 0


# ============================================================
# Evaluator Tests (dry run)
# ============================================================

class TestARCAGI3Evaluator:
    """Test the evaluator (dry run mode)."""

    def test_evaluator_init(self):
        """Evaluator should initialize correctly."""
        evaluator = ARCAGI3Evaluator(tomas_api_url="http://localhost:99999", verbose=False)
        assert evaluator.tomas_api_url == "http://localhost:99999"
        assert evaluator.action_budget_multiplier == 5

    def test_parse_action_key(self):
        """Should parse key actions."""
        evaluator = ARCAGI3Evaluator(verbose=False)
        action, params = evaluator._parse_action("I'll move up with key_up", ["key_up", "key_down"])
        assert action == "key_up"
        assert params is None

    def test_parse_action_cell_select(self):
        """Should parse cell_select with coordinates."""
        evaluator = ARCAGI3Evaluator(verbose=False)
        action, params = evaluator._parse_action(
            "I'll click cell_select 10 20",
            ["key_up", "cell_select"],
        )
        assert action == "cell_select"
        assert params is not None
        assert params["x"] == 10
        assert params["y"] == 20

    def test_parse_action_fallback(self):
        """Should fallback to first valid action if no match."""
        evaluator = ARCAGI3Evaluator(verbose=False)
        action, _ = evaluator._parse_action("do something random", ["key_up"])
        assert action == "key_up"

    def test_dry_run_evaluation(self):
        """Dry run should complete without errors."""
        envs = generate_demo_environments()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"environments": envs}, f)
            dataset_path = f.name

        try:
            evaluator = ARCAGI3Evaluator(
                tomas_api_url="http://localhost:99999",  # Will trigger fallback
                verbose=False,
            )
            report = evaluator.evaluate_dataset(dataset_path, max_envs=1)

            assert "total_score" in report
            assert "environments_evaluated" in report
            assert report["environments_evaluated"] == 1
            assert len(report["detailed_results"]) == 1
        finally:
            os.unlink(dataset_path)


# ============================================================
# Constants Tests
# ============================================================

class TestConstants:
    """Test module constants."""

    def test_grid_size(self):
        assert GRID_SIZE == 64

    def test_num_colors(self):
        from arc_agi3_eval import NUM_COLORS
        assert NUM_COLORS == 16

    def test_score_cap(self):
        assert SCORE_CAP == 1.15

    def test_system_prompt(self):
        assert "You are playing a game" in SYSTEM_PROMPT
        assert "goal is to win" in SYSTEM_PROMPT

    def test_action_types(self):
        assert ActionType.KEY_UP.value == "key_up"
        assert ActionType.CELL_SELECT.value == "cell_select"
        assert ActionType.UNDO.value == "undo"
