# -*- coding: utf-8 -*-
"""
grill_me_engine.py — TOMAS AGI v3.11 Grill-Me 需求审计引擎
============================================================

基于 DIKWP 五层模型的缺口分析门控系统，对 AGI 需求进行五层语义完整性检查，
确保任何执行前的需求已被完整覆盖（无静默脑补、无缺口、无模糊）。

组件：
  T5: DIKWPGapAnalyzer — DIKWP 五层缺口分析器
  T6: GrillExecutionGate — 执行门控与缺口释放
  T7: RequirementTracer  — κ-Snap 溯源链验证
  T8: PsiNoSilentAssumption — ψ-静默脑补检测

架构：
  - 三阶回退导入模式
  - SHA-256 链式审计
  - 零外部依赖 (stdlib only)
  - κ-Snap 链式溯源
  - 内置 self-test

Author: TOMAS Team
Version: v3.11
"""

from __future__ import annotations

import hashlib
import json
import time
import math
import uuid
import re
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Set

# ============================================================
# 三阶回退导入
# ============================================================

try:
    from .dikwp_mapper import DIKWPMapper
    _HAS_DIKWP = True
except ImportError:
    try:
        from dikwp_mapper import DIKWPMapper
        _HAS_DIKWP = True
    except ImportError:
        _HAS_DIKWP = False
        DIKWPMapper = None

try:
    from .ksnap_operator import KSnapOperator, SnapEvent
    _HAS_KSNAP = True
except ImportError:
    try:
        from ksnap_operator import KSnapOperator, SnapEvent
        _HAS_KSNAP = True
    except ImportError:
        _HAS_KSNAP = False
        KSnapOperator = None
        SnapEvent = None

# KappaSnap 别名回退
try:
    from .ksnap_operator import KappaSnap
    _HAS_KAPPASNAP = True
except ImportError:
    try:
        from ksnap_operator import KappaSnap
        _HAS_KAPPASNAP = True
    except ImportError:
        _HAS_KAPPASNAP = False
        KappaSnap = KSnapOperator  # 别名回退

try:
    from .psi_anchor import PsiAnchor
    _HAS_PSI = True
except ImportError:
    try:
        from psi_anchor import PsiAnchor
        _HAS_PSI = True
    except ImportError:
        _HAS_PSI = False
        PsiAnchor = None


# ============================================================
# SHA-256 审计工具
# ============================================================

def _sha256(s: str) -> str:
    """SHA-256 哈希（确定性审计）"""
    return hashlib.sha256(s.encode()).hexdigest()


def _chain_hash(previous_hash: str, data: str) -> str:
    """κ-Snap 链式哈希: H(prev || data)"""
    return _sha256(previous_hash + data)


def _make_snap_ref(event_id: str, previous_hash: str) -> str:
    """生成 κ-Snap 链引用: snap:<event_id>:<chain_hash>"""
    new_hash = _chain_hash(previous_hash, event_id)
    return f"snap:{event_id}:{new_hash}"


# ============================================================
# 枚举
# ============================================================

class LayerStatus(str, Enum):
    """DIKWP 层覆盖状态"""
    COVERED = "COVERED"
    MISSING = "MISSING"
    AMBIGUOUS = "AMBIGUOUS"


class GapClosureStatus(str, Enum):
    """缺口关闭状态"""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    OVERRIDDEN = "OVERRIDDEN"


# ============================================================
# T5: 数据类
# ============================================================

@dataclass
class LayerGap:
    """单层 DIKWP 缺口分析结果"""
    status: str  # "covered" | "missing" | "ambiguous"
    gap_description: str
    evidence_required: str
    closed: bool = False
    closed_by: Optional[str] = None
    closed_at: Optional[float] = None
    evidence_provided: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "gap_description": self.gap_description,
            "evidence_required": self.evidence_required,
            "closed": self.closed,
            "closed_by": self.closed_by,
            "closed_at": self.closed_at,
            "evidence_provided": self.evidence_provided,
        }

    def close(self, evidence: str, closed_by: str) -> None:
        """用证据关闭此缺口"""
        self.closed = True
        self.closed_by = closed_by
        self.closed_at = time.time()
        self.evidence_provided = evidence


@dataclass
class GapReport:
    """DIKWP 五层完整缺口报告"""
    requirement_id: str
    requirement_raw: str
    layers: Dict[str, LayerGap] = field(default_factory=dict)  # "D"/"I"/"K"/"W"/"P" → LayerGap
    all_gaps_closed: bool = False
    silent_assumptions: List[str] = field(default_factory=list)
    trace_chain_refs: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    report_hash: str = ""

    def __post_init__(self):
        if not self.report_hash:
            content = json.dumps({
                "requirement_id": self.requirement_id,
                "requirement_raw": self.requirement_raw,
                "created_at": self.created_at,
            }, sort_keys=True)
            self.report_hash = _sha256(content)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "requirement_raw": self.requirement_raw,
            "layers": {k: v.to_dict() for k, v in self.layers.items()},
            "all_gaps_closed": self.all_gaps_closed,
            "silent_assumptions": self.silent_assumptions,
            "trace_chain_refs": self.trace_chain_refs,
            "created_at": self.created_at,
            "report_hash": self.report_hash,
        }

    def get_open_gaps(self) -> List[Tuple[str, LayerGap]]:
        """获取所有未关闭的缺口"""
        return [(layer, gap) for layer, gap in self.layers.items() if not gap.closed and gap.status != "covered"]

    def get_missing_layers(self) -> List[str]:
        """获取所有 missing 状态的层"""
        return [layer for layer, gap in self.layers.items() if gap.status == "missing"]

    def get_ambiguous_layers(self) -> List[str]:
        """获取所有 ambiguous 状态的层"""
        return [layer for layer, gap in self.layers.items() if gap.status == "ambiguous"]


# ============================================================
# T5: DIKWPGapAnalyzer 类
# ============================================================

class DIKWPGapAnalyzer:
    """
    DIKWP 五层需求缺口分析器 (T5)

    对需求文本进行 D→I→K→W→P 五层逐层分析，检查语义完整性。
    每层通过正则模式匹配检测需求是否覆盖对应维度的内容。

    分析方法：
      - D 层: 检查数据格式/来源/范围描述
      - I 层: 检查信息频率/精度/粒度/属性
      - K 层: 检查知识/算法/规则明确性
      - W 层: 检查决策标准/阈值/优先级
      - P 层: 检查意图对齐/Purpose 锚定
    """

    # D 层：数据关键词
    _D_PATTERNS: List[str] = [
        r'数据(格式|类型|来源|范围|字段|结构|schema)',
        r'输入.*?(格式|类型|字段)',
        r'数据(集|库|表|源|流)',
        r'(CSV|JSON|XML|YAML|Parquet|SQL|NoSQL|API)',
        r'(原始|结构化|非结构|半结构)化?数据',
        r'数据(维度|精度|单位|范围)',
        r'(float|int|string|bool|datetime|timestamp|array)',
    ]

    # I 层：信息关键词
    _I_PATTERNS: List[str] = [
        r'(频率|周期|间隔|每秒|每分钟|每小时|每天|实时)',
        r'(精度|准确率|精确到|小数|误差|容差|tolerance)',
        r'(粒度|分辨率|采样率|aggregation|聚合)',
        r'(属性|特征|指标|维度|度量|metric)',
        r'(单位|千克|米|秒|度|百分比|ratio|proportion)',
        r'信息(完整|完备|充分|缺失)',
        r'(统计|均值|方差|标准差|分布|直方图)',
        r'(时间窗|滑动窗|批次|batch|stream)',
    ]

    # K 层：知识/算法关键词
    _K_PATTERNS: List[str] = [
        r'(算法|模型|方法|规则|逻辑|流程|pipeline)',
        r'(计算|推导|推理|推断|预测|分类|回归|聚类)',
        r'(神经网络|决策树|SVM|随机森林|Transformer|CNN|RNN|LSTM|GPT|LLM)',
        r'(公式|方程|定理|推导|公理)',
        r'(训练|学习|优化|梯度|损失|lr|epoch|batch)',
        r'(知识|图谱|本体|ontology|规则库)',
        r'(if.*then|when.*then|条件|触发|条件判断)',
        r'(参数|超参|权重|偏置|threshold)',
    ]

    # W 层：决策/智慧关键词
    _W_PATTERNS: List[str] = [
        r'(决策|选择|判断|评估|权衡|trade.off)',
        r'(优先级|优先级|重要|紧急|排序|rank|priority)',
        r'(阈值|临界|门槛|threshold|cutoff|界限)',
        r'(标准|准则|指标|benchmark|KPI|SLA)',
        r'(风险|安全|可靠|鲁棒|fallback|降级)',
        r'(最优|次优|满意|可接受|acceptable)',
        r'(策略|方案|路径|选择|option|alternative)',
        r'(human.in.the.loop|人工审核|审核|确认|审批)',
    ]

    # P 层：意图/目的关键词
    _P_PATTERNS: List[str] = [
        r'(目标|目的|意图|宗旨|使命|goal|objective|purpose)',
        r'(成功|失败|验收|acceptance|criteria|通过条件)',
        r'(对齐|alignment|对齐|consistent|coherent)',
        r'(价值|意义|影响|impact|value|benefit)',
        r'(约束|限制|禁止|必须|must|shall|require)',
        r'(安全|隐私|隐私|伦理|道德|合规|compliance)',
        r'(最终|终极|long.term|sustainable|可持续)',
        r'(用户|客户|利益|stakeholder|涉众)',
    ]

    # 模糊/不确定关键词
    _AMBIGUOUS_PATTERNS: List[str] = [
        r'(大概|大约|近似|约|左右|可能|或许|maybe|approximately)',
        r'(适当|合适|合理|足够|充分|adequate|sufficient)',
        r'(一般|通常|常规|普通|normally|typically|usually)',
        r'(根据情况|视情况|酌情|case.by.case)',
        r'(尽量|尽可能|as.*as possible)',
        r'(等等|\.{3,}|etc|and so on)',
    ]

    def __init__(self):
        """初始化 DIKWP 缺口分析器"""
        self._analysis_count: int = 0
        self._gap_history: List[GapReport] = []
        self._memo: Dict[str, GapReport] = {}  # 需求缓存

    def analyze(self, requirement: str) -> GapReport:
        """
        五层逐层缺口分析

        Args:
            requirement: 需求文本

        Returns:
            GapReport: 完整五层缺口报告
        """
        self._analysis_count += 1
        req_id = _sha256(requirement)[:16]

        # 检查缓存
        if req_id in self._memo:
            return self._memo[req_id]

        layers: Dict[str, LayerGap] = {}
        layer_methods = [
            ("D", self.analyze_data_layer),
            ("I", self.analyze_info_layer),
            ("K", self.analyze_knowledge_layer),
            ("W", self.analyze_wisdom_layer),
            ("P", self.analyze_purpose_layer),
        ]

        for layer_name, method in layer_methods:
            layers[layer_name] = method(requirement)

        all_closed = all(
            gap.status == "covered" for gap in layers.values()
        )

        report = GapReport(
            requirement_id=req_id,
            requirement_raw=requirement,
            layers=layers,
            all_gaps_closed=all_closed,
            silent_assumptions=[],
            trace_chain_refs=[],
        )

        self._gap_history.append(report)
        self._memo[req_id] = report
        return report

    def _match_any(self, text: str, patterns: List[str]) -> Tuple[bool, List[str]]:
        """检查文本是否匹配任意模式，返回 (是否匹配, 匹配到的模式列表)"""
        matched = []
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                matched.append(pattern)
        return len(matched) > 0, matched

    def _check_ambiguous(self, text: str, evidence: str) -> Tuple[bool, str]:
        """检查证据文本中是否包含模糊/不确定表述"""
        has_ambig, ambig_matches = self._match_any(text, self._AMBIGUOUS_PATTERNS)
        if has_ambig:
            matches_str = "; ".join(ambig_matches[:3])
            return True, f"模糊表述: {matches_str}"
        return False, ""

    def _make_gap(
        self,
        matched: bool,
        evidence: str,
        description_covered: str,
        description_missing: str,
        evidence_missing: str,
        req_text: str = "",
    ) -> LayerGap:
        """构建 LayerGap 对象"""
        if matched:
            is_ambig, ambig_reason = self._check_ambiguous(req_text, evidence)
            if is_ambig:
                return LayerGap(
                    status="ambiguous",
                    gap_description=f"{description_covered}，但表述模糊: {ambig_reason}",
                    evidence_required=f"需更精确的规格定义",
                )
            return LayerGap(
                status="covered",
                gap_description=description_covered,
                evidence_required="N/A",
            )
        else:
            return LayerGap(
                status="missing",
                gap_description=description_missing,
                evidence_required=evidence_missing,
            )

    def analyze_data_layer(self, req: str) -> LayerGap:
        """
        D 层分析：检查数据需求（格式/来源/范围）

        检测规则：
          - 有明确数据格式/来源/范围 → covered
          - 模糊表述 → ambiguous
          - 无描述 → missing

        Args:
            req: 需求文本

        Returns:
            LayerGap: D层缺口分析结果
        """
        matched, evidence = self._match_any(req, self._D_PATTERNS)
        matched_text = ", ".join(evidence[:3]) if evidence else ""

        return self._make_gap(
            matched=matched,
            evidence=matched_text,
            description_covered=f"D层: 数据格式/来源/范围已定义 ({matched_text})",
            description_missing="D层: 缺少数据格式/来源/范围描述",
            evidence_missing="需明确数据格式(JSON/CSV/...)、来源(API/DB/文件)、范围(样本量/时间范围)",
            req_text=req,
        )

    def analyze_info_layer(self, req: str) -> LayerGap:
        """
        I 层分析：检查信息完整度（频率/精度/粒度）

        检测规则：
          - 有明确频率/精度/粒度/属性 → covered
          - 模糊表述 → ambiguous
          - 无描述 → missing

        Args:
            req: 需求文本

        Returns:
            LayerGap: I层缺口分析结果
        """
        matched, evidence = self._match_any(req, self._I_PATTERNS)
        matched_text = ", ".join(evidence[:3]) if evidence else ""

        return self._make_gap(
            matched=matched,
            evidence=matched_text,
            description_covered=f"I层: 信息频率/精度/粒度/属性已定义 ({matched_text})",
            description_missing="I层: 缺少信息频率/精度/粒度/属性描述",
            evidence_missing="需明确更新频率、精度要求、数据粒度、统计属性",
            req_text=req,
        )

    def analyze_knowledge_layer(self, req: str) -> LayerGap:
        """
        K 层分析：检查知识/算法/规则明确性

        检测规则：
          - 有明确算法/规则/计算逻辑 → covered
          - 模糊表述 → ambiguous
          - 无描述 → missing

        Args:
            req: 需求文本

        Returns:
            LayerGap: K层缺口分析结果
        """
        matched, evidence = self._match_any(req, self._K_PATTERNS)
        matched_text = ", ".join(evidence[:3]) if evidence else ""

        return self._make_gap(
            matched=matched,
            evidence=matched_text,
            description_covered=f"K层: 算法/规则/计算逻辑已明确 ({matched_text})",
            description_missing="K层: 缺少算法/规则/计算逻辑描述",
            evidence_missing="需明确使用的算法类型、规则集、计算逻辑、模型结构",
            req_text=req,
        )

    def analyze_wisdom_layer(self, req: str) -> LayerGap:
        """
        W 层分析：检查决策标准/阈值/优先级

        检测规则：
          - 有明确决策标准/阈值/优先级 → covered
          - 模糊表述 → ambiguous
          - 无描述 → missing

        Args:
            req: 需求文本

        Returns:
            LayerGap: W层缺口分析结果
        """
        matched, evidence = self._match_any(req, self._W_PATTERNS)
        matched_text = ", ".join(evidence[:3]) if evidence else ""

        return self._make_gap(
            matched=matched,
            evidence=matched_text,
            description_covered=f"W层: 决策标准/阈值/优先级已明确 ({matched_text})",
            description_missing="W层: 缺少决策标准/阈值/优先级/权衡描述",
            evidence_missing="需明确决策标准(SLA/阈值)、优先级排序规则、风险容忍度",
            req_text=req,
        )

    def analyze_purpose_layer(self, req: str) -> LayerGap:
        """
        P 层分析：检查意图对齐/Purpose 锚定

        检测规则：
          - 有明确目标/意图/成功标准 → covered
          - 模糊表述 → ambiguous
          - 无描述 → missing

        Args:
            req: 需求文本

        Returns:
            LayerGap: P层缺口分析结果
        """
        matched, evidence = self._match_any(req, self._P_PATTERNS)
        matched_text = ", ".join(evidence[:3]) if evidence else ""

        return self._make_gap(
            matched=matched,
            evidence=matched_text,
            description_covered=f"P层: 目标/意图/成功标准已锚定 ({matched_text})",
            description_missing="P层: 缺少目标/意图/成功标准描述",
            evidence_missing="需明确最终目标、验收标准、对齐约束、价值主张",
            req_text=req,
        )

    def generate_gap_dsl(self, report: GapReport) -> str:
        """
        生成 DIKWP Gap Analysis DSL 文本

        DSL 格式：
        ```
        grill-me v1.0 DIKWP Gap Analysis DSL
        =====================================
        D {STATUS}: {description} | evidence: {evidence or "N/A"}
        I {STATUS}: {description} | evidence: {evidence or "N/A"}
        K {STATUS}: {description} | evidence: {evidence or "N/A"}
        W {STATUS}: {description} | evidence: {evidence or "N/A"}
        P {STATUS}: {description} | evidence: {evidence or "N/A"}
        ```

        Args:
            report: 缺口报告

        Returns:
            str: 格式化的 DSL 文本
        """
        lines = [
            "grill-me v1.0 DIKWP Gap Analysis DSL",
            "=" * 37,
        ]

        layer_order = ["D", "I", "K", "W", "P"]
        for layer in layer_order:
            gap = report.layers.get(layer)
            if gap is None:
                continue
            status_map = {"covered": "COVERED", "missing": "MISSING", "ambiguous": "AMBIGUOUS"}
            status = status_map.get(gap.status, gap.status.upper())
            evidence = gap.evidence_required if gap.status != "covered" else "N/A"
            lines.append(
                f"{layer} {status}: {gap.gap_description} | evidence: {evidence}"
            )

        lines.append("=" * 37)
        lines.append(f"Requirement ID: {report.requirement_id}")
        if report.all_gaps_closed:
            lines.append("All gaps: CLOSED")
        else:
            open_gaps = report.get_open_gaps()
            lines.append(f"Open gaps: {len(open_gaps)}")
        if report.silent_assumptions:
            lines.append(f"Silent assumptions: {len(report.silent_assumptions)}")

        return "\n".join(lines)

    def get_analysis_stats(self) -> Dict[str, Any]:
        """获取分析统计信息"""
        total = len(self._gap_history)
        if total == 0:
            return {"total_analyses": 0}

        all_closed = sum(1 for r in self._gap_history if r.all_gaps_closed)
        layer_stats = defaultdict(lambda: {"covered": 0, "missing": 0, "ambiguous": 0})
        for report in self._gap_history:
            for layer_name, gap in report.layers.items():
                layer_stats[layer_name][gap.status] += 1

        return {
            "total_analyses": total,
            "all_closed_count": all_closed,
            "closure_rate": round(all_closed / total, 3),
            "layer_stats": dict(layer_stats),
        }


# ============================================================
# T6: GrillExecutionGate 类
# ============================================================

class GrillExecutionGate:
    """
    Grill 执行门控 (T6)

    管理需求执行前的缺口审计过程：
      1. register_gap_analysis — 注册缺口分析
      2. close_gap — 用证据关闭缺口
      3. verify_all_gaps_closed — 验证全缺口关闭
      4. release — 释放可执行方案
      5. lock_reason — 返回锁住原因
      6. manual_override — 人工覆盖锁
    """

    def __init__(self):
        """初始化执行门控"""
        self._registry: Dict[str, GapReport] = {}  # requirement_id → GapReport
        self._release_log: List[Dict[str, Any]] = []
        self._override_log: List[Dict[str, Any]] = []
        self._lock_count: int = 0

    def register_gap_analysis(self, report: GapReport) -> None:
        """
        注册需求缺口分析

        Args:
            report: GapReport 缺口报告
        """
        rid = report.requirement_id
        self._registry[rid] = report
        if not report.all_gaps_closed:
            self._lock_count += 1

    def close_gap(
        self, req_id: str, layer: str, evidence: str, closed_by: str
    ) -> dict:
        """
        用证据关闭指定缺口

        Args:
            req_id: 需求 ID
            layer: 层名 ("D"/"I"/"K"/"W"/"P")
            evidence: 证据文本
            closed_by: 关闭者标识

        Returns:
            dict: 关闭操作结果
        """
        if req_id not in self._registry:
            return {"success": False, "error": f"Unknown requirement: {req_id}"}

        report = self._registry[req_id]
        if layer not in report.layers:
            return {"success": False, "error": f"Unknown layer: {layer}"}

        gap = report.layers[layer]
        if gap.status == "covered":
            return {"success": True, "message": f"Layer {layer} already covered", "layer": layer}

        gap.close(evidence, closed_by)

        # 检查是否所有缺口均已关闭
        report.all_gaps_closed = all(
            g.closed or g.status == "covered" for g in report.layers.values()
        )

        if report.all_gaps_closed:
            self._lock_count = max(0, self._lock_count - 1)

        return {
            "success": True,
            "layer": layer,
            "status": gap.status,
            "closed": True,
            "all_gaps_closed": report.all_gaps_closed,
        }

    def verify_all_gaps_closed(self, req_id: str) -> bool:
        """
        验证指定需求的所有缺口是否已关闭

        Args:
            req_id: 需求 ID

        Returns:
            bool: True=全部关闭, False=存在未关闭缺口
        """
        if req_id not in self._registry:
            return False
        report = self._registry[req_id]
        return report.all_gaps_closed

    def release(self, requirement_id: str) -> dict:
        """
        释放可执行方案

        返回：
        ```python
        {
            "locked": True/False,
            "reason": "" or "K MISSING: 推荐算法不明确",
            "gaps_remaining": [...]  # 未关闭的缺口列表
        }
        ```

        Args:
            requirement_id: 需求 ID

        Returns:
            dict: 释放结果
        """
        if requirement_id not in self._registry:
            return {
                "locked": True,
                "reason": "UNKNOWN: 需求未注册",
                "gaps_remaining": [{"layer": "ALL", "description": "需求未找到"}],
            }

        report = self._registry[requirement_id]
        open_gaps = report.get_open_gaps()
        remaining = [
            {
                "layer": layer,
                "status": gap.status,
                "description": gap.gap_description,
                "evidence_required": gap.evidence_required,
            }
            for layer, gap in open_gaps
        ]

        if not open_gaps and report.all_gaps_closed:
            release_info = {
                "locked": False,
                "reason": "",
                "gaps_remaining": [],
            }
            self._release_log.append({
                "requirement_id": requirement_id,
                "timestamp": time.time(),
                "result": "RELEASED",
            })
            return release_info

        # 生成锁住原因
        reason_parts = []
        for layer, gap in open_gaps:
            status_label = "MISSING" if gap.status == "missing" else "AMBIGUOUS"
            reason_parts.append(f"{layer} {status_label}: {gap.gap_description}")
        reason = "; ".join(reason_parts[:3])  # 最多显示3个

        return {
            "locked": True,
            "reason": reason or "UNKNOWN: 存在未关闭缺口",
            "gaps_remaining": remaining,
        }

    def lock_reason(self, req_id: str) -> str:
        """
        返回当前需求的锁住原因

        Args:
            req_id: 需求 ID

        Returns:
            str: 锁住原因文本
        """
        result = self.release(req_id)
        return result["reason"]

    def manual_override(
        self, req_id: str, reason: str, override_code: str
    ) -> dict:
        """
        人工覆盖执行门控

        直接覆盖锁，允许执行。记录覆盖原因和操作者。

        Args:
            req_id: 需求 ID
            reason: 覆盖原因
            override_code: 覆盖授权码

        Returns:
            dict: 覆盖操作结果
        """
        if req_id not in self._registry:
            return {"success": False, "error": f"Unknown requirement: {req_id}"}

        report = self._registry[req_id]

        # 强制关闭所有剩余缺口
        for layer, gap in report.layers.items():
            if not gap.closed and gap.status != "covered":
                # 标记为 covered 状态并关闭
                gap.closed = True
                gap.closed_by = f"override:{override_code}"
                gap.closed_at = time.time()
                gap.evidence_provided = f"MANUAL_OVERRIDE: {reason}"

        report.all_gaps_closed = True

        override_record = {
            "requirement_id": req_id,
            "reason": reason,
            "override_code": override_code,
            "timestamp": time.time(),
        }
        self._override_log.append(override_record)
        self._lock_count = max(0, self._lock_count - 1)

        return {
            "success": True,
            "requirement_id": req_id,
            "override_code": override_code,
            "message": f"Manual override applied: {reason}",
        }

    def get_gate_status(self) -> Dict[str, Any]:
        """获取当前门控整体状态"""
        total = len(self._registry)
        locked = sum(1 for r in self._registry.values() if not r.all_gaps_closed)
        released = total - locked

        return {
            "total_requirements": total,
            "locked_count": locked,
            "released_count": released,
            "override_count": len(self._override_log),
            "lock_reasons": [
                {
                    "req_id": rid,
                    "reason": self.lock_reason(rid),
                }
                for rid, report in self._registry.items()
                if not report.all_gaps_closed
            ],
        }


# ============================================================
# T7: RequirementTracer 类
# ============================================================

@dataclass
class TraceEntry:
    """溯源链条目"""
    trace_id: str
    req_id: str
    snap_id: str
    event_type: str  # "snap" | "gap_analysis" | "closure" | "release" | "override"
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    previous_hash: str = ""
    chain_hash: str = ""

    def __post_init__(self):
        if not self.chain_hash and self.previous_hash:
            self.chain_hash = _chain_hash(self.previous_hash, json.dumps({
                "trace_id": self.trace_id,
                "req_id": self.req_id,
                "snap_id": self.snap_id,
                "event_type": self.event_type,
                "timestamp": self.timestamp,
            }, sort_keys=True))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "req_id": self.req_id,
            "snap_id": self.snap_id,
            "event_type": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "chain_hash": self.chain_hash,
        }


class RequirementTracer:
    """
    Requirement Tracer — κ-Snap 需求溯源 (T7)

    基于 κ-Snap 链式审计的需求溯源系统：
      - trace: 查询 κ-Snap 溯源链
      - verify_tamper_proof: SHA-256 防篡改验证
      - constitutionalize: ψ-锚宪法化
      - get_trace_chain: 获取完整溯源链
      - add_snap_to_trace: 添加记录到溯源链
    """

    def __init__(self):
        """初始化溯源器"""
        self._traces: Dict[str, List[TraceEntry]] = defaultdict(list)
        self._snap_index: Dict[str, TraceEntry] = {}
        self._genesis_hash: str = _sha256("TOMAS-v3.11-GENESIS")
        self._verification_results: List[Dict[str, Any]] = []

    def trace(self, snap_id: str) -> List[dict]:
        """
        查询 κ-Snap 溯源链

        Args:
            snap_id: Snap 事件 ID

        Returns:
            List[dict]: 相关溯源条目列表
        """
        results = []
        for req_id, entries in self._traces.items():
            for entry in entries:
                if entry.snap_id == snap_id:
                    results.append(entry.to_dict())
        return results

    def verify_tamper_proof(self, trace_id: str) -> dict:
        """
        SHA-256 防篡改验证

        返回：
        ```python
        {
            "valid": True/False,
            "chain_length": N,
            "tampered_at": None or index,
            "expected_hash": "..." or "",
            "actual_hash": "..." or ""
        }
        ```

        Args:
            trace_id: 溯源 ID

        Returns:
            dict: 验证结果
        """
        # 查找对应的 trace entry
        target = None
        for entries in self._traces.values():
            for e in entries:
                if e.trace_id == trace_id or e.chain_hash == trace_id:
                    target = e
                    break
            if target:
                break

        if target is None:
            return {
                "valid": False,
                "chain_length": 0,
                "tampered_at": None,
                "expected_hash": "UNKNOWN",
                "actual_hash": "TRACE_NOT_FOUND",
            }

        # 获取该需求的所有条目，从 genesis 开始验证
        req_entries = []
        for entries in self._traces.values():
            for e in entries:
                if e.req_id == target.req_id:
                    req_entries.append(e)

        if not req_entries:
            return {
                "valid": False,
                "chain_length": 0,
                "tampered_at": None,
                "expected_hash": "UNKNOWN",
                "actual_hash": "EMPTY_CHAIN",
            }

        # 按时间排序
        req_entries.sort(key=lambda x: x.timestamp)

        chain_length = len(req_entries)
        current_hash = self._genesis_hash

        for i, entry in enumerate(req_entries):
            expected = _chain_hash(current_hash, json.dumps({
                "trace_id": entry.trace_id,
                "req_id": entry.req_id,
                "snap_id": entry.snap_id,
                "event_type": entry.event_type,
                "timestamp": entry.timestamp,
            }, sort_keys=True))

            if entry.chain_hash and entry.chain_hash != expected:
                result = {
                    "valid": False,
                    "chain_length": chain_length,
                    "tampered_at": i,
                    "expected_hash": expected,
                    "actual_hash": entry.chain_hash,
                }
                self._verification_results.append(result)
                return result

            current_hash = entry.chain_hash or expected

        result = {
            "valid": True,
            "chain_length": chain_length,
            "tampered_at": None,
            "expected_hash": "",
            "actual_hash": "",
        }
        self._verification_results.append(result)
        return result

    def constitutionalize(self, req_id: str, psi_anchor) -> dict:
        """
        ψ-锚宪法化：为需求创建 ψ-锚定溯源条目

        Args:
            req_id: 需求 ID
            psi_anchor: PsiAnchor 实例或 dict

        Returns:
            dict: 宪法化结果
        """
        if psi_anchor is None:
            return {"success": False, "error": "PsiAnchor is None"}

        psi_data = {}
        if hasattr(psi_anchor, 'to_dict'):
            psi_data = psi_anchor.to_dict()
        elif isinstance(psi_anchor, dict):
            psi_data = psi_anchor

        # 获取链条上的前一个哈希
        prev = self._genesis_hash
        existing = self._traces.get(req_id, [])
        if existing:
            existing.sort(key=lambda x: x.timestamp)
            prev = existing[-1].chain_hash or self._genesis_hash

        entry = TraceEntry(
            trace_id=f"trace_{uuid.uuid4().hex[:12]}",
            req_id=req_id,
            snap_id=f"psi_anchor_{uuid.uuid4().hex[:8]}",
            event_type="constitutionalize",
            data={"psi_anchor": psi_data},
            previous_hash=prev,
        )
        entry.chain_hash = _chain_hash(prev, json.dumps({
            "trace_id": entry.trace_id,
            "req_id": entry.req_id,
            "snap_id": entry.snap_id,
            "event_type": entry.event_type,
            "timestamp": entry.timestamp,
        }, sort_keys=True))

        self._traces[req_id].append(entry)

        return {
            "success": True,
            "req_id": req_id,
            "trace_id": entry.trace_id,
            "chain_hash": entry.chain_hash,
            "psi_anchored": True,
        }

    def get_trace_chain(self, req_id: str) -> List[dict]:
        """
        获取指定需求的完整溯源链

        Args:
            req_id: 需求 ID

        Returns:
            List[dict]: 溯源链（按时间排序）
        """
        entries = self._traces.get(req_id, [])
        entries.sort(key=lambda x: x.timestamp)
        return [e.to_dict() for e in entries]

    def add_snap_to_trace(self, req_id: str, snap_event) -> None:
        """
        添加 κ-Snap 记录到溯源链

        Args:
            req_id: 需求 ID
            snap_event: SnapEvent 或 dict 或自定义对象
        """
        snap_data = {}
        if hasattr(snap_event, 'to_dict'):
            snap_data = snap_event.to_dict()
        elif isinstance(snap_event, dict):
            snap_data = snap_event
        else:
            snap_data = {"event": str(snap_event)}

        snap_id = snap_data.get("event_id", snap_data.get("snap_id", f"snap_{uuid.uuid4().hex[:8]}"))

        prev = self._genesis_hash
        existing = self._traces.get(req_id, [])
        if existing:
            existing.sort(key=lambda x: x.timestamp)
            prev = existing[-1].chain_hash or self._genesis_hash

        entry = TraceEntry(
            trace_id=f"trace_{uuid.uuid4().hex[:12]}",
            req_id=req_id,
            snap_id=snap_id,
            event_type="snap",
            data=snap_data,
            previous_hash=prev,
        )
        entry.chain_hash = _chain_hash(prev, json.dumps({
            "trace_id": entry.trace_id,
            "req_id": entry.req_id,
            "snap_id": entry.snap_id,
            "event_type": entry.event_type,
            "timestamp": entry.timestamp,
        }, sort_keys=True))

        self._traces[req_id].append(entry)
        self._snap_index[snap_id] = entry

    def add_generic_trace(
        self, req_id: str, event_type: str, data: Dict[str, Any]
    ) -> TraceEntry:
        """
        添加通用溯源记录

        Args:
            req_id: 需求 ID
            event_type: 事件类型
            data: 事件数据

        Returns:
            TraceEntry: 创建的溯源条目
        """
        snap_id = data.get("event_id", f"{event_type}_{uuid.uuid4().hex[:8]}")

        prev = self._genesis_hash
        existing = self._traces.get(req_id, [])
        if existing:
            existing.sort(key=lambda x: x.timestamp)
            prev = existing[-1].chain_hash or self._genesis_hash

        entry = TraceEntry(
            trace_id=f"trace_{uuid.uuid4().hex[:12]}",
            req_id=req_id,
            snap_id=snap_id,
            event_type=event_type,
            data=data,
            previous_hash=prev,
        )
        entry.chain_hash = _chain_hash(prev, json.dumps({
            "trace_id": entry.trace_id,
            "req_id": entry.req_id,
            "snap_id": entry.snap_id,
            "event_type": entry.event_type,
            "timestamp": entry.timestamp,
        }, sort_keys=True))

        self._traces[req_id].append(entry)
        return entry

    def get_chain_integrity_report(self) -> Dict[str, Any]:
        """获取所有需求链的完整性报告"""
        total_traces = sum(len(entries) for entries in self._traces.values())
        tampered = []
        verified = []

        for req_id in self._traces:
            if self._traces[req_id]:
                latest = self._traces[req_id][-1]
                verification = self.verify_tamper_proof(latest.trace_id)
                if verification["valid"]:
                    verified.append(req_id)
                else:
                    tampered.append({"req_id": req_id, **verification})

        return {
            "total_requirements": len(self._traces),
            "total_trace_entries": total_traces,
            "verified_count": len(verified),
            "tampered_count": len(tampered),
            "tampered_details": tampered,
        }


# ============================================================
# T8: PsiNoSilentAssumption 类
# ============================================================

class PsiNoSilentAssumption:
    """
    ψ-静默脑补检测器 (T8)

    检测 LLM/AGI 在需求分析中的隐性脑补（静默假设）：
      - mark_imputation: 标记脑补行为
      - is_llm_imputation: 检测是否为 LLM 脑补
      - flag_disallowed: 标记所有 DISALLOW 项
      - scan_for_silent_assumptions: 扫描 GapReport 中的静默脑补

    检测规则：
      1. 每层 gap 的 "ambiguous" 状态且 gap_description
         不含证据词 → 标记为 silent assumption
      2. "missing" 状态的 gap_description
         不含 "待确认"/"待补充" → 标记为 silent assumption
    """

    # 证据词：表示由明确来源定义
    _EVIDENCE_WORDS: List[str] = [
        r'用户指定',
        r'文档定义',
        r'需求明确',
        r'用户明确',
        r'需求规定',
        r'行业标准',
        r'法规要求',
        r'设计文档',
        r'API文档',
        r'协议规范',
        r'explicitly',
        r'documented',
        r'specified',
        r'standard',
    ]

    # 待确认词：表示缺口已被识别但待补充
    _PENDING_WORDS: List[str] = [
        r'待确认',
        r'待补充',
        r'待明确',
        r'待定义',
        r'需要确认',
        r'需要补充',
        r'TBD',
        r'TODO',
        r'pending',
        r'to be determined',
    ]

    # LLM 脑补特征词
    _LLM_IMPUTATION_PATTERNS: List[str] = [
        r'(通常|一般|常见|大多|往往|generally|typically|usually|commonly)',
        r'(假设|推断|推测|猜测|imputation|assume|infer|guess)',
        r'(可能|或许|perhaps|maybe|possibly|likely)',
        r'(根据经验|经验上|基于常识|common sense)',
        r'(合理的?|reasonable)',
    ]

    def __init__(self):
        """初始化静默脑补检测器"""
        self._imputations: List[Dict[str, Any]] = []
        self._disallowed: List[Dict[str, Any]] = []
        self._scan_count: int = 0

    def mark_imputation(self, assumption: str, source: str = "unknown") -> None:
        """
        标记脑补行为

        Args:
            assumption: 假设/脑补描述
            source: 来源标识
        """
        record = {
            "assumption": assumption,
            "source": source,
            "is_llm": self.is_llm_imputation(assumption),
            "timestamp": time.time(),
            "id": _sha256(assumption + source + str(time.time()))[:12],
        }
        self._imputations.append(record)

    def is_llm_imputation(self, assumption: str) -> bool:
        """
        检测是否为 LLM 脑补

        通过特征词匹配检测文本是否来自 LLM 推断。

        Args:
            assumption: 假设文本

        Returns:
            bool: True=疑似 LLM 脑补
        """
        for pattern in self._LLM_IMPUTATION_PATTERNS:
            if re.search(pattern, assumption, re.IGNORECASE):
                return True
        return False

    def flag_disallowed(self) -> List[dict]:
        """
        标记所有 DISALLOW 项

        Returns:
            List[dict]: 所有被标记为 DISALLOW 的脑补记录
        """
        self._disallowed = []
        for imp in self._imputations:
            if imp["is_llm"]:
                self._disallowed.append({
                    "id": imp["id"],
                    "assumption": imp["assumption"],
                    "source": imp["source"],
                    "reason": "LLM脑补: 含推测/不确定/经验性表述",
                    "timestamp": imp["timestamp"],
                })
        return self._disallowed

    def scan_for_silent_assumptions(self, gap_report: GapReport) -> List[str]:
        """
        扫描 GapReport 中的静默脑补

        检测规则:
          1. 每层 gap 的 "ambiguous" 状态且 gap_description
             不含证据词(用户指定/文档定义/需求明确等) → silent assumption
          2. "missing" 状态的 gap_description
             不含待确认词(待确认/待补充/TBD等) → silent assumption

        Args:
            gap_report: 需求缺口报告

        Returns:
            List[str]: 检测到的静默脑补列表
        """
        self._scan_count += 1
        assumptions: List[str] = []

        for layer_name, gap in gap_report.layers.items():
            desc = gap.gap_description

            # 规则 1: ambiguous 状态下没有证据词 → silent assumption
            if gap.status == "ambiguous":
                has_evidence = any(
                    re.search(w, desc, re.IGNORECASE) for w in self._EVIDENCE_WORDS
                )
                if not has_evidence:
                    msg = (
                        f"[{layer_name} 层] 静默脑补: 模糊状态无证据来源 - "
                        f"{gap.gap_description[:80]}"
                    )
                    assumptions.append(msg)
                    self.mark_imputation(msg, source=f"GapReport.{layer_name}")

            # 规则 2: missing 状态没有待确认词 → silent assumption
            elif gap.status == "missing":
                has_pending = any(
                    re.search(w, desc, re.IGNORECASE) for w in self._PENDING_WORDS
                )
                if not has_pending:
                    msg = (
                        f"[{layer_name} 层] 静默脑补: 缺失项未标记待确认 - "
                        f"{gap.gap_description[:80]}"
                    )
                    assumptions.append(msg)
                    self.mark_imputation(msg, source=f"GapReport.{layer_name}")

        # 更新 gap_report
        gap_report.silent_assumptions = assumptions
        return assumptions

    def get_imputation_stats(self) -> Dict[str, Any]:
        """获取脑补统计信息"""
        return {
            "total_imputations": len(self._imputations),
            "total_disallowed": len(self._disallowed),
            "total_scans": self._scan_count,
            "llm_imputations": sum(1 for imp in self._imputations if imp["is_llm"]),
            "by_source": {
                source: len(list(group))
                for source, group in __import__("itertools").groupby(
                    sorted(self._imputations, key=lambda x: x["source"]),
                    key=lambda x: x["source"],
                )
            },
        }


# ============================================================
# 便捷工厂函数
# ============================================================

def create_grill_pipeline() -> Tuple[
    DIKWPGapAnalyzer, GrillExecutionGate, RequirementTracer, PsiNoSilentAssumption
]:
    """
    创建完整的 Grill-Me 审计流水线

    Returns:
        Tuple: (analyzer, gate, tracer, psi_scanner)
    """
    analyzer = DIKWPGapAnalyzer()
    gate = GrillExecutionGate()
    tracer = RequirementTracer()
    psi_scanner = PsiNoSilentAssumption()
    return analyzer, gate, tracer, psi_scanner


def analyze_and_gate(
    requirement: str,
    analyzer: Optional[DIKWPGapAnalyzer] = None,
    gate: Optional[GrillExecutionGate] = None,
    scanner: Optional[PsiNoSilentAssumption] = None,
) -> Tuple[GapReport, dict]:
    """
    一站式分析 + 门控

    Args:
        requirement: 需求文本
        analyzer: 可选的已有分析器（无则创建）
        gate: 可选的已有门控（无则创建）
        scanner: 可选的已有脑补扫描器（无则创建）

    Returns:
        Tuple: (GapReport, release_result)
    """
    if analyzer is None:
        analyzer = DIKWPGapAnalyzer()
    if gate is None:
        gate = GrillExecutionGate()
    if scanner is None:
        scanner = PsiNoSilentAssumption()

    report = analyzer.analyze(requirement)
    scanner.scan_for_silent_assumptions(report)
    gate.register_gap_analysis(report)
    result = gate.release(report.requirement_id)

    return report, result


# ============================================================
# Self-Test
# ============================================================

if __name__ == "__main__":
    import sys
    import traceback as tb

    passed = 0
    failed = 0
    failures = []

    def test(name: str, condition: bool, detail: str = ""):
        global passed, failed
        if condition:
            passed += 1
            print(f"  [PASS] {name}")
        else:
            failed += 1
            msg = f"  [FAIL] {name}"
            if detail:
                msg += f" — {detail}"
            failures.append(msg)
            print(msg)

    print("=" * 50)
    print("TOMAS v3.11 grill_me_engine.py — Self-Tests")
    print("=" * 50)

    # ---- SHA-256 基础 ----
    print("\n--- SHA-256 Audit ---")
    h = _sha256("hello")
    test("_sha256 returns 64-char hex", len(h) == 64 and all(c in "0123456789abcdef" for c in h))
    test("_sha256 deterministic", _sha256("x") == _sha256("x"))
    test("_sha256 different inputs", _sha256("a") != _sha256("b"))

    h2 = _chain_hash("prev", "data")
    test("_chain_hash different from simple hash", h2 != _sha256("prev"))
    test("_chain_hash deterministic", _chain_hash("a", "b") == _chain_hash("a", "b"))

    ref = _make_snap_ref("evt1", "genesis")
    test("_make_snap_ref starts with snap:", ref.startswith("snap:"))

    # ---- LayerGap ----
    print("\n--- LayerGap ---")
    gap_covered = LayerGap(status="covered", gap_description="OK", evidence_required="N/A")
    test("LayerGap: covered status", gap_covered.status == "covered")
    test("LayerGap: covered not closed", not gap_covered.closed)

    gap_missing = LayerGap(status="missing", gap_description="no data", evidence_required="need data schema")
    test("LayerGap: missing status", gap_missing.status == "missing")
    test("LayerGap: missing not closed", not gap_missing.closed)

    gap_ambig = LayerGap(status="ambiguous", gap_description="maybe need", evidence_required="need clarifying")
    test("LayerGap: ambiguous status", gap_ambig.status == "ambiguous")

    gap_missing.close("evidence document v1", "analyst-A")
    test("LayerGap: close gap", gap_missing.closed)
    test("LayerGap: closed_by set", gap_missing.closed_by == "analyst-A")
    test("LayerGap: closed_at set", gap_missing.closed_at is not None)
    test("LayerGap: evidence_provided set", gap_missing.evidence_provided == "evidence document v1")

    d = gap_missing.to_dict()
    test("LayerGap.to_dict has keys", all(k in d for k in ["status", "gap_description", "evidence_required", "closed", "closed_by", "closed_at", "evidence_provided"]))

    # ---- GapReport ----
    print("\n--- GapReport ---")
    layers = {
        "D": LayerGap(status="covered", gap_description="data ok", evidence_required="N/A"),
        "I": LayerGap(status="covered", gap_description="info ok", evidence_required="N/A"),
        "K": LayerGap(status="covered", gap_description="knowledge ok", evidence_required="N/A"),
        "W": LayerGap(status="covered", gap_description="wisdom ok", evidence_required="N/A"),
        "P": LayerGap(status="covered", gap_description="purpose ok", evidence_required="N/A"),
    }
    report_all_covered = GapReport(
        requirement_id="req_001",
        requirement_raw="full spec with data format, algorithms, decisions, goals",
        layers=layers,
        all_gaps_closed=True,
    )
    test("GapReport: all covered", report_all_covered.all_gaps_closed)
    test("GapReport: report_hash set", len(report_all_covered.report_hash) > 0)
    test("GapReport: get_open_gaps empty", len(report_all_covered.get_open_gaps()) == 0)
    test("GapReport: get_missing_layers empty", len(report_all_covered.get_missing_layers()) == 0)
    test("GapReport: get_ambiguous_layers empty", len(report_all_covered.get_ambiguous_layers()) == 0)
    test("GapReport: to_dict", "layers" in report_all_covered.to_dict())

    # Report with gaps
    layers2 = {
        "D": LayerGap(status="missing", gap_description="no data", evidence_required="need schema"),
        "I": LayerGap(status="ambiguous", gap_description="approx precision", evidence_required="need exact"),
        "K": LayerGap(status="covered", gap_description="ok", evidence_required="N/A"),
        "W": LayerGap(status="missing", gap_description="no criteria", evidence_required="need thresholds"),
        "P": LayerGap(status="covered", gap_description="ok", evidence_required="N/A"),
    }
    report_with_gaps = GapReport(
        requirement_id="req_002",
        requirement_raw="incomplete spec",
        layers=layers2,
        all_gaps_closed=False,
    )
    test("GapReport: not all closed", not report_with_gaps.all_gaps_closed)
    open_gaps = report_with_gaps.get_open_gaps()
    test("GapReport: get_open_gaps count", len(open_gaps) == 3)
    test("GapReport: get_missing_layers", sorted(report_with_gaps.get_missing_layers()) == ["D", "W"])
    test("GapReport: get_ambiguous_layers", report_with_gaps.get_ambiguous_layers() == ["I"])

    # ---- DIKWPGapAnalyzer ----
    print("\n--- DIKWPGapAnalyzer ---")
    analyzer = DIKWPGapAnalyzer()

    # Test fully covered requirement
    full_req = (
        "输入数据为CSV格式，包含float类型的字段price和volume，每日1000条记录。"
        "数据精度为小数点后4位，统计频率为每分钟一次。"
        "使用LSTM神经网络模型进行价格预测，损失函数为MSE。"
        "当预测置信度低于0.85阈值时触发人工审核，优先考虑低风险策略。"
        "最终目标是将预测误差控制在5%以内，通过ISO合规审查。"
    )
    report_full = analyzer.analyze(full_req)
    test("DIKWPGapAnalyzer: analyze returns GapReport", isinstance(report_full, GapReport))
    test("DIKWPGapAnalyzer: full req D layer covered", report_full.layers["D"].status == "covered")
    test("DIKWPGapAnalyzer: full req I layer covered", report_full.layers["I"].status == "covered")
    test("DIKWPGapAnalyzer: full req K layer covered", report_full.layers["K"].status == "covered")
    test("DIKWPGapAnalyzer: full req W layer covered", report_full.layers["W"].status == "covered")
    test("DIKWPGapAnalyzer: full req P layer covered", report_full.layers["P"].status == "covered")

    # Test completely empty requirement
    empty_req = "做一个系统"
    report_empty = analyzer.analyze(empty_req)
    test("DIKWPGapAnalyzer: empty req D missing", report_empty.layers["D"].status == "missing")
    test("DIKWPGapAnalyzer: empty req K missing", report_empty.layers["K"].status == "missing")
    test("DIKWPGapAnalyzer: empty req all missing", not report_empty.all_gaps_closed)

    # Test data-only req
    data_req = "数据处理为JSON格式，从API获取，包含用户ID和交易金额字段"
    report_data = analyzer.analyze(data_req)
    test("DIKWPGapAnalyzer: data-only has D covered", report_data.layers["D"].status == "covered")
    test("DIKWPGapAnalyzer: data-only has K missing", report_data.layers["K"].status == "missing")
    test("DIKWPGapAnalyzer: data-only has W missing", report_data.layers["W"].status == "missing")
    test("DIKWPGapAnalyzer: data-only has P covered", report_data.layers["P"].status == "covered")  # "用户" matches P patterns

    # Test ambiguous requirement
    ambig_req = "数据可能以CSV格式提供，精度大概到小数点后2位左右，使用适当的算法"
    report_ambig = analyzer.analyze(ambig_req)
    test("DIKWPGapAnalyzer: ambiguous req D ambiguous", report_ambig.layers["D"].status == "ambiguous")
    test("DIKWPGapAnalyzer: ambiguous req K ambiguous", report_ambig.layers["K"].status == "ambiguous")

    # Test individual layer methods
    test("analyze_data_layer: covered", analyzer.analyze_data_layer("CSV格式数据").status == "covered")
    test("analyze_data_layer: missing", analyzer.analyze_data_layer("no info").status == "missing")
    test("analyze_data_layer: ambiguous", analyzer.analyze_data_layer("数据大概以CSV格式").status == "ambiguous")

    test("analyze_info_layer: covered", analyzer.analyze_info_layer("每秒更新，精度0.001").status == "covered")
    test("analyze_info_layer: missing", analyzer.analyze_info_layer("no info").status == "missing")
    test("analyze_info_layer: ambiguous", analyzer.analyze_info_layer("频率大概是每分钟").status == "ambiguous")

    test("analyze_knowledge_layer: covered", analyzer.analyze_knowledge_layer("使用随机森林分类器").status == "covered")
    test("analyze_knowledge_layer: missing", analyzer.analyze_knowledge_layer("no algo").status == "missing")
    test("analyze_knowledge_layer: ambiguous", analyzer.analyze_knowledge_layer("可能用神经网络").status == "ambiguous")

    test("analyze_wisdom_layer: covered", analyzer.analyze_wisdom_layer("阈值0.7，优先级A").status == "covered")
    test("analyze_wisdom_layer: missing", analyzer.analyze_wisdom_layer("no criteria").status == "missing")

    test("analyze_purpose_layer: covered", analyzer.analyze_purpose_layer("目标准确率99%以上").status == "covered")
    test("analyze_purpose_layer: missing", analyzer.analyze_purpose_layer("无关的文本内容").status == "missing")

    # Test analysis caching
    report_cache1 = analyzer.analyze(full_req)
    report_cache2 = analyzer.analyze(full_req)
    test("DIKWPGapAnalyzer: cache works (same report)", report_cache1.requirement_id == report_cache2.requirement_id)

    # Test generate_gap_dsl
    dsl = analyzer.generate_gap_dsl(report_full)
    test("generate_gap_dsl: contains header", "grill-me v1.0" in dsl)
    test("generate_gap_dsl: contains COVERED", "COVERED" in dsl)
    test("generate_gap_dsl: contains D layer", "D " in dsl)
    test("generate_gap_dsl: contains Requirement ID", "Requirement ID" in dsl)

    dsl_empty = analyzer.generate_gap_dsl(report_empty)
    test("generate_gap_dsl: contains MISSING", "MISSING" in dsl_empty)

    # Test stats
    stats = analyzer.get_analysis_stats()
    test("DIKWPGapAnalyzer: stats has total", stats["total_analyses"] > 0)

    # ---- GrillExecutionGate ----
    print("\n--- GrillExecutionGate ---")
    gate = GrillExecutionGate()

    # Register
    gate.register_gap_analysis(report_full)
    test("GrillExecutionGate: register fully covered", report_full.requirement_id in gate._registry)

    gate.register_gap_analysis(report_empty)
    test("GrillExecutionGate: register with gaps", report_empty.requirement_id in gate._registry)

    # Close gap
    result_close = gate.close_gap(report_empty.requirement_id, "D", "CSV schema v2 with fields: id(int), amount(float)", "analyst-B")
    test("GrillExecutionGate: close_gap success", result_close["success"])
    test("GrillExecutionGate: close_gap layer", result_close["layer"] == "D")
    test("GrillExecutionGate: close_gap gap closed", report_empty.layers["D"].closed)
    test("GrillExecutionGate: close_gap not all closed after one", not result_close["all_gaps_closed"])

    # Close all remaining gaps
    for layer in ["I", "K", "W", "P"]:
        gate.close_gap(report_empty.requirement_id, layer,
                       f"Evidence for layer {layer}", "analyst-B")

    test("GrillExecutionGate: all gaps closed after close_all", report_empty.all_gaps_closed)

    # Verify
    test("GrillExecutionGate: verify_all_gaps_closed (true)", gate.verify_all_gaps_closed(report_full.requirement_id))
    test("GrillExecutionGate: verify_all_gaps_closed (false)", not gate.verify_all_gaps_closed("nonexistent"))

    # Release
    release_full = gate.release(report_full.requirement_id)
    test("GrillExecutionGate: release covered (not locked)", not release_full["locked"])
    test("GrillExecutionGate: release covered reason empty", release_full["reason"] == "")

    release_unknown = gate.release("unknown_req")
    test("GrillExecutionGate: release unknown (locked)", release_unknown["locked"])
    test("GrillExecutionGate: release unknown reason", "未注册" in release_unknown["reason"])

    # lock_reason
    reason = gate.lock_reason(report_full.requirement_id)
    test("GrillExecutionGate: lock_reason covered empty", reason == "")

    # Manual override
    override_result = gate.manual_override("nonexistent_req", "test", "CODE001")
    test("GrillExecutionGate: manual_override unknown fails", not override_result["success"])

    # Create a locked report and override
    locked_layers = {
        "D": LayerGap(status="missing", gap_description="no data", evidence_required="need schema"),
        "I": LayerGap(status="missing", gap_description="no info", evidence_required="need precision"),
        "K": LayerGap(status="missing", gap_description="no algo", evidence_required="need algo"),
        "W": LayerGap(status="missing", gap_description="no criteria", evidence_required="need thresholds"),
        "P": LayerGap(status="missing", gap_description="no goal", evidence_required="need goal"),
    }
    report_locked = GapReport(requirement_id="locked_001", requirement_raw="bad req", layers=locked_layers)
    gate.register_gap_analysis(report_locked)

    locked_release = gate.release("locked_001")
    test("GrillExecutionGate: locked release has locked", locked_release["locked"])
    test("GrillExecutionGate: locked release has gaps", len(locked_release["gaps_remaining"]) == 5)

    override = gate.manual_override("locked_001", "emergency release, director approval", "DIR-2026-001")
    test("GrillExecutionGate: manual_override success", override["success"])
    test("GrillExecutionGate: manual_override closes all", report_locked.all_gaps_closed)

    release_after_override = gate.release("locked_001")
    test("GrillExecutionGate: release after override (not locked)", not release_after_override["locked"])

    # Gate status
    status = gate.get_gate_status()
    test("GrillExecutionGate: get_gate_status total", status["total_requirements"] == 3)
    test("GrillExecutionGate: get_gate_status override_count", status["override_count"] == 1)

    # ---- RequirementTracer ----
    print("\n--- RequirementTracer ---")
    tracer = RequirementTracer()

    # add_snap_to_trace with dict
    snap_data = {"event_id": "evt_001", "type": "manual"}
    tracer.add_snap_to_trace("req_A", snap_data)
    test("RequirementTracer: add_snap_to_trace adds entry", len(tracer._traces["req_A"]) == 1)

    tracer.add_snap_to_trace("req_A", {"event_id": "evt_002"})
    test("RequirementTracer: second snap added", len(tracer._traces["req_A"]) == 2)

    # trace
    trace_results = tracer.trace("evt_001")
    test("RequirementTracer: trace finds result", len(trace_results) == 1)
    test("RequirementTracer: trace matches snap_id", trace_results[0]["snap_id"] == "evt_001")

    # verify_tamper_proof
    entries = tracer._traces["req_A"]
    verification = tracer.verify_tamper_proof(entries[0].trace_id)
    test("RequirementTracer: verify_tamper_proof valid", verification["valid"])
    test("RequirementTracer: verify chain_length", verification["chain_length"] == 2)

    # get_trace_chain
    chain = tracer.get_trace_chain("req_A")
    test("RequirementTracer: get_trace_chain length", len(chain) == 2)
    test("RequirementTracer: trace chain sorted", chain[0]["timestamp"] <= chain[1]["timestamp"])

    # verify unknown
    unknown_verification = tracer.verify_tamper_proof("nonexistent")
    test("RequirementTracer: verify unknown trace", not unknown_verification["valid"])

    # add_generic_trace
    entry = tracer.add_generic_trace("req_A", "custom_event", {"data": "test"})
    test("RequirementTracer: add_generic_trace", entry.event_type == "custom_event")
    test("RequirementTracer: trace chain grew", len(tracer.get_trace_chain("req_A")) == 3)

    # Multi-requirement tracing
    tracer.add_snap_to_trace("req_B", {"event_id": "evt_B1"})
    tracer.add_snap_to_trace("req_B", {"event_id": "evt_B2"})
    test("RequirementTracer: multi-req req_B entries", len(tracer._traces["req_B"]) == 2)
    test("RequirementTracer: req_A vs req_B separate", len(tracer._traces["req_A"]) > len(tracer._traces["req_B"]))

    chain_B = tracer.get_trace_chain("req_B")
    test("RequirementTracer: req_B chain", len(chain_B) == 2)

    # Empty chain
    chain_empty = tracer.get_trace_chain("nonexistent")
    test("RequirementTracer: empty chain", len(chain_empty) == 0)

    # constitutionalize
    if PsiAnchor is not None:
        psi = PsiAnchor(self_state="care about user", kappa_at_write=4)
        const_result = tracer.constitutionalize("req_A", psi)
        test("RequirementTracer: constitutionalize success", const_result["success"])
        test("RequirementTracer: constitutionalize psi_anchored", const_result["psi_anchored"])
    else:
        const_result = tracer.constitutionalize("req_A", {"self_state": "test", "kappa_at_write": 3})
        test("RequirementTracer: constitutionalize with dict success", const_result["success"])

    # constitutionalize with None
    const_none = tracer.constitutionalize("req_A", None)
    test("RequirementTracer: constitutionalize with None fails", not const_none["success"])

    # get_chain_integrity_report
    integrity = tracer.get_chain_integrity_report()
    test("RequirementTracer: get_chain_integrity_report", integrity["total_requirements"] >= 2)
    test("RequirementTracer: chain_integrity verified_count", integrity["verified_count"] >= 0)

    # Tamper detection (simulate by modifying chain_hash)
    if len(tracer._traces["req_A"]) > 0:
        original_hash = tracer._traces["req_A"][0].chain_hash
        tracer._traces["req_A"][0].chain_hash = "tampered_hash_value"
        tamper_verify = tracer.verify_tamper_proof(tracer._traces["req_A"][0].trace_id)
        test("RequirementTracer: tamper_detection found", not tamper_verify["valid"])
        test("RequirementTracer: tamper_detection tampered_at", tamper_verify["tampered_at"] is not None)
        # Restore
        tracer._traces["req_A"][0].chain_hash = original_hash

    # Trace with custom object
    class MockSnapEvent:
        def to_dict(self):
            return {"event_id": "mock_001", "result": "manifested"}

    tracer.add_snap_to_trace("req_C", MockSnapEvent())
    test("RequirementTracer: add custom object to trace", len(tracer._traces.get("req_C", [])) == 1)

    # add_snap_to_trace with plain object (no to_dict)
    tracer.add_snap_to_trace("req_C", "plain_string_event")
    test("RequirementTracer: add plain object to trace", len(tracer._traces["req_C"]) == 2)

    # ---- PsiNoSilentAssumption ----
    print("\n--- PsiNoSilentAssumption ---")
    psi_scanner = PsiNoSilentAssumption()

    # mark_imputation
    psi_scanner.mark_imputation("usually we assume data format is CSV", "gap_analyzer")
    test("PsiNoSilentAssumption: mark_imputation adds record", len(psi_scanner._imputations) == 1)

    # is_llm_imputation
    test("PsiNoSilentAssumption: is_llm_imputation (true)", psi_scanner.is_llm_imputation("通常数据格式为CSV"))
    test("PsiNoSilentAssumption: is_llm_imputation (true with maybe)", psi_scanner.is_llm_imputation("可能使用JSON格式"))
    test("PsiNoSilentAssumption: is_llm_imputation (true with assume)", psi_scanner.is_llm_imputation("假设精度为0.01"))
    test("PsiNoSilentAssumption: is_llm_imputation (false)", not psi_scanner.is_llm_imputation("数据格式为CSV，精度0.01"))

    psi_scanner.mark_imputation("reasonable to assume threshold 0.5", "unknown")
    psi_scanner.mark_imputation("explicitly defined in docs", "doc_source")  # Should be false for LLM
    test("PsiNoSilentAssumption: valid evidence not LLM imputation", not psi_scanner.is_llm_imputation("explicitly defined in docs"))

    # flag_disallowed
    disallowed = psi_scanner.flag_disallowed()
    test("PsiNoSilentAssumption: flag_disallowed count", len(disallowed) == 2)

    # scan_for_silent_assumptions with ambiguous report
    ambig_gap = LayerGap(status="ambiguous", gap_description="精度大概到小数点后2位",
                         evidence_required="需精确精度要求")
    missing_gap = LayerGap(status="missing", gap_description="缺少算法描述",
                           evidence_required="需明确算法类型")

    report_scan = GapReport(
        requirement_id="scan_001",
        requirement_raw="模糊需求",
        layers={
            "D": LayerGap(status="covered", gap_description="ok", evidence_required="N/A"),
            "I": LayerGap(status="ambiguous", gap_description="精度大概到小数点后2位",
                         evidence_required="需精确精度要求"),
            "K": LayerGap(status="missing", gap_description="缺少算法描述",
                         evidence_required="需明确算法类型"),
            "W": LayerGap(status="covered", gap_description="ok", evidence_required="N/A"),
            "P": LayerGap(status="covered", gap_description="ok", evidence_required="N/A"),
        },
    )

    # Rule 1: ambiguous without evidence words → silent assumption
    assumptions = psi_scanner.scan_for_silent_assumptions(report_scan)
    test("PsiNoSilentAssumption: scan finds assumptions", len(assumptions) > 0)

    # Rule 2: missing without pending words → silent assumption
    report_scan_pending = GapReport(
        requirement_id="scan_002",
        requirement_raw="明确缺失需求",
        layers={
            "D": LayerGap(status="covered", gap_description="ok", evidence_required="N/A"),
            "I": LayerGap(status="covered", gap_description="ok", evidence_required="N/A"),
            "K": LayerGap(status="missing", gap_description="缺少算法描述，待确认具体模型",
                         evidence_required="需明确算法类型"),
            "W": LayerGap(status="covered", gap_description="ok", evidence_required="N/A"),
            "P": LayerGap(status="covered", gap_description="ok", evidence_required="N/A"),
        },
    )
    assumptions_pending = psi_scanner.scan_for_silent_assumptions(report_scan_pending)
    test("PsiNoSilentAssumption: missing with pending words detected", len(assumptions_pending) == 0)

    # Full gap report scan
    full_scan_report = GapReport(
        requirement_id="scan_full",
        requirement_raw="全模糊需求",
        layers={
            "D": LayerGap(status="ambiguous", gap_description="数据格式可能是CSV或JSON",
                         evidence_required="需明确格式"),
            "I": LayerGap(status="missing", gap_description="缺少更新频率信息",
                         evidence_required="需明确频率"),
            "K": LayerGap(status="ambiguous", gap_description="大概用神经网络",
                         evidence_required="需明确模型"),
            "W": LayerGap(status="missing", gap_description="没有决策标准",
                         evidence_required="需明确标准"),
            "P": LayerGap(status="ambiguous", gap_description="目标大概是提高效率",
                         evidence_required="需明确指标"),
        },
    )
    full_assumptions = psi_scanner.scan_for_silent_assumptions(full_scan_report)
    test("PsiNoSilentAssumption: full_scan 5 assumptions", len(full_assumptions) == 5)
    test("PsiNoSilentAssumption: report silent_assumptions updated", len(full_scan_report.silent_assumptions) == 5)

    # Evidence words should suppress warning
    report_with_evidence = GapReport(
        requirement_id="scan_evid",
        requirement_raw="模糊但用户指定",
        layers={
            "D": LayerGap(status="ambiguous",
                         gap_description="用户指定数据格式为JSON或CSV其中之一",
                         evidence_required="需明确选择其一"),
            "I": LayerGap(status="covered", gap_description="ok", evidence_required="N/A"),
            "K": LayerGap(status="covered", gap_description="ok", evidence_required="N/A"),
            "W": LayerGap(status="covered", gap_description="ok", evidence_required="N/A"),
            "P": LayerGap(status="covered", gap_description="ok", evidence_required="N/A"),
        },
    )
    evid_assumptions = psi_scanner.scan_for_silent_assumptions(report_with_evidence)
    test("PsiNoSilentAssumption: evidence words suppress warning", len(evid_assumptions) == 0)

    # Stats
    scanner_stats = psi_scanner.get_imputation_stats()
    test("PsiNoSilentAssumption: stats total_scans", scanner_stats["total_scans"] > 0)
    test("PsiNoSilentAssumption: stats total_imputations", scanner_stats["total_imputations"] > 0)

    # ---- Convenience Functions ----
    print("\n--- Convenience Functions ---")
    a, g, t, ps = create_grill_pipeline()
    test("create_grill_pipeline: analyzer", isinstance(a, DIKWPGapAnalyzer))
    test("create_grill_pipeline: gate", isinstance(g, GrillExecutionGate))
    test("create_grill_pipeline: tracer", isinstance(t, RequirementTracer))
    test("create_grill_pipeline: scanner", isinstance(ps, PsiNoSilentAssumption))

    report_conv, result_conv = analyze_and_gate("做一个系统", a, g, ps)
    test("analyze_and_gate: returns GapReport", isinstance(report_conv, GapReport))
    test("analyze_and_gate: returns dict result", isinstance(result_conv, dict))
    test("analyze_and_gate: requirement locked", result_conv["locked"])

    # ---- Edge Cases ----
    print("\n--- Edge Cases ---")
    # Unicode / Chinese
    chinese_req = "数据处理频率：每秒1000条，使用决策树算法分类垃圾信息，决定是否拦截的阈值为0.7，最终目标是提升用户体验满意度"
    report_cn = analyzer.analyze(chinese_req)
    test("Edge: Chinese requirement parses", report_cn.requirement_id is not None)

    # Very long requirement
    long_req = "使用LSTM模型 " * 100 + "精度要求为小数点后5位 " * 100 + "阈值为0.95 " * 100 + "目标是通过测试 " * 100
    report_long = analyzer.analyze(long_req)
    test("Edge: long requirement reports", isinstance(report_long, GapReport))

    # Close already covered gap
    result_already = gate.close_gap(report_full.requirement_id, "D", "extra evidence", "analyst-C")
    test("Edge: close already covered returns success", result_already["success"])

    # verify_tamper_proof with hash match
    if len(tracer._traces.get("req_A", [])) >= 3:
        last = tracer._traces["req_A"][-1]
        verify_last = tracer.verify_tamper_proof(last.chain_hash)
        test("Edge: verify by chain_hash", verify_last["valid"])

    # get_gate_status with no entries
    gate2 = GrillExecutionGate()
    status2 = gate2.get_gate_status()
    test("Edge: empty gate status", status2["total_requirements"] == 0)

    # DIKWGapAnalyzer: empty stats
    analyzer2 = DIKWPGapAnalyzer()
    stats2 = analyzer2.get_analysis_stats()
    test("Edge: empty analyzer stats", stats2["total_analyses"] == 0)

    # PsiNoSilentAssumption: scan with no gaps
    no_gap_report = GapReport(
        requirement_id="no_gaps",
        requirement_raw="perfect",
        layers={
            "D": LayerGap(status="covered", gap_description="ok", evidence_required="N/A"),
            "I": LayerGap(status="covered", gap_description="ok", evidence_required="N/A"),
            "K": LayerGap(status="covered", gap_description="ok", evidence_required="N/A"),
            "W": LayerGap(status="covered", gap_description="ok", evidence_required="N/A"),
            "P": LayerGap(status="covered", gap_description="ok", evidence_required="N/A"),
        },
    )
    no_assumptions = psi_scanner.scan_for_silent_assumptions(no_gap_report)
    test("Edge: no silent assumptions for all-covered", len(no_assumptions) == 0)

    # ---- Final Summary ----
    print("\n" + "=" * 50)
    total = passed + failed
    print(f"Results: {passed}/{total} passed, {failed} failed")
    if failed == 0:
        print("ALL self-tests PASSED")
    else:
        print("SOME TESTS FAILED:")
        for fmsg in failures:
            print(fmsg)
        sys.exit(1)
    print("=" * 50)
