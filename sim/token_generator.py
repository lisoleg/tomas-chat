"""
Token Generator — φ→Token 无 LLM 对话生成器
=============================================

将 Token Bridge 的 φ 场解码为自然语言文本，完全不依赖 LLM。

两种模式：
  1. 模板模式（无需训练）：从 EML 图检索知识，用模板组装成回复
  2. 神经解码模式（需训练）：训练 LSTM/Transformer 解码器，φ→token→文本

作者：复合体理学研究中心（TOMAS 项目组）
日期：2026-06-13
"""

import os
import json
import math
import random
import numpy as np
from typing import List, Dict, Tuple, Optional, Any
from collections import Counter

# ============================================================
# 第1部分：简单分词器（Word-Level）
# ============================================================

class SimpleTokenizer:
    """
    词级分词器：从语料构建词表，支持 encode/decode。
    用于神经解码器的文本输入输出。
    """
    PAD_TOKEN = "<PAD>"
    UNK_TOKEN = "<UNK>"
    BOS_TOKEN = "<BOS>"
    EOS_TOKEN = "<EOS>"

    def __init__(self, vocab_size: int = 5000):
        self.vocab_size = vocab_size
        self.token_to_id: Dict[str, int] = {}
        self.id_to_token: Dict[int, str] = {}
        self._build_special_tokens()

    def _build_special_tokens(self):
        special = [self.PAD_TOKEN, self.UNK_TOKEN, self.BOS_TOKEN, self.EOS_TOKEN]
        for i, tok in enumerate(special):
            self.token_to_id[tok] = i
            self.id_to_token[i] = tok
        self.pad_id = 0
        self.unk_id = 1
        self.bos_id = 2
        self.eos_id = 3
        self._next_id = 4

    def build_vocab(self, texts: List[str], min_freq: int = 1):
        """
        从文本列表构建词表。
        支持中文（按字切分）和英文（按词切分）。
        """
        counter = Counter()
        for text in texts:
            tokens = self._tokenize(text)
            counter.update(tokens)

        # 按频率排序，取 top-(vocab_size - 4 special tokens)
        max_normal = self.vocab_size - self._next_id
        for token, freq in counter.most_common(max_normal):
            if freq < min_freq:
                break
            if token not in self.token_to_id:
                self.token_to_id[token] = self._next_id
                self.id_to_token[self._next_id] = token
                self._next_id += 1

        print(f"[SimpleTokenizer] 词表大小：{len(self.token_to_id)}（目标 {self.vocab_size}）")

    def _tokenize(self, text: str) -> List[str]:
        """
        简单分词：
        - 中文：按字切分（每个汉字单独作为一个 token）
        - 英文/数字：按空格和标点切分
        """
        tokens = []
        current_word = ""
        for ch in text:
            if '\u4e00' <= ch <= '\u9fff':  # 中文
                if current_word:
                    tokens.append(current_word)
                    current_word = ""
                tokens.append(ch)
            elif ch.isalnum():
                current_word += ch
            else:
                if current_word:
                    tokens.append(current_word)
                    current_word = ""
                if ch.strip():  # 保留标点
                    tokens.append(ch)
        if current_word:
            tokens.append(current_word)
        return tokens

    def encode(self, text: str, max_len: Optional[int] = None, add_bos: bool = True, add_eos: bool = True) -> List[int]:
        """文本 → token ID 序列"""
        tokens = self._tokenize(text)
        ids = []
        if add_bos:
            ids.append(self.bos_id)
        for tok in tokens:
            ids.append(self.token_to_id.get(tok, self.unk_id))
        if add_eos:
            ids.append(self.eos_id)
        if max_len is not None:
            ids = ids[:max_len]
        return ids

    def decode(self, ids: List[int], skip_special: bool = True) -> str:
        """token ID 序列 → 文本"""
        tokens = []
        for tid in ids:
            if tid in self.id_to_token:
                tok = self.id_to_token[tid]
                if skip_special and tok in (self.PAD_TOKEN, self.UNK_TOKEN, self.BOS_TOKEN, self.EOS_TOKEN):
                    continue
                tokens.append(tok)
            else:
                tokens.append(self.UNK_TOKEN)
        # 简单拼接（中文无需空格，英文需要）
        text = ""
        for i, tok in enumerate(tokens):
            if len(tok) == 1 and '\u4e00' <= tok <= '\u9fff':
                text += tok
            else:
                if i > 0 and text and text[-1] not in (' ', '\n', '。', '，', '：', '；', '！', '？'):
                    text += ' '
                text += tok
        return text.strip()

    def vocab(self) -> Dict[str, int]:
        return dict(self.token_to_id)

    def __len__(self):
        return len(self.token_to_id)


# ============================================================
# 第2部分：模板生成器（无需训练）
# ============================================================

def template_generate(
    query: str,
    matched_concepts: List[Dict],
    subgraph_vertices: List[Dict],
    subgraph_edges: List[Dict],
    concept_names: Dict[int, str],
    max_response_len: int = 300
) -> str:
    """
    模板驱动的文本生成（无需训练，立即可用）。

    从 EML 图中检索知识，用自然语言模板组装成回复。

    Args:
        query: 用户输入的查询文本
        matched_concepts: 匹配的概念列表 [{concept, similarity, delta, ...}]
        subgraph_vertices: 子图顶点列表
        subgraph_edges: 子图边列表
        concept_names: 概念 ID → 名称映射
        max_response_len: 最大回复长度（字符数）

    Returns:
        生成的自然语言回复文本
    """
    if not matched_concepts:
        return f"抱歉，我在当前知识库中没有找到与「{query}」相关的概念。请先通过蒸馏功能添加相关知识。"

    lines = []

    # 1. 开头：确认查询主题
    top_concept = matched_concepts[0]['concept']
    lines.append(f"关于「{top_concept}」，我找到了以下相关知识：\n")

    # 2. 核心概念介绍
    lines.append("【核心概念】")
    for i, mc in enumerate(matched_concepts[:5]):
        concept = mc['concept']
        delta = mc.get('delta', 0.0)
        # 查找这个概念的描述（从相邻概念的关系中推断）
        related = _find_related_concepts(mc['vertex_id'], subgraph_edges, concept_names)
        desc = f"信息存在度 δ={delta:.3f}"
        if related:
            desc += f"，与「{related[0]}」等相关"
        lines.append(f"  {i+1}. {concept} — {desc}")
    lines.append("")

    # 3. 关系网络
    if subgraph_edges:
        lines.append("【关系网络】")
        rel_summary = _summarize_relations(subgraph_edges, concept_names, matched_concepts)
        lines.append(rel_summary)
        lines.append("")

    # 4. 扩展知识
    if len(subgraph_vertices) > len(matched_concepts):
        lines.append("【扩展知识】")
        seen = {mc['concept'] for mc in matched_concepts}
        extra = []
        for v in subgraph_vertices:
            name = v.get('concept', f"概念_{v['id']}")
            if name not in seen and len(extra) < 5:
                delta = v.get('delta', 0.0)
                extra.append(f"  • {name}（δ={delta:.3f}）")
                seen.add(name)
        if extra:
            lines.extend(extra)
        lines.append("")

    # 5. 结尾
    lines.append(f"以上是基于已蒸馏知识库对「{query}」的回答。")
    lines.append("如需更深入的分析，请继续提问或蒸馏更多相关文本。")

    response = "\n".join(lines)
    if len(response) > max_response_len:
        response = response[:max_response_len] + "\n...(内容过长，已截断)"

    return response


def _find_related_concepts(vertex_id: int, edges: List[Dict], concept_names: Dict[int, str]) -> List[str]:
    """查找与给定顶点相关的概念名称列表"""
    related = []
    for e in edges:
        if e['src'] == vertex_id:
            related.append(concept_names.get(e['dst'], f"概念_{e['dst']}"))
        elif e['dst'] == vertex_id:
            related.append(concept_names.get(e['src'], f"概念_{e['src']}"))
        if len(related) >= 3:
            break
    return related


def _summarize_relations(edges: List[Dict], concept_names: Dict[int, str], matched_concepts: List[Dict]) -> str:
    """将关系边总结为自然语言"""
    # 关系类型映射
    rel_type_names = {
        'is_a': '是…的一种',
        'part_of': '是…的一部分',
        'causes': '导致',
        'related_to': '相关于',
        'used_in': '用于',
        'inspired_by': '受启发于'
    }

    matched_ids = {mc['vertex_id'] for mc in matched_concepts}
    lines = []

    # 只显示与匹配概念相关的关系
    shown = set()
    for e in edges:
        src_name = concept_names.get(e['src'], f"概念_{e['src']}")
        dst_name = concept_names.get(e['dst'], f"概念_{e['dst']}")
        rel_type = e.get('rel_type', 'related_to')
        rel_text = rel_type_names.get(rel_type, rel_type)

        # 只显示包含匹配概念的关系
        if e['src'] in matched_ids or e['dst'] in matched_ids:
            key = f"{e['src']}-{e['dst']}"
            if key not in shown:
                lines.append(f"  • {src_name} {rel_text} {dst_name}")
                shown.add(key)

        if len(shown) >= 5:
            break

    if not lines:
        lines.append("  （无显式关系，概念通过语义相似度关联）")

    return "\n".join(lines)


# ============================================================
# 第3部分：φ→Token 神经解码器（PyTorch LSTM）
# ============================================================

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    _HAS_TORCH = True
except ImportError:
    _HAS_TORCH = False
    print("[TokenGenerator] ⚠️ PyTorch 未安装，神经解码器不可用。将仅使用模板生成。")


if _HAS_TORCH:
    class PhiToTokenDecoder(nn.Module):
        """
        φ→Token 解码器（LSTM 版）

        输入：φ 序列 (batch, seq_len, 8)
        输出：token logits (batch, seq_len, vocab_size)

        架构：
          φ_proj (8 → hidden) → LSTM layers → output_proj (hidden → vocab_size)
        """
        def __init__(self, phi_dim: int = 8, hidden_dim: int = 256,
                     num_layers: int = 2, vocab_size: int = 5000,
                     dropout: float = 0.2):
            super().__init__()
            self.phi_dim = phi_dim
            self.hidden_dim = hidden_dim
            self.vocab_size = vocab_size

            # φ 投影层：将 8 维 φ 映射到 hidden_dim
            self.phi_proj = nn.Linear(phi_dim, hidden_dim)

            # LSTM 解码器
            self.lstm = nn.LSTM(
                input_size=hidden_dim,
                hidden_size=hidden_dim,
                num_layers=num_layers,
                dropout=dropout if num_layers > 1 else 0.0,
                batch_first=True
            )

            # 输出投影：hidden → vocab_size
            self.output_proj = nn.Linear(hidden_dim, vocab_size)

            # 可选的 token embedding（如果输入是 token ID 而非 φ）
            self.token_embedding = nn.Embedding(vocab_size, hidden_dim)

            self.dropout = nn.Dropout(dropout)

        def forward(self, phi_sequence: torch.Tensor,
                    hidden: Optional[Tuple[torch.Tensor, torch.Tensor]] = None) -> Tuple[torch.Tensor, Tuple[torch.Tensor, torch.Tensor]]:
            """
            Args:
                phi_sequence: (batch, seq_len, phi_dim) φ 序列
                hidden: LSTM 初始隐藏状态

            Returns:
                logits: (batch, seq_len, vocab_size) token logits
                hidden: 最终隐藏状态
            """
            # 投影 φ → hidden
            x = self.phi_proj(phi_sequence)    # (batch, seq_len, hidden_dim)
            x = F.relu(x)
            x = self.dropout(x)

            # LSTM
            x, hidden = self.lstm(x, hidden)   # (batch, seq_len, hidden_dim)
            x = self.dropout(x)

            # 投影到词表
            logits = self.output_proj(x)         # (batch, seq_len, vocab_size)

            return logits, hidden

        def generate_step(self, phi_step: torch.Tensor,
                         hidden: Optional[Tuple[torch.Tensor, torch.Tensor]] = None,
                         temperature: float = 1.0) -> Tuple[torch.Tensor, Tuple[torch.Tensor, torch.Tensor]]:
            """
            单步生成：给定当前 φ 向量，输出下一个 token 的 logits。

            Args:
                phi_step: (batch, 1, phi_dim) 或 (batch, phi_dim) 当前步的 φ
                hidden: LSTM 隐藏状态

            Returns:
                logits: (batch, 1, vocab_size)
                hidden: 更新后的隐藏状态
            """
            if phi_step.dim() == 2:
                phi_step = phi_step.unsqueeze(1)  # (batch, 1, phi_dim)
            logits, hidden = self.forward(phi_step, hidden)
            if temperature != 1.0:
                logits = logits / temperature
            return logits, hidden

    class PhiToTokenModel:
        """
        φ→Token 生成模型（包装 Decoder + 分词器 + 生成逻辑）
        """
        def __init__(self, phi_dim: int = 8, hidden_dim: int = 256,
                     num_layers: int = 2, vocab_size: int = 5000,
                     device: str = 'cpu'):
            if not _HAS_TORCH:
                raise RuntimeError("PyTorch 未安装，无法使用神经解码器。")

            self.phi_dim = phi_dim
            self.hidden_dim = hidden_dim
            self.vocab_size = vocab_size
            self.device = device

            self.decoder = PhiToTokenDecoder(phi_dim, hidden_dim, num_layers, vocab_size)
            self.decoder.to(device)

            self.tokenizer = SimpleTokenizer(vocab_size=vocab_size)

            self._trained = False

        def build_vocab(self, texts: List[str], concept_names: List[str]):
            """构建分词器词表（从语料 + 概念名称）"""
            all_texts = list(texts) + list(concept_names)
            self.tokenizer.build_vocab(all_texts, min_freq=1)
            # 更新 decoder 的 vocab_size 以匹配实际词表
            actual_vocab = len(self.tokenizer)
            if actual_vocab != self.vocab_size:
                print(f"[PhiToTokenModel] 实际词表大小 {actual_vocab} 与预设 {self.vocab_size} 不同，重新初始化输出层...")
                self.vocab_size = actual_vocab
                # 重新创建输出投影层
                self.decoder.output_proj = nn.Linear(self.hidden_dim, actual_vocab).to(self.device)

        def train_step(self, phi_sequence: torch.Tensor, target_ids: torch.Tensor,
                       optimizer: Optional[Any] = None) -> float:
            """
            单步训练：给定 φ 序列和目标 token ID 序列，计算损失并反向传播。

            Args:
                phi_sequence: (1, seq_len, phi_dim) φ 序列
                target_ids: (1, seq_len) 目标 token ID 序列
                optimizer: PyTorch 优化器（如果为 None，只计算损失不更新）

            Returns:
                loss_value: 损失值（标量）
            """
            self.decoder.train()
            if optimizer is not None:
                optimizer.zero_grad()

            phi_sequence = phi_sequence.to(self.device)
            target_ids = target_ids.to(self.device)

            logits, _ = self.decoder(phi_sequence)  # (1, seq_len, vocab_size)

            # 计算交叉熵损失（忽略 PAD token）
            loss_fn = nn.CrossEntropyLoss(ignore_index=self.tokenizer.pad_id)
            # logits: (batch*seq_len, vocab_size), targets: (batch*seq_len)
            loss = loss_fn(logits.view(-1, self.vocab_size), target_ids.view(-1))

            if optimizer is not None:
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.decoder.parameters(), 1.0)
                optimizer.step()

            return loss.item()

        def train_on_concepts(self, concept_names: List[str], epochs: int = 50,
                              lr: float = 0.001, verbose: bool = True):
            """
            在概念名称上训练解码器（自编码式训练）。

            对每个概念名称：
              输入：该概念的 φ 向量（重复 seq_len 次，或作为 1-step 输入）
              目标：该概念名称的 token ID 序列

            这是一个简化训练，让模型学习 φ → token 的映射。
            """
            if not concept_names:
                print("⚠️ 没有概念名称，跳过训练")
                return

            # 确保词表已构建
            if len(self.tokenizer) <= 4:  # 只有 special tokens
                print("[train_on_concepts] 词表未构建，自动构建...")
                self.build_vocab(concept_names, concept_names)

            # 准备训练数据：概念名称 → φ 向量（通过 text_to_octonion）
            from token_bridge import text_to_octonion

            train_data = []  # [(phi_vector, target_ids)]
            for name in concept_names:
                phi = text_to_octonion(name, self.phi_dim)  # (8,)
                target_ids = self.tokenizer.encode(name, max_len=20)
                train_data.append((phi, target_ids))

            # 训练
            self.decoder.train()
            optimizer = torch.optim.Adam(self.decoder.parameters(), lr=lr)

            for epoch in range(epochs):
                total_loss = 0.0
                random.shuffle(train_data)

                for phi, target_ids in train_data:
                    # phi: (8,) → (1, 1, 8) 作为单步输入
                    phi_tensor = torch.tensor(phi, dtype=torch.float32).unsqueeze(0).unsqueeze(0).to(self.device)
                    target_tensor = torch.tensor(target_ids, dtype=torch.long).unsqueeze(0).to(self.device)

                    loss = self.train_step(phi_tensor, target_tensor, optimizer)
                    total_loss += loss

                avg_loss = total_loss / len(train_data)
                if verbose and (epoch + 1) % 10 == 0:
                    print(f"  Epoch {epoch+1}/{epochs}: loss={avg_loss:.4f}")

            self._trained = True
            print(f"✅ 解码器训练完成（{len(train_data)} 个概念，{epochs} 轮）")

        def generate_greedy(self, phi_sequence: np.ndarray,
                           max_len: int = 20, temperature: float = 1.0) -> List[int]:
            """
            贪心解码：给定 φ 序列，逐 token 生成。

            Args:
                phi_sequence: (seq_len, phi_dim) numpy 数组
                max_len: 最大生成长度
                temperature: 采样温度（1.0 = 贪心）

            Returns:
                token_ids: 生成的 token ID 列表
            """
            self.decoder.eval()
            with torch.no_grad():
                seq_len = phi_sequence.shape[0]
                phi_tensor = torch.tensor(phi_sequence, dtype=torch.float32).unsqueeze(0).to(self.device)
                # (1, seq_len, phi_dim)

                hidden = None
                all_token_ids = [self.tokenizer.bos_id]

                for step in range(max_len):
                    # 取当前步的 φ（循环使用 phi_sequence）
                    step_phi = phi_tensor[:, step % seq_len, :].unsqueeze(1)  # (1, 1, phi_dim)
                    logits, hidden = self.decoder.generate_step(step_phi, hidden, temperature)
                    # logits: (1, 1, vocab_size)

                    # 取最后一个 token 的 logits
                    next_token_logits = logits[0, -1, :]  # (vocab_size,)

                    if temperature <= 0.01:
                        # 贪心
                        next_token = torch.argmax(next_token_logits).item()
                    else:
                        # 采样
                        probs = F.softmax(next_token_logits / temperature, dim=-1)
                        next_token = torch.multinomial(probs, 1).item()

                    all_token_ids.append(next_token)
                    if next_token == self.tokenizer.eos_id:
                        break

                return all_token_ids

        def generate_beam(self, phi_sequence: np.ndarray,
                          max_len: int = 20, beam_width: int = 3) -> List[List[int]]:
            """
            Beam Search 解码：返回 top-beam_width 个候选序列。
            """
            self.decoder.eval()
            with torch.no_grad():
                seq_len = phi_sequence.shape[0]
                phi_tensor = torch.tensor(phi_sequence, dtype=torch.float32).unsqueeze(0).to(self.device)

                # 初始状态：BOS token
                hidden = None
                beams = [([self.tokenizer.bos_id], 0.0, hidden)]  # (token_ids, score, hidden)

                for step in range(max_len):
                    new_beams = []
                    for token_ids, score, hidden in beams:
                        if token_ids[-1] == self.tokenizer.eos_id:
                            new_beams.append((token_ids, score, hidden))
                            continue

                        step_phi = phi_tensor[:, step % seq_len, :].unsqueeze(1)
                        logits, new_hidden = self.decoder.generate_step(step_phi, hidden)
                        log_probs = F.log_softmax(logits[0, -1, :], dim=-1)

                        # 取 top-k
                        topk_log_probs, topk_ids = torch.topk(log_probs, beam_width)

                        for i in range(beam_width):
                            new_token_ids = token_ids + [topk_ids[i].item()]
                            new_score = score + topk_log_probs[i].item()
                            new_beams.append((new_token_ids, new_score, new_hidden))

                    # 保留 top-beam_width 个
                    new_beams.sort(key=lambda x: x[1], reverse=True)
                    beams = new_beams[:beam_width]

                # 返回 token ID 序列（去掉 hidden）
                return [b[0] for b in beams]

        def generate_text(self, phi_sequence: np.ndarray,
                         max_len: int = 50, temperature: float = 0.8,
                         use_beam: bool = False, beam_width: int = 3) -> str:
            """生成文本（端到端：φ 序列 → 文本）"""
            if not self._trained:
                raise RuntimeError("解码器尚未训练，请先调用 train_on_concepts()")

            if use_beam:
                beams = self.generate_beam(phi_sequence, max_len, beam_width)
                best_ids = beams[0]
                return self.tokenizer.decode(best_ids)
            else:
                ids = self.generate_greedy(phi_sequence, max_len, temperature)
                return self.tokenizer.decode(ids)

        def save(self, path: str):
            """保存模型权重和分词器"""
            os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
            torch.save({
                'decoder_state': self.decoder.state_dict(),
                'vocab_size': self.vocab_size,
                'phi_dim': self.phi_dim,
                'hidden_dim': self.hidden_dim,
                'num_layers': self.decoder.lstm.num_layers,
                'tokenizer_vocab': self.tokenizer.vocab(),
            }, path)
            print(f"[PhiToTokenModel] 模型已保存：{path}")

        def load(self, path: str):
            """加载模型权重和分词器"""
            checkpoint = torch.load(path, map_location=self.device)
            self.decoder.load_state_dict(checkpoint['decoder_state'])
            # 恢复分词器词表
            saved_vocab = checkpoint.get('tokenizer_vocab', {})
            self.tokenizer.token_to_id = dict(saved_vocab)
            self.tokenizer.id_to_token = {int(v): k for k, v in self.tokenizer.token_to_id.items()}
            self.tokenizer._next_id = max(self.tokenizer.id_to_token.keys()) + 1 if self.tokenizer.id_to_token else 4
            self._trained = True
            print(f"[PhiToTokenModel] 模型已加载：{path}")


# ============================================================
# 第4部分：端到端生成函数（供外部调用）
# ============================================================

def generate_response_text(
    query: str,
    bridge: Any,   # TokenBridge 实例
    engine: Any,    # InferenceEngine 实例
    use_neural: bool = False,
    neural_model: Optional[Any] = None,
    max_len: int = 100
) -> str:
    """
    端到端无 LLM 对话生成。

    Args:
        query: 用户输入
        bridge: TokenBridge 实例（已加载 EML 图）
        engine: InferenceEngine 实例
        use_neural: 是否使用神经解码器（需先训练）
        neural_model: 训练好的 PhiToTokenModel（如果 use_neural=True）
        max_len: 最大生成长度

    Returns:
        生成的自然语言回复
    """
    # Step 1: 用 InferenceEngine 做概念匹配和子图检索
    result = engine.query(query, top_k=5)

    if not result['matched_concepts']:
        return f"❌ 未能找到与「{query}」相关的概念。请先蒸馏相关知识领域。"

    # 获取匹配概念和子图
    matched = result['matched_concepts']
    matched_ids = [m['vertex_id'] for m in matched if m['similarity'] > 0.3]

    # 获取子图顶点和边
    subgraph = bridge.extract_subgraph(matched_ids, radius=2)
    sub_vertices = subgraph['vertices']
    sub_edges = subgraph['edges']

    # 获取概念名称映射
    concept_names = {v['id']: v['concept'] for v in bridge.loader.vertices}

    # Step 2: 如果使用神经解码器且已训练
    if use_neural and neural_model is not None and neural_model._trained:
        try:
            # 构建 φ 序列（匹配概念 + 扩展概念的 φ）
            phi_sequence = []
            for m in matched[:3]:  # 取 top-3 匹配概念
                vid = m['vertex_id']
                if vid < len(bridge.loader.vertices):
                    phi = bridge.loader.vertices[vid]['octonion']
                    phi_sequence.append(phi)

            if not phi_sequence:
                raise ValueError("无法构建 φ 序列")

            phi_array = np.array(phi_sequence)  # (seq_len, 8)

            # 生成文本
            text = neural_model.generate_text(phi_array, max_len=max_len, temperature=0.8)
            return text
        except Exception as e:
            print(f"⚠️ 神经解码失败（回退到模板生成）：{e}")

    # Step 3: 模板生成（默认，无需训练）
    return template_generate(
        query=query,
        matched_concepts=matched,
        subgraph_vertices=sub_vertices,
        subgraph_edges=sub_edges,
        concept_names=concept_names,
        max_response_len=500
    )


# ============================================================
# 第5部分：CLI 测试
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Token Generator — φ→Token 无 LLM 对话生成器")
    parser.add_argument("--eml", type=str, help="EML 图文件路径")
    parser.add_argument("--concepts", type=str, help="概念名称 JSON 文件路径")
    parser.add_argument("--query", type=str, help="测试查询文本")
    parser.add_argument("--model", type=str, help="神经模型权重文件路径（.pt）")
    parser.add_argument("--train", action="store_true", help="训练神经解码器")
    parser.add_argument("--neural", action="store_true", help="使用神经解码器生成（需先训练）")
    parser.add_argument("--max-len", type=int, default=50, help="最大生成长度")
    args = parser.parse_args()

    if not args.eml or not args.query:
        print("用法：")
        print("  模板生成（无需训练）：")
        print("    python token_generator.py --eml data/distilled.eml --concepts data/concepts.json --query '量子计算'")
        print("  训练神经解码器：")
        print("    python token_generator.py --eml data/distilled.eml --concepts data/concepts.json --train")
        print("  神经生成（需先训练）：")
        print("    python token_generator.py --eml data/distilled.eml --model model.pt --query '量子计算' --neural")
        return

    # 加载 EML 图
    from token_bridge import TokenBridge, InferenceEngine
    bridge = TokenBridge(embedding_dim=768)
    bridge.load_eml(args.eml)

    if args.concepts:
        bridge.load_concept_names_from_json(args.concepts)

    engine = InferenceEngine(bridge)

    # 模板生成
    print(f"\n{'='*50}")
    print(f"查询：{args.query}")
    print(f"{'='*50}\n")

    if not args.neural:
        response = generate_response_text(args.query, bridge, engine, use_neural=False)
        print("【模板生成回复】")
        print(response)
    else:
        # 神经生成
        if not _HAS_TORCH:
            print("❌ PyTorch 未安装，无法使用神经解码器。")
            return
        model = PhiToTokenModel(phi_dim=8, hidden_dim=128, vocab_size=2000)
        if args.model and os.path.exists(args.model):
            model.load(args.model)
        elif args.train:
            # 训练
            concept_names = [v['concept'] for v in bridge.loader.vertices]
            model.build_vocab(concept_names, concept_names)
            model.train_on_concepts(concept_names, epochs=100, lr=0.001)
            if args.model:
                model.save(args.model)
        else:
            print("⚠️ 神经模型未训练，使用模板生成")
            response = generate_response_text(args.query, bridge, engine, use_neural=False)
            print("\n【模板生成回复】")
            print(response)
            return

        response = generate_response_text(
            args.query, bridge, engine,
            use_neural=True, neural_model=model, max_len=args.max_len
        )
        print("\n【神经生成回复】")
        print(response)


if __name__ == "__main__":
    main()
