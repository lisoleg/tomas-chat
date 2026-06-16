"""
TOMAS-MemOS 矛盾检测器（三层架构）

三层检测架构：
- Layer 1: 否定词检测（V1.1）— 快速检测肯定/否定矛盾
- Layer 2: NLP 主谓宾提取（V1.2）— 使用 jieba 提取 SPO 三元组
- Layer 3: EML 语义相似度（V2.0）— 查询 EML 图的 asym 值

Author: Zhang Feng / TOMAS Team
Date: 2026-06-16
"""

from typing import Dict, Tuple, Optional, List, Set
from dataclasses import dataclass
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class SPO:
    """主谓宾三元组"""
    subject: str    # 主语（如 "心"）
    predicate: str  # 谓语（如 "主"）
    object: str     # 宾语（如 "神明"）
    
    def __eq__(self, other):
        if not isinstance(other, SPO):
            return False
        return (self.subject == other.subject and
                self.predicate == other.predicate and
                self.object == other.object)
    
    def __repr__(self):
        return f"SPO({self.subject}, {self.predicate}, {self.object})"


class ContradictionDetector:
    """
    矛盾检测器（三层架构）
    
    层级：
    - Layer 1: 否定词检测（V1.1）
    - Layer 2: NLP 主谓宾提取（V1.2）
    - Layer 3: EML 语义相似度（V2.0）
    """
    
    def __init__(self, enable_nlp: bool = True, enable_eml: bool = False,
                 eml_path: Optional[str] = None,
                 concepts_json_path: Optional[str] = None):
        """
        初始化矛盾检测器
        
        Args:
            enable_nlp: 是否启用 NLP 主谓宾提取（V1.2）
            enable_eml: 是否启用 EML 语义相似度（V2.0）
            eml_path: EML 二进制文件路径（.eml）
            concepts_json_path: 概念名称 JSON 文件路径（.concepts.json）
        """
        self.enable_nlp = enable_nlp
        self.enable_eml = enable_eml
        self.eml_path = eml_path
        self.concepts_json_path = concepts_json_path
        
        # 否定词词典（Layer 1）
        self.negation_words = ["不", "不是", "不可能", "错误", "不对", "否认", "没有", "并非"]
        
        # NLP 工具（Layer 2）
        if enable_nlp:
            self._init_nlp()
        
        # EML 加载器（Layer 3）
        self.eml_loaded = False
        self._concept_to_vids: Dict[str, List[int]] = {}
        self._edge_asym: Dict[Tuple[int, int], float] = {}
        self._concept_adj: Dict[str, Set[str]] = {}
        if enable_eml:
            self._init_eml()
    
    def is_contradictory(self, relation1: str, relation2: str) -> bool:
        """
        检测两个关系是否矛盾（主入口）
        
        检测顺序：
        1. Layer 1: 否定词检测（快速）
        2. Layer 2: NLP 主谓宾提取（中等）
        3. Layer 3: EML 语义相似度（慢速）
        
        Args:
            relation1: 第一个关系文本
            relation2: 第二个关系文本
            
        Returns:
            是否矛盾
        """
        # Layer 1: 否定词检测
        if self._layer1_negation(relation1, relation2):
            return True
        
        # Layer 2: NLP 主谓宾提取
        if self.enable_nlp:
            if self._layer2_nlp(relation1, relation2):
                return True
        
        # Layer 3: EML 语义相似度
        if self.enable_eml:
            if self._layer3_eml(relation1, relation2):
                return True
        
        return False
    
    def _layer1_negation(self, relation1: str, relation2: str) -> bool:
        """
        Layer 1: 否定词检测
        
        规则：
        - 如果一个关系包含否定词，另一个不包含 → 可能矛盾
        - 如果两个关系包含不同的否定词组合 → 可能矛盾
        
        Args:
            relation1: 第一个关系文本
            relation2: 第二个关系文本
            
        Returns:
            是否检测到否定词矛盾
        """
        # 提取两个关系中的否定词
        neg1 = [w for w in self.negation_words if w in relation1]
        neg2 = [w for w in self.negation_words if w in relation2]
        
        # 情况1：一个包含否定词，另一个不包含
        if neg1 and not neg2:
            return True
        if neg2 and not neg1:
            return True
        
        # 情况2：两个都包含否定词，但是不同的否定词
        if neg1 and neg2:
            # 如果否定词集合不同，可能矛盾
            if set(neg1) != set(neg2):
                return True
        
        return False
    
    def _init_nlp(self):
        """初始化 NLP 工具（jieba + 规则）"""
        try:
            import jieba
            self.jieba = jieba
            self.jieba_initialized = True
        except ImportError:
            print("Warning: jieba not installed. Run: pip install jieba")
            self.jieba = None
            self.jieba_initialized = False
            self.enable_nlp = False
    
    def _extract_spo(self, relation: str) -> SPO:
        """
        提取主谓宾三元组（简化版）

        使用 jieba 分词 + 规则提取：
        - 主语：通常是第一个词（或 "的" 前的词）
        - 谓语：通常是动词或 "主"/"是"/"为" 等
        - 宾语：通常是最后一个词（或 "的" 后的词）

        增强：对 "X主Y，..." 模式，宾语截断到逗号/句号前
        对 "X为Y，..." 同理

        Args:
            relation: 关系文本（如 "心主神明"）

        Returns:
            SPO 三元组
        """
        # 预处理：截断到第一个标点，避免宾语包含后缀描述
        clean_relation = relation
        for sep in ("，", "。", "；", "：", ",", ".", ";"):
            idx = relation.find(sep)
            if idx > 2:  # 确保至少有 3 个字符的主体
                clean_relation = relation[:idx]
                break

        if len(clean_relation) >= 3:
            # 三字符结构：ABC → 主语=A, 谓语=B, 宾语=C
            subject = clean_relation[0]
            predicate = clean_relation[1]
            obj = clean_relation[2:]
        else:
            # 回退：整个关系作为主语
            subject = clean_relation
            predicate = ""
            obj = ""

        return SPO(subject=subject, predicate=predicate, object=obj)
    
    def _layer2_nlp(self, relation1: str, relation2: str) -> bool:
        """
        Layer 2: 基于主谓宾检测矛盾
        
        规则：
        - 如果主语不同，但谓语+宾语相同 → 矛盾
        - 如果主语+宾语相同，但谓语相反 → 矛盾
        - 如果主语+谓语相同，但宾语不同 → 矛盾（新增）
        
        Args:
            relation1: 第一个关系文本
            relation2: 第二个关系文本
            
        Returns:
            是否检测到主谓宾矛盾
        """
        # 提取主谓宾
        spo1 = self._extract_spo(relation1)
        spo2 = self._extract_spo(relation2)
        
        # 规则1：主语不同，但谓语+宾语相同 → 矛盾
        if (spo1.subject != spo2.subject and
            spo1.predicate == spo2.predicate and
            spo1.object == spo2.object):
            return True
        
        # 规则2：主语+宾语相同，但谓语相反 → 矛盾
        if (spo1.subject == spo2.subject and
            spo1.object == spo2.object and
            spo1.predicate != spo2.predicate):
            # 检查谓语是否相反（简化：检查是否一个包含否定词）
            pred1_neg = any(w in spo1.predicate for w in self.negation_words)
            pred2_neg = any(w in spo2.predicate for w in self.negation_words)
            if pred1_neg != pred2_neg:
                return True
        
        # 规则3：主语+谓语相同，但宾语不同 → 矛盾（新增）
        if (spo1.subject == spo2.subject and
            spo1.predicate == spo2.predicate and
            spo1.object != spo2.object):
            return True
        
        return False
    
    def _init_eml(self):
        """
        初始化 EML 加载器（V2.0）
        
        从 EML 二进制文件加载概念图，构建三套查找结构：
        1. _concept_to_vids: 概念名称 → 顶点 ID 列表
        2. _edge_asym: (vid1, vid2) → asym 值
        3. _concept_adj: 概念名称 → 相邻概念集合
        
        用于 Layer 3 的 EML 语义矛盾检测。
        """
        if not self.eml_path:
            logger.warning("EML path not set, Layer 3 disabled")
            self.eml_loaded = False
            return
        
        eml_file = Path(self.eml_path)
        if not eml_file.exists():
            logger.warning(f"EML file not found: {self.eml_path}")
            self.eml_loaded = False
            return
        
        try:
            from .eml_dimred.hyperedge import load_eml_graph
            
            vertices, edges, metadata = load_eml_graph(
                str(eml_file),
                self.concepts_json_path
            )
            
            # 构建概念名称 → 顶点 ID 映射
            self._concept_to_vids = {}
            for v in vertices:
                if v.concept:
                    self._concept_to_vids.setdefault(v.concept, []).append(v.vid)
            
            # 构建边 asym 查找表（双向）
            self._edge_asym = {}
            for e in edges:
                if len(e.nodes) >= 2:
                    for i, n1 in enumerate(e.nodes):
                        for n2 in e.nodes[i+1:]:
                            self._edge_asym[(n1, n2)] = e.asym
                            self._edge_asym[(n2, n1)] = e.asym
            
            # 构建概念邻接表
            self._concept_adj = {}
            vid_to_concept = {v.vid: v.concept for v in vertices if v.concept}
            for e in edges:
                concepts_in_edge = []
                for n in e.nodes:
                    c = vid_to_concept.get(n)
                    if c:
                        concepts_in_edge.append(c)
                for c1 in concepts_in_edge:
                    for c2 in concepts_in_edge:
                        if c1 != c2:
                            self._concept_adj.setdefault(c1, set()).add(c2)
            
            self.eml_loaded = True
            asym_edges = sum(1 for asym in self._edge_asym.values() if abs(asym) > 1e-6) // 2
            logger.info(
                f"EML loaded: {len(vertices)} vertices, {len(edges)} edges, "
                f"{len(self._concept_to_vids)} named concepts, "
                f"{asym_edges} MUS-capable edges"
            )
            
        except Exception as e:
            logger.error(f"Failed to load EML: {e}")
            self.eml_loaded = False
    
    def _extract_named_concepts(self, relation: str) -> List[str]:
        """
        从关系文本中提取可匹配 EML 的概念名称
        
        策略：使用滑动窗口匹配 EML 概念词典中的已知概念。
        优先匹配长概念（如"量子电动力学"优先于"量子"）。
        
        Args:
            relation: 关系文本
            
        Returns:
            匹配到的概念名称列表
        """
        if not self.eml_loaded or not self._concept_to_vids:
            return []
        
        all_concepts = sorted(
            self._concept_to_vids.keys(),
            key=len, reverse=True  # 长概念优先
        )
        
        matched = []
        remaining = relation
        for concept in all_concepts:
            if concept in remaining:
                matched.append(concept)
                # 不删除已匹配部分，允许重叠匹配
        return matched
    
    def _layer3_eml(self, relation1: str, relation2: str) -> bool:
        """
        Layer 3: EML 语义相似度检测（V2.0）
        
        检测策略：
        1. 从两个关系中提取 EML 已知概念
        2. **直接 MUS 边检测**：如果两个概念之间有直接边且 asym != 0 → 矛盾
        3. **共享邻居检测**：如果两个概念连接到同一个第三概念 → 潜在矛盾
        
        原理：EML 图中的 asym 标记了非 Boolean 关系（MUS 互斥稳态）。
        当两个概念被标记为 asym ≠ 0 时，它们可以双存但不能简单合并，
        这在逻辑上等价于矛盾。
        
        Args:
            relation1: 第一个关系文本
            relation2: 第二个关系文本
            
        Returns:
            是否检测到 EML 语义矛盾
        """
        if not self.eml_loaded:
            return False
        
        # 提取概念
        concepts1 = self._extract_named_concepts(relation1)
        concepts2 = self._extract_named_concepts(relation2)
        
        if not concepts1 or not concepts2:
            return False
        
        # 策略 1：直接 MUS 边检测
        for c1 in concepts1:
            for c2 in concepts2:
                if c1 == c2:
                    continue
                vids1 = self._concept_to_vids.get(c1, [])
                vids2 = self._concept_to_vids.get(c2, [])
                for vid1 in vids1:
                    for vid2 in vids2:
                        asym = self._edge_asym.get((vid1, vid2), 0.0)
                        if abs(asym) > 1e-6:
                            logger.debug(
                                f"EML contradiction: '{c1}' <-> '{c2}' "
                                f"(asym={asym:.4f})"
                            )
                            return True
        
        # 策略 2：共享邻居检测
        for c1 in concepts1:
            for c2 in concepts2:
                if c1 == c2:
                    continue
                adj1 = self._concept_adj.get(c1, set())
                adj2 = self._concept_adj.get(c2, set())
                shared = adj1 & adj2
                if shared:
                    logger.debug(
                        f"EML contradiction (shared neighbor): "
                        f"'{c1}' and '{c2}' both connect to {shared}"
                    )
                    return True
        
        return False
