"""
Palantir 本体映射器 — Ontology → EML 超图桥接

将 Palantir 风格的本体 (实体 + 关系 + 属性) 映射到
TOMAS EML 超图的顶点、超边、ℐ-权重。

参考: TOMAS vs Palantir 本体开发 (章锋, 2026)
      DIKWP 五层 ⇔ EML ℐ-bin 分度类
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================
# 本体模型
# ============================================================

class OntoEntityType(Enum):
    """本体实体类型"""
    CONCEPT = "concept"           # 概念
    OBJECT = "object"             # 物理对象
    PROCESS = "process"           # 过程
    PROPERTY = "property"         # 属性
    RELATION = "relation"         # 关系
    AGENT = "agent"               # 智能体
    EVENT = "event"               # 事件


@dataclass
class OntoEntity:
    """本体实体"""
    id: str
    name: str
    entity_type: OntoEntityType
    properties: Dict[str, Any] = field(default_factory=dict)
    aliases: List[str] = field(default_factory=list)
    confidence: float = 1.0        # 本体置信度 → TOMAS ℐ-值


@dataclass
class OntoRelation:
    """本体关系"""
    id: str
    source_id: str
    target_id: str
    relation_type: str             # e.g. "is_a", "part_of", "causes", "has_property"
    properties: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0        # → TOMAS ℐ-值


@dataclass
class Ontology:
    """本体定义"""
    name: str
    domain: str
    entities: Dict[str, OntoEntity] = field(default_factory=dict)
    relations: List[OntoRelation] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_entity(self, entity: OntoEntity):
        self.entities[entity.id] = entity

    def add_relation(self, relation: OntoRelation):
        self.relations.append(relation)


# ============================================================
# Palantir Pipeline → EML 映射器
# ============================================================

class PalantirEMLMapper:
    """Palantir 本体 → EML 超图 映射器

    Palantir Pipeline 风格:
      1. 实体提取 → EML 顶点
      2. 关系映射 → EML 超边
      3. 属性注入 → ℐ-权重
      4. DIKWP 层分派 → ℐ-bin 分类
    """

    # 关系类型 → DIKWP 层映射
    RELATION_DIKWP_MAP = {
        "is_a": "K",            # 分类关系 → Knowledge
        "part_of": "I",         # 组成关系 → Information
        "causes": "K",          # 因果关系 → Knowledge
        "has_property": "I",    # 属性关系 → Information
        "produces": "W",        # 产生关系 → Wisdom
        "regulates": "W",       # 调节关系 → Wisdom
        "depends_on": "K",      # 依赖关系 → Knowledge
        "instance_of": "D",     # 实例化 → Data
        "purpose_of": "P",      # 目的关系 → Purpose
        "evaluates": "W",       # 评估关系 → Wisdom
    }

    # 实体类型 → 默认 ℐ-值
    ENTITY_DEFAULT_I = {
        OntoEntityType.CONCEPT: 0.7,
        OntoEntityType.OBJECT: 0.8,
        OntoEntityType.PROCESS: 0.6,
        OntoEntityType.PROPERTY: 0.4,
        OntoEntityType.RELATION: 0.5,
        OntoEntityType.AGENT: 0.9,
        OntoEntityType.EVENT: 0.7,
    }

    def __init__(self, dikwp_mapper=None, theta_dead: float = 0.15):
        self.dikwp_mapper = dikwp_mapper
        self.theta_dead = theta_dead
        self.ontology: Optional[Ontology] = None

    def load_ontology(self, ontology: Ontology):
        """加载本体"""
        self.ontology = ontology
        logger.info(f"[Palantir] 加载本体: {ontology.name} "
                    f"({len(ontology.entities)} 实体, {len(ontology.relations)} 关系)")

    def load_from_json(self, path: str) -> Ontology:
        """从 JSON 文件加载本体"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        ontology = Ontology(
            name=data.get("name", "unnamed"),
            domain=data.get("domain", ""),
            metadata=data.get("metadata", {}),
        )

        for e_data in data.get("entities", []):
            entity = OntoEntity(
                id=e_data["id"],
                name=e_data["name"],
                entity_type=OntoEntityType(e_data.get("type", "concept")),
                properties=e_data.get("properties", {}),
                aliases=e_data.get("aliases", []),
                confidence=e_data.get("confidence", 1.0),
            )
            ontology.add_entity(entity)

        for r_data in data.get("relations", []):
            relation = OntoRelation(
                id=r_data["id"],
                source_id=r_data["source_id"],
                target_id=r_data["target_id"],
                relation_type=r_data["type"],
                properties=r_data.get("properties", {}),
                confidence=r_data.get("confidence", 1.0),
            )
            ontology.add_relation(relation)

        self.load_ontology(ontology)
        return ontology

    # ----------------------------------------------------------
    # 核心映射
    # ----------------------------------------------------------

    def map_to_eml(self) -> Dict:
        """将本体完整映射为 EML 超图

        Returns:
            {
                "vertices": [...],
                "edges": [...],
                "dikwp_layers": {...},
                "i_distribution": {...},
            }
        """
        if not self.ontology:
            return {"vertices": [], "edges": [], "dikwp_layers": {}, "i_distribution": {}}

        vertices = []
        edges = []
        dikwp_layers = {}
        i_distribution = {}

        # 实体 → 顶点
        for entity in self.ontology.entities.values():
            i_val = entity.confidence * self.ENTITY_DEFAULT_I.get(
                entity.entity_type, 0.5
            )
            vertex = {
                "id": entity.id,
                "name": entity.name,
                "entity_type": entity.entity_type.value,
                "i_val": i_val,
                "aliases": entity.aliases,
                "properties": entity.properties,
            }
            vertices.append(vertex)

        # 关系 → 超边
        for rel in self.ontology.relations:
            source = self.ontology.entities.get(rel.source_id)
            target = self.ontology.entities.get(rel.target_id)
            if not source or not target:
                continue

            i_val = rel.confidence * 0.5  # 关系 ℐ 默认 0.5 × confidence
            dikwp_layer = self.RELATION_DIKWP_MAP.get(rel.relation_type, "K")

            edge = {
                "id": rel.id,
                "nodes": [rel.source_id, rel.target_id],
                "relation_type": rel.relation_type,
                "i_val": i_val,
                "dikwp_layer": dikwp_layer,
                "source_name": source.name,
                "target_name": target.name,
            }

            # 死零过滤
            if i_val < self.theta_dead:
                edge["dead_zero"] = True
                edge["status"] = "rejected"
                logger.debug(f"[Palantir] DEAD_ZERO {rel.id}: "
                            f"I={i_val:.4f} < θ={self.theta_dead}")
            else:
                edge["dead_zero"] = False
                edge["status"] = "active"

            edges.append(edge)

            # DIKWP 层统计
            dikwp_layers[dikwp_layer] = dikwp_layers.get(dikwp_layer, 0) + 1

        # ℐ 分布统计
        i_values = [e["i_val"] for e in edges]
        i_distribution = {
            "min": min(i_values) if i_values else 0,
            "max": max(i_values) if i_values else 0,
            "mean": sum(i_values) / max(len(i_values), 1),
            "dead_zero_count": sum(1 for e in edges if e.get("dead_zero")),
            "active_count": sum(1 for e in edges if not e.get("dead_zero")),
        }

        eml_graph = {
            "vertices": vertices,
            "edges": edges,
            "dikwp_layers": dikwp_layers,
            "i_distribution": i_distribution,
            "ontology_name": self.ontology.name,
            "domain": self.ontology.domain,
        }

        logger.info(f"[Palantir] 映射完成: {len(vertices)} 顶点, "
                    f"{len(edges)} 超边, "
                    f"dead_zero={i_distribution['dead_zero_count']}")

        return eml_graph

    def get_dikwp_distribution(self) -> Dict[str, Any]:
        """获取 DIKWP 层分布 (用于饼图)"""
        eml = self.map_to_eml()
        layers = eml.get("dikwp_layers", {})

        total = sum(layers.values()) or 1
        distribution = {}
        for layer in ["D", "I", "K", "W", "P"]:
            count = layers.get(layer, 0)
            distribution[layer] = {
                "count": count,
                "percentage": round(count / total * 100, 1),
            }

        # 层描述
        layer_names = {
            "D": "数据(Data)", "I": "信息(Info)",
            "K": "知识(Knowledge)", "W": "智慧(Wisdom)", "P": "目的(Purpose)",
        }
        for layer, info in distribution.items():
            info["name"] = layer_names.get(layer, layer)

        return {
            "distribution": distribution,
            "total_edges": total,
            "ontology_name": self.ontology.name if self.ontology else "none",
        }

    # ----------------------------------------------------------
    # 本体→DIKWP 层分派
    # ----------------------------------------------------------

    def classify_to_dikwp(self, entity: OntoEntity) -> str:
        """将实体分派到 DIKWP 层

        基于 ℐ-值 + 实体类型的启发式分类
        """
        i_val = entity.confidence * self.ENTITY_DEFAULT_I.get(entity.entity_type, 0.5)

        if i_val < 0.15:
            return "D"  # 裸数据
        elif i_val < 0.35:
            return "I"  # 信息
        elif i_val < 0.65:
            return "K"  # 知识
        elif i_val < 0.85:
            return "W"  # 智慧
        else:
            return "P"  # 目的

    def build_palantir_pipeline(self, raw_data: List[Dict]) -> Dict:
        """Palantir 风格 4 阶段 Pipeline

        1. Extract: 从原始数据提取实体和关系
        2. Transform: 转换为本体表示
        3. Map: 映射为 EML 超图
        4. Load: 产出可查询的 EML 图
        """
        pipeline_log = []

        # Stage 1: Extract
        entities = {}
        relations = []
        for item in raw_data:
            if "entity" in item:
                e = OntoEntity(
                    id=item.get("id", f"e_{len(entities)}"),
                    name=item["entity"],
                    entity_type=OntoEntityType(item.get("type", "concept")),
                    confidence=item.get("confidence", 0.8),
                )
                entities[e.id] = e
            if "relation" in item:
                relations.append(OntoRelation(
                    id=item.get("id", f"r_{len(relations)}"),
                    source_id=item["source"],
                    target_id=item["target"],
                    relation_type=item["relation"],
                    confidence=item.get("confidence", 0.8),
                ))
        pipeline_log.append(f"Extract: {len(entities)} entities, {len(relations)} relations")

        # Stage 2: Transform
        ontology = Ontology(
            name="palantir_pipeline",
            domain=raw_data[0].get("domain", "") if raw_data else "",
            entities=entities,
            relations=relations,
        )
        pipeline_log.append(f"Transform: ontology '{ontology.name}' created")

        # Stage 3: Map
        self.load_ontology(ontology)
        eml_graph = self.map_to_eml()
        pipeline_log.append(f"Map: {len(eml_graph['vertices'])} vertices, "
                           f"{len(eml_graph['edges'])} edges")

        # Stage 4: Load
        pipeline_log.append("Load: EML graph ready for inference")
        eml_graph["pipeline_log"] = pipeline_log

        return eml_graph


# ============================================================
# 导出
# ============================================================

__all__ = [
    "OntoEntityType",
    "OntoEntity",
    "OntoRelation",
    "Ontology",
    "PalantirEMLMapper",
]
