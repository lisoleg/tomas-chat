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
    min_i_weight = float(request.args.get("min_i_weight", 0))

    session = get_session()
    try:
        q = session.query(KnowledgeTriple)
        if subject:
            q = q.filter(KnowledgeTriple.subject.like(f"%{subject}%"))
        if predicate:
            q = q.filter(KnowledgeTriple.predicate.like(f"%{predicate}%"))
        if obj:
            q = q.filter(KnowledgeTriple.object.like(f"%{obj}%"))
        if min_i_weight > 0:
            q = q.filter(KnowledgeTriple.i_weight >= min_i_weight)

        # 仅在有筛选条件时才 count（无筛选时全表 count 太慢）
        if subject or predicate or obj or min_i_weight > 0:
            total = q.count()
        else:
            total = -1  # 太大无法实时统计
        rows = q.order_by(KnowledgeTriple.id.desc()).limit(limit).offset(offset).all()

        return jsonify({
            "success": True,
            "data": [
                {
                    "id": r.id,
                    "subject": r.subject,
                    "predicate": r.predicate,
                    "object": r.object,
                    "i_weight": round(r.i_weight, 4) if r.i_weight else 1.0,
                }
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
    limit = int(request.args.get("limit", 1000))
    search = request.args.get("search", "")
    session = get_session()
    try:
        q = session.query(KnowledgeTriple.subject).distinct()
        if search:
            q = q.filter(KnowledgeTriple.subject.like(f"%{search}%"))
        rows = q.limit(limit).all()
        return jsonify({"success": True, "data": [r[0] for r in rows], "truncated": True, "limit": limit})
    finally:
        session.close()


@app.route("/api/knowledge/predicates")
def get_predicates():
    limit = int(request.args.get("limit", 1000))
    search = request.args.get("search", "")
    session = get_session()
    try:
        q = session.query(KnowledgeTriple.predicate).distinct()
        if search:
            q = q.filter(KnowledgeTriple.predicate.like(f"%{search}%"))
        rows = q.limit(limit).all()
        return jsonify({"success": True, "data": [r[0] for r in rows], "truncated": True, "limit": limit})
    finally:
        session.close()


@app.route("/api/knowledge/graph")
def get_graph():
    limit = int(request.args.get("limit", 200))
    subject = request.args.get("subject", "")
    min_i_weight = float(request.args.get("min_i_weight", 0))

    session = get_session()
    try:
        q = session.query(KnowledgeTriple)

        # κ-Gate 剪枝：仅取 i_weight 高于阈值的边
        if min_i_weight > 0:
            q = q.filter(KnowledgeTriple.i_weight >= min_i_weight)

        # 按主体过滤（子图展开）
        if subject:
            # 1-hop：subject 做主语或宾语
            q = q.filter(
                (KnowledgeTriple.subject == subject) |
                (KnowledgeTriple.object == subject)
            )

        rows = q.order_by(KnowledgeTriple.i_weight.desc()).limit(limit).all()

        triples = []
        concepts = set()
        for r in rows:
            triples.append({
                "subject": r.subject,
                "predicate": r.predicate,
                "object": r.object,
                "i_weight": round(r.i_weight, 4) if r.i_weight else 1.0,
            })
            concepts.add(r.subject)
            obj_val = r.object
            if obj_val and not obj_val[0].isdigit() and len(obj_val) < 50:
                concepts.add(obj_val)

        return jsonify({
            "success": True,
            "triples": triples,
            "concepts": list(concepts),
            "total": len(triples),
            "min_i_weight": min_i_weight,
        })
    finally:
        session.close()


# ==================== 健康检查 ====================

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "db": DB_PATH})


# ═══════════════════════════════════════════════════════════════
# TOMAS 引擎 API — IDO / FDE / DualTimeline / IT-OT
# ═══════════════════════════════════════════════════════════════

# 懒加载单例
_tomas_modules = {}

def _get_ido_bridge():
    if "ido" not in _tomas_modules:
        try:
            from tomas_agi.sim.ido_bridge import IDOBridge
            _tomas_modules["ido"] = IDOBridge()
        except Exception as e:
            _tomas_modules["ido"] = None
    return _tomas_modules["ido"]

def _get_fde_builder():
    if "fde" not in _tomas_modules:
        try:
            from tomas_agi.sim.fde_builder import FDEBuilder
            _tomas_modules["fde"] = FDEBuilder()
        except Exception as e:
            _tomas_modules["fde"] = None
    return _tomas_modules["fde"]

def _get_dual_timeline():
    if "dual" not in _tomas_modules:
        try:
            from tomas_agi.sim.dual_timeline import ExternalTimeline, InternalTimeline, DualTimelineAligner
            _tomas_modules["dual"] = {
                "external": ExternalTimeline(),
                "internal": InternalTimeline(),
                "aligner": DualTimelineAligner(),
            }
        except Exception as e:
            _tomas_modules["dual"] = None
    return _tomas_modules["dual"]

def _get_itot_bridge():
    if "itot" not in _tomas_modules:
        try:
            from tomas_agi.sim.itot_bridge import ITOTTranslator, TechnicalDebtGovernor, ZeroTrustGate, JointKPI
            import uuid
            _tomas_modules["itot"] = {
                "translator": ITOTTranslator(),
                "debt_gov": TechnicalDebtGovernor(),
                "zt_gate": ZeroTrustGate(),
                "kpi": JointKPI(),
            }
        except Exception as e:
            _tomas_modules["itot"] = None
    return _tomas_modules["itot"]


# ── IDO Bridge ─────────────────────────────────────────────

@app.route("/api/ido/evaluate", methods=["POST"])
def ido_evaluate():
    try:
        data = request.json or {}
        bridge = _get_ido_bridge()
        if bridge is None:
            return jsonify({"success": False, "error": "IDO module unavailable"}), 503
        try:
            from tomas_agi.sim.ido_bridge import IDOHypothesis
        except ImportError:
            from ido_bridge import IDOHypothesis
        h = IDOHypothesis(
            problem_name=data.get("problem_name", "unknown"),
            domain=data.get("domain", "general"),
            axiom_status={a: data.get("axioms", {}).get(a, False) for a in ["A1", "A2", "A3", "A4"]},
            i_support=data.get("i_support", 0.5),
        )
        result = bridge.evaluate_hypothesis(h)
        return jsonify({"success": True, "data": {
            "domain": result.domain,
            "tier": result.tier.value if hasattr(result.tier, "value") else str(result.tier),
            "audit": result.audit.value if hasattr(result.audit, "value") else str(result.audit),
            "i_value": getattr(result, "i_value", 0.0),
            "evidence": getattr(result, "evidence", []),
        }})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/ido/classify", methods=["POST"])
def ido_classify():
    try:
        data = request.json or {}
        bridge = _get_ido_bridge()
        if bridge is None:
            return jsonify({"success": False, "error": "IDO module unavailable"}), 503
        axiom_status = data.get("axiom_status", {})
        problem_name = data.get("problem_name", "unknown")
        tier = bridge.classifier.classify(problem_name, axiom_status)
        gaps = bridge.classifier.get_gaps(problem_name)
        return jsonify({"success": True, "data": {
            "tier": tier.value if hasattr(tier, "value") else str(tier),
            "gaps": gaps,
        }})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/ido/flow", methods=["POST"])
def ido_flow():
    try:
        data = request.json or {}
        bridge = _get_ido_bridge()
        if bridge is None:
            return jsonify({"success": False, "error": "IDO module unavailable"}), 503
        flow = bridge.template.run_flow(
            data.get("problem_name", "default"),
            max_steps=data.get("max_steps", 80),
            initial_i=data.get("i_support", 0.5),
        )
        return jsonify({"success": True, "data": {
            "steps": len(flow.get("history", [])),
            "final_i": flow.get("final_i", 0.0),
            "converged": flow.get("converged", False),
        }})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/ido/stats", methods=["GET"])
def ido_stats():
    try:
        bridge = _get_ido_bridge()
        if bridge is None:
            return jsonify({"success": True, "data": {"status": "unavailable"}})
        return jsonify({"success": True, "data": {
            "status": "available",
            "tiers": ["Tier1", "Tier2", "Tier3"],
            "axioms": ["A1", "A2", "A3", "A4"],
        }})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── FDE Builder ───────────────────────────────────────────

@app.route("/api/fde/build", methods=["POST"])
def fde_build():
    try:
        data = request.json or {}
        builder = _get_fde_builder()
        if builder is None:
            return jsonify({"success": False, "error": "FDE module unavailable"}), 503
        echo = data.get("echo_context", {"it": "", "ot": "", "et": ""})
        standard = data.get("standard_ref", "IEC62443")
        ontology = builder.build(echo, standard)
        return jsonify({"success": True, "data": {
            "qi_level": str(getattr(ontology, "qi_level", "unknown")),
            "sha_level": str(getattr(ontology, "sha_level", "unknown")),
            "validations": getattr(ontology, "validations", []),
        }})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/fde/calibrate", methods=["POST"])
def fde_calibrate():
    try:
        data = request.json or {}
        builder = _get_fde_builder()
        if builder is None:
            return jsonify({"success": False, "error": "FDE module unavailable"}), 503
        result = builder.calibrator.calibrate_iota(
            data.get("target_concept", ""),
            data.get("i_value", 0.5),
        )
        return jsonify({"success": True, "data": {"calibrated": result}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/fde/check-asym", methods=["POST"])
def fde_check_asym():
    try:
        data = request.json or {}
        builder = _get_fde_builder()
        if builder is None:
            return jsonify({"success": False, "error": "FDE module unavailable"}), 503
        result = builder.asym_checker.check_asym(data.get("skill_description", ""))
        return jsonify({"success": True, "data": {
            "asym": getattr(result, "asym", 0.0),
            "mus_flagged": getattr(result, "mus_flagged", False),
        }})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/fde/status", methods=["GET"])
def fde_status():
    try:
        builder = _get_fde_builder()
        if builder is None:
            return jsonify({"success": True, "data": {"status": "unavailable"}})
        return jsonify({"success": True, "data": {
            "status": "available",
            "levels": ["器", "术", "法", "道"],
            "standards": ["IEC62443", "ISO26262", "IEC61508"],
        }})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Dual Timeline ─────────────────────────────────────────

@app.route("/api/dual-timeline/tick", methods=["POST"])
def dual_tick():
    try:
        data = request.json or {}
        mods = _get_dual_timeline()
        if mods is None:
            return jsonify({"success": False, "error": "DualTimeline module unavailable"}), 503
        evt = data.get("event", "tick")
        ts = data.get("timestamp", None)
        state = mods["external"].tick(evt, ts)
        return jsonify({"success": True, "data": {
            "t": state.get("t", 0),
            "event_count": state.get("event_count", 0),
        }})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/dual-timeline/step", methods=["POST"])
def dual_step():
    try:
        data = request.json or {}
        mods = _get_dual_timeline()
        if mods is None:
            return jsonify({"success": False, "error": "DualTimeline module unavailable"}), 503
        evt = data.get("cognitive_event", "step")
        state = mods["internal"].step(evt)
        return jsonify({"success": True, "data": {
            "tau": state.get("tau", 0),
            "attention": state.get("attention", 0.0),
        }})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/dual-timeline/align", methods=["POST"])
def dual_align():
    try:
        mods = _get_dual_timeline()
        if mods is None:
            return jsonify({"success": False, "error": "DualTimeline module unavailable"}), 503
        result = mods["aligner"].align()
        singularities = getattr(result, "singularities", [])
        return jsonify({"success": True, "data": {
            "aligned": getattr(result, "aligned", False),
            "singularities": [str(s) for s in singularities],
        }})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/dual-timeline/status", methods=["GET"])
def dual_status():
    try:
        mods = _get_dual_timeline()
        if mods is None:
            return jsonify({"success": True, "data": {"status": "unavailable"}})
        return jsonify({"success": True, "data": {
            "status": "available",
            "external_t": mods["external"]._t if hasattr(mods["external"], "_t") else 0,
            "internal_tau": mods["internal"]._tau if hasattr(mods["internal"], "_tau") else 0,
        }})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── IT-OT Bridge ──────────────────────────────────────────

@app.route("/api/itot/translate", methods=["POST"])
def itot_translate():
    try:
        data = request.json or {}
        mods = _get_itot_bridge()
        if mods is None:
            return jsonify({"success": False, "error": "ITOT module unavailable"}), 503
        text = data.get("text", "")
        direction = data.get("direction", "it2ot")
        result = mods["translator"].translate(text, direction)
        return jsonify({"success": True, "data": {
            "original": text,
            "translated": result,
            "direction": direction,
        }})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/itot/debt-assess", methods=["POST"])
def itot_debt_assess():
    try:
        mods = _get_itot_bridge()
        if mods is None:
            return jsonify({"success": False, "error": "ITOT module unavailable"}), 503
        report = mods["debt_gov"].assess()
        return jsonify({"success": True, "data": {
            "total_debt": getattr(report, "total_debt", 0.0),
            "categories": getattr(report, "categories", {}),
            "recommendations": getattr(report, "recommendations", []),
        }})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/itot/zero-trust", methods=["POST"])
def itot_zero_trust():
    try:
        data = request.json or {}
        mods = _get_itot_bridge()
        if mods is None:
            return jsonify({"success": False, "error": "ITOT module unavailable"}), 503
        result = mods["zt_gate"].evaluate(
            source=data.get("source", "unknown"),
            request_iota=data.get("request_iota", 0.5),
            content=data.get("content", ""),
        )
        return jsonify({"success": True, "data": {
            "allowed": getattr(result, "allowed", False),
            "adc_mode": getattr(result, "adc_mode", "UNKNOWN"),
            "reason": getattr(result, "reason", ""),
        }})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/itot/kpi", methods=["GET"])
def itot_kpi():
    try:
        mods = _get_itot_bridge()
        if mods is None:
            return jsonify({"success": True, "data": {"status": "unavailable"}})
        r = mods["kpi"].compute_unified_r()
        return jsonify({"success": True, "data": {"unified_r": r}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ═══════════════════════════════════════════════════════════
# 启动入口
# ═══════════════════════════════════════════════════════════


# ==================== T-Processor v1.0 API ====================

def _get_tprocessor():
    """Lazy-init T-Processor v1.0 simulator."""
    if not hasattr(app, '_tproc'):
        try:
            from tprocessor_sim import TProcessorV1
            app._tproc = TProcessorV1(crossbar_shape=(128, 128))
        except Exception:
            app._tproc = None
    return app._tproc


@app.route("/api/tprocessor/tick", methods=["POST"])
def tproc_tick():
    try:
        import numpy as np
        data = request.json or {}
        tproc = _get_tprocessor()
        if tproc is None:
            return jsonify({"success": False, "error": "T-Processor unavailable"}), 503
        v_in = np.array(data.get("v_in", [0.5] * 128), dtype=np.float32)
        meta = data.get("meta", None)
        result = tproc.tick(v_in, meta)
        return jsonify({"success": True, "data": {
            "cycle": result["cycle"],
            "i_max": float(result["i_out"].max()) if hasattr(result["i_out"], "max") else 0.0,
            "dead_zero_fused": result["dead_zero_fused"],
            "mus_active": result["mus_active"],
            "scheduler": result["scheduler"],
            "energy": result["energy"],
        }})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tprocessor/load_eml", methods=["POST"])
def tproc_load_eml():
    try:
        data = request.json or {}
        tproc = _get_tprocessor()
        if tproc is None:
            return jsonify({"success": False, "error": "T-Processor unavailable"}), 503
        edges = data.get("edges", [])
        from tprocessor_sim import HyperEdgeState
        eml_edges = [HyperEdgeState(e["src"], e["dst"], e["weight"]) for e in edges]
        tproc.load_eml(eml_edges)
        return jsonify({"success": True, "data": {"loaded": len(eml_edges)}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== T-Shield API ====================

def _get_tshield():
    """Lazy-init T-Shield wrapper."""
    if not hasattr(app, '_tshield'):
        try:
            from tshield_wrapper import TShieldWrapper
            app._tshield = TShieldWrapper(stub_detector)
        except Exception:
            app._tshield = None
    return app._tshield


@app.route("/api/tshield/infer", methods=["POST"])
def tshield_infer():
    try:
        import numpy as np
        data = request.json or {}
        shield = _get_tshield()
        if shield is None:
            return jsonify({"success": False, "error": "T-Shield unavailable"}), 503
        img = np.array(data.get("img", []), dtype=np.uint8)
        context = data.get("context", {})
        depth_config = data.get("depth_config", "auto")
        result = shield.infer(img, context=context, depth_config=depth_config)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tshield/demo", methods=["GET"])
def tshield_demo():
    try:
        from tshield_wrapper import demo_tshield
        demo_tshield()
        return jsonify({"success": True, "data": {"status": "demo run complete"}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tshield/stats", methods=["GET"])
def tshield_stats():
    """返回 T-Shield 统计信息"""
    try:
        shield = _get_tshield()
        
        # 模拟统计数据（实际应该从 shield 对象获取）
        stats = {
            "total_inferences": 156,
            "dead_zero_count": 23,
            "mus_count": 8,
            "ksnap_count": 5,
            "i_scene_value": 0.42,
            "gego_mode": "Afferent",
            "gego_switches": 3,
            "shield_status": "active" if shield is not None else "unavailable",
            "last_inference": datetime.now().isoformat(),
        }
        
        return jsonify({"success": True, "data": stats})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tprocessor/stats", methods=["GET"])
def tprocessor_stats():
    """返回 T-Processor 统计信息"""
    try:
        tproc = _get_tprocessor()
        
        # 模拟统计数据（实际应该从 tproc 对象获取）
        stats = {
            "total_cycles": 1420,
            "dead_zero_count": 47,
            "mus_count": 12,
            "snap_count": 8,
            "avg_utilization": 66.25,
            "rram_util": 78,
            "dz_util": 92,
            "mus_util": 34,
            "ksnap_util": 61,
            "processor_status": "active" if tproc is not None else "unavailable",
        }
        
        return jsonify({"success": True, "data": stats})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    from models import get_engine
    get_engine()
    print(f"数据库初始化完成: {DB_PATH}")
    app.run(host="0.0.0.0", port=5000, debug=True)
