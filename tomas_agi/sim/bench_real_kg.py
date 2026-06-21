#!/usr/bin/env python3
"""
bench_real_kg.py — EMLSemZip v2.1 真实知识图谱评估脚本

论文 §8.2 功能 10：在真实 KG 数据（OwnThink / tomas.db）上评估压缩性能

使用方法:
    python bench_real_kg.py [--db PATH] [--limit N] [--repeat N]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from typing import List, Tuple

# ── 导入 EMLSemZip v2.1 ────────────────────────────────────────────────
try:
    from eml_semzip import (
        EMLSemZip,
        EMLHypergraph,
        HyperEdge,
        EMLNode,
        EMLiteKB,
        DEFAULT_I_THRESHOLD,
    )
    print("[OK] eml_semzip v2.1 导入成功")
except ImportError as e:
    print(f"[FAIL] 无法导入 eml_semzip: {e}")
    sys.exit(1)


# ── 数据结构 ─────────────────────────────────────────────────────────────
@dataclass
class BenchResult:
    """单次评估结果"""
    n_triples: int = 0
    n_nodes: int = 0
    n_edges: int = 0
    orig_size_bytes: int = 0
    comp_size_bytes: int = 0
    scr: float = 0.0
    compress_time_s: float = 0.0
    decompress_time_s: float = 0.0
    n_nodes_recovered: int = 0
    n_edges_recovered: int = 0
    roundtrip_ok: bool = False
    error: str = ""


# ── 主评估逻辑 ──────────────────────────────────────────────────────────
class RealKGBench:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.semzip = EMLSemZip()
        self.kb = EMLiteKB()

    def load_triples(self, limit: int) -> List[Tuple[str, str, str]]:
        """从 tomas.db 加载三元组"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT subject, predicate, object FROM knowledge_triples LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
        conn.close()
        return [(s, p, o) for s, p, o in rows]

    def triples_to_hypergraph(self, triples: List[Tuple[str, str, str]]) -> EMLHypergraph:
        """将三元组转换为 EMLHypergraph"""
        hg = EMLHypergraph()
        node_ids: dict[str, None] = {}

        for s, p, o in triples:
            for nid in (s, o):
                if nid not in node_ids:
                    node_ids[nid] = None
                    hg.add_node(EMLNode(node_id=nid, attributes={}))

            edge = HyperEdge(
                edge_id=f"edge_{s}_{p}_{o}",
                nodes=frozenset([s, o]),
                predicate=p,
                domain_tag="MANIFEST_XIAN_1_7",
            )
            hg.add_edge(edge)

        return hg

    def estimate_original_size(self, hg: EMLHypergraph) -> int:
        """估算原始 JSON 序列化大小（字节）"""
        data = {
            "nodes": {nid: {"semantic_weight": n.semantic_weight} for nid, n in hg.V.items()},
            "edges": [
                {"eid": e.eid, "nodes": list(e.nodes), "relation": e.relation}
                for e in hg.E
            ],
        }
        return len(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def run_once(self, triples: List[Tuple[str, str, str]]) -> BenchResult:
        """运行单次压缩-解压评估"""
        result = BenchResult(n_triples=len(triples))

        try:
            # 构建超图
            hg = self.triples_to_hypergraph(triples)
            result.n_nodes = len(hg.V)
            result.n_edges = len(hg.E)

            # 估算原始大小
            result.orig_size_bytes = self.estimate_original_size(hg)

            # 压缩
            t0 = time.perf_counter()
            pkt_bytes = self.semzip.compress(hg, self.kb, self.kb)
            result.compress_time_s = time.perf_counter() - t0

            result.comp_size_bytes = len(pkt_bytes)
            result.scr = result.orig_size_bytes / max(result.comp_size_bytes, 1)

            # 解压
            t0 = time.perf_counter()
            hg_rec = self.semzip.decompress(pkt_bytes, self.kb)
            result.decompress_time_s = time.perf_counter() - t0

            result.n_nodes_recovered = len(hg_rec.V)
            result.n_edges_recovered = len(hg_rec.E)
            result.roundtrip_ok = (
                result.n_nodes_recovered == result.n_nodes
                and result.n_edges_recovered == result.n_edges
            )

        except Exception as e:
            result.error = str(e)
            import traceback
            result.error += "\n" + traceback.format_exc()

        return result

    def run(self, limit: int = 1000, repeat: int = 1) -> List[BenchResult]:
        """运行完整评估"""
        print(f"\n{'='*60}")
        print(f"  Real KG Benchmark — limit={limit}, repeat={repeat}")
        print(f"{'='*60}\n")

        print(f"[1/3] 从数据库加载 {limit} 条三元组...")
        triples = self.load_triples(limit)
        print(f"  已加载 {len(triples)} 条三元组")

        results = []
        for i in range(repeat):
            print(f"\n[2/3] 运行第 {i+1}/{repeat} 次评估...")
            r = self.run_once(triples)
            results.append(r)
            self._print_result(r)

        print(f"\n{'='*60}")
        print("  汇总结果")
        print(f"{'='*60}")
        self._print_summary(results)
        return results

    def _print_result(self, r: BenchResult) -> None:
        if r.error:
            print(f"  [FAIL] {r.error}")
            return
        print(f"  三元组: {r.n_triples}")
        print(f"  节点:   {r.n_nodes}, 超边: {r.n_edges}")
        print(f"  原始:   {r.orig_size_bytes:,} B")
        print(f"  压缩后: {r.comp_size_bytes:,} B")
        print(f"  SCR:    {r.scr:.2f}x")
        print(f"  压缩耗时: {r.compress_time_s*1000:.1f} ms")
        print(f"  解压耗时: {r.decompress_time_s*1000:.1f} ms")
        print(f"  往返完整: {'YES' if r.roundtrip_ok else 'NO'}")

    def _print_summary(self, results: List[BenchResult]) -> None:
        ok = [r for r in results if not r.error]
        if not ok:
            print("  所有评估均失败")
            return
        avg_scr = sum(r.scr for r in ok) / len(ok)
        avg_ct = sum(r.compress_time_s for r in ok) / len(ok)
        avg_dt = sum(r.decompress_time_s for r in ok) / len(ok)
        all_rt = all(r.roundtrip_ok for r in ok)
        print(f"  有效次数: {len(ok)}/{len(results)}")
        print(f"  平均 SCR:    {avg_scr:.2f}x")
        print(f"  平均压缩耗时: {avg_ct*1000:.1f} ms")
        print(f"  平均解压耗时: {avg_dt*1000:.1f} ms")
        print(f"  往返完整:    {'ALL PASS' if all_rt else 'SOME FAIL'}")


# ── 入口 ────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="EMLSemZip 真实 KG 评估")
    parser.add_argument("--db", default="D:/tomas-data/tomas.db", help="tomas.db 路径")
    parser.add_argument("--limit", type=int, default=1000, help="加载三元组数量")
    parser.add_argument("--repeat", type=int, default=3, help="重复次数")
    args = parser.parse_args()

    bench = RealKGBench(args.db)
    bench.run(limit=args.limit, repeat=args.repeat)


if __name__ == "__main__":
    main()
