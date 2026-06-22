# -*- coding: utf-8 -*-
"""
TOMAS AGI v3.11 — Grill-Me Engine 单元测试
=============================================
覆盖: DIKWPGapAnalyzer, GrillExecutionGate, RequirementTracer, PsiNoSilentAssumption,
      LayerGap, GapReport, 审计链, DSL 生成
"""

import json
import time
import pytest

from sim.grill_me_engine import (
    DIKWPGapAnalyzer,
    GrillExecutionGate,
    RequirementTracer,
    PsiNoSilentAssumption,
    GapReport,
    LayerGap,
    LayerStatus,
    GapClosureStatus,
    TraceEntry,
    _sha256,
    _chain_hash,
    _make_snap_ref,
    create_grill_pipeline,
)


# ══════════════════════════════════════════════════════════════════
# Group 1: 审计工具函数
# ══════════════════════════════════════════════════════════════════

class TestAuditUtilities:
    def test_sha256_length(self):
        assert len(_sha256("test")) == 64

    def test_chain_hash_deterministic(self):
        h1 = _chain_hash("prev", "data")
        h2 = _chain_hash("prev", "data")
        assert h1 == h2

    def test_chain_hash_different_prev(self):
        h1 = _chain_hash("prev1", "data")
        h2 = _chain_hash("prev2", "data")
        assert h1 != h2

    def test_make_snap_ref_format(self):
        ref = _make_snap_ref("evt123", "0" * 64)
        assert ref.startswith("snap:evt123:")

    def test_sha256_hex(self):
        h = _sha256("")
        assert all(c in "0123456789abcdef" for c in h)


# ══════════════════════════════════════════════════════════════════
# Group 2: LayerGap 数据类
# ══════════════════════════════════════════════════════════════════

class TestLayerGap:
    def test_default_values(self):
        gap = LayerGap(status="missing", gap_description="test", evidence_required="ev")
        assert gap.closed is False
        assert gap.closed_by is None

    def test_close_method(self):
        gap = LayerGap(status="missing", gap_description="test", evidence_required="ev")
        gap.close("proof", "tester")
        assert gap.closed is True
        assert gap.closed_by == "tester"
        assert gap.evidence_provided == "proof"
        assert gap.closed_at is not None

    def test_to_dict(self):
        gap = LayerGap(status="missing", gap_description="test", evidence_required="ev")
        d = gap.to_dict()
        assert "status" in d
        assert d["closed"] is False


# ══════════════════════════════════════════════════════════════════
# Group 3: GapReport 数据类
# ══════════════════════════════════════════════════════════════════

class TestGapReport:
    def test_creation(self):
        report = GapReport(requirement_id="req1", requirement_raw="test requirement")
        assert report.requirement_id == "req1"
        assert report.all_gaps_closed is False

    def test_report_hash_auto_generated(self):
        report = GapReport(requirement_id="req1", requirement_raw="test")
        assert len(report.report_hash) > 0

    def test_get_open_gaps(self):
        gap_missing = LayerGap(status="missing", gap_description="test", evidence_required="ev")
        gap_covered = LayerGap(status="covered", gap_description="ok", evidence_required="N/A")
        report = GapReport(
            requirement_id="req1",
            requirement_raw="test",
            layers={"D": gap_missing, "I": gap_covered},
        )
        open_gaps = report.get_open_gaps()
        assert len(open_gaps) == 1
        assert open_gaps[0][0] == "D"

    def test_get_missing_layers(self):
        gap = LayerGap(status="missing", gap_description="test", evidence_required="ev")
        report = GapReport(
            requirement_id="req1", requirement_raw="test", layers={"D": gap}
        )
        assert "D" in report.get_missing_layers()

    def test_to_dict(self):
        report = GapReport(requirement_id="req1", requirement_raw="test")
        d = report.to_dict()
        assert "requirement_id" in d
        assert "layers" in d


# ══════════════════════════════════════════════════════════════════
# Group 4: DIKWPGapAnalyzer
# ══════════════════════════════════════════════════════════════════

class TestDIKWPGapAnalyzer:
    def test_analyze_returns_gap_report(self):
        analyzer = DIKWPGapAnalyzer()
        report = analyzer.analyze("做一个登录功能")
        assert isinstance(report, GapReport)
        assert len(report.layers) == 5

    def test_analyze_vague_requirement_has_gaps(self):
        analyzer = DIKWPGapAnalyzer()
        report = analyzer.analyze("做个东西")
        assert not report.all_gaps_closed

    def test_analyze_detailed_requirement(self):
        req = (
            "开发一个用户登录功能，使用邮箱+密码认证，支持JWT token，"
            "密码至少8位含大小写数字，登录失败3次锁定15分钟，"
            "需通过OWASP安全审计，使用算法模型验证，决策阈值0.95，"
            "目标：安全登录，意图对齐OWASP标准"
        )
        analyzer = DIKWPGapAnalyzer()
        report = analyzer.analyze(req)
        assert isinstance(report, GapReport)

    def test_analyze_caches_result(self):
        analyzer = DIKWPGapAnalyzer()
        r1 = analyzer.analyze("需要登录功能")
        r2 = analyzer.analyze("需要登录功能")
        assert r1.requirement_id == r2.requirement_id

    def test_generate_gap_dsl(self):
        analyzer = DIKWPGapAnalyzer()
        report = analyzer.analyze("做个东西")
        dsl = analyzer.generate_gap_dsl(report)
        assert "grill-me" in dsl
        assert "DIKWP" in dsl

    def test_dikwp_all_five_layers(self):
        analyzer = DIKWPGapAnalyzer()
        report = analyzer.analyze("test requirement")
        assert set(report.layers.keys()) == {"D", "I", "K", "W", "P"}

    def test_get_analysis_stats(self):
        analyzer = DIKWPGapAnalyzer()
        analyzer.analyze("需要登录功能")
        stats = analyzer.get_analysis_stats()
        assert stats["total_analyses"] >= 1

    def test_data_layer_analysis(self):
        analyzer = DIKWPGapAnalyzer()
        gap = analyzer.analyze_data_layer("数据格式为JSON，来源为API，范围1000条")
        assert gap.status == "covered"

    def test_purpose_layer_missing(self):
        analyzer = DIKWPGapAnalyzer()
        gap = analyzer.analyze_purpose_layer("测试文本")
        assert gap.status == "missing"


# ══════════════════════════════════════════════════════════════════
# Group 5: GrillExecutionGate
# ══════════════════════════════════════════════════════════════════

class TestGrillExecutionGate:
    def test_register_and_verify(self):
        analyzer = DIKWPGapAnalyzer()
        gate = GrillExecutionGate()
        report = analyzer.analyze("做个东西")
        gate.register_gap_analysis(report)
        # Should not be all closed for vague requirement
        assert gate.verify_all_gaps_closed(report.requirement_id) is False

    def test_close_gap(self):
        analyzer = DIKWPGapAnalyzer()
        gate = GrillExecutionGate()
        report = analyzer.analyze("做个东西")
        gate.register_gap_analysis(report)
        # Close each missing/ambiguous layer
        for layer, gap in report.layers.items():
            if gap.status != "covered":
                result = gate.close_gap(report.requirement_id, layer, "evidence", "tester")
                assert result["success"] is True

    def test_close_gap_unknown_requirement(self):
        gate = GrillExecutionGate()
        result = gate.close_gap("nonexistent", "D", "ev", "tester")
        assert result["success"] is False

    def test_close_gap_unknown_layer(self):
        analyzer = DIKWPGapAnalyzer()
        gate = GrillExecutionGate()
        report = analyzer.analyze("test")
        gate.register_gap_analysis(report)
        result = gate.close_gap(report.requirement_id, "Z", "ev", "tester")
        assert result["success"] is False

    def test_release_locked(self):
        analyzer = DIKWPGapAnalyzer()
        gate = GrillExecutionGate()
        report = analyzer.analyze("做个东西")
        gate.register_gap_analysis(report)
        result = gate.release(report.requirement_id)
        assert result["locked"] is True

    def test_release_unknown(self):
        gate = GrillExecutionGate()
        result = gate.release("nonexistent")
        assert result["locked"] is True

    def test_lock_reason(self):
        analyzer = DIKWPGapAnalyzer()
        gate = GrillExecutionGate()
        report = analyzer.analyze("做个东西")
        gate.register_gap_analysis(report)
        reason = gate.lock_reason(report.requirement_id)
        assert isinstance(reason, str)
        assert len(reason) > 0

    def test_manual_override(self):
        analyzer = DIKWPGapAnalyzer()
        gate = GrillExecutionGate()
        report = analyzer.analyze("做个东西")
        gate.register_gap_analysis(report)
        result = gate.manual_override(report.requirement_id, "emergency", "admin_code")
        assert result["success"] is True
        assert gate.verify_all_gaps_closed(report.requirement_id) is True

    def test_get_gate_status(self):
        analyzer = DIKWPGapAnalyzer()
        gate = GrillExecutionGate()
        report = analyzer.analyze("test")
        gate.register_gap_analysis(report)
        status = gate.get_gate_status()
        assert "total_requirements" in status
        assert status["total_requirements"] >= 1


# ══════════════════════════════════════════════════════════════════
# Group 6: RequirementTracer
# ══════════════════════════════════════════════════════════════════

class TestRequirementTracer:
    def test_add_snap_and_get_chain(self):
        tracer = RequirementTracer()
        tracer.add_snap_to_trace("req-001", {"event_id": "snap-001", "type": "test"})
        chain = tracer.get_trace_chain("req-001")
        assert len(chain) >= 1
        assert chain[0]["event_type"] == "snap"

    def test_verify_tamper_proof_valid(self):
        tracer = RequirementTracer()
        tracer.add_snap_to_trace("req-001", {"event_id": "snap-001", "type": "test"})
        chain = tracer.get_trace_chain("req-001")
        result = tracer.verify_tamper_proof(chain[0]["trace_id"])
        assert result["valid"] is True

    def test_verify_tamper_proof_nonexistent(self):
        tracer = RequirementTracer()
        result = tracer.verify_tamper_proof("nonexistent")
        assert result["valid"] is False

    def test_trace_lookup_by_snap_id(self):
        tracer = RequirementTracer()
        tracer.add_snap_to_trace("req-001", {"event_id": "snap-xyz", "type": "test"})
        results = tracer.trace("snap-xyz")
        assert len(results) >= 1

    def test_empty_chain(self):
        tracer = RequirementTracer()
        chain = tracer.get_trace_chain("nonexistent-req")
        assert chain == []

    def test_constitutionalize_with_dict(self):
        tracer = RequirementTracer()
        result = tracer.constitutionalize("req-001", {"anchor_id": "psi-001"})
        assert result["success"] is True
        assert result["psi_anchored"] is True

    def test_constitutionalize_with_none(self):
        tracer = RequirementTracer()
        result = tracer.constitutionalize("req-001", None)
        assert result["success"] is False

    def test_get_chain_integrity_report(self):
        tracer = RequirementTracer()
        tracer.add_snap_to_trace("req-001", {"event_id": "snap-001"})
        report = tracer.get_chain_integrity_report()
        assert "total_requirements" in report
        assert report["total_requirements"] >= 1

    def test_add_generic_trace(self):
        tracer = RequirementTracer()
        entry = tracer.add_generic_trace("req-001", "gap_analysis", {"data": "test"})
        assert isinstance(entry, TraceEntry)
        assert entry.event_type == "gap_analysis"


# ══════════════════════════════════════════════════════════════════
# Group 7: PsiNoSilentAssumption
# ══════════════════════════════════════════════════════════════════

class TestPsiNoSilentAssumption:
    def test_is_llm_imputation_true(self):
        psi = PsiNoSilentAssumption()
        assert psi.is_llm_imputation("通常是这样做") is True

    def test_is_llm_imputation_false(self):
        psi = PsiNoSilentAssumption()
        assert psi.is_llm_imputation("用户指定的需求") is False

    def test_mark_imputation(self):
        psi = PsiNoSilentAssumption()
        psi.mark_imputation("假设用户需要登录", "test")
        stats = psi.get_imputation_stats()
        assert stats["total_imputations"] >= 1

    def test_flag_disallowed(self):
        psi = PsiNoSilentAssumption()
        psi.mark_imputation("推测可能需要这个功能", "test")
        disallowed = psi.flag_disallowed()
        assert isinstance(disallowed, list)

    def test_scan_for_silent_assumptions(self):
        analyzer = DIKWPGapAnalyzer()
        psi = PsiNoSilentAssumption()
        report = analyzer.analyze("做个东西")
        assumptions = psi.scan_for_silent_assumptions(report)
        assert isinstance(assumptions, list)
        assert len(report.silent_assumptions) == len(assumptions)

    def test_scan_updates_report(self):
        analyzer = DIKWPGapAnalyzer()
        psi = PsiNoSilentAssumption()
        report = analyzer.analyze("做个东西")
        psi.scan_for_silent_assumptions(report)
        assert isinstance(report.silent_assumptions, list)


# ══════════════════════════════════════════════════════════════════
# Group 8: 工厂函数
# ══════════════════════════════════════════════════════════════════

class TestFactoryFunctions:
    def test_create_grill_pipeline(self):
        analyzer, gate, tracer, psi = create_grill_pipeline()
        assert isinstance(analyzer, DIKWPGapAnalyzer)
        assert isinstance(gate, GrillExecutionGate)
        assert isinstance(tracer, RequirementTracer)
        assert isinstance(psi, PsiNoSilentAssumption)


# ══════════════════════════════════════════════════════════════════
# Group 9: 枚举
# ══════════════════════════════════════════════════════════════════

class TestEnums:
    def test_layer_status_values(self):
        assert LayerStatus.COVERED.value == "COVERED"
        assert LayerStatus.MISSING.value == "MISSING"
        assert LayerStatus.AMBIGUOUS.value == "AMBIGUOUS"

    def test_gap_closure_status_values(self):
        assert GapClosureStatus.OPEN.value == "OPEN"
        assert GapClosureStatus.CLOSED.value == "CLOSED"
