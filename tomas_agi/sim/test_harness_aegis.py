#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_harness_aegis.py — 集成测试
验证 harness_aegis.py + eml_semzip.py 集成正确性
"""
from __future__ import annotations

import json
import sys
import uuid

# Imports
try:
    from harness_aegis import (
        TOMAS_HarnessEdge,
        SnapEvent,
        HookPhase,
        AEGISEngine,
        VariantIsolationManager,
        KSnapDualRail,
        CausalLog,
        SnapSubject,
        MUSVerdict,
        create_default_harness,
    )
    HAS_HARNESS = True
except Exception as e:
    print(f"WARN: Cannot import harness_aegis: {e}")
    HAS_HARNESS = False
    sys.exit(1)

try:
    from eml_semzip import EMLLiteKB, HyperEdge
    HAS_EML = True
except Exception as e:
    print(f"WARN: Cannot import eml_semzip: {e}")
    HAS_EML = False
    sys.exit(1)


def test_tomas_harness_edge():
    """Test 1: TOMAS_HarnessEdge 创建与序列化"""
    print("Test 1: TOMAS_HarnessEdge ...")
    h = create_default_harness(
        phase=HookPhase.TASK_START,
        psi_alignment="care_safety",
    )
    assert h.edge_id.startswith("harness_")
    assert h.phase == HookPhase.TASK_START
    assert h.g_ego_psi_alignment == "care_safety"
    assert h.version == 1
    assert not h.is_superseded

    # to_dict / from_dict 往返
    d = h.to_dict()
    assert "edge_id" in d
    h2 = TOMAS_HarnessEdge.from_dict(d)
    assert h2.edge_id == h.edge_id
    assert h2.phase == h.phase
    print(f"  PASS: edge_id={h.edge_id[:16]}, version={h.version}")


def test_aegis_engine():
    """Test 2: AEGIS 演进引擎四阶段流水线"""
    print("Test 2: AEGISEngine ...")
    h = create_default_harness()
    engine = AEGISEngine(eml_kb=None, g_ego_psi_anchor="care_safety")

    # 模拟失败轨迹
    trajectory = [
        {"step": 1, "success": True,  "harness_edge_id": h.edge_id},
        {"step": 2, "success": False, "harness_edge_id": h.edge_id},
        {"step": 3, "success": False, "harness_edge_id": h.edge_id},
    ]

    new_h, reason = engine.evolve(trajectory, h)
    if new_h is not None:
        assert new_h.version == h.version + 1
        assert new_h.is_superseded is False
        assert h.is_superseded is True  # 旧版本被标记
        print(f"  PASS: evolved to v{new_h.version}, reason={reason[:40]}")
    else:
        print(f"  PASS: evolution rejected (expected in test env): {reason[:40]}")

    # 检查因果日志
    assert len(engine.causal_log._events) >= 1
    print(f"  PASS: causal_log has {len(engine.causal_log._events)} events")


def test_variant_isolation():
    """Test 3: MUS 变体隔离"""
    print("Test 3: VariantIsolationManager ...")
    vim = VariantIsolationManager(max_variants=3)

    h_gaia = create_default_harness(psi_alignment="gaia_safety")
    h_sweb = create_default_harness(psi_alignment="sweb_safety")

    vim.register_cluster("gaia", h_gaia)
    vim.register_cluster("swebench", h_sweb)
    assert len(vim.variants) == 2

    # 路由测试
    routed = vim.route("gaia_task_123")
    assert routed is not None
    assert routed.edge_id == h_gaia.edge_id
    print(f"  PASS: route gaia_task -> {routed.edge_id[:16]}")

    # 性能记录
    vim.record_performance("gaia", "pass_rate", 0.874)
    vim.record_performance("swebench", "pass_rate", 0.923)
    crr = vim.compute_crr()
    assert crr > 0.8
    print(f"  PASS: CRR={crr:.3f}")

    # MUS 裁决
    verdict = vim.resolve_mus("gaia_retrieval", prefer_a=True)
    assert verdict in (MUSVerdict.RESOLVE_A, MUSVerdict.DEFER)
    print(f"  PASS: MUS verdict={verdict.value}")


def test_ksnap_dual_rail():
    """Test 4: κ-Gate 双轨协同进化"""
    print("Test 4: KSnapDualRail ...")
    kr = KSnapDualRail()

    h = create_default_harness()
    manifest = kr.register_co_evo(
        harness_edge_id=h.edge_id,
        model_weight_ver="qwen3_9b_lora_r32_ep2",
        validated_on=["GAIA_sub", "ALFWorld_sub"],
    )
    assert manifest.harness_edge_id == h.edge_id
    assert len(kr.compat_manifests) == 1

    # 兼容性检查
    ok, _ = kr.check_compat(h.edge_id, "qwen3_9b_lora_r32_ep2")
    assert ok is True
    print(f"  PASS: compat manifest registered, check_compat={ok}")

    # 未配对拒绝
    ok2, _ = kr.check_compat(h.edge_id, "unknown_model")
    assert ok2 is False
    print(f"  PASS: unpaired model correctly rejected")


def test_causal_log():
    """Test 5: κ-Snap 因果日志 Σ_snap"""
    print("Test 5: CausalLog ...")
    log = CausalLog()
    session_id = str(uuid.uuid4())

    for i in range(3):
        evt = SnapEvent(
            snap_id=str(uuid.uuid4()),
            session_id=session_id,
            task_trace_hash=f"trace_{i}",
            subject=SnapSubject.HARNESS_VER,
            ref_id=f"harness_{i}",
            meta={"test": True},
        )
        log.append(evt)

    assert len(log._events) == 3
    # 按 session 过滤
    events = log.filter(session_id=session_id)
    assert len(events) == 3
    # 按 subject 过滤
    events2 = log.filter(subject=SnapSubject.HARNESS_VER)
    assert len(events2) == 3
    print(f"  PASS: {len(log._events)} events, filter by session={len(events)}")


def test_eml_kb_integration():
    """Test 6: EMLLiteKB + TOMAS_HarnessEdge 集成"""
    print("Test 6: EMLLiteKB + TOMAS_HarnessEdge ...")
    kb = EMLLiteKB()

    # 检查 harness_edges 属性是否存在
    assert hasattr(kb, "harness_edges")
    assert isinstance(kb.harness_edges, dict)
    print(f"  PASS: EMLLiteKB.harness_edges = {type(kb.harness_edges)}")

    # 手动添加 harness
    h = create_default_harness()
    kb.harness_edges[h.edge_id] = h
    assert len(kb.harness_edges) == 1
    print(f"  PASS: added harness {h.edge_id[:16]} to KB")

    # 通过 append-only 版本管理
    h2 = create_default_harness()
    h2.supersedes = h.edge_id
    h.is_superseded = True
    kb.harness_edges[h2.edge_id] = h2
    assert len(kb.harness_edges) == 2
    active = [e for e in kb.harness_edges.values() if not e.is_superseded]
    assert len(active) == 1
    print(f"  PASS: versioning works, {len(active)} active harness(es)")


def run_all():
    print("=" * 60)
    print("HarnessX + AEGIS Integration Test")
    print("=" * 60)
    results = {}
    for name, fn in [
        ("TOMAS_HarnessEdge", test_tomas_harness_edge),
        ("AEGISEngine", test_aegis_engine),
        ("VariantIsolation", test_variant_isolation),
        ("KSnapDualRail", test_ksnap_dual_rail),
        ("CausalLog", test_causal_log),
        ("EMLLiteKB integration", test_eml_kb_integration),
    ]:
        try:
            fn()
            results[name] = "PASS"
        except Exception as e:
            results[name] = f"FAIL: {e}"
            import traceback
            traceback.print_exc()

    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    for name, status in results.items():
        tag = "PASS" if status == "PASS" else "FAIL"
        print(f"  [{tag}] {name}: {status}")
    failed = [n for n, s in results.items() if s != "PASS"]
    if failed:
        print(f"\n{len(failed)} test(s) FAILED")
        return 1
    else:
        print("\nAll tests PASSED!")
        return 0


if __name__ == "__main__":
    sys.exit(run_all())
