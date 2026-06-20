"""
EML 数学降维工具箱 (EML Slimming Toolkit)
===========================================

基于章锋《数学降维与 EML 超图可解性：GPCT 边界层降解 · 虚时计算(ITC) · 拟阵(Matroid) · Brown‑Miklós FPT》
(2026-06-15, 复合体理学)

四合一架构：
  ITC（识别边界层+退火初值）→ GPCT（分层STR-F）→ 拟阵（剪枝保基）→ 输出

统一主定理：若 EML 超图 H 源自太一投影且服从公理 A1（ℐ守恒），
则存在度类划分使 k = 活跃 κ-bin 数 ≤ 参数，
此时 H 通过 Brown‑Miklós + GPCT + 拟阵属于 FPT；ITC 提供物理搜索引擎。

核心模块 (v2.0):
  数据模型:
  - hyperedge: HypEdge 超边数据模型 (v1.0 二元边)
  - eml_v2: EML v2.0 n元超边二进制格式 (2026-06-19)

  降维引擎:
  - hyperindex: HyperIndex v2.0 DB-backed k-hop 子图按需加载 (LRU cache)
  - matroid: 拟阵贪心剪枝 (κ-Gate 最优独立集)
  - unionfind_matroid: Union-Find 拟阵回路检测 O(|E|·α(|V|)) (2026-06-19)
  - gpct: GPCT 边界层分解 (STR-F 分层 SAT 降解)
  - itc: ITC 虚时退火 (Wick 旋转基态搜索)
  - brown_miklos: Brown‑Miklós FPT 度类压缩
  - strf: STR-F 四大等价变换
  - pipeline: slim_eml 完整瘦身流水线

  分布式:
  - chaindb_bridge: 分布式超图数据库 (ChainDB RelationIndex + HyperShard) (2026-06-19)
"""

from .hyperedge import HypEdge, EMLVertex, load_eml_graph
from .hyperindex import HyperIndex, LRUCache
from .matroid import Matroid, matroid_prune
from .unionfind_matroid import UnionFind, HyperCircuitDetector, matroid_prune_unionfind
from .gpct import GpctDecomposer, gpct_decompose
from .itc import ItcAnneal, itc_anneal
from .brown_miklos import BrownMiklosCompressor, brown_miklos_compress
from .strf import StrfTransformer
from .pipeline import slim_eml, DimredResult
from .eml_v2 import save_eml_v2, load_eml_v2, convert_v1_to_v2, build_nary_edge
from .chaindb_bridge import HyperShard, ShardInfo, DistributedHyperIndex, shard_knowledge_triples

__all__ = [
    # 数据模型
    "HypEdge",
    "EMLVertex",
    "load_eml_graph",
    # EML v2.0
    "save_eml_v2",
    "load_eml_v2",
    "convert_v1_to_v2",
    "build_nary_edge",
    # HyperIndex v2.0
    "HyperIndex",
    "LRUCache",
    # 拟阵
    "Matroid",
    "matroid_prune",
    "UnionFind",
    "HyperCircuitDetector",
    "matroid_prune_unionfind",
    # 降维引擎
    "GpctDecomposer",
    "gpct_decompose",
    "ItcAnneal",
    "itc_anneal",
    "BrownMiklosCompressor",
    "brown_miklos_compress",
    "StrfTransformer",
    "slim_eml",
    "DimredResult",
    # 分布式超图
    "HyperShard",
    "ShardInfo",
    "DistributedHyperIndex",
    "shard_knowledge_triples",
]

__version__ = "2.0.0"
