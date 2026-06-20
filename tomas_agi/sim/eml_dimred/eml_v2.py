"""
EML v2.0 二进制格式 — 支持 n 元超边
=====================================

EML v1.0 限制: 每条边仅支持 2 个端点 (src, dst)，无法表达超图的 n 元关系。
EML v2.0 突破: 支持任意 n 元超边，利用变长编码实现高效存储。

格式对比:
  v1.0: Header(72B) + Vertices(N*80B) + Edges(M*32B)  → 仅二元边
  v2.0: Header(96B) + Vertices(N*80B) + Edges(变长)    → n 元超边 + φ场边级

EML v2.0 Header (96B, 小端序):
  Offset  Size  Field              Description
  0       4     magic              0x454D4C32 ('EML2')
  4       4     version            0x00000200
  8       4     num_vertices       N
  12      4     num_edges          M
  16      4     flags              bit0: has_phi_per_edge
  20      8     laplacian_alpha    double
  28      8     graph_delta        double
  36      8     timestamp          uint64
  44      8     total_i_sum        double (ℐ 守恒和)
  52      44    reserved           padding

EML v2.0 Vertex (80B, 与 v1.0 兼容):
  Offset  Size  Field
  0       4     vertex_id (int32)
  4       4     padding
  8       64    octonion[8] (8×double)
  72      8     delta (=ℐ) (double)

EML v2.0 Edge (变长):
  Offset  Size   Field
  0       2      arity (uint16) — n = 2..65535
  2       4*n    nodes[n] (n×int32) — 端点 ID 列表
  2+4*n   8      weight (double)
  10+4*n  8      delta_weight (double)
  18+4*n  8      asym (double) — φ 场非结合标量
  26+4*n  [可选] octonion_edge[8] (8×double, 64B, 仅当 flags&0x01)

总边大小: 26 + 4*n + (64 if has_phi_per_edge else 0) 字节

example: n=2, no phi → 34B; n=4, with phi → 106B

向后兼容:
  load_eml_v2() 自动检测 magic → 路由到 v1.0 或 v2.0 解析器
  save_eml_v2() 支持从 HypEdge 列表写入 v2.0
  convert_v1_to_v2() 升级旧 .eml 文件
"""

import struct
from typing import List, Tuple, Dict, Optional, BinaryIO
from pathlib import Path
import json

from eml_dimred.hyperedge import HypEdge, EMLVertex

# 常量
EML_V2_MAGIC = 0x454D4C32  # 'EML2'
EML_V2_VERSION = 0x00000200
EML_V1_MAGIC = 0x454D4C47  # 'EMLG'

V2_HEADER_SIZE = 96
V2_HEADER_FMT = "<IIIIIddQd44s"  # 96B

VERTEX_SIZE = 80
VERTEX_FMT = "<ii8dd"  # 80B

# 边变长字段
EDGE_ARITY_FMT = "<H"      # uint16 arity
EDGE_FIXED_FMT = "<ddd"    # weight, delta_weight, asym (固定24B)
PHI_EDGE_FMT = "<8d"       # octonion_edge[8] (64B)


# ============ 写入 ============

def save_eml_v2(
    filepath: str,
    vertices: List[EMLVertex],
    edges: List[HypEdge],
    laplacian_alpha: float = 0.0,
    graph_delta: float = 0.0,
    has_phi_per_edge: bool = False,
) -> None:
    """
    将超图数据写入 EML v2.0 文件。

    Args:
        filepath: 输出 .eml 文件路径
        vertices: 顶点列表
        edges: 超边列表（支持 n 元）
        laplacian_alpha: 谱拉普拉斯参数
        graph_delta: 图级 ℐ 值
        has_phi_per_edge: 是否为每条边附加 φ 场
    """
    import time as _time

    num_v = len(vertices)
    num_e = len(edges)

    # 计算 ℐ 守恒和
    total_i = sum(e.i_val for e in edges)

    # Flags
    flags = 0x01 if has_phi_per_edge else 0x00

    with open(filepath, "wb") as f:
        # ---- Header ----
        f.write(struct.pack(
            V2_HEADER_FMT,
            EML_V2_MAGIC,          # magic
            EML_V2_VERSION,        # version
            num_v,                 # num_vertices
            num_e,                 # num_edges
            flags,                 # flags
            laplacian_alpha,       # laplacian_alpha
            graph_delta,           # graph_delta
            int(_time.time()),     # timestamp
            total_i,               # total_i_sum
            b"\x00" * 44,          # reserved
        ))

        # ---- Vertices ----
        for v in vertices:
            phi = v.phi if len(v.phi) >= 8 else v.phi + [0.0] * (8 - len(v.phi))
            f.write(struct.pack(
                VERTEX_FMT,
                v.vid,
                0,  # padding
                phi[0], phi[1], phi[2], phi[3],
                phi[4], phi[5], phi[6], phi[7],
                v.i_val,
            ))

        # ---- Edges (变长) ----
        for e in edges:
            n = e.arity
            f.write(struct.pack(EDGE_ARITY_FMT, n))
            # 节点列表
            node_data = struct.pack(f"<{n}i", *e.nodes)
            f.write(node_data)
            # 固定字段
            f.write(struct.pack(
                EDGE_FIXED_FMT,
                e.weight,
                e.delta_weight,
                e.asym,
            ))
            # 可选 φ 场
            if has_phi_per_edge:
                phi_edge = [0.0] * 8
                f.write(struct.pack(PHI_EDGE_FMT, *phi_edge))


# ============ 读取 ============

def load_eml_v2(filepath: str) -> Tuple[List[EMLVertex], List[HypEdge], Dict]:
    """
    从 EML v2.0 文件加载超图。

    自动检测版本: 如果 magic 是 v1.0 ('EMLG')，则调用 load_eml_v1 兼容加载。

    Returns:
        (vertices, edges, metadata)
    """
    with open(filepath, "rb") as f:
        magic = struct.unpack("<I", f.read(4))[0]
        f.seek(0)

        if magic == EML_V1_MAGIC:
            return _load_eml_v1_from_file(f, filepath)
        elif magic != EML_V2_MAGIC:
            raise ValueError(
                f"Unknown EML magic: 0x{magic:08X}, "
                f"expected 0x{EML_V2_MAGIC:08X} (v2) or 0x{EML_V1_MAGIC:08X} (v1)"
            )

        return _load_eml_v2_from_file(f)

def _load_eml_v2_from_file(f: BinaryIO) -> Tuple[List[EMLVertex], List[HypEdge], Dict]:
    """从文件流加载 EML v2.0"""
    # Header
    (
        magic, version, num_v, num_e, flags,
        laplacian_alpha, graph_delta, timestamp, total_i, _reserved,
    ) = struct.unpack(V2_HEADER_FMT, f.read(V2_HEADER_SIZE))

    has_phi_per_edge = bool(flags & 0x01)

    metadata = {
        "format": "EML v2.0",
        "magic": f"0x{magic:08X}",
        "version": f"0x{version:08X}",
        "num_vertices": num_v,
        "num_edges": num_e,
        "flags": f"0x{flags:08X}",
        "has_phi_per_edge": has_phi_per_edge,
        "laplacian_alpha": laplacian_alpha,
        "graph_delta": graph_delta,
        "timestamp": timestamp,
        "total_i_sum": total_i,
    }

    # Vertices
    vertices = []
    for i in range(num_v):
        data = f.read(VERTEX_SIZE)
        (
            vid, _pad,
            b0, b1, b2, b3, b4, b5, b6, b7,
            i_val,
        ) = struct.unpack(VERTEX_FMT, data)
        vertices.append(EMLVertex(
            vid=vid,
            concept=f"v{vid}",
            phi=[b0, b1, b2, b3, b4, b5, b6, b7],
            i_val=i_val,
        ))

    # Edges (变长)
    edges = []
    for i in range(num_e):
        arity = struct.unpack(EDGE_ARITY_FMT, f.read(2))[0]
        # 节点列表
        nodes_data = f.read(4 * arity)
        nodes = list(struct.unpack(f"<{arity}i", nodes_data))
        # 固定字段
        fixed_data = f.read(24)
        weight, delta_weight, asym = struct.unpack(EDGE_FIXED_FMT, fixed_data)
        # 可选 φ 场
        if has_phi_per_edge:
            f.read(64)  # skip phi_edge (暂不使用)

        edges.append(HypEdge(
            nodes=tuple(nodes),
            eid=f"e_{i}",
            i_val=abs(weight),
            asym=asym,
            weight=weight,
            delta_weight=delta_weight,
            source=nodes[0] if len(nodes) > 0 else None,
            target=nodes[-1] if len(nodes) > 1 else None,
        ))

    return vertices, edges, metadata


def _load_eml_v1_from_file(f: BinaryIO, filepath: str) -> Tuple[List[EMLVertex], List[HypEdge], Dict]:
    """
    兼容加载 EML v1.0 文件（路由到 hyperedge.load_eml_graph）

    由于 v1.0 数据格式不同（固定 32B 边），这里调用现有解析器。
    """
    f.seek(0)
    data = f.read()

    # Header
    magic, version, num_v, num_e = struct.unpack_from("<IIII", data, 0)
    laplacian_alpha, graph_delta = struct.unpack_from("<dd", data, 16)
    timestamp = struct.unpack_from("<Q", data, 32)[0]

    metadata = {
        "format": "EML v1.0 (compat mode)",
        "magic": f"0x{magic:08X}",
        "version": f"0x{version:08X}",
        "num_vertices": num_v,
        "num_edges": num_e,
        "laplacian_alpha": laplacian_alpha,
        "graph_delta": graph_delta,
        "timestamp": timestamp,
    }

    # Vertices (80B each, v1.0 compatible)
    vertices = []
    offset = 72
    for i in range(num_v):
        vid, _pad = struct.unpack_from("<ii", data, offset)
        phi = list(struct.unpack_from("<8d", data, offset + 8))
        delta = struct.unpack_from("<d", data, offset + 72)[0]
        vertices.append(EMLVertex(vid=vid, concept=f"v{vid}", phi=phi, i_val=delta))
        offset += 80

    # Edges (32B each, v1.0: only binary)
    edges = []
    for i in range(num_e):
        src, dst = struct.unpack_from("<ii", data, offset)
        weight, delta_weight = struct.unpack_from("<dd", data, offset + 8)
        assoc_flag, _pad = struct.unpack_from("<ii", data, offset + 24)
        edges.append(HypEdge(
            nodes=(src, dst),
            eid=f"e_{i}",
            i_val=abs(weight),
            asym=float(assoc_flag),
            weight=weight,
            delta_weight=delta_weight,
            source=src,
            target=dst,
        ))
        offset += 32

    return vertices, edges, metadata


# ============ v1 → v2 转换 ============

def convert_v1_to_v2(
    v1_path: str,
    v2_path: str,
    concepts_json_path: str = None,
    has_phi_per_edge: bool = False,
) -> Dict:
    """
    将 EML v1.0 (.eml + .concepts.json) 升级为 EML v2.0。

    Args:
        v1_path: 输入 v1.0 .eml 文件路径
        v2_path: 输出 v2.0 .eml 文件路径
        concepts_json_path: .concepts.json 路径 (可选)
        has_phi_per_edge: 是否为每条边附加 φ 场

    Returns:
        {"vertices": N, "edges": M, "file_size_v1": bytes, "file_size_v2": bytes}
    """
    # 加载 v1.0
    vertices, edges, meta = load_eml_v2(v1_path)

    # 如果有概念名称文件，更新顶点 concept
    if concepts_json_path and Path(concepts_json_path).exists():
        with open(concepts_json_path, "r", encoding="utf-8") as f:
            cdata = json.load(f)
        concept_map = {}
        for c in cdata.get("concepts", []):
            concept_map[c.get("id", -1)] = c.get("concept", "")
        for v in vertices:
            if v.vid in concept_map:
                v.concept = concept_map[v.vid]

    # 写入 v2.0
    save_eml_v2(
        v2_path,
        vertices,
        edges,
        laplacian_alpha=meta.get("laplacian_alpha", 0.0),
        graph_delta=meta.get("graph_delta", 0.0),
        has_phi_per_edge=has_phi_per_edge,
    )

    # 统计
    v1_size = Path(v1_path).stat().st_size
    v2_size = Path(v2_path).stat().st_size

    return {
        "vertices": len(vertices),
        "edges": len(edges),
        "file_size_v1": v1_size,
        "file_size_v2": v2_size,
        "size_ratio": round(v2_size / v1_size, 2),
    }


# ============ 便捷函数 ============

def build_nary_edge(
    nodes: List[int],
    eid: str,
    i_val: float = 1.0,
    asym: float = 0.0,
    weight: float = 1.0,
) -> HypEdge:
    """
    构建 n 元超边 (便捷工厂函数)。

    Example:
        edge = build_nary_edge([1, 2, 3, 4], "e_quad", i_val=0.8)
        # arity=4 的四元超边

    Args:
        nodes: 节点 ID 列表
        eid: 超边标识符
        i_val: ℐ 信息存在度
        asym: 非结合标记
        weight: 关联权重

    Returns:
        HypEdge 对象
    """
    return HypEdge(
        nodes=tuple(nodes),
        eid=eid,
        i_val=i_val,
        asym=asym,
        weight=weight,
        source=nodes[0] if nodes else None,
        target=nodes[-1] if len(nodes) > 1 else None,
    )
