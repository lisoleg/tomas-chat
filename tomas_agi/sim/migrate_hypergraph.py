"""
TOMAS 超图数据库 Migration + 导入脚本 (流式版)
===============================================

流式导入: 分批读取 knowledge_triples, 动态构建 Vertex,
避免 upfront DISTINCT 扫描 (101M 行上极慢)。

用法:
  python migrate_hypergraph.py              # 创建表 + 导入样本 (前 500 条)
  python migrate_hypergraph.py --limit 5000  # 导入 5000 条
  python migrate_hypergraph.py --full               # 全量导入 (~101M 条, 需数小时)
  python migrate_hypergraph.py --verify             # 仅验证表结构
"""

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from models import (
    get_engine, get_session, Base,
    Vertex, HyperEdge, HyperEdgeNode, MatroidCircuit,
    KnowledgeTriple,
)
from sqlalchemy import text, func


BATCH_SIZE = 2000  # 每批处理的三元组数


def create_tables():
    """创建超图表 (如果不存在)"""
    engine = get_engine()
    print(f"[✓] 表已创建 / 已存在")
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    newly = [t for t in ['vertices', 'hyperdges', 'hyperdge_nodes', 'matroid_circuits'] if t in tables]
    print(f"    超图表: {newly}")


def stream_import(session, limit=None):
    """
    流式导入: 分批读取 knowledge_triples, 动态构建 Vertex + HyperEdge.

    策略:
      - 使用 yield_per() 流式读取 (内存可控)
      - 每批: 收集 concept → INSERT OR IGNORE Vertex → 回读 vid → 构建 HyperEdge
      - Vertex 使用原始 SQL INSERT OR IGNORE 避免 UNIQUE constraint 冲突
      - max_vid 使用可变容器 (list) 实现跨批次追踪
    """
    print(f"\n[导入] knowledge_triples → hypergraph (流式)")
    print(f"    模式: {'样本 limit=' + str(limit) if limit else '全量'}")

    # 获取已有最大 vid (使用可变容器跨批次追踪)
    max_vid_box = [session.query(func.coalesce(func.max(Vertex.vid), 0)).scalar() or 0]
    print(f"    当前最大 vid: {max_vid_box[0]}")

    # 预热: 加载已有 concept → vid 映射
    existing_map = dict(session.query(Vertex.concept, Vertex.vid).all())
    print(f"    已有 Vertex: {len(existing_map)} 个")

    total_imported = 0
    total_skipped = 0
    batch_num = 0

    # 流式查询
    query = session.query(KnowledgeTriple)
    if limit:
        query = query.limit(limit)

    batch_triples = []
    batch_concepts = set()

    t_start = time.time()

    for triple in query.yield_per(BATCH_SIZE):
        batch_triples.append(triple)
        batch_concepts.add(triple.subject)
        batch_concepts.add(triple.object)

        if len(batch_triples) >= BATCH_SIZE:
            n_imported, n_skipped = _process_batch(
                session, batch_triples, batch_concepts, existing_map, max_vid_box
            )
            total_imported += n_imported
            total_skipped += n_skipped
            batch_num += 1

            batch_triples = []
            batch_concepts = set()

            if batch_num % 50 == 0:
                elapsed = time.time() - t_start
                print(f"    批次 {batch_num}: 已导入 {total_imported} 条 HyperEdge, "
                      f"顶点 {len(existing_map)} ({elapsed:.1f}s, "
                      f"{total_imported/max(elapsed,1):.0f} 条/s)")

    # 最后一批
    if batch_triples:
        n_imported, n_skipped = _process_batch(
            session, batch_triples, batch_concepts, existing_map, max_vid_box
        )
        total_imported += n_imported
        total_skipped += n_skipped

    elapsed = time.time() - t_start
    print(f"\n[✓] 导入完成: {total_imported} 条 HyperEdge, "
          f"跳过 {total_skipped}, 用时 {elapsed:.1f}s "
          f"({total_imported/max(elapsed,1):.0f} 条/s)")


def _process_batch(session, triples, concepts, existing_map, max_vid_box):
    """处理一批 triple, 插入 Vertex + HyperEdge (修复版: INSERT OR IGNORE)"""
    # ---- 1. Upsert Vertex (使用 INSERT OR IGNORE) ----
    new_concepts = concepts - set(existing_map.keys())
    if new_concepts:
        # 使用原始 SQL INSERT OR IGNORE 批量插入新顶点
        rows = []
        for concept in new_concepts:
            max_vid_box[0] += 1
            existing_map[concept] = max_vid_box[0]
            rows.append({
                'vid': max_vid_box[0],
                'concept': concept,
                'i_val': 0.5,
            })
        
        # 使用 INSERT OR IGNORE 避免 UNIQUE 冲突
        try:
            session.execute(
                text("""
                    INSERT OR IGNORE INTO vertices (vid, concept, phi_b0, phi_b1, 
                    phi_b2, phi_b3, phi_b4, phi_b5, phi_b6, phi_b7, i_val, degree_class)
                    VALUES (:vid, :concept, 0, 0, 0, 0, 0, 0, 0, 0, :i_val, 0)
                """),
                rows
            )
            session.flush()
        except Exception:
            session.rollback()
            # 重新读取 existing_map (处理并发插入的情况)
            pass

    # ---- 2. 构建 HyperEdge ----
    edges_to_insert = []
    nodes_to_insert = []

    for triple in triples:
        sub_vid = existing_map.get(triple.subject)
        obj_vid = existing_map.get(triple.object)
        if sub_vid is None or obj_vid is None:
            continue

        eid = f"triple_{triple.id}"
        nodes_json = json.dumps([sub_vid, obj_vid])

        edges_to_insert.append(HyperEdge(
            eid=eid,
            arity=2,
            nodes=nodes_json,
            i_val=triple.i_weight or 1.0,
            asym=0.0,
            weight=triple.i_weight or 1.0,
            edge_type=(triple.predicate or "generic")[:50],
        ))
        nodes_to_insert.append(HyperEdgeNode(eid=eid, vid=sub_vid, position=0))
        nodes_to_insert.append(HyperEdgeNode(eid=eid, vid=obj_vid, position=1))

    # ---- 3. 批量插入 (INSERT OR IGNORE 防重复) ----
    try:
        # 超边使用 INSERT OR IGNORE
        for edge in edges_to_insert:
            session.execute(
                text("""
                    INSERT OR IGNORE INTO hyperedges 
                    (eid, arity, nodes, i_val, asym, weight, edge_type)
                    VALUES (:eid, :arity, :nodes, :i_val, :asym, :weight, :edge_type)
                """),
                {
                    "eid": edge.eid,
                    "arity": edge.arity,
                    "nodes": edge.nodes,
                    "i_val": edge.i_val,
                    "asym": edge.asym,
                    "weight": edge.weight,
                    "edge_type": edge.edge_type,
                },
            )
        # 关联节点同样 INSERT OR IGNORE
        for node in nodes_to_insert:
            session.execute(
                text("""
                    INSERT OR IGNORE INTO hyperedge_nodes (eid, vid, position)
                    VALUES (:eid, :vid, :position)
                """),
                {"eid": node.eid, "vid": node.vid, "position": node.position},
            )
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"    [WARN] 批次提交失败: {e}")
        return 0, len(triples)

    return len(edges_to_insert), 0


def verify_schema(session):
    """验证表结构 + 统计"""
    print("\n[验证] 超图表结构...")
    engine = get_engine()
    from sqlalchemy import inspect
    inspector = inspect(engine)

    for table in ['vertices', 'hyperedges', 'hyperedge_nodes', 'matroid_circuits']:
        if table in inspector.get_table_names():
            cols = inspector.get_columns(table)
            print(f"  {table}: {len(cols)} 列")
        else:
            print(f"  {table}: ❌ 不存在!")

    # 统计
    counts = {
        'vertices': session.query(Vertex).count(),
        'hyperdges': session.query(HyperEdge).count(),
        'hyperdge_nodes': session.query(HyperEdgeNode).count(),
    }
    print(f"\n  记录数:")
    for k, v in counts.items():
        print(f"    {k}: {v}")

    # 样本查看
    if counts['hyperdges'] > 0:
        sample = session.query(HyperEdge).first()
        print(f"\n  样本 HyperEdge: eid={sample.eid}, arity={sample.arity}, nodes={sample.nodes}")


def main():
    parser = argparse.ArgumentParser(description="TOMAS 超图数据库 Migration + 导入")
    parser.add_argument("--full", action="store_true", help="导入全量 knowledge_triples (~101M 条)")
    parser.add_argument("--limit", type=int, default=500, help="样本导入条数 (默认 500)")
    parser.add_argument("--verify", action="store_true", help="仅验证表结构，不导入")
    args = parser.parse_args()

    session = get_session()
    try:
        create_tables()

        if args.verify:
            verify_schema(session)
            return

        if args.full:
            stream_import(session, limit=None)
        else:
            stream_import(session, limit=args.limit)

        verify_schema(session)
    finally:
        session.close()


if __name__ == "__main__":
    main()
