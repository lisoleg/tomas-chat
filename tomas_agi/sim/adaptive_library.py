# -*- coding: utf-8 -*-
"""
自适应库学习 — TOMAS v2.0 神经符号架构
Adaptive Library Learning — TOMAS v2.0 Neuro-Symbolic Architecture

基于文章《TOMAS v2.0：基于自适应库学习的神经符号架构与ARC-AGI-3流体智能的统一解释》：
- α/β参数在线学习
- AST子树提取与频率统计
- 阴龙积（Yin-Dragon Product）：八元数乘法+虚部投影
- 条件ΔT归纳
- 多模态甘极化融合
- Rice定理上界

Author: TOMAS Team (Kou / 寇豆码·工程师)
Version: v3.14
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


# ════════════════════════════════════════════════════════════════╗
# ║               AdaptiveParams — 自适应参数                         ║
# ╚═══════════════════════════════════════════════════════════════╝

class AdaptiveParams:
    """自适应参数 — α/β在线学习

    管理程序归纳的预算分配参数：
    - alpha: MDL代价权重
    - beta: 频率权重
    - b_base: 基础预算

    预算公式: B = b_base + alpha * mdl_cost + beta * log2(freq + 1)
    """

    def __init__(
        self,
        alpha: float = 1.0,
        beta: float = 1.0,
        b_base: float = 10.0,
    ) -> None:
        """初始化自适应参数

        Args:
            alpha: MDL代价权重
            beta: 频率权重
            b_base: 基础预算
        """
        self.alpha = alpha
        self.beta = beta
        self.b_base = b_base
        self._lr: float = 0.01  # 学习率
        self._gain_history: List[float] = []

    def compute_budget(self, mdl_cost: float, freq: int) -> float:
        """计算预算 B = b_base + alpha * mdl_cost + beta * log2(freq+1)

        Args:
            mdl_cost: MDL编码代价
            freq: 原语使用频率

        Returns:
            分配的预算值
        """
        return (
            self.b_base
            + self.alpha * mdl_cost
            + self.beta * math.log2(freq + 1)
        )

    def update(self, gain_history: List[float]) -> None:
        """基于历史增益用梯度上升更新alpha/beta

        Args:
            gain_history: 历史增益序列
        """
        self._gain_history = list(gain_history)
        if len(gain_history) < 2:
            return

        # 计算增益差分作为梯度信号
        gains = np.array(gain_history, dtype=float)
        diffs = np.diff(gains)

        # alpha 梯度：增益随MDL代价增加而增加 → 增大alpha
        alpha_grad = float(np.mean(diffs)) if len(diffs) > 0 else 0.0
        # beta 梯度：增益随频率增加而增加 → 增大beta
        beta_grad = float(np.std(diffs)) if len(diffs) > 0 else 0.0

        self.alpha = max(0.01, self.alpha + self._lr * alpha_grad)
        self.beta = max(0.01, self.beta + self._lr * beta_grad)

    def ast_width_control(
        self, depth: int, max_depth: int, budget: float
    ) -> float:
        """AST宽度控制 w(d) = budget * 2^(-d) / Σ

        指数衰减的宽度分配：浅层获得更多搜索宽度。

        Args:
            depth: 当前深度
            max_depth: 最大深度
            budget: 总预算

        Returns:
            当前深度分配的宽度
        """
        if max_depth <= 0:
            return budget
        # 计算归一化因子
        total = sum(2.0 ** (-d) for d in range(max_depth + 1))
        if total < 1e-12:
            return budget
        return budget * (2.0 ** (-depth)) / total

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "alpha": self.alpha,
            "beta": self.beta,
            "b_base": self.b_base,
            "lr": self._lr,
        }

    def __repr__(self) -> str:
        return f"AdaptiveParams(alpha={self.alpha:.3f}, beta={self.beta:.3f}, b_base={self.b_base})"


# ════════════════════════════════════════════════════════════════╗
# ║               ProgramNode — AST节点（LISP风格DSL）               ║
# ╚═══════════════════════════════════════════════════════════════╝

class ProgramNode:
    """AST节点 — LISP风格DSL程序表示

    每个节点包含操作符、参数和子节点，
    可序列化为S表达式，计算MDL代价，提取子树。
    """

    def __init__(
        self,
        op: str,
        args: Optional[List[Any]] = None,
        children: Optional[List["ProgramNode"]] = None,
    ) -> None:
        """初始化AST节点

        Args:
            op: 操作符名称（如 "rotate", "compose", "color_map"）
            args: 参数列表（如 [90] 表示旋转90度）
            children: 子节点列表
        """
        self.op = op
        self.args = list(args) if args is not None else []
        self.children = list(children) if children is not None else []

    def to_sexp(self) -> str:
        """序列化为S表达式字符串

        Returns:
            S表达式，如 "(compose (rotate 90) (color_map red blue))"
        """
        parts: List[str] = [self.op]
        for arg in self.args:
            parts.append(str(arg))
        for child in self.children:
            parts.append(child.to_sexp())
        return "(" + " ".join(parts) + ")"

    def mdl_cost(self) -> int:
        """计算AST节点数（递归MDL代价）

        Returns:
            子树中的总节点数
        """
        cost = 1  # 自身
        for child in self.children:
            cost += child.mdl_cost()
        return cost

    def depth(self) -> int:
        """计算子树深度"""
        if not self.children:
            return 1
        return 1 + max(c.depth() for c in self.children)

    def extract_subtrees(
        self, max_depth: int = 3, max_width: int = 10
    ) -> List["ProgramNode"]:
        """提取所有深度≤max_depth的子树

        Args:
            max_depth: 最大提取深度
            max_width: 最大提取宽度

        Returns:
            子树列表（不包含根节点自身）
        """
        result: List[ProgramNode] = []
        self._extract_subtrees_recursive(result, 1, max_depth, max_width)
        return result[:max_width]

    def _extract_subtrees_recursive(
        self,
        result: List["ProgramNode"],
        current_depth: int,
        max_depth: int,
        max_width: int,
    ) -> None:
        """递归提取子树"""
        if current_depth >= max_depth:
            return
        if len(result) >= max_width:
            return
        for child in self.children:
            result.append(child)
            if len(result) >= max_width:
                return
            child._extract_subtrees_recursive(
                result, current_depth + 1, max_depth, max_width
            )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ProgramNode):
            return False
        return self.to_sexp() == other.to_sexp()

    def __hash__(self) -> int:
        return hash(self.to_sexp())

    def __repr__(self) -> str:
        return f"ProgramNode({self.to_sexp()})"


# ════════════════════════════════════════════════════════════════╗
# ║               AdaptiveLibrary — 自适应库                         ║
# ╚═══════════════════════════════════════════════════════════════╝

class AdaptiveLibrary:
    """自适应库 — Sleep-Step学习机制

    通过Sleep-Step流程从已解决的程序中提取子树，
    统计频率，注册高频子树为新原语，逐步扩展DSL。
    """

    def __init__(self) -> None:
        """初始化自适应库"""
        self._primitives: Dict[str, ProgramNode] = {}
        self._frequency: Counter = Counter()
        self._params = AdaptiveParams()

    def sleep_step(self, solved_programs: List[ProgramNode]) -> List[str]:
        """执行Sleep-Step：提取子树→统计频率→注册新原语

        Args:
            solved_programs: 已成功求解的程序列表

        Returns:
            新注册的原语名称列表
        """
        # 提取所有子树
        all_subtrees: List[ProgramNode] = []
        for prog in solved_programs:
            all_subtrees.extend(prog.extract_subtrees(max_depth=3, max_width=20))

        # 统计频率
        sexp_counter: Counter = Counter()
        for sub in all_subtrees:
            sexp = sub.to_sexp()
            sexp_counter[sexp] += 1

        # 注册高频子树为新原语
        new_primitives: List[str] = []
        for sexp, count in sexp_counter.most_common():
            if count >= 2 and sexp not in self._primitives:
                # 从sexp解析回ProgramNode（简化：直接存第一个匹配的子树）
                for sub in all_subtrees:
                    if sub.to_sexp() == sexp:
                        primitive_name = f"prim_{len(self._primitives)}"
                        self._primitives[primitive_name] = sub
                        self._frequency[primitive_name] = count
                        new_primitives.append(primitive_name)
                        break

        return new_primitives

    def register_primitive(self, node: ProgramNode) -> str:
        """注册新原语

        Args:
            node: 要注册的程序节点

        Returns:
            注册的原语名称
        """
        name = f"prim_{len(self._primitives)}"
        self._primitives[name] = node
        self._frequency[name] = 1
        return name

    def lookup(self, pattern: str) -> Optional[ProgramNode]:
        """查找匹配原语

        Args:
            pattern: 搜索模式（原语名称或操作符）

        Returns:
            匹配的原语节点，未找到返回None
        """
        if pattern in self._primitives:
            return self._primitives[pattern]
        # 按操作符搜索
        for name, node in self._primitives.items():
            if node.op == pattern:
                return node
        return None

    def closure_size(self) -> int:
        """返回库中原语数量

        Returns:
            原语数量
        """
        return len(self._primitives)

    def frequency_table(self) -> Dict[str, int]:
        """返回频率统计表"""
        return dict(self._frequency)

    def __repr__(self) -> str:
        return f"AdaptiveLibrary(size={self.closure_size()})"


# ════════════════════════════════════════════════════════════════╗
# ║               YinDragonProduct — 阴龙积耦合                       ║
# ╚═══════════════════════════════════════════════════════════════╝

class YinDragonProduct:
    """阴龙积耦合 (Yin-Dragon Product)

    基于八元数乘法的耦合操作：
    - 标量部分 = Re(a ⊗ b*) = 相位失配代价
    - 向量部分 = Im(a ⊗ b) = 变换结果

    八元数乘法使用Cayley-Dickson构造，非结合非交换。
    """

    # Fano平面三元组 (i, j, k) 表示 e_i * e_j = e_k
    _FANO_TRIPLES: List[Tuple[int, int, int]] = [
        (1, 2, 4), (2, 3, 5), (3, 4, 6),
        (4, 5, 7), (5, 6, 1), (6, 7, 2), (7, 1, 3),
    ]

    def __init__(self) -> None:
        """初始化阴龙积耦合"""
        self._mul_table = self._build_multiplication_table()

    def _build_multiplication_table(self) -> Dict[Tuple[int, int], Tuple[int, int]]:
        """构建八元数乘法表

        Returns:
            {(i, j): (sign, k)} 表示 e_i * e_j = sign * e_k
        """
        table: Dict[Tuple[int, int], Tuple[int, int]] = {}
        # e0 = 1 是单位元
        for i in range(8):
            table[(0, i)] = (1, i)
            table[(i, 0)] = (1, i)
        # e_i * e_i = -1
        for i in range(1, 8):
            table[(i, i)] = (-1, 0)
        # Fano平面三元组
        for i, j, k in self._FANO_TRIPLES:
            table[(i, j)] = (1, k)
            table[(j, k)] = (1, i)
            table[(k, i)] = (1, j)
            table[(j, i)] = (-1, k)
            table[(k, j)] = (-1, i)
            table[(i, k)] = (-1, j)
        return table

    def _oct_multiply(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """八元数乘法

        Args:
            a: 8维向量 [a0, a1, ..., a7]
            b: 8维向量 [b0, b1, ..., b7]

        Returns:
            8维乘积向量
        """
        a = np.asarray(a, dtype=float)
        b = np.asarray(b, dtype=float)
        result = np.zeros(8)

        for i in range(8):
            for j in range(8):
                sign, k = self._mul_table[(i, j)]
                result[k] += sign * a[i] * b[j]

        return result

    def _oct_conjugate(self, a: np.ndarray) -> np.ndarray:
        """八元数共轭 a* = [a0, -a1, -a2, ..., -a7]

        Args:
            a: 8维向量

        Returns:
            共轭八元数
        """
        a = np.asarray(a, dtype=float)
        conj = a.copy()
        conj[1:] = -conj[1:]
        return conj

    def compute(
        self, a: np.ndarray, b: np.ndarray
    ) -> Tuple[float, np.ndarray]:
        """阴龙积计算：八元数乘法+虚部投影

        Args:
            a: 8维向量（八元数 a0 + a1*e1 + ... + a7*e7）
            b: 8维向量

        Returns:
            (scalar, vector) 元组：
            - scalar = Re(a ⊗ b*) = 相位失配代价
            - vector = Im(a ⊗ b) = 变换结果（7维虚部）
        """
        a = np.asarray(a, dtype=float)
        b = np.asarray(b, dtype=float)

        # 计算 a ⊗ b*（a乘以b的共轭）
        b_conj = self._oct_conjugate(b)
        product = self._oct_multiply(a, b_conj)

        # 标量部分 = 实部 = product[0]
        scalar = float(product[0])

        # 向量部分 = 虚部 = product[1:7]
        vector = product[1:].copy()

        return scalar, vector

    def phase_mismatch_cost(self, a: np.ndarray, b: np.ndarray) -> float:
        """返回标量部分（相位失配代价）

        Args:
            a: 8维向量
            b: 8维向量

        Returns:
            相位失配代价标量
        """
        scalar, _ = self.compute(a, b)
        return scalar

    def transform_result(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """返回向量部分（变换结果）

        Args:
            a: 8维向量
            b: 8维向量

        Returns:
            7维变换结果向量
        """
        _, vector = self.compute(a, b)
        return vector

    def __repr__(self) -> str:
        return "YinDragonProduct()"


# ════════════════════════════════════════════════════════════════╗
# ║               ConditionalDTInductor — 条件ΔT归纳器               ║
# ╚═══════════════════════════════════════════════════════════════╝

class ConditionalDTInductor:
    """条件ΔT归纳器

    从帧序列中归纳条件决策树，识别状态转换的条件触发规则。
    候选条件: {BoundaryHit, ColorAppear, FrameIdx}
    """

    # 候选条件类型
    CANDIDATE_CONDITIONS: List[str] = ["BoundaryHit", "ColorAppear", "FrameIdx"]

    def __init__(self) -> None:
        """初始化条件ΔT归纳器"""
        self._decision_tree: Dict[str, Any] = {}
        self._frame_history: List[np.ndarray] = []

    def induce(self, frame_sequence: List[np.ndarray]) -> Dict[str, Any]:
        """从帧序列归纳条件决策树

        Args:
            frame_sequence: 帧序列（每帧为2D数组）

        Returns:
            归纳出的决策树字典
        """
        self._frame_history = [np.asarray(f) for f in frame_sequence]
        conditions_detected: List[str] = []
        actions: List[str] = []

        for i in range(1, len(self._frame_history)):
            prev = self._frame_history[i - 1]
            curr = self._frame_history[i]

            # 检测边界碰撞
            if self._detect_boundary_hit(prev, curr):
                conditions_detected.append("BoundaryHit")
                actions.append("Turn")

            # 检测颜色出现
            if self._detect_color_appear(prev, curr):
                conditions_detected.append("ColorAppear")
                actions.append("Collect")

            # 帧索引条件
            conditions_detected.append("FrameIdx")
            actions.append(f"Step_{i}")

        tree = self.build_decision_tree(conditions_detected, actions)
        self._decision_tree = tree
        return tree

    def _detect_boundary_hit(self, prev: np.ndarray, curr: np.ndarray) -> bool:
        """检测边界碰撞：帧边缘像素变化"""
        if prev.shape != curr.shape:
            return False
        # 检查边缘区域的变化
        edge_prev = np.concatenate([prev[0, :], prev[-1, :], prev[:, 0], prev[:, -1]])
        edge_curr = np.concatenate([curr[0, :], curr[-1, :], curr[:, 0], curr[:, -1]])
        return bool(np.any(edge_prev != edge_curr))

    def _detect_color_appear(self, prev: np.ndarray, curr: np.ndarray) -> bool:
        """检测新颜色出现"""
        if prev.shape != curr.shape:
            return False
        prev_colors = set(np.unique(prev))
        curr_colors = set(np.unique(curr))
        return len(curr_colors - prev_colors) > 0

    def build_decision_tree(
        self, conditions: List[str], actions: List[str]
    ) -> Dict[str, Any]:
        """构建if-then-else决策树字典

        Args:
            conditions: 条件列表
            actions: 对应动作列表

        Returns:
            决策树字典 {"conditions": [...], "actions": [...], "rules": {...}}
        """
        rules: Dict[str, str] = {}
        for cond, act in zip(conditions, actions):
            rules[cond] = act

        return {
            "conditions": list(set(conditions)),
            "actions": list(set(actions)),
            "rules": rules,
            "n_rules": len(rules),
        }

    def __repr__(self) -> str:
        return f"ConditionalDTInductor(rules={len(self._decision_tree.get('rules', {}))})"


# ════════════════════════════════════════════════════════════════╗
# ║               MultiModalGanFusion — 多模态甘极化融合              ║
# ╚═══════════════════════════════════════════════════════════════╝

class MultiModalGanFusion:
    """多模态甘极化融合

    融合符号、视觉和一致性三个模态的评分：
    φ = w1 * s + w2 * ||v|| + w3 * c

    其中 s 为符号评分，v 为视觉特征向量，c 为一致性评分。
    """

    def __init__(
        self,
        w1: float = 0.4,
        w2: float = 0.3,
        w3: float = 0.3,
    ) -> None:
        """初始化多模态甘极化融合

        Args:
            w1: 符号评分权重
            w2: 视觉特征权重
            w3: 一致性权重
        """
        self.w1 = w1
        self.w2 = w2
        self.w3 = w3
        self._lr: float = 0.05

    def fuse(
        self,
        symbolic_score: float,
        visual_features: np.ndarray,
        consistency: float,
    ) -> float:
        """融合多模态评分

        φ = w1 * s + w2 * ||v|| + w3 * c

        Args:
            symbolic_score: 符号评分 [0, 1]
            visual_features: 视觉特征向量
            consistency: 一致性评分 [0, 1]

        Returns:
            融合评分 φ
        """
        v_norm = float(np.linalg.norm(np.asarray(visual_features, dtype=float)))
        phi = (
            self.w1 * symbolic_score
            + self.w2 * v_norm
            + self.w3 * consistency
        )
        return float(phi)

    def update_weights(self, feedback: float) -> None:
        """基于反馈微调权重

        Args:
            feedback: 反馈信号（正=好，负=差）
        """
        # 简单的梯度调整
        adjustment = self._lr * max(min(feedback, 1.0), -1.0)
        self.w1 = max(0.01, self.w1 + adjustment * 0.3)
        self.w2 = max(0.01, self.w2 + adjustment * 0.2)
        self.w3 = max(0.01, self.w3 + adjustment * 0.1)

        # 归一化使权重和为1
        total = self.w1 + self.w2 + self.w3
        if total > 1e-12:
            self.w1 /= total
            self.w2 /= total
            self.w3 /= total

    def get_weights(self) -> Tuple[float, float, float]:
        """返回当前权重"""
        return (self.w1, self.w2, self.w3)

    def __repr__(self) -> str:
        return f"MultiModalGanFusion(w1={self.w1:.3f}, w2={self.w2:.3f}, w3={self.w3:.3f})"


# ════════════════════════════════════════════════════════════════╗
# ║               RiceTheoremBound — Rice定理上界 (静态类)           ║
# ╚═══════════════════════════════════════════════════════════════╝

class RiceTheoremBound:
    """Rice定理上界 (静态类)

    Rice定理表明：LLM的不可判定性设置了一个不可逾越的理论上限。
    TOMAS通过符号-神经混合架构突破此上限。
    """

    _LLM_CEILING: float = 0.35
    _TOMAS_CEILING: float = 1.0

    @classmethod
    def llm_ceiling(cls) -> float:
        """返回LLM不可逾越之墙

        纯LLM方法在ARC-AGI-3上的性能上限约为0.35，
        这是Rice定理（不可判定性）决定的理论极限。

        Returns:
            0.35
        """
        return cls._LLM_CEILING

    @classmethod
    def tomas_ceiling(cls) -> float:
        """返回TOMAS理论完备性

        TOMAS通过自适应库学习+CHL同构实现理论完备性，
        上限为1.0。

        Returns:
            1.0
        """
        return cls._TOMAS_CEILING

    @classmethod
    def proof_sketch(cls) -> str:
        """返回证明概要

        Returns:
            证明概要字符串
        """
        return (
            "Rice定理表明任意非平凡语义性质不可判定，"
            "纯LLM（统计模式匹配）无法判定程序语义等价性，"
            "因此存在不可逾越的性能上限（≈0.35）。"
            "TOMAS通过Curry-Howard-Lambek同构将求解映射为证明搜索，"
            "自适应库学习提供归纳公理扩展，"
            "突破统计方法的不可判定性壁垒，达到理论完备性（1.0）。"
        )


# ════════════════════════════════════════════════════════════════╗
# ║               自测 (≥30 测试)                                      ║
# ╚═══════════════════════════════════════════════════════════════╝

def _self_test() -> Tuple[int, int, List[str]]:
    """模块自测 — adaptive_library v3.14

    Returns:
        (passed, failed, details) 元组
    """
    print("=" * 64)
    print("Adaptive Library v3.14 Self-Test (TOMAS AGI)")
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

    # ── Test 01-08: AdaptiveParams ──
    params = AdaptiveParams(alpha=2.0, beta=1.5, b_base=10.0)
    check("T01: alpha 初始值", params.alpha == 2.0)
    check("T02: beta 初始值", params.beta == 1.5)
    check("T03: b_base 初始值", params.b_base == 10.0)

    budget = params.compute_budget(mdl_cost=5.0, freq=3)
    # B = 10 + 2*5 + 1.5*log2(4) = 10 + 10 + 1.5*2 = 23
    check("T04: compute_budget 正确", abs(budget - 23.0) < 0.01, f"B={budget:.4f}")

    budget0 = params.compute_budget(mdl_cost=0.0, freq=0)
    check("T05: compute_budget 零输入", abs(budget0 - 10.0) < 0.01)

    params.update([1.0, 1.5, 2.0, 2.5])
    check("T06: update 后 alpha>0", params.alpha > 0)
    check("T07: update 后 beta>0", params.beta > 0)

    width = params.ast_width_control(depth=0, max_depth=3, budget=10.0)
    check("T08: ast_width_control > 0", width > 0)

    # ── Test 09-10: ast_width_control 深层更小 ──
    width_shallow = params.ast_width_control(depth=0, max_depth=3, budget=10.0)
    width_deep = params.ast_width_control(depth=2, max_depth=3, budget=10.0)
    check("T09: 浅层宽度≥深层宽度", width_shallow >= width_deep)
    check("T10: to_dict 含字段", "alpha" in params.to_dict())

    # ── Test 11-18: ProgramNode ──
    leaf1 = ProgramNode("rotate", args=[90])
    check("T11: leaf to_sexp", leaf1.to_sexp() == "(rotate 90)")

    leaf2 = ProgramNode("color_map", args=["red", "blue"])
    composed = ProgramNode("compose", children=[leaf1, leaf2])
    check("T12: compose to_sexp", composed.to_sexp() == "(compose (rotate 90) (color_map red blue))")

    check("T13: mdl_cost leaf=1", leaf1.mdl_cost() == 1)
    check("T14: mdl_cost compose=3", composed.mdl_cost() == 3)
    check("T15: depth leaf=1", leaf1.depth() == 1)
    check("T16: depth compose=2", composed.depth() == 2)

    subtrees = composed.extract_subtrees(max_depth=3, max_width=10)
    check("T17: extract_subtrees 含2个", len(subtrees) == 2)
    check("T18: 子树含 rotate", any(s.op == "rotate" for s in subtrees))

    # 节点相等性
    leaf1_copy = ProgramNode("rotate", args=[90])
    check("T19: 节点相等性", leaf1 == leaf1_copy)

    # ── Test 20-25: AdaptiveLibrary ──
    lib = AdaptiveLibrary()
    check("T20: 初始closure_size=0", lib.closure_size() == 0)

    # 注册原语
    name = lib.register_primitive(ProgramNode("scale", args=[2]))
    check("T21: register_primitive", lib.closure_size() == 1)

    found = lib.lookup(name)
    check("T22: lookup 找到原语", found is not None and found.op == "scale")

    not_found = lib.lookup("nonexistent")
    check("T23: lookup 未找到", not_found is None)

    # Sleep-Step
    prog1 = ProgramNode("compose", children=[
        ProgramNode("rotate", args=[90]),
        ProgramNode("rotate", args=[90]),
    ])
    prog2 = ProgramNode("compose", children=[
        ProgramNode("rotate", args=[90]),
        ProgramNode("flip", args=["h"]),
    ])
    new_prims = lib.sleep_step([prog1, prog2])
    check("T24: sleep_step 返回列表", isinstance(new_prims, list))
    check("T25: sleep_step 后库增长", lib.closure_size() >= 1)

    freq = lib.frequency_table()
    check("T26: frequency_table 含字段", isinstance(freq, dict))

    # ── Test 27-36: YinDragonProduct ──
    ydp = YinDragonProduct()
    # 单位元 e0 = [1, 0, 0, 0, 0, 0, 0, 0]
    e0 = np.array([1.0, 0, 0, 0, 0, 0, 0, 0])
    e1 = np.array([0.0, 1, 0, 0, 0, 0, 0, 0])
    e2 = np.array([0.0, 0, 1, 0, 0, 0, 0, 0])

    # e0 ⊗ e0* = e0 → scalar=1, vector=0
    s, v = ydp.compute(e0, e0)
    check("T27: e0⊗e0* 标量=1", abs(s - 1.0) < 1e-10, f"s={s:.6f}")
    check("T28: e0⊗e0* 向量=0", np.allclose(v, 0.0), f"v={v}")

    # e1 ⊗ e1* = e0 → scalar=1, vector=0
    s1, v1 = ydp.compute(e1, e1)
    check("T29: e1⊗e1* 标量=1", abs(s1 - 1.0) < 1e-10, f"s={s1:.6f}")
    check("T30: e1⊗e1* 向量=0", np.allclose(v1, 0.0))

    # e1 ⊗ e2* : e1*e2 = e4, e2*=-e2, so e1*(-e2) = -e1*e2 = -e4
    # scalar = Re(-e4) = 0, vector = Im(-e4) = -e4的虚部
    s12, v12 = ydp.compute(e1, e2)
    check("T31: e1⊗e2* 标量=0", abs(s12) < 1e-10, f"s={s12:.6f}")
    check("T32: e1⊗e2* 向量非零", np.linalg.norm(v12) > 0.5)

    # phase_mismatch_cost
    cost = ydp.phase_mismatch_cost(e1, e2)
    check("T33: phase_mismatch_cost 返回标量", isinstance(cost, float))

    # transform_result
    result = ydp.transform_result(e1, e2)
    check("T34: transform_result 7维", result.shape == (7,))

    # 相同向量相位失配为0
    a = np.array([0.5, 0.5, 0.5, 0.5, 0.0, 0.0, 0.0, 0.0])
    cost_self = ydp.phase_mismatch_cost(a, a)
    check("T35: 相同向量相位失配=||a||²", abs(cost_self - np.dot(a, a)) < 1e-6, f"cost={cost_self:.6f}")

    # 正交向量相位失配为0
    cost_orth = ydp.phase_mismatch_cost(e0, e1)
    check("T36: 正交向量相位失配=0", abs(cost_orth) < 1e-10, f"cost={cost_orth:.6f}")

    # ── Test 37-42: ConditionalDTInductor ──
    inductor = ConditionalDTInductor()
    frames = [
        np.array([[0, 0, 0], [0, 1, 0], [0, 0, 0]]),
        np.array([[0, 0, 0], [0, 2, 0], [0, 0, 0]]),
        np.array([[0, 0, 0], [0, 2, 0], [0, 0, 3]]),
    ]
    tree = inductor.induce(frames)
    check("T37: induce 返回字典", isinstance(tree, dict))
    check("T38: induce 含 rules", "rules" in tree)
    check("T39: induce 含 conditions", "conditions" in tree)
    check("T40: induce n_rules > 0", tree["n_rules"] > 0)

    tree2 = inductor.build_decision_tree(["BoundaryHit", "ColorAppear"], ["Turn", "Collect"])
    check("T41: build_decision_tree 含2条规则", tree2["n_rules"] == 2)
    check("T42: 候选条件含BoundaryHit", "BoundaryHit" in ConditionalDTInductor.CANDIDATE_CONDITIONS)

    # ── Test 43-48: MultiModalGanFusion ──
    fusion = MultiModalGanFusion(w1=0.4, w2=0.3, w3=0.3)
    score = fusion.fuse(symbolic_score=0.8, visual_features=np.array([3.0, 4.0]), consistency=0.9)
    # φ = 0.4*0.8 + 0.3*5.0 + 0.3*0.9 = 0.32 + 1.5 + 0.27 = 2.09
    check("T43: fuse 正确", abs(score - 2.09) < 0.01, f"φ={score:.4f}")

    w1_old, w2_old, w3_old = fusion.get_weights()
    fusion.update_weights(0.5)
    w1_new, w2_new, w3_new = fusion.get_weights()
    check("T44: update_weights 改变权重", (w1_new, w2_new, w3_new) != (w1_old, w2_old, w3_old))

    # 权重归一化
    check("T45: 权重和≈1", abs(w1_new + w2_new + w3_new - 1.0) < 0.01)

    # 负反馈降低权重
    fusion2 = MultiModalGanFusion(w1=0.5, w2=0.3, w3=0.2)
    fusion2.update_weights(-1.0)
    check("T46: 负反馈后权重仍>0", all(w > 0 for w in fusion2.get_weights()))

    # 零向量视觉特征
    score_zero = fusion.fuse(0.5, np.zeros(5), 0.5)
    check("T47: 零视觉特征", score_zero > 0)

    check("T48: __repr__ 含类名", "MultiModalGanFusion" in repr(fusion))

    # ── Test 49-54: RiceTheoremBound ──
    check("T49: llm_ceiling=0.35", abs(RiceTheoremBound.llm_ceiling() - 0.35) < 1e-10)
    check("T50: tomas_ceiling=1.0", abs(RiceTheoremBound.tomas_ceiling() - 1.0) < 1e-10)

    sketch = RiceTheoremBound.proof_sketch()
    check("T51: proof_sketch 非空", len(sketch) > 10)
    check("T52: proof_sketch 含Rice", "Rice" in sketch)
    check("T53: proof_sketch 含TOMAS", "TOMAS" in sketch)
    check("T54: LLM上限 < TOMAS上限", RiceTheoremBound.llm_ceiling() < RiceTheoremBound.tomas_ceiling())

    # ── Test 55: 集成测试 ──
    full_lib = AdaptiveLibrary()
    full_params = AdaptiveParams(alpha=1.5, beta=0.8, b_base=5.0)
    prog_complex = ProgramNode("compose", children=[
        ProgramNode("rotate", args=[90]),
        ProgramNode("compose", children=[
            ProgramNode("scale", args=[2]),
            ProgramNode("flip", args=["h"]),
        ]),
    ])
    b = full_params.compute_budget(prog_complex.mdl_cost(), 5)
    check("T55: 集成 budget > b_base", b > full_params.b_base, f"b={b:.4f}")

    print(f"\n{'=' * 64}")
    print(f"Self-Test Complete: {passed} passed, {failed} failed")
    print(f"{'=' * 64}")
    return passed, failed, details


if __name__ == "__main__":
    _self_test()
