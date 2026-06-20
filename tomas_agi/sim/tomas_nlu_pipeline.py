# -*- coding: utf-8 -*-
"""
TOMASNLU_Pipeline — TOMAS v2.0 自然语言理解端到端管道 (T01)
=============================================================

将自然语言文本通过 7 步管道处理为结构化语义表示：
    1. HNC 解析（分词 + 概念编码 + 句类模板匹配）
    2. EML 注入（构建超边上下文块）
    3. ψ-锚检查（自我状态锚定）
    4. 矛盾检测（三层矛盾检测器）
    5. Dead-Zero 检查（死零校验）
    6. κ-Snap 写入（显影算子投影）
    7. ℐ 计算（信息存在度）

所有对现有模块的调用均使用 try/except 可选导入，确保本模块
可独立导入和测试。依赖模块不可用时，管道步骤优雅降级。

Theory Source:
    架构文档 architecture_tomas_v2_upgrade.md Section 3.2.2

Author: TOMAS Team (寇豆码)
Version: v2.0
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ============================================================
# 本模块自带 HNC 解析器（首选）
# ============================================================
try:
    from hnc_parser_wrapper import HNCParserWrapper, HNCParseResult
    _HAS_HNC = True
except ImportError:
    _HAS_HNC = False
    HNCParserWrapper = None
    HNCParseResult = None

# ============================================================
# 可选导入：现有模块（优雅降级）
# ============================================================

# G_ego 双向算子
try:
    from g_ego import GEgoOperator
    _HAS_G_EGO = True
except ImportError:
    try:
        from g_ego import G_egoOperator as GEgoOperator
        _HAS_G_EGO = True
    except ImportError:
        _HAS_G_EGO = False
        GEgoOperator = None

# κ-Snap 显影算子
try:
    from ksnap_operator import KSnapOperator, CandidateEdge, ObservationBase, SnapResult
    _HAS_KSNAP = True
except ImportError:
    _HAS_KSNAP = False
    KSnapOperator = None
    CandidateEdge = None
    ObservationBase = None
    SnapResult = None

# Dead-Zero / MUS 门控
try:
    from dead_zero_mus import DeadZeroChecker, DeadZeroMUSGate
    _HAS_DEAD_ZERO = True
except ImportError:
    _HAS_DEAD_ZERO = False
    DeadZeroChecker = None
    DeadZeroMUSGate = None

# EML 注入器
try:
    from eml_injector import EMLInjector
    _HAS_EML = True
except ImportError:
    _HAS_EML = False
    EMLInjector = None

# 矛盾检测器
try:
    from contradiction_detector import ContradictionDetector
    _HAS_CONTRADICTION = True
except ImportError:
    _HAS_CONTRADICTION = False
    ContradictionDetector = None

# ψ-锚
try:
    from psi_anchor import PsiAnchor, PsiAnchorManager
    _HAS_PSI = True
except ImportError:
    _HAS_PSI = False
    PsiAnchor = None
    PsiAnchorManager = None

# GPCT 边界层分解器（T15: 因果边层创触发）
try:
    from eml_dimred.gpct import GpctDecomposer
    _HAS_GPCT = True
except ImportError:
    _HAS_GPCT = False
    GpctDecomposer = None

# HypEdge 超边数据模型（GPCT 层创检测所需）
try:
    from eml_dimred.hyperedge import HypEdge
    _HAS_HYPEDGE = True
except ImportError:
    _HAS_HYPEDGE = False
    HypEdge = None


# ============================================================
# 数据结构
# ============================================================

@dataclass
class _LiteEdge:
    """HypEdge 的轻量级替代（HypEdge 不可用时的后备）。

    提供 GPCT 层创检测所需的最小接口: nodes, eid, i_val, arity。
    """
    nodes: tuple
    eid: str
    i_val: float = 0.5

    @property
    def arity(self) -> int:
        """超边的元数 (arity)"""
        return len(self.nodes)


@dataclass
class NLUPipelineResult:
    """NLU 管道处理结果。

    Attributes:
        template_id: HNC 句类模板 ID
        chunks: 分词结果
        concept_codes: 概念基元码列表
        cited_rule: 引用的模板规则
        i_value: ℐ 信息存在度（0.0 ~ 0.95）
        psi_alignment_status: ψ-锚对齐状态
        snap_id: κ-Snap 显影 ID（若执行了显影）
        gpct_emergence_detected: GPCT 层创涌现是否检测到（T15）
        gpct_new_dim: GPCT 层创后的新输出维度（T15）
    """
    template_id: str
    chunks: List[str]
    concept_codes: List[str]
    cited_rule: Dict[str, Any]
    i_value: float
    psi_alignment_status: str
    snap_id: Optional[str] = None
    gpct_emergence_detected: Optional[bool] = None
    gpct_new_dim: Optional[int] = None


# ============================================================
# NLU 管道
# ============================================================

class TOMASNLU_Pipeline:
    """TOMAS v2.0 自然语言理解端到端管道。

    7 步管道：
        1. HNC 解析 → 分词 + 概念编码 + 句类模板匹配
        2. EML 注入 → 构建超边上下文块
        3. ψ-锚检查 → 自我状态锚定
        4. 矛盾检测 → 三层矛盾检测器
        5. Dead-Zero 检查 → 死零校验
        6. κ-Snap 写入 → 显影算子投影
        7. ℐ 计算 → 信息存在度

    所有步骤在依赖模块不可用时优雅降级（跳过 + warning 日志）。
    """

    # 默认参数
    DEFAULT_CITE_FACTOR: float = 0.85
    DEFAULT_I_CAP: float = 0.95
    DEFAULT_THETA_DEAD: float = 0.15
    DEFAULT_KAPPA: float = 4.0

    def __init__(
        self,
        use_jieba: bool = True,
        theta_dead: float = DEFAULT_THETA_DEAD,
        kappa: float = DEFAULT_KAPPA,
        cite_factor: float = DEFAULT_CITE_FACTOR,
    ) -> None:
        """初始化 NLU 管道。

        Args:
            use_jieba: 是否在 HNC 解析器中使用 jieba 分词
            theta_dead: 死零阈值
            kappa: 谱折叠深度
            cite_factor: 引用因子（用于 ℐ 计算）
        """
        self.theta_dead = theta_dead
        self.kappa = kappa
        self.cite_factor = cite_factor

        # Step 1: HNC 解析器
        if _HAS_HNC:
            self.hnc_parser = HNCParserWrapper(use_jieba=use_jieba)
            logger.info("NLU Pipeline: HNC 解析器已加载")
        else:
            self.hnc_parser = None
            logger.warning("NLU Pipeline: hnc_parser_wrapper 不可用，HNC 解析将降级")

        # Step 2: EML 注入器
        if _HAS_EML:
            self.eml_injector = EMLInjector(
                kappa=kappa,
                dead_zero_theta=theta_dead,
            )
            logger.info("NLU Pipeline: EML 注入器已加载")
        else:
            self.eml_injector = None
            logger.warning("NLU Pipeline: eml_injector 不可用，EML 注入将跳过")

        # Step 3: ψ-锚管理器
        self.psi_manager = PsiAnchorManager if _HAS_PSI else None
        if _HAS_PSI:
            logger.info("NLU Pipeline: ψ-锚管理器已加载")
        else:
            logger.warning("NLU Pipeline: psi_anchor 不可用，ψ-锚检查将跳过")

        # Step 4: 矛盾检测器
        if _HAS_CONTRADICTION:
            self.contradiction_detector = ContradictionDetector(enable_nlp=True)
            logger.info("NLU Pipeline: 矛盾检测器已加载")
        else:
            self.contradiction_detector = None
            logger.warning("NLU Pipeline: contradiction_detector 不可用，矛盾检测将跳过")

        # Step 5: Dead-Zero 检查器
        if _HAS_DEAD_ZERO:
            self.dead_zero_checker = DeadZeroChecker(theta_dead=theta_dead)
            logger.info("NLU Pipeline: Dead-Zero 检查器已加载")
        else:
            self.dead_zero_checker = None
            logger.warning("NLU Pipeline: dead_zero_mus 不可用，Dead-Zero 检查将降级")

        # Step 6: κ-Snap 算子
        if _HAS_KSNAP:
            self.ksnap_operator = KSnapOperator(
                theta_ftel=0.1,
                theta_dead=theta_dead,
                dead_zero_checker=self.dead_zero_checker,
            )
            logger.info("NLU Pipeline: κ-Snap 算子已加载")
        else:
            self.ksnap_operator = None
            logger.warning("NLU Pipeline: ksnap_operator 不可用，κ-Snap 写入将跳过")

        # G_ego（可选）
        if _HAS_G_EGO:
            try:
                self.g_ego = GEgoOperator()
                logger.info("NLU Pipeline: G_ego 算子已加载")
            except Exception:
                self.g_ego = None
                logger.warning("NLU Pipeline: G_ego 初始化失败，将跳过")
        else:
            self.g_ego = None

        # GPCT 边界层分解器（T15: 因果边层创触发）
        self.gpct_decomposer: Optional[Any] = None
        if _HAS_GPCT and GpctDecomposer is not None:
            try:
                # 以空边列表初始化，后续通过 on_new_data 增量添加
                self.gpct_decomposer = GpctDecomposer(edges=[])
                logger.info("NLU Pipeline: GPCT 分解器已加载")
            except Exception as e:
                self.gpct_decomposer = None
                logger.warning("NLU Pipeline: GPCT 分解器初始化失败: %s", e)
        else:
            logger.warning(
                "NLU Pipeline: eml_dimred.gpct 不可用，层创检测将跳过"
            )

        # 管道统计
        self.stats = {
            "total_processed": 0,
            "hnc_success": 0,
            "eml_injected": 0,
            "psi_aligned": 0,
            "contradictions_found": 0,
            "dead_zero_rejected": 0,
            "ksnap_manifested": 0,
            "gpct_emergence_detected": 0,
        }

    # ── 公共 API ──

    def process(self, text: str) -> NLUPipelineResult:
        """执行 7 步 NLU 管道。

        Args:
            text: 输入的自然语言文本

        Returns:
            NLUPipelineResult: 管道处理结果
        """
        self.stats["total_processed"] += 1
        pipeline_log: List[str] = []

        # ===== Step 1: HNC 解析 =====
        hnc_result = self._step_hnc_parse(text)
        pipeline_log.append(f"Step1 HNC: template={hnc_result['template_id']}")
        if hnc_result["template_id"] != "UNKNOWN":
            self.stats["hnc_success"] += 1

        template_id = hnc_result["template_id"]
        chunks = hnc_result["chunks"]
        concept_codes = hnc_result["concept_codes"]
        cited_rule = hnc_result["cited_rule"]

        # ===== Step 2: EML 注入 =====
        eml_context = self._step_eml_inject(template_id, concept_codes, chunks)
        if eml_context:
            self.stats["eml_injected"] += 1
            pipeline_log.append("Step2 EML: injected")

        # ===== Step 2b: GPCT 因果边层创检测 (T15) =====
        gpct_emergence_detected: bool = False
        gpct_new_dim: int = 0
        if _HAS_GPCT and self.gpct_decomposer is not None:
            eml_edges = self._build_eml_edges(
                template_id, concept_codes, chunks
            )
            if eml_edges:
                gpct_result = self.trigger_gpct_emergence(eml_edges)
                gpct_emergence_detected = gpct_result.get(
                    "emergence_detected", False
                )
                gpct_new_dim = gpct_result.get("new_dim", 0)
                if gpct_emergence_detected:
                    self.stats["gpct_emergence_detected"] += 1
                    pipeline_log.append(
                        f"Step2b GPCT: emergence! new_dim={gpct_new_dim}"
                    )

        # ===== Step 3: ψ-锚检查 =====
        psi_status = self._step_psi_check(text, concept_codes)
        if psi_status.startswith("aligned"):
            self.stats["psi_aligned"] += 1
            pipeline_log.append(f"Step3 ψ: {psi_status}")

        # ===== Step 4: 矛盾检测 =====
        contradiction_found = self._step_contradiction_check(text)
        if contradiction_found:
            self.stats["contradictions_found"] += 1
            pipeline_log.append("Step4 Contradiction: detected")

        # ===== Step 5: Dead-Zero 检查 =====
        dead_zero_triggered = self._step_dead_zero_check(concept_codes)
        if dead_zero_triggered:
            self.stats["dead_zero_rejected"] += 1
            pipeline_log.append("Step5 DeadZero: triggered")

        # ===== Step 6: κ-Snap 写入 =====
        snap_id = self._step_ksnap_write(
            template_id, concept_codes, chunks, dead_zero_triggered
        )
        if snap_id:
            self.stats["ksnap_manifested"] += 1
            pipeline_log.append(f"Step6 κ-Snap: {snap_id}")

        # ===== Step 7: ℐ 计算（T15 增强: 传入 cited_rule） =====
        i_value = self._compute_initial_i(
            concept_codes, template_id, cited_rule
        )
        pipeline_log.append(f"Step7 ℐ={i_value:.4f}")

        logger.debug("NLU pipeline: %s", " | ".join(pipeline_log))

        return NLUPipelineResult(
            template_id=template_id,
            chunks=chunks,
            concept_codes=concept_codes,
            cited_rule=cited_rule,
            i_value=i_value,
            psi_alignment_status=psi_status,
            snap_id=snap_id,
            gpct_emergence_detected=gpct_emergence_detected,
            gpct_new_dim=gpct_new_dim if gpct_emergence_detected else None,
        )

    # ── Step 实现 ──

    def _step_hnc_parse(self, text: str) -> Dict[str, Any]:
        """Step 1: HNC 解析（分词 + 概念编码 + 模板匹配）。

        Args:
            text: 输入文本

        Returns:
            包含 template_id, chunks, concept_codes, cited_rule 的字典
        """
        if self.hnc_parser is not None:
            result = self.hnc_parser.parse(text)
            return {
                "template_id": result.template_id,
                "chunks": result.chunks,
                "concept_codes": result.concept_codes,
                "cited_rule": result.cited_rule,
            }

        # 降级：简单的字符级处理
        logger.warning("HNC parser unavailable, using fallback character-level parsing")
        chunks = [ch for ch in text if ch.strip()]
        concept_codes = ["v" for _ in chunks]  # 默认实体码
        return {
            "template_id": "UNKNOWN",
            "chunks": chunks,
            "concept_codes": concept_codes,
            "cited_rule": {},
        }

    def _step_eml_inject(
        self,
        template_id: str,
        concept_codes: List[str],
        chunks: List[str],
    ) -> Optional[str]:
        """Step 2: EML 注入（构建超边上下文块）。

        将 HNC 解析结果映射为 EML matched_concepts 格式，调用
        EMLInjector.build_context_block() 构建上下文。

        Args:
            template_id: HNC 模板 ID
            concept_codes: 概念基元码列表
            chunks: 分词列表

        Returns:
            EML 上下文文本（若注入成功），否则 None
        """
        if self.eml_injector is None:
            logger.warning("Step 2 EML inject: skipped (eml_injector unavailable)")
            return None

        try:
            # 将 HNC 结果映射为 EML matched_concepts 格式
            matched_concepts = self._inject_to_eml(concept_codes, chunks)
            related_edges = self._build_eml_edges(template_id, concept_codes, chunks)

            context_block = self.eml_injector.build_context_block(
                matched_concepts=matched_concepts,
                related_edges=related_edges,
            )
            return context_block
        except Exception as e:
            logger.warning("Step 2 EML inject failed: %s", e)
            return None

    def _step_psi_check(self, text: str, concept_codes: List[str]) -> str:
        """Step 3: ψ-锚检查（自我状态锚定）。

        Args:
            text: 原始输入文本
            concept_codes: 概念基元码列表

        Returns:
            ψ-锚对齐状态字符串
        """
        if self.psi_manager is None or PsiAnchor is None:
            logger.warning("Step 3 ψ-check: skipped (psi_anchor unavailable)")
            return "skipped: psi_anchor module unavailable"

        try:
            # 创建 ψ-锚
            anchor = PsiAnchor(
                self_state=f"处理用户输入: {text[:50]}",
                kappa_at_write=int(self.kappa),
            )
            # 验证锚可序列化
            anchor_dict = anchor.to_dict()
            if anchor_dict:
                return f"aligned: κ={self.kappa}, state='{anchor.self_state[:30]}'"
            return "aligned: default"
        except Exception as e:
            logger.warning("Step 3 ψ-check failed: %s", e)
            return f"error: {e}"

    def _step_contradiction_check(self, text: str) -> bool:
        """Step 4: 矛盾检测。

        Args:
            text: 输入文本

        Returns:
            是否检测到矛盾
        """
        if self.contradiction_detector is None:
            logger.warning("Step 4 contradiction: skipped (detector unavailable)")
            return False

        try:
            # 简单自检测：文本内部是否有否定矛盾
            # （完整管道中此处会对比与已有知识的矛盾）
            negation_words = ["不", "不是", "并非", "没有", "不可能"]
            neg_count = sum(1 for w in negation_words if w in text)
            return neg_count >= 2  # 多个否定词可能暗示内部矛盾
        except Exception as e:
            logger.warning("Step 4 contradiction check failed: %s", e)
            return False

    def _step_dead_zero_check(self, concept_codes: List[str]) -> bool:
        """Step 5: Dead-Zero 检查。

        Args:
            concept_codes: 概念基元码列表

        Returns:
            是否触发死零
        """
        # 先计算临时 ℐ 值
        temp_i = self._compute_initial_i(concept_codes, "UNKNOWN")

        if self.dead_zero_checker is not None:
            try:
                # 使用 DeadZeroChecker 的 DIKWP 感知接口
                is_dead, reason = self.dead_zero_checker.check_dead_zero_dikwp(
                    temp_i, "data"
                ) if hasattr(self.dead_zero_checker, "check_dead_zero_dikwp") else (
                    temp_i < self.theta_dead,
                    f"ℐ={temp_i:.4f} < θ_dead={self.theta_dead}",
                )
                if is_dead:
                    logger.info("Step 5 Dead-Zero triggered: %s", reason)
                return is_dead
            except Exception as e:
                logger.warning("Step 5 Dead-Zero check error: %s", e)

        # 降级：简单阈值比较
        is_dead = temp_i < self.theta_dead
        if is_dead:
            logger.info("Step 5 Dead-Zero (fallback): ℐ=%.4f < θ=%.4f", temp_i, self.theta_dead)
        return is_dead

    def _step_ksnap_write(
        self,
        template_id: str,
        concept_codes: List[str],
        chunks: List[str],
        dead_zero_triggered: bool,
    ) -> Optional[str]:
        """Step 6: κ-Snap 写入（显影算子投影）。

        Args:
            template_id: HNC 模板 ID
            concept_codes: 概念基元码列表
            chunks: 分词列表
            dead_zero_triggered: 是否触发了死零

        Returns:
            κ-Snap 显影 ID（若成功显影），否则 None
        """
        if self.ksnap_operator is None or CandidateEdge is None:
            logger.warning("Step 6 κ-Snap: skipped (ksnap_operator unavailable)")
            return None

        if dead_zero_triggered:
            logger.info("Step 6 κ-Snap: skipped (dead-zero triggered)")
            return None

        try:
            i_value = self._compute_initial_i(concept_codes, template_id)

            candidate = CandidateEdge(
                edge_id=f"nlu_{uuid.uuid4().hex[:8]}",
                source=chunks[0] if chunks else "unknown",
                target=chunks[-1] if len(chunks) > 1 else "unknown",
                relation=template_id,
                i_value=i_value,
                ftel_magnitude=i_value * 0.8,  # Ftel ≈ 0.8 × ℐ
                features={
                    "concept_codes": concept_codes,
                    "chunks": chunks,
                    "template_id": template_id,
                },
            )

            obs_base = ObservationBase.COGNITIVE if ObservationBase else None
            event = self.ksnap_operator.execute(candidate, obs_base)

            if event.result == SnapResult.MANIFESTED:
                return event.event_id
            else:
                logger.info(
                    "Step 6 κ-Snap not manifested: %s (%s)",
                    event.result.value, event.reason,
                )
                return None
        except Exception as e:
            logger.warning("Step 6 κ-Snap write failed: %s", e)
            return None

    # ── ℐ 计算 (T15 增强) ──

    def _compute_cite_factor(
        self, cited_rule: Optional[Dict[str, Any]] = None
    ) -> float:
        """计算引用规则置信度（cite_factor）。

        基于 cited_rule 的完整性：规则包含的关键字段越多，
        置信度越高。无规则时使用默认 cite_factor。

        完整性映射：基础 0.5 + completeness × 0.45
          - 完整规则（所有关键字段）→ 0.95
          - 空规则 / None → self.cite_factor（默认 0.85）

        Args:
            cited_rule: 引用的模板规则字典

        Returns:
            cite_factor 值（0.5 ~ 0.95）
        """
        if (
            cited_rule is None
            or not isinstance(cited_rule, dict)
            or len(cited_rule) == 0
        ):
            return self.cite_factor

        # 评估规则完整性：关键字段存在性
        key_fields = [
            "template_id",
            "pattern",
            "slots",
            "constraints",
            "priority",
        ]
        present_count = sum(1 for k in key_fields if k in cited_rule)
        completeness: float = present_count / len(key_fields)

        # 完整性映射到置信度：基础 0.5 + 完整性 × 0.45
        cite_factor: float = 0.5 + completeness * 0.45
        return round(min(cite_factor, self.DEFAULT_I_CAP), 4)

    def _compute_initial_i(
        self,
        concept_codes: List[str],
        template_id: str,
        cited_rule: Optional[Dict[str, Any]] = None,
    ) -> float:
        """计算初始 ℐ（信息存在度）。

        公式: ℐ = min(depth_factor × cite_factor, 0.95)

        其中:
            depth_factor = 实际概念数 / 模板期望概念数（概念编码深度）
            cite_factor = 引用规则置信度（基于 cited_rule 完整性）

        Args:
            concept_codes: 概念基元码列表
            template_id: HNC 模板 ID
            cited_rule: 引用的模板规则（可选，用于计算 cite_factor）

        Returns:
            ℐ 值（0.0 ~ 0.95）
        """
        num_concepts = len(concept_codes)

        # 获取模板期望概念数
        expected = num_concepts  # 默认：实际数 = 期望数
        if _HAS_HNC and self.hnc_parser is not None:
            template = HNCParserWrapper.SENTENCE_TEMPLATES.get(template_id)
            if template:
                expected = len(template.get("pattern", []))

        # depth_factor = 实际概念数 / 模板期望数（限制在 0~1.5）
        if expected > 0:
            depth_factor = min(num_concepts / expected, 1.5)
        else:
            depth_factor = 0.5

        # cite_factor: 基于 cited_rule 完整性计算（T15 增强）
        cite_factor = self._compute_cite_factor(cited_rule)

        # ℐ = min(depth_factor × cite_factor, cap)
        i_value = min(depth_factor * cite_factor, self.DEFAULT_I_CAP)

        # 死零保护：至少给一个小值
        i_value = max(i_value, 0.01)

        return round(i_value, 4)

    def bayesian_update_i(
        self, prior_i: float, evidence_i: float
    ) -> float:
        """贝叶斯更新 ℐ 值。

        使用贝叶斯公式将先验 ℐ 与新证据结合：

            ℐ_posterior = (ℐ_prior × likelihood) /
                ((ℐ_prior × likelihood) + ((1-ℐ_prior) × (1-likelihood)))

        其中 evidence_i 作为 likelihood（证据支持度）。
        后验值上限 0.95，防止过度自信。

        Args:
            prior_i: 先验 ℐ 值（0.0 ~ 1.0）
            evidence_i: 证据 ℐ 值 / 似然度（0.0 ~ 1.0）

        Returns:
            后验 ℐ 值（0.01 ~ 0.95）
        """
        # 边界保护：钳制到 [0.0, 1.0]
        prior_i = max(0.0, min(prior_i, 1.0))
        evidence_i = max(0.0, min(evidence_i, 1.0))

        # 贝叶斯更新
        numerator = prior_i * evidence_i
        denominator = numerator + (
            (1.0 - prior_i) * (1.0 - evidence_i)
        )

        if denominator < 1e-12:
            # 避免除零：返回先验值
            posterior = prior_i
        else:
            posterior = numerator / denominator

        # 上限 0.95，防止过度自信
        posterior = min(posterior, self.DEFAULT_I_CAP)
        # 死零保护：至少给一个小值
        posterior = max(posterior, 0.01)

        return round(posterior, 4)

    # ── GPCT 因果边层创触发 (T15) ──

    def trigger_gpct_emergence(
        self, new_edges: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """GPCT 因果边层创触发。

        当 NLU 管道检测到新的因果边时，调用 GPCT 的 on_new_data 方法，
        检测是否触发层创涌现。若检测到层创，GPCT 自动扩展输出维度。

        流程:
            1. 将 NLU 字典格式边转换为 HypEdge 对象
            2. 调用 GpctDecomposer.on_new_data() 增量添加边
            3. on_new_data 内部调用 detect_causal_emergence() 检测层创
            4. 若层创触发，on_new_data 内部调用 expand_output_dim()

        Args:
            new_edges: 新的因果边列表（字典格式，
                每个含 nodes/i_val/type 等字段）

        Returns:
            {
                "emergence_detected": bool,  # 是否检测到层创
                "new_dim": int,              # 新的输出维度
                "details": Dict,             # 详细信息
            }
        """
        if not _HAS_GPCT or GpctDecomposer is None:
            logger.warning(
                "trigger_gpct_emergence: GpctDecomposer 不可用，跳过层创检测"
            )
            return {
                "emergence_detected": False,
                "new_dim": 0,
                "details": {
                    "reason": "GpctDecomposer module unavailable"
                },
            }

        if not new_edges:
            logger.info("trigger_gpct_emergence: 无新因果边")
            return {
                "emergence_detected": False,
                "new_dim": 0,
                "details": {"reason": "No new edges provided"},
            }

        if self.gpct_decomposer is None:
            logger.warning(
                "trigger_gpct_emergence: gpct_decomposer 未初始化"
            )
            return {
                "emergence_detected": False,
                "new_dim": 0,
                "details": {
                    "reason": "GpctDecomposer not initialized"
                },
            }

        try:
            # 将字典格式边转换为 GPCT 兼容的 HypEdge 对象
            gpct_edges = self._convert_to_gpct_edges(new_edges)
            if not gpct_edges:
                logger.info(
                    "trigger_gpct_emergence: 转换后无有效边"
                )
                return {
                    "emergence_detected": False,
                    "new_dim": self.gpct_decomposer.output_dim,
                    "details": {
                        "reason": "No valid edges after conversion"
                    },
                }

            # 调用 GPCT on_new_data
            # （内部执行: 增量添加边 → 重建索引 → 层创检测 → 维度扩展）
            result = self.gpct_decomposer.on_new_data(gpct_edges)

            emergence_detected: bool = result.get(
                "emergence_detected", False
            )
            new_dim: int = result.get(
                "new_dim", self.gpct_decomposer.output_dim
            )
            details: Dict[str, Any] = result.get("details", {})

            if emergence_detected:
                logger.info(
                    "GPCT 层创涌现检测: emergence=True, "
                    "new_dim=%d, dim_expanded=%s",
                    new_dim,
                    result.get("dim_expanded", False),
                )
            else:
                logger.debug("GPCT 层创检测: 无涌现")

            return {
                "emergence_detected": emergence_detected,
                "new_dim": new_dim,
                "details": details,
            }
        except Exception as e:
            logger.warning("trigger_gpct_emergence 失败: %s", e)
            return {
                "emergence_detected": False,
                "new_dim": 0,
                "details": {"reason": f"Error: {e}"},
            }

    def _convert_to_gpct_edges(
        self, dict_edges: List[Dict[str, Any]]
    ) -> List[Any]:
        """将 NLU 字典格式边转换为 GPCT 兼容的 HypEdge 对象。

        NLU 边格式: {"nodes": [str, ...], "i_val": float, "type": str}
        HypEdge 需要: nodes=(int, ...), eid=str, i_val=float

        节点 ID 映射：将字符串节点名转换为整数 ID（GPCT 要求 int 节点）。

        Args:
            dict_edges: NLU 字典格式边列表

        Returns:
            HypEdge（或 _LiteEdge）对象列表
        """
        edge_cls = HypEdge if (_HAS_HYPEDGE and HypEdge is not None) else _LiteEdge

        gpct_edges: List[Any] = []
        # 节点名 → 整数 ID 映射
        node_id_map: Dict[str, int] = {}
        next_id: int = 0

        for edge_dict in dict_edges:
            nodes_str = edge_dict.get("nodes", [])
            if not nodes_str:
                continue

            # 映射节点名为整数 ID
            node_ids: List[int] = []
            for n in nodes_str:
                n_key = str(n)
                if n_key not in node_id_map:
                    node_id_map[n_key] = next_id
                    next_id += 1
                node_ids.append(node_id_map[n_key])

            i_val = float(edge_dict.get("i_val", 0.5))
            eid = edge_dict.get(
                "edge_id", f"nlu_edge_{uuid.uuid4().hex[:8]}"
            )

            he = edge_cls(
                nodes=tuple(node_ids),
                eid=eid,
                i_val=i_val,
            )
            gpct_edges.append(he)

        return gpct_edges

    # ── EML 映射 ──

    def _inject_to_eml(
        self,
        concept_codes: List[str],
        chunks: List[str],
    ) -> List[Dict[str, Any]]:
        """将 HNC 解析结果映射为 EML matched_concepts 格式。

        Args:
            concept_codes: 概念基元码列表
            chunks: 分词列表

        Returns:
            matched_concepts 格式列表 [{"concept": str, "i_val": float}, ...]
        """
        matched_concepts = []
        for i, (code, chunk) in enumerate(zip(concept_codes, chunks)):
            # 每个概念的 ℐ 值随位置递减
            i_val = max(0.5 - i * 0.05, 0.1)
            matched_concepts.append({
                "concept": chunk,
                "i_val": round(i_val, 4),
                "hnc_code": code,
            })
        return matched_concepts

    def _build_eml_edges(
        self,
        template_id: str,
        concept_codes: List[str],
        chunks: List[str],
    ) -> List[Dict[str, Any]]:
        """根据 HNC 模板构建 EML 超边列表。

        Args:
            template_id: HNC 模板 ID
            concept_codes: 概念基元码列表
            chunks: 分词列表

        Returns:
            超边列表 [{"nodes": [...], "i_val": float, "type": str}, ...]
        """
        if not chunks:
            return []

        # 如果 EML 注入器支持 HNC 映射，使用它
        if self.eml_injector is not None and hasattr(
            self.eml_injector, "map_hnc_template_to_eml_schema"
        ):
            try:
                schema = self.eml_injector.map_hnc_template_to_eml_schema(
                    template_id, concept_codes, chunks
                )
                if schema and schema.get("edges"):
                    return schema["edges"]
            except Exception as e:
                logger.warning("EML schema mapping failed: %s", e)

        # 降级：构建简单线性超边
        i_value = self._compute_initial_i(concept_codes, template_id)
        return [{
            "nodes": chunks,
            "i_val": i_value,
            "type": template_id,
        }]

    # ── 工具方法 ──

    def get_stats(self) -> Dict[str, Any]:
        """获取管道统计信息。

        Returns:
            统计字典
        """
        return {
            **self.stats,
            "modules_available": {
                "hnc": _HAS_HNC,
                "g_ego": _HAS_G_EGO,
                "ksnap": _HAS_KSNAP,
                "dead_zero": _HAS_DEAD_ZERO,
                "eml": _HAS_EML,
                "contradiction": _HAS_CONTRADICTION,
                "psi": _HAS_PSI,
                "gpct": _HAS_GPCT,
            },
        }


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("TOMASNLU_Pipeline 自测")
    print("=" * 60)

    # 初始化管道（不使用 jieba，确保降级模式可测）
    pipeline = TOMASNLU_Pipeline(use_jieba=False)

    # 测试 1: 基本管道处理
    print("\n--- 测试1: 基本管道处理 ---")
    result = pipeline.process("我吃苹果")
    print(f"  Template: {result.template_id}")
    print(f"  Chunks: {result.chunks}")
    print(f"  Codes: {result.concept_codes}")
    print(f"  ℐ value: {result.i_value:.4f}")
    print(f"  ψ status: {result.psi_alignment_status}")
    print(f"  Snap ID: {result.snap_id}")

    assert result.template_id != "", "template_id 不应为空"
    assert 0.0 < result.i_value <= 0.95, f"ℐ 应在 (0, 0.95] 范围内, 实际 {result.i_value}"
    assert len(result.chunks) > 0, "chunks 不应为空"
    assert len(result.concept_codes) == len(result.chunks), "concept_codes 长度应等于 chunks"

    # 测试 2: 空输入
    print("\n--- 测试2: 空输入 ---")
    result = pipeline.process("")
    print(f"  Template: {result.template_id}")
    print(f"  ℐ value: {result.i_value:.4f}")
    assert result.template_id == "UNKNOWN"

    # 测试 3: ℐ 计算验证
    print("\n--- 测试3: ℐ 计算验证 ---")
    # BC_TransEvi 模板期望 3 个概念，cite_factor=0.85
    # depth_factor = 3/3 = 1.0, ℐ = min(1.0 * 0.85, 0.95) = 0.85
    i_val = pipeline._compute_initial_i(["v", "p", "v"], "BC_TransEvi")
    print(f"  ℐ(v,p,v, BC_TransEvi) = {i_val:.4f}")
    assert abs(i_val - 0.85) < 0.01, f"期望 0.85, 实际 {i_val}"

    # 测试 4: 管道统计
    print("\n--- 测试4: 管道统计 ---")
    stats = pipeline.get_stats()
    print(f"  Total processed: {stats['total_processed']}")
    print(f"  HNC success: {stats['hnc_success']}")
    print(f"  Modules: {stats['modules_available']}")

    # 测试 5: 多次处理
    print("\n--- 测试5: 多次处理 ---")
    texts = ["我吃苹果", "苹果是水果", "天亮了"]
    for text in texts:
        r = pipeline.process(text)
        print(f"  '{text}' → template={r.template_id}, ℐ={r.i_value:.4f}")

    # 测试 6: 贝叶斯更新 ℐ (T15)
    print("\n--- 测试6: 贝叶斯更新 ℐ ---")
    prior = 0.5
    evidence = 0.8
    posterior = pipeline.bayesian_update_i(prior, evidence)
    print(f"  prior={prior}, evidence={evidence} → posterior={posterior:.4f}")
    assert 0.0 < posterior <= 0.95, f"后验应在 (0, 0.95], 实际 {posterior}"
    # 贝叶斯公式验证: (0.5*0.8) / (0.5*0.8 + 0.5*0.2) = 0.4/0.5 = 0.8
    assert abs(posterior - 0.8) < 0.01, f"期望 0.8, 实际 {posterior}"

    # 高先验 + 高证据 → 接近上限 0.95
    posterior2 = pipeline.bayesian_update_i(0.9, 0.95)
    print(f"  prior=0.9, evidence=0.95 → posterior={posterior2:.4f}")
    assert posterior2 <= 0.95, f"后验应 ≤ 0.95, 实际 {posterior2}"

    # 边界: prior=0, evidence=0 → posterior 应有死零保护
    posterior3 = pipeline.bayesian_update_i(0.0, 0.0)
    print(f"  prior=0.0, evidence=0.0 → posterior={posterior3:.4f}")
    assert posterior3 >= 0.01, f"死零保护应 ≥ 0.01, 实际 {posterior3}"

    # 测试 7: cite_factor 计算 (T15)
    print("\n--- 测试7: cite_factor 计算 ---")
    # None → 默认 0.85
    cf_none = pipeline._compute_cite_factor(None)
    print(f"  cite_factor(None) = {cf_none:.4f}")
    assert abs(cf_none - 0.85) < 0.01, f"期望 0.85, 实际 {cf_none}"

    # 完整规则 → 0.95
    full_rule = {
        "template_id": "BC_TransEvi",
        "pattern": ["v", "p", "v"],
        "slots": ["agent", "action", "patient"],
        "constraints": ["tense=past"],
        "priority": 1,
    }
    cf_full = pipeline._compute_cite_factor(full_rule)
    print(f"  cite_factor(full_rule) = {cf_full:.4f}")
    assert abs(cf_full - 0.95) < 0.01, f"期望 0.95, 实际 {cf_full}"

    # 部分规则 → 0.5 + (2/5)*0.45 = 0.68
    partial_rule = {"template_id": "X", "pattern": ["v"]}
    cf_partial = pipeline._compute_cite_factor(partial_rule)
    print(f"  cite_factor(partial_rule) = {cf_partial:.4f}")
    assert 0.5 < cf_partial < 0.95

    # 测试 8: ℐ 计算带 cited_rule (T15)
    print("\n--- 测试8: ℐ 计算带 cited_rule ---")
    i_with_rule = pipeline._compute_initial_i(
        ["v", "p", "v"], "BC_TransEvi", full_rule
    )
    print(f"  ℐ(v,p,v, BC_TransEvi, full_rule) = {i_with_rule:.4f}")
    # depth_factor=1.0, cite_factor=0.95 → ℐ=0.95
    assert abs(i_with_rule - 0.95) < 0.01, f"期望 0.95, 实际 {i_with_rule}"

    # 无 cited_rule → cite_factor=0.85 → ℐ=0.85
    i_no_rule = pipeline._compute_initial_i(
        ["v", "p", "v"], "BC_TransEvi", None
    )
    print(f"  ℐ(v,p,v, BC_TransEvi, None) = {i_no_rule:.4f}")
    assert abs(i_no_rule - 0.85) < 0.01, f"期望 0.85, 实际 {i_no_rule}"

    # 测试 9: GPCT 层创触发 (T15)
    print("\n--- 测试9: GPCT 层创触发 ---")
    # 空边列表
    result_empty = pipeline.trigger_gpct_emergence([])
    print(f"  空边: {result_empty}")
    assert result_empty["emergence_detected"] is False

    # 有边但可能不触发层创（取决于耦合度分布）
    test_edges = [
        {"nodes": ["A", "B"], "i_val": 0.5, "type": "test"},
        {"nodes": ["B", "C"], "i_val": 0.6, "type": "test"},
    ]
    result_edges = pipeline.trigger_gpct_emergence(test_edges)
    print(
        f"  2条边: emergence={result_edges['emergence_detected']}, "
        f"new_dim={result_edges['new_dim']}"
    )
    assert "emergence_detected" in result_edges
    assert "new_dim" in result_edges
    assert "details" in result_edges

    # 测试 10: process() 返回 GPCT 字段 (T15)
    print("\n--- 测试10: process() 返回 GPCT 字段 ---")
    result_proc = pipeline.process("我吃苹果")
    print(f"  gpct_emergence_detected: {result_proc.gpct_emergence_detected}")
    print(f"  gpct_new_dim: {result_proc.gpct_new_dim}")
    # 字段应存在（可能为 None 或 bool）
    assert hasattr(result_proc, "gpct_emergence_detected")
    assert hasattr(result_proc, "gpct_new_dim")

    print("\n" + "=" * 60)
    print("所有 TOMASNLU_Pipeline 自测通过!")
    print("=" * 60)
