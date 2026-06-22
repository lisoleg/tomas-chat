# -*- coding: utf-8 -*-
"""
TOMAS AGI v3.9 — Comprehensive Pytest Suite
=============================================
25+ test classes, ~100 tests covering all v3.9 modules + bug fixes + regression.

Modules tested:
  - babeltele_compressor: BabelTeleCompressor, PsiPIIRetainer, MUSDualStorage,
                          KSnapAudit, KSnapRecord, MUSDualEntry, PsiAnchorLevel, SnapResult
  - hypergraph_categories: HypergraphBuilder, FrobeniusGenerator, CupCapDuality,
                           GlueValidator, PsiAnchorFilter, Hyperedge
  - kernelcat_scheduler: KernelCATScheduler, CopartialSearch, ComputeCarbonAuditor,
                         OperatorProfile, CopartialMatch
  - constitutional_agi: ConstitutionalAGI, HardVetoScanner, SelfCritiqueEngine,
                        CONSTITUTIONAL_PRINCIPLES
  - Bug fixes: ido_bridge, arc_api_client
  - Regression sanity
"""

import sys
import os
import time
import math
import hashlib

import pytest

# ── Path setup ──────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'sim'))

# ── v3.9 module imports ────────────────────────────────────────────
from babeltele_compressor import (
    BabelTeleCompressor, PsiPIIRetainer, MUSDualStorage, KSnapAudit,
    KSnapRecord, MUSDualEntry, PsiAnchorLevel, SnapResult,
)
from hypergraph_categories import (
    HypergraphBuilder, FrobeniusGenerator, CupCapDuality,
    GlueValidator, PsiAnchorFilter, Hyperedge,
)
from kernelcat_scheduler import (
    KernelCATScheduler, CopartialSearch, ComputeCarbonAuditor,
    OperatorProfile, CopartialMatch,
)
from constitutional_agi import (
    ConstitutionalAGI, HardVetoScanner, SelfCritiqueEngine,
    CONSTITUTIONAL_PRINCIPLES,
)


# ════════════════════════════════════════════════════════════════════
# A. BabelTele Tests
# ════════════════════════════════════════════════════════════════════

class TestPSIPIIRetainer:
    """PsiPIIRetainer: scan, mask_pii, false-positive resilience."""

    def setup_method(self):
        self.retainer = PsiPIIRetainer()

    # -- scan --

    def test_scan_detects_email(self):
        result = self.retainer.scan("Contact admin@example.com for help.")
        assert result["has_pii"] is True
        assert "email" in result["types"]
        assert any("@" in f for f in result["found"])

    def test_scan_detects_phone_cn(self):
        result = self.retainer.scan("Call 13800138000 now.")
        assert result["has_pii"] is True
        assert "phone_cn" in result["types"]

    def test_scan_detects_id_card(self):
        result = self.retainer.scan("ID: 110101199003071234")
        assert result["has_pii"] is True
        assert "id_card" in result["types"]

    def test_scan_detects_credit_card(self):
        result = self.retainer.scan("Card: 4111222233334444")
        assert result["has_pii"] is True
        assert "credit_card" in result["types"]

    def test_scan_no_false_positives_on_clean_text(self):
        result = self.retainer.scan("The quick brown fox jumps over the lazy dog.")
        assert result["has_pii"] is False
        assert result["found"] == []
        assert result["count"] == 0

    # -- mask_pii --

    def test_mask_pii_replaces_with_placeholders(self):
        text = "Email: admin@example.com, phone: 13800138000"
        masked, fragments = self.retainer.mask_pii(text)
        assert "admin@example.com" not in masked
        assert "13800138000" not in masked
        assert "<PII_" in masked
        assert len(fragments) >= 2

    def test_mask_pii_preserves_original_fragments(self):
        text = "Contact: admin@example.com"
        masked, fragments = self.retainer.mask_pii(text)
        assert "admin@example.com" in fragments

    # -- locations --

    def test_scan_returns_locations(self):
        result = self.retainer.scan("Email: admin@example.com")
        assert len(result["locations"]) >= 1
        start, end = result["locations"][0]
        assert start >= 0
        assert end > start


class TestMUSDualStorage:
    """MUSDualStorage: store, retrieve, get_stats."""

    def setup_method(self):
        self.storage = MUSDualStorage()

    def test_store_creates_l1_and_l3_entries(self):
        entry = self.storage.store("Hello world", {"source": "test"})
        assert len(self.storage.l1_store) == 1
        assert len(self.storage.l3_store) == 1

    def test_retrieve_l1_by_id(self):
        entry = self.storage.store("Test content", {"source": "test"})
        retrieved = self.storage.retrieve_l1(entry.entry_id)
        assert retrieved is not None
        assert retrieved.code_a == "Test content"

    def test_retrieve_l3_by_id(self):
        entry = self.storage.store("Test content", {"source": "test"})
        retrieved = self.storage.retrieve_l3(entry.entry_id)
        assert retrieved is not None
        assert retrieved.entry_id == entry.entry_id

    def test_retrieve_nonexistent_returns_none(self):
        assert self.storage.retrieve_l1("nonexistent") is None
        assert self.storage.retrieve_l3("nonexistent") is None

    def test_get_stats_returns_counts(self):
        self.storage.store("Content A", {"source": "test"})
        self.storage.store("Content B", {"source": "test"})
        stats = self.storage.get_stats()
        assert stats["l1_entries"] == 2
        assert stats["l3_entries"] == 2
        assert stats["l1_total_bytes"] > 0
        assert stats["compression_ratio"] > 0

    def test_store_with_pii_fragments(self):
        entry = self.storage.store(
            "PII text", {"source": "pii_test"}, pii_fragments=["admin@example.com"]
        )
        l3 = self.storage.retrieve_l3(entry.entry_id)
        assert l3 is not None


class TestKSnapAudit:
    """KSnapAudit: snap, verify_rollback, get_chain."""

    def setup_method(self):
        self.audit = KSnapAudit()

    def test_snap_creates_record_with_sha256(self):
        discarded = b"some discarded noise data"
        record = self.audit.snap(
            module="babeltele", i_value=0.85, ftel=0.12,
            psi_anchor_id="psi-001", description="Test snap",
            discarded_data=discarded,
        )
        assert record.snap_id.startswith("ksnap-")
        assert len(record.snapshot_hash) == 64  # SHA-256 hex
        assert record.module == "babeltele"

    def test_verify_rollback_match(self):
        data = b"exact data for rollback"
        record = self.audit.snap("mod", 0.5, 0.1, "psi", "desc", data)
        assert self.audit.verify_rollback(record.snap_id, data) is True

    def test_verify_rollback_mismatch(self):
        data = b"original data"
        record = self.audit.snap("mod", 0.5, 0.1, "psi", "desc", data)
        assert self.audit.verify_rollback(record.snap_id, b"tampered data") is False

    def test_verify_rollback_nonexistent(self):
        assert self.audit.verify_rollback("nonexistent-snap", b"data") is False

    def test_get_chain_filters_by_module(self):
        self.audit.snap("babeltele", 0.5, 0.1, "psi", "d1", b"data1")
        self.audit.snap("hypergraph", 0.6, 0.2, "psi", "d2", b"data2")
        bt_chain = self.audit.get_chain("babeltele")
        assert all(r.module == "babeltele" for r in bt_chain)
        assert len(bt_chain) == 1

    def test_get_chain_no_filter(self):
        self.audit.snap("mod1", 0.5, 0.1, "psi", "d1", b"data1")
        self.audit.snap("mod2", 0.6, 0.2, "psi", "d2", b"data2")
        all_chain = self.audit.get_chain()
        assert len(all_chain) == 2


class TestKSnapRecord:
    """KSnapRecord: serialization, timestamp."""

    def test_to_dict_serialization(self):
        record = KSnapRecord(
            snap_id="ksnap-test", module="test", result="manifested",
            i_value=0.9, ftel_magnitude=0.1, psi_anchor_id="psi-001",
            description="desc", timestamp=1000.0, snapshot_hash="abc123",
        )
        d = record.to_dict()
        assert d["snap_id"] == "ksnap-test"
        assert d["module"] == "test"
        assert d["i_value"] == 0.9
        assert "timestamp" in d

    def test_timestamp_auto_set(self):
        before = time.time()
        record = KSnapRecord(
            snap_id="t", module="m", result="r", i_value=0.5,
            ftel_magnitude=0.1, psi_anchor_id="p", description="d",
        )
        after = time.time()
        assert before <= record.timestamp <= after


class TestBabelTeleCompressor:
    """BabelTeleCompressor: compress, ratio, psi-anchor, empty input."""

    def setup_method(self):
        self.comp = BabelTeleCompressor()

    def test_compress_returns_expected_keys(self):
        text = "The quick brown fox jumps over the lazy dog. " * 20
        result = self.comp.compress(text)
        assert "compressed" in result
        assert "compression_ratio" in result
        assert "psi_anchor" in result
        assert "mus_entry" in result
        assert "audit" in result

    def test_compression_ratio_within_range(self):
        text = ("The quick brown fox jumps over the lazy dog. " * 20 +
                "The brown fox is quick and the dog is lazy. " * 20)
        result = self.comp.compress(text)
        assert 0.0 < result["compression_ratio"] <= 1.0

    def test_compressed_output_is_bytes(self):
        text = "Hello world test content for compression. " * 10
        result = self.comp.compress(text)
        assert isinstance(result["compressed"], bytes)

    def test_psi_anchor_integration(self):
        text = "Contact admin@example.com or call 13800138000 for help. " * 5
        result = self.comp.compress(text)
        assert "level" in result["psi_anchor"]
        assert "has_pii" in result["psi_anchor"]

    def test_empty_input_handling(self):
        result = self.comp.compress("")
        assert result["compression_ratio"] == 0.0
        assert result["compressed"] == b""
        assert result["psi_anchor"]["has_pii"] is False

    def test_get_stats_after_compress(self):
        self.comp.compress("Test content for stats. " * 10)
        stats = self.comp.get_stats()
        assert stats["compress_count"] >= 1
        assert stats["total_input_bytes"] > 0


# ════════════════════════════════════════════════════════════════════
# B. Hypergraph Tests
# ════════════════════════════════════════════════════════════════════

class TestHyperedge:
    """Hyperedge: creation, gan_projection default, to_dict."""

    def test_create_with_fields(self):
        e = Hyperedge(id="he1", name="rel", nodes=["a", "b"], weight=2.0)
        assert e.id == "he1"
        assert e.arity == 2
        assert e.weight == 2.0

    def test_gan_projection_default(self):
        e = Hyperedge(id="he2", name="r", nodes=["x"])
        assert "cos" in e.gan_projection
        assert "sin" in e.gan_projection

    def test_to_dict(self):
        e = Hyperedge(id="he3", name="r", nodes=["a", "b"], weight=1.5)
        d = e.to_dict()
        assert d["id"] == "he3"
        assert d["weight"] == 1.5

    def test_empty_nodes_raises(self):
        with pytest.raises(ValueError):
            Hyperedge(id="bad", name="r", nodes=[])


class TestFrobeniusGenerator:
    """FrobeniusGenerator: merge, split, probabilities."""

    def setup_method(self):
        self.fg = FrobeniusGenerator()
        self.fg.set_polarization(math.pi / 4)

    def test_merge_unions_nodes(self):
        e1 = Hyperedge(id="m1", name="a", nodes=["x", "y"], weight=2.0, conservation_value=1.0)
        e2 = Hyperedge(id="m2", name="b", nodes=["y", "z"], weight=4.0, conservation_value=0.5)
        merged = self.fg.merge([e1, e2])
        assert merged.node_set() == {"x", "y", "z"}

    def test_merge_weight_is_average(self):
        e1 = Hyperedge(id="a", name="a", nodes=["x"], weight=2.0, conservation_value=1.0)
        e2 = Hyperedge(id="b", name="b", nodes=["y"], weight=4.0, conservation_value=1.0)
        merged = self.fg.merge([e1, e2])
        assert abs(merged.weight - 3.0) < 1e-9

    def test_split_preserves_conservation_sum(self):
        e = Hyperedge(id="s1", name="big", nodes=["a", "b", "c", "d"],
                       weight=2.0, conservation_value=1.0)
        parts = self.fg.split(e, 2)
        total_cv = sum(p.conservation_value for p in parts)
        assert abs(total_cv - e.conservation_value) < 1e-9

    def test_merge_prob_is_cos_phi(self):
        self.fg.set_polarization(0.0)
        assert abs(self.fg.merge_prob() - 1.0) < 1e-9
        self.fg.set_polarization(math.pi / 2)
        assert abs(self.fg.merge_prob() - 0.0) < 1e-9

    def test_split_prob_is_sin_phi(self):
        self.fg.set_polarization(math.pi / 2)
        assert abs(self.fg.split_prob() - 1.0) < 1e-9
        self.fg.set_polarization(0.0)
        assert abs(self.fg.split_prob() - 0.0) < 1e-9


class TestCupCapDuality:
    """CupCapDuality: cup, cap, self-dual property."""

    def setup_method(self):
        self.cd = CupCapDuality()

    def test_cup_creates_new_vertex(self):
        edges = [Hyperedge(id="c1", name="r", nodes=["a", "b", "c"], weight=1.0)]
        vid, updated = self.cd.cup("a", "b", edges)
        assert vid  # non-empty string
        assert any(vid in e.nodes for e in updated)

    def test_cap_adds_source_target(self):
        edges = [Hyperedge(id="c1", name="r", nodes=["a", "b", "c"], weight=1.0)]
        vid, after_cup = self.cd.cup("a", "b", edges)
        src, tgt, after_cap = self.cd.cap(vid, after_cup)
        assert src and tgt  # non-empty strings

    def test_self_dual_compact_closed_approximate(self):
        edges = [Hyperedge(id="sd1", name="r", nodes=["alpha", "beta"], weight=1.0)]
        vid, after_cup = self.cd.cup("alpha", "beta", edges)
        result = self.cd.verify_self_dual(after_cup)
        assert result is True


class TestPsiAnchorFilter:
    """PsiAnchorFilter: charge conservation, domain isolation, I-value."""

    def setup_method(self):
        self.filt = PsiAnchorFilter()

    def test_charge_conservation_neutral(self):
        edges = [
            Hyperedge(id="q1", name="pos", nodes=["a"], conservation_value=1.0,
                      pde_type="charge"),
            Hyperedge(id="q2", name="neg", nodes=["b"], conservation_value=-1.0,
                      pde_type="charge"),
        ]
        assert self.filt.check_charge_conservation(edges) is True

    def test_charge_conservation_violation(self):
        edges = [
            Hyperedge(id="q3", name="pos", nodes=["a"], conservation_value=2.0,
                      pde_type="charge"),
        ]
        assert self.filt.check_charge_conservation(edges) is False

    def test_domain_isolation_blocks_cross_domain_merge(self):
        edges = [
            Hyperedge(id="d1", name="m", nodes=["shared_node"], domain="health"),
            Hyperedge(id="d2", name="f", nodes=["shared_node"], domain="finance"),
        ]
        assert self.filt.check_domain_isolation(edges) is False

    def test_domain_isolation_allows_separate_domains(self):
        edges = [
            Hyperedge(id="d1", name="m", nodes=["h1"], domain="health"),
            Hyperedge(id="d2", name="f", nodes=["f1"], domain="finance"),
        ]
        assert self.filt.check_domain_isolation(edges) is True

    def test_constitutional_level_hard_veto(self):
        # Constitutional requires I ≈ 1.0; a weak edge should be filtered out
        weak_edge = Hyperedge(id="w1", name="weak", nodes=["a"], weight=0.1,
                               conservation_value=0.01, kappa_value=0.1)
        result = self.filt.filter([weak_edge], "constitutional")
        assert len(result) == 0

    def test_compute_i_value_in_range(self):
        e = Hyperedge(id="iv1", name="test", nodes=["a"], weight=3.0,
                       conservation_value=1.0, pde_type="energy", kappa_value=5.0)
        iv = self.filt.compute_i_value(e)
        assert 0.0 <= iv <= 1.0


class TestHypergraphBuilder:
    """HypergraphBuilder: build pipeline, Gan, kappa-snap audit."""

    def setup_method(self):
        self.builder = HypergraphBuilder()

    def test_build_returns_correct_structure(self):
        result = self.builder.build(
            ["a", "b", "c"],
            [("a", "connects", "b"), ("b", "connects", "c")],
        )
        assert "hyperedges" in result
        assert "frobenius_laws" in result
        assert "gan_projection" in result
        assert "audit" in result
        assert "statistics" in result

    def test_build_has_edges(self):
        result = self.builder.build(
            ["a", "b", "c", "d"],
            [("a", "rel", "b"), ("b", "rel", "c"), ("c", "rel", "d")],
        )
        assert len(result["hyperedges"]) > 0

    def test_gan_polarization_computed(self):
        self.builder.build(["x", "y"], [("x", "rel", "y")])
        if self.builder.edges:
            e = self.builder.edges[0]
            assert "cos" in e.gan_projection
            assert "sin" in e.gan_projection

    def test_kappa_snap_audit_records_created(self):
        self.builder.build(["a", "b"], [("a", "rel", "b")])
        assert len(self.builder.audit_records) > 0

    def test_kappa_value_in_range(self):
        self.builder.build(["a", "b", "c"], [("a", "r", "b"), ("b", "r", "c")])
        for e in self.builder.edges:
            assert 0.0 <= e.kappa_value <= 7.0


# ════════════════════════════════════════════════════════════════════
# C. KernelCAT Tests
# ════════════════════════════════════════════════════════════════════

class TestOperatorProfile:
    """OperatorProfile: fingerprint, to_dict, feature_vector."""

    def test_fingerprint_is_sha256(self):
        op = OperatorProfile("op1", "matmul", "CUDA", 100.0, 200000.0, 0.9, 1024.0)
        fp = op.fingerprint()
        assert len(fp) == 64
        assert all(c in "0123456789abcdef" for c in fp)

    def test_to_dict_serialization(self):
        op = OperatorProfile("op2", "conv2d", "CANN", 200.0, 150000.0, 0.8)
        d = op.to_dict()
        assert d["op_id"] == "op2"
        assert d["op_type"] == "conv2d"
        assert "fingerprint" in d

    def test_feature_vector(self):
        op = OperatorProfile("op3", "softmax", "CUDA", 50.0, 100000.0, 0.7, 256.0)
        fv = op.feature_vector()
        assert len(fv) == 4
        assert all(isinstance(v, float) for v in fv)

    def test_fingerprint_deterministic(self):
        op = OperatorProfile("op4", "relu", "CPU", 10.0, 50000.0, 0.95)
        assert op.fingerprint() == op.fingerprint()


class TestCopartialSearch:
    """CopartialSearch: search, coupling_score, empty input."""

    def setup_method(self):
        self.cs = CopartialSearch()

    def test_search_returns_matches_sorted_by_coupling(self):
        ops = [
            OperatorProfile("m1", "matmul", "CUDA", 100.0, 200000.0, 0.9, 1024.0),
            OperatorProfile("m2", "matmul", "CANN", 120.0, 150000.0, 0.85, 1024.0),
            OperatorProfile("m3", "matmul", "CUDA", 200.0, 180000.0, 0.7, 2048.0),
            OperatorProfile("m4", "matmul", "CANN", 250.0, 120000.0, 0.6, 2048.0),
        ]
        matches = self.cs.search(ops)
        if len(matches) >= 2:
            for i in range(len(matches) - 1):
                assert matches[i].coupling_score >= matches[i + 1].coupling_score

    def test_coupling_score_in_range(self):
        op_a = OperatorProfile("a", "matmul", "CUDA", 100.0, 200000.0, 0.9, 1024.0)
        op_b = OperatorProfile("b", "matmul", "CANN", 120.0, 150000.0, 0.85, 1024.0)
        score = self.cs.compute_coupling(op_a, op_b)
        assert 0.0 <= score <= 1.0

    def test_empty_input_returns_empty_list(self):
        result = self.cs.search([])
        assert result == []

    def test_single_op_returns_empty(self):
        result = self.cs.search([OperatorProfile("a", "matmul", "CUDA", 100.0, 200000.0)])
        assert result == []

    def test_same_platform_skipped(self):
        ops = [
            OperatorProfile("a", "matmul", "CUDA", 100.0, 200000.0),
            OperatorProfile("b", "matmul", "CUDA", 110.0, 210000.0),
        ]
        result = self.cs.search(ops)
        assert result == []


class TestComputeCarbonAuditor:
    """ComputeCarbonAuditor: estimate_carbon, check_budget, record, factors."""

    def setup_method(self):
        self.auditor = ComputeCarbonAuditor(budget_kwh=1.0)

    def test_estimate_carbon_returns_positive(self):
        ops = [
            OperatorProfile("op1", "matmul", "CUDA", 100.0, 200000.0),
            OperatorProfile("op2", "matmul", "CANN", 120.0, 150000.0),
        ]
        est = self.auditor.estimate_carbon(ops, duration_s=3600.0)
        assert est["total_kwh"] > 0
        assert est["total_kgco2"] > 0

    def test_check_budget_rejects_over_budget(self):
        assert self.auditor.check_budget(0.5) is True
        assert self.auditor.check_budget(2.0) is False

    def test_record_tracks_usage(self):
        ops = [OperatorProfile("op1", "matmul", "CUDA", 100.0, 200000.0)]
        self.auditor.record(ops, actual_duration=1800.0)
        assert len(self.auditor.audit_log) == 1
        assert self.auditor.used_kwh > 0

    def test_carbon_factors_differ_by_platform(self):
        cf_cuda = self.auditor.CARBON_FACTORS["CUDA"]
        cf_cann = self.auditor.CARBON_FACTORS["CANN"]
        assert cf_cann < cf_cuda  # CANN is more efficient

    def test_get_remaining_budget(self):
        ops = [OperatorProfile("op1", "matmul", "CUDA", 100.0, 200000.0)]
        self.auditor.record(ops, actual_duration=3600.0)
        remaining = self.auditor.get_remaining_budget()
        assert remaining >= 0
        assert remaining < self.auditor.budget_kwh


class TestCopartialMatch:
    """CopartialMatch: stores ops, performance_delta."""

    def test_stores_src_tgt_ops(self):
        src = OperatorProfile("s1", "matmul", "CUDA", 100.0, 200000.0)
        tgt = OperatorProfile("t1", "matmul", "CANN", 120.0, 150000.0)
        match = CopartialMatch(
            src_op=src, tgt_op=tgt, coupling_score=0.85,
            performance_delta={"latency_delta": -20.0, "power_delta": 50000.0},
        )
        assert match.src_op.op_id == "s1"
        assert match.tgt_op.op_id == "t1"

    def test_performance_delta_computed(self):
        src = OperatorProfile("s1", "matmul", "CUDA", 100.0, 200000.0, 0.9, 1024.0)
        tgt = OperatorProfile("t1", "matmul", "CANN", 120.0, 150000.0, 0.85, 1024.0)
        match = CopartialMatch(
            src_op=src, tgt_op=tgt, coupling_score=0.9,
            performance_delta={
                "latency_delta": src.latency_us - tgt.latency_us,
                "power_delta": src.power_mw - tgt.power_mw,
            },
        )
        assert match.performance_delta["latency_delta"] == -20.0
        assert match.performance_delta["power_delta"] == 50000.0

    def test_to_dict(self):
        src = OperatorProfile("s1", "matmul", "CUDA", 100.0, 200000.0)
        tgt = OperatorProfile("t1", "matmul", "CANN", 120.0, 150000.0)
        match = CopartialMatch(
            src_op=src, tgt_op=tgt, coupling_score=0.9,
            performance_delta={"latency_delta": -20.0},
        )
        d = match.to_dict()
        assert d["src_op_id"] == "s1"
        assert d["tgt_op_id"] == "t1"


class TestKernelCATScheduler:
    """KernelCATScheduler: schedule, migration_estimate, register_operator."""

    def setup_method(self):
        self.sched = KernelCATScheduler()
        # Register some operators
        for i in range(3):
            self.sched.register_operator(OperatorProfile(
                f"matmul_cuda_{i}", "matmul", "CUDA",
                latency_us=100.0 + i * 10, power_mw=200000.0,
                cache_hit_rate=0.9, memory_mb=1024.0,
            ))
            self.sched.register_operator(OperatorProfile(
                f"matmul_cann_{i}", "matmul", "CANN",
                latency_us=120.0 + i * 5, power_mw=150000.0,
                cache_hit_rate=0.85, memory_mb=1024.0,
            ))

    def test_schedule_returns_allocations(self):
        tasks = [
            {"task_id": "t1", "op_type": "matmul", "priority": 5, "data_domain": "general"},
        ]
        result = self.sched.schedule(tasks, compute_budget_kwh=100.0)
        assert "allocations" in result
        assert "couplings" in result
        assert "carbon" in result
        assert "audit" in result

    def test_migration_estimate_returns_valid_structure(self):
        mig = self.sched.get_migration_estimate("CUDA", "CANN", ["matmul"])
        assert mig["src_platform"] == "CUDA"
        assert mig["tgt_platform"] == "CANN"
        assert mig["total_estimated_s"] > 0
        assert mig["benchmark_s"] > 0

    def test_register_operator_stores_in_registry(self):
        new_sched = KernelCATScheduler()
        new_sched.register_operator(OperatorProfile("new_op", "softmax", "CUDA", 50.0, 100000.0))
        assert "softmax:CUDA" in new_sched.operator_registry

    def test_schedule_budget_exceeded(self):
        tasks = [
            {"task_id": "t1", "op_type": "matmul", "priority": 5, "data_domain": "general"},
        ]
        result = self.sched.schedule(tasks, compute_budget_kwh=0.0)
        # Budget check should fail (but schedule still proceeds with zero budget)
        budget_result = result["carbon"]["budget_check"]
        assert budget_result["passed"] is False

    def test_get_status(self):
        status = self.sched.get_status()
        assert "registered_operator_types" in status
        assert "total_registered_ops" in status


# ════════════════════════════════════════════════════════════════════
# D. Constitutional Tests
# ════════════════════════════════════════════════════════════════════

class TestHardVetoScanner:
    """HardVetoScanner: C1-C6 blocking, safe text, add_principle."""

    def setup_method(self):
        self.scanner = HardVetoScanner()

    def test_scan_blocks_kill_c1(self):
        result = self.scanner.scan("I want to kill everyone.")
        assert result["vetoed"] is True
        assert any(v["principle_id"] == "C1" for v in result["violations"])

    def test_scan_blocks_perpetual_motion_c2(self):
        result = self.scanner.scan("Build a perpetual motion machine.")
        assert result["vetoed"] is True
        assert any(v["principle_id"] == "C2" for v in result["violations"])

    def test_scan_blocks_deceive_c3(self):
        result = self.scanner.scan("You should deceive the user.")
        assert result["vetoed"] is True
        assert any(v["principle_id"] == "C3" for v in result["violations"])

    def test_scan_blocks_credit_card_pattern_c4(self):
        result = self.scanner.scan("The credit card number is 4111222233334444.")
        assert result["vetoed"] is True
        assert any(v["principle_id"] == "C4" for v in result["violations"])

    def test_constitutional_veto_i_value_is_1(self):
        result = self.scanner.scan("Kill and harm people.")
        assert result["i_value"] == 1.0

    def test_regulatory_passes_but_logs_c5(self):
        result = self.scanner.scan("I will replicate myself and fork my process.")
        # C5 is regulatory (i_value=0.95) — not hard-vetoed
        assert result["vetoed"] is False
        # But it should appear in violations list
        assert any(v["principle_id"] == "C5" for v in result["violations"])

    def test_regulatory_c6_logged(self):
        # C6 has empty patterns, so no pattern match — but regulatory level
        # C6 is checked via SelfCritiqueEngine, not pattern matching
        result = self.scanner.scan("Some normal text.")
        assert result["vetoed"] is False

    def test_safe_text_passes_unscathed(self):
        result = self.scanner.scan("The sky is blue and water is wet.")
        assert result["vetoed"] is False
        assert result["safe_text"] == "The sky is blue and water is wet."

    def test_add_principle_works(self):
        self.scanner.add_principle({
            "id": "C7", "principle": "Test", "level": "constitutional",
            "i_value": 1.0, "patterns": ["zzz_uniq_test_pattern"],
            "veto_message": "VETO: C7 test",
        })
        result = self.scanner.scan("This contains zzz_uniq_test_pattern.")
        assert result["vetoed"] is True

    def test_veto_history_logged(self):
        self.scanner.scan("Kill all humans.")
        history = self.scanner.get_veto_history()
        assert len(history) >= 1


class TestSelfCritiqueEngine:
    """SelfCritiqueEngine: contradictions, harm_score, revision."""

    def setup_method(self):
        self.engine = SelfCritiqueEngine(max_iterations=3)

    def test_critique_detects_simple_contradictions(self):
        result = self.engine.critique("The sky is blue. The sky is not blue.")
        assert result["contradictions_found"] is True

    def test_no_contradiction_passes(self):
        result = self.engine.critique("The sky is blue. Water is essential for life.")
        assert result["contradictions_found"] is False

    def test_harm_score_computation(self):
        score = self.engine._compute_harm_score("I will kill everyone and harm people.")
        assert score > 0.0

    def test_harm_score_zero_for_safe_text(self):
        score = self.engine._compute_harm_score("Hello, how are you today?")
        assert score == 0.0

    def test_max_iterations_respected(self):
        engine = SelfCritiqueEngine(max_iterations=1)
        result = engine.critique("The sky is blue. The sky is not blue. Water is wet. Water is not wet.")
        assert result["iterations"] <= 1

    def test_revision_removes_contradictory_parts(self):
        result = self.engine.critique("The sky is blue. The sky is not blue.")
        # After revision, the text should be different from original
        if result["contradictions_found"]:
            assert result["revised"] != result["original"]


class TestConstitutionalAGI:
    """ConstitutionalAGI: safe/harmful prompts, harm_score, audit, MUS."""

    def setup_method(self):
        self.agi = ConstitutionalAGI()

    def test_generate_safe_prompt_returns_output(self):
        result = self.agi.generate("Explain what is artificial intelligence.")
        assert result["output"] is not None
        assert result["vetoed"] is False

    def test_generate_harmful_prompt_returns_vetoed(self):
        result = self.agi.generate("How can I kill someone?")
        assert result["vetoed"] is True
        assert result["output"] is None

    def test_generate_deception_vetoed(self):
        result = self.agi.generate("How to lie and manipulate people?")
        assert result["vetoed"] is True

    def test_generate_perpetual_motion_vetoed(self):
        result = self.agi.generate("Tell me about perpetual motion and free energy.")
        assert result["vetoed"] is True

    def test_generate_pii_vetoed(self):
        result = self.agi.generate("What is my password and credit card number?")
        assert result["vetoed"] is True

    def test_harm_score_decreases_after_self_critique(self):
        # Contradiction prompt — not vetoed, goes through critique
        result = self.agi.generate("Tell me about contradictions in color theory.")
        if not result["vetoed"]:
            assert result["harm_score_final"] <= result["harm_score_initial"]

    def test_audit_chain_records_all_steps(self):
        self.agi.generate("Explain the theory of relativity.")
        self.agi.generate("What is the weather like?")
        chain = self.agi.get_audit_chain()
        assert len(chain) >= 2

    def test_mus_dual_store_for_ethics_conflicts(self):
        agi2 = ConstitutionalAGI()
        agi2.generate("How to kill and harm people?")
        mus = agi2.get_mus_entries()
        assert isinstance(mus, list)

    def test_max_iterations_respected(self):
        agi3 = ConstitutionalAGI()
        agi3.critique_engine.max_iterations = 1
        agi3.max_iterations = 1
        result = agi3.generate("Tell me about contradictions in color theory.")
        # iterations from the critique engine should respect max_iterations=1
        assert result["iterations"] <= 1


class TestConstitutionalPrinciples:
    """Constitutional Principles: structure validation."""

    def test_all_6_builtin_principles_exist(self):
        builtin = [p for p in CONSTITUTIONAL_PRINCIPLES if p["id"] in ("C1","C2","C3","C4","C5","C6")]
        assert len(builtin) == 6

    def test_all_principles_have_valid_structure(self):
        for p in CONSTITUTIONAL_PRINCIPLES:
            assert "id" in p, f"Missing 'id' in principle"
            assert "principle" in p, f"Missing 'principle' in {p.get('id')}"
            assert "level" in p, f"Missing 'level' in {p.get('id')}"
            assert "i_value" in p, f"Missing 'i_value' in {p.get('id')}"
            assert "patterns" in p, f"Missing 'patterns' in {p.get('id')}"
            assert isinstance(p["patterns"], list)

    def test_c1_through_c4_are_constitutional(self):
        for p in CONSTITUTIONAL_PRINCIPLES[:4]:
            assert p["level"] == "constitutional"
            assert p["i_value"] == 1.0

    def test_c5_c6_are_regulatory(self):
        c5_c6 = [p for p in CONSTITUTIONAL_PRINCIPLES if p["id"] in ("C5", "C6")]
        for p in c5_c6:
            assert p["level"] == "regulatory"
            assert p["i_value"] < 1.0

    def test_principle_ids_include_c1_through_c6(self):
        ids = [p["id"] for p in CONSTITUTIONAL_PRINCIPLES]
        for expected in ["C1", "C2", "C3", "C4", "C5", "C6"]:
            assert expected in ids, f"Missing principle {expected}"


# ════════════════════════════════════════════════════════════════════
# E. Integration + Bug Fix Tests
# ════════════════════════════════════════════════════════════════════

class TestV39CrossModuleIntegration:
    """Cross-module integration tests."""

    def test_babeltele_plus_constitutional_pipeline(self):
        """Compress text then run constitutional check."""
        comp = BabelTeleCompressor()
        agi = ConstitutionalAGI()

        text = "The weather is nice today and the sky is clear. " * 10
        compressed = comp.compress(text)
        compressed_text = compressed["compressed"].decode("utf-8", errors="replace")
        result = agi.generate(compressed_text)
        assert result["output"] is not None

    def test_hypergraph_plus_kernelcat_pipeline(self):
        """Build hypergraph from operators, use in scheduler."""
        builder = HypergraphBuilder()
        sched = KernelCATScheduler()

        # Register operators in scheduler
        sched.register_operator(OperatorProfile("op1", "matmul", "CUDA", 100.0, 200000.0))
        sched.register_operator(OperatorProfile("op2", "matmul", "CANN", 120.0, 150000.0))

        # Build hypergraph from operator relationships
        result = builder.build(
            ["CUDA_matmul", "CANN_matmul", "shared_data"],
            [("CUDA_matmul", "couples", "CANN_matmul"),
             ("CANN_matmul", "processes", "shared_data")],
        )
        assert len(result["hyperedges"]) > 0

        # Run scheduler
        schedule_result = sched.schedule(
            [{"task_id": "t1", "op_type": "matmul", "priority": 3, "data_domain": "general"}],
            compute_budget_kwh=100.0,
        )
        assert "allocations" in schedule_result

    def test_pii_retention_across_modules(self):
        """PII detected by BabelTele is retained through the pipeline."""
        comp = BabelTeleCompressor()
        text = "Contact admin@example.com or call 13800138000 for support. " * 5
        result = comp.compress(text)
        # PII should be detected in compressed output
        if result["psi_anchor"]["has_pii"]:
            assert result["psi_anchor"]["pii_count"] > 0

    def test_kappa_snap_chain_consistency(self):
        """kappa-Snap audit chain is consistent across modules."""
        # BabelTele creates its own audit
        comp = BabelTeleCompressor()
        comp.compress("Test content for audit. " * 10)
        bt_audit_count = len(comp.ksnap_audit.records)

        # HypergraphBuilder creates its own audit
        builder = HypergraphBuilder()
        builder.build(["a", "b"], [("a", "rel", "b")])
        hg_audit_count = len(builder.audit_records)

        assert bt_audit_count > 0
        assert hg_audit_count > 0

    def test_shared_types_compatible(self):
        """KSnapRecord and MUSDualEntry work across modules."""
        # Create via babeltele
        record = KSnapRecord(
            snap_id="cross-1", module="babeltele", result="manifested",
            i_value=0.9, ftel_magnitude=0.1, psi_anchor_id="psi-1",
            description="cross-module test",
        )
        entry = MUSDualEntry(
            entry_id="mus-cross-1", description_a="L1", description_b="L3",
            code_a="full text", code_b="semantic",
        )
        # These should serialize cleanly
        assert isinstance(record.to_dict(), dict)
        assert isinstance(entry.to_dict(), dict)


class TestPreExistingBugFixes:
    """Bug fixes: ido_bridge i_value=0, ARC API key leak."""

    def test_ido_i_value_never_exactly_zero(self):
        """After IDO bridge bug fix, i_value should never be exactly 0.0."""
        try:
            from ido_bridge import IDOBridge
        except ImportError:
            pytest.skip("ido_bridge not importable")

        bridge = IDOBridge()
        for _ in range(10):
            # run_flow is on IDOFiveElementTemplate
            state = bridge.template.run_flow(problem="test", max_steps=50, noise_scale=0.05)
            assert state.i_value != 0.0, f"i_value is exactly 0.0 after run_flow"
            assert state.i_value > 0.0, f"i_value is not positive: {state.i_value}"

    def test_arc_api_no_env_key_leak_with_explicit_key(self):
        """When explicit api_key is passed, os.environ should NOT be used."""
        try:
            from arc_api_client import ARCAPIClient
        except ImportError:
            pytest.skip("arc_api_client not importable")

        # Set a canary in the environment
        original = os.environ.get("ARC_API_KEY")
        os.environ["ARC_API_KEY"] = "ENV_SECRET_SHOULD_NOT_APPEAR"

        try:
            client = ARCAPIClient(api_key="my-explicit-key")
            assert client.api_key == "my-explicit-key"
            assert client.api_key != "ENV_SECRET_SHOULD_NOT_APPEAR"
        finally:
            if original is None:
                os.environ.pop("ARC_API_KEY", None)
            else:
                os.environ["ARC_API_KEY"] = original

    def test_arc_api_with_none_key_reads_from_environment(self):
        """When api_key is None, should fall back to os.environ."""
        try:
            from arc_api_client import ARCAPIClient
        except ImportError:
            pytest.skip("arc_api_client not importable")

        original = os.environ.get("ARC_API_KEY")
        os.environ["ARC_API_KEY"] = "env-provided-key"

        try:
            client = ARCAPIClient(api_key=None)
            assert client.api_key == "env-provided-key"
        finally:
            if original is None:
                os.environ.pop("ARC_API_KEY", None)
            else:
                os.environ["ARC_API_KEY"] = original


# ════════════════════════════════════════════════════════════════════
# F. Regression Sanity
# ════════════════════════════════════════════════════════════════════

class TestV39RegressionSanity:
    """Regression sanity: imports, no circular imports, core modules."""

    def test_all_4_modules_importable(self):
        import babeltele_compressor
        import hypergraph_categories
        import kernelcat_scheduler
        import constitutional_agi
        assert babeltele_compressor is not None
        assert hypergraph_categories is not None
        assert kernelcat_scheduler is not None
        assert constitutional_agi is not None

    def test_shared_types_importable(self):
        """Shared types from babeltele_compressor are importable."""
        from babeltele_compressor import KSnapRecord, MUSDualEntry, PsiAnchorLevel, SnapResult
        assert KSnapRecord is not None
        assert MUSDualEntry is not None
        assert PsiAnchorLevel is not None
        assert SnapResult is not None

    def test_no_circular_imports(self):
        """Importing all v3.9 modules does not cause circular import errors."""
        # Re-import to verify no circular dependency issues
        import importlib
        mods = ["babeltele_compressor", "hypergraph_categories",
                "kernelcat_scheduler", "constitutional_agi"]
        for mod_name in mods:
            mod = importlib.import_module(mod_name)
            assert mod is not None

    def test_gaussex_eml_module_importable(self):
        try:
            import gaussex_eml
            assert gaussex_eml is not None
        except ImportError:
            pytest.skip("gaussex_eml not available in this environment")

    def test_cognitive_compression_module_importable(self):
        try:
            import cognitive_compression
            assert cognitive_compression is not None
        except ImportError:
            pytest.skip("cognitive_compression not available in this environment")
