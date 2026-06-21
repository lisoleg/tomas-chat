"""
TOMAS 数据库模型 — SQLAlchemy ORM
===================================

7 张表：corpus_entries, conflict_decisions, chat_sessions,
        api_keys, knowledge_items, knowledge_triples, settings

数据库文件：D:/tomas-data/tomas.db（D 盘大空间）
"""

import os
from datetime import datetime

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime,
    Float, Boolean, Index, UniqueConstraint, event, text as sa_text
)
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker
from sqlalchemy.pool import QueuePool

# ---- 数据库路径 ----
DB_DIR = os.environ.get("TOMAS_DB_DIR", "D:/tomas-data")
DB_PATH = os.path.join(DB_DIR, "tomas.db")

# ---- 引擎 & 会话 ----
_engine = None
_session_factory = None

def get_engine():
    """获取（或创建）SQLAlchemy 引擎，首次调用时自动建目录建表"""
    global _engine, _session_factory
    if _engine is None:
        os.makedirs(DB_DIR, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{DB_PATH}",
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            connect_args={
                "check_same_thread": False,
                "timeout": 30,  # busy_timeout 30秒
            },
            echo=False,
        )
        _session_factory = sessionmaker(bind=_engine)

        # 首次创建时自动建表
        Base.metadata.create_all(_engine)

    return _engine

def get_session():
    """获取线程安全的 scoped session"""
    get_engine()  # 确保引擎已初始化
    return scoped_session(_session_factory)()

# ---- 声明式基类 ----
class Base(DeclarativeBase):
    pass


# ======================== 模型定义 ========================

class CorpusEntry(Base):
    __tablename__ = "corpus_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(Text, nullable=False)
    domain = Column(Text, default="")
    concepts_count = Column(Integer, default=0)
    relations_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class ConflictDecision(Base):
    __tablename__ = "conflict_decisions"
    __table_args__ = (
        UniqueConstraint("conflict_id", name="uq_conflict_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    conflict_id = Column(Text, nullable=False)
    concept_name = Column(Text, default="")
    domain = Column(Text, default="")
    decision = Column(Text, default="")
    resolved_at = Column(DateTime, default=datetime.utcnow)


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_session_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Text, nullable=False)
    title = Column(Text, default="")
    messages = Column(Text, default="[]")       # JSON 字符串（兼容旧格式）
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (
        UniqueConstraint("key_name", name="uq_key_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    key_name = Column(Text, nullable=False)
    key_value = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.utcnow)


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    concept = Column(Text, nullable=False)
    content = Column(Text, default="")
    source = Column(Text, default="")
    type = Column(Text, default="concept")
    created_at = Column(DateTime, default=datetime.utcnow)


class KnowledgeTriple(Base):
    __tablename__ = "knowledge_triples"
    __table_args__ = (
        Index("idx_triples_subject", "subject"),
        Index("idx_triples_object", "object"),
        Index("idx_triples_sp", "subject", "predicate"),
        Index("idx_triples_po", "predicate", "object"),
        Index("idx_triples_i_weight", "i_weight"),       # κ-Gate 剪枝索引
        # INSERT OR IGNORE 去重依赖此唯一约束
        UniqueConstraint("subject", "predicate", "object", name="uq_triple_spo"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    subject   = Column(Text, nullable=False)
    predicate = Column(Text, nullable=False)
    object    = Column(Text, nullable=False)
    i_weight  = Column(Float, default=1.0, server_default=sa_text("1.0"), nullable=False)   # I(X) 信息存在度（κ-Gate 用）
    created_at = Column(DateTime, default=datetime.utcnow)


class Setting(Base):
    __tablename__ = "settings"
    __table_args__ = (
        UniqueConstraint("key", name="uq_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(Text, nullable=False)
    value = Column(Text, default="")


# ======================= 超图数据模型 (Hypergraph) =======================
# 基于 TOMAS EML 超图五元组: H = (V, E, ℑ, κ, Asym)
# 参考: eml_dimred/hyperedge.py, eml_dimred/matroid.py
# 参考: ChainDB 关系索引范式 (lisoleg/chain-db)

class Vertex(Base):
    """
    EML 顶点 — 概念/实体/状态节点
    对应 eml_dimred/hyperedge.py::EMLVertex
    """
    __tablename__ = "vertices"
    __table_args__ = (
        UniqueConstraint("concept", name="uq_vertex_concept"),
        Index("idx_vertex_concept", "concept"),
        Index("idx_vertex_i_val", "i_val"),
    )

    vid = Column(Integer, primary_key=True, autoincrement=False)  # 顶点 ID (显式指定)
    concept = Column(Text, nullable=False, default="")
    # 八元数 φ 场 (8 个分量, 对应 EMLVertex.phi)
    phi_b0 = Column(Float, default=0.0)
    phi_b1 = Column(Float, default=0.0)
    phi_b2 = Column(Float, default=0.0)
    phi_b3 = Column(Float, default=0.0)
    phi_b4 = Column(Float, default=0.0)
    phi_b5 = Column(Float, default=0.0)
    phi_b6 = Column(Float, default=0.0)
    phi_b7 = Column(Float, default=0.0)
    i_val = Column(Float, default=0.0)           # ℑ(v) — 信息存在度
    degree_class = Column(Integer, default=0)       # 度类 C_i (按 ℑ 分层)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_vertex_concept", "concept"),
        Index("idx_vertex_i_val", "i_val"),
    )


class HyperEdge(Base):
    """
    EML 超边 — n 元语义关系 (n-ary)
    对应 eml_dimred/hyperedge.py::HypEdge
    注: nodes 存为 JSON 数组; 高效节点查询用 hyperedge_nodes junction 表
    """
    __tablename__ = "hyperedges"

    eid = Column(Text, primary_key=True)            # 超边唯一标识 (对应 HypEdge.eid)
    arity = Column(Integer, nullable=False)          # 元数 n (len(nodes))
    nodes = Column(Text, nullable=False, default="[]")  # JSON 数组: [vid1, vid2, ...]
    i_val = Column(Float, default=1.0)            # ℑ(e) — 信息存在度 [0, 1]
    asym = Column(Float, default=0.0)              # Asym — 非结合残联 (0=Boolean, ≠0=MUS-capable)
    weight = Column(Float, default=1.0)            # 关联权重
    delta_weight = Column(Float, default=0.0)       # delta_weight
    source = Column(Integer, default=None)            # 有向边源节点 (None=无向)
    target = Column(Integer, default=None)            # 有向边目标节点
    edge_type = Column(Text, default="generic")      # 边类型 (来自 ChainDB 7种 + 自定义)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_hyperedge_i_val", "i_val"),
        Index("idx_hyperedge_arity", "arity"),
        Index("idx_hyperedge_type", "edge_type"),
    )


class HyperEdgeNode(Base):
    """
    HyperEdge-Vertex junction 表 — 支持高效 "查找包含顶点 X 的所有超边"
    这是超图数据库的关键索引结构。
    """
    __tablename__ = "hyperedge_nodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    eid = Column(Text, nullable=False, index=True)    # 对应 hyperedges.eid
    vid = Column(Integer, nullable=False, index=True)  # 对应 vertices.vid
    position = Column(Integer, default=0)             # 节点在 nodes 元组中的位置

    __table_args__ = (
        Index("idx_hen_eid_vid", "eid", "vid"),
        Index("idx_hen_vid", "vid"),
    )


class MatroidCircuit(Base):
    """
    拟阵回路缓存表 — 持久化 MUS-Circuit / Paradox-Circuit 检测结果
    对应 eml_dimred/matroid.py::Matroid.identify_circuits()
    """
    __tablename__ = "matroid_circuits"

    circuit_id = Column(Text, primary_key=True)         # 回路唯一标识
    edge_ids = Column(Text, nullable=False)             # JSON 数组: [eid1, eid2, ...]
    circuit_type = Column(Text, nullable=False)         # 'MUS' | 'Paradox'
    detected_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_circuit_type", "circuit_type"),
    )


# ======================= MNQ-Deep 训练运行记录 =======================

class MNQTrainingRun(Base):
    """MNQ-Deep 训练运行记录"""
    __tablename__ = 'mnq_training_runs'
    
    id = Column(Integer, primary_key=True)
    dataset = Column(String(255))
    optimizer = Column(String(50), default='mnq_deep')
    epochs = Column(Integer, default=100)
    batch_size = Column(Integer, default=32)
    iwpu_bits = Column(Integer, default=8)
    final_loss = Column(Float, nullable=True)
    status = Column(String(20), default='pending')
    frozen = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
