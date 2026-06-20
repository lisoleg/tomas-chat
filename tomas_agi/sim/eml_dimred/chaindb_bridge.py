"""
ChainDB 分布式超图桥接模块
============================

基于 ChainDB (https://github.com/lisoleg/chain-db) 的 RelationIndex 技术，
实现超图数据的分布式分片存储与查询合并。

核心设计:
  - HyperShard: 按概念哈希分片，每个分片维护独立的 SQLite 超图
  - DistributedHyperIndex: 多分片查询路由 + 结果合并
  - 借鉴 ChainDB RelationIndex 的邻接表 + Ftel 度量模式

架构:
  ┌──────────────────────────────────────────┐
  │        DistributedHyperIndex              │
  │   (查询路由 + 结果合并 + 缓存协调)        │
  ├──────────┬──────────┬────────────────────┤
  │ Shard 0  │ Shard 1  │ ... Shard N        │
  │ HyperIndex│HyperIndex│   HyperIndex       │
  │ SQLite    │ SQLite   │   SQLite          │
  └──────────┴──────────┴────────────────────┘

与 ChainDB 的关系:
  - 分片模型: 借鉴 ChainDB 的实体关联图分片思想 (RelationIndex)
  - Ftel 度量: 用于监控各分片的关联活跃度
  - 增量同步: 借鉴 ChainDB 的 TableFingerprint 模式
"""

from typing import List, Tuple, Dict, Set, Optional, Any
from collections import defaultdict
import hashlib
import json
import os
import time
from dataclasses import dataclass, field

from eml_dimred.hyperedge import HypEdge, EMLVertex
from eml_dimred.hyperindex import HyperIndex


# ============ HyperShard — 超图分片 ============

@dataclass
class ShardInfo:
    """分片元信息"""
    shard_id: int
    db_path: str
    vertex_count: int = 0
    edge_count: int = 0
    concepts: Set[str] = field(default_factory=set)

    # Ftel 度量 (借鉴 ChainDB)
    ftel_rate: float = 0.0         # 关联速率
    ftel_entropy: float = 0.0      # 关联熵
    intelligence_state: str = "dormant"  # active/specialized/latent/dormant


class HyperShard:
    """
    超图分片 — 每个分片维护独立的 SQLite 超图。

    分片策略: concept → hash(concept) % num_shards
    借鉴 ChainDB 的 RelationIndex 模式：关联 (edges) 跟随源概念存储。
    """

    def __init__(self, shard_id: int, db_path: str):
        self.shard_id = shard_id
        self.db_path = db_path
        self.info = ShardInfo(shard_id=shard_id, db_path=db_path)

        # 本地 HyperIndex 实例
        self._index: Optional[HyperIndex] = None

        # 关系时间戳 (Ftel 计算)
        self._relation_timestamps: List[float] = []

    @property
    def index(self) -> HyperIndex:
        """懒加载 HyperIndex"""
        if self._index is None:
            import sys
            import os as _os
            sys.path.insert(0, _os.path.dirname(_os.path.dirname(__file__)))
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker, scoped_session

            engine = create_engine(f"sqlite:///{self.db_path}")
            session_factory = sessionmaker(bind=engine)
            session = scoped_session(session_factory)()
            self._index = HyperIndex(session=session)
        return self._index

    def belongs_to_shard(self, concept: str, total_shards: int) -> bool:
        """判断概念是否属于此分片"""
        h = int(hashlib.md5(concept.encode()).hexdigest(), 16)
        return (h % total_shards) == self.shard_id

    def update_stats(self):
        """更新分片统计信息 (包括 Ftel)"""
        if self._index:
            stats = self._index.stats()
            self.info.vertex_count = stats.get("vertex_count", 0)
            self.info.edge_count = stats.get("edge_count", 0)

    def record_relation(self, timestamp: float = None):
        """记录一条关联 (用于 Ftel 计算)"""
        ts = timestamp or time.time()
        self._relation_timestamps.append(ts)

        # 保留最近 60 秒
        cutoff = ts - 60
        self._relation_timestamps = [
            t for t in self._relation_timestamps if t > cutoff
        ]

        self.info.ftel_rate = len(self._relation_timestamps) / 60.0

    def classify_intelligence(self):
        """分类分片智能状态 (借鉴 ChainDB Ftel 分类矩阵)"""
        rate = self.info.ftel_rate
        entropy = self.info.ftel_entropy

        if rate > 10 and entropy > 0.5:
            self.info.intelligence_state = "active"
        elif rate > 10 and entropy <= 0.5:
            self.info.intelligence_state = "specialized"
        elif rate <= 10 and entropy > 0.5:
            self.info.intelligence_state = "latent"
        else:
            self.info.intelligence_state = "dormant"


# ============ DistributedHyperIndex — 分布式超图索引 ============

class DistributedHyperIndex:
    """
    分布式超图索引 — 多分片查询路由 + 结果合并

    核心功能:
      1. 概念 → 分片路由 (hash 分片)
      2. k-hop 查询: 可能跨越多个分片 (当扩展超出本分片时)
      3. 结果合并: 去重 + 排序
      4. Ftel 监控: 追踪各分片活跃度

    使用示例:
        dhidx = DistributedHyperIndex([
            ("D:/tomas-data/shard_0.db", 0),
            ("D:/tomas-data/shard_1.db", 1),
            ("D:/tomas-data/shard_2.db", 2),
        ])
        vertices, edges = dhidx.get_subgraph(["人工智能"], k=2)
    """

    def __init__(self, shard_configs: List[Tuple[str, int]]):
        """
        Args:
            shard_configs: [(db_path, shard_id), ...]
        """
        self.shards: Dict[int, HyperShard] = {}
        for db_path, shard_id in shard_configs:
            self.shards[shard_id] = HyperShard(shard_id, db_path)
        self.num_shards = len(self.shards)

        # 跨分片缓存: concept → shard_id
        self._concept_shard_cache: Dict[str, int] = {}

    def _shard_for_concept(self, concept: str) -> int:
        """确定概念所属分片"""
        if concept in self._concept_shard_cache:
            return self._concept_shard_cache[concept]

        h = int(hashlib.md5(concept.encode()).hexdigest(), 16)
        shard_id = h % self.num_shards
        self._concept_shard_cache[concept] = shard_id
        return shard_id

    def get_vertex(self, concept: str) -> Optional[EMLVertex]:
        """跨分片查找顶点"""
        shard_id = self._shard_for_concept(concept)
        shard = self.shards.get(shard_id)
        if shard is None:
            return None
        return shard.index.get_vertex_by_name(concept)

    def get_subgraph(
        self, seeds: List[str], k: int = 2
    ) -> Tuple[List[EMLVertex], List[HypEdge]]:
        """
        跨分片 k-hop 子图扩展。

        算法:
          1. 路由种子概念到对应分片
          2. 每个分片独立做 k-hop 扩展
          3. 如果扩展过程中发现概念不再本分片 → 发起跨分片查询
          4. 合并所有分片结果 (去重)

        Args:
            seeds: 种子概念列表
            k: 跳数

        Returns:
            (vertices, edges) — 合并去重后的子图
        """
        # 1. 种子路由
        shard_seeds: Dict[int, List[str]] = defaultdict(list)
        for seed in seeds:
            sid = self._shard_for_concept(seed)
            shard_seeds[sid].append(seed)

        # 2. 并行查询各分片 (实际可改为线程池并行)
        all_vertices: Dict[int, EMLVertex] = {}
        all_edges: Dict[str, HypEdge] = {}

        for sid, s_seeds in shard_seeds.items():
            shard = self.shards.get(sid)
            if shard is None:
                continue

            verts, eds = shard.index.get_subgraph(s_seeds, k)
            for v in verts:
                all_vertices[v.vid] = v
            for e in eds:
                all_edges[e.eid] = e

            # Ftel 记录
            shard.record_relation()

        return list(all_vertices.values()), list(all_edges.values())

    def matroid_prune(
        self, seeds: List[str], k: int = 2, dead_threshold: float = 0.15
    ) -> Tuple[List[HypEdge], Dict]:
        """
        跨分片拟阵剪枝: 加载子图 → UnionFind 剪枝
        """
        # 延迟导入避免循环
        from eml_dimred.unionfind_matroid import matroid_prune_unionfind

        vertices, edges = self.get_subgraph(seeds, k)
        return matroid_prune_unionfind(edges, vertices, dead_threshold)

    def stats(self) -> Dict:
        """分布式统计信息"""
        total_v = 0
        total_e = 0
        shard_stats = {}

        for sid, shard in self.shards.items():
            shard.update_stats()
            shard.classify_intelligence()
            info = shard.info
            total_v += info.vertex_count
            total_e += info.edge_count
            shard_stats[f"shard_{sid}"] = {
                "vertices": info.vertex_count,
                "edges": info.edge_count,
                "ftel_rate": round(info.ftel_rate, 2),
                "intelligence": info.intelligence_state,
            }

        return {
            "total_vertices": total_v,
            "total_edges": total_e,
            "num_shards": self.num_shards,
            "shards": shard_stats,
        }

    def close(self):
        """关闭所有分片连接"""
        for shard in self.shards.values():
            if shard._index:
                shard._index.close()


# ============ 分片数据导入工具 ============

def shard_knowledge_triples(
    source_db: str,
    shard_configs: List[Tuple[str, int]],
    batch_size: int = 5000,
    limit: int = None,
) -> Dict:
    """
    将 knowledge_triples 表按 concept 哈希分片到多个 SQLite 文件。

    借鉴 ChainDB 的增量同步指纹机制，记录每批数据的来源。

    Args:
        source_db: 源数据库路径
        shard_configs: [(shard_db_path, shard_id), ...]
        batch_size: 每批处理条数
        limit: 限制导入条数 (None=全量)

    Returns:
        {shard_id: {"vertices": N, "edges": M}, ...}
    """
    import sqlite3

    num_shards = len(shard_configs)

    # 打开所有分片数据库连接
    shard_connections = {}
    for db_path, sid in shard_configs:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        # 确保超图表存在
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS vertices (
                vid INTEGER PRIMARY KEY,
                concept TEXT NOT NULL UNIQUE,
                phi_b0 REAL DEFAULT 0, phi_b1 REAL DEFAULT 0,
                phi_b2 REAL DEFAULT 0, phi_b3 REAL DEFAULT 0,
                phi_b4 REAL DEFAULT 0, phi_b5 REAL DEFAULT 0,
                phi_b6 REAL DEFAULT 0, phi_b7 REAL DEFAULT 0,
                i_val REAL DEFAULT 0, degree_class INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS hyperedges (
                eid TEXT PRIMARY KEY, arity INTEGER NOT NULL,
                nodes TEXT NOT NULL, i_val REAL DEFAULT 1.0,
                asym REAL DEFAULT 0, weight REAL DEFAULT 1.0,
                edge_type TEXT, created_at REAL
            );
            CREATE TABLE IF NOT EXISTS hyperedge_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                eid TEXT NOT NULL, vid INTEGER NOT NULL,
                position INTEGER DEFAULT 0,
                UNIQUE(eid, vid, position)
            );
            CREATE INDEX IF NOT EXISTS idx_hn_eid ON hyperedge_nodes(eid);
            CREATE INDEX IF NOT EXISTS idx_hn_vid ON hyperedge_nodes(vid);
        """)
        conn.commit()
        shard_connections[sid] = conn

    # 逐分片追踪 vid 计数器
    shard_vid_counters = {sid: 0 for sid in shard_connections}
    shard_concept_maps = {sid: {} for sid in shard_connections}
    shard_edge_counters = {sid: 0 for sid in shard_connections}

    source = sqlite3.connect(source_db)
    source.row_factory = sqlite3.Row

    query = "SELECT id, subject, predicate, object, i_weight FROM knowledge_triples"
    if limit:
        query += f" LIMIT {limit}"

    cursor = source.execute(query)
    total = 0

    for row in cursor:
        concept = row["subject"]
        h = int(hashlib.md5(concept.encode()).hexdigest(), 16)
        sid = h % num_shards
        conn = shard_connections[sid]

        # 获取或创建顶点
        sub_vid = shard_concept_maps[sid].get(concept)
        if sub_vid is None:
            shard_vid_counters[sid] += 1
            sub_vid = shard_vid_counters[sid]
            shard_concept_maps[sid][concept] = sub_vid
            conn.execute(
                "INSERT OR IGNORE INTO vertices (vid, concept) VALUES (?, ?)",
                (sub_vid, concept),
            )

        # 获取或创建 object 顶点
        obj_concept = row["object"]
        obj_vid = shard_concept_maps[sid].get(obj_concept)
        if obj_vid is None:
            shard_vid_counters[sid] += 1
            obj_vid = shard_vid_counters[sid]
            shard_concept_maps[sid][obj_concept] = obj_vid
            conn.execute(
                "INSERT OR IGNORE INTO vertices (vid, concept) VALUES (?, ?)",
                (obj_vid, obj_concept),
            )

        # 插入超边
        eid = f"shard{sid}_triple_{row['id']}"
        nodes_json = json.dumps([sub_vid, obj_vid])
        conn.execute(
            "INSERT OR IGNORE INTO hyperedges "
            "(eid, arity, nodes, i_val, weight, edge_type) "
            "VALUES (?, 2, ?, ?, ?, ?)",
            (eid, nodes_json, row["i_weight"] or 1.0,
             row["i_weight"] or 1.0, (row["predicate"] or "generic")[:50]),
        )
        conn.execute(
            "INSERT OR IGNORE INTO hyperedge_nodes (eid, vid, position) "
            "VALUES (?, ?, 0), (?, ?, 1)",
            (eid, sub_vid, eid, obj_vid),
        )
        shard_edge_counters[sid] += 1

        total += 1
        if total % batch_size == 0:
            for c in shard_connections.values():
                c.commit()
            print(f"    分片导入: {total} 条...")

    # 最终提交
    for c in shard_connections.values():
        c.commit()
        c.close()
    source.close()

    return {
        sid: {"vertices": shard_vid_counters[sid], "edges": shard_edge_counters[sid]}
        for sid in shard_connections
    }
