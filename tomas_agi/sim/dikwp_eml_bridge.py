"""
DIKWP-EML 桥接器
=================
连接段玉聪 DIKWP 五层模型与 TOMAS EML 超图基础设施。

核心转换:
  1. DIKWP Layer → EML ℐ-bin 映射
  2. DIKWP 陈述 → EML 超边转换
  3. EML 超图 → DIKWP 层快照提取
  4. DIKWP 反馈 → EML 权重调节

应用:
  >>> bridge = DIKWPEMLBridge()
  >>> bridge.ingest_dikwp_statements([
  ...     SemanticStatement("S0", "火", "导致", "热", i_value=0.6)
  ... ])
  >>> profile = bridge.get_dikwp_profile()
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
import logging

logger = logging.getLogger(__name__)

# 内部导入
try:
    from .dikwp_mapper import DIKWPLayer, DIKWPMapper, IDensityBin
    from .semantic_math import SemanticStatement, SemanticClosure
except ImportError:
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from dikwp_mapper import DIKWPLayer, DIKWPMapper, IDensityBin  # type: ignore
    from semantic_math import SemanticStatement, SemanticClosure  # type: ignore


@dataclass
class EMLHyperEdge:
    """EML 超边 — 桥接器使用的简化表示"""
    id: str
    nodes: List[str]
    i_value: float
    dikwp_layer: Optional[DIKWPLayer] = None
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EMLNode:
    """EML 节点 — 桥接器使用的简化表示"""
    id: str
    label: str
    i_value: float
    dikwp_layer: Optional[DIKWPLayer] = None


class DIKWPEMLBridge:
    """
    DIKWP ↔ EML 双向桥接器
    
    将 DIKWP 五层的语义陈述转化为 EML 超图结构,
    并将 EML 超图的 ℐ-bin 分布反哺回 DIKWP 层分类。
    """

    def __init__(self, custom_thresholds: Optional[Dict] = None):
        self.mapper = DIKWPMapper(custom_thresholds=custom_thresholds)
        self.closure = SemanticClosure()
        
        # EML 数据存储
        self.nodes: Dict[str, EMLNode] = {}
        self.edges: Dict[str, EMLHyperEdge] = {}
        
        # DIKWP 陈述存储
        self.statements: List[SemanticStatement] = []
        
        # 转换记录
        self.conversion_log: List[Dict] = []
        
        logger.info("[DIKWP-EML] 桥接器初始化完成")

    # === DIKWP → EML 转换 ===

    def ingest_dikwp_statements(
        self, statements: List[SemanticStatement]
    ) -> Dict[DIKWPLayer, int]:
        """
        将 DIKWP 语义陈述转换为 EML 节点和超边
        
        Args:
            statements: DIKWP 陈述列表
        
        Returns:
            各层新增元素计数
        """
        layer_counts = {layer: 0 for layer in DIKWPLayer}

        for stmt in statements:
            layer = self.mapper.classify(stmt.i_value)
            layer_counts[layer] += 1

            # 创建/更新节点
            for concept in [stmt.subject, stmt.object]:
                if concept not in self.nodes:
                    node = EMLNode(
                        id=f"n_{concept}",
                        label=concept,
                        i_value=stmt.i_value,
                        dikwp_layer=layer,
                    )
                    self.nodes[concept] = node
                else:
                    # 更新最大的 ℐ 值和对应层级
                    if stmt.i_value > self.nodes[concept].i_value:
                        self.nodes[concept].i_value = stmt.i_value
                        self.nodes[concept].dikwp_layer = layer

            # 创建超边
            edge_id = f"e_{stmt.subject}_{stmt.predicate}_{stmt.object}"
            edge = EMLHyperEdge(
                id=edge_id,
                nodes=[stmt.subject, stmt.object],
                i_value=stmt.i_value,
                dikwp_layer=layer,
                meta={
                    "predicate": stmt.predicate,
                    "confidence": stmt.confidence,
                    "source": stmt.source,
                },
            )
            self.edges[edge_id] = edge

        self.statements.extend(statements)
        self.closure.add_statements(statements)

        logger.info(
            f"[DIKWP-EML] 摄入 {len(statements)} 条陈述, "
            f"分布: {', '.join(f'{k.value}:{v}' for k,v in layer_counts.items())}"
        )
        return layer_counts

    def convert_eml_to_dikwp(
        self, vertices: Optional[Dict] = None, hyperedges: Optional[List] = None
    ) -> Dict[DIKWPLayer, List[Any]]:
        """
        从 EML 超图提取 DIKWP 层分类
        
        Args:
            vertices: EML 顶点字典 (兼容外部 EML 加载器)
            hyperedges: EML 超边列表
        
        Returns:
            {DIKWPLayer: [元素列表]}
        """
        result: Dict[DIKWPLayer, List[Any]] = {
            layer: [] for layer in DIKWPLayer
        }

        if vertices:
            for node_id, node_data in vertices.items():
                i_val = getattr(node_data, 'i_value', 
                                getattr(node_data, 'weight', 0.5))
                if isinstance(i_val, (int, float)):
                    layer = self.mapper.classify(min(max(i_val, 0), 1))
                    result[layer].append({
                        "id": str(node_id),
                        "type": "vertex",
                        "i_value": i_val,
                    })

        if hyperedges:
            for edge in hyperedges:
                i_val = getattr(edge, 'i_value',
                                getattr(edge, 'weight', 0.5))
                if isinstance(i_val, (int, float)):
                    layer = self.mapper.classify(min(max(i_val, 0), 1))
                    result[layer].append({
                        "id": str(getattr(edge, 'id', 'unknown')),
                        "type": "hyperedge",
                        "i_value": i_val,
                    })

        return result

    # === EML → DIKWP 反馈 ===

    def apply_dikwp_feedback(
        self, layer_feedbacks: List[Tuple[DIKWPLayer, DIKWPLayer, float]]
    ) -> List[Dict]:
        """
        应用 DIKWP 双向反馈到 EML 权重
        
        Args:
            layer_feedbacks: [(源层, 目标层, ℐ-梯度), ...]
                如 [(W, K, -0.2)] 表示 Wisdom 抑制 Knowledge 权重
        
        Returns:
            受影响的边列表
        """
        affected = []
        for source, target, gradient in layer_feedbacks:
            record = self.mapper.backpropagate(source, target, gradient)
            
            # 找到属于目标层的边并调整
            for edge_id, edge in self.edges.items():
                if edge.dikwp_layer == target:
                    old_i = edge.i_value
                    edge.i_value = max(0.0, min(1.0, edge.i_value + gradient))
                    
                    affected.append({
                        "edge_id": edge_id,
                        "old_i_value": round(old_i, 4),
                        "new_i_value": round(edge.i_value, 4),
                        "delta": round(gradient, 4),
                        "feedback": f"{source.value}→{target.value}",
                    })
                    
                    # 可能改变了层级
                    new_layer = self.mapper.classify(edge.i_value)
                    if new_layer != edge.dikwp_layer:
                        affected[-1]["layer_changed"] = True
                        affected[-1]["from_layer"] = edge.dikwp_layer.value
                        affected[-1]["to_layer"] = new_layer.value
                        edge.dikwp_layer = new_layer
        
        logger.info(
            f"[DIKWP-EML] 反馈应用: {len(layer_feedbacks)} 条, "
            f"影响 {len(affected)} 条边"
        )
        return affected

    # === 综合查询 ===

    def get_dikwp_profile(self) -> Dict:
        """获取当前 DIKWP-EML 完整画像"""
        mapper_profile = self.mapper.get_profile()
        feedback_summary = self.mapper.get_feedback_summary()

        # 按层统计 EML 数据
        eml_by_layer = {layer.value: {"nodes": 0, "edges": 0} for layer in DIKWPLayer}
        for node in self.nodes.values():
            if node.dikwp_layer:
                eml_by_layer[node.dikwp_layer.value]["nodes"] += 1
        for edge in self.edges.values():
            if edge.dikwp_layer:
                eml_by_layer[edge.dikwp_layer.value]["edges"] += 1

        return {
            "total_statements": len(self.statements),
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "dikwp_layers": mapper_profile,
            "eml_by_layer": eml_by_layer,
            "feedback": feedback_summary,
        }

    def check_semantic_closure(
        self, target_subject: str, target_predicate: str, target_object: str
    ) -> Dict[str, Any]:
        """
        检查目标命题在当前知识库中的语义闭合性
        
        Args:
            target_subject: 目标主语
            target_predicate: 目标谓词
            target_object: 目标宾语
        
        Returns:
            闭合检查结果
        """
        # 从 EML 边构建三元组
        triples = []
        i_values = {}
        for idx, edge in enumerate(self.edges.values()):
            if len(edge.nodes) >= 2:
                triples.append((
                    edge.nodes[0],
                    edge.meta.get("predicate", "关联"),
                    edge.nodes[1],
                ))
                i_values[idx] = edge.i_value

        result = self.closure.check_closure(
            statements=triples,
            target=(target_subject, target_predicate, target_object),
            i_values=i_values,
        )

        return {
            "is_derivable": result.is_derivable,
            "confidence": result.confidence,
            "i_conserved": result.i_conserved,
            "derivation_path": str(result.explanation),
            "gaps": result.gaps,
        }

    def get_layer_transition_map(self) -> Dict[str, List[str]]:
        """
        获取 DIKWP 层级转换图 — 哪些概念在层间移动
        
        Returns:
            {概念: [源层→目标层, ...]}
        """
        transitions = {}
        for node_id, node in self.nodes.items():
            # 检查是否有边改变了此概念所在层级
            related_edges = [
                e for e in self.edges.values()
                if node_id in e.nodes
            ]
            edge_layers = {e.dikwp_layer for e in related_edges if e.dikwp_layer}
            if len(edge_layers) > 1:
                transitions[node_id] = [l.value for l in edge_layers]
        
        return transitions
