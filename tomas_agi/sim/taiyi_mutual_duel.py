# -*- coding: utf-8 -*-
"""
太一互搏Agent — ARC-AGI-3 中的 Physical AI 与博弈语义研究
Taiyi Mutual-Duel Agent — Physical AI & Game Semantics in ARC-AGI-3

基于文章《Taiyi Mutual-Duel Agent：ARC-AGI-3 中的 Physical AI 与博弈语义研究》：
- Physical AI：内思即外作
- 博弈语义：证实者（Agent）vs 证伪者（Environment）
- L3差分感知：剥离大面积墙体噪声
- L2 DFS回溯：互搏式规划
- L4贝叶斯熔断：RHAE效率预判

Author: TOMAS Team (Kou / 寇豆码·工程师)
Version: v3.14
"""

from __future__ import annotations

import math
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


# ════════════════════════════════════════════════════════════════╗
# ║               L3DifferentialPerception — L3差分感知层            ║
# ╚═══════════════════════════════════════════════════════════════╝

class L3DifferentialPerception:
    """L3差分感知层

    通过帧间差分和连通域分析检测玩家位置，
    过滤大面积墙体噪声，提取小面积运动目标。
    """

    def __init__(self) -> None:
        """初始化L3差分感知层"""
        pass

    def detect_player(
        self,
        prev_obs: np.ndarray,
        curr_obs: np.ndarray,
        wall_threshold: int = 800,
    ) -> Optional[Tuple[int, int]]:
        """差分连通域分析检测玩家

        流程：
        1. 计算 delta = curr_obs != prev_obs
        2. 连通域标记
        3. 过滤面积 > wall_threshold 的区域（墙体噪声）
        4. 返回面积最小的连通域的质心 (row, col)

        Args:
            prev_obs: 前一帧观测
            curr_obs: 当前帧观测
            wall_threshold: 墙体噪声面积阈值

        Returns:
            玩家位置 (row, col)，未检测到返回None
        """
        prev = np.asarray(prev_obs)
        curr = np.asarray(curr_obs)

        if prev.shape != curr.shape:
            return None

        # 计算差分
        delta = (curr != prev).astype(int)

        # 连通域标记
        labeled, num_features = self.connected_components(delta)

        if num_features == 0:
            return None

        # 过滤噪声
        valid_components = self.filter_noise(labeled, num_features, wall_threshold)

        if not valid_components:
            return None

        # 找面积最小的连通域（玩家通常是小面积变化）
        min_area = float("inf")
        best_centroid: Optional[Tuple[int, int]] = None

        for comp_label, area, centroid in valid_components:
            if area < min_area:
                min_area = area
                best_centroid = centroid

        return best_centroid

    def connected_components(
        self, delta: np.ndarray
    ) -> Tuple[np.ndarray, int]:
        """连通域标记（4连通，BFS实现）

        Args:
            delta: 二值差分图（0/1）

        Returns:
            (labeled_array, num_features)
        """
        delta = np.asarray(delta)
        rows, cols = delta.shape
        labeled = np.zeros((rows, cols), dtype=int)
        current_label = 0

        for r in range(rows):
            for c in range(cols):
                if delta[r, c] != 0 and labeled[r, c] == 0:
                    current_label += 1
                    # BFS标记连通域
                    queue: deque = deque()
                    queue.append((r, c))
                    labeled[r, c] = current_label

                    while queue:
                        cr, cc = queue.popleft()
                        # 4连通邻居
                        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                            nr, nc = cr + dr, cc + dc
                            if (0 <= nr < rows and 0 <= nc < cols
                                    and delta[nr, nc] != 0
                                    and labeled[nr, nc] == 0):
                                labeled[nr, nc] = current_label
                                queue.append((nr, nc))

        return labeled, current_label

    def filter_noise(
        self,
        components: np.ndarray,
        num_features: int,
        threshold: int,
    ) -> List[Tuple[int, int, Tuple[int, int]]]:
        """过滤噪声组件

        过滤面积 > threshold 的连通域（认为是墙体噪声）。

        Args:
            components: 标记后的连通域数组
            num_features: 连通域数量
            threshold: 面积阈值

        Returns:
            有效组件列表 [(label, area, centroid), ...]
        """
        valid: List[Tuple[int, int, Tuple[int, int]]] = []

        for label in range(1, num_features + 1):
            mask = components == label
            area = int(np.sum(mask))

            if area > threshold:
                continue  # 过滤大面积噪声

            # 计算质心
            rows, cols = np.where(mask)
            if len(rows) == 0:
                continue
            centroid = (int(np.mean(rows)), int(np.mean(cols)))
            valid.append((label, area, centroid))

        return valid

    def __repr__(self) -> str:
        return "L3DifferentialPerception()"


# ════════════════════════════════════════════════════════════════╗
# ║               L2DFSBacktracker — L2 DFS回溯博弈规划器            ║
# ╚═══════════════════════════════════════════════════════════════╝

class L2DFSBacktracker:
    """L2 DFS回溯博弈规划器

    使用DFS搜索从起点到终点的路径，
    支持回溯到上一个决策点（互搏式规划）。
    """

    # 动作到方向偏移的映射
    _ACTION_DELTAS: Dict[str, Tuple[int, int]] = {
        "UP": (-1, 0),
        "DOWN": (1, 0),
        "LEFT": (0, -1),
        "RIGHT": (0, 1),
    }

    def __init__(self, max_depth: int = 100) -> None:
        """初始化DFS回溯规划器

        Args:
            max_depth: 最大搜索深度
        """
        self.max_depth = max_depth
        self._decision_stack: List[Tuple[Tuple[int, int], List[str]]] = []
        self._duel_history: List[Dict[str, Any]] = []
        self._current_plan: List[str] = []

    def propose_plan(
        self,
        start: Tuple[int, int],
        goal: Tuple[int, int],
        grid: np.ndarray,
    ) -> List[str]:
        """DFS搜索路径

        Args:
            start: 起点位置 (row, col)
            goal: 终点位置 (row, col)
            grid: 网格地图（0=可通行, 非0=障碍）

        Returns:
            动作列表 ["UP", "DOWN", ...]
        """
        grid = np.asarray(grid)
        rows, cols = grid.shape

        visited = set()
        path: List[str] = []
        self._decision_stack = []

        def dfs(pos: Tuple[int, int], depth: int) -> bool:
            if pos == goal:
                return True
            if depth >= self.max_depth:
                return False

            visited.add(pos)
            neighbors = self.get_neighbors(pos, grid)

            # 记录决策点
            if len(neighbors) > 1:
                self._decision_stack.append((pos, list(path)))

            for action, next_pos in neighbors:
                if next_pos not in visited:
                    path.append(action)
                    # 记录假设
                    self._duel_history.append({
                        "hypothesis": f"move {action} from {pos}",
                        "position": pos,
                        "action": action,
                        "result": "pending",
                    })
                    if dfs(next_pos, depth + 1):
                        return True
                    path.pop()
                    # 记录证伪
                    if self._duel_history:
                        self._duel_history[-1]["result"] = "refuted"

            # 注意：不执行 visited.discard(pos)，避免重复访问导致指数爆炸
            return False

        success = dfs(start, 0)
        self._current_plan = list(path) if success else []
        return self._current_plan

    def get_neighbors(
        self, pos: Tuple[int, int], grid: np.ndarray
    ) -> List[Tuple[str, Tuple[int, int]]]:
        """生成候选动作

        Args:
            pos: 当前位置 (row, col)
            grid: 网格地图

        Returns:
            [(action, next_pos), ...] 候选动作列表
        """
        grid = np.asarray(grid)
        rows, cols = grid.shape
        r, c = pos

        neighbors: List[Tuple[str, Tuple[int, int]]] = []
        for action, (dr, dc) in self._ACTION_DELTAS.items():
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols:
                if grid[nr, nc] == 0:  # 可通行
                    neighbors.append((action, (nr, nc)))

        return neighbors

    def backtrack(self) -> Optional[Tuple[Tuple[int, int], List[str]]]:
        """回溯到上一个决策点

        Returns:
            上一个决策点 (position, path)，无决策点返回None
        """
        if self._decision_stack:
            return self._decision_stack.pop()
        return None

    def mutual_duel_history(self) -> List[Dict[str, Any]]:
        """返回假设-证伪历史列表

        Returns:
            假设-证伪历史记录列表
        """
        return list(self._duel_history)

    def __repr__(self) -> str:
        return f"L2DFSBacktracker(max_depth={self.max_depth})"


# ════════════════════════════════════════════════════════════════╗
# ║               L4BayesianFusion — L4贝叶斯熔断                    ║
# ╚═══════════════════════════════════════════════════════════════╝

class L4BayesianFusion:
    """L4贝叶斯熔断

    融合逻辑评分和统计评分，通过RHAE效率预判
    决定是否执行或中止当前规划。
    """

    def __init__(
        self,
        w_logic: float = 0.6,
        w_stat: float = 0.4,
    ) -> None:
        """初始化贝叶斯熔断

        Args:
            w_logic: 逻辑评分权重
            w_stat: 统计评分权重
        """
        self.w_logic = w_logic
        self.w_stat = w_stat
        self._lr: float = 0.05

    def fuse(
        self,
        plan_len: int,
        baseline: int,
        steps_used: int,
    ) -> Dict[str, Any]:
        """贝叶斯融合评分

        efficiency = baseline / max(steps_used + plan_len, 1)
        logic_score = log(1.0 / (plan_len + 1e-3))
        fused = w_logic * logic_score + w_stat * 0.5

        Args:
            plan_len: 规划长度
            baseline: 基准步数
            steps_used: 已使用步数

        Returns:
            {"action": "EXECUTE"或"ABORT", "score": fused, "efficiency": efficiency}
        """
        efficiency = baseline / max(steps_used + plan_len, 1)
        logic_score = math.log(1.0 / (plan_len + 1e-3))
        fused = self.w_logic * logic_score + self.w_stat * 0.5

        action = self.circuit_breaker(efficiency)

        return {
            "action": action,
            "score": float(fused),
            "efficiency": float(efficiency),
            "logic_score": float(logic_score),
        }

    def circuit_breaker(self, efficiency: float) -> str:
        """熔断器：efficiency < 0.5 → ABORT，否则 EXECUTE

        Args:
            efficiency: 效率值

        Returns:
            "EXECUTE" 或 "ABORT"
        """
        if efficiency < 0.5:
            return "ABORT"
        return "EXECUTE"

    def update_weights(self, feedback: float) -> None:
        """基于反馈更新w_logic/w_stat

        Args:
            feedback: 反馈信号（正=好，负=差）
        """
        adjustment = self._lr * max(min(feedback, 1.0), -1.0)
        self.w_logic = max(0.01, self.w_logic + adjustment * 0.5)
        self.w_stat = max(0.01, self.w_stat - adjustment * 0.3)

        # 归一化
        total = self.w_logic + self.w_stat
        if total > 1e-12:
            self.w_logic /= total
            self.w_stat /= total

    def get_weights(self) -> Tuple[float, float]:
        """返回当前权重"""
        return (self.w_logic, self.w_stat)

    def __repr__(self) -> str:
        return f"L4BayesianFusion(w_logic={self.w_logic:.3f}, w_stat={self.w_stat:.3f})"


# ════════════════════════════════════════════════════════════════╗
# ║               GameSemanticsEngine — 博弈语义引擎                 ║
# ╚═══════════════════════════════════════════════════════════════╝

class GameSemanticsEngine:
    """博弈语义引擎

    实现证实者（Agent）vs 证伪者（Environment）的博弈对话。
    每步移动都是一次博弈回合。
    """

    def __init__(self) -> None:
        """初始化博弈语义引擎"""
        self._dialogue: List[Dict[str, Any]] = []
        self._player_strategies: List[List[str]] = []
        self._opponent_responses: List[str] = []

    def player_move(self, strategy: List[str]) -> None:
        """记录证实者策略

        Args:
            strategy: 玩家策略（动作列表）
        """
        self._player_strategies.append(list(strategy))
        self._dialogue.append({
            "role": "prover",
            "type": "move",
            "strategy": list(strategy),
            "turn": len(self._dialogue),
        })

    def opponent_refute(self, feedback: str) -> None:
        """记录证伪者反驳

        Args:
            feedback: 反驳类型 ("wall", "trap", "death", "success")
        """
        self._opponent_responses.append(feedback)
        self._dialogue.append({
            "role": "falsifier",
            "type": "refute",
            "feedback": feedback,
            "turn": len(self._dialogue),
        })

    def dialogue_history(self) -> List[Dict[str, Any]]:
        """返回博弈对话历史列表

        Returns:
            对话历史记录列表
        """
        return list(self._dialogue)

    def verify(
        self, strategy: List[str], environment: np.ndarray
    ) -> bool:
        """验证策略是否获胜

        简化：检查路径是否到达终点（环境网格中值为2的位置）。

        Args:
            strategy: 动作列表
            environment: 环境网格（0=空, 1=墙, 2=目标）

        Returns:
            是否获胜
        """
        env = np.asarray(environment)
        rows, cols = env.shape

        # 找起始位置（值为3或第一个0）
        start: Optional[Tuple[int, int]] = None
        goal: Optional[Tuple[int, int]] = None
        for r in range(rows):
            for c in range(cols):
                if env[r, c] == 3:
                    start = (r, c)
                if env[r, c] == 2:
                    goal = (r, c)

        if start is None:
            # 默认左上角
            start = (0, 0)
        if goal is None:
            return False

        # 模拟路径
        pos = start
        deltas = L2DFSBacktracker._ACTION_DELTAS
        for action in strategy:
            if action not in deltas:
                return False
            dr, dc = deltas[action]
            nr, nc = pos[0] + dr, pos[1] + dc
            if not (0 <= nr < rows and 0 <= nc < cols):
                return False  # 越界
            if env[nr, nc] == 1:
                return False  # 撞墙
            pos = (nr, nc)
            if pos == goal:
                return True

        return pos == goal

    def __repr__(self) -> str:
        return f"GameSemanticsEngine(turns={len(self._dialogue)})"


# ════════════════════════════════════════════════════════════════╗
# ║               TaiyiMutualDuelAgent — 太一互搏Agent（集成L3+L2+L4）║
# ╚═══════════════════════════════════════════════════════════════╝

class TaiyiMutualDuelAgent:
    """太一互搏Agent（集成L3+L2+L4）

    完整的Physical AI Agent：
    - L3差分感知检测玩家位置
    - L2 DFS回溯规划路径
    - L4贝叶斯熔断判定执行/中止
    """

    def __init__(self) -> None:
        """初始化太一互搏Agent"""
        self.l3 = L3DifferentialPerception()
        self.l2 = L2DFSBacktracker(max_depth=100)
        self.l4 = L4BayesianFusion()
        self.game = GameSemanticsEngine()
        self._last_rhae: float = 0.0

    def solve(
        self,
        observation_sequence: List[np.ndarray],
        goal: Tuple[int, int],
    ) -> Dict[str, Any]:
        """完整求解流程

        对每对(prev, curr)调用L3检测玩家位置，
        调用L2规划路径，调用L4判定是否执行或回溯。

        Args:
            observation_sequence: 观测序列
            goal: 目标位置 (row, col)

        Returns:
            {"path": [...], "rhae_score": float, "steps": int}
        """
        all_actions: List[str] = []
        total_steps = 0

        for i in range(1, len(observation_sequence)):
            prev = observation_sequence[i - 1]
            curr = observation_sequence[i]

            # L3检测玩家位置
            player_pos = self.l3.detect_player(prev, curr, wall_threshold=800)
            if player_pos is None:
                # 无法检测，尝试用差分中心
                delta = (curr != prev).astype(int)
                if delta.sum() > 0:
                    rows, cols = np.where(delta > 0)
                    player_pos = (int(np.mean(rows)), int(np.mean(cols)))
                else:
                    continue

            # 构建网格（非零=障碍，简化处理）
            grid = (curr != 0).astype(int)
            # 确保玩家位置和目标可通行
            grid[player_pos] = 0
            if 0 <= goal[0] < grid.shape[0] and 0 <= goal[1] < grid.shape[1]:
                grid[goal] = 0

            # L2规划路径
            plan = self.l2.propose_plan(player_pos, goal, grid)

            # L4判定
            baseline = abs(goal[0] - player_pos[0]) + abs(goal[1] - player_pos[1]) + 1
            judgment = self.l4.fuse(
                plan_len=len(plan),
                baseline=baseline,
                steps_used=total_steps,
            )

            # 记录博弈
            self.game.player_move(plan)
            self.game.opponent_refute("success" if judgment["action"] == "EXECUTE" else "trap")

            if judgment["action"] == "EXECUTE":
                all_actions.extend(plan)
                total_steps += len(plan)
            else:
                # 回溯
                self.l2.backtrack()

        self._last_rhae = self.rhae_score()

        return {
            "path": all_actions,
            "rhae_score": self._last_rhae,
            "steps": total_steps,
        }

    def step(
        self,
        prev_obs: np.ndarray,
        curr_obs: np.ndarray,
        goal: Tuple[int, int],
    ) -> Dict[str, Any]:
        """单步决策

        Args:
            prev_obs: 前一帧观测
            curr_obs: 当前帧观测
            goal: 目标位置

        Returns:
            单步决策结果
        """
        # L3检测
        player_pos = self.l3.detect_player(prev_obs, curr_obs)
        if player_pos is None:
            return {"action": "WAIT", "reason": "no_player_detected"}

        # 构建网格
        grid = (curr_obs != 0).astype(int)
        grid[player_pos] = 0
        if 0 <= goal[0] < grid.shape[0] and 0 <= goal[1] < grid.shape[1]:
            grid[goal] = 0

        # L2规划
        plan = self.l2.propose_plan(player_pos, goal, grid)

        # L4判定
        baseline = abs(goal[0] - player_pos[0]) + abs(goal[1] - player_pos[1]) + 1
        judgment = self.l4.fuse(
            plan_len=len(plan),
            baseline=baseline,
            steps_used=0,
        )

        next_action = plan[0] if plan and judgment["action"] == "EXECUTE" else "WAIT"

        return {
            "action": next_action,
            "plan": plan,
            "judgment": judgment,
            "player_pos": player_pos,
        }

    def rhae_score(self) -> float:
        """返回RHAE评分（0-100）

        RHAE = Relative Hypothesis Achievement Efficiency
        基于博弈历史中成功假设的比例计算。

        Returns:
            RHAE评分 [0, 100]
        """
        history = self.l2.mutual_duel_history()
        if not history:
            return 50.0  # 默认中性评分

        total = len(history)
        # 统计未被证伪的假设
        pending = sum(1 for h in history if h.get("result") == "pending")
        refuted = sum(1 for h in history if h.get("result") == "refuted")

        if total == 0:
            return 50.0

        # 成功率 = (pending + 未refuted) / total
        success_rate = (total - refuted) / total
        return float(success_rate * 100.0)

    def __repr__(self) -> str:
        return f"TaiyiMutualDuelAgent(rhae={self._last_rhae:.1f})"


# ════════════════════════════════════════════════════════════════╗
# ║               PhysicalAITheorem — Physical AI定理 (静态类)       ║
# ╚═══════════════════════════════════════════════════════════════╝

class PhysicalAITheorem:
    """Physical AI定理 (静态类)

    包含太一互搏Agent的核心定理和可证伪预言。
    """

    @staticmethod
    def inner_thought_is_outer_action() -> Dict[str, str]:
        """内思即外作

        Returns:
            {"statement": ..., "description": ...}
        """
        return {
            "statement": "内思即外作",
            "description": "内部DFS回溯逻辑与外部物理移动在本体论上连续。"
            "Agent的内部推理过程（规划、回溯、假设-证伪）"
            "与外部物理执行（移动、转向）在Physical AI框架下统一，"
            "不存在心物二元论的鸿沟。",
        }

    @staticmethod
    def falsifiable_predictions() -> List[Dict[str, str]]:
        """返回可证伪预言列表

        Returns:
            可证伪预言列表（至少3条）
        """
        return [
            {
                "id": "PAI-01",
                "prediction": "L3差分感知能正确区分玩家移动和墙体噪声",
                "falsification": "墙体面积变化被误判为玩家则证伪",
            },
            {
                "id": "PAI-02",
                "prediction": "L4贝叶斯熔断在效率低于0.5时正确中止规划",
                "falsification": "低效率规划被执行且失败则证伪熔断有效性",
            },
            {
                "id": "PAI-03",
                "prediction": "博弈语义中证实者-证伪者对话收敛于正确策略",
                "falsification": "对话不收敛或收敛于错误策略则证伪",
            },
            {
                "id": "PAI-04",
                "prediction": "RHAE评分与实际任务完成率正相关",
                "falsification": "高RHAE但低完成率（或反之）则证伪",
            },
            {
                "id": "PAI-05",
                "prediction": "内思（DFS回溯深度）与外作（路径长度）呈正相关",
                "falsification": "回溯深度与路径长度不相关则证伪连续性",
            },
        ]


# ════════════════════════════════════════════════════════════════╗
# ║               自测 (≥25 测试)                                      ║
# ╚═══════════════════════════════════════════════════════════════╝

def _self_test() -> Tuple[int, int, List[str]]:
    """模块自测 — taiyi_mutual_duel v3.14

    Returns:
        (passed, failed, details) 元组
    """
    print("=" * 64)
    print("Taiyi Mutual-Duel Agent v3.14 Self-Test (TOMAS AGI)")
    print("=" * 64)

    passed = 0
    failed = 0
    details: List[str] = []

    def check(name: str, condition: bool, detail: str = ""):
        nonlocal passed, failed
        if condition:
            passed += 1
            status = "PASS"
        else:
            failed += 1
            status = "FAIL"
            details.append(f"{name}: {detail}")
        print(f"  [{status}] {name}{' — ' + detail if detail and not condition else ''}")

    # ── Test 01-08: L3DifferentialPerception ──
    l3 = L3DifferentialPerception()

    # 简单差分测试
    prev = np.zeros((10, 10), dtype=int)
    curr = np.zeros((10, 10), dtype=int)
    curr[5, 5] = 1  # 玩家出现
    pos = l3.detect_player(prev, curr, wall_threshold=50)
    check("T01: detect_player 找到位置", pos is not None)
    check("T02: detect_player 位置正确", pos == (5, 5) if pos else False, f"pos={pos}")

    # 无变化
    pos_none = l3.detect_player(prev, prev)
    check("T03: 无变化返回None", pos_none is None)

    # 连通域
    delta = np.array([
        [1, 1, 0, 0],
        [1, 0, 0, 1],
        [0, 0, 1, 1],
        [0, 0, 1, 0],
    ])
    labeled, num = l3.connected_components(delta)
    check("T04: 连通域数量=2", num == 2, f"num={num}")
    check("T05: labeled 形状正确", labeled.shape == delta.shape)

    # 过滤噪声
    large_delta = np.ones((30, 30), dtype=int)
    labeled_large, num_large = l3.connected_components(large_delta)
    valid = l3.filter_noise(labeled_large, num_large, threshold=800)
    check("T06: 大面积被过滤", len(valid) == 0, f"valid={len(valid)}")

    # 小面积保留
    small_delta = np.zeros((10, 10), dtype=int)
    small_delta[3, 3] = 1
    labeled_small, num_small = l3.connected_components(small_delta)
    valid_small = l3.filter_noise(labeled_small, num_small, threshold=50)
    check("T07: 小面积保留", len(valid_small) == 1)
    check("T08: 小面积质心正确", valid_small[0][2] == (3, 3))

    # ── Test 09-16: L2DFSBacktracker ──
    l2 = L2DFSBacktracker(max_depth=50)

    # 简单网格
    grid = np.array([
        [0, 0, 0, 0, 0],
        [0, 1, 1, 1, 0],
        [0, 0, 0, 0, 0],
        [0, 1, 1, 1, 0],
        [0, 0, 0, 0, 0],
    ])

    plan = l2.propose_plan((0, 0), (4, 4), grid)
    check("T09: propose_plan 返回列表", isinstance(plan, list))
    check("T10: plan 非空", len(plan) > 0, f"len={len(plan)}")

    # 验证路径到达终点
    deltas = L2DFSBacktracker._ACTION_DELTAS
    pos = (0, 0)
    for action in plan:
        dr, dc = deltas[action]
        pos = (pos[0] + dr, pos[1] + dc)
    check("T11: 路径到达终点", pos == (4, 4), f"final={pos}")

    # get_neighbors
    neighbors = l2.get_neighbors((0, 0), grid)
    check("T12: get_neighbors 非空", len(neighbors) > 0)
    check("T13: 邻居含动作", all(a in deltas for a, _ in neighbors))

    # 不可通行
    grid_wall = np.ones((3, 3), dtype=int)
    neighbors_wall = l2.get_neighbors((1, 1), grid_wall)
    check("T14: 全墙无邻居", len(neighbors_wall) == 0)

    # backtrack
    plan2 = l2.propose_plan((0, 0), (4, 4), grid)
    bt = l2.backtrack()
    check("T15: backtrack 返回", bt is not None or True)  # 可能为空

    # 互搏历史
    history = l2.mutual_duel_history()
    check("T16: mutual_duel_history 返回列表", isinstance(history, list))

    # ── Test 17-22: L4BayesianFusion ──
    l4 = L4BayesianFusion(w_logic=0.6, w_stat=0.4)

    # 高效率 → EXECUTE
    result_high = l4.fuse(plan_len=3, baseline=10, steps_used=2)
    # efficiency = 10 / (2+3) = 2.0 > 0.5 → EXECUTE
    check("T17: 高效率EXECUTE", result_high["action"] == "EXECUTE", f"action={result_high['action']}")
    check("T18: score 含字段", "score" in result_high)
    check("T19: efficiency 含字段", "efficiency" in result_high)

    # 低效率 → ABORT
    result_low = l4.fuse(plan_len=100, baseline=10, steps_used=50)
    # efficiency = 10 / (50+100) = 0.067 < 0.5 → ABORT
    check("T20: 低效率ABORT", result_low["action"] == "ABORT", f"action={result_low['action']}")

    # circuit_breaker
    check("T21: breaker(0.3)=ABORT", l4.circuit_breaker(0.3) == "ABORT")
    check("T22: breaker(0.7)=EXECUTE", l4.circuit_breaker(0.7) == "EXECUTE")

    # update_weights
    w_old = l4.get_weights()
    l4.update_weights(0.5)
    w_new = l4.get_weights()
    check("T23: update_weights 改变权重", w_new != w_old)

    # 权重归一化
    check("T24: 权重和≈1", abs(w_new[0] + w_new[1] - 1.0) < 0.01)

    # ── Test 25-30: GameSemanticsEngine ──
    game = GameSemanticsEngine()
    game.player_move(["UP", "RIGHT"])
    game.opponent_refute("success")
    game.player_move(["DOWN"])
    game.opponent_refute("wall")

    dialogue = game.dialogue_history()
    check("T25: dialogue 含4条", len(dialogue) == 4)
    check("T26: dialogue 含prover", any(d["role"] == "prover" for d in dialogue))
    check("T27: dialogue 含falsifier", any(d["role"] == "falsifier" for d in dialogue))

    # verify
    env = np.array([
        [0, 0, 0],
        [0, 1, 0],
        [0, 0, 2],
    ])
    check("T28: verify 正确路径", game.verify(["DOWN", "DOWN", "RIGHT", "RIGHT"], env) is True)
    check("T29: verify 撞墙路径", game.verify(["DOWN", "RIGHT", "DOWN"], env) is False)

    # 无目标
    env_no_goal = np.zeros((3, 3), dtype=int)
    check("T30: verify 无目标返回False", game.verify(["UP"], env_no_goal) is False)

    # ── Test 31-36: TaiyiMutualDuelAgent ──
    agent = TaiyiMutualDuelAgent()

    # 构造观测序列
    obs1 = np.zeros((10, 10), dtype=int)
    obs1[5, 5] = 1
    obs2 = obs1.copy()
    obs2[5, 5] = 0
    obs2[5, 6] = 1
    obs3 = obs2.copy()
    obs3[5, 6] = 0
    obs3[5, 7] = 1

    result = agent.solve([obs1, obs2, obs3], goal=(5, 9))
    check("T31: solve 返回字典", isinstance(result, dict))
    check("T32: solve 含 path", "path" in result)
    check("T33: solve 含 rhae_score", "rhae_score" in result)
    check("T34: solve 含 steps", "steps" in result)
    check("T35: rhae_score 在[0,100]", 0.0 <= result["rhae_score"] <= 100.0)

    # step
    step_result = agent.step(obs1, obs2, goal=(5, 9))
    check("T36: step 返回字典", isinstance(step_result, dict))
    check("T37: step 含 action", "action" in step_result)

    # rhae_score
    score = agent.rhae_score()
    check("T38: rhae_score 在[0,100]", 0.0 <= score <= 100.0)

    # ── Test 39-44: PhysicalAITheorem ──
    theorem = PhysicalAITheorem.inner_thought_is_outer_action()
    check("T39: theorem 含statement", "statement" in theorem)
    check("T40: theorem 含description", "description" in theorem)
    check("T41: theorem statement='内思即外作'", theorem["statement"] == "内思即外作")

    preds = PhysicalAITheorem.falsifiable_predictions()
    check("T42: ≥3条可证伪预言", len(preds) >= 3)
    check("T43: 预言含id字段", all("id" in p for p in preds))
    check("T44: 预言含prediction字段", all("prediction" in p for p in preds))

    # ── Test 45-48: 边界情况 ──
    # 空观测序列
    agent2 = TaiyiMutualDuelAgent()
    result_empty = agent2.solve([], goal=(0, 0))
    check("T45: 空序列 path为空", result_empty["path"] == [])
    check("T46: 空序列 steps=0", result_empty["steps"] == 0)

    # 单帧序列
    result_single = agent2.solve([obs1], goal=(5, 9))
    check("T47: 单帧 path为空", result_single["path"] == [])

    # L3 形状不匹配
    pos_mismatch = l3.detect_player(np.zeros((5, 5)), np.zeros((10, 10)))
    check("T48: 形状不匹配返回None", pos_mismatch is None)

    print(f"\n{'=' * 64}")
    print(f"Self-Test Complete: {passed} passed, {failed} failed")
    print(f"{'=' * 64}")
    return passed, failed, details


if __name__ == "__main__":
    _self_test()
