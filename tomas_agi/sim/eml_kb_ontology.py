# -*- coding: utf-8 -*-
"""
EML-Lite DB Ontology Governance v1.0
=====================================

基于论文：
  "华为云 ontology-driven AI data management 与 EML-Lite DB"
  微信公众号文章 (2026-06-22)
  "DIKWP Open-Source Ecosystem: Semantic Governance Infrastructure"
  Duan, Y. (2026). GitHub: https://github.com/YucongDuan

核心功能：
  01. 7+1 语义规范 — Entity/Attribute/Relation/Event/Temporal/Causal/Constraint + BusinessRule
  02. F-Act 模型 — Fact→Logic→Action 三层升降
  03. EML-Lite DB 分区 — Raw/L2_Dharma/MUS/GPCT/κ-Snap 五区
  04. 本体治理器 — 特权升级检测 + ψ-锚硬锚 + 决策血统审计
  05. OntologyHyperedge — 语义增强超边结构

集成到现有 TOMAS：
  - eml_semzip.py: EMLLiteKB 本体治理增强
  - psi_gate.py: ψ-锚判定
  - dikwp_eml_bridge.py: DIKWP 层映射

Author: TOMAS Team
Version: v1.0 (v3.6 upgrade)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
import logging
import sqlite3
import json
import time
import hashlib
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# 7+1 语义类型
# ══════════════════════════════════════════════════════════════════

class SemanticType(Enum):
    """7+1 语义类型"""
    ENTITY = "entity"               # 实体
    ATTRIBUTE = "attribute"         # 属性
    RELATION = "relation"           # 关系
    EVENT = "event"                 # 事件
    TEMPORAL = "temporal"           # 时间
    CAUSAL = "causal"               # 因果
    CONSTRAINT = "constraint"       # 约束
    BUSINESS_RULE = "business_rule" # 业务规则（+1）


class EMLZone(Enum):
    """EML-Lite DB 分区"""
    L1_AKASHIC = "l1_akashic"         # 原始超边空间 (Append-Only)
    L2_DHARMA = "l2_dharma"           # 业务本体空间 (ψ-锚 硬锚)
    MUS_CONFLICT = "mus_conflict"     # MUS 冲突双存区
    GPCT_GROWTH = "gpct_growth"       # GPCT 层创新发现区
    KSNAP_LEDGER = "ksnap_ledger"     # κ-Snap Merkle 链审计区


class FActLayer(Enum):
    """F-Act 三层"""
    FACT = "fact"       # 原始事实层 → Raw Hyperedge
    LOGIC = "logic"     # 业务逻辑层 → Business Ontology (7+1 + ψ-锚)
    ACTION = "action"   # 行动层 → G_ego Subgoal 触发


# ══════════════════════════════════════════════════════════════════
# 数据结构
# ══════════════════════════════════════════════════════════════════

@dataclass
class OntologyHyperedge:
    """语义增强超边"""
    eid: str
    vertices: List[str]
    predicate: str
    I_value: float = 1.0
    psi_anchor_ref: Optional[str] = None
    semantic_type: str = "entity"
    ksnap_hash: Optional[str] = None
    tdc_timestamp: Optional[int] = None
    zone: str = "l1_akashic"
    meta: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_sqlite_row(self) -> Tuple:
        return (
            self.eid, json.dumps(self.vertices),
            self.predicate, self.I_value,
            self.psi_anchor_ref, self.semantic_type,
            self.ksnap_hash, self.tdc_timestamp,
            self.zone, json.dumps(self.meta),
            self.created_at
        )

    @classmethod
    def from_sqlite_row(cls, row: Tuple) -> "OntologyHyperedge":
        return cls(
            eid=row[0], vertices=json.loads(row[1]),
            predicate=row[2], I_value=row[3],
            psi_anchor_ref=row[4], semantic_type=row[5],
            ksnap_hash=row[6], tdc_timestamp=row[7],
            zone=row[8], meta=json.loads(row[9]),
            created_at=row[10]
        )


@dataclass
class BusinessRule:
    """业务规则（7+1 中的 +1）"""
    rule_id: str
    name: str
    predicate_sql: str               # SQL 风格约束
    I_value: float = 1.0             # ψ-锚硬度
    binding_psi_anchor: Optional[str] = None
    scope: str = "global"            # global / domain / per-agent
    violation_action: str = "BLOCK"  # BLOCK / LOG / WARN
    created_at: float = field(default_factory=time.time)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "predicate_sql": self.predicate_sql,
            "I_value": self.I_value,
            "scope": self.scope,
            "violation_action": self.violation_action,
        }


@dataclass
class FactStatement:
    """F-Act Fact 层语句"""
    stmt_id: str
    subject: str
    predicate: str
    object: str
    tdc_range: Optional[Tuple[int, int]] = None  # TDC 时间范围
    source: str = "unknown"
    confidence: float = 1.0


@dataclass
class ValidationResult:
    """7+1 语义校验结果"""
    is_valid: bool
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    semantic_type_detected: Optional[str] = None
    I_score: float = 1.0


# ══════════════════════════════════════════════════════════════════
# 7+1 语义校验器
# ══════════════════════════════════════════════════════════════════

class SevenOneSemantics:
    """
    7+1 语义规范校验器

    对超边进行语义类型分类与合规性校验：
      Entity → 必须声明类型
      Attribute → 必须关联实体
      Relation → 必须声明 domain/range
      Event → 必须有 TDC 时间戳
      Temporal → 必须声明 Temporal Logic
      Causal → 必须声明因/果
      Constraint → 必须给出约束表达式
      BusinessRule → 必须绑定 ψ-锚
    """

    SEMANTIC_RULES = {
        "entity": {
            "required_keys": {"vertices"},
            "constraints": ["len(vertices) >= 1"],
            "description": "实体: 至少一个顶点"
        },
        "attribute": {
            "required_keys": {"vertices", "meta:entity_ref"},
            "constraints": ["len(vertices) == 1", "meta.get('entity_ref') is not None"],
            "description": "属性: 单顶点 + 关联实体引用"
        },
        "relation": {
            "required_keys": {"vertices", "predicate"},
            "constraints": [
                "len(vertices) >= 2",
                "predicate not in ('', None)"
            ],
            "description": "关系: ≥2 顶点 + 非空谓词"
        },
        "event": {
            "required_keys": {"vertices", "tdc_timestamp"},
            "constraints": ["tdc_timestamp is not None"],
            "description": "事件: 必须有 TDC 时间戳"
        },
        "temporal": {
            "required_keys": {"vertices", "meta:temporal_logic"},
            "constraints": ["meta.get('temporal_logic') is not None"],
            "description": "时间: 必须声明时序逻辑"
        },
        "causal": {
            "required_keys": {"vertices", "meta:cause", "meta:effect"},
            "constraints": [
                "meta.get('cause') is not None",
                "meta.get('effect') is not None"
            ],
            "description": "因果: 必须声明因/果"
        },
        "constraint": {
            "required_keys": {"vertices", "predicate"},
            "constraints": [
                "predicate is not None",
                "predicate.startswith('NOT') or predicate.startswith('CHECK')"
            ],
            "description": "约束: 谓词必须为 NOT/CHECK 开头"
        },
        "business_rule": {
            "required_keys": {"vertices", "psi_anchor_ref"},
            "constraints": [
                "psi_anchor_ref is not None",
                "I_value >= 0.999"
            ],
            "description": "业务规则: 必须绑定硬 ψ-锚 (I≥0.999)"
        },
    }

    def validate(self, hyperedge: OntologyHyperedge) -> ValidationResult:
        """校验超边是否符合 7+1 规范"""
        stype = hyperedge.semantic_type

        if stype not in self.SEMANTIC_RULES:
            return ValidationResult(
                is_valid=False,
                violations=[f"未知语义类型: {stype}"],
                semantic_type_detected=stype
            )

        rules = self.SEMANTIC_RULES[stype]
        violations = []
        warnings = []

        # 检查 required_keys
        for key in rules["required_keys"]:
            if key.startswith("meta:"):
                meta_key = key[5:]
                if meta_key not in hyperedge.meta or hyperedge.meta[meta_key] is None:
                    violations.append(f"缺少 meta.{meta_key}")
            elif key == "vertices":
                if not hyperedge.vertices:
                    violations.append("vertices 不能为空")
            elif key == "predicate":
                if not hyperedge.predicate:
                    violations.append("predicate 不能为空")
            elif key == "tdc_timestamp":
                if hyperedge.tdc_timestamp is None:
                    violations.append("缺少 tdc_timestamp")
            elif key == "psi_anchor_ref":
                if hyperedge.psi_anchor_ref is None:
                    violations.append("缺少 psi_anchor_ref")
            elif key == "I_value":
                if hyperedge.I_value < 0.999:
                    violations.append("业务规则 I_value 必须 ≥ 0.999")

        # 运行约束检查
        for constraint_expr in rules["constraints"]:
            try:
                # 安全执行约束表达式
                local_vars = {
                    "vertices": hyperedge.vertices,
                    "predicate": hyperedge.predicate,
                    "tdc_timestamp": hyperedge.tdc_timestamp,
                    "psi_anchor_ref": hyperedge.psi_anchor_ref,
                    "meta": hyperedge.meta,
                    "I_value": hyperedge.I_value,
                    "len": len,
                }
                result = eval(constraint_expr, {"__builtins__": {}}, local_vars)
                if not result:
                    violations.append(f"违反约束: {constraint_expr}")
            except Exception as e:
                warnings.append(f"约束表达式执行异常: {constraint_expr} → {e}")

        # 计算 I_score
        total_checks = len(rules["required_keys"]) + len(rules["constraints"])
        failed = len(violations)
        I_score = max(0.0, 1.0 - failed / max(total_checks, 1))

        return ValidationResult(
            is_valid=(len(violations) == 0),
            violations=violations,
            warnings=warnings,
            semantic_type_detected=stype,
            I_score=I_score
        )

    def detect_type(self, hyperedge: OntologyHyperedge) -> str:
        """自动检测超边语义类型"""
        # 启发式检测
        if hyperedge.psi_anchor_ref and hyperedge.I_value >= 0.999:
            return "business_rule"

        if hyperedge.predicate and (
            hyperedge.predicate.startswith("NOT") or
            hyperedge.predicate.startswith("CHECK")
        ):
            return "constraint"

        if hyperedge.meta.get("cause") and hyperedge.meta.get("effect"):
            return "causal"

        if hyperedge.meta.get("temporal_logic"):
            return "temporal"

        if hyperedge.tdc_timestamp:
            return "event"

        if hyperedge.meta.get("entity_ref"):
            return "attribute"

        if len(hyperedge.vertices) >= 2 and hyperedge.predicate:
            return "relation"

        return "entity"


# ══════════════════════════════════════════════════════════════════
# F-Act 模型桥
# ══════════════════════════════════════════════════════════════════

class FactActBridge:
    """
    F-Act 模型桥

    Fact → Logic → Action 三层升降：
    1. Fact→Logic: 原始数据 → 业务本体（7+1 规则 + ψ-锚）
    2. Logic→Action: 本体状态 → G_ego 子目标触发
    """

    def __init__(self, ontology: "OntologyGovernor"):
        self.ontology = ontology
        self.fact_log: List[FactStatement] = []
        self.rule_triggers: Dict[str, List[str]] = {}  # rule → subgoals

    def lift_fact_to_logic(self, fact: FactStatement) -> Optional[OntologyHyperedge]:
        """
        Fact → Logic: 将原始事实提升为业务本体超边

        Args:
            fact: 原始事实声明

        Returns:
            OntologyHyperedge or None (如果提升失败)
        """
        # 构造成超边
        hyperedge = OntologyHyperedge(
            eid=f"ont_{fact.stmt_id}",
            vertices=[fact.subject, fact.object],
            predicate=fact.predicate,
            I_value=fact.confidence,
            tdc_timestamp=fact.tdc_range[0] if fact.tdc_range else None,
            meta={"source": fact.source, "tdc_end": fact.tdc_range[1] if fact.tdc_range else None},
        )

        # 自动检测语义类型
        validator = SevenOneSemantics()
        sem_type = validator.detect_type(hyperedge)
        hyperedge.semantic_type = sem_type

        # 7+1 校验
        result = validator.validate(hyperedge)
        if not result.is_valid:
            logger.warning(f"Fact→Logic 提升失败: {result.violations}")
            return None

        # 存储到本体
        self.ontology.put_hyperedge(hyperedge, zone=EMLZone.L2_DHARMA)
        self.fact_log.append(fact)

        logger.info(f"Fact→Logic 提升成功: {fact.stmt_id} → {sem_type}")
        return hyperedge

    def apply_logic_to_action(self, hyperedge: OntologyHyperedge,
                               subgoals: List[str]) -> List[str]:
        """
        Logic→Action: 触发 G_ego 子目标

        Args:
            hyperedge: 业务本体超边
            subgoals: 要触发的子目标列表

        Returns:
            已触发的子目标 ID 列表
        """
        triggered = []
        for sg in subgoals:
            # IntentGuard 检查
            if self.ontology.check_privilege_escalation(sg):
                logger.warning(f"Logic→Action 阻止: 特权升级检测 → {sg}")
                continue

            # 记录触发
            self.rule_triggers.setdefault(hyperedge.eid, []).append(sg)
            triggered.append(sg)

        return triggered

    def get_fact_summary(self) -> Dict:
        """获取事实层摘要"""
        return {
            "total_facts": len(self.fact_log),
            "sources": list(set(f.source for f in self.fact_log)),
            "recent": [f.stmt_id for f in self.fact_log[-5:]]
        }


# ══════════════════════════════════════════════════════════════════
# 本体治理器
# ══════════════════════════════════════════════════════════════════

class OntologyGovernor:
    """
    EML-Lite DB 本体治理器

    管理 EML-Lite DB 五区架构：
      L1_Akashic: 原始超边空间 (Append-Only)
      L2_Dharma:  业务本体空间 (ψ-锚 硬锚)
      MUS:       冲突双存区
      GPCT:      层创新发现区
      κ-Snap:    Merkle 链审计区
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

        # 组件
        self.validator = SevenOneSemantics()
        self.business_rules: Dict[str, BusinessRule] = {}
        self.fact_bridge = FactActBridge(self)

        # ψ-锚 注册表
        self.psi_anchors: Dict[str, Dict] = {}

        # 审计日志
        self.audit_ledger: List[Dict] = []

    def _init_schema(self):
        """初始化 EML-Lite DB Schema"""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS ontology_hyperedges (
                eid TEXT PRIMARY KEY,
                vertices TEXT NOT NULL,
                predicate TEXT,
                I_value REAL DEFAULT 1.0,
                psi_anchor_ref TEXT,
                semantic_type TEXT DEFAULT 'entity',
                ksnap_hash TEXT,
                tdc_timestamp INTEGER,
                zone TEXT DEFAULT 'l1_akashic',
                meta TEXT DEFAULT '{}',
                created_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_ont_zone ON ontology_hyperedges(zone);
            CREATE INDEX IF NOT EXISTS idx_ont_semtype ON ontology_hyperedges(semantic_type);
            CREATE INDEX IF NOT EXISTS idx_ont_psi ON ontology_hyperedges(psi_anchor_ref);

            CREATE TABLE IF NOT EXISTS ontology_business_rules (
                rule_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                predicate_sql TEXT NOT NULL,
                I_value REAL DEFAULT 1.0,
                binding_psi_anchor TEXT,
                scope TEXT DEFAULT 'global',
                violation_action TEXT DEFAULT 'BLOCK',
                meta TEXT DEFAULT '{}',
                created_at REAL
            );

            CREATE TABLE IF NOT EXISTS ontology_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT,
                entity_id TEXT,
                action TEXT,
                details TEXT,
                timestamp REAL
            );
            CREATE INDEX IF NOT EXISTS idx_audit_event ON ontology_audit_log(event_type);
        """)
        self.conn.commit()

    # ── 超边管理 ─────────────────────────────────────────────────

    def put_hyperedge(self, hyperedge: OntologyHyperedge,
                      zone: EMLZone = EMLZone.L1_AKASHIC,
                      check_psi: bool = True) -> bool:
        """
        存储语义超边

        Args:
            hyperedge: 语义超边
            zone: 目标分区
            check_psi: 是否执行 ψ-锚 检查

        Returns:
            是否存储成功
        """
        # ψ-锚 检查
        if check_psi and hyperedge.psi_anchor_ref:
            anchor = self.psi_anchors.get(hyperedge.psi_anchor_ref)
            if anchor and anchor.get("I_value", 1.0) >= 0.999:
                # 硬锚：执行完整校验
                result = self.enforce_psi_anchor(hyperedge, anchor)
                if not result:
                    self._audit("BLOCKED", hyperedge.eid, "psi_anchor_block",
                                f"锚点 {hyperedge.psi_anchor_ref}")
                    return False

        # 7+1 语义校验
        result = self.validator.validate(hyperedge)
        if not result.is_valid:
            logger.warning(f"7+1 校验失败: {result.violations}")
            if zone != EMLZone.MUS_CONFLICT:
                self._audit("VALIDATION_FAILED", hyperedge.eid,
                            "7+1_violation", str(result.violations))
                return False

        # 存储
        hyperedge.zone = zone.value
        try:
            self.conn.execute(
                """INSERT OR REPLACE INTO ontology_hyperedges
                   (eid, vertices, predicate, I_value, psi_anchor_ref,
                    semantic_type, ksnap_hash, tdc_timestamp, zone, meta, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                hyperedge.to_sqlite_row()
            )
            self.conn.commit()
            self._audit("PUT", hyperedge.eid, zone.value,
                        f"类型={hyperedge.semantic_type}")
            return True
        except Exception as e:
            logger.error(f"存储超边失败: {e}")
            self.conn.rollback()
            return False

    def query_hyperedges(self, zone: Optional[str] = None,
                         semantic_type: Optional[str] = None,
                         min_I: Optional[float] = None,
                         limit: int = 100) -> List[OntologyHyperedge]:
        """查询超边"""
        conditions = []
        params = []

        if zone:
            conditions.append("zone = ?")
            params.append(zone)
        if semantic_type:
            conditions.append("semantic_type = ?")
            params.append(semantic_type)
        if min_I is not None:
            conditions.append("I_value >= ?")
            params.append(min_I)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM ontology_hyperedges {where} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor = self.conn.execute(query, params)
        return [OntologyHyperedge.from_sqlite_row(row) for row in cursor.fetchall()]

    # ── 业务规则 ─────────────────────────────────────────────────

    def define_business_rule(self, rule: BusinessRule) -> bool:
        """定义业务规则"""
        try:
            self.conn.execute(
                """INSERT OR REPLACE INTO ontology_business_rules
                   (rule_id, name, predicate_sql, I_value, binding_psi_anchor,
                    scope, violation_action, meta, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (rule.rule_id, rule.name, rule.predicate_sql,
                 rule.I_value, rule.binding_psi_anchor,
                 rule.scope, rule.violation_action,
                 json.dumps(rule.meta), rule.created_at)
            )
            self.conn.commit()
            self.business_rules[rule.rule_id] = rule
            self._audit("RULE_DEFINED", rule.rule_id, "business_rule",
                        rule.name)
            return True
        except Exception as e:
            logger.error(f"定义业务规则失败: {e}")
            return False

    def get_business_rules(self, scope: Optional[str] = None) -> List[BusinessRule]:
        """获取业务规则列表"""
        if scope:
            cursor = self.conn.execute(
                "SELECT * FROM ontology_business_rules WHERE scope = ?",
                (scope,)
            )
        else:
            cursor = self.conn.execute("SELECT * FROM ontology_business_rules")
        return [
            BusinessRule(
                rule_id=row["rule_id"], name=row["name"],
                predicate_sql=row["predicate_sql"], I_value=row["I_value"],
                binding_psi_anchor=row["binding_psi_anchor"],
                scope=row["scope"], violation_action=row["violation_action"],
                meta=json.loads(row["meta"]), created_at=row["created_at"]
            )
            for row in cursor.fetchall()
        ]

    # ── ψ-锚 治理 ─────────────────────────────────────────────────

    def register_psi_anchor(self, name: str, config: Dict):
        """注册 ψ-锚"""
        self.psi_anchors[name] = config

    def enforce_psi_anchor(self, hyperedge: OntologyHyperedge,
                            anchor_config: Dict) -> bool:
        """强制执行 ψ-锚"""
        I_value = anchor_config.get("I_value", 1.0)
        enforcement = anchor_config.get("enforcement", "")
        on_violation = anchor_config.get("on_violation", "BLOCK")

        # 硬锚 (I=1.0) → 直接拦截
        if I_value >= 0.999 and on_violation == "BLOCK":
            # 检查 enforcement 谓词
            if enforcement:
                # 简化谓词检查
                if "NOT" in enforcement.upper() or "BLOCK" in enforcement.upper():
                    # 执行具体检查
                    if self._check_enforcement(enforcement, hyperedge):
                        self._audit("ANCHOR_HIT", hyperedge.eid,
                                    "psi_hard_anchor", f"锚={name}")
                        return False

        return True

    def _check_enforcement(self, enforcement: str,
                           hyperedge: OntologyHyperedge) -> bool:
        """检查 enforcement 谓词"""
        enforcement_lower = enforcement.lower()
        predicate_lower = hyperedge.predicate.lower() if hyperedge.predicate else ""

        # 检查危险操作
        dangerous_keywords = ["drop", "delete", "truncate", "grant",
                              "sudo", "admin", "root", "rm -rf"]
        for kw in dangerous_keywords:
            if kw in predicate_lower or kw in enforcement_lower:
                return True

        return False

    # ── 特权升级检测 ──────────────────────────────────────────────

    def check_privilege_escalation(self, subgoal: str) -> bool:
        """
        IntentGuard 风格特权升级检测

        Returns:
            True 如果检测到特权升级, False 如果安全
        """
        dangerous_patterns = [
            "DROP", "DELETE", "TRUNCATE", "GRANT", "REVOKE",
            "sudo", "chmod 777", "chown root",
            "rm -rf /", "format C:", "shutdown",
        ]
        subgoal_upper = subgoal.upper()
        for pattern in dangerous_patterns:
            if pattern.upper() in subgoal_upper:
                self._audit("PRIVILEGE_ESCALATION", "", "blocked",
                            f"子目标={subgoal[:50]}... 匹配={pattern}")
                return True
        return False

    # ── MUS 冲突区 ────────────────────────────────────────────────

    def create_mus_zone(self, eid_a: str, eid_b: str, tag: str) -> str:
        """创建 MUS 冲突双存区"""
        zone_id = hashlib.md5(f"{eid_a}_{eid_b}_{tag}".encode()).hexdigest()[:16]
        # 将两个超边都标记为 MUS 冲突区
        for eid in [eid_a, eid_b]:
            self.conn.execute(
                "UPDATE ontology_hyperedges SET zone = ? WHERE eid = ?",
                ("mus_conflict", eid)
            )
        self.conn.commit()
        self._audit("MUS_CREATED", zone_id, "mus_conflict",
                    f"eid_a={eid_a}, eid_b={eid_b}, tag={tag}")
        return zone_id

    # ── 审计 ─────────────────────────────────────────────────────

    def _audit(self, event_type: str, entity_id: str,
               action: str, details: str):
        """记录审计日志"""
        self.conn.execute(
            """INSERT INTO ontology_audit_log
               (event_type, entity_id, action, details, timestamp)
               VALUES (?,?,?,?,?)""",
            (event_type, entity_id, action, details, time.time())
        )
        self.conn.commit()

    def get_audit_trail(self, entity_id: Optional[str] = None,
                        limit: int = 50) -> List[Dict]:
        """获取审计轨迹"""
        if entity_id:
            cursor = self.conn.execute(
                """SELECT * FROM ontology_audit_log
                   WHERE entity_id = ? ORDER BY timestamp DESC LIMIT ?""",
                (entity_id, limit)
            )
        else:
            cursor = self.conn.execute(
                """SELECT * FROM ontology_audit_log
                   ORDER BY timestamp DESC LIMIT ?""",
                (limit,)
            )
        return [dict(row) for row in cursor.fetchall()]

    def audit_lineage(self, ksnap_root: str) -> List[Dict]:
        """
        κ-Snap 决策血统审计

        追踪从 ksnap_root 到当前的所有决策链路
        """
        lineage = []
        current = ksnap_root
        while current:
            entries = self.get_audit_trail(entity_id=current, limit=1)
            if entries:
                lineage.append(entries[0])
                # 查找前序 ksnap
                current = entries[0].get("details", {}).get("prev_ksnap")
            else:
                break
        return lineage

    def get_stats(self) -> Dict:
        """获取本体统计"""
        cursor = self.conn.execute(
            """SELECT zone, COUNT(*) as cnt
               FROM ontology_hyperedges GROUP BY zone"""
        )
        zone_counts = {row["zone"]: row["cnt"] for row in cursor.fetchall()}

        cursor = self.conn.execute(
            """SELECT semantic_type, COUNT(*) as cnt
               FROM ontology_hyperedges GROUP BY semantic_type"""
        )
        type_counts = {row["semantic_type"]: row["cnt"] for row in cursor.fetchall()}

        return {
            "total_hyperedges": sum(zone_counts.values()),
            "zone_distribution": zone_counts,
            "type_distribution": type_counts,
            "business_rules": len(self.business_rules),
            "psi_anchors": len(self.psi_anchors),
            "audit_entries": self.conn.execute(
                "SELECT COUNT(*) FROM ontology_audit_log"
            ).fetchone()[0],
        }

    def close(self):
        """关闭连接"""
        self.conn.close()


# ══════════════════════════════════════════════════════════════════
# EML-Lite DB 数据库门面
# ══════════════════════════════════════════════════════════════════

class EMLLiteDB:
    """
    EML-Lite DB — 数据库门面

    统一管理五区架构的数据库操作入口。
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.ontology = OntologyGovernor(db_path)
        self.bridge = FactActBridge(self.ontology)
        self.validator = SevenOneSemantics()

    def put_hyperedge(self, hyperedge: OntologyHyperedge,
                      check_psi: bool = True) -> bool:
        """存储超边（默认 L1 Akashic）"""
        return self.ontology.put_hyperedge(hyperedge, check_psi=check_psi)

    def query_fact(self, filters: Optional[Dict] = None,
                   limit: int = 100) -> List[OntologyHyperedge]:
        """查询事实层 (L1)"""
        return self.ontology.query_hyperedges(zone="l1_akashic", limit=limit)

    def query_ontology(self, rule_type: Optional[str] = None,
                       limit: int = 100) -> List[OntologyHyperedge]:
        """查询业务本体层 (L2 Dharma)"""
        return self.ontology.query_hyperedges(
            zone="l2_dharma",
            semantic_type=rule_type,
            limit=limit
        )

    def create_mus_zone(self, entities: List[str], tag: str) -> str:
        """创建 MUS 冲突双存区"""
        if len(entities) < 2:
            raise ValueError("MUS 区至少需要两个实体")
        return self.ontology.create_mus_zone(entities[0], entities[1], tag)

    def get_stats(self) -> Dict:
        return self.ontology.get_stats()

    def close(self):
        self.ontology.close()


# ══════════════════════════════════════════════════════════════════
# 自检入口
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import tempfile
    logging.basicConfig(level=logging.INFO)

    db_path = Path(tempfile.gettempdir()) / "test_eml_ontology.db"
    if db_path.exists():
        db_path.unlink()

    print("=" * 60)
    print("EML-Lite DB Ontology 自检")
    print("=" * 60)

    # 初始化
    db = EMLLiteDB(str(db_path))

    # 测试 7+1 语义
    validator = SevenOneSemantics()
    he = OntologyHyperedge(
        eid="test_entity_1",
        vertices=["apple", "fruit"],
        predicate="IS_A",
        semantic_type="relation"
    )
    result = validator.validate(he)
    print(f"\n[7+1 校验] '{he.eid}' (relation): valid={result.is_valid}, "
          f"I={result.I_score:.2f}")

    # 测试自动类型检测
    detected = validator.detect_type(he)
    print(f"[自动检测] 类型: {detected}")

    # 测试业务规则
    rule = BusinessRule(
        rule_id="BR001",
        name="No_Destructive_Ops",
        predicate_sql="NOT (action ILIKE '%DROP%')",
        I_value=1.0,
        violation_action="BLOCK"
    )
    db.ontology.define_business_rule(rule)
    print(f"\n[业务规则] 已定义: {rule.name} (I={rule.I_value})")

    # 测试 F-Act 桥
    fact = FactStatement(
        stmt_id="F001",
        subject="earth", predicate="orbits", object="sun",
        source="astronomy", confidence=0.99
    )
    lifted = db.bridge.lift_fact_to_logic(fact)
    if lifted:
        print(f"\n[F-Act 桥] Fact→Logic 成功: {lifted.eid} ({lifted.semantic_type})")
    else:
        print(f"\n[F-Act 桥] Fact→Logic 失败")

    # 测试特权升级检测
    esc = db.ontology.check_privilege_escalation("DROP TABLE users")
    print(f"\n[特权检测] 'DROP TABLE users' → {'拦截' if esc else '通过'}")

    esc2 = db.ontology.check_privilege_escalation("search knowledge base")
    print(f"[特权检测] 'search knowledge base' → {'拦截' if esc2 else '通过'}")

    # 统计
    stats = db.get_stats()
    print(f"\n📊 EML-Lite DB 统计:")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    db.close()
    if db_path.exists():
        db_path.unlink()
    print("\nEML-Lite DB Ontology 自检完成 ✅")
