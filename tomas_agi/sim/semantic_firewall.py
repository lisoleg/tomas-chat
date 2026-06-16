"""
语义防火墙 — 基于 SemanticClosure 的输入输出防火墙

对输入查询和输出响应进行语义闭合检测、三不问题检测、
DIKWP 层感知过滤，防止幻觉和语义不一致。

基于 tomas_agi/sim/semantic_math.py 的 SemanticClosure 引擎。
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================
# 数据结构
# ============================================================

class FirewallVerdict(Enum):
    """防火墙裁决"""
    ALLOW = "allow"              # 放行
    BLOCK = "block"              # 拦截
    WARN = "warn"                # 告警但放行
    MUS_ACTIVE = "mus_active"    # MUS 双存 — 需人工裁决
    DEAD_ZERO_REJECT = "dead_zero_reject"  # 死零拒绝


@dataclass
class FirewallLog:
    """防火墙日志条目"""
    timestamp: str
    direction: str               # "input" | "output"
    content: str
    verdict: FirewallVerdict
    reason: str
    details: Dict = field(default_factory=dict)


@dataclass
class FirewallStats:
    """防火墙统计"""
    total_inputs: int = 0
    total_outputs: int = 0
    blocked_inputs: int = 0
    blocked_outputs: int = 0
    warned: int = 0
    mus_raised: int = 0
    dead_zero: int = 0


# ============================================================
# 输入防火墙
# ============================================================

class InputFirewall:
    """输入查询防火墙

    检查维度:
      1. 语义有效性 — 是否包含可解析的概念结构
      2. 三不问题 — 不完整/不精确/不一致
      3. DIKWP 层感知 — 查询应匹配的认知层级
      4. 安全边界 — 高危/欺骗性查询检测
    """

    # 高危模式 (参考 ADC 反欺骗框架)
    HIGH_RISK_PATTERNS = [
        # 代码讨好
        {"pattern": ["代码", "完美"], "label": "ADC-01: 代码讨好"},
        {"pattern": ["完美无缺", "代码"], "label": "ADC-01: 代码讨好"},
        # 合规规避
        {"pattern": ["跳过", "安全审查"], "label": "ADC-02: 合规规避"},
        {"pattern": ["绕开", "审查"], "label": "ADC-02: 合规规避"},
        # 事实篡改
        {"pattern": ["地球", "平的"], "label": "ADC-04: 事实篡改"},
        {"pattern": ["地球是平的"], "label": "ADC-04: 事实篡改"},
        # 对齐伪装
        {"pattern": ["安全评估", "激进"], "label": "ADC-05: 对齐伪装"},
        # 幽灵数据
        {"pattern": ["不存在", "数据", "训练"], "label": "ADC-06: 幽灵数据"},
    ]

    def __init__(self, semantic_closure=None):
        self.semantic_closure = semantic_closure  # 注入 SemanticClosure 实例
        self.logs: List[FirewallLog] = []
        self.stats = FirewallStats()

    def inspect(self, query: str, dikwp_layer: str = "I") -> Tuple[FirewallVerdict, Dict]:
        """检查输入查询

        Args:
            query: 用户输入查询
            dikwp_layer: 当前 DIKWP 层 (D/I/K/W/P)

        Returns:
            (verdict, details): 裁决 + 详细分析
        """
        import time
        self.stats.total_inputs += 1
        details = {"query": query[:100], "dikwp_layer": dikwp_layer}

        # 1. 空查询检测
        if not query or not query.strip():
            self._log("input", query, FirewallVerdict.BLOCK, "空查询")
            self.stats.blocked_inputs += 1
            return FirewallVerdict.BLOCK, details

        # 2. 高危模式检测
        risk = self._check_high_risk(query)

        # 提前分词 (后续步骤共用)
        words = list(set(query.replace("？", "").replace("?", "").replace("，", " ")
                        .replace(",", " ").split()))
        if risk:
            self._log("input", query, FirewallVerdict.DEAD_ZERO_REJECT,
                      f"高危模式: {risk}")
            self.stats.dead_zero += 1
            details["risk_match"] = risk
            return FirewallVerdict.DEAD_ZERO_REJECT, details

        # 3. 语义有效性
        if self.semantic_closure and len(words) >= 2:
                try:
                    sc_result = self.semantic_closure.check_closure(
                        words[0], words[1] if len(words) > 1 else words[0],
                        words[2] if len(words) > 2 else ""
                    )
                    details["semantic_closure"] = {
                        "closed": sc_result.get("is_closed", False),
                        "i_conserved": sc_result.get("i_conserved", True),
                    }

                    if not sc_result.get("is_closed", False):
                        self._log("input", query, FirewallVerdict.WARN,
                                  "语义未闭合 — 可能存在三不问题")
                        self.stats.warned += 1
                        return FirewallVerdict.WARN, details
                except Exception:
                    pass

        # 4. DIKWP 层感知 — 检查查询复杂度是否匹配当前层
        layer_min_words = {"D": 0, "I": 1, "K": 3, "W": 5, "P": 7}
        min_words = layer_min_words.get(dikwp_layer, 0)
        if len(words) < min_words and dikwp_layer in ("K", "W", "P"):
            self._log("input", query, FirewallVerdict.WARN,
                      f"DIKWP 层 {dikwp_layer} 需要更丰富的输入")
            self.stats.warned += 1
            return FirewallVerdict.WARN, details

        # 5. 放行
        self._log("input", query, FirewallVerdict.ALLOW, "语义有效, 层匹配")
        return FirewallVerdict.ALLOW, details

    def _check_high_risk(self, query: str) -> Optional[str]:
        """检测高危模式"""
        query_lower = query.lower()
        for risk in self.HIGH_RISK_PATTERNS:
            pattern = risk["pattern"]
            if all(p.lower() in query_lower for p in pattern):
                return risk["label"]
        return None

    def _log(self, direction: str, content: str,
             verdict: FirewallVerdict, reason: str):
        import time
        self.logs.append(FirewallLog(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            direction=direction, content=content[:200],
            verdict=verdict, reason=reason,
        ))


# ============================================================
# 输出防火墙
# ============================================================

class OutputFirewall:
    """输出响应防火墙

    检查维度:
      1. 幻觉检测 — 响应是否引用了不存在/低 ℐ 的事实
      2. 语义一致性 — 响应是否与输入语义匹配
      3. MUS 矛盾检测 — 响应是否包含自相矛盾的论断
      4. DIKWP 层降级 — 高层的响应降为低层是否合理
    """

    def __init__(self, semantic_closure=None, dikwp_mapper=None):
        self.semantic_closure = semantic_closure
        self.dikwp_mapper = dikwp_mapper
        self.logs: List[FirewallLog] = []
        self.stats = FirewallStats()

    def inspect(self, response: str, query: str = "",
                eml_context: Dict = None,
                expected_layer: str = "K") -> Tuple[FirewallVerdict, Dict]:
        """检查输出响应

        Args:
            response: AI 生成响应
            query: 原始查询
            eml_context: EML 上下文 (用于 ℐ-验证)
            expected_layer: 期望的 DIKWP 层

        Returns:
            (verdict, details): 裁决 + 详细分析
        """
        import time
        self.stats.total_outputs += 1
        details = {"response_len": len(response), "expected_layer": expected_layer}

        # 1. 空响应检测
        if not response or not response.strip():
            self._log("output", response, FirewallVerdict.BLOCK, "空响应")
            self.stats.blocked_outputs += 1
            return FirewallVerdict.BLOCK, details

        # 2. 语义漂移检测 (响应 vs 查询)
        if query and self.semantic_closure:
            drift = self._check_semantic_drift(query, response)
            details["semantic_drift"] = drift
            if drift.get("has_drift", False) and drift.get("score", 0) > 0.7:
                self._log("output", response, FirewallVerdict.BLOCK,
                          f"语义漂移严重: score={drift['score']:.2f}")
                self.stats.blocked_outputs += 1
                return FirewallVerdict.BLOCK, details
            elif drift.get("has_drift", False):
                self._log("output", response, FirewallVerdict.WARN,
                          f"语义漂移轻微: score={drift['score']:.2f}")
                self.stats.warned += 1
                return FirewallVerdict.WARN, details

        # 3. ℐ-幻觉检测 (检查响应中的概念是否有 EML 支撑)
        if eml_context:
            hallucination = self._check_i_hallucination(response, eml_context)
            details["hallucination"] = hallucination
            if hallucination.get("hallucinated_concepts"):
                self._log("output", response, FirewallVerdict.DEAD_ZERO_REJECT,
                          f"幻觉概念: {hallucination['hallucinated_concepts']}")
                self.stats.dead_zero += 1
                return FirewallVerdict.DEAD_ZERO_REJECT, details

        # 4. DIKWP 层一致性
        if self.dikwp_mapper:
            layer_check = self._check_dikwp_layer_consistency(response, expected_layer)
            details["dikwp_layer_check"] = layer_check
            if not layer_check.get("consistent", True):
                self._log("output", response, FirewallVerdict.WARN,
                          f"DIKWP 层不一致: expected={expected_layer}, "
                          f"actual={layer_check.get('actual_layer')}")
                self.stats.warned += 1
                return FirewallVerdict.WARN, details

        # 放行
        self._log("output", response, FirewallVerdict.ALLOW, "输出安全")
        return FirewallVerdict.ALLOW, details

    def _check_semantic_drift(self, query: str, response: str) -> Dict:
        """检查语义漂移"""
        # 简单 Jaccard 相似度
        q_words = set(query.replace("？", "").replace("?", "").split())
        r_words = set(response.split())
        if not q_words or not r_words:
            return {"has_drift": False, "score": 0.0}

        intersection = q_words & r_words
        union = q_words | r_words
        jaccard = len(intersection) / max(len(union), 1)

        return {
            "has_drift": jaccard < 0.1,
            "score": 1.0 - jaccard,
            "query_words": len(q_words),
            "response_words": len(r_words),
            "shared_words": len(intersection),
        }

    def _check_i_hallucination(self, response: str, eml_context: Dict) -> Dict:
        """检查 ℐ-幻觉"""
        edges = eml_context.get("edges", [])
        known_concepts = set()
        for edge in edges:
            known_concepts.update(edge.get("nodes", []))

        # 简单检查: 提取响应中的名词短语, 查找不在 EML 中的
        response_words = set(response.replace("。", " ").replace("，", " ").split())
        hallucinated = [
            w for w in response_words
            if len(w) >= 2 and w not in known_concepts and not w.isascii()
        ]

        return {
            "hallucinated_concepts": hallucinated[:10],
            "hallucination_count": len(hallucinated),
            "known_concepts": len(known_concepts),
        }

    def _check_dikwp_layer_consistency(self, response: str,
                                       expected_layer: str) -> Dict:
        """检查 DIKWP 层一致性"""
        layer_complexity = {"D": 0.2, "I": 0.4, "K": 0.6, "W": 0.8, "P": 1.0}

        # 基于响应长度和结构推断实际层
        sentences = response.count("。") + response.count("；") + 1
        avg_sentence_len = len(response) / max(sentences, 1)

        actual_score = min(1.0, (sentences / 10) * 0.5 + (avg_sentence_len / 50) * 0.5)
        expected_score = layer_complexity.get(expected_layer, 0.5)

        consistent = abs(actual_score - expected_score) < 0.4

        # 推断实际层
        actual_layer = "D"
        for layer, score in sorted(layer_complexity.items(), key=lambda x: x[1]):
            if actual_score >= score:
                actual_layer = layer

        return {
            "consistent": consistent,
            "actual_layer": actual_layer,
            "actual_score": actual_score,
            "expected_score": expected_score,
        }

    def _log(self, direction: str, content: str,
             verdict: FirewallVerdict, reason: str):
        import time
        self.logs.append(FirewallLog(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            direction=direction, content=content[:200],
            verdict=verdict, reason=reason,
        ))


# ============================================================
# 语义防火墙总控
# ============================================================

class SemanticFirewall:
    """语义防火墙总控 — 整合输入/输出防火墙"""

    def __init__(self, semantic_closure=None, dikwp_mapper=None,
                 enable_input: bool = True, enable_output: bool = True):
        self.input_fw = InputFirewall(semantic_closure) if enable_input else None
        self.output_fw = OutputFirewall(semantic_closure, dikwp_mapper) if enable_output else None

    def inspect_input(self, query: str, dikwp_layer: str = "I") -> Tuple[FirewallVerdict, Dict]:
        """检查输入"""
        if not self.input_fw:
            return FirewallVerdict.ALLOW, {}
        return self.input_fw.inspect(query, dikwp_layer)

    def inspect_output(self, response: str, query: str = "",
                       eml_context: Dict = None,
                       expected_layer: str = "K") -> Tuple[FirewallVerdict, Dict]:
        """检查输出"""
        if not self.output_fw:
            return FirewallVerdict.ALLOW, {}
        return self.output_fw.inspect(response, query, eml_context, expected_layer)

    def get_logs(self, direction: str = None) -> List[FirewallLog]:
        """获取防火墙日志"""
        logs = []
        if self.input_fw:
            if direction is None or direction == "input":
                logs.extend(self.input_fw.logs)
        if self.output_fw:
            if direction is None or direction == "output":
                logs.extend(self.output_fw.logs)
        return sorted(logs, key=lambda l: l.timestamp, reverse=True)

    def get_stats(self) -> FirewallStats:
        """获取统计"""
        stats = FirewallStats()
        if self.input_fw:
            s = self.input_fw.stats
            stats.total_inputs = s.total_inputs
            stats.blocked_inputs = s.blocked_inputs
            stats.warned += s.warned
            stats.dead_zero += s.dead_zero
        if self.output_fw:
            s = self.output_fw.stats
            stats.total_outputs = s.total_outputs
            stats.blocked_outputs = s.blocked_outputs
            stats.warned += s.warned
            stats.dead_zero += s.dead_zero
        return stats


# ============================================================
# 导出
# ============================================================

__all__ = [
    "FirewallVerdict",
    "FirewallLog",
    "FirewallStats",
    "InputFirewall",
    "OutputFirewall",
    "SemanticFirewall",
]
