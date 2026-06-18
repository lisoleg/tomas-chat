# -*- coding: utf-8 -*-
"""
ARC-AGI-3 Evaluation Module for TOMAS
======================================

Based on: "ARC-AGI-3: A New Challenge for Frontier Agentic Intelligence"
          ARC Prize Foundation, April 20, 2026

Core Concepts:
    1. Interactive turn-based environments (64x64 grid, 16 colors)
    2. Four pillars of agentic intelligence:
       - Exploration: actively obtain information by interacting
       - Modeling: build generalizable world model from observations
       - Goal-Setting: infer win conditions without instructions
       - Planning & Execution: map action path to identified goal
    3. RHAE (Relative Human Action Efficiency) scoring:
       - Level Score: S = min(1.15, (h/a)^2)  where h=human baseline, a=AI actions
       - Environment Score: weighted average with linear level weights
       - Total Score: mean of all environment scores
    4. Action space: 5 keys + Undo + cell_select(x,y)
    5. Action budget: 5x human baseline median

System Prompt (official):
    "You are playing a game. Your goal is to win. Reply with the exact
     action you want to take. The final action in your reply will be
     executed next turn. Your entire reply will be carried to the next turn."

Author: TOMAS Team
Version: v1.0
"""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass, field as dc_field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ============================================================
# Constants
# ============================================================

GRID_SIZE = 64
NUM_COLORS = 16
SYSTEM_PROMPT = (
    "You are playing a game. Your goal is to win. "
    "Reply with the exact action you want to take. "
    "The final action in your reply will be executed next turn. "
    "Your entire reply will be carried to the next turn."
)
MAX_LEVELS_PER_ENV = 5  # Standard: 5 levels per environment
ACTION_BUDGET_MULTIPLIER = 5  # 5x human baseline
SCORE_CAP = 1.15  # Maximum per-level score


class ActionType(Enum):
    """ARC-AGI-3 action types."""
    KEY_UP = "key_up"
    KEY_DOWN = "key_down"
    KEY_LEFT = "key_left"
    KEY_RIGHT = "key_right"
    KEY_SPACE = "key_space"
    UNDO = "undo"
    CELL_SELECT = "cell_select"  # Requires (x, y) coordinates


# ============================================================
# Data Structures
# ============================================================

@dataclass
class Frame:
    """A single 64x64 grid frame."""
    grid: List[List[int]]  # 64x64 grid, values 0-15

    def to_dict(self) -> Dict:
        return {"grid": self.grid, "size": GRID_SIZE}

    def to_flat_string(self) -> str:
        """Flatten grid to compact string for LLM context."""
        rows = []
        for row in self.grid:
            rows.append("".join(hex(c)[2:] for c in row))
        return "\n".join(rows)


@dataclass
class ActionResult:
    """Result of executing an action."""
    next_frame: Frame
    is_win: bool = False
    is_level_complete: bool = False
    is_env_complete: bool = False
    is_invalid: bool = False
    metadata: Dict = dc_field(default_factory=dict)


@dataclass
class LevelResult:
    """Result of completing (or failing) a single level."""
    level_id: int
    actions_taken: int
    completed: bool
    action_history: List[str] = dc_field(default_factory=list)
    time_seconds: float = 0.0


@dataclass
class EnvironmentResult:
    """Result of evaluating one environment."""
    env_id: str
    levels: List[LevelResult] = dc_field(default_factory=list)
    total_actions: int = 0
    time_seconds: float = 0.0


@dataclass
class RHAEScore:
    """RHAE score breakdown."""
    level_scores: List[Tuple[int, float]] = dc_field(default_factory=list)  # (level_id, score)
    environment_score: float = 0.0
    environment_cap: float = 0.0
    details: Dict = dc_field(default_factory=dict)


# ============================================================
# ARC-AGI-3 Environment Simulator
# ============================================================

class ARCAgi3Environment:
    """
    Simulates an ARC-AGI-3 turn-based environment.

    Each environment has multiple levels. The agent interacts with
    the environment by submitting actions, and receives frames in return.
    The agent must infer the win condition without explicit instructions.
    """

    def __init__(self, env_id: str, levels: List[Dict]):
        """
        Args:
            env_id: Unique 4-character environment ID
            levels: List of level definitions, each containing:
                - 'initial_frame': 64x64 grid
                - 'win_condition': dict describing how to win
                - 'human_baseline': int, human action count
                - 'valid_actions': list of ActionType strings
        """
        self.env_id = env_id
        self.levels = levels
        self.current_level_idx = 0
        self.current_frame: Optional[Frame] = None
        self.action_history: List[str] = []
        self._level_state: Dict = {}

    def reset(self, level_idx: int = 0) -> Frame:
        """Reset to specified level (default: first level)."""
        self.current_level_idx = level_idx
        level = self.levels[level_idx]
        self.current_frame = Frame(grid=[row[:] for row in level["initial_frame"]])
        self.action_history = []
        self._level_state = {"explored_cells": set(), "key_presses": 0}
        return self.current_frame

    def step(self, action: str, params: Optional[Dict] = None) -> ActionResult:
        """
        Execute one action in the environment.

        Args:
            action: Action string (e.g. "key_up", "cell_select")
            params: Additional parameters (e.g. {"x": 10, "y": 20} for cell_select)

        Returns:
            ActionResult with next frame and status flags
        """
        if self.current_frame is None:
            raise RuntimeError("Environment not initialized. Call reset() first.")

        self.action_history.append(action)
        level = self.levels[self.current_level_idx]

        # Process action
        new_grid = [row[:] for row in self.current_frame.grid]

        if action == "undo":
            if len(self.action_history) > 1:
                self.action_history.pop()  # Remove the undo itself
                self.action_history.pop()  # Remove the last action
                # Replay from start (simplified: just go back to initial + replay)
                new_grid = [row[:] for row in level["initial_frame"]]
                for a in self.action_history:
                    new_grid = self._apply_action_to_grid(new_grid, a, level)
            return ActionResult(next_frame=Frame(grid=new_grid), is_invalid=False)

        elif action.startswith("key_"):
            self._level_state["key_presses"] += 1
            new_grid = self._apply_action_to_grid(new_grid, action, level)

        elif action == "cell_select" and params:
            x, y = params.get("x", 0), params.get("y", 0)
            if 0 <= x < GRID_SIZE and 0 <= y < GRID_SIZE:
                self._level_state["explored_cells"].add((x, y))
                new_grid = self._apply_cell_select(new_grid, x, y, level)
            else:
                return ActionResult(
                    next_frame=Frame(grid=new_grid),
                    is_invalid=True,
                    metadata={"reason": "out_of_bounds"},
                )
        else:
            return ActionResult(
                next_frame=Frame(grid=new_grid),
                is_invalid=True,
                metadata={"reason": f"unknown_action: {action}"},
            )

        self.current_frame = Frame(grid=new_grid)

        # Check win condition
        is_win = self._check_win_condition(new_grid, level)

        is_level_complete = is_win
        is_env_complete = is_win and self.current_level_idx >= len(self.levels) - 1

        return ActionResult(
            next_frame=self.current_frame,
            is_win=is_win,
            is_level_complete=is_level_complete,
            is_env_complete=is_env_complete,
        )

    def _apply_action_to_grid(
        self, grid: List[List[int]], action: str, level: Dict
    ) -> List[List[int]]:
        """Apply a key action to the grid (environment-specific logic)."""
        # Generic movement: find agent position (color 1 = agent) and move
        agent_pos = None
        for y in range(GRID_SIZE):
            for x in range(GRID_SIZE):
                if grid[y][x] == 1:
                    agent_pos = (x, y)
                    break
            if agent_pos:
                break

        if not agent_pos:
            return grid

        x, y = agent_pos
        dx, dy = 0, 0
        if action == "key_up":
            dy = -1
        elif action == "key_down":
            dy = 1
        elif action == "key_left":
            dx = -1
        elif action == "key_right":
            dx = 1
        elif action == "key_space":
            # Space: context-dependent (e.g., interact, jump)
            pass

        if dx != 0 or dy != 0:
            nx, ny = x + dx, y + dy
            if 0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE:
                target = grid[ny][nx]
                # 0 = empty (passable), 2 = wall (impassable)
                if target != 2:
                    grid[y][x] = 0  # Clear old position
                    grid[ny][nx] = 1  # Move agent

        return grid

    def _apply_cell_select(
        self, grid: List[List[int]], x: int, y: int, level: Dict
    ) -> List[List[int]]:
        """Apply cell selection to the grid."""
        # Toggle or activate a cell (environment-specific)
        cell_value = grid[y][x]
        # Simple toggle: cycle through states
        if cell_value == 0:
            grid[y][x] = 3  # Mark as selected
        elif cell_value == 3:
            grid[y][x] = 0  # Deselect
        return grid

    def _check_win_condition(self, grid: List[List[int]], level: Dict) -> bool:
        """Check if the current grid state satisfies the win condition."""
        win_cond = level.get("win_condition", {})
        cond_type = win_cond.get("type", "reach_target")

        if cond_type == "reach_target":
            # Agent (color 1) must reach target cell (color 4)
            target_pos = win_cond.get("target_pos")
            if target_pos:
                tx, ty = target_pos
                return grid[ty][tx] == 1  # Agent is on target

        elif cond_type == "collect_all":
            # All items (color 5) must be collected
            for y in range(GRID_SIZE):
                for x in range(GRID_SIZE):
                    if grid[y][x] == 5:
                        return False
            return True

        elif cond_type == "reach_exit":
            # Agent must reach exit (color 6)
            for y in range(GRID_SIZE):
                for x in range(GRID_SIZE):
                    if grid[y][x] == 6 and grid[y][x] == 1:
                        return True
            # Check if agent is adjacent to exit
            for y in range(GRID_SIZE):
                for x in range(GRID_SIZE):
                    if grid[y][x] == 6:
                        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                            nx, ny = x + dx, y + dy
                            if 0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE:
                                if grid[ny][nx] == 1:
                                    return True
            return False

        elif cond_type == "pattern_match":
            # Grid must match a target pattern
            target = win_cond.get("target_grid")
            if target:
                return grid == target

        elif cond_type == "custom":
            # Custom win condition function
            check_fn = level.get("win_check_fn")
            if check_fn:
                return check_fn(grid)

        return False

    def get_human_baseline(self, level_idx: int) -> int:
        """Get human baseline action count for a level."""
        return self.levels[level_idx].get("human_baseline", 50)

    def get_valid_actions(self, level_idx: int) -> List[str]:
        """Get valid actions for a level."""
        return self.levels[level_idx].get(
            "valid_actions",
            ["key_up", "key_down", "key_left", "key_right", "key_space", "undo", "cell_select"],
        )


# ============================================================
# RHAE Scorer
# ============================================================

class RHAEscorer:
    """
    RHAE (Relative Human Action Efficiency) Scorer.

    Implements the official ARC-AGI-3 scoring methodology:
    - Level Score: S = min(1.15, (h/a)^2)  where h=human baseline, a=AI actions
    - Environment Score: E = min(completion_cap, weighted_average)
    - Total Score: T = mean of all environment scores
    """

    @staticmethod
    def level_score(human_baseline: int, ai_actions: int) -> float:
        """
        Calculate per-level efficiency score.

        S = min(1.15, (h/a)^2)

        Args:
            human_baseline: Human upper-median best action count
            ai_actions: AI agent's action count

        Returns:
            Score between 0 and 1.15
        """
        if ai_actions <= 0:
            return 0.0
        raw = (human_baseline / ai_actions) ** 2
        return min(SCORE_CAP, raw)

    @staticmethod
    def environment_score(
        level_scores: List[Tuple[int, float]],
        total_levels: int,
        completed_levels: int,
    ) -> RHAEScore:
        """
        Calculate per-environment score with weighted levels and completion cap.

        E = min(completion_cap, weighted_average)

        Level weights are linear: level l gets weight l (1-indexed).
        completion_cap = sum(weights for completed) / sum(weights for all)

        Args:
            level_scores: List of (level_id, score) tuples
            total_levels: Total number of levels in environment
            completed_levels: Number of levels completed by agent

        Returns:
            RHAEScore with breakdown
        """
        if total_levels == 0:
            return RHAEScore(level_scores=[], environment_score=0.0, environment_cap=0.0)

        # Linear weights: level 1 -> weight 1, level 2 -> weight 2, ...
        weights = [i + 1 for i in range(total_levels)]
        total_weight = sum(weights)

        # Completion cap: weighted fraction of levels completed
        completed_weight = sum(weights[:completed_levels])
        completion_cap = completed_weight / total_weight

        # Weighted average of level scores
        weighted_sum = 0.0
        score_details = []
        for level_id, score in level_scores:
            w = weights[level_id - 1] if level_id <= total_levels else 1
            weighted_sum += w * score
            score_details.append((level_id, score))

        weighted_avg = weighted_sum / total_weight if total_weight > 0 else 0.0

        # Environment score = min(cap, weighted_avg)
        env_score = min(completion_cap, weighted_avg)

        return RHAEScore(
            level_scores=score_details,
            environment_score=env_score,
            environment_cap=completion_cap,
            details={
                "total_levels": total_levels,
                "completed_levels": completed_levels,
                "completion_cap": completion_cap,
                "weighted_avg": weighted_avg,
                "weights": weights,
            },
        )

    @staticmethod
    def total_score(environment_scores: List[float]) -> float:
        """
        Calculate total benchmark score.

        T = mean of all environment scores

        Args:
            environment_scores: List of per-environment scores

        Returns:
            Total score between 0 and 1.0
        """
        if not environment_scores:
            return 0.0
        return sum(environment_scores) / len(environment_scores)


# ============================================================
# ARC-AGI-3 Evaluator (TOMAS Integration)
# ============================================================

class ARCAGI3Evaluator:
    """
    Evaluates a TOMAS agent on ARC-AGI-3 environments.

    The evaluator:
    1. Loads environments from JSON dataset
    2. For each environment, runs the agent through all levels
    3. Counts actions per level
    4. Scores using RHAE methodology
    5. Reports total benchmark score
    """

    def __init__(
        self,
        tomas_api_url: str = "http://localhost:5000",
        action_budget_multiplier: int = ACTION_BUDGET_MULTIPLIER,
        verbose: bool = True,
    ):
        """
        Args:
            tomas_api_url: TOMAS inference API URL
            action_budget_multiplier: Max actions = multiplier * human_baseline
            verbose: Print detailed progress
        """
        self.tomas_api_url = tomas_api_url
        self.action_budget_multiplier = action_budget_multiplier
        self.verbose = verbose
        self.results: List[EnvironmentResult] = []

    def load_dataset(self, dataset_path: str) -> List[Dict]:
        """Load ARC-AGI-3 dataset from JSON file."""
        with open(dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "environments" in data:
            return data["environments"]
        else:
            return [data]

    def evaluate_environment(self, env_def: Dict) -> EnvironmentResult:
        """
        Evaluate the agent on a single environment.

        Args:
            env_def: Environment definition with 'env_id' and 'levels'

        Returns:
            EnvironmentResult with per-level breakdown
        """
        env_id = env_def.get("env_id", "unknown")
        levels = env_def.get("levels", [])

        if self.verbose:
            print(f"\n{'='*60}")
            print(f"Environment: {env_id} ({len(levels)} levels)")
            print(f"{'='*60}")

        env = ARCAgi3Environment(env_id, levels)
        env_result = EnvironmentResult(env_id=env_id)
        env_start_time = time.time()

        for level_idx in range(len(levels)):
            level_start = time.time()
            frame = env.reset(level_idx)
            human_baseline = env.get_human_baseline(level_idx)
            max_actions = human_baseline * self.action_budget_multiplier

            if self.verbose:
                print(f"\n  Level {level_idx + 1}/{len(levels)}")
                print(f"  Human baseline: {human_baseline} actions")
                print(f"  Action budget: {max_actions} actions")

            # Run agent
            actions_taken = 0
            level_completed = False
            action_history = []

            for step in range(max_actions):
                # Get agent's action
                action, params = self._query_agent(
                    env_id, level_idx, frame, action_history, env.get_valid_actions(level_idx)
                )

                if action is None:
                    if self.verbose:
                        print(f"  Step {step}: Agent returned no action")
                    continue

                actions_taken += 1
                action_history.append(action)

                # Execute action
                result = env.step(action, params)

                if self.verbose and step < 5:
                    print(f"  Step {step}: {action} -> win={result.is_win}")

                if result.is_level_complete:
                    level_completed = True
                    if self.verbose:
                        print(f"  ✅ Level {level_idx + 1} completed in {actions_taken} actions")
                    break

                frame = result.next_frame

            if not level_completed and self.verbose:
                print(f"  ❌ Level {level_idx + 1} NOT completed ({actions_taken}/{max_actions} actions)")

            level_result = LevelResult(
                level_id=level_idx + 1,
                actions_taken=actions_taken,
                completed=level_completed,
                action_history=action_history,
                time_seconds=time.time() - level_start,
            )
            env_result.levels.append(level_result)
            env_result.total_actions += actions_taken

            if not level_completed:
                # Can't proceed to next level if current not completed
                break

        env_result.time_seconds = time.time() - env_start_time
        return env_result

    def _query_agent(
        self,
        env_id: str,
        level_idx: int,
        frame: Frame,
        action_history: List[str],
        valid_actions: List[str],
    ) -> Tuple[Optional[str], Optional[Dict]]:
        """
        Query the TOMAS agent for the next action.

        Uses the official ARC-AGI-3 system prompt and sends:
        - Current frame as grid
        - Action history (compressed)
        - Valid actions list

        Returns:
            (action_string, params_dict) or (None, None) if failed
        """
        # Build context for the agent
        frame_str = frame.to_flat_string()
        history_str = ", ".join(action_history[-20:]) if action_history else "(none)"

        user_prompt = (
            f"Environment: {env_id}, Level: {level_idx + 1}\n"
            f"Valid actions: {', '.join(valid_actions)}\n"
            f"Action history (last 20): {history_str}\n"
            f"Current frame (64x64 grid, hex values 0-f):\n{frame_str}\n"
            f"Your action:"
        )

        try:
            import requests

            resp = requests.post(
                f"{self.tomas_api_url}/api/chat",
                json={
                    "message": user_prompt,
                    "system_prompt": SYSTEM_PROMPT,
                    "use_eml": False,  # ARC-AGI-3 doesn't use EML knowledge
                },
                timeout=30,
            )
            data = resp.json()
            raw_response = data.get("response", "")

            # Parse action from response
            action, params = self._parse_action(raw_response, valid_actions)
            return action, params

        except Exception as e:
            logger.warning(f"Agent query failed: {e}")
            # Fallback: random action
            action = random.choice(valid_actions)
            params = None
            if action == "cell_select":
                params = {"x": random.randint(0, GRID_SIZE - 1), "y": random.randint(0, GRID_SIZE - 1)}
            return action, params

    def _parse_action(self, response: str, valid_actions: List[str]) -> Tuple[Optional[str], Optional[Dict]]:
        """
        Parse agent's text response to extract an action.

        Supports formats:
        - "key_up"
        - "cell_select 10 20"
        - "action: key_down"
        - "I'll move up -> key_up"
        """
        response_lower = response.lower().strip()

        # Try to find a valid action in the response
        for action in valid_actions:
            if action in response_lower:
                # Check for cell_select with coordinates
                if action == "cell_select":
                    # Try to extract coordinates
                    import re
                    coords = re.findall(r"cell_select\s+(\d+)\s+(\d+)", response_lower)
                    if coords:
                        x, y = int(coords[0][0]), int(coords[0][1])
                        return action, {"x": x, "y": y}
                    # Default coordinates
                    return action, {"x": 0, "y": 0}
                return action, None

        # No valid action found — return first valid action as fallback
        if valid_actions:
            return valid_actions[0], None
        return None, None

    def evaluate_dataset(self, dataset_path: str, max_envs: int = 0) -> Dict:
        """
        Evaluate the agent on a full ARC-AGI-3 dataset.

        Args:
            dataset_path: Path to JSON dataset file
            max_envs: Maximum number of environments to evaluate (0 = all)

        Returns:
            Full evaluation report with RHAE scores
        """
        environments = self.load_dataset(dataset_path)
        if max_envs > 0:
            environments = environments[:max_envs]

        if self.verbose:
            print(f"\n{'#'*60}")
            print(f"# ARC-AGI-3 Evaluation")
            print(f"# Environments: {len(environments)}")
            print(f"# TOMAS API: {self.tomas_api_url}")
            print(f"{'#'*60}")

        all_env_scores = []
        detailed_results = []

        for env_def in environments:
            env_result = self.evaluate_environment(env_def)
            self.results.append(env_result)

            # Score with RHAE
            level_scores = []
            total_levels = len(env_def.get("levels", []))
            completed = sum(1 for l in env_result.levels if l.completed)

            for lr in env_result.levels:
                env = ARCAgi3Environment(env_result.env_id, env_def.get("levels", []))
                h = env.get_human_baseline(lr.level_id - 1)
                s = RHAEscorer.level_score(h, lr.actions_taken)
                level_scores.append((lr.level_id, s))

            rhae = RHAEscorer.environment_score(level_scores, total_levels, completed)
            all_env_scores.append(rhae.environment_score)

            detailed_results.append({
                "env_id": env_result.env_id,
                "total_actions": env_result.total_actions,
                "levels_completed": completed,
                "total_levels": total_levels,
                "time_seconds": round(env_result.time_seconds, 2),
                "rhae_score": round(rhae.environment_score * 100, 2),
                "level_scores": [(l, round(s * 100, 2)) for l, s in rhae.level_scores],
            })

            if self.verbose:
                print(f"\n  RHAE Score: {rhae.environment_score*100:.2f}%")
                print(f"  Cap: {rhae.environment_cap*100:.2f}%")

        total = RHAEscorer.total_score(all_env_scores)

        report = {
            "total_score": round(total * 100, 2),
            "environments_evaluated": len(environments),
            "detailed_results": detailed_results,
            "system_prompt": SYSTEM_PROMPT,
            "action_budget_multiplier": self.action_budget_multiplier,
        }

        if self.verbose:
            print(f"\n{'#'*60}")
            print(f"# Total RHAE Score: {total*100:.2f}%")
            print(f"# (Frontier AI baseline: < 1%)")
            print(f"{'#'*60}")

        return report


# ============================================================
# Demo Environment Generator (for testing without real dataset)
# ============================================================

def generate_demo_environments() -> List[Dict]:
    """
    Generate minimal demo environments for testing the evaluator.

    These are simplified environments that demonstrate the ARC-AGI-3 format
    without requiring the actual private dataset.
    """
    def make_grid(agent_pos=(32, 32), target_pos=None, walls=None):
        """Create a 64x64 grid with agent and optional target/walls."""
        grid = [[0] * GRID_SIZE for _ in range(GRID_SIZE)]
        ax, ay = agent_pos
        grid[ay][ax] = 1  # Agent (color 1)
        if target_pos:
            tx, ty = target_pos
            grid[ty][tx] = 4  # Target (color 4)
        if walls:
            for wx, wy in walls:
                grid[wy][wx] = 2  # Wall (color 2)
        return grid

    # Environment 1: Simple navigation (tutorial)
    env1 = {
        "env_id": "dm01",
        "levels": [
            {
                "initial_frame": make_grid(agent_pos=(10, 32), target_pos=(50, 32)),
                "win_condition": {"type": "reach_target", "target_pos": (50, 32)},
                "human_baseline": 40,
                "valid_actions": ["key_up", "key_down", "key_left", "key_right", "key_space", "undo"],
            },
            {
                "initial_frame": make_grid(agent_pos=(5, 5), target_pos=(58, 58), walls=[(30, j) for j in range(20, 44)]),
                "win_condition": {"type": "reach_target", "target_pos": (58, 58)},
                "human_baseline": 80,
                "valid_actions": ["key_up", "key_down", "key_left", "key_right", "key_space", "undo"],
            },
            {
                "initial_frame": make_grid(agent_pos=(32, 60), target_pos=(32, 4)),
                "win_condition": {"type": "reach_target", "target_pos": (32, 4)},
                "human_baseline": 60,
                "valid_actions": ["key_up", "key_down", "key_left", "key_right", "key_space", "undo"],
            },
        ],
    }

    # Environment 2: Collect items
    env2 = {
        "env_id": "dm02",
        "levels": [
            {
                "initial_frame": make_grid(agent_pos=(32, 32)),
                "win_condition": {"type": "collect_all"},
                "human_baseline": 50,
                "valid_actions": ["key_up", "key_down", "key_left", "key_right", "key_space", "undo", "cell_select"],
            },
        ],
    }

    # Environment 3: Pattern matching
    env3 = {
        "env_id": "dm03",
        "levels": [
            {
                "initial_frame": make_grid(agent_pos=(32, 32)),
                "win_condition": {"type": "reach_target", "target_pos": (32, 32)},
                "human_baseline": 5,
                "valid_actions": ["key_space", "undo"],
            },
        ],
    }

    return [env1, env2, env3]


# ============================================================
# CLI Entry Point
# ============================================================

if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser(description="ARC-AGI-3 Evaluation for TOMAS")
    parser.add_argument("--dataset", type=str, default=None, help="Path to ARC-AGI-3 dataset JSON")
    parser.add_argument("--api-url", type=str, default="http://localhost:5000", help="TOMAS API URL")
    parser.add_argument("--max-envs", type=int, default=0, help="Max environments to evaluate (0=all)")
    parser.add_argument("--demo", action="store_true", help="Use demo environments")
    parser.add_argument("--dry-run", action="store_true", help="Dry run (no API calls, random actions)")
    parser.add_argument("--output", type=str, default=None, help="Output report JSON path")
    parser.add_argument("--verbose", action="store_true", default=True)

    args = parser.parse_args()

    # Determine dataset source
    if args.demo or (args.dataset is None and not os.path.exists("data/arc_agi3_public.json")):
        print("⚠️ Using demo environments (no real dataset available)")
        demo_envs = generate_demo_environments()
        demo_path = "data/arc_agi3_demo.json"
        os.makedirs("data", exist_ok=True)
        with open(demo_path, "w") as f:
            json.dump({"environments": demo_envs}, f, indent=2)
        args.dataset = demo_path

    if args.dataset is None:
        args.dataset = "data/arc_agi3_public.json"

    if not os.path.exists(args.dataset):
        print(f"❌ Dataset not found: {args.dataset}")
        print("Use --demo to generate demo environments")
        sys.exit(1)

    evaluator = ARCAGI3Evaluator(
        tomas_api_url=args.api_url,
        verbose=args.verbose,
    )

    if args.dry_run:
        # Dry run: simulate with random actions
        print("🏃 Dry run mode (random actions, no API calls)")
        evaluator.tomas_api_url = "http://localhost:99999"  # Will trigger fallback

    report = evaluator.evaluate_dataset(args.dataset, max_envs=args.max_envs)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\n📄 Report saved to: {args.output}")

    print(f"\n✅ Total RHAE Score: {report['total_score']}%")
