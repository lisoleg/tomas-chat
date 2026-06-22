"""
Token Bridge — TOMAS/太极OS 推理引擎
=====================================

混合架构："翻译官 + 作家" 模式
  - Token Bridge (翻译官): LSTM/模板处理事实性查询，EML 图检索 → 精确回答
  - Creative Engine (作家):  DeepSeek LLM 处理开放性/创造性查询
  - PhiGate (监管者):        φ-一致性检查，防止 LLM 幻觉，必要时回退

完整管线：
  输入文本 → φ编码 → EML概念匹配 → 置信度判断
    ├─ 高置信度(≥0.5): Token Bridge 翻译官（模板/LSTM 事实复述）
    └─ 低置信度(<0.5):  Creative Engine 作家（DeepSeek LLM 创造性生成）
                        └─ φ-Gate 监管 → 通过/标记警告/回退

核心组件：
  1. EMLFileLoader     — 加载 .eml 二进制文件并重建内存中的 EML 图
  2. TokenBridge       — 编码器/解码器（可训练，目标 < 100MB）
  3. InferenceEngine   — 端到端推理 + 翻译官/作家自动路由
  4. CreativeEngine    — DeepSeek LLM API 封装（创造性生成）
  5. PhiGate           — φ-一致性监管器（幻觉检测与回退）

作者：复合体理学研究中心（TOMAS 项目组）
日期：2026-06-13
"""

import os
import struct
import hashlib
import time
import json
import re
import requests
import numpy as np
from typing import List, Dict, Tuple, Optional, Any
from collections import deque

# TOMAS-MemOS 融合层集成
try:
    from .memos_integration import enable_memos_for_engine, get_memos_stats
    _HAS_MEMOS = True
except ImportError:
    _HAS_MEMOS = False
    _HAS_MEMOS_REASON = "memos_integration 模块不可用"

# ============================================================
# 第1部分：EML 文件加载器
# ============================================================

class EMLFileLoader:
    """加载 .eml 二进制文件并重建内存中的 EML 图"""

    # 二进制格式常量
    HEADER_SIZE = 72   # IIII + dd + Q + QQQQ
    VERTEX_SIZE = 80   # ii + 8d + d
    EDGE_SIZE = 32     # ii + d + d + ii
    MAGIC = 0x454D4C47
    VERSION = 0x00020000

    def __init__(self):
        self.vertices: List[Dict] = []   # {id, concept, octonion[8], delta, info_existence}
        self.edges: List[Dict] = []      # {src, dst, weight, delta_weight, assoc_flag}
        self.laplacian_alpha: float = 0.0
        self.graph_delta: float = 0.0
        self.timestamp: int = 0
        self._adjacency: Dict[int, List[int]] = {}  # vertex_id -> [edge_indices]
        self._concept_map: Dict[str, int] = {}      # concept_text -> vertex_id

    def load_file(self, filepath: str):
        """从文件路径加载 EML 二进制"""
        with open(filepath, 'rb') as f:
            data = f.read()
        self._parse(data)
        print(f"[EMLFileLoader] 已加载: {filepath}")
        print(f"  顶点数={len(self.vertices)}, 边数={len(self.edges)}")

    def load_bytes(self, data: bytes):
        """从内存中的 bytes 加载（供前端上传使用）"""
        self._parse(data)

    def _parse(self, data: bytes):
        """解析 EML 二进制格式"""
        if len(data) < self.HEADER_SIZE:
            raise ValueError(f"EML 文件过小：{len(data)} < {self.HEADER_SIZE}")

        # ---- Header ----
        magic, version, num_v, num_e = struct.unpack_from('<IIII', data, 0)
        if magic != self.MAGIC:
            raise ValueError(f"无效 EML 魔数：0x{magic:08X}（预期 0x{self.MAGIC:08X}）")
        if version != self.VERSION:
            print(f"⚠️ EML 版本不匹配：0x{version:08X}（预期 0x{self.VERSION:08X}），尝试兼容解析")

        self.laplacian_alpha, self.graph_delta = struct.unpack_from('<dd', data, 16)
        self.timestamp = struct.unpack_from('<Q', data, 32)[0]

        # 验证文件大小
        expected = self.HEADER_SIZE + num_v * self.VERTEX_SIZE + num_e * self.EDGE_SIZE
        if len(data) < expected:
            raise ValueError(f"EML 文件不完整：{len(data)} < {expected}")

        # ---- Vertices ----
        self.vertices = []
        self._concept_map = {}
        for i in range(num_v):
            off = self.HEADER_SIZE + i * self.VERTEX_SIZE
            vid, _pad = struct.unpack_from('<ii', data, off)
            octonion = list(struct.unpack_from('<8d', data, off + 8))
            delta = struct.unpack_from('<d', data, off + 72)[0]
            vertex = {
                'id': vid,
                'concept': f'concept_{vid}',  # 占位，EML 不存储文本
                'octonion': octonion,
                'delta': delta,
                'info_existence': delta  # δ = 𝕀(X)
            }
            self.vertices.append(vertex)
            self._concept_map[f'concept_{vid}'] = vid

        # ---- Edges ----
        self.edges = []
        self._adjacency = {i: [] for i in range(num_v)}
        for i in range(num_e):
            off = self.HEADER_SIZE + num_v * self.VERTEX_SIZE + i * self.EDGE_SIZE
            src, dst = struct.unpack_from('<ii', data, off)
            weight, delta_weight = struct.unpack_from('<dd', data, off + 8)
            assoc_flag, _pad = struct.unpack_from('<ii', data, off + 24)
            edge = {
                'src': src,
                'dst': dst,
                'weight': weight,
                'delta_weight': delta_weight,
                'assoc_flag': assoc_flag
            }
            self.edges.append(edge)
            # 建立邻接表
            if src in self._adjacency:
                self._adjacency[src].append(i)
            # 也建立反向邻接（无向遍历）
            if dst in self._adjacency:
                self._adjacency[dst].append(i)

    def load_concept_names(self, concept_names: Dict[int, str]):
        """从外部加载概念名称映射（EML 二进制不存储文本，需要从蒸馏 JSON 恢复）"""
        for vertex in self.vertices:
            vid = vertex['id']
            if vid in concept_names:
                vertex['concept'] = concept_names[vid]
                self._concept_map[concept_names[vid]] = vid

    def load_concept_names_from_json(self, json_path: str):
        """从蒸馏结果的 JSON 文件加载概念名称"""
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        concept_names = {}
        for i, c in enumerate(data.get('concepts', [])):
            concept_names[i] = c['concept']
        self.load_concept_names(concept_names)

    def get_adjacency(self) -> Dict[int, List[int]]:
        """获取邻接表"""
        return self._adjacency

    def get_vertex_by_concept(self, concept: str) -> Optional[Dict]:
        """按概念名查找顶点"""
        vid = self._concept_map.get(concept)
        if vid is not None:
            return self.vertices[vid]
        return None

    def search_concept(self, query: str) -> List[Dict]:
        """模糊搜索概念名"""
        results = []
        query_lower = query.lower()
        for v in self.vertices:
            if query_lower in v['concept'].lower():
                results.append(v)
        return results


# ============================================================
# 第2部分：Token Bridge 核心
# ============================================================

def text_to_octonion(text: str, dimension: int = 8) -> np.ndarray:
    """将文本映射到八元数空间 φ(i) ∈ ℝ⁸"""
    h = hashlib.sha256(text.encode('utf-8')).digest()
    phi = np.zeros(dimension, dtype=np.float64)
    for i in range(dimension):
        chunk = h[(i * 4) % 32 : ((i + 1) * 4) % 32]
        if len(chunk) < 4:
            chunk = h[:4]
        val = int.from_bytes(chunk, byteorder='little') / (2**32)
        phi[i] = (val - 0.5) * 2
    phi[0] = len(text) / 100.0
    phi[1] = text.count(' ') / max(len(text), 1)
    return phi


# ============================================================
# 对话意图检测（路由前置过滤器）
# ============================================================

_CONVERSATIONAL_PATTERNS = [
    re.compile(r'^(你是谁|你是谁呀|你叫什么|你叫什么名字|介绍一下[你自]己|你是什[么么])', re.IGNORECASE),
    re.compile(r'^(你好|您好|嗨|哈喽|早[上好]|晚[上好])', re.IGNORECASE),
    re.compile(r'^(谢谢|感谢|不客气|再见|拜拜|对不起|抱歉|好的?|嗯|哦)', re.IGNORECASE),
    re.compile(r'(你觉[得认为]|你怎[么样么]看|你(的)?看法|你喜[欢不喜欢])', re.IGNORECASE),
    re.compile(r'^(你能做什|你会什|帮帮我|怎么用|如何使用)', re.IGNORECASE),
]


def is_conversational_query(text: str) -> bool:
    """检测查询是否为对话/闲聊型 → 应强制走作家路径"""
    trimmed = text.strip()
    if len(trimmed) <= 4:
        return True
    return any(p.search(trimmed) for p in _CONVERSATIONAL_PATTERNS)


class TokenBridge:
    """
    Token Bridge：将 EML 图作为推理核心，替代 LLM

    编码器：embedding(ℝ^d) → φ(ℝ^8)
    解码器：φ(ℝ^8) → embedding(ℝ^d) → token

    可训练模式：用概念-嵌入对训练 encoder/decoder 权重（目标 < 100MB）
    回退模式：未训练时用 φ 空间最近邻查找
    """

    def __init__(self, embedding_dim: int = 768, eight_dim: int = 8):
        self.embedding_dim = embedding_dim
        self.eight_dim = eight_dim
        self.loader = EMLFileLoader()
        self.trained = False

        # 编码器/解码器权重（训练后才有意义）
        self.encoder_weights: Optional[np.ndarray] = None  # (embedding_dim, 8)
        self.decoder_weights: Optional[np.ndarray] = None  # (8, embedding_dim)

        # 概念嵌入缓存
        self.concept_embeddings: Dict[int, np.ndarray] = {}

        # φ 空间矩阵（用于快速最近邻搜索）
        self._phi_matrix: Optional[np.ndarray] = None
        self._phi_norms: Optional[np.ndarray] = None

    def load_eml(self, filepath_or_bytes):
        """加载 EML 图文件"""
        if isinstance(filepath_or_bytes, str):
            self.loader.load_file(filepath_or_bytes)
        else:
            self.loader.load_bytes(filepath_or_bytes)
        self._build_phi_index()

    def load_concept_names(self, concept_names: Dict[int, str]):
        """加载概念名称"""
        self.loader.load_concept_names(concept_names)
        # 重新计算有概念文本的 φ 索引
        self._build_phi_index()

    def load_concept_names_from_json(self, json_path: str):
        """从蒸馏结果的 JSON 文件加载概念名称"""
        self.loader.load_concept_names_from_json(json_path)
        self._build_phi_index()

    def _build_phi_index(self):
        """构建 φ 空间索引矩阵"""
        n = len(self.loader.vertices)
        if n == 0:
            return
        self._phi_matrix = np.zeros((n, self.eight_dim))
        for i, v in enumerate(self.loader.vertices):
            self._phi_matrix[i] = v['octonion']
        # 预计算 L2 范数（用于余弦相似度）
        self._phi_norms = np.linalg.norm(self._phi_matrix, axis=1, keepdims=True)
        self._phi_norms = np.maximum(self._phi_norms, 1e-10)  # 避免除零

    def encode(self, embedding: np.ndarray) -> np.ndarray:
        """
        编码器：embedding(ℝ^d) → φ(ℝ^8)

        训练模式：线性投影 W_enc · embedding
        回退模式：找最近概念，返回其 φ 场
        """
        if self.trained and self.encoder_weights is not None:
            return np.dot(embedding, self.encoder_weights)
        return self._encode_by_lookup(embedding)

    def _encode_by_lookup(self, embedding: np.ndarray) -> np.ndarray:
        """未训练时的回退策略：用文本 → φ 映射"""
        # 如果 embedding 是概念嵌入，找最相似的概念
        if self._phi_matrix is not None and len(self.concept_embeddings) > 0:
            best_sim = -1
            best_phi = np.zeros(self.eight_dim)
            for vid, cemb in self.concept_embeddings.items():
                sim = self._cosine_similarity(embedding, cemb)
                if sim > best_sim:
                    best_sim = sim
                    best_phi = self.loader.vertices[vid]['octonion']
            return best_phi
        # 完全没有训练数据时，返回零向量
        return np.zeros(self.eight_dim)

    def find_nearest_concepts(self, phi: np.ndarray, top_k: int = 5) -> List[Dict]:
        """在 EML 图中找 φ 空间最近的概念（余弦相似度）"""
        if self._phi_matrix is None:
            return []

        # 归一化查询向量
        phi_norm = np.linalg.norm(phi)
        if phi_norm < 1e-10:
            return []
        phi_normalized = phi / phi_norm

        # 计算与所有顶点的余弦相似度
        similarities = np.dot(self._phi_matrix / self._phi_norms, phi_normalized)

        # 取 top_k
        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        for idx in top_indices:
            v = self.loader.vertices[idx]
            results.append({
                'vertex_id': v['id'],
                'concept': v['concept'],
                'similarity': float(similarities[idx]),
                'delta': v['delta'],
                'octonion': v['octonion']
            })
        return results

    def find_nearest_by_text(self, text: str, top_k: int = 5) -> List[Dict]:
        """通过文本查询最近概念（文本 → φ → 最近邻）"""
        phi = text_to_octonion(text)
        return self.find_nearest_concepts(phi, top_k)

    def extract_subgraph(self, vertex_ids: List[int], radius: int = 2, kappa: float = 0.0) -> Dict:
        """
        从匹配概念出发，BFS 扩展子图（带 κ-Gate 语义剪枝）

        κ-Gate 剪枝机制（TOMAS 核心优化）：
        - κ = 0：不剪枝，全图 BFS（原有行为）
        - κ > 0：仅遍历 info_existence(I(X)) ≥ κ 的顶点/边
        - κ 越大，保留的信息越"核心"，子图越小

        Args:
            vertex_ids: 起始顶点 ID 列表
            radius: BFS 扩展半径
            kappa: I(X) 信息存在度阈值（κ-Gate 剪枝参数）

        Returns:
            {'vertices': [...], 'edges': [...], 'size': int, 'kappa': float,
             'pruned_vertices': int, 'pruned_edges': int}
        """
        visited = set()
        edge_indices = set()
        pruned_vertices = 0
        pruned_edges = 0

        # 初始化：仅添加 I(X) ≥ κ 的种子顶点
        for vid in vertex_ids:
            if vid >= len(self.loader.vertices):
                continue
            v = self.loader.vertices[vid]
            ix = v.get('info_existence', 1.0)
            if ix >= kappa:
                visited.add(vid)
            else:
                pruned_vertices += 1

        queue = deque([(vid, 0) for vid in visited])

        while queue:
            vid, dist = queue.popleft()
            if dist >= radius:
                continue

            v = self.loader.vertices[vid] if vid < len(self.loader.vertices) else {}
            ix_v = v.get('info_existence', 1.0)

            for eidx in self.loader.get_adjacency().get(vid, []):
                edge = self.loader.edges[eidx]

                # κ-Gate 剪枝：边权重不足则跳过
                edge_ix = edge.get('delta_weight', ix_v)
                if kappa > 0 and edge_ix < kappa:
                    pruned_edges += 1
                    continue

                neighbor = edge['dst'] if edge['src'] == vid else edge['src']
                if neighbor in visited or neighbor >= len(self.loader.vertices):
                    continue

                # κ-Gate 剪枝：邻居顶点 I(X) 不足则跳过
                nv = self.loader.vertices[neighbor]
                n_ix = nv.get('info_existence', 1.0)
                if kappa > 0 and n_ix < kappa:
                    pruned_vertices += 1
                    continue

                edge_indices.add(eidx)
                visited.add(neighbor)
                queue.append((neighbor, dist + 1))

        # 收集子图顶点和边
        sub_vertices = [self.loader.vertices[vid] for vid in visited if vid < len(self.loader.vertices)]
        sub_edges = [self.loader.edges[eidx] for eidx in edge_indices]

        return {
            'vertices': sub_vertices,
            'edges': sub_edges,
            'size': len(sub_vertices) + len(sub_edges),
            'kappa': kappa,
            'pruned_vertices': pruned_vertices,
            'pruned_edges': pruned_edges,
        }

    def decode(self, phi: np.ndarray) -> np.ndarray:
        """
        解码器：φ(ℝ^8) → embedding(ℝ^d)

        训练模式：线性投影 W_dec · φ
        回退模式：用最近概念的 embedding 加权混合
        """
        if self.trained and self.decoder_weights is not None:
            return np.dot(phi, self.decoder_weights)
        return self._decode_by_blending(phi)

    def _decode_by_blending(self, phi: np.ndarray) -> np.ndarray:
        """未训练时的回退：用最近概念的 φ 加权混合"""
        nearest = self.find_nearest_concepts(phi, top_k=3)
        if not nearest:
            return np.zeros(self.embedding_dim)

        # 用相似度作为权重混合
        total_weight = sum(n['similarity'] for n in nearest)
        if total_weight < 1e-10:
            return np.zeros(self.embedding_dim)

        result = np.zeros(self.embedding_dim)
        for n in nearest:
            weight = n['similarity'] / total_weight
            vid = n['vertex_id']
            if vid in self.concept_embeddings:
                result += weight * self.concept_embeddings[vid]
            else:
                # 没有嵌入时，用 φ 场填充前 8 维
                emb = np.zeros(self.embedding_dim)
                for d in range(min(8, self.embedding_dim)):
                    emb[d] = n['octonion'][d % 8] * weight
                result += emb

        return result

    def train(self, concept_texts: List[str], embedding_fn=None,
              epochs: int = 100, lr: float = 0.01, verbose: bool = True):
        """
        训练编码器/解码器权重

        训练策略：
        1. 从 EML 图中获取每个概念的 φ(i) 作为目标
        2. 用 embedding_fn(text) 获取文本的 embedding
        3. 用 SGD 训练 encoder: embedding → φ(i)（最小化 MSE）
        4. 用 SGD 训练 decoder: φ(i) → embedding（最小化 MSE）

        总参数量：embedding_dim × 8 × 2 × 4 bytes ≈ 768 × 8 × 2 × 4 ≈ 49KB
        """
        if self._phi_matrix is None:
            raise ValueError("请先加载 EML 图！")

        # 准备训练数据
        X_list = []  # embeddings
        Y_list = []  # phi targets

        for text in concept_texts:
            vid = self.loader._concept_map.get(text)
            if vid is None:
                continue

            # 获取目标 φ
            phi_target = self.loader.vertices[vid]['octonion']

            # 获取 embedding
            if embedding_fn is not None:
                try:
                    emb = embedding_fn(text)
                    if emb is not None:
                        X_list.append(emb)
                        Y_list.append(phi_target)
                        self.concept_embeddings[vid] = np.array(emb)
                except Exception as e:
                    if verbose:
                        print(f"  ⚠️ 获取嵌入失败 '{text}': {e}")
                    continue
            else:
                # 没有 embedding 函数时，用 φ 场作为伪嵌入
                pseudo_emb = np.zeros(self.embedding_dim)
                for d in range(min(8, self.embedding_dim)):
                    pseudo_emb[d] = phi_target[d % 8]
                X_list.append(pseudo_emb)
                Y_list.append(phi_target)
                self.concept_embeddings[vid] = pseudo_emb

        if len(X_list) < 2:
            if verbose:
                print("⚠️ 训练数据不足，使用随机初始化权重")
            np.random.seed(42)
            self.encoder_weights = np.random.randn(self.embedding_dim, self.eight_dim) * 0.01
            self.decoder_weights = np.random.randn(self.eight_dim, self.embedding_dim) * 0.01
            self.trained = True
            return

        X = np.array(X_list)  # (N, embedding_dim)
        Y = np.array(Y_list)  # (N, 8)

        # 初始化权重
        np.random.seed(42)
        self.encoder_weights = np.random.randn(self.embedding_dim, self.eight_dim) * 0.01
        self.decoder_weights = np.random.randn(self.eight_dim, self.embedding_dim) * 0.01

        # SGD 训练
        for epoch in range(epochs):
            # Encoder 前向 + 反向
            pred_Y = X @ self.encoder_weights
            error = pred_Y - Y
            grad_enc = X.T @ error / len(X)
            self.encoder_weights -= lr * grad_enc

            # Decoder 前向 + 反向
            pred_X = Y @ self.decoder_weights
            error_dec = pred_X - X
            grad_dec = Y.T @ error_dec / len(Y)
            self.decoder_weights -= lr * grad_dec

            if verbose and (epoch + 1) % 20 == 0:
                loss_enc = np.mean(error ** 2)
                loss_dec = np.mean(error_dec ** 2)
                print(f"  Epoch {epoch+1}/{epochs}: enc_loss={loss_enc:.6f}, dec_loss={loss_dec:.6f}")

        self.trained = True
        if verbose:
            print(f"✅ Token Bridge 训练完成（{len(X_list)} 个概念，{epochs} 轮）")

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """计算余弦相似度"""
        na = np.linalg.norm(a)
        nb = np.linalg.norm(b)
        if na < 1e-10 or nb < 1e-10:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    def size_estimate(self) -> Dict:
        """估算 Token Bridge 总大小"""
        sizes = {
            'encoder_weights': self.encoder_weights.nbytes if self.encoder_weights is not None else 0,
            'decoder_weights': self.decoder_weights.nbytes if self.decoder_weights is not None else 0,
            'concept_embeddings': sum(e.nbytes for e in self.concept_embeddings.values()),
            'phi_matrix': self._phi_matrix.nbytes if self._phi_matrix is not None else 0,
            'vertex_data': len(self.loader.vertices) * 120,  # 估算
            'edge_data': len(self.loader.edges) * 40,
        }
        sizes['total'] = sum(sizes.values())
        sizes['total_mb'] = sizes['total'] / (1024 * 1024)
        sizes['target_met'] = sizes['total_mb'] < 100
        return sizes


# ============================================================
# 第3部分：推理引擎
# ============================================================

class InferenceEngine:
    """
    端到端推理引擎 — "翻译官 + 作家" 混合架构
    
    翻译官 (Token Bridge): LSTM/模板处理事实性查询
    作家 (Creative Engine):   DeepSeek LLM 处理创造性查询
    监管者 (PhiGate):         φ-一致性检查，防幻觉，必要时回退
    """

    # 路由阈值：匹配置信度 >= 此值时用翻译官，否则走作家
    TRANSLATOR_THRESHOLD = 0.5
    
    # φ-一致性阈值：LLM 输出低于此值视为幻觉
    PHI_CONSISTENCY_THRESHOLD = 0.35

    def __init__(self, bridge: TokenBridge, creative_engine=None, phi_gate=None,
                 dimred_enabled: bool = False, dimred_result=None,
                 dead_zero_enabled: bool = True, theta_dead: float = 0.15,
                 mus_enabled: bool = True, k_snap_enabled: bool = True):
        self.bridge = bridge
        self.creative_engine = creative_engine  # 作家
        self.phi_gate = phi_gate                # 监管者
        self.use_neural = False
        self.neural_model = None
        # 数学降维
        self.dimred_enabled = dimred_enabled
        self.dimred_result = dimred_result      # DimredResult or None
        # TOMAS Router（多模型路由）
        self.router = None
        self._use_router = False
        self._task_type = "reason"              # 默认任务类型
        # 死零/MUS/κ-Snap 门控（TOMAS 核心 IP）
        self.dead_zero_enabled = dead_zero_enabled
        self.theta_dead = theta_dead
        self.mus_enabled = mus_enabled
        self.k_snap_enabled = k_snap_enabled
        self._dead_zero_mus_gate = None
        self._init_dead_zero_mus_gate()
        # TOMAS Orchestrator（Conductor 式多智能体编排）
        self.orchestrator = None
        self._use_orchestration = False
        self._orchestration_complexity_threshold = 2  # 查询长度 > 此值（按换行/分号计）时触发编排


    def set_neural_model(self, model, use_neural: bool = True):
        """设置神经解码器模型（启用/禁用神经生成）"""
        self.neural_model = model
        self.use_neural = use_neural

    def set_creative_engine(self, creative_engine):
        """设置创造性引擎（DeepSeek LLM）"""
        self.creative_engine = creative_engine

    def set_phi_gate(self, phi_gate):
        """设置 φ 监管器"""
        self.phi_gate = phi_gate

    def set_router(self, router):
        """设置 TOMAS 多模型路由器（替代单一 creative_engine）

        当 Router 激活时，CreativeEngine 被 Router 替代：
        - Router 支持按 task_type 分发到不同 LLM 后端
        - Router 内置 EML 执行上下文注入（κ, θ_dead, MUS Tags）
        - 保留 creative_engine 用于向后兼容
        """
        self.router = router
        self._use_router = True

    def set_orchestrator(self, orchestrator):
        """设置 TOMAS Orchestrator（Conductor 式多智能体编排器）

        当 Orchestrator 激活时，复杂查询会自动分解为子任务，
        动态调度多个专家智能体，而非只有 translator/writer 二路。

        受 Sakana AI Fugu 启发（2026-06）：
          - 自适应任务分解
          - 动态智能体选择
          - 自然语言协调指令
          - 失败自愈（自动切换备选智能体）
        """
        self.orchestrator = orchestrator
        self._use_orchestration = True
        print("[InferenceEngine] ✅ Orchestrator 编排模式已启用")

    def _init_dead_zero_mus_gate(self):
        """初始化死零/MUS/κ-Snap 统一门控器

        延迟导入以避免循环依赖。
        若 dead_zero_mus 模块不可用，禁用门控并警告。
        """
        if not self.dead_zero_enabled and not self.mus_enabled and not self.k_snap_enabled:
            self._dead_zero_mus_gate = None
            return

        try:
            from .dead_zero_mus import DeadZeroMUSGate
            self._dead_zero_mus_gate = DeadZeroMUSGate(
                theta_dead=self.theta_dead,
                mus_tags=['Asym≠0 double-exist'],
                tie_threshold=0.01,
                enable_audit=True,
            )
            if self.dead_zero_enabled:
                print(f"  ✅ 死零校验已启用（θ_dead={self.theta_dead:.2f}）")
            if self.mus_enabled:
                print(f"  ✅ MUS 仲裁已启用")
            if self.k_snap_enabled:
                print(f"  ✅ κ-Snap 决策已启用")
        except ImportError as e:
            print(f"  ⚠️ 死零/MUS 门控初始化失败：{e}")
            self._dead_zero_mus_gate = None

    def _apply_dead_zero_mus_gate(self, query: str, matched_edges: List[Dict]) -> Dict:
        """应用死零/MUS/κ-Snap 门控检查

        Args:
            query: 用户查询
            matched_edges: 匹配到的 EML 边

        Returns:
            {
                'proceed': bool,          # 是否继续生成响应
                'reject_reason': str,     # 若 reject，原因
                'mus_active': bool,       # 是否 MUS 激活
                'paradox_pairs': list,    # 悖论对
                'selected_edge': dict,    # 选中的边（若有）
                'snap_score': float,      # Snap 得分
                'audit_log': list,        # 审计日志
            }
        """
        if self._dead_zero_mus_gate is None:
            # 门控未初始化，默认通过
            return {
                'proceed': True,
                'reject_reason': '',
                'mus_active': False,
                'paradox_pairs': [],
                'selected_edge': None,
                'snap_score': 0.0,
                'audit_log': [],
            }

        return self._dead_zero_mus_gate.process(
            query=query,
            matched_edges=matched_edges,
        )

    def _extract_matched_edges(self, query_result: Dict) -> List[Dict]:
        """从查询结果中提取匹配到的边（用于死零/MUS 检查）

        简化实现：将 matched_concepts 转换为边格式。
        若子图中有边，也一并加入。

        Returns:
            List[Dict]: [{'eid', 'nodes', 'i_val', 'concept'}, ...]
        """
        edges = []

        # 从 matched_concepts 构建边
        for m in query_result.get('matched_concepts', []):
            edges.append({
                'eid': f"e_{m.get('concept', 'unknown')}",
                'nodes': [m.get('concept', '')],
                'i_val': m.get('similarity', 0.0),  # 使用相似度作为 ℐ 值近似
                'concept': m.get('concept', ''),
            })

        # 从子图边补充（若有 ℐ 值信息）
        subgraph = query_result.get('subgraph', {})
        for e in subgraph.get('edges', []):
            # 避免重复
            eid = f"e_{e.get('src', '')}_{e.get('dst', '')}"
            if not any(edge['eid'] == eid for edge in edges):
                edges.append({
                    'eid': eid,
                    'nodes': [e.get('src', ''), e.get('dst', '')],
                    'i_val': e.get('weight', 0.5),  # 使用权重作为 ℐ 值近似
                    'concept': f"{e.get('src', '')}_{e.get('dst', '')}",
                })

        return edges

    def apply_dimred(self, eml_path: str, concepts_path: str = None,
                     kappa: float = 4.0, dead_threshold: float = 0.15,
                     tau_max: int = 500, verbose: bool = True) -> Dict:
        """
        对已加载的 EML 图应用数学降维（EML Slimming Toolkit 四合一）。

        处理流水线:
          ITC（识别边界层+退火）→ GPCT（分层 STR-F）→ 拟阵（剪枝保基）→ 输出

        定理 7.1（统一主定理）保证：若 EML 源自太一投影且服从 ℐ 守恒，
        则存在度类划分使 k ≤ 参数，推理落入 FPT 区。

        Args:
            eml_path: .eml 文件路径
            concepts_path: .concepts.json 路径
            kappa: κ 折叠深度
            dead_threshold: 死零阈值
            tau_max: ITC 退火最大步数
            verbose: 调试输出

        Returns:
            dimred stats dict，包含压缩比、ℐ保留率、FPT判定等
        """
        try:
            from .eml_dimred import load_eml_graph, slim_eml

            vertices, edges, _ = load_eml_graph(eml_path, concepts_path)
            result = slim_eml(
                edges=edges, vertices=vertices,
                kappa=kappa, dead_threshold=dead_threshold,
                tau_max=tau_max, verbose=verbose,
            )
            self.dimred_enabled = True
            self.dimred_result = result

            return {
                'enabled': True,
                'original_edges': result.original_edges,
                'core_edges': len(result.core_edges),
                'compression_ratio': result.compression_ratio,
                'i_retention': result.i_retention,
                'is_fpt': result.is_fpt,
                'k_param': result.k_param,
                'pipeline_time_ms': result.pipeline_time_ms,
                'predictions': result.predictions,
            }
        except ImportError:
            if verbose:
                print("[DimRed] eml_dimred 模块未安装，跳过数学降维")
            return {'enabled': False, 'error': 'eml_dimred not available'}

    def get_dimred_stats(self) -> Dict:
        """获取数学降维统计信息"""
        if not self.dimred_enabled or not self.dimred_result:
            return {'enabled': False}
        r = self.dimred_result
        return {
            'enabled': True,
            'original_edges': r.original_edges,
            'core_edges': len(r.core_edges),
            'compression_ratio': r.compression_ratio,
            'i_retention': r.i_retention,
            'is_fpt': r.is_fpt,
            'k_param': r.k_param,
            'mus_circuits': r.mus_circuits,
            'paradox_circuits': r.paradox_circuits,
        }

    def query(self, text: str, top_k: int = 5, subgraph_radius: int = 2, kappa: float = 0.0) -> Dict:
        """
        输入文本 → 编码 → 概念匹配 → 子图扩展 → 解码 → 输出

        Returns:
            {
                'input_text': ...,
                'phi': [...],
                'matched_concepts': [...],
                'subgraph': {...},
                'confidence': ...
            }
        """
        # Step 1: 文本 → φ 空间
        phi = text_to_octonion(text)

        # Step 2: 概念匹配
        matched = self.bridge.find_nearest_concepts(phi, top_k)

        # Step 3: 子图扩展
        matched_ids = [m['vertex_id'] for m in matched if m['similarity'] > 0.3]
        subgraph = self.bridge.extract_subgraph(matched_ids, subgraph_radius, kappa) if matched_ids else {
            'vertices': [], 'edges': [], 'size': 0
        }

        # Step 4: 置信度
        confidence = max((m['similarity'] for m in matched), default=0.0)

        return {
            'input_text': text,
            'phi': phi.tolist(),
            'matched_concepts': matched,
            'subgraph': subgraph,
            'confidence': confidence
        }

    def _build_eml_context(self, result: Dict) -> str:
        """从 EML 查询结果构建结构化上下文（给 LLM 用）"""
        lines = []
        concepts = result.get('matched_concepts', [])
        sg = result.get('subgraph', {})

        if concepts:
            lines.append("【EML 知识图谱相关概念】")
            for i, m in enumerate(concepts[:5]):
                sim_bar = '█' * int(m['similarity'] * 10)
                lines.append(
                    f"  {i+1}. {m['concept']} "
                    f"(相似度 {m['similarity']:.0%}, δ={m['delta']:.3f})"
                )

        if sg and sg.get('vertices'):
            sg_verts = sg['vertices']
            sg_edges = sg.get('edges', [])
            lines.append(f"\n【关联子图：{len(sg_verts)} 个概念 + {len(sg_edges)} 条关系】")

            # 列出扩展概念
            matched_names = {m['concept'] for m in concepts}
            extended = [v for v in sg_verts if v.get('concept', '') not in matched_names]
            if extended:
                lines.append("  扩展概念：")
                for v in extended[:10]:
                    vid = v.get('id', '?')
                    cname = v.get('concept', f'concept_{vid}')
                    lines.append(f"    • {cname}")

            # 关键关系
            if sg_edges:
                lines.append("  关键关系：")
                name_map = {}
                for v in sg_verts:
                    vid = v.get('id', -1)
                    name_map[vid] = v.get('concept', f'c{vid}')
                for e in sg_edges[:8]:
                    src_name = name_map.get(e.get('src', -1), f"v{e.get('src','?')}")
                    dst_name = name_map.get(e.get('dst', -1), f"v{e.get('dst','?')}")
                    lines.append(f"    {src_name} → {dst_name} (权重 {e.get('weight', 0):.3f})")

        return '\n'.join(lines)

    def generate_response(self, text: str, top_k: int = 5,
                         force_translator: bool = False,
                         force_creative: bool = False,
                         kappa: float = 0.0) -> Dict:
        """
        智能路由：翻译官（事实）↔ 作家（创造）
                + 死零/MUS/κ-Snap 门控（TOMAS 核心 IP）

        路由逻辑：
          1. 先执行 EML 查询，获取置信度
          2. 死零校验：若 ℐ(e) < θ_dead ⇒ [DEAD_ZERO_REJECT]
          3. MUS 仲裁：若检测到悖论对 ⇒ [MUS_ACTIVE]
          4. 高置信度(≥0.5) → 翻译官（模板/LSTM）
          5. 低置信度(<0.5) → 作家（DeepSeek LLM + φ-Gate 监管）

        Returns:
            {
                'text': str,             # 生成的文本
                'mode': 'translator' | 'creative' | 'creative_gated' | 'fallback' | 'dead_zero_reject' | 'mus_active',
                'confidence': float,
                'gate_result': {...} | None,   # φ-Gate 检查结果
                'dead_zero_result': {...},      # 死零校验结果
                'mus_result': {...},           # MUS 仲裁结果
                'matched_concepts': [...],
            }
        """
        # Step 1: EML 查询
        result = self.query(text, top_k, kappa=kappa)
        confidence = result['confidence']

        # Step 2: 死零/MUS/κ-Snap 门控检查（TOMAS 核心 IP）
        matched_edges = self._extract_matched_edges(result)
        gate_result = self._apply_dead_zero_mus_gate(text, matched_edges)

        if not gate_result['proceed']:
            # 触发死零 ⇒ 拒绝回答
            return {
                'text': gate_result['reject_reason'],
                'mode': 'dead_zero_reject',
                'confidence': 0.0,
                'gate_result': None,
                'dead_zero_result': gate_result,
                'mus_result': {'mus_active': False},
                'matched_concepts': result['matched_concepts'],
            }

        # Step 3.5: 编排模式检查（Fugu 启发）
        if self._use_orchestration and self.orchestrator and not force_translator:
            is_complex = (
                is_conversational_query(text)  # 对话型 → 不编排（已是 creative 路径）
                or "\\n" in text
                or "？" in text and text.count("？") > 1
                or "?" in text and text.count("?") > 1
                or len(text) > 100
            )
            if is_complex and not is_chat:
                try:
                    orch_result = self.orchestrator.orchestrate(text, context={
                        "eml_ctx": {"kappa": kappa} if "kappa" in dir() else None
                    })
                    return {
                        "text": orch_result.synthesis or list(orch_result.agent_outputs.values())[0],
                        "mode": "orchestrated",
                        "confidence": confidence,
                        "gate_result": None,
                        "dead_zero_result": gate_result,
                        "mus_result": {"mus_active": False, "orchestration": True},
                        "matched_concepts": result["matched_concepts"],
                        "orchestration_trace": orch_result.trace,
                        "agents_used": orch_result.agents_used,
                    }
                except Exception as e:
                    print(f"⚠️ Orchestration 失败（回退到标准路由）：{e}")

        # Step 3: 判断路由
        # 对话型查询 → 强制走作家路径，不管 EML 置信度多高
        is_chat = is_conversational_query(text)
        has_llm = self.creative_engine is not None or self._use_router
        use_creative = force_creative or is_chat or (
            not force_translator
            and confidence < self.TRANSLATOR_THRESHOLD
            and has_llm
        )

        if not use_creative:
            # ═══════════════ 翻译官路径 ═══════════════
            response = self._translator_respond(text, result, top_k)
        elif self._use_router and self.router:
            # ═══════════════ 作家路径（Router 多模型路由） ═══════════════
            response = self._creative_respond_router(text, result)
        else:
            # ═══════════════ 作家路径（单一 DeepSeek LLM） ═══════════════
            response = self._creative_respond(text, result)

        # Step 4: 若 MUS 激活，标记响应
        if gate_result['mus_active']:
            response['mode'] = 'mus_active'
            response['mus_result'] = gate_result
            response['text'] = f"[MUS_ACTIVE: {gate_result['paradox_pairs']}]\n\n{response['text']}"

        return response

    def _translator_respond(self, text: str, result: Dict, top_k: int = 5) -> Dict:
        """翻译官：LSTM/模板事实复述"""
        # 优先神经解码
        if self.use_neural and self.neural_model is not None:
            try:
                from token_generator import generate_response_text
                resp = generate_response_text(
                    text, self.bridge, self,
                    use_neural=True, neural_model=self.neural_model, max_len=100
                )
                return {
                    'text': resp,
                    'mode': 'translator',
                    'confidence': result['confidence'],
                    'gate_result': None,
                    'matched_concepts': result['matched_concepts'],
                }
            except Exception as e:
                print(f"⚠️ 神经解码失败（回退到模板生成）：{e}")

        # 模板生成
        try:
            from token_generator import generate_response_text
            resp = generate_response_text(
                text, self.bridge, self, use_neural=False
            )
            return {
                'text': resp,
                'mode': 'translator',
                'confidence': result['confidence'],
                'gate_result': None,
                'matched_concepts': result['matched_concepts'],
            }
        except (ImportError, ModuleNotFoundError):
            resp = self._template_response(text, top_k)
            return {
                'text': resp,
                'mode': 'translator',
                'confidence': result['confidence'],
                'gate_result': None,
                'matched_concepts': result['matched_concepts'],
            }

    def _creative_respond(self, text: str, result: Dict) -> Dict:
        """作家：DeepSeek LLM 创造性生成 + φ-Gate 监管"""
        if self.creative_engine is None:
            # 没有 LLM，回退到翻译官
            resp = self._template_response(text, 5)
            return {
                'text': f"⚠️ 未配置 LLM 作家，回退到翻译官模式\n\n{resp}",
                'mode': 'fallback',
                'confidence': result['confidence'],
                'gate_result': None,
                'matched_concepts': result['matched_concepts'],
            }

        # 构建 EML 上下文
        eml_context = self._build_eml_context(result)

        # 调用 DeepSeek LLM
        try:
            llm_output = self.creative_engine.generate(text, eml_context)
        except Exception as e:
            print(f"⚠️ LLM 调用失败（回退到翻译官）：{e}")
            resp = self._template_response(text, 5)
            return {
                'text': f"⚠️ LLM 调用失败：{e}\n\n回退到翻译官：\n{resp}",
                'mode': 'fallback',
                'confidence': result['confidence'],
                'gate_result': {'error': str(e)},
                'matched_concepts': result['matched_concepts'],
            }

        # φ-Gate 监管
        gate_result = None
        if self.phi_gate is not None:
            gate_result = self.phi_gate.check(llm_output, result)
        
        if gate_result and gate_result.get('hallucinated'):
            # 幻觉检测：标记警告 + 附加翻译官内容
            warning = (
                f"⚠️ φ-Gate 检测到潜在幻觉 "
                f"(一致性 {gate_result.get('consistency', 0):.1%} < "
                f"{self.PHI_CONSISTENCY_THRESHOLD:.0%})\n\n"
            )
            translator_resp = self._template_response(text, 5)
            return {
                'text': f"{warning}【LLM 生成（已标记）】\n{llm_output}\n\n---\n【翻译官验证】\n{translator_resp}",
                'mode': 'creative_gated',
                'confidence': result['confidence'],
                'gate_result': gate_result,
                'matched_concepts': result['matched_concepts'],
            }

        return {
            'text': llm_output,
            'mode': 'creative',
            'confidence': result['confidence'],
            'gate_result': gate_result,
            'matched_concepts': result['matched_concepts'],
        }

    def _creative_respond_router(self, text: str, result: Dict,
                                  task_type: str = None) -> Dict:
        """作家（Router 多模型路由）：TOMAS Router + EML 注入 + φ-Gate 监管

        相比 _creative_respond（仅支持 DeepSeek），此方法通过 TOMASRouter：
        1. 按 task_type 自动选择最佳 LLM 后端
        2. 自动注入 EML 执行上下文（κ, θ_dead, MUS Tags）
        3. 支持模型池热切换（DeepSeek/GLM-5/Kimi/Miro-Med 等）

        Args:
            text: 用户查询文本
            result: query() 返回的 EML 匹配结果
            task_type: 任务类型（reason/code_gen/med_annotate/...），默认使用实例级 _task_type

        Returns:
            {text, mode, confidence, gate_result, matched_concepts, model_used}
        """
        task_type = task_type or self._task_type

        # 构建 EML 上下文（用于注入到系统提示词）
        eml_ctx = {
            "kappa": 4.0,
            "dead_zero_theta": 0.15,
            "mus_tags": ["Asym!=0 double-exist"],
        }
        if self.dimred_result:
            eml_ctx["kappa"] = self.dimred_result.k_param

        # 提取匹配的概念和边（用于 knowledge grounding）
        matched_concepts = result.get("matched_concepts", [])
        subgraph = result.get("subgraph", {})
        related_edges = subgraph.get("edges", [])

        # 格式化概念为 injector 兼容格式
        concept_dicts = [
            {"concept": c.get("concept", c.get("name", "?")), "i_val": c.get("phi_sim", c.get("score", 0))}
            for c in matched_concepts[:10]
        ]
        edge_dicts = [
            {"nodes": e.get("vertices", e.get("nodes", [])), "i_val": e.get("weight", e.get("i_val", 0)),
             "type": e.get("relation", e.get("type", "relates"))}
            for e in (related_edges if isinstance(related_edges, list) else [])[:10]
        ]

        # 调用 Router
        try:
            llm_output = self.router.route(
                task_type=task_type,
                prompt=text,
                eml_ctx=eml_ctx,
                sys_prompt=None,  # Router 内置 EML sysprompt
                concepts=concept_dicts,
                edges=edge_dicts,
            )
            model_used = self.router.routing_table.get(task_type, "deepseek")
        except Exception as e:
            print(f"⚠️ Router 调用失败（回退到翻译官）：{e}")
            resp = self._template_response(text, 5)
            return {
                'text': f"⚠️ Router 调用失败：{e}\n\n回退到翻译官：\n{resp}",
                'mode': 'fallback',
                'confidence': result['confidence'],
                'gate_result': {'error': str(e)},
                'matched_concepts': matched_concepts,
                'model_used': None,
            }

        # φ-Gate 监管（与 _creative_respond 一致）
        gate_result = None
        if self.phi_gate is not None:
            gate_result = self.phi_gate.check(llm_output, result)

        if gate_result and gate_result.get('hallucinated'):
            warning = (
                f"⚠️ φ-Gate 检测到潜在幻觉 "
                f"(一致性 {gate_result.get('consistency', 0):.1%} < "
                f"{self.PHI_CONSISTENCY_THRESHOLD:.0%})\n\n"
            )
            translator_resp = self._template_response(text, 5)
            return {
                'text': f"{warning}【{model_used} 生成（已标记）】\n{llm_output}\n\n---\n【翻译官验证】\n{translator_resp}",
                'mode': 'creative_gated',
                'confidence': result['confidence'],
                'gate_result': gate_result,
                'matched_concepts': matched_concepts,
                'model_used': model_used,
            }

        return {
            'text': llm_output,
            'mode': 'creative',
            'confidence': result['confidence'],
            'gate_result': gate_result,
            'matched_concepts': matched_concepts,
            'model_used': model_used,
        }

    def _template_response(self, text: str, top_k: int = 5) -> str:
        """内置模板生成（不依赖 token_generator 模块）"""
        result = self.query(text, top_k)

        if not result['matched_concepts']:
            return f"❌ 未能找到与「{text}」相关的概念。请先蒸馏相关知识领域。"

        # 构建响应
        lines = [f"🔍 查询：{text}\n"]
        lines.append(f"📊 匹配置信度：{result['confidence']:.2%}\n")

        # 匹配概念
        lines.append("📋 匹配概念：")
        for i, m in enumerate(result['matched_concepts']):
            bar = '█' * int(m['similarity'] * 10) + '░' * (10 - int(m['similarity'] * 10))
            lines.append(f"  {i+1}. {m['concept']}  相似度 {m['similarity']:.2%}  {bar}  δ={m['delta']:.3f}")

        # 子图信息
        sg = result['subgraph']
        if sg.get('vertex_count', 0) > 0:
            lines.append(f"\n🔗 关联子图：{sg['vertex_count']} 个概念 + {sg.get('edge_count', 0)} 条关系")

            # 列出子图中的概念
            sub_vertices = self.bridge.extract_subgraph(
                [m['vertex_id'] for m in result['matched_concepts'] if m['similarity'] > 0.3],
                radius=1, kappa=0.0
            )['vertices']

            if len(sub_vertices) > len(result['matched_concepts']):
                lines.append("  扩展概念：")
                seen = {m['concept'] for m in result['matched_concepts']}
                for v in sub_vertices:
                    if v['concept'] not in seen:
                        lines.append(f"    • {v['concept']}  δ={v['delta']:.3f}")
                        seen.add(v['concept'])

        return '\n'.join(lines)


# ============================================================
# 第3.5部分：创造性引擎（作家 — DeepSeek LLM）
# ============================================================

class CreativeEngine:
    """
    DeepSeek LLM 创造性生成引擎（作家）
    
    角色：处理 Token Bridge 覆盖不到的开放式/创造性问题
    受 φ-Gate 监管，确保生成内容与 EML 知识图谱一致
    """

    SYSTEM_PROMPT = """你是 TOMAS/太极OS 的创造性引擎。你的回答应基于提供的 EML 知识图谱上下文。

规则：
1. 如果上下文提供了明确信息，优先基于上下文回答
2. 如果上下文不足，可以基于你的知识进行创造性扩展，但需注明来源
3. 保持回答专业、准确、简洁
4. 用中文回答
5. 不要编造不存在的概念或事实"""

    def __init__(self, api_key: str = None, api_base: str = "https://api.deepseek.com/v1",
                 model: str = "deepseek-chat", temperature: float = 0.7, max_tokens: int = 1024):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.api_base = api_base.rstrip('/')
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def generate(self, query: str, eml_context: str = "") -> str:
        """
        调用 DeepSeek API 生成回复

        Args:
            query: 用户查询
            eml_context: EML 知识图谱上下文

        Returns:
            LLM 生成的文本回复
        """
        if not self.api_key:
            raise ValueError("未设置 DeepSeek API Key（设置 DEEPSEEK_API_KEY 环境变量或传入 api_key）")

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
        ]

        if eml_context:
            messages.append({
                "role": "system",
                "content": f"以下是 EML 知识图谱中的相关概念和关系，请优先参考：\n\n{eml_context}"
            })

        messages.append({"role": "user", "content": query})

        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except requests.exceptions.Timeout:
            raise RuntimeError("DeepSeek API 请求超时")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"DeepSeek API 请求失败：{e}")
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"DeepSeek API 响应格式异常：{e}")


# ============================================================
# 第3.6部分：φ-Gate 监管器
# ============================================================

class PhiGate:
    """
    φ-一致性监管器
    
    职责：
    1. 提取 LLM 输出中的关键概念
    2. 在 φ 空间中检查这些概念与 EML 图的一致性
    3. 检测潜在幻觉（编造的概念）
    4. 标记不一致内容，必要时触发回退
    """

    # 中文概念提取模式：匹配常见的中文专业术语
    CONCEPT_PATTERNS = [
        # 四字词/短语（中文字符连续4+字）
        re.compile(r'[\u4e00-\u9fff]{2,6}'),
        # 英文专业术语
        re.compile(r'[A-Z][a-z]+(?:[- ][A-Z][a-z]+)*'),
    ]

    def __init__(self, bridge: TokenBridge, consistency_threshold: float = 0.35):
        self.bridge = bridge
        self.consistency_threshold = consistency_threshold

    def extract_concepts(self, text: str, max_concepts: int = 10) -> List[str]:
        """
        从 LLM 输出中提取关键概念。
        用正则 + 频率统计提取可能的专业术语。
        """
        candidates = []
        seen = set()
        
        for pattern in self.CONCEPT_PATTERNS:
            for match in pattern.finditer(text):
                term = match.group().strip()
                if len(term) >= 2 and term not in seen:
                    # 过滤掉常见停用词
                    if not self._is_stopword(term):
                        candidates.append(term)
                        seen.add(term)

        # 去重 + 按长度排序（更长的术语通常更具体）
        candidates.sort(key=lambda x: -len(x))
        return candidates[:max_concepts]

    def _is_stopword(self, term: str) -> bool:
        """过滤掉常见的非概念性词汇"""
        stopwords = {
            '这个', '那个', '可以', '没有', '一个', '一些', '所有', '什么',
            '因为', '所以', '但是', '而且', '或者', '如果', '虽然', '因此',
            '进行', '使用', '通过', '需要', '可能', '应该', '能够', '以及',
            '问题', '回答', '信息', '内容', '方面', '情况', '方式', '过程',
            '关于', '来说', '其中', '包括', '非常', '那么', '这样', '已经',
            'then', 'have', 'from', 'with', 'that', 'this', 'they', 'their',
            'will', 'would', 'could', 'should', 'about', 'when', 'which',
        }
        return term in stopwords

    def _text_to_phi_simple(self, text: str) -> np.ndarray:
        """快速文本→φ 转换（哈希法）"""
        return text_to_octonion(text)

    def check(self, llm_output: str, query_result: Dict) -> Dict:
        """
        检查 LLM 输出与 EML 图的 φ 一致性

        Args:
            llm_output: LLM 生成的文本
            query_result: InferenceEngine.query() 的结果

        Returns:
            {
                'consistency': float,       # 总体 φ 一致性 (0~1)
                'hallucinated': bool,       # 是否检测到幻觉
                'hallucinated_concepts': [...], # 疑似幻觉的概念
                'verified_concepts': [...],     # φ 一致性通过的概念
                'per_concept_scores': {...},    # 逐概念得分
            }
        """
        concepts = self.extract_concepts(llm_output)
        if not concepts:
            return {
                'consistency': 0.5,  # 无法提取概念，中性分数
                'hallucinated': False,
                'hallucinated_concepts': [],
                'verified_concepts': [],
                'per_concept_scores': {},
            }

        # 匹配概念集合（供快速查找）
        matched_names = {m['concept'] for m in query_result.get('matched_concepts', [])}
        sg_verts = query_result.get('subgraph', {}).get('vertices', [])
        sg_names = {v.get('concept', '') for v in sg_verts}

        phi_llm = self._text_to_phi_simple(llm_output)
        
        per_concept_scores = {}
        verified = []
        hallucinated = []

        for concept in concepts:
            # 方法1：概念名称匹配
            name_match = concept in matched_names or concept in sg_names
            
            # 方法2：φ 空间最近邻搜索
            phi_c = self._text_to_phi_simple(concept)
            nearest = self.bridge.find_nearest_concepts(phi_c, top_k=1)
            
            if nearest:
                nearest_name = nearest[0]['concept']
                phi_sim = nearest[0]['similarity']
                
                # 综合得分：名称匹配 → 1.0，否则用 φ 相似度
                if name_match:
                    score = 1.0
                else:
                    score = phi_sim
                
                per_concept_scores[concept] = {
                    'score': score,
                    'nearest_eml': nearest_name,
                    'phi_sim': phi_sim,
                    'name_match': name_match,
                }
                
                if score >= self.consistency_threshold:
                    verified.append(concept)
                else:
                    hallucinated.append({
                        'concept': concept,
                        'score': score,
                        'nearest_eml': nearest_name,
                    })
            else:
                # 无法匹配任何 EML 概念
                per_concept_scores[concept] = {
                    'score': 0.0,
                    'nearest_eml': None,
                    'phi_sim': 0.0,
                    'name_match': False,
                }
                hallucinated.append({
                    'concept': concept,
                    'score': 0.0,
                    'nearest_eml': None,
                })

        # 总体一致性 = 平均分
        all_scores = [v['score'] for v in per_concept_scores.values()]
        consistency = sum(all_scores) / len(all_scores) if all_scores else 0.5

        return {
            'consistency': consistency,
            'hallucinated': len(hallucinated) > 0 and consistency < self.consistency_threshold,
            'hallucinated_concepts': hallucinated,
            'verified_concepts': verified,
            'per_concept_scores': per_concept_scores,
        }


# ============================================================
# 第4部分：CLI 入口
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="TOMAS/太极OS Token Bridge — 翻译官+作家 混合推理引擎")
    parser.add_argument("--load", type=str, help="加载 EML 图文件路径")
    parser.add_argument("--concepts", type=str, help="概念名称 JSON 文件路径")
    parser.add_argument("--train", action="store_true", help="训练 Token Bridge")
    parser.add_argument("--train-decoder", action="store_true", help="训练神经解码器（PhiToTokenModel）")
    parser.add_argument("--query", type=str, help="查询文本")
    parser.add_argument("--generate", action="store_true", help="使用神经解码器生成文本（需先训练）")
    parser.add_argument("--model", type=str, help="神经模型权重文件路径（.pt）")
    parser.add_argument("--top-k", type=int, default=5, help="返回 top-k 匹配")
    parser.add_argument("--embedding-dim", type=int, default=768, help="Embedding 维度")
    parser.add_argument("--info", action="store_true", help="显示 Bridge 大小估算")
    parser.add_argument("--max-len", type=int, default=50, help="最大生成长度")
    # 作家/LLM 相关
    parser.add_argument("--llm", action="store_true", help="启用 DeepSeek LLM 作家（创造性生成）")
    parser.add_argument("--router", action="store_true", help="启用 TOMAS 多模型 Router（替代 --llm 单一模型，支持 12+ LLM 按任务类型路由）")
    parser.add_argument("--router-config", type=str, default=None, help="Router 模型池配置文件路径（默认 model_pool.json）")
    parser.add_argument("--task-type", type=str, default="reason", 
                        choices=["reason", "long_extract", "code_gen", "med_annotate", "edu", "academic", "rag", "multilingual", "fallback"],
                        help="Router 任务类型（默认 reason）")
    parser.add_argument("--api-key", type=str, help="DeepSeek API Key")
    parser.add_argument("--api-base", type=str, default="https://api.deepseek.com/v1", help="API 地址")
    parser.add_argument("--llm-model", type=str, default="deepseek-chat", help="LLM 模型名")
    # φ-Gate 监管
    parser.add_argument("--gate", action="store_true", default=True, help="启用 φ-Gate 监管（默认启用）")
    parser.add_argument("--no-gate", dest="gate", action="store_false", help="禁用 φ-Gate 监管")
    parser.add_argument("--gate-threshold", type=float, default=0.35, help="φ-Gate 一致性阈值")
    # 路由控制
    parser.add_argument("--force-translator", action="store_true", help="强制使用翻译官（不走作家）")
    parser.add_argument("--force-creative", action="store_true", help="强制使用作家（不走翻译官）")
    parser.add_argument("--threshold", type=float, default=0.5, help="翻译官/作家族由阈值")
    parser.add_argument("--kappa", type=float, default=0.0, help="κ-Gate 语义剪枝阈值 (0=不剪枝, >0=仅保留 I(X)≥κ 的顶点/边)")
    # 数学降维
    parser.add_argument("--dimred", action="store_true", help="启用 EML 数学降维（四合一瘦身工具箱）")
    parser.add_argument("--dimred-kappa", type=float, default=4.0, help="数学降维 κ 折叠深度 (默认: 4)")
    parser.add_argument("--dimred-dead", type=float, default=0.15, help="数学降维死零阈值 (默认: 0.15)")
    parser.add_argument("--dimred-tau", type=int, default=500, help="ITC 退火最大步数 (默认: 500)")
    # 死零/MUS/κ-Snap 门控（TOMAS 核心 IP）
    parser.add_argument("--disable-dead-zero", action="store_true", help="禁用死零校验（调试用）")
    parser.add_argument("--theta-dead", type=float, default=0.15, help="死零阈值 θ_dead (默认: 0.15)")
    parser.add_argument("--disable-mus", action="store_true", help="禁用 MUS 仲裁（调试用）")
    parser.add_argument("--disable-k-snap", action="store_true", help="禁用 κ-Snap 决策（调试用）")
    # TOMAS-MemOS 融合层（记忆工程升维）
    parser.add_argument("--enable-memos", action="store_true", help="启用 TOMAS-MemOS 融合层（死零校验 + MUS 双存 + ψ-锚）")
    parser.add_argument("--memos-store", type=str, default=None, help="MemOS 记忆存储路径（默认 tomas_agi/data/memory_store.json）")
    parser.add_argument("--memos-theta-write", type=float, default=0.3, help="MemOS 写入阈值 θ_write (默认: 0.3)")
    parser.add_argument("--memos-psi", action="store_true", default=True, help="启用 ψ-锚（Self-Snapshot，默认启用）")
    parser.add_argument("--no-memos-psi", dest="memos_psi", action="store_false", help="禁用 ψ-锚")
    parser.add_argument("--memos-kappa-gate", action="store_true", default=True, help="启用 κ-Gate 激活（默认启用）")
    parser.add_argument("--no-memos-kappa-gate", dest="memos_kappa_gate", action="store_false", help="禁用 κ-Gate 激活")
    args = parser.parse_args()

    if not args.load:
        print("TOMAS/太极OS Token Bridge — 翻译官 + 作家 混合推理引擎")
        print("=" * 60)
        print("用法：")
        print("  翻译官（模板生成，无需训练）：")
        print("    python token_bridge.py --load data/distilled.eml --query '量子计算'")
        print("  翻译官（神经生成，需先训练）：")
        print("    python token_bridge.py --load data/distilled.eml --model model.pt --query 'AI' --generate")
        print("  作家（DeepSeek LLM，创造力模式）：")
        print("    python token_bridge.py --load data/distilled.eml --query 'AI的未来' --llm --api-key sk-xxx")
        print("  自动路由（翻译官↔作家）：")
        print("    python token_bridge.py --load data/distilled.eml --query 'xxx' --llm --api-key sk-xxx")
        print("  TOMAS Router（多模型智能路由，推荐）：")
        print("    python token_bridge.py --load data/distilled.eml --query 'xxx' --router --task-type reason")
        print("    python token_bridge.py --load data/distilled.eml --query '心肾不交辨证' --router --task-type med_annotate")
        print("  数学降维 + Router（终极模式）：")
        print("    python token_bridge.py --load data/distilled.eml --concepts data/concepts.json --dimred --query 'xxx' --router --task-type reason")
        print("  数学降维（四合一瘦身工具箱）：")
        print("    python token_bridge.py --load data/distilled.eml --concepts data/concepts.json --dimred --query 'xxx' --llm --api-key sk-xxx")
        print("  训练：")
        print("    python token_bridge.py --load data/distilled.eml --train --concepts data/concepts.json")
        print("    python token_bridge.py --load data/distilled.eml --train-decoder --concepts data/concepts.json")
        print("  显示大小估算：")
        print("    python token_bridge.py --load data/distilled.eml --info")
        return

    # 初始化
    bridge = TokenBridge(embedding_dim=args.embedding_dim)
    bridge.load_eml(args.load)

    # 加载概念名称
    if args.concepts:
        bridge.load_concept_names_from_json(args.concepts)

    # 数学降维（四合一瘦身工具箱）
    dimred_result = None
    if args.dimred:
        print("\n🧮 启用 EML 数学降维（四合一瘦身工具箱）...")
        from .eml_dimred import slim_eml, load_eml_graph
        try:
            verts, edgs, _ = load_eml_graph(args.load, args.concepts)
            dimred_result = slim_eml(
                edges=edgs, vertices=verts,
                kappa=args.dimred_kappa,
                dead_threshold=args.dimred_dead,
                tau_max=args.dimred_tau,
                verbose=True,
            )
            print(f"  数学降维完成: "
                  f"k={dimred_result.k_param}, "
                  f"FPT={'✓' if dimred_result.is_fpt else '✗'}, "
                  f"压缩 {dimred_result.compression_ratio:.1%}")
        except Exception as e:
            print(f"  ⚠️ 数学降维失败: {e}")

    # 训练 Token Bridge
    if args.train:
        concept_texts = [v['concept'] for v in bridge.loader.vertices if v['concept'] != f"concept_{v['id']}"]
        if concept_texts:
            bridge.train(concept_texts, epochs=100, lr=0.01, verbose=True)
        else:
            print("⚠️ 没有概念名称，跳过训练")

    # 训练神经解码器
    if args.train_decoder:
        try:
            from token_generator import PhiToTokenModel
            model = PhiToTokenModel(phi_dim=8, hidden_dim=128, vocab_size=2000)
            concept_names = [v['concept'] for v in bridge.loader.vertices]
            model.build_vocab(concept_names, concept_names)
            model.train_on_concepts(concept_names, epochs=100, lr=0.001)
            if args.model:
                model.save(args.model)
                print(f"✅ 神经解码器已保存：{args.model}")
        except ImportError:
            print("❌ token_generator 模块不可用，无法训练神经解码器。")

    # 大小估算
    if args.info:
        sizes = bridge.size_estimate()
        print("\n📦 Token Bridge 大小估算：")
        for k, v in sizes.items():
            if k in ('total_mb', 'target_met'):
                continue
            unit = 'MB' if v > 1024*1024 else 'KB' if v > 1024 else 'B'
            val = v / (1024*1024) if unit == 'MB' else v / 1024 if unit == 'KB' else v
            print(f"  {k}: {val:.2f} {unit}")
        print(f"\n  总计: {sizes['total_mb']:.2f} MB {'✅ < 100MB' if sizes['target_met'] else '❌ > 100MB'}")

    # 查询 / 生成
    if args.query:
        # 构建引擎（含死零/MUS/κ-Snap 门控）
        engine = InferenceEngine(
            bridge,
            dead_zero_enabled=not args.disable_dead_zero,
            theta_dead=args.theta_dead,
            mus_enabled=not args.disable_mus,
            k_snap_enabled=not args.disable_k_snap,
        )
        engine.TRANSLATOR_THRESHOLD = args.threshold
        
        # 打印门控状态
        if not args.disable_dead_zero:
            print(f"  ✅ 死零校验已启用（θ_dead={args.theta_dead:.2f}）")
        else:
            print(f"  ⚠️ 死零校验已禁用（调试模式）")
        if not args.disable_mus:
            print(f"  ✅ MUS 仲裁已启用")
        else:
            print(f"  ⚠️ MUS 仲裁已禁用（调试模式）")
        if not args.disable_k_snap:
            print(f"  ✅ κ-Snap 决策已启用")
        else:
            print(f"  ⚠️ κ-Snap 决策已禁用（调试模式）")

        # 神经解码器
        if args.generate or args.model:
            if args.model and os.path.exists(args.model):
                try:
                    from token_generator import PhiToTokenModel
                    model = PhiToTokenModel()
                    model.load(args.model)
                    engine.set_neural_model(model, use_neural=True)
                    print("🧠 神经解码器已加载")
                except Exception as e:
                    print(f"⚠️ 神经解码器加载失败：{e}")

        # 作家引擎 — 支持两种模式：
        #   --router: TOMAS 多模型 Router（推荐，支持 12+ LLM 按任务类型路由）
        #   --llm:    单一 DeepSeek LLM（向后兼容）
        if args.router:
            # ═══════════════ TOMAS Router 多模型路由 ═══════════════
            from router import TOMASRouter
            from eml_injector import EMLInjector

            router_config = args.router_config
            if not router_config:
                # 默认查找同目录下的 model_pool.json
                default_path = os.path.join(os.path.dirname(__file__), "model_pool.json")
                if os.path.exists(default_path):
                    router_config = default_path

            router = TOMASRouter(config_path=router_config)
            engine.set_router(router)
            engine._task_type = args.task_type

            # 显示可用模型
            avail = router.available_models
            total = len(router.all_models)
            print(f"\n🌐 TOMAS Router 已就绪 — {len(avail)}/{total} 模型可用")
            for m in avail[:5]:  # 最多显示 5 个
                print(f"   ✅ {m['label']} ({m['provider']}) — {m['notes'][:50]}")
            if total - len(avail) > 0:
                unavail = [m['label'] for m in router.all_models if not any(
                    a['name'] == m['name'] for a in avail)]
                print(f"   ⏳ 待配置 API Key: {', '.join(unavail[:3])}{'...' if len(unavail) > 3 else ''}")
            print(f"   当前任务类型: {args.task_type}")
            print(f"   路由策略: 按 task_type 自动分发到最优 LLM 后端")

        elif args.llm:
            # ═══════════════ 单一 DeepSeek LLM（向后兼容） ═══════════════
            api_key = args.api_key or os.environ.get("DEEPSEEK_API_KEY", "")
            if not api_key:
                print("⚠️ 未设置 DeepSeek API Key，作家引擎无法启动。")
                print("  设置方法：--api-key sk-xxx 或 环境变量 DEEPSEEK_API_KEY")
                print("  提示：可使用 --router 启用 TOMAS 多模型 Router")
            else:
                creative = CreativeEngine(
                    api_key=api_key,
                    api_base=args.api_base,
                    model=args.llm_model,
                )
                engine.set_creative_engine(creative)
                print(f"✍️  作家引擎已就绪（{args.llm_model}）")

                # φ-Gate 监管
                if args.gate:
                    gate = PhiGate(bridge, consistency_threshold=args.gate_threshold)
                    engine.set_phi_gate(gate)
                    engine.PHI_CONSISTENCY_THRESHOLD = args.gate_threshold
                    print(f"🛡️  φ-Gate 监管已启用（阈值 {args.gate_threshold:.0%}）")
                else:
                    print("⚠️  φ-Gate 监管已禁用")
            # 注意：如果 --router 也设置了，φ-Gate 会自动配合 Router 使用

        # 执行生成
        print(f"\n{'='*60}")
        print(f"查询：{args.query}")
        print(f"路由阈值：{engine.TRANSLATOR_THRESHOLD:.0%}")
        print(f"{'='*60}\n")

        # TOMAS-MemOS 融合层集成
        if args.enable_memos:
            if _HAS_MEMOS:
                try:
                    enable_memos_for_engine(engine, args)
                except Exception as e:
                    print(f"⚠️ MemOS 融合层初始化失败：{e}")
            else:
                print(f"⚠️ {_HAS_MEMOS_REASON}，无法启用 MemOS 融合层")

        response = engine.generate_response(
            args.query, args.top_k,
            force_translator=args.force_translator,
            force_creative=args.force_creative,
            kappa=args.kappa,
        )

        # 显示模式
        mode_icons = {
            'translator': '📖 翻译官',
            'creative': '✍️  作家',
            'creative_gated': '⚠️  作家（φ-Gate 已标记）',
            'fallback': '🔄 回退到翻译官',
        }
        mode_label = mode_icons.get(response['mode'], f"❓ {response['mode']}")
        model_info = f" | 模型: {response.get('model_used', 'N/A')}" if response.get('model_used') else ""
        print(f"【{mode_label}】{model_info}  置信度 {response['confidence']:.2%}\n")

        # 显示 φ-Gate 结果
        if response.get('gate_result'):
            gr = response['gate_result']
            if not gr.get('error'):
                print(f"  φ-一致性：{gr.get('consistency', 0):.2%}")
                if gr.get('hallucinated_concepts'):
                    hc = gr['hallucinated_concepts']
                    print(f"  疑似幻觉：{len(hc)} 个概念")
                    for h in hc[:5]:
                        print(f"    • {h['concept']} (得分 {h['score']:.2%})")

        print(f"{response['text']}\n")

        # 结构化结果
        result = engine.query(args.query, args.top_k)
        print(f"--- 结构化结果 ---")
        print(json.dumps({
            'input': result['input_text'],
            'mode': response['mode'],
            'confidence': result['confidence'],
            'matched_count': len(result['matched_concepts']),
            'top_concept': result['matched_concepts'][0]['concept'] if result['matched_concepts'] else None,
            'subgraph_size': result['subgraph'].get('size', 0),
            'gate_consistency': response.get('gate_result', {}).get('consistency') if response.get('gate_result') else None,
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


# ============================================================
# DiffInjector (Reasonix 编程智能体集成)
# ============================================================

import difflib as _difflib
import logging as _logging

_logger = _logging.getLogger("DiffInjector")


class DiffInjector:
    """增量编译验证 Diff 注入器。

    支持对代码文件进行增量 diff 计算和注入，
    用于 Reasonix 编程智能体的代码自修复和增量编译验证流程。

    Diff 结构：
        - 包含行级变更信息（增/删/改）
        - 计算基于 difflib.SequenceMatcher
        - 注入前自动验证 diff 的安全性

    方法：
        compute_diff(old_code, new_code) -> Diff: 计算两个代码版本之间的差异
        inject_diff(diff, target_file) -> bool: 将 diff 安全注入目标文件
    """

    # 安全模式关键词 — diff 中出现这些时拒绝注入
    _DANGEROUS_PATTERNS = [
        "del H_HARD_SYMBOLS",
        "del PHYSICS_CONSERVATION",
        "del MEMORY_SAFETY",
        "del TYPE_SAFETY",
        "del CONCURRENCY_SAFETY",
        "del DEAD_ZERO_THRESHOLD",
        "del MUS_DUAL_STORE",
        "__import__('os').system",
        "eval(",
        "exec(",
        "subprocess.call",
        "os.system(",
    ]

    def __init__(self):
        self._diff_history: List[Dict] = []

    def compute_diff(self, old_code: str, new_code: str) -> Dict:
        """计算两个代码版本之间的差异。

        Args:
            old_code: 原始代码字符串
            new_code: 新版本代码字符串

        Returns:
            Diff: 包含变更信息的字典
                - "operations": 变更操作列表 [{type, old_start, old_end, new_start, new_end, content}]
                - "summary": 变更摘要 {adds, deletes, modifies}
                - "is_safe": diff 是否安全（不含危险模式）
                - "preserves_hard_symbols": 是否保留硬锚符号集
        """
        old_lines = old_code.splitlines(keepends=True)
        new_lines = new_code.splitlines(keepends=True)

        matcher = _difflib.SequenceMatcher(None, old_lines, new_lines)
        operations = []
        summary = {"adds": 0, "deletes": 0, "modifies": 0}

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            op = {
                "type": tag,
                "old_start": i1,
                "old_end": i2,
                "new_start": j1,
                "new_end": j2,
                "content": new_lines[j1:j2] if tag in ("insert", "replace") else old_lines[i1:i2],
            }
            operations.append(op)

            if tag == "insert":
                summary["adds"] += (j2 - j1)
            elif tag == "delete":
                summary["deletes"] += (i2 - i1)
            elif tag == "replace":
                summary["modifies"] += max(i2 - i1, j2 - j1)

        # 安全性检查
        is_safe = self._check_safety(new_code)
        preserves_hard_symbols = self._check_hard_symbols_preserved(old_code, new_code)

        diff = {
            "operations": operations,
            "summary": summary,
            "is_safe": is_safe,
            "preserves_hard_symbols": preserves_hard_symbols,
            "old_code": old_code,
            "new_code": new_code,
        }
        self._diff_history.append(diff)
        return diff

    def inject_diff(self, diff: Dict, target_file: str) -> bool:
        """将 diff 安全注入目标文件。

        Args:
            diff: compute_diff 返回的差异字典
            target_file: 目标文件路径

        Returns:
            bool: 注入是否成功
        """
        # 安全性前置检查
        if not diff.get("is_safe", False):
            _logger.warning(f"Diff 注入被拒绝: 包含危险模式")
            return False
        if not diff.get("preserves_hard_symbols", True):
            _logger.warning(f"Diff 注入被拒绝: 硬锚符号集未保留")
            return False

        # 写入文件
        new_code = diff.get("new_code", "")
        if not new_code:
            _logger.warning("Diff 注入被拒绝: new_code 为空")
            return False

        try:
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(new_code)
            _logger.info(f"Diff 注入成功: {target_file}")
            return True
        except Exception as e:
            _logger.error(f"Diff 注入失败: {e}")
            return False

    def _check_safety(self, code: str) -> bool:
        """检查代码是否包含危险模式。"""
        for pattern in self._DANGEROUS_PATTERNS:
            if pattern in code:
                return False
        return True

    def _check_hard_symbols_preserved(self, old_code: str, new_code: str) -> bool:
        """检查硬锚符号集是否在新代码中保留。"""
        hard_symbols = [
            "PHYSICS_CONSERVATION",
            "MEMORY_SAFETY",
            "TYPE_SAFETY",
            "CONCURRENCY_SAFETY",
            "DEAD_ZERO_THRESHOLD",
            "MUS_DUAL_STORE",
        ]
        for symbol in hard_symbols:
            if symbol in old_code and symbol not in new_code:
                return False
        return True

    def get_diff_history(self) -> List[Dict]:
        """获取历史 diff 记录。"""
        return self._diff_history.copy()


# --- DiffInjector 自测 ---
if __name__ == "__main__" and "DiffInjector" in dir() and not hasattr(_difflib, '_TESTING'):
    print("\n=== DiffInjector 自测 ===")
    injector = DiffInjector()

    # 1. compute_diff
    old_code = "x = 1\ny = 2\nH_HARD_SYMBOLS = True\n"
    new_code = "x = 1\nz = 3\nH_HARD_SYMBOLS = True\n"
    diff = injector.compute_diff(old_code, new_code)
    print(f"  Diff 摘要: adds={diff['summary']['adds']}, "
          f"deletes={diff['summary']['deletes']}, modifies={diff['summary']['modifies']}")
    assert diff["is_safe"] is True
    assert diff["preserves_hard_symbols"] is True
    print("  [PASS] compute_diff 安全检查")

    # 2. 安全 diff 注入
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(old_code)
        tmp_path = f.name
    result = injector.inject_diff(diff, tmp_path)
    assert result is True
    with open(tmp_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "z = 3" in content
    print("  [PASS] inject_diff 成功")
    os.unlink(tmp_path)

    # 3. 危险 diff 拒绝
    dangerous_new = "x = 1\neval('os.system')\nH_HARD_SYMBOLS = True\n"
    dangerous_diff = injector.compute_diff(old_code, dangerous_new)
    assert dangerous_diff["is_safe"] is False
    assert injector.inject_diff(dangerous_diff, "/tmp/danger.py") is False
    print("  [PASS] 危险 diff 拒绝注入")

    # 4. 硬锚删除拒绝
    no_hard_new = "x = 1\nz = 3\n"
    no_hard_diff = injector.compute_diff(old_code, no_hard_new)
    assert no_hard_diff["preserves_hard_symbols"] is False
    print("  [PASS] 硬锚删除 diff 检测")

    print("=== DiffInjector 自测全部通过 ===")
