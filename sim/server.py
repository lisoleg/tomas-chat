"""
TOMAS 后端 API 服务器
提供 RESTful API 用于数据存储（替代 localStorage）
使用 SQLite 数据库存储所有数据
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import json
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

# 数据库文件
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'tomas.db')

def get_db():
    """获取数据库连接"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """初始化数据库表"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 语料表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS corpus_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            domain TEXT,
            concepts_count INTEGER DEFAULT 0,
            relations_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 冲突决策表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conflict_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conflict_id TEXT NOT NULL,
            concept_name TEXT,
            domain TEXT,
            decision TEXT,
            resolved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(conflict_id)
        )
    ''')
    
    # 聊天会话表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            title TEXT,
            messages TEXT,  -- JSON 字符串
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # API Key 表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_name TEXT UNIQUE NOT NULL,
            key_value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 知识条目表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS knowledge_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concept TEXT NOT NULL,
            content TEXT,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

# ==================== 语料 API ====================

@app.route('/api/corpus', methods=['GET'])
def get_corpus():
    """获取所有语料"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM corpus_entries ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    
    entries = []
    for row in rows:
        entries.append({
            'id': row['id'],
            'text': row['text'],
            'domain': row['domain'],
            'conceptsCount': row['concepts_count'],
            'relationsCount': row['relations_count'],
            'createdAt': row['created_at']
        })
    
    return jsonify({'success': True, 'data': entries})

@app.route('/api/corpus', methods=['POST'])
def add_corpus():
    """添加语料"""
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    
    # 支持前端字段名（name, content）和后端字段名（text, domain）
    text = data.get('text', data.get('name', ''))
    domain = data.get('domain', data.get('content', 'general'))
    concepts_count = data.get('conceptsCount', data.get('conceptsCount', 0))
    relations_count = data.get('relationsCount', data.get('relationsCount', 0))
    
    cursor.execute('''
        INSERT INTO corpus_entries (text, domain, concepts_count, relations_count)
        VALUES (?, ?, ?, ?)
    ''', (text, domain, concepts_count, relations_count))
    
    conn.commit()
    entry_id = cursor.lastrowid
    conn.close()
    
    return jsonify({'success': True, 'id': entry_id})

@app.route('/api/corpus/<int:entry_id>', methods=['DELETE'])
def delete_corpus(entry_id):
    """删除语料"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM corpus_entries WHERE id = ?', (entry_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

# ==================== 冲突决策 API ====================

@app.route('/api/conflicts', methods=['GET'])
def get_conflicts():
    """获取所有冲突决策"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM conflict_decisions')
    rows = cursor.fetchall()
    conn.close()
    
    decisions = []
    for row in rows:
        decisions.append({
            'conflictId': row['conflict_id'],
            'conceptName': row['concept_name'],
            'domain': row['domain'],
            'decision': row['decision'],
            'resolvedAt': row['resolved_at']
        })
    
    return jsonify({'success': True, 'data': decisions})

@app.route('/api/conflicts', methods=['POST'])
def add_conflict():
    """添加/更新冲突决策"""
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    
    # 尝试更新，如果不存在则插入
    cursor.execute('''
        INSERT INTO conflict_decisions (conflict_id, concept_name, domain, decision)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(conflict_id) DO UPDATE SET
            decision = excluded.decision,
            resolved_at = CURRENT_TIMESTAMP
    ''', (data['conflictId'], data.get('conceptName', ''), data.get('domain', ''), data['decision']))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

# ==================== 聊天会话 API ====================

@app.route('/api/sessions', methods=['GET'])
def get_sessions():
    """获取所有聊天会话"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM chat_sessions ORDER BY updated_at DESC')
    rows = cursor.fetchall()
    conn.close()
    
    sessions = []
    for row in rows:
        sessions.append({
            'sessionId': row['session_id'],
            'title': row['title'],
            'messages': json.loads(row['messages']) if row['messages'] else [],
            'createdAt': row['created_at'],
            'updatedAt': row['updated_at']
        })
    
    return jsonify({'success': True, 'data': sessions})

@app.route('/api/sessions', methods=['POST'])
def save_sessions():
    """保存聊天会话（批量更新）"""
    data = request.json  # 期望是会话数组
    conn = get_db()
    cursor = conn.cursor()
    
    for session in data:
        cursor.execute('''
            INSERT INTO chat_sessions (session_id, title, messages, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(session_id) DO UPDATE SET
                title = excluded.title,
                messages = excluded.messages,
                updated_at = CURRENT_TIMESTAMP
        ''', (session['sessionId'], session.get('title', ''), json.dumps(session.get('messages', []))))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/sessions/<session_id>', methods=['DELETE'])
def delete_session(session_id):
    """删除聊天会话"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM chat_sessions WHERE session_id = ?', (session_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

# ==================== API Key API ====================

@app.route('/api/apikey', methods=['GET'])
def get_api_key():
    """获取 API Key"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT key_value FROM api_keys WHERE key_name = ?', ('deepseek',))
    row = cursor.fetchone()
    conn.close()
    
    return jsonify({'success': True, 'data': row['key_value'] if row else ''})

@app.route('/api/apikey', methods=['POST'])
def save_api_key():
    """保存 API Key"""
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO api_keys (key_name, key_value)
        VALUES (?, ?)
        ON CONFLICT(key_name) DO UPDATE SET
            key_value = excluded.key_value,
            updated_at = CURRENT_TIMESTAMP
    ''', ('deepseek', data.get('apiKey', '')))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

# ==================== 知识条目 API ====================

@app.route('/api/knowledge', methods=['GET'])
def get_knowledge():
    """获取所有知识条目"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM knowledge_items')
    rows = cursor.fetchall()
    conn.close()
    
    items = []
    for row in rows:
        items.append({
            'id': row['id'],
            'concept': row['concept'],
            'content': row['content'],
            'source': row['source']
        })
    
    return jsonify({'success': True, 'data': items})

@app.route('/api/knowledge', methods=['POST'])
def add_knowledge():
    """批量添加知识条目"""
    items = request.json  # 期望是数组
    conn = get_db()
    cursor = conn.cursor()
    
    ids = []
    for item in items:
        # 映射字段：label -> concept, extra -> content, domain -> source
        cursor.execute('''
            INSERT INTO knowledge_items (concept, content, source)
            VALUES (?, ?, ?)
        ''', (item.get('label', ''), item.get('extra', ''), item.get('domain', '')))
        ids.append(cursor.lastrowid)
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'ids': ids})

@app.route('/api/knowledge/<int:item_id>', methods=['DELETE'])
def delete_knowledge(item_id):
    """删除知识条目"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM knowledge_items WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

# ==================== 知识三元组 API ====================

@app.route('/api/knowledge/triples')
def get_triples():
    """查询知识三元组（支持过滤）"""
    subject = request.args.get('subject', '')
    predicate = request.args.get('predicate', '')
    obj = request.args.get('object', '')
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))
    
    conn = get_db()
    cursor = conn.cursor()
    
    # 构建查询
    query = 'SELECT * FROM knowledge_triples WHERE 1=1'
    params = []
    
    if subject:
        query += ' AND subject LIKE ?'
        params.append(f'%{subject}%')
    
    if predicate:
        query += ' AND predicate LIKE ?'
        params.append(f'%{predicate}%')
    
    if obj:
        query += ' AND object LIKE ?'
        params.append(f'%{obj}%')
    
    query += ' ORDER BY id LIMIT ? OFFSET ?'
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    # 统计总数
    count_query = 'SELECT COUNT(*) FROM knowledge_triples WHERE 1=1'
    count_params = []
    if subject:
        count_query += ' AND subject LIKE ?'
        count_params.append(f'%{subject}%')
    if predicate:
        count_query += ' AND predicate LIKE ?'
        count_params.append(f'%{predicate}%')
    if obj:
        count_query += ' AND object LIKE ?'
        count_params.append(f'%{obj}%')
    
    cursor.execute(count_query, count_params)
    total = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'success': True,
        'data': [{'id': r['id'], 'subject': r['subject'], 'predicate': r['predicate'], 'object': r['object']} for r in rows],
        'total': total,
        'limit': limit,
        'offset': offset
    })

@app.route('/api/knowledge/subjects')
def get_subjects():
    """获取所有唯一实体"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT DISTINCT subject FROM knowledge_triples ORDER BY subject')
    subjects = [row['subject'] for row in cursor.fetchall()]
    
    conn.close()
    return jsonify({'success': True, 'data': subjects})

@app.route('/api/knowledge/predicates')
def get_predicates():
    """获取所有唯一关系"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT DISTINCT predicate FROM knowledge_triples ORDER BY predicate')
    predicates = [row['predicate'] for row in cursor.fetchall()]
    
    conn.close()
    return jsonify({'success': True, 'data': predicates})

@app.route('/api/knowledge/graph')
def get_graph():
    """获取图数据（用于可视化）"""
    limit = int(request.args.get('limit', 100))
    
    conn = get_db()
    cursor = conn.cursor()
    
    # 获取三元组
    cursor.execute('''
        SELECT subject, predicate, object 
        FROM knowledge_triples 
        LIMIT ?
    ''', (limit,))
    
    triples = []
    concepts = set()
    
    for row in cursor.fetchall():
        triples.append({
            'subject': row['subject'],
            'predicate': row['predicate'],
            'object': row['object']
        })
        concepts.add(row['subject'])
        # 仅当 object 不是数字/日期等字面量时才添加为概念
        if not row['object'][0].isdigit() and len(row['object']) < 50:
            concepts.add(row['object'])
    
    conn.close()
    
    return jsonify({
        'success': True,
        'triples': triples,
        'concepts': list(concepts),
        'total': len(triples)
    })

# ==================== 健康检查 ====================

@app.route('/api/health')
def health():
    """健康检查"""
    return jsonify({'status': 'ok', 'db': DB_PATH})

if __name__ == '__main__':
    init_db()
    print(f"数据库初始化完成: {DB_PATH}")
    app.run(host='0.0.0.0', port=5000, debug=True)
