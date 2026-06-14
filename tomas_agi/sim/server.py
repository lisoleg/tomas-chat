"""
TOMAS 后端 API 服务器 — SQLAlchemy ORM 版
============================================

提供 RESTful API 用于数据存储，使用 SQLite + SQLAlchemy ORM。
数据库文件默认在 D:/tomas-data/tomas.db。
"""

import json
from datetime import datetime

from flask import Flask, request, jsonify
from flask_cors import CORS
from sqlalchemy import func, text, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from models import (
    DB_PATH, get_session,
    CorpusEntry, ConflictDecision, ChatSession,
    ApiKey, KnowledgeItem, KnowledgeTriple, Setting,
)

app = Flask(__name__)
CORS(app)

# ---- 工具函数 ----

def _row_to_dict(row):
    """将 SQLAlchemy 模型实例转为 dict（通用）"""
    if row is None:
        return None
    d = {}
    for col in row.__table__.columns:
        d[col.name] = getattr(row, col.name)
    return d

def _dt_to_ts(dt):
    """datetime → 毫秒时间戳"""
    if dt is None:
        return 0
    if isinstance(dt, str):
        try:
            dt = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            return 0
    return int(dt.timestamp() * 1000)

def _ts_to_dt(ts):
    """毫秒时间戳 → datetime"""
    if ts and isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts / 1000)
    return None


# ==================== 语料 API ====================

@app.route("/api/corpus", methods=["GET"])
def get_corpus():
    session = get_session()
    try:
        rows = session.query(CorpusEntry).order_by(CorpusEntry.created_at.desc()).all()
        entries = [
            {
                "id": r.id,
                "text": r.text,
                "domain": r.domain,
                "conceptsCount": r.concepts_count,
                "relationsCount": r.relations_count,
                "createdAt": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ]
        return jsonify({"success": True, "data": entries})
    finally:
        session.close()


@app.route("/api/corpus", methods=["POST"])
def add_corpus():
    data = request.json
    session = get_session()
    try:
        text = data.get("text", data.get("name", ""))
        domain = data.get("domain", data.get("content", "general"))
        concepts_count = data.get("conceptsCount", 0)
        relations_count = data.get("relationsCount", 0)

        entry = CorpusEntry(
            text=text,
            domain=domain,
            concepts_count=concepts_count,
            relations_count=relations_count,
        )
        session.add(entry)
        session.commit()
        entry_id = entry.id
        return jsonify({"success": True, "id": entry_id})
    finally:
        session.close()


@app.route("/api/corpus/<int:entry_id>", methods=["DELETE"])
def delete_corpus(entry_id):
    session = get_session()
    try:
        session.query(CorpusEntry).filter_by(id=entry_id).delete()
        session.commit()
        return jsonify({"success": True})
    finally:
        session.close()


# ==================== 冲突决策 API ====================

@app.route("/api/conflicts", methods=["GET"])
def get_conflicts():
    session = get_session()
    try:
        rows = session.query(ConflictDecision).all()
        decisions = [
            {
                "conflictId": r.conflict_id,
                "conceptName": r.concept_name,
                "domain": r.domain,
                "decision": r.decision,
                "resolvedAt": r.resolved_at.isoformat() if r.resolved_at else "",
            }
            for r in rows
        ]
        return jsonify({"success": True, "data": decisions})
    finally:
        session.close()


@app.route("/api/conflicts", methods=["POST"])
def add_conflict():
    data = request.json
    session = get_session()
    try:
        stmt = sqlite_insert(ConflictDecision).values(
            conflict_id=data["conflictId"],
            concept_name=data.get("conceptName", ""),
            domain=data.get("domain", ""),
            decision=data["decision"],
            resolved_at=datetime.utcnow(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["conflict_id"],
            set_=dict(
                decision=stmt.excluded.decision,
                resolved_at=datetime.utcnow(),
            ),
        )
        session.execute(stmt)
        session.commit()
        return jsonify({"success": True})
    finally:
        session.close()


# ==================== 聊天会话 API ====================

@app.route("/api/sessions", methods=["GET"])
def get_sessions():
    session = get_session()
    try:
        rows = session.query(ChatSession).order_by(ChatSession.updated_at.desc()).all()
        sessions = [
            {
                "sessionId": r.session_id,
                "title": r.title,
                "messages": json.loads(r.messages) if r.messages else [],
                "createdAt": r.created_at.isoformat() if r.created_at else "",
                "updatedAt": r.updated_at.isoformat() if r.updated_at else "",
            }
            for r in rows
        ]
        return jsonify({"success": True, "data": sessions})
    finally:
        session.close()


@app.route("/api/sessions", methods=["POST"])
def save_sessions():
    data = request.json
    session = get_session()
    try:
        for s in data:
            stmt = sqlite_insert(ChatSession).values(
                session_id=s["sessionId"],
                title=s.get("title", ""),
                messages=json.dumps(s.get("messages", [])),
                updated_at=datetime.utcnow(),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["session_id"],
                set_=dict(
                    title=stmt.excluded.title,
                    messages=stmt.excluded.messages,
                    updated_at=datetime.utcnow(),
                ),
            )
            session.execute(stmt)
        session.commit()
        return jsonify({"success": True})
    finally:
        session.close()


@app.route("/api/sessions/<session_id>", methods=["DELETE"])
def delete_session(session_id):
    session = get_session()
    try:
        session.query(ChatSession).filter_by(session_id=session_id).delete()
        session.commit()
        return jsonify({"success": True})
    finally:
        session.close()


# ==================== API Key API ====================

@app.route("/api/apikey", methods=["GET"])
def get_api_key():
    session = get_session()
    try:
        row = session.query(ApiKey).filter_by(key_name="deepseek").first()
        return jsonify({"success": True, "data": row.key_value if row else ""})
    finally:
        session.close()


@app.route("/api/apikey", methods=["POST"])
def save_api_key():
    data = request.json
    session = get_session()
    try:
        stmt = sqlite_insert(ApiKey).values(
            key_name="deepseek",
            key_value=data.get("apiKey", ""),
            updated_at=datetime.utcnow(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["key_name"],
            set_=dict(
                key_value=stmt.excluded.key_value,
                updated_at=datetime.utcnow(),
            ),
        )
        session.execute(stmt)
        session.commit()
        return jsonify({"success": True})
    finally:
        session.close()


# ==================== 知识条目 API ====================

@app.route("/api/knowledge", methods=["GET"])
def get_knowledge():
    session = get_session()
    try:
        rows = session.query(KnowledgeItem).all()
        items = [
            {
                "id": r.id,
                "type": r.type if r.type else "concept",
                "label": r.concept,
                "extra": r.content if r.content else "",
                "domain": r.source if r.source else "",
                "createdAt": _dt_to_ts(r.created_at),
            }
            for r in rows
        ]
        return jsonify({"success": True, "data": items})
    finally:
        session.close()


@app.route("/api/knowledge", methods=["POST"])
def add_knowledge():
    items = request.json
    session = get_session()
    try:
        ids = []
        triple_count = 0
        for item in items:
            item_type = item.get("type", "concept")
            label = item.get("label", "")
            extra = item.get("extra", "")
            domain = item.get("domain", "")
            created_at = item.get("createdAt", None)
            created_dt = _ts_to_dt(created_at) or datetime.utcnow()

            ki = KnowledgeItem(
                concept=label,
                content=extra,
                source=domain,
                type=item_type,
                created_at=created_dt,
            )
            session.add(ki)
            session.flush()
            ids.append(ki.id)

            # 关系条目 → 额外写入三元组
            if item_type == "relation":
                arrow_idx = label.find(" → ")
                if arrow_idx > 0:
                    src = label[:arrow_idx].strip()
                    dst = label[arrow_idx + 3:].strip()
                    predicate = extra if extra else "related_to"
                    # INSERT OR IGNORE（Safeguard 重复）
                    existing = session.query(KnowledgeTriple).filter_by(
                        subject=src, predicate=predicate, object=dst
                    ).first()
                    if not existing:
                        session.add(KnowledgeTriple(
                            subject=src,
                            predicate=predicate,
                            object=dst,
                            created_at=created_dt,
                        ))
                        triple_count += 1

        session.commit()
        return jsonify({"success": True, "ids": ids, "triples_added": triple_count})
    finally:
        session.close()


@app.route("/api/knowledge/<int:item_id>", methods=["DELETE"])
def delete_knowledge(item_id):
    session = get_session()
    try:
        session.query(KnowledgeItem).filter_by(id=item_id).delete()
        session.commit()
        return jsonify({"success": True})
    finally:
        session.close()


# ==================== 设置 API ====================

@app.route("/api/settings/<key>", methods=["GET"])
def get_setting(key):
    session = get_session()
    try:
        row = session.query(Setting).filter_by(key=key).first()
        if row:
            return jsonify({"success": True, "data": row.value})
        else:
            return jsonify({"success": False, "message": "设置项不存在"}), 404
    finally:
        session.close()


@app.route("/api/settings", methods=["POST"])
def save_setting():
    data = request.json
    key = data.get("key")
    value = data.get("value")
    if not key:
        return jsonify({"success": False, "message": "key 不能为空"}), 400

    session = get_session()
    try:
        stmt = sqlite_insert(Setting).values(
            key=key,
            value=value,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["key"],
            set_=dict(value=stmt.excluded.value),
        )
        session.execute(stmt)
        session.commit()
        return jsonify({"success": True})
    finally:
        session.close()


# ==================== 知识三元组 API ====================

@app.route("/api/knowledge/triples")
def get_triples():
    subject = request.args.get("subject", "")
    predicate = request.args.get("predicate", "")
    obj = request.args.get("object", "")
    limit = int(request.args.get("limit", 100))
    offset = int(request.args.get("offset", 0))

    session = get_session()
    try:
        q = session.query(KnowledgeTriple)
        if subject:
            q = q.filter(KnowledgeTriple.subject.like(f"%{subject}%"))
        if predicate:
            q = q.filter(KnowledgeTriple.predicate.like(f"%{predicate}%"))
        if obj:
            q = q.filter(KnowledgeTriple.object.like(f"%{obj}%"))

        total = q.count()
        rows = q.order_by(KnowledgeTriple.id).limit(limit).offset(offset).all()

        return jsonify({
            "success": True,
            "data": [
                {"id": r.id, "subject": r.subject, "predicate": r.predicate, "object": r.object}
                for r in rows
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        })
    finally:
        session.close()


@app.route("/api/knowledge/subjects")
def get_subjects():
    session = get_session()
    try:
        rows = session.query(KnowledgeTriple.subject).distinct().order_by(KnowledgeTriple.subject).all()
        return jsonify({"success": True, "data": [r[0] for r in rows]})
    finally:
        session.close()


@app.route("/api/knowledge/predicates")
def get_predicates():
    session = get_session()
    try:
        rows = session.query(KnowledgeTriple.predicate).distinct().order_by(KnowledgeTriple.predicate).all()
        return jsonify({"success": True, "data": [r[0] for r in rows]})
    finally:
        session.close()


@app.route("/api/knowledge/graph")
def get_graph():
    limit = int(request.args.get("limit", 100))
    session = get_session()
    try:
        rows = session.query(KnowledgeTriple).limit(limit).all()

        triples = []
        concepts = set()
        for r in rows:
            triples.append({
                "subject": r.subject,
                "predicate": r.predicate,
                "object": r.object,
            })
            concepts.add(r.subject)
            # 仅当 object 不是数字/日期等字面量时才添加为概念
            obj_val = r.object
            if obj_val and not obj_val[0].isdigit() and len(obj_val) < 50:
                concepts.add(obj_val)

        return jsonify({
            "success": True,
            "triples": triples,
            "concepts": list(concepts),
            "total": len(triples),
        })
    finally:
        session.close()


# ==================== 健康检查 ====================

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "db": DB_PATH})


if __name__ == "__main__":
    # 首次启动时导入 models 会自动建表（通过 get_engine 触发 create_all）
    from models import get_engine
    get_engine()
    print(f"数据库初始化完成: {DB_PATH}")
    app.run(host="0.0.0.0", port=5000, debug=True)
