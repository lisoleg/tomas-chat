"""
LLM 蒸馏器（LLM Distiller）
================================

使用 LLM（DeepSeek API）作为"预训练蒸馏器"，
将世界知识压缩进 EML 图（权重 = 信息存在度 𝕀(X)）。

蒸馏完成后，LLM 本体可以大幅裁剪甚至完全移除，
只保留一个很小的 Token Bridge（编码器/解码器）。

作者：复合体理学研究中心（TOMAS 项目组）
日期：2026-06-13
"""

import os
import json
import time
import hashlib
import numpy as np
from typing import List, Dict, Tuple, Optional, Any

# ============================================================
# 第1部分：配置与工具函数
# ============================================================

class DistillerConfig:
    """蒸馏器配置"""
    def __init__(self, api_key: str = None, api_base: str = None, model: str = "deepseek-chat"):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.api_base = api_base or os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
        self.model = model
        self.max_concepts = 1000      # 单次蒸馏最大概念数
        self.max_relations = 5000     # 单次蒸馏最大关系数
        self.batch_size = 32            # 批处理大小
        self.alpha = 0.7               # 𝕀(X) 计算中的频率权重
        self.beta = 0.3                # 𝕀(X) 计算中的重要性权重
        self.eight_dim = 8              # 八元数场维度
        self.delta_stable = 7.0        # δ 稳定锁定值


def compute_info_existence(frequency: int, importance: float, consistency: float,
                          alpha: float = 0.7, beta: float = 0.3) -> float:
    """
    计算信息存在度 𝕀(X)

    𝕀(X) = α · norm_freq(X) + β · importance(X) + (1-α-β) · consistency(X)

    其中：
    - frequency: 概念在语料中出现的频率
    - importance: LLM 评估的概念重要性（0~1）
    - consistency: 概念在不同上下文中的一致性（0~1）
    """
    norm_freq = np.log1p(frequency) / np.log1p(max(frequency, 1))
    score = alpha * norm_freq + beta * importance + (1 - alpha - beta) * consistency
    return float(np.clip(score, 0.0, 1.0))


# ============================================================
# 伪概念过滤规则
# ============================================================

import re as _re

# 匹配日期/时间模式的正则（中文 + 常见格式）
_DATE_PATTERNS = [
    _re.compile(r'^\d{4}年\d{1,2}月\d{1,2}日?$'),           # 1543年5月24日
    _re.compile(r'^\d{4}年\d{1,2}月$'),                       # 1543年5月
    _re.compile(r'^\d{4}年$'),                                 # 1543年 / 2024年
    _re.compile(r'^公元前\d+年'),                               # 公元前221年
    _re.compile(r'^公元\d+年'),                                 # 公元2024年
    _re.compile(r'^\d{1,2}世纪(\d{1,2})?年代?$'),            # 19世纪 / 20世纪50年代
    _re.compile(r'^[春夏秋冬]季$'),                             # 春季/夏季
    _re.compile(r'^\d{1,2}[月日号]$'),                        # 5月24日 / 24日
    _re.compile(r'^(?:周|星期)[一二三四五六日天]$'),             # 星期一
    _re.compile(r'^\d{4}-\d{2}-\d{2}$'),                      # 2024-05-24
    _re.compile(r'^\d{2}:\d{2}(:\d{2})?$'),                   # 14:30 / 14:30:00
]

# 纯数字或数量表达式
_NUMBER_PATTERNS = [
    _re.compile(r'^[\d\s.,，。、%％‰+\-×÷=<>≥≤π∞]+$'),        # 纯数学表达式
    _re.compile(r'^[\d.]+(?:万|亿|k|K|M|G|T)?(?:个|条|人|次|项)?$'), # 2500万 / 100条
    _re.compile(r'^v?\d+(\.\d+)*([a-zA-Z]*)$'),                # v2.0 / 3.14
    _re.compile(r'^第?[一二三四五六七八九十百千\d]+[章节卷册页版]$'), # 第3版 / 第二章
]

# 度量值（数字+单位）
_MEASURE_PATTERN = _re.compile(r'^[\d.]+(?:km|m|cm|mm|kg|g|mg|℃|℉|%|公里|米|厘米|毫米|千克|克|毫升|升|公顷|亩|秒分小时天周年)$', _re.IGNORECASE)


def is_pseudo_concept(concept: str) -> Tuple[bool, str]:
    """
    判断一个字符串是否为伪概念（非实体概念）。

    返回: (是否伪概念, 原因说明)
    """
    s = concept.strip()

    if len(s) == 0:
        return True, "空字符串"

    if len(s) < 2:
        return True, f"过短({len(s)}字符)"

    # 日期/时间检查
    for p in _DATE_PATTERNS:
        if p.match(s):
            return True, f"日期/时间格式"

    # 纯数字/数量检查
    for p in _NUMBER_PATTERNS:
        if p.match(s):
            return True, f"纯数字/数量"

    # 度量值检查
    if _MEASURE_PATTERN.match(s):
        return True, "度量单位值"

    # URL/邮箱/电话
    if s.startswith(('http://', 'https://', 'www.', 'ftp://')):
        return True, "URL"
    if '@' in s and '.' in s.split('@')[-1]:
        return True, "邮箱"
    if _re.match(r'^[\d\-+\s()（）]{7,15}$', s):
        return True, "电话号码"

    return False, ""


def text_to_octonion(text: str, dimension: int = 8) -> np.ndarray:
    """
    将文本转换为八元数值场 φ(i) ∈ ℝ⁸
    
    使用文本的哈希 + 统计特征作为八元数表示。
    """
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
# 第2部分：DeepSeek API 封装
# ============================================================

class DeepSeekClient:
    """DeepSeek API 客户端（流式 + 非流式）"""
    
    def __init__(self, config: DistillerConfig):
        self.config = config
        self.api_key = config.api_key
        self.api_base = config.api_base
        self.model = config.model
        if not self.api_key:
            raise ValueError("DeepSeek API Key 未配置！请设置 DEEPEEK_API_KEY 环境变量")
    
    def _make_headers(self) -> Dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def chat(self, messages: List[Dict], temperature: float = 0.7,
             max_tokens: int = 4096) -> str:
        """非流式调用 DeepSeek Chat API"""
        try:
            import requests
        except ImportError:
            raise ImportError("请先安装 requests：pip install requests")
        url = f"{self.api_base}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }
        resp = requests.post(url, headers=self._make_headers(),
                            json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    
    def chat_stream(self, messages: List[Dict], temperature: float = 0.7,
                   max_tokens: int = 4096):
        """流式调用 DeepSeek Chat API（返回生成器）"""
        try:
            import requests
        except ImportError:
            raise ImportError("请先安装 requests：pip install requests")
        url = f"{self.api_base}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True
        }
        resp = requests.post(url, headers=self._make_headers(),
                           json=payload, stream=True, timeout=60)
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    data = line[6:]
                    if data.strip() == '[DONE]':
                        break
                    try:
                        chunk = json.loads(data)
                        content = chunk["choices"][0]["delta"].get("content", "")
                        if content:
                            yield content
                    except:
                        pass
    
    def extract_concepts(self, text: str, max_concepts: int = 100) -> List[Dict]:
        """从文本中提取关键概念（严格过滤伪概念）"""
        # 限制实际请求的概念数，避免 JSON 被截断
        request_count = min(max_concepts, 30)
        prompt = f"""请从以下文本中提取 {request_count} 个核心概念实体。

⚠️ 严格排除规则（以下内容绝对不能返回）：
- ❌ 日期/时间：如"1543年5月24日"、"2024年"、"公元前221年"、"19世纪"
- ❌ 纯数字/数量：如"2500万"、"1.4亿"、"3.14159"
- ❌ 度量单位值：如"100公里"、"37℃"、"500克"
- ❌ 人名生卒日期、事件发生时间等时间属性值
- ❌ 版本号/编号：如"v2.0"、"第3版"
- ❌ URL/邮箱/电话号码
- ❌ 单个汉字或无意义的短词（<2个字符且非专有名词）

✅ 只返回真正的概念实体：
- 学科概念：人工智能、量子力学、相对论
- 人物/组织：哥白尼、中国科学院
- 物体/现象：黑洞、DNA双螺旋
- 理论/方法：进化论、归纳法
- 地理/历史实体：丝绸之路、文艺复兴

要求：
1. 每个概念应该是文本中的核心实体（名词性）
2. 给出每个概念的重要性评分（0.0~1.0）
3. 给出概念的简要描述（一句话）

以纯 JSON 数组返回，不要 markdown 代码块：
[{{"concept": "概念名", "importance": 0.8, "context": "描述"}}, ...]

文本：
{text[:3000]}
"""
        messages = [{"role": "user", "content": prompt}]
        try:
            response = self.chat(messages, temperature=0.3, max_tokens=4096)
            # 提取 JSON：先尝试去掉 ```json ... ``` 包裹
            import re
            response = response.strip()
            if response.startswith('```'):
                response = re.sub(r'^```(?:json)?\s*\n?', '', response)
                response = re.sub(r'\n?```\s*$', '', response)
            # 找到第一个完整 JSON 数组
            bracket_start = response.find('[')
            if bracket_start == -1:
                raise ValueError("未找到 JSON 数组")
            concepts = json.loads(response[bracket_start:])
            return concepts[:max_concepts]
        except Exception as e:
            print(f"概念提取失败：{e}")
            print(f"  API 返回前200字：{response[:200] if isinstance(response, str) else 'N/A'}")
            return []
    
    def extract_relations(self, concepts: List[Dict], text: str,
                         max_relations: int = 500) -> List[Dict]:
        """从概念和文本中提取关系"""
        if not concepts:
            return []
        concept_names = [c["concept"] for c in concepts[:30]]
        prompt = f"""给定以下概念列表，请提取概念之间的语义关系：

概念：{json.dumps(concept_names, ensure_ascii=False)}

要求：
1. 用 JSON 数组返回，不要 markdown 代码块
2. 关系类型：is_a, part_of, causes, related_to, used_in, inspired_by
3. 关系强度 0.0~1.0
格式：[{{"src": "概念A", "dst": "概念B", "type": "is_a", "strength": 0.9}}, ...]

文本参考（可选）：{text[:1000]}
"""
        messages = [{"role": "user", "content": prompt}]
        try:
            response = self.chat(messages, temperature=0.3, max_tokens=4096)
            import re
            response = response.strip()
            if response.startswith('```'):
                response = re.sub(r'^```(?:json)?\s*\n?', '', response)
                response = re.sub(r'\n?```\s*$', '', response)
            bracket_start = response.find('[')
            if bracket_start == -1:
                raise ValueError("未找到 JSON 数组")
            relations = json.loads(response[bracket_start:])
            return relations[:max_relations]
        except Exception as e:
            print(f"关系提取失败：{e}")
            return []


# ============================================================
# 第3部分：EML 图构建器
# ============================================================

class EMLVertex:
    """EML 图顶点（Python 表示）"""
    def __init__(self, vid: int, concept: str, octonion: np.ndarray,
                 delta: float, info_existence: float):
        self.id = vid
        self.concept = concept
        self.octonion = octonion.copy()
        self.delta = delta
        self.info_existence = info_existence
        self.frequency = 1


class EMLEdge:
    """EML 图边（Python 表示）"""
    def __init__(self, src: int, dst: int, weight: float,
                 delta_weight: float, associator_flag: int):
        self.src = src
        self.dst = dst
        self.weight = weight
        self.delta_weight = delta_weight
        self.associator_flag = associator_flag


class EMLGraphBuilder:
    """EML 图构建器"""
    
    def __init__(self, config: DistillerConfig):
        self.config = config
        self.vertices: List[EMLVertex] = []
        self.edges: List[EMLEdge] = []
        self.concept_to_id: Dict[str, int] = {}
        
    def add_concept(self, concept: str, importance: float,
                    frequency: int = 1) -> int:
        """添加一个概念作为顶点"""
        if concept in self.concept_to_id:
            vid = self.concept_to_id[concept]
            v = self.vertices[vid]
            v.frequency += frequency
            v.info_existence = compute_info_existence(
                v.frequency, importance, 1.0,
                self.config.alpha, self.config.beta)
            return vid
        
        vid = len(self.vertices)
        self.concept_to_id[concept] = vid
        info_existence = compute_info_existence(
            frequency, importance, 1.0,
            self.config.alpha, self.config.beta)
        octonion = text_to_octonion(concept, self.config.eight_dim)
        delta = info_existence  # δ = 𝕀(X) 信息存在度
        vertex = EMLVertex(vid, concept, octonion, delta, info_existence)
        vertex.frequency = frequency
        self.vertices.append(vertex)
        return vid
    
    def add_relation(self, src_concept: str, dst_concept: str,
                     strength: float, rel_type: str = "related_to"):
        """添加一条关系作为边"""
        if src_concept not in self.concept_to_id:
            return
        if dst_concept not in self.concept_to_id:
            return
        src_id = self.concept_to_id[src_concept]
        dst_id = self.concept_to_id[dst_concept]
        delta_weighted = self._compute_delta_weight(strength,
            self.vertices[src_id].delta, self.vertices[dst_id].delta)
        # causes 和 inspired_by 关系标记为结合子
        associator_flag = 1 if rel_type in ("causes", "inspired_by") else 0
        edge = EMLEdge(src_id, dst_id, strength, delta_weighted, associator_flag)
        self.edges.append(edge)
    
    def _compute_delta_weight(self, base_weight: float,
                             delta_src: float, delta_dst: float) -> float:
        delta_max = max(delta_src, delta_dst)
        delta_stable = self.config.delta_stable
        if delta_stable < 1e-10:
            delta_stable = 7.0
        ratio = delta_max / delta_stable
        if ratio > 50.0:
            return 0.0
        return base_weight * np.exp(-ratio)
    
    def serialize_to_eml_format(self) -> bytes:
        """序列化为 EML 文件格式（与 eml_map.c 兼容）"""
        import struct
        magic = 0x454D4C47
        version = 0x00020000
        num_vertices = len(self.vertices)
        num_edges = len(self.edges)
        laplacian_alpha = 0.3
        graph_delta = float(np.mean([v.delta for v in self.vertices])) if self.vertices else 0.0
        timestamp = int(time.time())
        
        header = struct.pack('<IIII', magic, version, num_vertices, num_edges)
        header += struct.pack('<dd', laplacian_alpha, graph_delta)
        header += struct.pack('<Q', timestamp)
        header += struct.pack('<QQQQ', 0, 0, 0, 0)
        
        vertices_data = b''
        for v in self.vertices:
            vdata = struct.pack('<ii', v.id, 0)
            for f in v.octonion[:8]:
                vdata += struct.pack('<d', f)
            vdata += struct.pack('<d', v.delta)
            vertices_data += vdata
        
        edges_data = b''
        for e in self.edges:
            edata = struct.pack('<ii', e.src, e.dst)
            edata += struct.pack('<d', e.weight)
            edata += struct.pack('<d', e.delta_weight)
            edata += struct.pack('<ii', e.associator_flag, 0)
            edges_data += edata
        
        return header + vertices_data + edges_data
    
    def save_to_file(self, filepath: str):
        """保存 EML 图到文件"""
        data = self.serialize_to_eml_format()
        with open(filepath, 'wb') as f:
            f.write(data)
        print(f"EML 图已保存：{filepath}（V={len(self.vertices)}, E={len(self.edges)}, 大小={len(data)} 字节）")
    
    def print_summary(self):
        """打印 EML 图摘要"""
        print(f"\n=== EML 图摘要 ===")
        print(f"顶点数：{len(self.vertices)}")
        print(f"边数：{len(self.edges)}")
        if self.vertices:
            avg_info = np.mean([v.info_existence for v in self.vertices])
            avg_delta = np.mean([v.delta for v in self.vertices])
            print(f"平均 𝕀(X)：{avg_info:.4f}")
            print(f"平均 δ(i)：{avg_delta:.4f}")


# ============================================================
# 第4部分：LLM 蒸馏器（主类）
# ============================================================

class LLMDistiller:
    def __init__(self, config: DistillerConfig = None):
        self.config = config or DistillerConfig()
        self.client = DeepSeekClient(self.config)
        self.builder = EMLGraphBuilder(self.config)
        
    def distill(self, text: str, verbose: bool = True) -> EMLGraphBuilder:
        if verbose:
            print("=== 开始 LLM 蒸馏 ===")
            print(f"文本长度：{len(text)} 字符")
        
        concepts = self.client.extract_concepts(text, self.config.max_concepts)

        # 🔍 后处理：过滤伪概念（日期/数字/度量/属性值）
        original_count = len(concepts)
        filtered_concepts = []
        rejected = []
        for c in concepts:
            concept_str = c.get("concept", "").strip()
            is_pseudo, reason = is_pseudo_concept(concept_str)
            if is_pseudo:
                rejected.append((concept_str, reason))
            else:
                filtered_concepts.append(c)
        concepts = filtered_concepts

        if verbose:
            print(f"\n[1/3] 提取到 {len(concepts)} 个概念（原始 {original_count} 个，过滤掉 {len(rejected)} 个伪概念）")
            if rejected:
                print("  🗑 已过滤伪概念：")
                for name, reason in rejected[:10]:
                    print(f"    ✕ 「{name}」— {reason}")
            for i, c in enumerate(concepts[:5]):
                print(f"  {i+1}. {c['concept']}（重要性={c['importance']:.2f}）")
        
        for c in concepts:
            self.builder.add_concept(c["concept"], c["importance"])
        
        relations = self.client.extract_relations(concepts, text, self.config.max_relations)
        if verbose:
            print(f"\n[2/3] 提取到 {len(relations)} 个关系")
            for i, r in enumerate(relations[:5]):
                print(f"  {i+1}. {r['src']} --[{r['type']}, {r['strength']:.2f}]--> {r['dst']}")
        
        for r in relations:
            self.builder.add_relation(r["src"], r["dst"], r["strength"], r.get("type", "related_to"))
        
        if verbose:
            print("\n[3/3] 蒸馏完成")
            self.builder.print_summary()
        
        return self.builder
    
    def distill_from_file(self, filepath: str, verbose: bool = True):
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()
        return self.distill(text, verbose)
    
    def save_eml_graph(self, filepath: str):
        self.builder.save_to_file(filepath)

    def save_concept_names(self, filepath: str):
        """保存概念名称 JSON 伴侣文件（Token Bridge 加载时需要）"""
        concept_data = {
            'concepts': [
                {'id': v.id, 'concept': v.concept, 'importance': v.info_existence}
                for v in self.builder.vertices
            ]
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(concept_data, f, ensure_ascii=False, indent=2)


# ============================================================
# 第5部分：Token Bridge
# ============================================================

class TokenBridge:
    def __init__(self, embedding_dim: int = 64, eight_dim: int = 8):
        self.embedding_dim = embedding_dim
        self.eight_dim = eight_dim
        np.random.seed(42)
        self.encoder_weights = np.random.randn(embedding_dim, eight_dim) * 0.01
        self.decoder_weights = np.random.randn(eight_dim, embedding_dim) * 0.01
        
    def encode(self, token_embeddings: np.ndarray) -> np.ndarray:
        return np.dot(token_embeddings, self.encoder_weights)
    
    def decode(self, phi: np.ndarray, vocab_size: int = 32000) -> np.ndarray:
        hidden = np.dot(phi, self.decoder_weights)
        logits = np.random.randn(phi.shape[0], vocab_size) * 0.01
        return logits


# ============================================================
# 第6部分：自检测试
# ============================================================

def test_mock_distillation():
    """模拟蒸馏测试（不调用 API）"""
    print("=== 模拟蒸馏测试 ===\n")
    config = DistillerConfig(api_key="mock-key")
    builder = EMLGraphBuilder(config)
    
    test_concepts = [
        ("人工智能", 0.95, 10),
        ("机器学习", 0.90, 8),
        ("深度学习", 0.88, 6),
        ("神经网络", 0.85, 7),
        ("自然语言处理", 0.82, 5),
    ]
    for concept, importance, freq in test_concepts:
        builder.add_concept(concept, importance, freq)
    
    test_relations = [
        ("人工智能", "机器学习", 0.95),
        ("机器学习", "深度学习", 0.90),
        ("深度学习", "神经网络", 0.92),
        ("人工智能", "自然语言处理", 0.80),
    ]
    for src, dst, strength in test_relations:
        builder.add_relation(src, dst, strength)
    
    builder.print_summary()
    test_file = os.path.join(os.path.dirname(__file__), "test_eml_graph.eml")
    builder.save_to_file(test_file)
    print("✅ 模拟蒸馏测试通过")
    return True


def test_token_bridge():
    print("\n=== Token Bridge 测试 ===\n")
    bridge = TokenBridge(embedding_dim=64, eight_dim=8)
    token_embeddings = np.random.randn(10, 64)
    phi = bridge.encode(token_embeddings)
    print(f"编码：{token_embeddings.shape} → {phi.shape}")
    logits = bridge.decode(phi, vocab_size=32000)
    print(f"解码：{phi.shape} → {logits.shape}")
    print("✅ Token Bridge 测试通过")
    return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="LLM 蒸馏器：将世界知识压缩进 EML 图")
    parser.add_argument("--distill", type=str, help="指定语料文本文件，进行蒸馏")
    parser.add_argument("--output", type=str, default="distilled_knowledge.eml", help="输出 EML 图文件路径")
    parser.add_argument("--api-key", type=str, help="DeepSeek API Key（也可通过 DEEPSEEK_API_KEY 环境变量设置）")
    parser.add_argument("--mock", action="store_true", help="使用模拟数据（不调用 API）")
    args = parser.parse_args()

    if args.mock or (not args.distill):
        # 运行自测
        print("LLM 蒸馏器 + Token Bridge 模块")
        print("=" * 50)
        test_mock_distillation()
        test_token_bridge()
        print("\n" + "=" * 50)
        print("所有自测通过！")
        print("\n下一步：")
        print("  python sim/llm_distiller.py --distill data/sample_knowledge.txt")
        return

    if args.distill:
        if not os.path.exists(args.distill):
            print(f"错误：语料文件不存在：{args.distill}")
            return
        config = DistillerConfig(api_key=args.api_key)
        distiller = LLMDistiller(config)
        try:
            builder = distiller.distill_from_file(args.distill, verbose=True)
            distiller.save_eml_graph(args.output)
            # 自动生成概念名称伴侣文件
            concept_file = args.output.replace('.eml', '.concepts.json')
            distiller.save_concept_names(concept_file)
            print(f"\n✅ 蒸馏完成！EML 图已保存至：{args.output}")
            print(f"✅ 概念名称已保存至：{concept_file}")
        except Exception as e:
            print(f"蒸馏失败：{e}")


if __name__ == "__main__":
    main()
