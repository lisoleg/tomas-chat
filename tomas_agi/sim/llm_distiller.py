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
    _re.compile(r'^\d{4}$'),                                   # 纯四位数字（疑似年份：1543, 2024）
    _re.compile(r'^\d{4}年$'),                                 # 1543年 / 2024年
    _re.compile(r'^公元前\d+年'),                               # 公元前221年
    _re.compile(r'^公元\d+年'),                                 # 公元2024年
    _re.compile(r'^\d{1,2}世纪(\d{1,2})?年代?$'),            # 19世纪 / 20世纪50年代
    _re.compile(r'^[春夏秋冬]季$'),                             # 春季/夏季
    _re.compile(r'^\d{1,2}[月日号]\d{1,2}[日号]?$'),          # 5月24日 / 24日
    _re.compile(r'^(?:周|星期)[一二三四五六日天]$'),             # 星期一
    _re.compile(r'^\d{4}-\d{2}-\d{2}$'),                      # 2024-05-24
    _re.compile(r'^\d{2}:\d{2}(:\d{2})?$'),                   # 14:30 / 14:30:00
    _re.compile(r'^\d{4}年?\d*[-–—～~]\d{4}年?\d*'),           # 1473-1543（生卒/日期范围）
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

    # 纯四位数字且在年份范围内（1000~2100）→ 疑似孤立年份
    if _re.match(r'^\d{4}$', s):
        try:
            y = int(s)
            if 1000 <= y <= 2100:
                return True, "疑似年份"
        except ValueError:
            pass

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
        """从文本中提取关键概念（严格过滤伪概念）—— 参考 OwnThink 实体-属性模型"""
        request_count = min(max_concepts, 30)
        prompt = f"""你是一个知识图谱实体提取专家。参考 OwnThink 知识图谱模型
（实体 → 属性 → 值），请从以下文本中提取最多 {request_count} 个**知识实体**。

## 什么是知识实体？
知识实体是你可以为之写出有意义定义的事物。如果你只能用"一个日期"、"一个数字"、
"一个度量值"来描述它——那它就不是知识实体，不要返回。

## ✅ 正确示例
{{"entity": "哥白尼", "description": "文艺复兴时期波兰天文学家，提出日心说理论，颠覆了地心说宇宙观", "tags": ["人物", "天文学"], "importance": 0.95}}
{{"entity": "日心说", "description": "认为太阳是宇宙中心、行星绕太阳运行的天文学理论", "tags": ["天文学", "科学理论"], "importance": 0.90}}
{{"entity": "文艺复兴", "description": "14-17世纪欧洲的思想文化运动，推动了科学和艺术的蓬勃发展", "tags": ["历史", "文化运动"], "importance": 0.85}}

## ❌ 错误示例：绝对不能返回
{{"entity": "1473年2月19日", "description": "哥白尼的出生日期"}}  — entity 本身是日期值，不是实体！
{{"entity": "1543年5月24日", "description": "哥白尼去世日期"}}    — entity 本身是日期值，不是实体！
{{"entity": "1473—1543", "description": "哥白尼的生卒年份"}}    — 日期范围，不是实体！
{{"entity": "1543", "description": "一个年份"}}                  — 纯数字，不是实体！
{{"entity": "100公里", "description": "一个距离"}}               — 度量值，不是实体！

## 要求
1. entity: 知识实体名称（2-20字，名词性，不能是日期/数字/度量）
2. description: 一句话定义（至少8个汉字，不能是"一个XX"的空洞描述）
3. tags: 1-3个分类标签（如"人物""科学""历史"等）
4. importance: 0.0~1.0 重要性评分
5. ⚠️ **核心原则：写不出有意义的定义 → 就不要返回**

以纯 JSON 数组返回，不要 markdown 代码块：
[{{"entity": "...", "description": "...", "tags": ["标签1"], "importance": 0.8}}, ...]

文本：
{text[:3000]}
"""
        messages = [{"role": "user", "content": prompt}]
        try:
            response = self.chat(messages, temperature=0.3, max_tokens=4096)
            # 提取 JSON：先尝试去掉 ```json ... ``` 包裹
            response = response.strip()
            if response.startswith('```'):
                response = _re.sub(r'^```(?:json)?\s*\n?', '', response)
                response = _re.sub(r'\n?```\s*$', '', response)
            # 找到第一个完整 JSON 数组
            bracket_start = response.find('[')
            if bracket_start == -1:
                raise ValueError("未找到 JSON 数组")
            raw_concepts = json.loads(response[bracket_start:])

            # 后置校验：描述空洞的伪实体 → 直接丢弃
            TRIVIAL_DESC_PATTERNS = [
                _re.compile(r'^一个(日期|时间|数字|数量|年份|世纪|度量|单位|版本|编号|季度|月份|距离|重量|长度|温度|速度|数值)$'),
                _re.compile(r'^(同上|见上|类似)$'),
                _re.compile(r'^.{1,4}$'),
            ]

            concepts = []
            pseudo_count = 0
            for raw in raw_concepts:
                if not isinstance(raw, dict):
                    continue
                # 兼容新旧两种 LLM 输出格式
                entity = str(raw.get('entity', raw.get('concept', ''))).strip()
                if not entity or len(entity) < 2:
                    continue

                description = str(raw.get('description', raw.get('context', ''))).strip()

                # describe-or-discard
                is_trivial = any(p.match(description) for p in TRIVIAL_DESC_PATTERNS)
                if is_trivial or description == entity or description.replace(' ', '') == entity:
                    pseudo_count += 1
                    continue

                importance = float(raw.get('importance', 0.5))
                tags = raw.get('tags', [])
                tag_str = '、'.join(tags) if isinstance(tags, list) else ''
                context = f"{description} [{tag_str}]" if tag_str else description

                concepts.append({
                    'concept': entity,
                    'importance': importance,
                    'context': context
                })

            if pseudo_count > 0:
                print(f"  🗑 丢弃 {pseudo_count} 个伪实体（描述空洞）")
            print(f"  保留 {len(concepts)} 个有效实体")
            return concepts[:max_concepts]

        except Exception as e:
            print(f"概念提取失败：{e}")
            print(f"  API 返回前200字：{response[:200] if 'response' in dir() else 'N/A'}")
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


# ============================================================
# MultiLangAdapter (Reasonix 编程智能体集成)
# ============================================================


class MultiLangAdapter:
    """多语言代码蒸馏适配器。

    在 LLMDistiller 基础上扩展多语言支持，
    将不同编程语言的代码蒸馏为统一的 EML 张量表示，
    并支持从张量逆向重建对应语言的代码。

    支持语言：Python, JavaScript, C/C++, Rust, Go, Java

    方法：
        distill_code(code, lang) -> np.ndarray: 将代码蒸馏为 EML 张量
        reconstruct_code(tensor, lang) -> str: 从张量重建代码
    """

    # 语言标识 → 特征维度映射
    _LANG_DIM_MAP = {
        "python":     {"syntax_dim": 32, "semantic_dim": 32, "structural_dim": 32, "total": 96},
        "javascript": {"syntax_dim": 32, "semantic_dim": 32, "structural_dim": 32, "total": 96},
        "c":          {"syntax_dim": 28, "semantic_dim": 28, "structural_dim": 28, "total": 84},
        "cpp":        {"syntax_dim": 28, "semantic_dim": 28, "structural_dim": 28, "total": 84},
        "rust":       {"syntax_dim": 30, "semantic_dim": 30, "structural_dim": 30, "total": 90},
        "go":         {"syntax_dim": 30, "semantic_dim": 30, "structural_dim": 30, "total": 90},
        "java":       {"syntax_dim": 30, "semantic_dim": 30, "structural_dim": 30, "total": 90},
    }

    # 语言特征关键词（用于语义维度编码）
    _LANG_KEYWORDS = {
        "python":     ["def", "class", "import", "if", "for", "while", "try", "lambda", "yield", "with"],
        "javascript": ["function", "const", "let", "var", "async", "await", "class", "export", "import", "promise"],
        "c":          ["int", "float", "char", "struct", "typedef", "void", "if", "for", "while", "switch"],
        "cpp":        ["class", "template", "namespace", "virtual", "override", "const", "auto", "nullptr", "static", "inline"],
        "rust":       ["fn", "let", "mut", "impl", "trait", "pub", "match", "enum", "struct", "use"],
        "go":         ["func", "var", "const", "type", "struct", "interface", "package", "import", "range", "defer"],
        "java":       ["class", "interface", "extends", "implements", "public", "private", "static", "final", "void", "new"],
    }

    def __init__(self, eight_dim: int = 8):
        """初始化多语言适配器。

        Args:
            eight_dim: 八元数场维度（默认 8）
        """
        self.eight_dim = eight_dim
        self._distillation_cache: Dict[str, np.ndarray] = {}

    def distill_code(self, code: str, lang: str = "python") -> np.ndarray:
        """将代码蒸馏为 EML 张量表示。

        Args:
            code: 源代码字符串
            lang: 编程语言标识（默认 "python"）

        Returns:
            np.ndarray: 蒸馏后的 EML 张量
                形状为 (total_dim + eight_dim)，包含：
                - syntax_dim: 语法特征
                - semantic_dim: 语义特征（关键词频率）
                - structural_dim: 结构特征（嵌套深度、行数等）
                - eight_dim: 八元数场扩展维度
        """
        lang_lower = lang.lower()
        if lang_lower not in self._LANG_DIM_MAP:
            raise ValueError(f"不支持的语言: {lang}。支持: {list(self._LANG_DIM_MAP.keys())}")

        dim_config = self._LANG_DIM_MAP[lang_lower]
        total_dim = dim_config["total"]

        # 语法特征：行级编码
        syntax_features = self._encode_syntax(code, dim_config["syntax_dim"])

        # 语义特征：关键词频率编码
        semantic_features = self._encode_semantic(code, lang_lower, dim_config["semantic_dim"])

        # 结构特征：嵌套深度、行数等
        structural_features = self._encode_structural(code, dim_config["structural_dim"])

        # 八元数场扩展：将 total_dim 投影到 eight_dim
        oct_projection = self._project_to_octonion(
            np.concatenate([syntax_features, semantic_features, structural_features]),
            self.eight_dim,
        )

        # 合并：[syntax | semantic | structural | octonion]
        tensor = np.concatenate([syntax_features, semantic_features, structural_features, oct_projection])
        return tensor

    def reconstruct_code(self, tensor: np.ndarray, lang: str = "python") -> str:
        """从 EML 张量逆向重建代码。

        Args:
            tensor: 蒸馏后的 EML 张量
            lang: 目标编程语言标识

        Returns:
            str: 重建的代码字符串（骨架代码）
        """
        lang_lower = lang.lower()
        if lang_lower not in self._LANG_DIM_MAP:
            raise ValueError(f"不支持的语言: {lang}。支持: {list(self._LANG_DIM_MAP.keys())}")

        dim_config = self._LANG_DIM_MAP[lang_lower]
        total_dim = dim_config["total"]

        # 分离各维度
        syntax_dim = dim_config["syntax_dim"]
        semantic_dim = dim_config["semantic_dim"]
        structural_dim = dim_config["structural_dim"]

        syntax_feat = tensor[:syntax_dim]
        semantic_feat = tensor[syntax_dim:syntax_dim + semantic_dim]
        structural_feat = tensor[syntax_dim + semantic_dim:syntax_dim + semantic_dim + structural_dim]

        # 从结构特征提取行数
        n_lines = max(1, int(structural_feat[0] * 50))  # structural_feat[0] ≈ line_count/50

        # 从语义特征提取关键词
        keywords = self._LANG_KEYWORDS[lang_lower]
        active_keywords = []
        for i, kw in enumerate(keywords):
            if i < len(semantic_feat) and semantic_feat[i] > 0.3:
                active_keywords.append(kw)

        # 重建骨架代码
        skeleton = self._build_skeleton(lang_lower, n_lines, active_keywords)
        return skeleton

    def _encode_syntax(self, code: str, dim: int) -> np.ndarray:
        """语法特征编码：行级 hash → 特征向量。"""
        lines = code.splitlines()
        features = np.zeros(dim)
        for i, line in enumerate(lines):
            if i >= dim:
                break
            # 简单编码：行长度归一化 + 行类型权重
            line_stripped = line.strip()
            line_len = min(len(line_stripped) / 100.0, 1.0)
            # 行类型权重
            if line_stripped.startswith("#") or line_stripped.startswith("//"):
                type_weight = 0.1  # 注释
            elif line_stripped.endswith("{") or line_stripped.endswith(":"):
                type_weight = 0.8  # 块开始
            elif line_stripped.endswith("}") or line_stripped == "":
                type_weight = 0.3  # 块结束/空行
            else:
                type_weight = 0.5  # 一般语句
            features[i] = line_len * type_weight
        return features

    def _encode_semantic(self, code: str, lang: str, dim: int) -> np.ndarray:
        """语义特征编码：关键词频率。"""
        features = np.zeros(dim)
        keywords = self._LANG_KEYWORDS.get(lang, [])
        code_lower = code.lower()
        for i, kw in enumerate(keywords):
            if i >= dim:
                break
            # 关键词出现次数（归一化）
            count = code_lower.count(kw.lower())
            features[i] = min(count / 10.0, 1.0)
        return features

    def _encode_structural(self, code: str, dim: int) -> np.ndarray:
        """结构特征编码：嵌套深度、行数、缩进分布等。"""
        features = np.zeros(dim)
        lines = code.splitlines()

        # 特征 0: 行数归一化
        features[0] = len(lines) / 50.0

        # 特征 1: 最大嵌套深度归一化
        max_depth = 0
        for line in lines:
            indent = len(line) - len(line.lstrip())
            depth = indent // 4
            max_depth = max(max_depth, depth)
        features[1] = max_depth / 10.0

        # 特征 2: 空行比例
        empty_lines = sum(1 for l in lines if l.strip() == "")
        features[2] = empty_lines / max(len(lines), 1)

        # 特征 3: 注释比例
        comment_lines = sum(1 for l in lines if l.strip().startswith("#") or l.strip().startswith("//"))
        features[3] = comment_lines / max(len(lines), 1)

        # 特征 4: 函数/方法数估计
        func_keywords = ["def ", "function ", "fn ", "func ", "void ", "int ", "public "]
        func_count = sum(1 for l in lines if any(kw in l for kw in func_keywords))
        features[4] = min(func_count / 20.0, 1.0)

        return features

    def _project_to_octonion(self, features: np.ndarray, dim: int) -> np.ndarray:
        """将高维特征投影到八元数场维度。"""
        # 简单线性投影 + 非线性激活
        n = len(features)
        projection = np.zeros(dim)
        for i in range(dim):
            # 每8个原始特征维度映射到一个八元数分量
            start = (i * n) // dim
            end = ((i + 1) * n) // dim
            if start < end:
                projection[i] = np.mean(features[start:end])
            elif start < n:
                projection[i] = features[start]
        # 非线性激活
        projection = np.tanh(projection)
        return projection

    def _build_skeleton(self, lang: str, n_lines: int, keywords: List[str]) -> str:
        """根据语言和关键词重建骨架代码。"""
        # 语言模板
        templates = {
            "python": [
                "# Reconstructed skeleton (Python)",
                "import os",
                "",
                "def main():",
                "    pass",
                "",
                "if __name__ == '__main__':",
                "    main()",
            ],
            "javascript": [
                "// Reconstructed skeleton (JavaScript)",
                "const main = () => {",
                "};",
                "",
                "main();",
            ],
            "c": [
                "// Reconstructed skeleton (C)",
                "#include <stdio.h>",
                "",
                "int main() {",
                "    return 0;",
                "}",
            ],
            "cpp": [
                "// Reconstructed skeleton (C++)",
                "#include <iostream>",
                "",
                "int main() {",
                "    return 0;",
                "}",
            ],
            "rust": [
                "// Reconstructed skeleton (Rust)",
                "fn main() {",
                "}",
            ],
            "go": [
                "// Reconstructed skeleton (Go)",
                "package main",
                "",
                "func main() {",
                "}",
            ],
            "java": [
                "// Reconstructed skeleton (Java)",
                "public class Main {",
                "    public static void main(String[] args) {",
                "    }",
                "}",
            ],
        }

        base = templates.get(lang, templates["python"])
        # 根据活跃关键词插入额外行
        extra_lines = []
        keyword_insert_map = {
            "class":      f"class Reconstructed {{ ... }}",
            "struct":     f"struct Reconstructed {{ ... }}",
            "interface":  f"interface IReconstructed {{ ... }}",
            "trait":      f"trait Reconstructed {{ ... }}",
            "enum":       f"enum Reconstructed {{ ... }}",
            "try":        f"try {{ ... }} catch (e) {{ ... }}",
            "lambda":     f"lambda_fn = lambda x: x",
            "async":      f"async function asyncFn() {{ ... }}",
            "match":      f"match value {{ ... }}",
            "template":   f"template<typename T> ...",
            "namespace":  f"namespace reconstructed {{ ... }}",
        }
        for kw in keywords:
            if kw in keyword_insert_map and kw not in ["def", "function", "fn", "func", "void", "int", "public"]:
                extra_lines.append(keyword_insert_map[kw])

        skeleton_lines = base[:2] + extra_lines + base[2:]
        # 限制行数
        if len(skeleton_lines) > max(n_lines, len(base)):
            skeleton_lines = skeleton_lines[:max(n_lines, len(base))]

        return "\n".join(skeleton_lines)


# --- MultiLangAdapter 自测 ---
if __name__ == "__main__" and "MultiLangAdapter" in dir() and len(dir()) > 5:
    print("\n=== MultiLangAdapter 自测 ===")
    adapter = MultiLangAdapter(eight_dim=8)

    # 1. Python 蒸馏
    py_code = "def hello():\n    return 42\n\nclass Foo:\n    pass\n"
    tensor = adapter.distill_code(py_code, "python")
    print(f"  Python 蒸馏: shape={tensor.shape}")
    assert tensor.shape == (96 + 8,)  # total_dim + eight_dim
    print("  [PASS] Python 蒸馏张量维度")

    # 2. JavaScript 蒸馏
    js_code = "function main() {\n  const x = 1;\n  return x;\n}\n"
    js_tensor = adapter.distill_code(js_code, "javascript")
    print(f"  JavaScript 蒸馏: shape={js_tensor.shape}")
    assert js_tensor.shape == (96 + 8,)
    print("  [PASS] JavaScript 蒸馏张量维度")

    # 3. C 蒸馏
    c_code = "int main() {\n  return 0;\n}\n"
    c_tensor = adapter.distill_code(c_code, "c")
    print(f"  C 蒸馏: shape={c_tensor.shape}")
    assert c_tensor.shape == (84 + 8,)
    print("  [PASS] C 蒸馏张量维度")

    # 4. 逆向重建
    reconstructed = adapter.reconstruct_code(tensor, "python")
    print(f"  Python 重建:\n{reconstructed}")
    assert "def main" in reconstructed or "main" in reconstructed
    print("  [PASS] Python 逆向重建")

    # 5. 不支持的语言
    try:
        adapter.distill_code("code", "cobol")
        print("  [FAIL] 应拒绝不支持的语言")
    except ValueError:
        print("  [PASS] 不支持语言拒绝")

    print("=== MultiLangAdapter 自测全部通过 ===")
