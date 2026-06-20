"""
HyperIndex DB-backed v2.0 — 超图数据库索引层
================================================

封装 SQLite 超图查询，支持 k-hop 子图按需加载 + 批量预取 + LRU 缓存。
避免将 101M+ 三元组全部装入内存，只在推理时加载相关子图。

v2.0 新增:
  - OrderedDict LRU 缓存 (真正 O(1) 淘汰)
  - 批量查询: get_vertices_batch / get_edges_batch
  - get_subgraph 预取优化 (一轮 SQL 加载所有边，再转换)
  - 连接池复用 + 统计信息

核心功能:
  1. 顶点/超边查询（按 ID 或概念名称）
  2. k-hop 子图扩展（BFS 通过 hyperedge_nodes 表）
  3. OrderedDict LRU 缓存（真正 O(1) 淘汰）
  4. 批量预取（避免 N+1 查询）
  5. 转换为 EML 内存格式（HypEdge / EMLVertex）
"""

from typing import List, Tuple, Dict, Set, Optional
from collections import OrderedDict
import json
import time

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session

from eml_dimred.hyperedge import HypEdge, EMLVertex


# ---- 数据库连接 ----
_ENGINE = None
_SESSION_FACTORY = None


def get_db_engine():
    """获取 SQLAlchemy 引擎 (单例)"""
    global _ENGINE
    if _ENGINE is None:
        import os
        DB_DIR = os.environ.get("TOMAS_DB_DIR", "D:/tomas-data")
        DB_PATH = os.path.join(DB_DIR, "tomas.db")
        _ENGINE = create_engine(
            f"sqlite:///{DB_PATH}",
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
    return _ENGINE


def get_db_session():
    """获取数据库连接会话"""
    global _SESSION_FACTORY
    if _SESSION_FACTORY is None:
        _SESSION_FACTORY = sessionmaker(bind=get_db_engine())
        _SESSION_FACTORY = scoped_session(_SESSION_FACTORY)
    return _SESSION_FACTORY()


class LRUCache:
    """
    OrderedDict LRU 缓存 — O(1) 淘汰。

    替代简单 dict，实现真正的 Least Recently Used 淘汰策略。
    """

    def __init__(self, maxsize: int = 10000):
        self._cache: OrderedDict = OrderedDict()
        self.maxsize = maxsize
        self.hits = 0
        self.misses = 0

    def get(self, key):
        """获取项，命中则移到末尾 (最近使用)"""
        if key in self._cache:
            self._cache.move_to_end(key)
            self.hits += 1
            return self._cache[key]
        self.misses += 1
        return None

    def put(self, key, value):
        """添加项，容量满时淘汰最久未使用"""
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self.maxsize:
                self._cache.popitem(last=False)  # 淘汰最旧
            self._cache[key] = value

    def clear(self):
        self._cache.clear()
        self.hits = 0
        self.misses = 0

    def __len__(self):
        return len(self._cache)

    def stats(self) -> Dict:
        total = self.hits + self.misses
        return {
            "size": len(self._cache),
            "maxsize": self.maxsize,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.hits / max(total, 1),
        }


class HyperIndex:
    """
    HyperIndex v2.0 — 超图数据库索引层

    封装 SQLite 超图表的查询，支持按需子图加载。
    使用 LRU 缓存避免重复查询，批量预取优化 k-hop 扩展。

    使用示例:
        hidx = HyperIndex(k_hops=2)
        vertices, edges = hidx.get_subgraph(["人工智能", "机器学习"], k=2)
        pruned, stats = matroid_prune(edges, vertices)
    """

    def __init__(self, session=None, k_hops: int = 2, cache_size: int = 10000):
        """
        Args:
            session: SQLAlchemy session（可选，默认自动创建）
            k_hops: 默认 k-hop 扩展跳数
            cache_size: 每类缓存大小上限
        """
        self.session = session or get_db_session()
        self.k_hops = k_hops

        # LRU 缓存
        self._v_cache = LRUCache(maxsize=cache_size)  # vid → EMLVertex
        self._e_cache = LRUCache(maxsize=cache_size)  # eid → HypEdge

        # 统计
        self._query_count = 0
        self._query_time = 0.0

    # ============ 顶点查询 ============

    def get_vertex(self, vid: int) -> Optional[EMLVertex]:
        """按 ID 获取顶点 (带 LRU 缓存)"""
        cached = self._v_cache.get(vid)
        if cached is not None:
            return cached

        t0 = time.perf_counter()
        sql = text("SELECT * FROM vertices WHERE vid = :vid")
        row = self.session.execute(sql, {"vid": vid}).fetchone()
        self._query_count += 1
        self._query_time += time.perf_counter() - t0

        if row is None:
            return None

        v = self._row_to_vertex(row)
        self._v_cache.put(vid, v)
        return v

    def get_vertices_batch(self, vids: List[int]) -> Dict[int, EMLVertex]:
        """
        批量获取顶点 — 一次 SQL 查询加载多个。

        Args:
            vids: 顶点 ID 列表

        Returns:
            vid → EMLVertex 字典（未找到的不在结果中）
        """
        if not vids:
            return {}

        # 先从缓存取
        result = {}
        missing = []
        for vid in vids:
            cached = self._v_cache.get(vid)
            if cached is not None:
                result[vid] = cached
            else:
                missing.append(vid)

        if not missing:
            return result

        # 批量查询未命中
        t0 = time.perf_counter()
        placeholders = ",".join([":vid_" + str(i) for i in range(len(missing))])
        params = {f"vid_{i}": vid for i, vid in enumerate(missing)}
        sql = text(f"SELECT * FROM vertices WHERE vid IN ({placeholders})")
        rows = self.session.execute(sql, params).fetchall()
        self._query_count += 1
        self._query_time += time.perf_counter() - t0

        for row in rows:
            v = self._row_to_vertex(row)
            self._v_cache.put(v.vid, v)
            result[v.vid] = v

        return result

    def get_vertex_by_name(self, concept: str) -> Optional[EMLVertex]:
        """按概念名称获取顶点"""
        t0 = time.perf_counter()
        sql = text("SELECT * FROM vertices WHERE concept = :concept LIMIT 1")
        row = self.session.execute(sql, {"concept": concept}).fetchone()
        self._query_count += 1
        self._query_time += time.perf_counter() - t0

        if row is None:
            return None

        v = self._row_to_vertex(row)
        self._v_cache.put(v.vid, v)
        return v

    def get_vertex_id_by_name(self, concept: str) -> Optional[int]:
        """按概念名称获取顶点 ID"""
        t0 = time.perf_counter()
        sql = text("SELECT vid FROM vertices WHERE concept = :concept LIMIT 1")
        row = self.session.execute(sql, {"concept": concept}).fetchone()
        self._query_count += 1
        self._query_time += time.perf_counter() - t0
        return row[0] if row else None

    def _row_to_vertex(self, row) -> EMLVertex:
        """将数据库行转换为 EMLVertex"""
        phi = [
            float(getattr(row, f"phi_b{i}", 0.0))
            for i in range(8)
        ]
        return EMLVertex(
            vid=getattr(row, "vid"),
            concept=getattr(row, "concept", ""),
            phi=phi,
            i_val=float(getattr(row, "i_val", 0.0)),
            degree_class=int(getattr(row, "degree_class", 0)),
        )

    # ============ 超边查询 ============

    def get_edge(self, eid: str) -> Optional[HypEdge]:
        """按 ID 获取超边 (带 LRU 缓存)"""
        cached = self._e_cache.get(eid)
        if cached is not None:
            return cached

        t0 = time.perf_counter()
        sql = text("SELECT * FROM hyperedges WHERE eid = :eid")
        row = self.session.execute(sql, {"eid": eid}).fetchone()
        self._query_count += 1
        self._query_time += time.perf_counter() - t0

        if row is None:
            return None

        e = self._row_to_edge(row)
        self._e_cache.put(eid, e)
        return e

    def get_edges_batch(self, eids: List[str]) -> Dict[str, HypEdge]:
        """
        批量获取超边 — 一次 SQL 查询加载多个。

        Args:
            eids: 超边 ID 列表

        Returns:
            eid → HypEdge 字典
        """
        if not eids:
            return {}

        result = {}
        missing = []
        for eid in eids:
            cached = self._e_cache.get(eid)
            if cached is not None:
                result[eid] = cached
            else:
                missing.append(eid)

        if not missing:
            return result

        t0 = time.perf_counter()
        placeholders = ",".join([":eid_" + str(i) for i in range(len(missing))])
        params = {f"eid_{i}": eid for i, eid in enumerate(missing)}
        sql = text(f"SELECT * FROM hyperedges WHERE eid IN ({placeholders})")
        rows = self.session.execute(sql, params).fetchall()
        self._query_count += 1
        self._query_time += time.perf_counter() - t0

        for row in rows:
            e = self._row_to_edge(row)
            self._e_cache.put(e.eid, e)
            result[e.eid] = e

        return result

    def get_edges_for_vertex(self, vid: int) -> List[HypEdge]:
        """获取顶点参与的所有超边"""
        t0 = time.perf_counter()
        sql = text(
            "SELECT DISTINCT eid FROM hyperedge_nodes WHERE vid = :vid"
        )
        eid_rows = self.session.execute(sql, {"vid": vid}).fetchall()
        self._query_count += 1
        self._query_time += time.perf_counter() - t0

        eids = [eid for (eid,) in eid_rows]
        edge_map = self.get_edges_batch(eids)
        return list(edge_map.values())

    def get_edges_for_concept(self, concept: str) -> List[HypEdge]:
        """按概念名称获取相关超边"""
        vid = self.get_vertex_id_by_name(concept)
        if vid is None:
            return []
        return self.get_edges_for_vertex(vid)

    def _row_to_edge(self, row) -> HypEdge:
        """将数据库行转换为 HypEdge"""
        nodes = json.loads(row.nodes) if isinstance(row.nodes, str) else row.nodes
        return HypEdge(
            nodes=tuple(nodes),
            eid=row.eid,
            i_val=float(row.i_val or 1.0),
            asym=float(row.asym or 0.0),
            weight=float(row.weight or 1.0),
            source=nodes[0] if len(nodes) > 0 else None,
            target=nodes[-1] if len(nodes) > 1 else None,
        )

    # ============ k-hop 子图扩展 (预取优化版) ============

    def get_subgraph(
        self, seeds: List[str], k: int = None
    ) -> Tuple[List[EMLVertex], List[HypEdge]]:
        """
        k-hop 子图扩展 (v2.0 预取优化版)

        算法:
          1. 获取种子顶点 ID
          2. BFS k-hop 扩展 (通过 hyperedge_nodes 表)
          3. 收集所有 eid 后批量加载边 (避免 N+1 查询)
          4. 从边中提取所有 vid 后批量加载顶点

        Args:
            seeds: 种子概念名称列表（如 ["人工智能", "机器学习"]）
            k: 跳数（默认使用 self.k_hops）

        Returns:
            (vertices, edges) — 子图中的顶点和超边列表
        """
        k = k or self.k_hops

        # 1. 获取种子顶点 ID
        seed_vids = []
        for concept in seeds:
            vid = self.get_vertex_id_by_name(concept)
            if vid is not None:
                seed_vids.append(vid)

        if not seed_vids:
            return [], []

        return self.get_subgraph_by_vids(seed_vids, k)

    def get_subgraph_by_vids(
        self, seed_vids: List[int], k: int = None
    ) -> Tuple[List[EMLVertex], List[HypEdge]]:
        """
        按顶点 ID 列表进行 k-hop 子图扩展 (v2.0 预取优化版)

        优化: 先批量收集 eid，再一次性加载边和顶点。
        """
        k = k or self.k_hops

        visited_vids: Set[int] = set(seed_vids)
        visited_eids: Set[str] = set()

        frontier = list(seed_vids)
        for hop in range(k):
            if not frontier:
                break

            # 批量查询: 获取 frontier 中所有顶点关联的超边
            placeholders = ",".join([f":vid_{i}" for i in range(len(frontier))])
            params = {f"vid_{i}": vid for i, vid in enumerate(frontier)}

            t0 = time.perf_counter()
            sql = text(
                f"SELECT DISTINCT eid, vid FROM hyperedge_nodes "
                f"WHERE vid IN ({placeholders})"
            )
            rows = self.session.execute(sql, params).fetchall()
            self._query_count += 1
            self._query_time += time.perf_counter() - t0

            next_vids = []
            for row in rows:
                eid, vid = row.eid, row.vid
                if eid in visited_eids:
                    continue
                visited_eids.add(eid)
                if vid not in visited_vids:
                    visited_vids.add(vid)
                    next_vids.append(vid)

            frontier = next_vids

        # 3. 批量加载所有边 (一轮 SQL)
        edges = []
        if visited_eids:
            edge_map = self.get_edges_batch(list(visited_eids))
            # 收集边中所有顶点
            all_edge_vids = set()
            for e in edge_map.values():
                edges.append(e)
                all_edge_vids.update(e.nodes)
            visited_vids.update(all_edge_vids)

        # 4. 批量加载所有顶点 (一轮 SQL)
        vertices = list(self.get_vertices_batch(list(visited_vids)).values())

        return vertices, edges

    # ============ 转换为 EML 格式 ============

    def to_eml_format(
        self, vertices: List[EMLVertex], edges: List[HypEdge]
    ) -> Tuple[List[EMLVertex], List[HypEdge]]:
        """直接返回 (无需转换，已经是标准格式)"""
        return vertices, edges

    # ============ 统计与缓存管理 ============

    def clear_cache(self):
        """清空所有缓存"""
        self._v_cache.clear()
        self._e_cache.clear()

    def cache_stats(self) -> Dict:
        """返回缓存统计信息"""
        return {
            "vertex_cache": self._v_cache.stats(),
            "edge_cache": self._e_cache.stats(),
        }

    def query_stats(self) -> Dict:
        """返回查询统计信息"""
        return {
            "query_count": self._query_count,
            "query_time_total": round(self._query_time, 4),
            "query_time_avg": round(
                self._query_time / max(self._query_count, 1), 6
            ),
        }

    def stats(self) -> Dict:
        """返回数据库统计信息"""
        v_count = self.session.execute(
            text("SELECT COUNT(*) FROM vertices")
        ).scalar()
        e_count = self.session.execute(
            text("SELECT COUNT(*) FROM hyperedges")
        ).scalar()
        n_count = self.session.execute(
            text("SELECT COUNT(*) FROM hyperedge_nodes")
        ).scalar()

        return {
            "vertex_count": v_count,
            "edge_count": e_count,
            "node_count": n_count,
            "cache": self.cache_stats(),
            "query": self.query_stats(),
        }

    def close(self):
        """关闭数据库连接"""
        if self.session:
            self.session.close()
