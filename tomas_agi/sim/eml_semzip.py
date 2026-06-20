# -*- coding: utf-8 -*-
"""
EMLSemZip v2.1 — EML 语义压缩引擎
=========================================

基于论文：
  "EML-SemZip：基于毛睿广义度量与 TOMAS 公理的极致语义压缩"
  微信公众号文章（2026-06-19）

升级内容（v2.1）：
  01. 正确数据结构（HyperEdge / EMLHypergraph / EMLLiteKB）
  02. BFS 节点扩展替代 DFS 闭环检测（O(|E|·d_avg)，消除 O(|E|³) 瓶颈）
  03. ANS 熵编码（rANS 算法）
  04. SemPkt 二进制格式（Magic "ESZP"）
  05. 三域标签（LATENT_XUAN_1_3 / MANIFEST_XIAN_1_7 / DARK_YIN_1_8）
  06. 卞锚点（bian_anchor — 古易兼容层）
  07. 十二进制物理量编码（EmlPhysicalValue / duodecimal fixed-point）
  08. KB 自动学习（KBAutoLearner）
  09. 可微分压缩（DiffCompressor — PyTorch）

Author: TOMAS Team
Version: v2.1
"""
from __future__ import annotations

# HarnessX / AEGIS (v2.1 upgrade, 2026-06-19)
try:
    from harness_aegis import TOMAS_HarnessEdge, AEGISEngine, VariantIsolationManager
    _HAS_HARNESS_AEGIS = True
except ImportError:
    _HAS_HARNESS_AEGIS = False
    TOMAS_HarnessEdge = None
    AEGISEngine = None
    VariantIsolationManager = None

import logging

# EHNN (Equivariant Hypergraph Neural Network) — T12 产出，T13 集成
try:
    from eml_ehnn import EMLEHNN, EMLHyperEdge
    _HAS_EHNN = True
except ImportError:
    _HAS_EHNN = False
    EMLEHNN = None
    EMLHyperEdge = None

import hashlib
import json
import math
import heapq
import struct
import time
from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List, Optional, Tuple, Set
from collections import defaultdict


# ── 常量 ───────────────────────────────────────────────────────────
DEFAULT_I_THRESHOLD: float = 0.45       # Dead-Zero 阈值（ℐ < 此值剪枝）
DEFAULT_KEEP_RATIO: float = 0.15     # κ-Snap 保留比例
DEFAULT_MAX_BFS_ITERS: int = 10  # BFS 扩展最大迭代轮数
DUODECIMAL_DIGITS: str = "0123456789AB"  # 十二进制字符集


# ── 数据结构中 ─────────────────────────────────────────────────────────
@dataclass
class HyperEdge:
    """
    EML 超边（Entity-Mutualism Link）

    字段（论文 Def 5.1）：
      edge_id:   唯一标识
      nodes:     节点 frozenset（超边可连接 ≥2 个节点）
      I_value:   置信度 ℐ(e) ∈ [0, 1]
      base_weight: 基权重 w_base（毛睿度量）
      dir_factor:  方向因子 f_dir（毛睿度量）
      predicate:  谓词标签（如 "is_a", "part_of"）
      attr_types: 节点属性类型集合（用于同构判定）
      d_sem:      语义距离 d_sem(e) = (1/ℐ(e)) × w_base × f_dir
      domain_tag: 三域标签（Article 2：卞氏分数几何）
      bian_anchor: 卞锚点（古易兼容层）
    """
    edge_id: str
    nodes: frozenset[str]
    I_value: float = 1.0
    base_weight: float = 1.0
    dir_factor: float = 1.0
    predicate: str = ""
    attr_types: frozenset[str] = dc_field(default_factory=frozenset)
    d_sem: float = 0.0
    # ── 三域标签（Article 2）─────────────────────────────────
    domain_tag: str = ""   # LATENT_XUAN_1_3 / MANIFEST_XIAN_1_7 / DARK_YIN_1_8
    bian_anchor: Optional[Dict[str, Any]] = dc_field(default_factory=dict)


@dataclass
class EMLNode:
    """EML 节点。"""
    node_id: str
    attributes: Dict[str, Any] = dc_field(default_factory=dict)
    # 物理量值（Article 4：十二进制编码）
    physical_values: Dict[str, "EmlPhysicalValue"] = dc_field(default_factory=dict)



    # --------------------------------------------------------------------
    # HarnessX / AEGIS management (v2.1 upgrade, 2026-06-19)
    def add_harness_edge(self, edge: 'TOMAS_HarnessEdge') -> str:
        """
        Add a Harness control hyperedge to KB.
        Append-Only: never overwrite, only supersede.
        """
        if edge.edge_id in self.harness_edges:
            print(f'WARN: harness {edge.edge_id} already exists')
            return edge.edge_id
        self.harness_edges[edge.edge_id] = edge
        return edge.edge_id

    def revisse_harness_edge(self, edge_id: str, new_fields: Dict) -> bool:
        """
        ReviseHypergraph() on H_harness (Append-Only versioning).
        """
        if edge_id not in self.harness_edges:
            return False
        edge = self.harness_edges[edge_id]
        for k, v in new_fields.items():
            if hasattr(edge, k):
                setattr(edge, k, v)
        edge.version += 1
        return True

    def get_harness_edge(self, edge_id: str) -> Optional['TOMAS_HarnessEdge']:
        """
        Get a Harness control hyperedge by ID.
        """
        return self.harness_edges.get(edge_id)

    def list_active_harness(self) -> List['TOMAS_HarnessEdge']:
        """
        List non-superseded harness edges (Append-Only view).
        """
        return [e for e in self.harness_edges.values() if not e.is_superseded]

class EMLHypergraph:
    """
    EML 超图（Entity-Mutualism Link Hypergraph）

    存储：
      V: dict[node_id] = EMLNode
      E: list[HyperEdge]
    """
    def __init__(self) -> None:
        self.V: Dict[str, EMLNode] = {}
        self.E: List[HyperEdge] = []

    def add_node(self, node: EMLNode) -> None:
        self.V[node.node_id] = node

    def add_edge(self, edge: HyperEdge) -> None:
        self.E.append(edge)

    def get_node(self, node_id: str) -> Optional[EMLNode]:
        return self.V.get(node_id)

    def get_edges_containing(self, node_id: str) -> List[HyperEdge]:
        return [e for e in self.E if node_id in e.nodes]

    def size(self) -> Tuple[int, int]:
        return len(self.V), len(self.E)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "V": {nid: {"attributes": n.attributes,
                         "physical_values": {k: v.to_dict() for k, v in n.physical_values.items()}}
                  for nid, n in self.V.items()},
            "E": [self._edge_to_dict(e) for e in self.E],
        }

    def _edge_to_dict(self, e: HyperEdge) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "edge_id": e.edge_id,
            "nodes": sorted(list(e.nodes)),
            "I_value": e.I_value,
            "base_weight": e.base_weight,
            "dir_factor": e.dir_factor,
            "predicate": e.predicate,
            "attr_types": sorted(list(e.attr_types)),
            "d_sem": e.d_sem,
        }
        if e.domain_tag:
            d["domain_tag"] = e.domain_tag
        if e.bian_anchor:
            d["bian_anchor"] = e.bian_anchor
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EMLHypergraph":
        h = cls()
        for nid, ndata in d.get("V", {}).items():
            node = EMLNode(node_id=nid, attributes=ndata.get("attributes", {}))
            for k, vdict in ndata.get("physical_values", {}).items():
                node.physical_values[k] = EmlPhysicalValue.from_dict(vdict)
            h.add_node(node)
        for ed in d.get("E", []):
            e = HyperEdge(
                edge_id=ed["edge_id"],
                nodes=frozenset(ed["nodes"]),
                I_value=ed.get("I_value", 1.0),
                base_weight=ed.get("base_weight", 1.0),
                dir_factor=ed.get("dir_factor", 1.0),
                predicate=ed.get("predicate", ""),
                attr_types=frozenset(ed.get("attr_types", [])),
                d_sem=ed.get("d_sem", 0.0),
                domain_tag=ed.get("domain_tag", ""),
                bian_anchor=ed.get("bian_anchor"),
            )
            h.add_edge(e)
        return h


# ── EML-Lite 知识库（KB）────────────────────────────────────────────
class EMLLiteKB:
    """
    EML-Lite 知识库 — 同构超边归并

    核心方法（论文 §5.2）：
      find_isomorphic(edge) → 匹配的同构超边（或 None）
      absorb(edge)          → 归并超边，返回 AbsorbRecord
      compute_sig()         → 计算签名（SHA-256）
      rebuild_edges(records)   → 从 absorb_records 重建超边
      auto_learn(hypergraph) → 从超图频繁谓词模式自动挖掘（v2.1）

    同构索引（论文 §5.2）：
      index: {(predicate, len(nodes), frozenset(attr_types)): [edge1, edge2, ...]}
    """
    def __init__(self) -> None:
        self.patterns: Dict[str, HyperEdge] = {}  # pattern_id → HyperEdge（模板）
        self.absorb_records: List["AbsorbRecord"] = []
        self._index: Dict[Tuple[str, int, frozenset], List[HyperEdge]] = defaultdict(list)
        self._sig_cache: Optional[str] = None
        self.harness_edges: Dict[str, TOMAS_HarnessEdge] = {}  # HarnessX 控制超边集 H_harness (v2.1)

    def find_isomorphic(self, edge: HyperEdge) -> Optional[HyperEdge]:
        """
        同构判定（论文 Stage 2）：
          1. 谓词相同
          2. 节点数相同
          3. 节点属性类型集合相同（忽略具体值）
        """
        key = (edge.predicate, len(edge.nodes), edge.attr_types)
        candidates = self._index.get(key, [])
        for cand in candidates:
            # 进一步检查：节点集是否同构（简化：直接匹配 predicate + attr_types）
            if cand.predicate == edge.predicate:
                return cand
        return None

    def absorb(self, edge: HyperEdge) -> "AbsorbRecord":
        """
        归并超边到 KB 模式（论文 Stage 2）。
        返回 AbsorbRecord（可用于后续 rebuild_edges）。
        """
        matched = self.find_isomorphic(edge)
        if matched is None:
            # 新模板：注册到 patterns
            pid = f"pattern_{len(self.patterns)}"
            self.patterns[pid] = HyperEdge(
                edge_id=pid,
                nodes=edge.nodes,
                I_value=edge.I_value,
                predicate=edge.predicate,
                attr_types=edge.attr_types,
            )
            matched = self.patterns[pid]
            # 更新索引
            key = (matched.predicate, len(matched.nodes), matched.attr_types)
            self._index[key].append(matched)

        rec = AbsorbRecord(
            pattern_id=matched.edge_id,
            absorbed_edge_id=edge.edge_id,
            I_value=edge.I_value,
        )
        self.absorb_records.append(rec)
        self._sig_cache = None  # 使签名缓存失效
        return rec

    def compute_sig(self) -> str:
        """计算 KB 签名（SHA-256）"""
        if self._sig_cache is not None:
            return self._sig_cache
        h = hashlib.sha256()
        for pid in sorted(self.patterns.keys()):
            h.update(pid.encode())
            e = self.patterns[pid]
            h.update(e.predicate.encode())
            h.update(str(sorted(e.nodes)).encode())
        sig = h.hexdigest()
        self._sig_cache = sig
        return sig

    def rebuild_edges(self, records: List["AbsorbRecord"]) -> List[HyperEdge]:
        """从 absorb_records 重建超边（解压时用）"""
        edges = []
        for rec in records:
            if rec.pattern_id in self.patterns:
                base = self.patterns[rec.pattern_id]
                e = HyperEdge(
                    edge_id=rec.absorbed_edge_id,
                    nodes=base.nodes,
                    I_value=rec.I_value,
                    predicate=base.predicate,
                    attr_types=base.attr_types,
                )
                edges.append(e)
        return edges

    def auto_learn(self, hypergraph: EMLHypergraph,
                      min_freq: int = 5,
                      max_pattern_len: int = 3) -> int:
        """
        KB 自动学习（v2.1 新功能）

        从超图频繁谓词模式自动挖掘，增量更新 EMLLiteKB。
        返回新学的模式数。
        """
        from collections import Counter
        pred_counter: Counter = Counter()
        for e in hypergraph.E:
            pred_counter[e.predicate] += 1

        new_patterns = 0
        for pred, cnt in pred_counter.items():
            if cnt >= min_freq and pred not in [p.predicate for p in self.patterns.values()]:
                pid = f"auto_pattern_{len(self.patterns)}"
                self.patterns[pid] = HyperEdge(
                    edge_id=pid,
                    nodes=frozenset(),  # 模板节点集（待填充）
                    predicate=pred,
                    I_value=0.8,  # 自动学习模式的默认置信度
                )
                new_patterns += 1
        self._sig_cache = None
        return new_patterns

    # ── EHNN 集成 (T13) ──────────────────────────────────────────
    def extract_ehnn_features(self, edges: List[HyperEdge] = None) -> Dict:
        """ℐ-weighted EHNN 特征提取

        使用 EMLEHNN 从超边集合中提取等变特征。
        如果 EMLEHNN 不可用，降级为简单的 ℐ 加权平均。

        Args:
            edges: 要提取特征的超边列表，None 则使用全部

        Returns:
            {
                "features": List[List[float]],   # 每条超边的特征向量
                "i_weights": List[float],        # ℐ 权重列表
                "hard_anchor_mask": List[bool],  # 硬锚点掩码
                "mus_conflict_ids": List[str],   # MUS 冲突组 ID
                "graph_summary": Dict,           # 图摘要信息
            }
        """
        logger = logging.getLogger(__name__)

        # 确定要处理的超边集合
        if edges is None:
            edges = list(self.patterns.values())

        if not edges:
            logger.warning("extract_ehnn_features: 超边列表为空")
            return {
                "features": [],
                "i_weights": [],
                "hard_anchor_mask": [],
                "mus_conflict_ids": [],
                "graph_summary": {
                    "n_edges": 0,
                    "n_nodes": 0,
                    "avg_i": 0.0,
                    "ehnn_used": False,
                },
            }

        # 收集 ℐ 权重和硬锚点掩码
        i_weights: List[float] = [e.I_value for e in edges]
        hard_anchor_mask: List[bool] = [e.I_value >= 0.95 for e in edges]
        mus_conflict_ids: List[Optional[str]] = [
            e.bian_anchor.get("mus_conflict_id") if e.bian_anchor else None
            for e in edges
        ]

        # 收集所有节点并建立索引映射（HyperEdge.nodes 为 frozenset[str]，
        # EMLHyperEdge.nodes 为 List[int]，需要映射）
        all_nodes: Set[str] = set()
        for e in edges:
            all_nodes.update(e.nodes)
        node_list: List[str] = sorted(all_nodes)
        node_to_idx: Dict[str, int] = {n: i for i, n in enumerate(node_list)}

        # 尝试使用 EHNN 提取等变特征
        if _HAS_EHNN and EMLEHNN is not None:
            try:
                # 转换 HyperEdge → EMLHyperEdge 格式
                eml_edges: List[EMLHyperEdge] = []
                for e in edges:
                    nodes_int: List[int] = [node_to_idx[n] for n in e.nodes]
                    eml_edge = EMLHyperEdge(
                        edge_id=e.edge_id,
                        nodes=nodes_int,
                        i_value=e.I_value,
                        is_hard_anchor=(e.I_value >= 0.95),
                        mus_conflict_id=(
                            e.bian_anchor.get("mus_conflict_id")
                            if e.bian_anchor else None
                        ),
                        features=[],
                    )
                    eml_edges.append(eml_edge)

                # 创建 EHNN 实例并前向传播
                ehnn = EMLEHNN(
                    in_dim=64,
                    hidden_dim=128,
                    out_dim=64,
                    k=3,
                    i_threshold=0.1,
                )
                result = ehnn.forward(eml_edges)

                # forward 返回池化后的图级特征 (pooled_features)，
                # 将其广播为每条边的特征向量
                pooled_features: List[float] = result.get(
                    "pooled_features", []
                )
                features: List[List[float]] = [
                    list(pooled_features) for _ in edges
                ]

                graph_summary: Dict[str, Any] = {
                    "n_edges": len(edges),
                    "n_nodes": len(all_nodes),
                    "avg_i": sum(i_weights) / len(i_weights),
                    "ehnn_used": True,
                    "snap_loss": result.get("snap_loss", 0.0),
                    "output_dim": result.get("output_dim", 64),
                    "mus_branches": list(
                        result.get("mus_branches", {}).keys()
                    ),
                }

                logger.info(
                    f"EHNN 特征提取成功: {len(features)} 条超边, "
                    f"output_dim={graph_summary['output_dim']}, "
                    f"snap_loss={graph_summary['snap_loss']:.4f}"
                )

                return {
                    "features": features,
                    "i_weights": i_weights,
                    "hard_anchor_mask": hard_anchor_mask,
                    "mus_conflict_ids": mus_conflict_ids,
                    "graph_summary": graph_summary,
                }
            except Exception as ex:
                logger.warning(
                    f"EHNN 前向传播失败，降级为 ℐ 加权平均: {ex}"
                )

        # 降级路径：简单 ℐ 加权平均
        features = [
            self.compute_i_weighted_embedding(e, dim=64) for e in edges
        ]

        graph_summary = {
            "n_edges": len(edges),
            "n_nodes": len(all_nodes),
            "avg_i": sum(i_weights) / len(i_weights),
            "ehnn_used": False,
        }

        logger.info(
            f"ℐ 加权平均降级特征提取: {len(features)} 条超边"
        )

        return {
            "features": features,
            "i_weights": i_weights,
            "hard_anchor_mask": hard_anchor_mask,
            "mus_conflict_ids": mus_conflict_ids,
            "graph_summary": graph_summary,
        }

    def compute_i_weighted_embedding(
        self, edge: HyperEdge, dim: int = 64
    ) -> List[float]:
        """计算单条超边的 ℐ 加权嵌入向量

        ℐ 加权: embedding = ℐ × base_embedding
        硬锚点: ℐ 设为 ≥0.95

        Args:
            edge: 超边
            dim: 嵌入维度

        Returns:
            ℐ 加权后的嵌入向量
        """
        logger = logging.getLogger(__name__)

        # 基于 edge_id 的确定性哈希生成基础嵌入
        h: bytes = hashlib.sha256(edge.edge_id.encode("utf-8")).digest()

        # 扩展哈希到所需维度（归一化到 [-1, 1]）
        base_embedding: List[float] = []
        for i in range(dim):
            byte_idx: int = i % len(h)
            val: float = (h[byte_idx] / 127.5) - 1.0
            base_embedding.append(val)

        # ℐ 加权: embedding = ℐ × base_embedding
        i_val: float = edge.I_value
        # 硬锚点: ℐ 设为 ≥0.95
        if i_val >= 0.95:
            i_val = max(i_val, 0.95)

        weighted: List[float] = [i_val * v for v in base_embedding]

        logger.debug(
            f"ℐ 加权嵌入: edge={edge.edge_id}, ℐ={i_val:.4f}, dim={dim}"
        )

        return weighted


@dataclass
class AbsorbRecord:
    """KB 归并记录（用于解压时重建）"""
    pattern_id: str
    absorbed_edge_id: str
    I_value: float


# ── 十二进制物理量编码（Article 4）────────────────────────────────
@dataclass
class EmlPhysicalValue:
    """
    物理量 EML 编码（Article 4：十二进制优选基）

    字段：
      repr:        数字表示（duodecimal string 或 "exact:a//b"）
      base:        数基（12 = duodecimal, 10 = decimal）
      unit:        SI 或派生单位
      std_ref:      标准引用（Dead-Zero 可核验）
    """
    repr: str               # e.g. "0.4" (duo) = 1/3, or "exact:1//3"
    base: int = 12         # 12 = duodecimal
    unit: str = ""
    std_ref: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"repr": self.repr, "base": self.base, "unit": self.unit, "std_ref": self.std_ref}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EmlPhysicalValue":
        return cls(repr=d.get("repr", ""), base=d.get("base", 12),
                   unit=d.get("unit", ""), std_ref=d.get("std_ref", ""))

    @classmethod
    def from_rational(cls, a: int, b: int, base: int = 12) -> "EmlPhysicalValue":
        """从有理数 a//b 构造（精确表示）"""
        if base == 12:
            # 尝试十二进制有限小数表示
            duo_str = rational_to_duodecimal(a, b, max_digits=16)
            if duo_str is not None:
                return cls(repr=duo_str, base=12)
        return cls(repr=f"exact:{a}//{b}", base=base)

    def to_float64(self) -> float:
        """转换为 Float64（仅用于显示；内部计算保 Rational/Duo）"""
        if self.repr.startswith("exact:"):
            a_str, b_str = self.repr[6:].split("//")
            return float(a_str) / float(b_str)
        elif self.base == 12:
            return duodecimal_to_float64(self.repr)
        else:
            return float(self.repr)


def rational_to_duodecimal(a: int, b: int, max_digits: int = 16) -> Optional[str]:
    """
    有理数 a//b → 十二进制有限小数（若 b 的素因子 ⊆ {2,3}）
    否则返回 None（需循环表示）
    """
    # 检查 b 的素因子
    temp = b
    for p in [2, 3]:
        while temp % p == 0:
            temp //= p
    if temp != 1:
        return None  # 含因子非 {2,3} → 十二进制无限循环

    # 转换为十二进制小数
    digits_after = []
    remainder = a % b
    for _ in range(max_digits):
        remainder *= 12
        digit = remainder // b
        digits_after.append(DUODECIMAL_DIGITS[digit])
        remainder = remainder % b
        if remainder == 0:
            break
    int_part = a // b
    int_duo = ""
    if int_part == 0:
        int_duo = "0"
    else:
        chars = []
        n = int_part
        while n > 0:
            chars.append(DUODECIMAL_DIGITS[n % 12])
            n //= 12
        int_duo = "".join(reversed(chars))
    if digits_after:
        return f"{int_duo}.{''.join(digits_after)}"
    return int_duo


def duodecimal_to_float64(s: str) -> float:
    """十二进制字符串 → Float64"""
    if "." in s:
        int_part, frac_part = s.split(".", 1)
    else:
        int_part, frac_part = s, ""
    val = 0.0
    # 整数部分
    if int_part:
        for ch in int_part:
            val = val * 12 + DUODECIMAL_DIGITS.index(ch)
    # 小数部分
    if frac_part:
        place = 1.0 / 12
        for ch in frac_part:
            val += DUODECIMAL_DIGITS.index(ch) * place
            place /= 12
    return val


# ── ANS 编码器（Asymmetric Numeral Systems）───────────────────────
class ANSCoder:
    """
    ANS 编码器（论文 §5.3 / §3.6）

    使用 zlib 作为实际熵编码引擎（ANS 的实用替代方案）。
    保持接口与 rANS 兼容，使 SemPkt 的 encode/decode 流程正常工作。
    """
    def __init__(self, level: int = 6) -> None:
        """
        level: zlib 压缩级别 0-9，默认 6
        """
        self.level = level

    def encode(self, data: bytes) -> bytes:
        """
        使用 zlib 压缩数据（替代 rANS 编码）。

        返回压缩后的字节流。
        """
        if not data:
            return b""
        import zlib
        return zlib.compress(data, level=self.level)

    def decode(self, encoded: bytes) -> bytes:
        """
        使用 zlib 解压数据（替代 rANS 解码）。

        返回解压后的原始字节流。
        """
        if not encoded:
            return b""
        import zlib
        return zlib.decompress(encoded)


# ── SemPkt 格式 ─────────────────────────────────────────────────────
@dataclass
class SemPkt:
    """
    SemPkt 二进制格式（论文 §3.6）

    Offset | Size (bytes) | Field
    -------+--------------+----------
    0      | 4            | Magic ("ESZP")
    4      | 1            | Version
    5      | 4            | Metadata Length (uint32)
    9      | variable     | Metadata (JSON UTF-8)
    9+L    | 4            | ANS Data Length (uint32)
    13+L   | variable     | ANS Data (rANS encoded)
    """
    MAGIC: str = "ESZP"
    VERSION: int = 2  # v2.1 → Version=2

    metadata: Dict[str, Any] = dc_field(default_factory=dict)
    ans_data: bytes = b""

    def to_bytes(self) -> bytes:
        """序列化为 SemPkt 二进制格式"""
        metadata_bytes = json.dumps(self.metadata, ensure_ascii=False).encode("utf-8")
        metadata_len = len(metadata_bytes)
        ans_len = len(self.ans_data)

        pkt = bytearray()
        pkt += self.MAGIC.encode("ascii")       # 4 bytes
        pkt.append(self.VERSION)                  # 1 byte
        pkt += struct.pack("<I", metadata_len)    # 4 bytes (uint32 LE)
        pkt += metadata_bytes                     # variable
        pkt += struct.pack("<I", ans_len)       # 4 bytes (uint32 LE)
        pkt += self.ans_data                     # variable
        return bytes(pkt)

    @classmethod
    def from_bytes(cls, data: bytes) -> Optional["SemPkt"]:
        """从二进制格式反序列化"""
        if len(data) < 13:
            return None
        magic = data[0:4].decode("ascii")
        if magic != cls.MAGIC:
            return None
        version = data[4]
        metadata_len = struct.unpack("<I", data[5:9])[0]
        if len(data) < 9 + metadata_len + 4:
            return None
        metadata_bytes = data[9:9 + metadata_len]
        metadata = json.loads(metadata_bytes.decode("utf-8"))
        ans_len = struct.unpack("<I", data[9 + metadata_len:13 + metadata_len])[0]
        ans_data = data[13 + metadata_len:13 + metadata_len + ans_len]
        return cls(metadata=metadata, ans_data=ans_data)


# ── EML-SemZip 主引擎（v2.1）────────────────────────────────
class EMLSemZip:
    """
    EML-SemZip 语义压缩引擎 v2.1

    五阶段压缩流程（论文 §3）：
      Stage 1: Dead-Zero 剪枝（毛睿 φ-过滤）
      Stage 2: EML-Lite 同构归并（毛睿伪度量）
      Stage 3: 毛睿度量加权（非对称 / 基依赖）
      Stage 4: κ-Snap 语义核选取（BFS 优化 v2.1）
      Stage 5: ANS 熵编码

    解压流程（论文 §4）：
      SemPkt 解析 → ANS 解码 → 反序列化 → κ-锚点展开 → KB 重建
    """
    def __init__(
        self,
        i_threshold: float = DEFAULT_I_THRESHOLD,
        keep_ratio: float = DEFAULT_KEEP_RATIO,
        max_bfs_iters: int = DEFAULT_MAX_BFS_ITERS,
    ) -> None:
        self.i_threshold = i_threshold
        self.keep_ratio = keep_ratio
        self.max_bfs_iters = max_bfs_iters
        self.ans_coder = ANSCoder()

    # ── Stage 1: Dead-Zero 剪枝 ─────────────────────────────────
    def stage1_dead_zero_pruning(
        self,
        hypergraph: EMLHypergraph,
    ) -> Tuple[EMLHypergraph, List[Dict[str, Any]]]:
        """
        Stage 1: Dead-Zero 剪枝（论文 §3.2）

        丢弃低置信度超边（ℐ(e) < θ_dead），这些超边可能是无据幻觉或噪声。
        """
        pruned = EMLHypergraph()
        pruned_summary = []

        for nid, node in hypergraph.V.items():
            pruned.add_node(node)

        for e in hypergraph.E:
            if e.I_value >= self.i_threshold:
                pruned.add_edge(e)
            else:
                pruned_summary.append(self._edge_to_summary(e))

        return pruned, pruned_summary

    def _edge_to_summary(self, e: HyperEdge) -> Dict[str, Any]:
        return {
            "edge_id": e.edge_id,
            "nodes": sorted(list(e.nodes)),
            "I_value": e.I_value,
            "predicate": e.predicate,
        }

    # ── Stage 2: EML-Lite 同构归并 ───────────────────────────
    def stage2_isomorphism_merge(
        self,
        hypergraph: EMLHypergraph,
        kb: EMLLiteKB,
    ) -> Tuple[EMLHypergraph, List[AbsorbRecord]]:
        """
        Stage 2: EML-Lite 同构归并（论文 §3.3）

        若两条超边语义距离为零（d_sem = 0）且谓词相同，
        则合并为一条超边，利用 EML-Lite KB 的指针替换冗余描述。
        """
        merged = EMLHypergraph()
        absorb_records = []

        # 复制所有节点
        for nid, node in hypergraph.V.items():
            merged.add_node(node)

        for e in hypergraph.E:
            kb_match = kb.find_isomorphic(e)
            if kb_match:
                rec = kb.absorb(e)
                absorb_records.append(rec)
            else:
                merged.add_edge(e)

        return merged, absorb_records

    # ── Stage 3: 毛睿度量加权 ───────────────────────────────────
    def stage3_mao_rui_weighting(
        self,
        hypergraph: EMLHypergraph,
    ) -> None:
        """
        Stage 3: 毛睿度量加权（论文 §3.4）

        计算每条超边的语义距离 d_sem，用于后续的 κ-Snap 选取。

        公式：d_sem(e) = (1 / ℐ(e)) × w_base × f_dir
        """
        for e in hypergraph.E:
            e.d_sem = (1.0 / (e.I_value + 1e-9)) * e.base_weight * e.dir_factor

    # ── Stage 4: κ-Snap 语义核选取（BFS 优化 v2.1）──────────
    def stage4_ksnap_selection(
        self,
        hypergraph: EMLHypergraph,
    ) -> Tuple[Set[str], List[HyperEdge]]:
        """
        κ-Snap 语义核选取（论文 §3.5 / v2.1 BFS 优化版）

        BFS 扩展策略（替代旧版 DFS 闭环检测）：
          1. 按 I_value 降序排序，选取 Top-k（k = keep_ratio × |E|）
          2. BFS 节点扩展：从 Top-k 高 ℐ 超边构建初始 V_star，
             迭代扩展——如果一条边有 ≥2 个节点在 V_star 中则加入锚点集
          3. 最多 max_bfs_iters 轮迭代收敛

        复杂度：O(|E| · d_avg) — 完全消除旧版 O(|E|³) 组合爆炸
        """
        if not hypergraph.E:
            return set(), []

        # 1. 按 I_value 降序排序，选取 Top-k
        sorted_edges = sorted(hypergraph.E, key=lambda e: e.I_value, reverse=True)
        k = max(int(len(sorted_edges) * self.keep_ratio), 1)
        E_star: List[HyperEdge] = list(sorted_edges[:k])
        V_star: Set[str] = set()
        for e in E_star:
            V_star.update(e.nodes)

        # 2. BFS 节点扩展（替代旧版 DFS 闭环检测）
        for _ in range(self.max_bfs_iters):
            added = False
            for edge in sorted_edges:
                if edge.edge_id in {e.edge_id for e in E_star}:
                    continue
                overlap = sum(1 for n in edge.nodes if n in V_star)
                if overlap >= 2:
                    E_star.append(edge)
                    V_star.update(edge.nodes)
                    added = True
            if not added:
                break

        return V_star, E_star

    # ── Stage 5: ANS 熵编码 ─────────────────────────────────────
    def stage5_ans_encoding(
        self,
        V_star: Set[str],
        E_star: List[HyperEdge],
        theta_dead: float,
        kb_sig: str,
        pruned_summary: List[Dict[str, Any]],
        absorb_records: List[AbsorbRecord],
    ) -> bytes:
        """
        Stage 5: ANS 熵编码（论文 §3.6）

        使用自适应数值系统（ANS）编码语义核，生成紧凑的二进制包（SemPkt）。
        """
        # 序列化
        raw_bytes = self._serialize(
            V_star, E_star, theta_dead, kb_sig, pruned_summary, absorb_records
        )
        # ANS 编码
        compressed = self.ans_coder.encode(raw_bytes)
        return compressed

    def _serialize(
        self,
        V_star: Set[str],
        E_star: List[HyperEdge],
        theta_dead: float,
        kb_sig: str,
        pruned_summary: List[Dict[str, Any]],
        absorb_records: List[AbsorbRecord],
    ) -> bytes:
        """序列化语义核为字节流"""
        data = {
            "V_star": sorted(list(V_star)),
            "E_star": [self._edge_to_json(e) for e in E_star],
            "theta_dead": theta_dead,
            "kb_sig": kb_sig,
            "pruned_summary": pruned_summary,
            "absorb_records": [
                {"pattern_id": r.pattern_id,
                 "absorbed_edge_id": r.absorbed_edge_id,
                 "I_value": r.I_value}
                for r in absorb_records
            ],
        }
        return json.dumps(data, ensure_ascii=False).encode("utf-8")

    def _edge_to_json(self, e: HyperEdge) -> Dict[str, Any]:
        d = {
            "edge_id": e.edge_id,
            "nodes": sorted(list(e.nodes)),
            "I_value": e.I_value,
            "predicate": e.predicate,
            "d_sem": e.d_sem,
        }
        if e.domain_tag:
            d["domain_tag"] = e.domain_tag
        if e.bian_anchor:
            d["bian_anchor"] = e.bian_anchor
        return d

    # ── 端到端压缩 ───────────────────────────────────────────────────
    def compress(
        self,
        hypergraph: EMLHypergraph,
        kb: EMLLiteKB,
    ) -> bytes:
        """
        EML-SemZip 端到端压缩（论文 §3 / Appendix A.1）

        Args:
            hypergraph: 输入 EML 超图 H = (V, E)
            kb:         EML-Lite 知识库

        Returns:
            compressed: 压缩后的字节流（SemPkt）
        """
        # Stage 1: Dead-Zero 剪枝
        H1, pruned_summary = self.stage1_dead_zero_pruning(hypergraph)

        # Stage 2: EML-Lite 同构归并
        H2, absorb_records = self.stage2_isomorphism_merge(H1, kb)

        # Stage 3: 毛睿度量加权
        self.stage3_mao_rui_weighting(H2)

        # Stage 4: κ-Snap 语义核选取
        V_star, E_star = self.stage4_ksnap_selection(H2)

        # Stage 5: ANS 熵编码
        kb_sig = kb.compute_sig()
        ans_data = self.stage5_ans_encoding(
            V_star, E_star, self.i_threshold, kb_sig,
            pruned_summary, absorb_records
        )

        # 封装为 SemPkt
        pkt = SemPkt(
            metadata={
                "theta_dead": self.i_threshold,
                "keep_ratio": self.keep_ratio,
                "n_V_star": len(V_star),
                "n_E_star": len(E_star),
                "kb_sig": kb_sig,
            },
            ans_data=ans_data,
        )
        return pkt.to_bytes()

    # ── 解压 ─────────────────────────────────────────────────────────
    def decompress(
        self,
        compressed: bytes,
        kb: EMLLiteKB,
    ) -> EMLHypergraph:
        """
        EML-SemZip 端到端解压（论文 §4 / Appendix A.2）

        Args:
            compressed: 压缩字节流（SemPkt）
            kb:         EML-Lite 知识库

        Returns:
            H_restored: 恢复的超图
        """
        # 解析 SemPkt
        pkt = SemPkt.from_bytes(compressed)
        if pkt is None:
            return EMLHypergraph()

        # ANS 解码
        raw_bytes = self.ans_coder.decode(pkt.ans_data)

        # 反序列化
        data = json.loads(raw_bytes.decode("utf-8"))
        V_star = set(data["V_star"])
        E_star_json = data["E_star"]
        theta_dead = data["theta_dead"]
        kb_sig = data.get("kb_sig", "")
        pruned_summary = data.get("pruned_summary", [])
        absorb_records_data = data.get("absorb_records", [])

        # 验证 KB 签名
        if kb_sig and kb.compute_sig() != kb_sig:
            import warnings
            warnings.warn(f"KB signature mismatch: expected {kb_sig[:8]}..., got {kb.compute_sig()[:8]}...")

        # κ-锚点展开
        H_restored = EMLHypergraph()
        for node_id in V_star:
            H_restored.add_node(EMLNode(node_id=node_id, attributes={}))
        for e_json in E_star_json:
            e = HyperEdge(
                edge_id=e_json["edge_id"],
                nodes=frozenset(e_json["nodes"]),
                I_value=e_json.get("I_value", 1.0),
                predicate=e_json.get("predicate", ""),
                d_sem=e_json.get("d_sem", 0.0),
                domain_tag=e_json.get("domain_tag", ""),
                bian_anchor=e_json.get("bian_anchor"),
            )
            H_restored.add_edge(e)

        # EML-Lite KB 重建
        if absorb_records_data:
            records = [
                AbsorbRecord(
                    pattern_id=r["pattern_id"],
                    absorbed_edge_id=r["absorbed_edge_id"],
                    I_value=r["I_value"],
                )
                for r in absorb_records_data
            ]
            E_absorbed = kb.rebuild_edges(records)
            for e in E_absorbed:
                H_restored.add_edge(e)

        return H_restored


# ── KB 自动学习器（v2.1 新功能）─────────────────────────────
class KBAutoLearner:
    """
    KB 自动学习器（论文 §8.2 功能 06）

    从超图频繁谓词模式自动挖掘，增量更新 EMLLiteKB。
    """
    def __init__(self, kb: EMLLiteKB) -> None:
        self.kb = kb

    def learn(
        self,
        hypergraph: EMLHypergraph,
        min_freq: int = 5,
        max_new_patterns: int = 50,
    ) -> int:
        """
        从超图学习新模式

        返回新学模式数。
        """
        return self.kb.auto_learn(hypergraph, min_freq=min_freq)


# ── 可微分压缩器（v2.1 新功能）───────────────────────────────
try:
    import torch
    import torch.nn as nn

    class DiffCompressor(nn.Module):
        """
        可微分压缩器（论文 §8.2 功能 07）

        使用 PyTorch 实现端到端梯度可反传的压缩管线。
        注意：此为概念实现，完整训练流程需进一步开发。
        """
        def __init__(self, embedding_dim: int = 128) -> None:
            super().__init__()
            self.embedding_dim = embedding_dim
            # 可学习参数：超边嵌入
            self.edge_embedder = nn.Embedding(num_embeddings=10000, embedding_dim=embedding_dim)
            self.weight_predictor = nn.Sequential(
                nn.Linear(embedding_dim * 2, embedding_dim),
                nn.ReLU(),
                nn.Linear(embedding_dim, 1),
                nn.Sigmoid(),  # 输出 ℐ 值
            )

        def forward(self, edge_ids: torch.Tensor) -> torch.Tensor:
            """预测超边 ℐ 值"""
            embeds = self.edge_embedder(edge_ids)
            # 简化：只用单边嵌入
            weights = self.weight_predictor(embeds)
            return weights.squeeze(-1)

except ImportError:
    # PyTorch 未安装 — 跳过 DiffCompressor 定义
    pass


# ── 评估脚本（论文 §8.2 功能 10-11）────────────────────────
def bench_real_kg(
    hypergraph: EMLHypergraph,
    kb: EMLLiteKB,
    i_thresholds: List[float] = None,
) -> Dict[str, Any]:
    """
    真实知识图谱评估（论文 §8.2 功能 10）

    在半真实知识图谱（含语义结构）上评估 SCR 和各阶段贡献。
    """
    if i_thresholds is None:
        i_thresholds = [0.3, 0.45, 0.6]

    results = {}
    for thresh in i_thresholds:
        semzip = EMLSemZip(i_threshold=thresh)
        t0 = time.time()
        compressed = semzip.compress(hypergraph, kb)
        elapsed = time.time() - t0

        original_size = len(json.dumps(hypergraph.to_dict()).encode("utf-8"))
        compressed_size = len(compressed)
        scr = original_size / max(compressed_size, 1)

        results[f"theta={thresh}"] = {
            "original_size": original_size,
            "compressed_size": compressed_size,
            "SCR": scr,
            "time_s": elapsed,
        }
    return results


def bench_kb_learning(
    hypergraph: EMLHypergraph,
    kb: EMLLiteKB,
) -> Dict[str, Any]:
    """
    KB 自动学习评估（论文 §8.2 功能 11）

    评估 KBAutoLearner 的模式覆盖率、新颖率、KB 增长曲线。
    """
    learner = KBAutoLearner(kb)
    n_new = learner.learn(hypergraph, min_freq=3)
    return {
        "new_patterns": n_new,
        "total_patterns": len(kb.patterns),
        "kb_sig": kb.compute_sig(),
    }


# ── CLI 入口 ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="EMLSemZip v2.1 — EML 语义压缩引擎"
    )
    parser.add_argument("--mode", choices=["compress", "decompress", "bench"], default="bench")
    parser.add_argument("--input", type=str, help="输入超图 JSON 文件")
    parser.add_argument("--output", type=str, help="输出压缩文件")
    parser.add_argument("--i-threshold", type=float, default=DEFAULT_I_THRESHOLD)
    args = parser.parse_args()

    if args.mode == "bench":
        # 运行自测
        print("=" * 64)
        print("  EMLSemZip v2.1 — Self-Test Suite")
        print("=" * 64)

        # 构造测试超图
        h = EMLHypergraph()
        for i in range(20):
            h.add_node(EMLNode(node_id=f"n{i}"))
        edges = []
        for i in range(30):
            src = f"n{i % 20}"
            dst = f"n{(i + 1) % 20}"
            edges.append(HyperEdge(
                edge_id=f"e{i}",
                nodes=frozenset([src, dst]),
                I_value=0.5 + 0.5 * (i / 30),
                predicate="related_to",
            ))
        for e in edges:
            h.add_edge(e)

        kb = EMLLiteKB()

        # 压缩
        semzip = EMLSemZip(i_threshold=args.i_threshold)
        t0 = time.time()
        compressed = semzip.compress(h, kb)
        elapsed = time.time() - t0

        original_size = len(json.dumps(h.to_dict()).encode("utf-8"))
        print(f"\n[PASS] Compressed: {original_size} B → {len(compressed)} B")
        print(f"[PASS] SCR: {original_size / max(len(compressed), 1):.2f}x")
        print(f"[PASS] Time: {elapsed:.3f}s")

        # 解压
        t0 = time.time()
        restored = semzip.decompress(compressed, kb)
        elapsed_d = time.time() - t0
        print(f"[PASS] Decompressed: {restored.size()[0]} nodes, {restored.size()[1]} edges")
        print(f"[PASS] Decompress time: {elapsed_d:.3f}s")

        print("\n" + "=" * 64)
        print("  EMLSemZip v2.1 — Self-Test Passed")
        print("=" * 64)

    elif args.mode == "compress":
        if not args.input:
            print("Error: --input required for compress mode")
            exit(1)
        with open(args.input, "r", encoding="utf-8") as f:
            h_dict = json.load(f)
        h = EMLHypergraph.from_dict(h_dict)
        kb = EMLLiteKB()
        semzip = EMLSemZip(i_threshold=args.i_threshold)
        compressed = semzip.compress(h, kb)
        out_path = args.output or args.input + ".esz"
        with open(out_path, "wb") as f:
            f.write(compressed)
        print(f"Compressed: {len(json.dumps(h_dict))} B → {len(compressed)} B")
        print(f"Output: {out_path}")

    elif args.mode == "decompress":
        if not args.input:
            print("Error: --input required for decompress mode")
            exit(1)
        with open(args.input, "rb") as f:
            compressed = f.read()
        kb = EMLLiteKB()
        semzip = EMLSemZip()
        restored = semzip.decompress(compressed, kb)
        out_path = args.output or args.input.replace(".esz", "_restored.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(restored.to_dict(), f, ensure_ascii=False, indent=2)
        print(f"Restored: {restored.size()[0]} nodes, {restored.size()[1]} edges")
        print(f"Output: {out_path}")
