"""
EML 谱图 Laplacian Python 实现
用于 TOMAS-AGI 仿真器 —— M1 里程碑 Phase 2
"""

import numpy as np
from typing import List, Tuple, Dict, Optional
import networkx as nx


# ============================================================
# 核心数据结构
# ============================================================

class EMLNode:
    """EML 谱图节点"""
    def __init__(self, node_id: int, features: List[float]):
        self.id = node_id
        self.features = np.array(features, dtype=np.float64)
        self.dim = len(features)
    
    def __repr__(self) -> str:
        return f"EMLNode(id={self.id}, dim={self.dim})"


class EMLEdge:
    """EML 谱图边（含谱权重）"""
    def __init__(self, edge_id: int, src: int, dst: int, weight: float = 1.0):
        self.id = edge_id
        self.src = src          # 源节点 ID
        self.dst = dst          # 目标节点 ID
        self.weight = weight    # 谱权重（映射到忆阻器电导）
    
    def __repr__(self) -> str:
        return f"EMLEdge(id={self.id}, {self.src}->{self.dst}, w={self.weight:.4f})"


class EMLGraph:
    """
    EML 谱图（非结合谱图代数 NASGA 的核心数据结构）
    
    边权重表示谱相互作用强度，可映射到忆阻器电导。
    Laplacian 矩阵捕获谱图的拓扑性质。
    """
    
    def __init__(self, name: str = "EMLGraph"):
        self.name = name
        self.nodes: Dict[int, EMLNode] = {}
        self.edges: Dict[int, EMLEdge] = {}
        self.adj_list: Dict[int, List[int]] = {}   # 邻接表（节点ID → 邻居ID列表）
        self.next_node_id = 0
        self.next_edge_id = 0
    
    # ------------------------------------------------------------
    # 图构建 API
    # ------------------------------------------------------------
    
    def add_node(self, features: List[float]) -> int:
        """添加节点，返回节点 ID"""
        nid = self.next_node_id
        self.nodes[nid] = EMLNode(nid, features)
        self.adj_list[nid] = []
        self.next_node_id += 1
        return nid
    
    def add_edge(self, src: int, dst: int, weight: float = 1.0) -> int:
        """添加有向边，返回边 ID"""
        if src not in self.nodes:
            raise ValueError(f"源节点 {src} 不存在")
        if dst not in self.nodes:
            raise ValueError(f"目标节点 {dst} 不存在")
        
        eid = self.next_edge_id
        self.edges[eid] = EMLEdge(eid, src, dst, weight)
        self.adj_list[src].append(dst)
        self.next_edge_id += 1
        return eid
    
    def add_undirected_edge(self, u: int, v: int, weight: float = 1.0) -> int:
        """添加无向边（两条有向边）"""
        eid1 = self.add_edge(u, v, weight)
        eid2 = self.add_edge(v, u, weight)
        return eid1  # 返回其中一条的 ID
    
    def set_edge_weight(self, edge_id: int, weight: float):
        """设置边权重"""
        if edge_id not in self.edges:
            raise ValueError(f"边 {edge_id} 不存在")
        self.edges[edge_id].weight = weight
    
    @property
    def num_nodes(self) -> int:
        return len(self.nodes)
    
    @property
    def num_edges(self) -> int:
        return len(self.edges)
    
    # ------------------------------------------------------------
    # Laplacian 计算
    # ------------------------------------------------------------
    
    def get_adjacency_matrix(self) -> np.ndarray:
        """
        构建邻接矩阵 A（num_nodes x num_nodes）
        A[i][j] = 边 (i->j) 的权重（若无边则为 0）
        """
        n = self.num_nodes
        A = np.zeros((n, n), dtype=np.float64)
        for eid, edge in self.edges.items():
            A[edge.src][edge.dst] = edge.weight
        return A
    
    def get_degree_matrix(self) -> np.ndarray:
        """
        构建度矩阵 D（对角矩阵）
        D[i][i] = 所有从 i 出发的边的权重之和（出度）
        """
        n = self.num_nodes
        D = np.zeros((n, n), dtype=np.float64)
        for eid, edge in self.edges.items():
            D[edge.src][edge.src] += edge.weight
        return D
    
    def calc_laplacian(self, normalized: bool = False) -> np.ndarray:
        """
        计算 Laplacian 矩阵 L = D - A
        
        参数：
            normalized: 是否计算归一化 Laplacian（L_sym = D^(-1/2) L D^(-1/2)）
        
        返回：
            L: np.ndarray，形状 (num_nodes, num_nodes)
        """
        A = self.get_adjacency_matrix()
        D = self.get_degree_matrix()
        L = D - A
        
        if normalized:
            # 归一化 Laplacian：L_sym = D^(-1/2) (D - A) D^(-1/2)
            d = np.diag(D)
            d_sqrt_inv = np.zeros_like(d)
            mask = d > 1e-15
            d_sqrt_inv[mask] = 1.0 / np.sqrt(d[mask])
            D_sqrt_inv = np.diag(d_sqrt_inv)
            L = D_sqrt_inv @ L @ D_sqrt_inv
        
        return L
    
    def calc_laplacian_spectrum(self, k: Optional[int] = None) -> Tuple[np.ndarray, np.ndarray]:
        """
        计算 Laplacian 的特征值和特征向量
        
        参数：
            k: 计算前 k 个最小特征值（默认为全部）
        
        返回：
            eigenvalues: np.ndarray，升序排列
            eigenvectors: np.ndarray，每列是一个特征向量
        """
        L = self.calc_laplacian()
        eigenvalues, eigenvectors = np.linalg.eig(L)
        
        # 按特征值升序排列
        idx = np.argsort(eigenvalues.real)
        eigenvalues = eigenvalues[idx]
        eigenvectors = eigenvectors[:, idx]
        
        if k is not None and k < len(eigenvalues):
            return eigenvalues[:k], eigenvectors[:, :k]
        
        return eigenvalues, eigenvectors
    
    # ------------------------------------------------------------
    # 与 NetworkX 对比验证
    # ------------------------------------------------------------
    
    def to_networkx(self) -> nx.DiGraph:
        """转换为 NetworkX 有向图（用于验证）"""
        G = nx.DiGraph()
        for nid, node in self.nodes.items():
            G.add_node(nid, features=node.features)
        for eid, edge in self.edges.items():
            G.add_edge(edge.src, edge.dst, weight=edge.weight)
        return G
    
    def verify_laplacian(self, tol: float = 1e-6) -> Dict:
        """
        使用 NetworkX 验证 Laplacian 计算的正确性
        
        返回：
            {'match': bool, 'max_error': float, 'details': ...}
        """
        L_ours = self.calc_laplacian()
        
        # 使用 NetworkX 计算 Laplacian
        G = self.to_networkx()
        # NetworkX 的有向图 Laplacian 需要自己计算
        A_nx = nx.adjacency_matrix(G, weight='weight').toarray()
        in_degree = A_nx.sum(axis=0)  # 入度
        out_degree = A_nx.sum(axis=1)  # 出度
        D_in = np.diag(in_degree)
        D_out = np.diag(out_degree)
        
        # 对于有向图，通常使用出度 Laplacian：L = D_out - A
        L_nx = D_out - A_nx
        
        error = np.abs(L_ours - L_nx)
        max_error = np.max(error)
        match = max_error < tol
        
        return {
            'match': match,
            'max_error': max_error,
            'L_ours': L_ours,
            'L_nx': L_nx,
            'error_matrix': error,
        }
    
    # ------------------------------------------------------------
    # 可视化辅助
    # ------------------------------------------------------------
    
    def summary(self) -> str:
        """返回图的摘要信息"""
        L = self.calc_laplacian()
        eigenvalues, _ = self.calc_laplacian_spectrum()
        
        return (
            f"EMLGraph '{self.name}'\n"
            f"  节点数：{self.num_nodes}\n"
            f"  边数：{self.num_edges}\n"
            f"  Laplacian 形状：{L.shape}\n"
            f"  最小特征值：{eigenvalues[0]:.6f}\n"
            f"  特征值（前5个）：{eigenvalues[:5]}"
        )


# ============================================================
# 测试套件
# ============================================================

def test_laplacian_triangle():
    """
    测试1：三角形图（3个节点，3条有向边）
    手动计算 Laplacian，与代码结果对比
    """
    print("[测试1] 三角形图 Laplacian...")
    
    g = EMLGraph("triangle")
    # 添加 3 个节点
    n0 = g.add_node([1.0, 0.0])
    n1 = g.add_node([0.0, 1.0])
    n2 = g.add_node([1.0, 1.0])
    
    # 添加有向边：0->1, 1->2, 2->0，权重均为 1.0
    g.add_edge(n0, n1, 1.0)
    g.add_edge(n1, n2, 1.0)
    g.add_edge(n2, n0, 1.0)
    
    L = g.calc_laplacian()
    
    # 手动计算：
    # A = [[0, 1, 0], [0, 0, 1], [1, 0, 0]]
    # D = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    # L = D - A = [[1, -1, 0], [0, 1, -1], [-1, 0, 1]]
    expected = np.array([
        [1.0, -1.0, 0.0],
        [0.0, 1.0, -1.0],
        [-1.0, 0.0, 1.0],
    ], dtype=np.float64)
    
    error = np.max(np.abs(L - expected))
    match = error < 1e-10
    
    print(f"  计算结果：\n{L}")
    print(f"  期望结果：\n{expected}")
    print(f"  最大误差：{error:.2e}")
    if match:
        print("  [PASS] Laplacian 计算正确")
    else:
        print("  [FAIL] Laplacian 计算错误")
    
    return match


def test_laplacian_verify_networkx():
    """
    测试2：使用 NetworkX 验证 Laplacian 计算
    """
    print("\n[测试2] NetworkX 交叉验证...")
    
    # 创建一个随机图
    np.random.seed(42)
    g = EMLGraph("random_5")
    for i in range(5):
        g.add_node(np.random.randn(3))
    
    # 添加随机边
    for _ in range(8):
        src = np.random.randint(0, 5)
        dst = np.random.randint(0, 5)
        if src != dst:
            weight = np.random.rand()
            g.add_edge(src, dst, weight)
    
    result = g.verify_laplacian(tol=1e-6)
    
    print(f"  最大误差：{result['max_error']:.2e}")
    if result['match']:
        print("  [PASS] 与 NetworkX 结果一致")
    else:
        print("  [FAIL] 与 NetworkX 结果不一致")
        print(f"  误差矩阵：\n{result['error_matrix']}")
    
    return result['match']


def test_laplacian_spectrum():
    """
    测试3：Laplacian 谱计算（特征值应为非负实数）
    """
    print("\n[测试3] Laplacian 谱计算...")
    
    # 创建一个路径图：0-1-2-3（无向）
    g = EMLGraph("path_4")
    for i in range(4):
        g.add_node([float(i)])
    
    g.add_undirected_edge(0, 1, 1.0)
    g.add_undirected_edge(1, 2, 1.0)
    g.add_undirected_edge(2, 3, 1.0)
    
    eigenvalues, eigenvectors = g.calc_laplacian_spectrum()
    
    print(f"  特征值：{eigenvalues}")
    
    # 检查特征值是否非负（Laplacian 半正定）
    non_negative = np.all(eigenvalues >= -1e-10)
    
    # 检查第一个特征值是否接近 0（连通图的 Laplacian 有 0 特征值）
    lambda0_near_zero = abs(eigenvalues[0]) < 1e-6
    
    if non_negative:
        print("  [PASS] 特征值非负（半正定）")
    else:
        print("  [FAIL] 存在负特征值")
    
    if lambda0_near_zero:
        print("  [PASS] 最小特征值为 0（连通图）")
    else:
        print("  [WARN] 最小特征值不为 0")
    
    return non_negative and lambda0_near_zero


def test_eml_graph_build():
    """
    测试4：EML 谱图构建 API
    """
    print("\n[测试4] EML 谱图构建 API...")
    
    g = EMLGraph("test_build")
    
    # 添加节点
    n0 = g.add_node([1.0])
    n1 = g.add_node([2.0])
    n2 = g.add_node([3.0])
    
    assert n0 == 0
    assert n1 == 1
    assert n2 == 2
    assert g.num_nodes == 3
    
    # 添加边
    e0 = g.add_edge(n0, n1, 0.5)
    e1 = g.add_edge(n1, n2, 0.8)
    
    assert g.num_edges == 2
    assert g.edges[e0].weight == 0.5
    assert g.edges[e1].weight == 0.8
    
    # 修改边权重
    g.set_edge_weight(e0, 0.7)
    assert g.edges[e0].weight == 0.7
    
    print("  [PASS] 构建 API 正确")
    return True


if __name__ == '__main__':
    print("=" * 60)
    print("EML 谱图 Laplacian Python 实现 —— 测试套件")
    print("=" * 60)
    
    results = []
    
    results.append(("三角形 Laplacian", test_laplacian_triangle()))
    results.append(("NetworkX 验证", test_laplacian_verify_networkx()))
    results.append(("Laplacian 谱", test_laplacian_spectrum()))
    results.append(("构建 API", test_eml_graph_build()))
    
    print("\n" + "=" * 60)
    print("测试汇总：")
    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {name}")
    
    n_pass = sum(1 for _, p in results if p)
    n_total = len(results)
    print(f"\n总计：{n_pass}/{n_total} 通过")
    print("=" * 60)
