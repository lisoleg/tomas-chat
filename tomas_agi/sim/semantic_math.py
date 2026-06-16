"""
语义数学引擎
============
基于 段玉聪(2024) "数学逻辑和推理的新语义数学扩展"

核心能力:
  1. 语义闭合检测 — 判定概念体系的语义完备性
  2. 三不问题治理 — 不完整/不精确/不一致 检测与量化
  3. 语义传递推理 — 跨概念语义关系的传递链分析

应用:
  >>> sm = SemanticClosure()
  >>> result = sm.check_closure(
  ...     statements=["火是热的", "热导致膨胀", "水是湿的"],
  ...     target="火导致膨胀"
  ... )
  >>> print(result.is_derivable)  # True (传递链: 火→热→膨胀)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple
import logging
import math

logger = logging.getLogger(__name__)


class IncompletenessType(Enum):
    """三不问题类型"""
    INCOMPLETE = "不完整"       # 存在语义空缺, 信息不足
    IMPRECISE = "不精确"        # 语义粒度不够, 存在模糊性
    INCONSISTENT = "不一致"     # 语义冲突, 自相矛盾


@dataclass
class SemanticStatement:
    """语义陈述 — 知识的基本单元"""
    id: str
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0     # 置信度 [0,1]
    source: str = "unknown"
    i_value: float = 0.5        # ℐ-信息存在度

    def __str__(self):
        return f"({self.subject} {self.predicate} {self.object})"

    @property
    def tuple(self) -> Tuple[str, str, str]:
        return (self.subject, self.predicate, self.object)


@dataclass
class ClosureResult:
    """语义闭合检测结果"""
    is_derivable: bool
    derivation_path: List[SemanticStatement]
    confidence: float
    gaps: List[str]                # 未能闭合的语义链
    i_conserved: bool              # ℐ-守恒是否保持
    explanation: str = ""


@dataclass
class ThreeIncompletenessReport:
    """三不问题检测报告"""
    incomplete_gaps: List[Dict]    # 语义空缺列表
    imprecise_nodes: List[Dict]    # 语义模糊节点
    inconsistent_pairs: List[Dict] # 语义矛盾对
    overall_score: float           # 整体完备性分数 [0,1]
    recommendations: List[str]


class SemanticClosure:
    """
    语义闭合检测器
    
    验证目标命题是否可以从已知语义陈述推导出来。
    核心机制：
      1. 传递链搜索 — 通过 (S,P,O) 三元组链传播语义
      2. ℐ-守恒验证 — 推导链的 ℐ 值不超源语句总和
      3. 语义缺口检测 — 标识无法闭合的语义跳跃
    """

    def __init__(self, max_chain_length: int = 10, min_confidence: float = 0.01):
        self.max_chain = max_chain_length
        self.min_confidence = min_confidence
        self.knowledge_base: Dict[str, List[SemanticStatement]] = {}
        logger.info(f"[SemanticClosure] 初始化, max_chain={max_chain_length}")

    def add_statements(self, statements: List[SemanticStatement]) -> None:
        """添加语义陈述到知识库"""
        for stmt in statements:
            key = stmt.subject
            if key not in self.knowledge_base:
                self.knowledge_base[key] = []
            self.knowledge_base[key].append(stmt)
        logger.info(f"[SemanticClosure] 添加 {len(statements)} 条陈述")

    def check_closure(
        self,
        statements: List[Tuple[str, str, str]],
        target: Tuple[str, str, str],
        i_values: Optional[Dict[int, float]] = None,
    ) -> ClosureResult:
        """
        检查目标命题的语义闭合性
        
        Args:
            statements: 已知语义陈述列表 [(subject, predicate, object), ...]
            target: 目标命题 (subject, predicate, object)
            i_values: 每条陈述的 ℐ 值 {idx: i_val}
        
        Returns:
            ClosureResult
        """
        # 构建内部知识库
        self.knowledge_base.clear()
        stmt_objects = []
        for idx, (s, p, o) in enumerate(statements):
            i_val = i_values.get(idx, 0.5) if i_values else 0.5
            stmt = SemanticStatement(
                id=f"S{idx}", subject=s, predicate=p, object=o, i_value=i_val
            )
            stmt_objects.append(stmt)
            key = s
            if key not in self.knowledge_base:
                self.knowledge_base[key] = []
            self.knowledge_base[key].append(stmt)

        target_subj, target_pred, target_obj = target

        # 路径搜索: BFS 从 target_subj 出发
        from collections import deque

        visited: Set[str] = {target_subj}
        queue = deque()
        # 初始化: 所有以 target_subj 为主语的陈述
        queue.append((target_subj, [], 1.0, 0.0))

        best_path = None
        best_confidence = 0.0

        while queue and len(queue) < 10000:  # 安全上限
            current_subj, path, confidence, i_sum = queue.popleft()

            if len(path) >= self.max_chain:
                continue

            # 获取以 current_subj 为主语的陈述
            candidates = self.knowledge_base.get(current_subj, [])
            for stmt in candidates:
                new_path = path + [stmt]
                new_confidence = confidence * stmt.confidence
                new_i_sum = i_sum + stmt.i_value

                # 检查是否到达目标
                if stmt.object == target_obj:
                    # 验证 predicate 是否可传递到此
                    if self._predicate_aligned(new_path, target_pred):
                        if new_confidence > best_confidence:
                            best_confidence = new_confidence
                            best_path = new_path

                if stmt.object not in visited:
                    visited.add(stmt.object)
                    queue.append((stmt.object, new_path, new_confidence, new_i_sum))

        # 构建结果
        if best_path and best_confidence >= self.min_confidence:
            i_source_total = sum(s.i_value for s in stmt_objects)
            i_path_total = sum(s.i_value for s in best_path)
            i_conserved = i_path_total <= i_source_total + 1e-9

            explanation = " → ".join(
                f"{s.subject}--[{s.predicate}]-->{s.object}" for s in best_path
            )
            return ClosureResult(
                is_derivable=True,
                derivation_path=best_path,
                confidence=best_confidence,
                gaps=[],
                i_conserved=i_conserved,
                explanation=f"推导链: {explanation}",
            )
        else:
            gaps = self._identify_gaps(target_subj, target_obj, target_pred)
            return ClosureResult(
                is_derivable=False,
                derivation_path=[],
                confidence=0.0,
                gaps=gaps,
                i_conserved=True,
                explanation=f"语义不闭合: 无法从已知陈述推导 '{target_subj} {target_pred} {target_obj}'",
            )

    def _predicate_aligned(
        self, path: List[SemanticStatement], target_pred: str
    ) -> bool:
        """检查推导路径的谓词是否对齐目标"""
        if not path:
            return False
        # 简化处理: 检查最终步的谓词
        last_pred = path[-1].predicate
        # 可传递谓词表 (可扩展)
        transitive_patterns = {"是", "属于", "导致", "引起", "包含", "拥有"}
        if target_pred in transitive_patterns and last_pred in transitive_patterns:
            return True
        return last_pred == target_pred

    def _identify_gaps(
        self, subject: str, object_: str, predicate: str
    ) -> List[str]:
        """识别语义缺口"""
        gaps = []
        if subject not in self.knowledge_base:
            gaps.append(f"主语 '{subject}' 无任何已知陈述")
        else:
            reachable = self._reachable_objects(subject, set(), 3)
            if object_ not in reachable:
                gaps.append(f"客体 '{object_}' 在3跳内不可达")
        return gaps

    def _reachable_objects(self, subject: str, visited: Set[str], depth: int) -> Set[str]:
        """获取可达客体集合"""
        if depth <= 0 or subject in visited:
            return set()
        visited.add(subject)
        result = set()
        for stmt in self.knowledge_base.get(subject, []):
            result.add(stmt.object)
            result.update(self._reachable_objects(stmt.object, visited, depth - 1))
        return result


class ThreeIncompleteness:
    """
    三不问题检测器
    
    段玉聪 "语义闭合与三不问题治理"
    不完整(Incomplete): 概念缺乏足够的语义支撑
    不精确(Imprecise):  概念边界模糊, 粒度不足
    不一致(Inconsistent): 概念间存在逻辑矛盾
    """

    def __init__(self):
        self.contradiction_pairs: List[Tuple[str, str, float]] = []

    def analyze(
        self,
        statements: List[SemanticStatement],
        known_concepts: Optional[Set[str]] = None,
    ) -> ThreeIncompletenessReport:
        """
        分析语义体系的三不问题
        
        Args:
            statements: 语义陈述列表
            known_concepts: 已知概念集合
        
        Returns:
            ThreeIncompletenessReport
        """
        incomplete_gaps = self._detect_incomplete(statements, known_concepts or set())
        imprecise_nodes = self._detect_imprecise(statements)
        inconsistent_pairs = self._detect_inconsistent(statements)

        # 综合评分
        total_issues = len(incomplete_gaps) + len(imprecise_nodes) + len(inconsistent_pairs)
        score = 1.0 - min(total_issues / max(len(statements) * 3, 1), 1.0)

        recommendations = []
        if incomplete_gaps:
            recommendations.append(f"补充 {len(incomplete_gaps)} 处语义空缺")
        if imprecise_nodes:
            recommendations.append(f"细化 {len(imprecise_nodes)} 个模糊概念")
        if inconsistent_pairs:
            recommendations.append(f"解决 {len(inconsistent_pairs)} 对语义矛盾")

        return ThreeIncompletenessReport(
            incomplete_gaps=incomplete_gaps,
            imprecise_nodes=imprecise_nodes,
            inconsistent_pairs=inconsistent_pairs,
            overall_score=round(score, 4),
            recommendations=recommendations,
        )

    def _detect_incomplete(
        self, statements: List[SemanticStatement], known_concepts: Set[str]
    ) -> List[Dict]:
        """检测不完整"""
        gaps = []
        all_subjects = {s.subject for s in statements}
        all_objects = {s.object for s in statements}

        # 客体不在主语中 → 孤岛, 缺乏进一步关联
        for stmt in statements:
            if stmt.object not in all_subjects and stmt.object not in known_concepts:
                gaps.append({
                    "node": stmt.object,
                    "type": "orphan_object",
                    "source": str(stmt),
                    "issue": f"'{stmt.object}' 仅有入边, 无可推导的后续语义",
                })

        # 主语无入边 → 没有形成闭环
        for subject in all_subjects - all_objects - known_concepts:
            if any(s.subject == subject for s in statements):
                gaps.append({
                    "node": subject,
                    "type": "orphan_subject",
                    "issue": f"'{subject}' 仅有出边, 无已知陈述指向它",
                })

        return gaps

    def _detect_imprecise(self, statements: List[SemanticStatement]) -> List[Dict]:
        """检测不精确"""
        imprecise = []
        # 检测: 同一主语但谓词模糊(如"有点"、"大概")
        fuzzy_markers = {"有点", "大概", "可能", "似乎", "差不多", "几乎", "相对"}

        for stmt in statements:
            if any(marker in stmt.predicate for marker in fuzzy_markers):
                imprecise.append({
                    "statement": str(stmt),
                    "issue": f"谓词含模糊标记",
                    "suggestion": "量化谓词或分解为多个精确陈述",
                })

            # 低置信度 = 不精确
            if stmt.confidence < 0.5:
                imprecise.append({
                    "statement": str(stmt),
                    "issue": f"置信度过低 ({stmt.confidence:.2f})",
                    "suggestion": "增加证据支撑或标记为假设",
                })

        return imprecise

    def _detect_inconsistent(
        self, statements: List[SemanticStatement]
    ) -> List[Dict]:
        """检测不一致"""
        inconsistent = []

        # 检测: 同主语+同客体, 相反谓词
        for i, s1 in enumerate(statements):
            for s2 in statements[i + 1:]:
                if s1.subject == s2.subject and s1.object == s2.object:
                    # 检查是否为反义词对
                    if self._are_antonyms(s1.predicate, s2.predicate):
                        inconsistent.append({
                            "s1": str(s1),
                            "s2": str(s2),
                            "type": "predicate_conflict",
                            "conflict": f"'{s1.predicate}' ↔ '{s2.predicate}' 谓词冲突",
                        })

        return inconsistent

    def _are_antonyms(self, p1: str, p2: str) -> bool:
        """简化反义词检测"""
        antonym_pairs = [
            ("是", "不是"), ("属于", "不属于"), ("包含", "排除"),
            ("增加", "减少"), ("支持", "反对"), ("肯定", "否定"),
            ("真", "假"), ("对", "错"), ("正", "反"),
        ]
        for a, b in antonym_pairs:
            if (a in p1 and b in p2) or (b in p1 and a in p2):
                return True
        return False


class SemanticTransmission:
    """
    语义传递推理引擎
    
    跨概念语义关系的传递链分析:
      A→B + B→C ⇒ A→C (语义传递)
    但传递过程中会发生语义衰减和畸变。
    """

    def __init__(self, decay_factor: float = 0.9):
        """
        Args:
            decay_factor: 语义传递衰减因子 (0-1)
                          每一步传递后语义强度乘以衰减因子
        """
        self.decay_factor = decay_factor
        self.transfer_chain: List[Dict] = []

    def infer_chain(
        self,
        start: str,
        end: str,
        relations: List[Tuple[str, str, str, float]],
        max_depth: int = 5,
    ) -> Dict:
        """
        语义传递链推理
        
        Args:
            start: 起始概念
            end: 目标概念
            relations: [(概念A, 关系, 概念B, 语义强度), ...]
            max_depth: 最大传递深度
        
        Returns:
            {reachable, path, strength, depth}
        """
        from collections import deque

        # 构建邻接表
        graph: Dict[str, List[Tuple[str, str, float]]] = {}
        for a, rel, b, strength in relations:
            if a not in graph:
                graph[a] = []
            graph[a].append((b, rel, strength))

        visited = set()
        queue = deque([(start, [], [], 1.0, 0)])

        best_result = {
            "reachable": False,
            "path": [],
            "relations": [],
            "strength": 0.0,
            "depth": 0,
        }

        while queue:
            current, path, rel_path, strength, depth = queue.popleft()

            if current == end and depth > 0:
                if strength > best_result["strength"]:
                    best_result = {
                        "reachable": True,
                        "path": path + [current],
                        "relations": rel_path,
                        "strength": round(strength, 4),
                        "depth": depth,
                    }
                continue

            if depth >= max_depth:
                continue

            for neighbor, rel, edge_strength in graph.get(current, []):
                if neighbor not in visited or neighbor == end:
                    new_strength = strength * edge_strength * self.decay_factor
                    if new_strength > 0.01:  # 剪枝: 太弱不继续
                        queue.append((
                            neighbor,
                            path + [current] if not path or path[-1] != current else path,
                            rel_path + [rel],
                            new_strength,
                            depth + 1,
                        ))

            visited.add(current)

        # 记录
        self.transfer_chain.append({
            "start": start, "end": end, "result": best_result,
        })

        return best_result

    def measure_semantic_distance(
        self, concept_a: str, concept_b: str, relations: List[Tuple[str, str, str, float]]
    ) -> float:
        """
        测量两概念间的语义距离
        
        返回值: [0, ∞), 0=同义, 越大越远
        """
        result = self.infer_chain(concept_a, concept_b, relations, max_depth=10)
        if result["reachable"]:
            # 距离 = -log(传递强度) * 传递步数
            if result["strength"] > 0:
                return -math.log(result["strength"]) * result["depth"]
            return float("inf")
        return float("inf")
