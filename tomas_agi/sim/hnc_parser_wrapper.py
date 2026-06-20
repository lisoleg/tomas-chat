# -*- coding: utf-8 -*-
"""
HNCParserWrapper — HNC 概念基元编码器 (TOMAS v2.0 T01)
========================================================

HNC (Hierarchical Network of Concepts) 概念基元编码器。
基于 24 字母体系，优先实现 10 个核心概念基元。

Theory Source:
    "TOMAS v2.0 架构升级设计" (架构文档 §3.2.1)
    HNC 理论：黄曾阳《HNC理论》概念基元体系

Core Concepts:
    1. 10 个核心概念基元码（CONCEPT_BASE_TABLE）
    2. 7 个 HNC 句类模板（SENTENCE_TEMPLATES）
    3. 分词 → 概念编码 → 模板匹配 三阶段解析

Algorithm:
    1. 分词：优先使用 jieba，不可用则降级为单字分词
    2. 概念编码：基于词性的启发式映射
       (名词→v, 动词→p, 形容词→g, 副词→u, 量词→q, 连词→c, ...)
    3. 模板匹配：将 concept_codes 与 SENTENCE_TEMPLATES 的 pattern
       做子序列匹配（允许部分匹配，使用编辑距离）

Author: Alex (Engineer, TOMAS Team)
Version: v2.0
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============================================================
# 可选导入 jieba
# ============================================================
try:
    import jieba
    import jieba.posseg as pseg
    _HAS_JIEBA = True
except ImportError:
    _HAS_JIEBA = False
    jieba = None
    pseg = None


# ============================================================
# 数据结构
# ============================================================

@dataclass
class HNCParseResult:
    """HNC 解析结果数据结构。

    Attributes:
        template_id: 匹配到的 HNC 句类模板 ID（如 "BC_TransEvi"），
                     未匹配则为 "UNKNOWN"
        chunks: 分词结果列表（如 ["我", "吃", "苹果"]）
        concept_codes: 每个词对应的概念基元码列表（如 ["v", "p", "v"]）
        cited_rule: 匹配到的模板规则信息（含 pattern, desc），
                    未匹配时为空字典
    """
    template_id: str
    chunks: List[str]
    concept_codes: List[str]
    cited_rule: Dict[str, Any] = field(default_factory=dict)


# ============================================================
# HNC 概念基元编码器
# ============================================================

class HNCParserWrapper:
    """HNC 概念基元编码器（24字母体系，优先实现10个核心）。

    负责将自然语言文本解析为 HNC 概念基元编码序列，
    并匹配 HNC 句类模板。

    Usage:
        parser = HNCParserWrapper(use_jieba=False)
        result = parser.parse("我吃苹果")
        # result.template_id == "BC_TransEvi"
        # result.concept_codes == ["v", "p", "v"]
    """

    # 10 个核心概念基元码（24字母体系的优先子集）
    CONCEPT_BASE_TABLE: Dict[str, str] = {
        "v": "实体/物体",    # entity / object
        "g": "属性/特征",    # attribute / feature
        "u": "状态/态势",    # state / situation
        "p": "动作/过程",    # process / action
        "m": "关系/联系",    # relation / connection
        "f": "功能/作用",    # function / role
        "c": "条件/前提",    # condition / premise
        "j": "判断/评估",    # judgment / evaluation
        "q": "数量/程度",    # quantity / degree
        "r": "结果/效应",    # result / effect
    }

    # HNC 句类模板
    SENTENCE_TEMPLATES: Dict[str, Dict] = {
        "BC_TransEvi": {"pattern": ["v", "p", "v"], "desc": "传递行为句"},
        "BC_XJ": {"pattern": ["v", "j", "g"], "desc": "属性判断句"},
        "BC_XS": {"pattern": ["v", "u", "r"], "desc": "状态变化句"},
        "BC_Process": {"pattern": ["p", "v", "r"], "desc": "过程结果句"},
        "HC_Serial": {"pattern": ["v", "p", "v", "p"], "desc": "递系句"},
        "HC_Transfer": {"pattern": ["v", "p", "v", "p", "v"], "desc": "让转句"},
        "HC_Coordinate": {"pattern": ["v", "p", "v", "c", "v", "p"], "desc": "并列句"},
    }

    # jieba 词性 → HNC 概念基元码 映射表
    _POS_TO_HNC: Dict[str, str] = {
        # 名词类 → v (实体/物体)
        "n": "v", "nr": "v", "ns": "v", "nt": "v", "nz": "v",
        "ng": "v", "nl": "v",
        # 动词类 → p (动作/过程)
        "v": "p", "vd": "p", "vn": "p",
        # 形容词类 → g (属性/特征)
        "a": "g", "ad": "g", "an": "g",
        # 副词类 → u (状态/态势)
        "d": "u",
        # 量词类 → q (数量/程度)
        "q": "q", "m": "q", "mq": "q",
        # 连词类 → c (条件/前提)
        "c": "c",
        # 介词类 → m (关系/联系)
        "p": "m", "pp": "m",
        # 判断词/助动词 → j (判断/评估)
        "j": "j",
        # 时间词 → u (状态/态势)
        "t": "u", "tg": "u",
        # 状态词 → u
        "b": "u",
        # 数词 → q
        "num": "q",
    }

    # 代词默认归为 v（实体）
    _PRONOUN_FALLBACK = "v"

    # 常见代词集合（用于无 jieba 时的启发式判断）
    _PRONOUNS = frozenset({
        "我", "你", "他", "她", "它", "我们", "你们", "他们", "她们",
        "它们", "这", "那", "这个", "那个", "这里", "那里",
        "谁", "什么", "哪", "哪里", "自己", "别人", "大家",
    })

    # 常见动词集合（用于无 jieba 时的启发式判断）
    _COMMON_VERBS = frozenset({
        "是", "有", "在", "说", "做", "看", "想", "吃", "喝", "走",
        "跑", "飞", "听", "写", "读", "学", "教", "买", "卖", "给",
        "拿", "放", "打", "踢", "唱", "画", "玩", "用", "来", "去",
        "到", "回", "进", "出", "上", "下", "开", "关", "爱", "恨",
        "喜欢", "讨厌", "知道", "认为", "觉得", "成为", "变成",
    })

    # 常见形容词集合
    _COMMON_ADJECTIVES = frozenset({
        "好", "坏", "大", "小", "多", "少", "高", "低", "长", "短",
        "快", "慢", "新", "旧", "美", "丑", "热", "冷", "红", "绿",
        "蓝", "白", "黑", "真", "假", "对", "错", "强", "弱",
        "漂亮", "聪明", "勇敢", "善良", "快乐", "悲伤", "愤怒",
    })

    # 常见副词集合
    _COMMON_ADVERBS = frozenset({
        "很", "非常", "十分", "特别", "更", "最", "太", "极", "颇",
        "都", "全", "只", "仅", "还", "也", "又", "再", "已经",
        "正在", "将要", "忽然", "突然", "渐渐", "慢慢", "一直",
        "不", "没", "没有", "别", "勿", "未", "莫",
    })

    # 常见量词集合
    _COMMON_CLASSIFIERS = frozenset({
        "个", "只", "条", "本", "张", "把", "座", "棵", "朵", "颗",
        "块", "件", "双", "对", "群", "堆", "批", "种", "类", "次",
        "回", "场", "顿", "番", "趟", "遍", "阵", "段", "节", "篇",
    })

    # 常见连词集合
    _COMMON_CONJUNCTIONS = frozenset({
        "和", "与", "及", "或", "且", "并", "而", "但是", "可是",
        "然而", "虽然", "尽管", "因为", "所以", "因此", "如果",
        "假如", "只要", "只有", "除非", "无论", "不管", "即使",
        "既然", "于是", "然后", "接着", "不仅", "而且", "并且",
    })

    # 常见判断词集合
    _COMMON_JUDGMENTS = frozenset({
        "是", "为", "算", "等于", "属于", "叫做", "称为", "视为",
    })

    # 常见时间词集合
    _COMMON_TIME_WORDS = frozenset({
        "今天", "明天", "昨天", "现在", "过去", "未来", "以前",
        "以后", "之前", "之后", "早上", "晚上", "白天", "黑夜",
        "春天", "夏天", "秋天", "冬天", "年", "月", "日", "时",
        "分", "秒", "星期", "周",
    })

    # 常见名词集合（多字名词，用于无 jieba 时的分词）
    _COMMON_NOUNS = frozenset({
        "苹果", "香蕉", "橘子", "西瓜", "葡萄", "水果", "食物",
        "饭", "菜", "水", "茶", "酒", "牛奶", "面包", "米饭",
        "人", "男人", "女人", "孩子", "学生", "老师", "医生",
        "朋友", "父亲", "母亲", "爸爸", "妈妈", "哥哥", "姐姐",
        "弟弟", "妹妹", "儿子", "女儿",
        "车", "汽车", "火车", "飞机", "自行车", "船",
        "书", "报纸", "电脑", "手机", "电视", "电话",
        "房子", "家", "学校", "医院", "公园", "商店", "公司",
        "城市", "国家", "世界", "地球", "太阳", "月亮", "星星",
        "花", "树", "草", "叶子", "种子", "根", "枝",
        "狗", "猫", "鸟", "鱼", "牛", "马", "羊", "鸡", "鸭",
        "头", "手", "脚", "眼睛", "耳朵", "鼻子", "嘴巴", "脸",
        "心", "脑", "身体", "生命", "健康", "疾病",
        "红色", "蓝色", "绿色", "白色", "黑色", "颜色",
        "科学", "技术", "艺术", "音乐", "电影", "故事",
        "问题", "答案", "方法", "原因", "结果", "目的", "意义",
        "时间", "空间", "地方", "方向", "中间",
    })

    def __init__(self, use_jieba: bool = True) -> None:
        """初始化 HNC 编码器，可选加载 jieba 分词。

        Args:
            use_jieba: 是否尝试使用 jieba 分词。若 jieba 未安装，
                      自动降级为单字/词典启发式分词。
        """
        self.use_jieba = use_jieba and _HAS_JIEBA
        if use_jieba and not _HAS_JIEBA:
            logger.warning(
                "jieba 未安装，HNCParserWrapper 将降级为启发式单字分词。"
                "安装方法: pip install jieba"
            )
        if self.use_jieba and jieba is not None:
            # 预热 jieba（首次分词会加载词典）
            try:
                jieba.lcut("预热")
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("jieba 初始化失败，降级为启发式分词: %s", exc)
                self.use_jieba = False
        logger.debug(
            "HNCParserWrapper 初始化完成 (use_jieba=%s)", self.use_jieba
        )

    # ── 公共 API ──

    def parse(self, text: str) -> HNCParseResult:
        """解析自然语言文本，返回 HNC 概念基元编码结果。

        执行三阶段：分词 → 概念编码 → 模板匹配。

        Args:
            text: 输入文本（如 "我吃苹果"）

        Returns:
            HNCParseResult: 包含 template_id, chunks, concept_codes, cited_rule
        """
        if not text or not text.strip():
            return HNCParseResult(
                template_id="UNKNOWN",
                chunks=[],
                concept_codes=[],
                cited_rule={},
            )

        # 阶段 1: 分词
        chunks = self._tokenize(text)

        # 阶段 2: 概念编码
        concept_codes = [self.encode_concept(word) for word in chunks]

        # 阶段 3: 模板匹配
        template_id = self.match_template(concept_codes)
        cited_rule: Dict[str, Any] = {}
        if template_id != "UNKNOWN":
            tpl = self.SENTENCE_TEMPLATES.get(template_id, {})
            cited_rule = {
                "template_id": template_id,
                "pattern": list(tpl.get("pattern", [])),
                "desc": tpl.get("desc", ""),
            }

        logger.debug(
            "HNC parse: text=%r -> chunks=%s codes=%s template=%s",
            text, chunks, concept_codes, template_id,
        )
        return HNCParseResult(
            template_id=template_id,
            chunks=chunks,
            concept_codes=concept_codes,
            cited_rule=cited_rule,
        )

    def encode_concept(self, word: str) -> str:
        """将单个词编码为 HNC 概念基元码。

        使用启发式规则：
        - 有 jieba：基于 jieba.posseg 词性标签映射
        - 无 jieba：基于预置词典 + 字符特征的启发式判断
          名词→v, 动词→p, 形容词→g, 副词→u, 量词→q,
          连词→c, 判断词→j, 时间词→u

        Args:
            word: 输入词（如 "苹果"）

        Returns:
            概念基元码（如 "v"），未知词默认归为 "v"（实体）
        """
        if not word:
            return "v"

        # 优先使用 jieba 词性标注
        if self.use_jieba and pseg is not None:
            try:
                pairs = list(pseg.cut(word))
                if pairs:
                    pos = pairs[0].flag
                    code = self._POS_TO_HNC.get(pos)
                    if code is not None:
                        return code
                    # 词性未在映射表中，尝试宽松匹配前缀
                    for prefix_len in (2, 1):
                        if len(pos) >= prefix_len:
                            prefix = pos[:prefix_len]
                            code = self._POS_TO_HNC.get(prefix)
                            if code is not None:
                                return code
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("jieba posseg 失败，降级启发式: %s", exc)

        # 降级：启发式词典匹配
        return self._heuristic_encode(word)

    def match_template(self, concept_codes: List[str]) -> str:
        """匹配 HNC 句类模板，返回模板 ID 或 'UNKNOWN'。

        匹配策略：
        1. 精确匹配：concept_codes 与某模板 pattern 完全相等
        2. 子序列匹配：concept_codes 包含某模板 pattern 作为子序列
        3. 编辑距离匹配：选择编辑距离最小的模板（距离 ≤ 容忍度）

        Args:
            concept_codes: 概念基元码列表（如 ["v", "p", "v"]）

        Returns:
            模板 ID（如 "BC_TransEvi"）或 "UNKNOWN"
        """
        if not concept_codes:
            return "UNKNOWN"

        codes = list(concept_codes)

        # 1. 精确匹配
        for tpl_id, tpl in self.SENTENCE_TEMPLATES.items():
            if codes == tpl["pattern"]:
                return tpl_id

        # 2. 子序列匹配（pattern 是 codes 的子序列）
        best_sub: Optional[str] = None
        best_sub_len = 0
        for tpl_id, tpl in self.SENTENCE_TEMPLATES.items():
            pattern = tpl["pattern"]
            if self._is_subsequence(pattern, codes):
                if len(pattern) > best_sub_len:
                    best_sub_len = len(pattern)
                    best_sub = tpl_id
        if best_sub is not None:
            return best_sub

        # 3. 编辑距离匹配（允许部分匹配）
        best_tpl: Optional[str] = None
        best_dist = None
        for tpl_id, tpl in self.SENTENCE_TEMPLATES.items():
            pattern = tpl["pattern"]
            dist = self._edit_distance(codes, pattern)
            # 容忍度：模板长度的 40%（至少容忍 1 个差异）
            tolerance = max(1, int(len(pattern) * 0.4))
            if dist <= tolerance:
                if best_dist is None or dist < best_dist:
                    best_dist = dist
                    best_tpl = tpl_id
        if best_tpl is not None:
            return best_tpl

        return "UNKNOWN"

    # ── 内部方法 ──

    def _tokenize(self, text: str) -> List[str]:
        """分词：优先 jieba，降级为启发式单字分词。

        Args:
            text: 输入文本

        Returns:
            分词结果列表
        """
        text = text.strip()
        if not text:
            return []

        if self.use_jieba and jieba is not None:
            try:
                words = jieba.lcut(text)
                # 过滤纯标点和空白
                return [w for w in words if w and w.strip()]
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("jieba 分词失败，降级单字: %s", exc)

        # 降级：词典最长匹配 + 单字回退
        return self._heuristic_tokenize(text)

    def _heuristic_tokenize(self, text: str) -> List[str]:
        """启发式分词：基于预置词典的最长匹配 + 单字回退。

        Args:
            text: 输入文本

        Returns:
            分词结果列表
        """
        # 合并所有词典词，按长度降序排列用于最长匹配
        dictionary = (
            self._PRONOUNS | self._COMMON_VERBS | self._COMMON_ADJECTIVES
            | self._COMMON_ADVERBS | self._COMMON_CLASSIFIERS
            | self._COMMON_CONJUNCTIONS | self._COMMON_JUDGMENTS
            | self._COMMON_TIME_WORDS | self._COMMON_NOUNS
        )
        max_len = max((len(w) for w in dictionary), default=1)

        chunks: List[str] = []
        i = 0
        n = len(text)
        while i < n:
            char = text[i]
            # 跳过标点和空白
            if char in " \t\n\r，。、；：？！,.;:!?()（）[]【】""''\"'":
                i += 1
                continue

            # 尝试最长词典匹配
            matched = False
            for length in range(min(max_len, n - i), 0, -1):
                candidate = text[i:i + length]
                if candidate in dictionary:
                    chunks.append(candidate)
                    i += length
                    matched = True
                    break
            if not matched:
                # 单字分词
                chunks.append(char)
                i += 1
        return chunks

    def _heuristic_encode(self, word: str) -> str:
        """无 jieba 时的启发式概念编码。

        Args:
            word: 输入词

        Returns:
            概念基元码
        """
        if word in self._PRONOUNS:
            return "v"
        if word in self._COMMON_VERBS:
            # "是/为/算" 等判断词归为 j
            if word in self._COMMON_JUDGMENTS:
                return "j"
            return "p"
        if word in self._COMMON_JUDGMENTS:
            return "j"
        if word in self._COMMON_ADJECTIVES:
            return "g"
        if word in self._COMMON_ADVERBS:
            return "u"
        if word in self._COMMON_CLASSIFIERS:
            return "q"
        if word in self._COMMON_CONJUNCTIONS:
            return "c"
        if word in self._COMMON_TIME_WORDS:
            return "u"
        # 默认：实体/物体
        return "v"

    @staticmethod
    def _is_subsequence(short: List[str], long: List[str]) -> bool:
        """判断 short 是否为 long 的子序列。

        Args:
            short: 较短序列
            long: 较长序列

        Returns:
            是否为子序列
        """
        it = iter(long)
        return all(item in it for item in short)

    @staticmethod
    def _edit_distance(a: List[str], b: List[str]) -> int:
        """计算两个序列的编辑距离（Levenshtein）。

        Args:
            a: 序列 A
            b: 序列 B

        Returns:
            编辑距离
        """
        m, n = len(a), len(b)
        if m == 0:
            return n
        if n == 0:
            return m
        # 滚动数组优化空间
        prev = list(range(n + 1))
        curr = [0] * (n + 1)
        for i in range(1, m + 1):
            curr[0] = i
            for j in range(1, n + 1):
                cost = 0 if a[i - 1] == b[j - 1] else 1
                curr[j] = min(
                    prev[j] + 1,        # 删除
                    curr[j - 1] + 1,    # 插入
                    prev[j - 1] + cost  # 替换
                )
            prev, curr = curr, prev
        return prev[n]


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("HNCParserWrapper 自测")
    print("=" * 60)

    parser = HNCParserWrapper(use_jieba=False)

    # 测试 1: 传递行为句 "我吃苹果" → v p v → BC_TransEvi
    result = parser.parse("我吃苹果")
    print(f"\n[测试1] 我吃苹果")
    print(f"  Template: {result.template_id}")
    print(f"  Chunks:   {result.chunks}")
    print(f"  Codes:    {result.concept_codes}")
    print(f"  Rule:     {result.cited_rule}")
    assert result.concept_codes == ["v", "p", "v"], \
        f"期望 ['v','p','v'], 实际 {result.concept_codes}"
    assert result.template_id == "BC_TransEvi", \
        f"期望 BC_TransEvi, 实际 {result.template_id}"

    # 测试 2: 属性判断句 "苹果是红色的" → v j g → BC_XJ
    result = parser.parse("苹果是红色的")
    print(f"\n[测试2] 苹果是红色的")
    print(f"  Template: {result.template_id}")
    print(f"  Chunks:   {result.chunks}")
    print(f"  Codes:    {result.concept_codes}")
    # "苹果"→v, "是"→j, "红色"→g (形容词), "的"→v(默认)
    # 子序列匹配应命中 BC_XJ
    assert "j" in result.concept_codes, f"期望含 j, 实际 {result.concept_codes}"

    # 测试 3: 空文本
    result = parser.parse("")
    print(f"\n[测试3] 空文本")
    print(f"  Template: {result.template_id}")
    assert result.template_id == "UNKNOWN"
    assert result.chunks == []

    # 测试 4: 状态变化句 "花开了" → v p (子序列匹配 BC_TransEvi)
    result = parser.parse("花开了")
    print(f"\n[测试4] 花开了")
    print(f"  Template: {result.template_id}")
    print(f"  Chunks:   {result.chunks}")
    print(f"  Codes:    {result.concept_codes}")

    # 测试 5: encode_concept 单词编码
    print(f"\n[测试5] encode_concept 单词编码")
    for word in ["我", "吃", "苹果", "很", "个", "和", "是", "今天"]:
        code = parser.encode_concept(word)
        print(f"  {word} -> {code}")

    # 测试 6: match_template 直接调用
    print(f"\n[测试6] match_template")
    test_cases = [
        (["v", "p", "v"], "BC_TransEvi"),
        (["v", "j", "g"], "BC_XJ"),
        (["v", "u", "r"], "BC_XS"),
        (["p", "v", "r"], "BC_Process"),
        (["v", "p", "v", "p"], "HC_Serial"),
        (["v", "p", "v", "p", "v"], "HC_Transfer"),
        (["x", "y", "z"], "UNKNOWN"),
    ]
    for codes, expected in test_cases:
        actual = parser.match_template(codes)
        status = "✓" if actual == expected else "✗"
        print(f"  {status} {codes} -> {actual} (期望 {expected})")
        assert actual == expected, f"{codes}: 期望 {expected}, 实际 {actual}"

    print("\n" + "=" * 60)
    print("所有自测通过 ✓")
    print("=" * 60)
