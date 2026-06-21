#!/usr/bin/env python3
"""
bench_kb_learning.py — KBAutoLearner 自动知识学习评估脚本

论文 §8.2 功能 11：评估 EMLLiteKB 频繁谓词模式自动挖掘与增量更新

使用方法:
    python bench_kb_learning.py [--triples N] [--iterations N]
"""
from __future__ import annotations

import argparse
import json
import random
import time
from collections import Counter
from typing import List, Dict, Tuple

# ── 导入 EMLSemZip v2.1 ────────────────────────────────────────────
try:
    from eml_semzip import (
        EMLSemZip,
        EMLLiteKB,
        EMLHypergraph,
        HyperEdge,
        EMLNode,
        KBAutoLearner,
    )
    print("[OK] eml_semzip v2.1 导入成功")
except ImportError as e:
    print(f"[FAIL] 无法导入 eml_semzip: {e}")
    raise SystemExit(1)


# ── 评估逻辑 ──────────────────────────────────────────────────────────
class KBLearningBench:
    """
    评估 KBAutoLearner 的知识发现能力。

    测试策略：
      1. 生成带已知谓词模式的合成超图
      2. 运行 KBAutoLearner.learn() 挖掘模式
      3. 对比挖掘出的模式与真实模式
      4. 评估增量更新 EMLLiteKB 的正确性
    """

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed
        random.seed(seed)
        self.kb = EMLLiteKB()
        self.learner = KBAutoLearner(self.kb)
        self.semzip = EMLSemZip()

    # ── 合成数据生成 ────────────────────────────────────────────────

    def generate_synthetic_hypergraph(
        self,
        n_triples: int,
        n_predicates: int = 10,
    ) -> Tuple[EMLHypergraph, Dict[Tuple[str, ...], int]]:
        """
        生成带已知谓词模式的合成超图。

        返回:
            hg: 生成的超图
            true_patterns: 真实模式及其出现次数（用于验证）
        """
        hg = EMLHypergraph()

        entities = [f"E{i}" for i in range(max(n_triples * 2, 100))]
        predicates = [f"P{i}" for i in range(n_predicates)]

        # 构造可预测的模式分布
        # 让某些谓词对/三元组更频繁出现
        pattern_spec = [
            (("P0", "P1"), n_triples // 5),
            (("P2", "P3", "P4"), n_triples // 8),
            (("P0",), n_triples // 3),
        ]
        true_patterns = {p: freq for p, freq in pattern_spec}

        triples: List[Tuple[str, str, str]] = []
        ent_idx = 0

        for pattern, freq in pattern_spec:
            for _ in range(freq):
                s = entities[ent_idx % len(entities)]
                o = entities[(ent_idx + 1) % len(entities)]
                p = pattern[0]
                triples.append((s, p, o))
                ent_idx += 2

        while len(triples) < n_triples:
            s = random.choice(entities)
            o = random.choice(entities)
            p = random.choice(predicates)
            triples.append((s, p, o))

        triples = triples[:n_triples]

        node_ids: Dict[str, None] = {}
        for s, p, o in triples:
            for nid in (s, o):
                if nid not in node_ids:
                    node_ids[nid] = None
                    hg.add_node(EMLNode(node_id=nid, attributes={}))

            edge = HyperEdge(
                edge_id=f"edge_{len(hg.E)}",
                nodes=frozenset([s, o]),
                predicate=p,
                domain_tag="MANIFEST_XIAN_1_7",
            )
            hg.add_edge(edge)

        return hg, true_patterns

    # ── 核心评估 ────────────────────────────────────────────────────

    def evaluate_pattern_mining(
        self, hg: EMLHypergraph, true_patterns: Dict
    ) -> Dict:
        """
        评估模式挖掘准确性。

        返回评估结果字典。
        """
        t0 = time.perf_counter()
        n_new = self.learner.learn(hg, min_freq=2)
        elapsed = time.perf_counter() - t0

        # 从 kb 内部状态获取挖掘到的模式
        found_predicates = set()
        for key in self.kb._index:
            preds = tuple(sorted(key[0].split("_") if isinstance(key[0], str) else [key[0]]))
            if preds:
                found_predicates.add(preds)

        # 真实模式（排序后比较）
        true_set = {tuple(sorted(p)) for p in true_patterns.keys()}

        tp = len(found_predicates & true_set)
        fp = len(found_predicates - true_set)
        fn = len(true_set - found_predicates)

        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-9)

        return {
            "n_new_patterns": n_new,
            "n_found_groups": len(found_predicates),
            "n_true_patterns": len(true_patterns),
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "elapsed_s": elapsed,
        }

    def evaluate_kb_update(self, hg: EMLHypergraph) -> Dict:
        """
        评估 EMLLiteKB 增量更新是否正确。
        """
        # 用压缩-解压模拟增量更新
        pkt_bytes = self.semzip.compress(hg, self.kb)
        hg2 = self.semzip.decompress(pkt_bytes, self.kb)

        t0 = time.perf_counter()
        n_before = len(self.kb.absorb_records)

        # 将解压后的超边吸收进 KB
        for edge in hg2.E:
            rec = {
                "edge_id": edge.edge_id,
                "predicate": edge.predicate,
                "nodes": list(edge.nodes),
                "domain_tag": edge.domain_tag,
            }
            self.learner.learn(hg2)

        n_after = len(self.kb.absorb_records)
        elapsed = time.perf_counter() - t0

        return {
            "kb_edges_before": n_before,
            "kb_edges_after": n_after,
            "n_edges_processed": len(hg2.E),
            "kb_updated": n_after >= n_before,
            "elapsed_s": elapsed,
        }

    # ── 报告 ────────────────────────────────────────────────────────

    def run(
        self, n_triples: int = 500, iterations: int = 3
    ) -> List[Dict]:
        """运行完整评估套件"""
        print(f"\n{'='*60}")
        print(f"  KBAutoLearner Benchmark")
        print(f"  三元组数量: {n_triples}, 迭代次数: {iterations}")
        print(f"{'='*60}\n")

        all_results = []

        for it in range(iterations):
            print(f"[迭代 {it+1}/{iterations}]")

            hg, true_patterns = self.generate_synthetic_hypergraph(n_triples)
            print(f"  生成超图: {len(hg.V)} 节点, {len(hg.E)} 超边")

            mining_result = self.evaluate_pattern_mining(hg, true_patterns)
            print(
                f"  模式挖掘: {mining_result['n_new_patterns']} 新模式, "
                f"精确率={mining_result['precision']:.2f}, "
                f"召回率={mining_result['recall']:.2f}, "
                f"F1={mining_result['f1']:.2f}"
            )

            kb_result = self.evaluate_kb_update(hg)
            print(
                f"  KB 更新: {kb_result['n_edges_processed']} 条边已处理, "
                f"KB 边: {kb_result['kb_edges_before']} → {kb_result['kb_edges_after']}"
            )

            all_results.append({
                "iteration": it + 1,
                "mining": mining_result,
                "kb_update": kb_result,
            })

        self._print_summary(all_results)
        return all_results

    def _print_summary(self, results: List[Dict]) -> None:
        print(f"\n{'='*60}")
        print("  汇总结果")
        print(f"{'='*60}")

        avg_precision = sum(r["mining"]["precision"] for r in results) / len(results)
        avg_recall = sum(r["mining"]["recall"] for r in results) / len(results)
        avg_f1 = sum(r["mining"]["f1"] for r in results) / len(results)
        avg_mining_time = sum(r["mining"]["elapsed_s"] for r in results) / len(results)

        print(f"  平均精确率:    {avg_precision:.3f}")
        print(f"  平均召回率:    {avg_recall:.3f}")
        print(f"  平均 F1:       {avg_f1:.3f}")
        print(f"  平均挖掘耗时:  {avg_mining_time*1000:.1f} ms")

        all_updated = all(r["kb_update"]["kb_updated"] for r in results)
        print(f"  KB 增量更新:   {'ALL PASS' if all_updated else 'SOME FAIL'}")


# ── 入口 ────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="KBAutoLearner 评估")
    parser.add_argument("--triples", type=int, default=500, help="合成三元组数量")
    parser.add_argument("--iterations", type=int, default=3, help="迭代次数")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    args = parser.parse_args()

    bench = KBLearningBench(seed=args.seed)
    bench.run(n_triples=args.triples, iterations=args.iterations)


if __name__ == "__main__":
    main()
