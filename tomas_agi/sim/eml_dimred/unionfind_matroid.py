"""
Union-Find 拟阵回路检测引擎
=============================

基于并查集 (Union-Find / Disjoint Set Union) 实现高效回路检测，
支持高阶超图 (arity > 2) 的 MUS-Circuit 与 Paradox-Circuit 分型。

复杂度:
  - 回路检测: O(|E| · α(|V|)) — 近乎线性 (α 为反阿克曼函数)
  - 原实现: O(|E|²) — 平方级

算法基础:
  1. 路径压缩 (path compression): find(x) 时平展树
  2. 按秩合并 (union by rank): 小树挂大树
  3. 超图扩展: 对 n 元边，Union-Find 检测连通分量 → 回路判定

回路分型 (TOMAS 核心特色):
  - MUS-Circuit: 存在 e_a, e_b 标记 Asym≠0，允许互斥双存 (阴平阳秘)
  - Paradox-Circuit: 所有 Asym≡0，须 XOR 消解或死零拒绝
"""

from typing import List, Tuple, Set, Dict, Optional
from collections import defaultdict
import heapq

from eml_dimred.hyperedge import HypEdge, EMLVertex


# ============ Union-Find 数据结构 ============

class UnionFind:
    """
    并查集 — 路径压缩 + 按秩合并

    复杂度: find ≈ O(α(N)), union ≈ O(α(N))
    """

    def __init__(self, n: int = 0):
        self.parent: List[int] = list(range(n))
        self.rank: List[int] = [0] * n
        self.size: List[int] = [1] * n  # 连通分量大小

    def find(self, x: int) -> int:
        """查找根节点 (路径压缩)"""
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]  # 路径减半
            x = self.parent[x]
        return x

    def union(self, x: int, y: int) -> bool:
        """
        合并两个集合 (按秩合并)

        Returns:
            True: 合并成功 (原本不同集合)
            False: 已在同一集合 (形成回路!)
        """
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return False  # 回路!

        # 按秩合并: 小树挂大树
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx

        self.parent[ry] = rx
        self.size[rx] += self.size[ry]
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1
        return True

    def connected(self, x: int, y: int) -> bool:
        """是否在同一连通分量"""
        return self.find(x) == self.find(y)

    def component_size(self, x: int) -> int:
        """x 所在连通分量的大小"""
        return self.size[self.find(x)]

    def components(self) -> Dict[int, List[int]]:
        """获取所有连通分量"""
        groups = defaultdict(list)
        for i in range(len(self.parent)):
            groups[self.find(i)].append(i)
        return dict(groups)

    def add_node(self) -> int:
        """动态添加新节点"""
        idx = len(self.parent)
        self.parent.append(idx)
        self.rank.append(0)
        self.size.append(1)
        return idx

    def ensure_capacity(self, n: int):
        """确保容量至少为 n"""
        while len(self.parent) < n:
            self.parent.append(len(self.parent))
            self.rank.append(0)
            self.size.append(1)


# ============ 高阶超图回路检测器 ============

class HyperCircuitDetector:
    """
    高阶超图回路检测器

    利用 Union-Find 检测超边集合中的回路，支持:
      - n 元超边 (arity >= 2)
      - MUS-Circuit 分型(允许 Asym≠0 互斥双存)
      - Paradox-Circuit 分型 (须 XOR 消解)

    回路判定逻辑:
      对于超边 e = (v1, v2, ..., vn):
        1. 令 reference = v1 (任意选定参考节点)
        2. 对所有 vi (i > 1): 检查 find(vi) == find(reference)
           - 若存在已连通 → 可能形成回路
        3. 若所有 vi 均与 reference 不连通 → 不做任何 union
        4. 若部分 vi 与 reference 连通:
           - MUS 边 (Asym≠0): 允许 (阴阳双存)，将新节点 union 到 reference
           - Boolean 边 (Asym=0): 所有已有节点都被覆盖 → 回路!

    定理: 对于 MUS 边，不允许所有节点都在同一连通分量，
          但允许部分节点在分量内 (即"重叠"而非"短路")
    """

    def __init__(self):
        self.uf = UnionFind()
        self._vid_to_idx: Dict[int, int] = {}  # 真实 vid → UnionFind 索引

    def _ensure_vid(self, vid: int) -> int:
        """确保 vid 在 UnionFind 中有对应索引"""
        if vid not in self._vid_to_idx:
            idx = self.uf.add_node()
            self._vid_to_idx[vid] = idx
        return self._vid_to_idx[vid]

    def test_edge(
        self, edge: HypEdge, current_edges: List[HypEdge]
    ) -> Tuple[bool, Optional[str]]:
        """
        测试加入 edge 是否形成回路。

        Args:
            edge: 待测试超边
            current_edges: 已选中的超边集合

        Returns:
            (is_circuit, circuit_type)
            - (False, None): 不形成回路
            - (True, "mus"): MUS-Circuit
            - (True, "paradox"): Paradox-Circuit
        """
        nodes = list(edge.nodes)
        if len(nodes) < 2:
            return False, None

        # 确保所有节点在 UF 中
        for n in nodes:
            self._ensure_vid(n)

        ref = nodes[0]
        ref_idx = self._vid_to_idx[ref]

        # 检查已有连通性
        all_connected = True
        new_count = 0

        for n in nodes[1:]:
            n_idx = self._vid_to_idx[n]
            if not self.uf.connected(ref_idx, n_idx):
                all_connected = False
                new_count += 1

        # 判定
        if edge.is_mus_capable:
            # MUS 边: 所有节点已在同一分量且没有新节点 → 回路
            if all_connected and new_count == 0:
                return True, "mus"
            return False, None
        else:
            # Boolean 边: 所有节点已连通 → 回路
            if all_connected:
                return True, "paradox"
            return False, None

    def apply_edge(self, edge: HypEdge):
        """
        将 edge 应用到 UnionFind (合并节点)。

        对 MUS 边: 将所有节点 union 到 reference
        对 Boolean 边: 同上
        """
        nodes = list(edge.nodes)
        if len(nodes) < 2:
            return

        for n in nodes:
            self._ensure_vid(n)

        ref = nodes[0]
        ref_idx = self._vid_to_idx[ref]

        for n in nodes[1:]:
            n_idx = self._vid_to_idx[n]
            self.uf.union(ref_idx, n_idx)

    def detect_circuits(
        self, edges: List[HypEdge], dead_threshold: float = 0.15
    ) -> Dict[str, List[List[HypEdge]]]:
        """
        检测所有回路 (贪心 + Union-Find)

        算法:
          1. 按 ℐ(e) 降序排列
          2. 过滤死零边 (ℐ < dead_threshold)
          3. 贪心: Union-Find 检测 → 分类回路

        Returns:
            {"mus_circuits": [[HypEdge, ...]], "paradox_circuits": [[HypEdge, ...]]}
        """
        # 过滤 + 排序
        alive = [e for e in edges if e.is_alive(dead_threshold)]
        alive.sort(key=lambda e: e.i_val, reverse=True)

        mus_circuits = []
        paradox_circuits = []
        applied = []

        for e in alive:
            is_circuit, ctype = self.test_edge(e, applied)
            if is_circuit:
                if ctype == "mus":
                    mus_circuits.append([e])
                else:
                    paradox_circuits.append([e])
            else:
                self.apply_edge(e)
                applied.append(e)

        return {
            "mus_circuits": mus_circuits,
            "paradox_circuits": paradox_circuits,
        }

    def reset(self):
        """重置 UnionFind 状态"""
        self.uf = UnionFind()
        self._vid_to_idx.clear()


# ============ 集成到 Matroid 流程 ============

def matroid_prune_unionfind(
    edges: List[HypEdge],
    vertices: List[EMLVertex] = None,
    dead_threshold: float = 0.15,
    verbose: bool = False,
) -> Tuple[List[HypEdge], Dict]:
    """
    拟阵贪心剪枝 — Union-Find 优化版

    使用 HyperCircuitDetector (Union-Find) 替代原 O(|E|²) 回路检测。
    算法复杂度: O(|E| · α(|V|)) ≈ O(|E|)

    Args:
        edges: 输入超边列表
        vertices: 顶点列表 (可选)
        dead_threshold: 死零阈值
        verbose: 是否输出调试信息

    Returns:
        (pruned_edges, stats) — 剪枝后的超边集合 + 统计信息
    """
    detector = HyperCircuitDetector()

    # 过滤死零边 + 排序
    alive = [e for e in edges if e.is_alive(dead_threshold)]
    alive.sort(key=lambda e: e.i_val, reverse=True)

    # 贪心选择
    base: List[HypEdge] = []
    mus_circuits = []
    paradox_circuits = []

    for e in alive:
        is_circuit, ctype = detector.test_edge(e, base)
        if is_circuit:
            if ctype == "mus":
                mus_circuits.append(e)
            else:
                paradox_circuits.append(e)
        else:
            detector.apply_edge(e)
            base.append(e)

    # 统计
    total_i = sum(e.i_val for e in base)
    total_i_original = sum(e.i_val for e in alive)

    stats = {
        "original_count": len(edges),
        "alive_count": len(alive),
        "pruned_count": len(base),
        "removed_count": len(edges) - len(base),
        "compression_ratio": round(len(base) / max(len(edges), 1), 4),
        "total_i_before": round(total_i_original, 4),
        "total_i_after": round(total_i, 4),
        "i_retention": round(total_i / max(total_i_original, 1e-9), 4),
        "mus_circuits": len(mus_circuits),
        "paradox_circuits": len(paradox_circuits),
        "algorithm": "unionfind",
        "complexity": "O(|E|·α(|V|))",
    }

    if verbose:
        print(
            f"[UnionFind拟阵剪枝] {len(edges)}→{len(base)} "
            f"(压缩 {stats['compression_ratio']:.1%}, "
            f"ℐ保留 {stats['i_retention']:.1%}, "
            f"MUS:{stats['mus_circuits']}, 悖论:{stats['paradox_circuits']})"
        )

    return base, stats


# ============ 兼容包装 (与现有 matroid.py 接口对齐) ============

def detect_circuits_in_edges(
    edges: List[HypEdge], dead_threshold: float = 0.15
) -> Dict[str, List[List[HypEdge]]]:
    """
    便捷函数: 检测超边集合中的所有回路。

    Args:
        edges: 超边列表
        dead_threshold: 死零阈值

    Returns:
        {"mus_circuits": [...], "paradox_circuits": [...]}
    """
    detector = HyperCircuitDetector()
    return detector.detect_circuits(edges, dead_threshold)
