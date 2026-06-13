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

    def extract_subgraph(self, vertex_ids: List[int], radius: int = 2) -> Dict:
        """
        从匹配概念出发，BFS 扩展子图

        Args:
            vertex_ids: 起始顶点 ID 列表
            radius: BFS 扩展半径

        Returns:
            {'vertices': [...], 'edges': [...], 'size': int}
        """
        visited = set(vertex_ids)
        edge_indices = set()
        queue = deque([(vid, 0) for vid in vertex_ids])

        while queue:
            vid, dist = queue.popleft()
            if dist >= radius:
                continue

            # 查看邻接边
            for eidx in self.loader.get_adjacency().get(vid, []):
                edge = self.loader.edges[eidx]
                edge_indices.add(eidx)

                neighbor = edge['dst'] if edge['src'] == vid else edge['src']
                if neighbor not in visited and neighbor < len(self.loader.vertices):
                    visited.add(neighbor)
                    queue.append((neighbor, dist + 1))

        # 收集子图顶点和边
        sub_vertices = [self.loader.vertices[vid] for vid in visited if vid < len(self.loader.vertices)]
        sub_edges = [self.loader.edges[eidx] for eidx in edge_indices]

        return {
            'vertices': sub_vertices,
            'edges': sub_edges,
            'size': len(sub_vertices) + len(sub_edges)
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

    def __init__(self, bridge: TokenBridge, creative_engine=None, phi_gate=None):
        self.bridge = bridge
        self.creative_engine = creative_engine  # 作家
        self.phi_gate = phi_gate                # 监管者
        self.use_neural = False
        self.neural_model = None

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

    def query(self, text: str, top_k: int = 5, subgraph_radius: int = 2) -> Dict:
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
        subgraph = self.bridge.extract_subgraph(matched_ids, subgraph_radius) if matched_ids else {
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
                         force_creative: bool = False) -> Dict:
        """
        智能路由：翻译官（事实）↔ 作家（创造）

        路由逻辑：
          1. 先执行 EML 查询，获取置信度
          2. 高置信度(≥0.5) → 翻译官（模板/LSTM）
          3. 低置信度(<0.5) → 作家（DeepSeek LLM + φ-Gate 监管）

        Returns:
            {
                'text': str,             # 生成的文本
                'mode': 'translator' | 'creative' | 'creative_gated' | 'fallback',
                'confidence': float,
                'gate_result': {...} | None,   # φ-Gate 检查结果
                'matched_concepts': [...],
            }
        """
        # Step 1: EML 查询
        result = self.query(text, top_k)
        confidence = result['confidence']

        # Step 2: 判断路由
        use_creative = force_creative or (
            not force_translator
            and confidence < self.TRANSLATOR_THRESHOLD
            and self.creative_engine is not None
        )

        if not use_creative:
            # ═══════════════ 翻译官路径 ═══════════════
            return self._translator_respond(text, result, top_k)
        else:
            # ═══════════════ 作家路径 ═══════════════
            return self._creative_respond(text, result)

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
                radius=1
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
        # 构建引擎
        engine = InferenceEngine(bridge)
        engine.TRANSLATOR_THRESHOLD = args.threshold

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

        # 作家引擎（DeepSeek LLM）
        if args.llm:
            api_key = args.api_key or os.environ.get("DEEPSEEK_API_KEY", "")
            if not api_key:
                print("⚠️ 未设置 DeepSeek API Key，作家引擎无法启动。")
                print("  设置方法：--api-key sk-xxx 或 环境变量 DEEPSEEK_API_KEY")
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

        # 执行生成
        print(f"\n{'='*60}")
        print(f"查询：{args.query}")
        print(f"路由阈值：{engine.TRANSLATOR_THRESHOLD:.0%}")
        print(f"{'='*60}\n")

        response = engine.generate_response(
            args.query, args.top_k,
            force_translator=args.force_translator,
            force_creative=args.force_creative,
        )

        # 显示模式
        mode_icons = {
            'translator': '📖 翻译官',
            'creative': '✍️  作家',
            'creative_gated': '⚠️  作家（φ-Gate 已标记）',
            'fallback': '🔄 回退到翻译官',
        }
        mode_label = mode_icons.get(response['mode'], f"❓ {response['mode']}")
        print(f"【{mode_label}】  置信度 {response['confidence']:.2%}\n")

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
