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
    Float, Index, UniqueConstraint, event, text as sa_text
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
            connect_args={"check_same_thread": False},
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
