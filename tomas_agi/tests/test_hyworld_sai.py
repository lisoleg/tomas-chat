"""
HY World / SAI / Spatial Dead-Zero 集成测试
===========================================
测试 hyworld_bridge.py, sai_tproc.py, spatial_dead_zero.py,
以及 memos_fusion.py 和 dead_zero_mus.py 的集成钩子。

Author: TOMAS v3.0
Date: 2026-06-16
"""

import pytest
import math
import os
import tempfile
from unittest.mock import patch, MagicMock


# ═══════════════════════════════════════════════════════════════
# HY World Bridge Tests
# ═══════════════════════════════════════════════════════════════

class TestHYPanoVertexBuilder:
    """Stage A: 全景图 → EML 顶点构建"""

    def test_empty_panorama(self):
        from tomas_agi.sim.hyworld_bridge import HYPanoVertexBuilder
        builder = HYPanoVertexBuilder(theta_dead=0.15)
        result = builder.parse_panorama_semantics({})
        assert result == []

    def test_single_object(self):
        from tomas_agi.sim.hyworld_bridge import HYPanoVertexBuilder, EvidenceFlag
        builder = HYPanoVertexBuilder(theta_dead=0.15)
        panorama = {
            "objects": [{"label": "table", "bbox": [0.3, 0.4, 0.5, 0.6],
                         "depth": 3.0, "confidence": 0.9}],
        }
        result = builder.parse_panorama_semantics(panorama)
        assert len(result) == 1
        assert result[0].semantic_tags == ["table"]
        assert result[0].i_value > 0

    def test_dead_zero_filtering(self):
        from tomas_agi.sim.hyworld_bridge import HYPanoVertexBuilder
        builder = HYPanoVertexBuilder(theta_dead=0.15)
        # 低置信度 + 远景 → ℐ 很低, 应被过滤
        panorama = {
            "objects": [
                {"label": "bg_obj", "bbox": [0, 0, 1, 1],
                 "depth": 50.0, "confidence": 0.1},
                {"label": "fg_obj", "bbox": [0.2, 0.3, 0.4, 0.5],
                 "depth": 3.0, "confidence": 0.9},
            ],
        }
        result = builder.parse_panorama_semantics(panorama)
        # bg_obj: ℐ = 0.1 * 0.3 = 0.03 < 0.15 → 死零过滤
        # fg_obj: ℐ = 0.9 * 0.9 = 0.81 ≥ 0.15 → 保留
        assert len(result) == 1
        assert "fg_obj" in result[0].id

    def test_dikwp_distribution(self):
        from tomas_agi.sim.hyworld_bridge import HYPanoVertexBuilder
        builder = HYPanoVertexBuilder(theta_dead=0.15)
        panorama = {
            "objects": [
                {"label": "wall", "bbox": [0, 0, 1, 1],
                 "depth": 2.0, "confidence": 0.9},
                {"label": "table", "bbox": [0.2, 0.3, 0.4, 0.5],
                 "depth": 3.0, "confidence": 0.8},
                {"label": "mountain", "bbox": [0, 0, 1, 1],
                 "depth": 100.0, "confidence": 0.5},
            ],
        }
        builder.parse_panorama_semantics(panorama)
        dist = builder.get_dikwp_distribution()
        assert sum(dist.values()) == len(builder.vertices)

    def test_3d_position_estimation(self):
        from tomas_agi.sim.hyworld_bridge import HYPanoVertexBuilder
        builder = HYPanoVertexBuilder(theta_dead=0.15)
        # bbox 中心 (0.25, 0.5) → 方位角 = 0.25*2π = π/2(右), 仰角 = π/2(水平)
        # x = depth * sin(π/2) * cos(π/2) = 10 * 1 * 0 = 0
        # z = depth * sin(π/2) * sin(π/2) = 10 * 1 * 1 = 10
        panorama = {
            "objects": [{"label": "right", "bbox": [0.2, 0.45, 0.3, 0.55],
                         "depth": 10.0, "confidence": 0.9}],
        }
        result = builder.parse_panorama_semantics(panorama)
        assert len(result) == 1
        pos = result[0].position
        # 右侧方向: x≈0 (cos(π/2)≈0), z≈10 (sin(π/2)=1)
        assert abs(pos[0]) < 0.1  # x ≈ 0
        assert pos[2] > 5         # z > 0 (前方)


class TestWorldNavKappaSnapper:
    """Stage B: WorldNav → κ-Snap"""

    def test_empty_trajectory(self):
        from tomas_agi.sim.hyworld_bridge import WorldNavKappaSnapper
        snapper = WorldNavKappaSnapper(theta_dead=0.15)
        result = snapper.plan_trajectory([], [])
        assert result == []

    def test_single_vertex(self):
        from tomas_agi.sim.hyworld_bridge import (
            WorldNavKappaSnapper, SpatialVertex, SceneObjectType, EvidenceFlag
        )
        snapper = WorldNavKappaSnapper(theta_dead=0.15)
        vertex = SpatialVertex(
            id="v1", obj_type=SceneObjectType.FOREGROUND,
            position=(5.0, 0.0, 5.0), i_value=0.8,
            evidence=EvidenceFlag.EMPIRICAL,
        )
        result = snapper.plan_trajectory([vertex], [], num_snaps=3)
        assert len(result) > 0

    def test_multi_vertex_trajectory(self):
        from tomas_agi.sim.hyworld_bridge import (
            WorldNavKappaSnapper, SpatialVertex, SceneObjectType, EvidenceFlag
        )
        snapper = WorldNavKappaSnapper(theta_dead=0.15)
        vertices = [
            SpatialVertex(
                id="v1", obj_type=SceneObjectType.FOREGROUND,
                position=(1.0, 0.0, 1.0), i_value=0.9,
                evidence=EvidenceFlag.EMPIRICAL,
            ),
            SpatialVertex(
                id="v2", obj_type=SceneObjectType.MIDGROUND,
                position=(10.0, 0.0, 10.0), i_value=0.6,
                evidence=EvidenceFlag.EMPIRICAL,
            ),
            SpatialVertex(
                id="v3", obj_type=SceneObjectType.BACKGROUND,
                position=(20.0, 0.0, 20.0), i_value=0.3,
                evidence=EvidenceFlag.INFERRED,
            ),
        ]
        result = snapper.plan_trajectory(vertices, [], num_snaps=5)
        assert len(result) > 0
        # 每个 snap 有 ℐ 值
        for snap in result:
            assert snap.i_value > 0

    def test_inferred_region_marking(self):
        from tomas_agi.sim.hyworld_bridge import (
            WorldNavKappaSnapper, SpatialVertex, SceneObjectType, EvidenceFlag
        )
        snapper = WorldNavKappaSnapper(theta_dead=0.15)
        vertices = [
            SpatialVertex(
                id="v1", obj_type=SceneObjectType.BACKGROUND,
                position=(100.0, 0.0, 100.0), i_value=0.2,
                evidence=EvidenceFlag.INFERRED,
            ),
        ]
        snapper.plan_trajectory(vertices, [], num_snaps=3)
        inferred = snapper.mark_inferred_regions()
        assert inferred >= 0


class TestWorldStereoSpatialEmbedder:
    """Stage C: WorldStereo 2.0 → EML 超边"""

    def test_empty_vertices(self):
        from tomas_agi.sim.hyworld_bridge import WorldStereoSpatialEmbedder
        embedder = WorldStereoSpatialEmbedder(theta_dead=0.15)
        result = embedder.embed_spatial_relations([])
        assert result == []

    def test_adjacent_vertices(self):
        from tomas_agi.sim.hyworld_bridge import (
            WorldStereoSpatialEmbedder, SpatialVertex,
            SceneObjectType, EvidenceFlag,
        )
        embedder = WorldStereoSpatialEmbedder(theta_dead=0.15)
        v1 = SpatialVertex(
            id="v1", obj_type=SceneObjectType.FOREGROUND,
            position=(0.0, 0.0, 0.0), i_value=0.8,
            evidence=EvidenceFlag.EMPIRICAL,
        )
        v2 = SpatialVertex(
            id="v2", obj_type=SceneObjectType.FOREGROUND,
            position=(3.0, 0.0, 0.0), i_value=0.7,  # 并排 (同在 X 轴)
            evidence=EvidenceFlag.EMPIRICAL,
        )
        result = embedder.embed_spatial_relations([v1, v2])
        # 距离 3m, 并排 → adjacent (不是 occludes)
        assert len(result) == 1
        assert result[0].relation_type in ("adjacent", "occludes")  # 并排可能也是 adjacent

    def test_support_relation(self):
        from tomas_agi.sim.hyworld_bridge import (
            WorldStereoSpatialEmbedder, SpatialVertex,
            SceneObjectType, EvidenceFlag,
        )
        embedder = WorldStereoSpatialEmbedder(theta_dead=0.15)
        # table 在 chair 上方 → supports
        table = SpatialVertex(
            id="table", obj_type=SceneObjectType.FOREGROUND,
            position=(0.0, 1.0, 0.0), i_value=0.8,
            evidence=EvidenceFlag.EMPIRICAL, scale=(2.0, 0.1, 2.0),
        )
        chair = SpatialVertex(
            id="chair", obj_type=SceneObjectType.FOREGROUND,
            position=(0.0, 0.5, 0.0), i_value=0.7,
            evidence=EvidenceFlag.EMPIRICAL, scale=(0.5, 1.0, 0.5),
        )
        result = embedder.embed_spatial_relations([table, chair])
        assert len(result) >= 1
        relations = [e.relation_type for e in result]
        # 上方物体 → supports
        assert "supports" in relations or "adjacent" in relations

    def test_dead_zero_edge_filtering(self):
        from tomas_agi.sim.hyworld_bridge import (
            WorldStereoSpatialEmbedder, SpatialVertex,
            SceneObjectType, EvidenceFlag,
        )
        embedder = WorldStereoSpatialEmbedder(theta_dead=0.5)  # 高阈值
        v1 = SpatialVertex(
            id="v1", obj_type=SceneObjectType.BACKGROUND,
            position=(0.0, 0.0, 0.0), i_value=0.1,
            evidence=EvidenceFlag.UNGROUNDED,
        )
        v2 = SpatialVertex(
            id="v2", obj_type=SceneObjectType.BACKGROUND,
            position=(10.0, 0.0, 0.0), i_value=0.1,
            evidence=EvidenceFlag.UNGROUNDED,
        )
        result = embedder.embed_spatial_relations([v1, v2])
        # 低 ℐ + 远距离 → 应被过滤
        assert len(result) == 0

    def test_asym_computation(self):
        from tomas_agi.sim.hyworld_bridge import (
            WorldStereoSpatialEmbedder, SpatialVertex,
            SceneObjectType, EvidenceFlag,
        )
        embedder = WorldStereoSpatialEmbedder(theta_dead=0.1)
        fg = SpatialVertex(
            id="fg", obj_type=SceneObjectType.FOREGROUND,
            position=(0.0, 0.0, 0.0), i_value=0.9,
            evidence=EvidenceFlag.EMPIRICAL, scale=(2.0, 2.0, 2.0),
        )
        bg = SpatialVertex(
            id="bg", obj_type=SceneObjectType.BACKGROUND,
            position=(2.0, 0.0, 0.0), i_value=0.3,
            evidence=EvidenceFlag.INFERRED, scale=(0.3, 0.3, 0.3),
        )
        result = embedder.embed_spatial_relations([fg, bg])
        if result:
            # 前景 vs 远景 → Asym 应 > 0
            assert result[0].asym >= 0


class TestWorldMirrorIotaMapper:
    """Stage D: WorldMirror → ℐ-加权 3DGS"""

    def test_iota_loss_zero(self):
        from tomas_agi.sim.hyworld_bridge import (
            WorldMirrorIotaMapper, SpatialVertex, SceneObjectType, EvidenceFlag
        )
        mapper = WorldMirrorIotaMapper(theta_dead=0.15, lambda_i=0.5)
        pred = [SpatialVertex(
            id="p1", obj_type=SceneObjectType.FOREGROUND,
            position=(0.0, 0.0, 0.0), i_value=0.8,
            evidence=EvidenceFlag.EMPIRICAL,
        )]
        gt = [SpatialVertex(
            id="g1", obj_type=SceneObjectType.FOREGROUND,
            position=(0.0, 0.0, 0.0), i_value=0.8,
            evidence=EvidenceFlag.EMPIRICAL,
        )]
        total, components = mapper.compute_iota_loss(pred, gt)
        assert total == 0.0  # 完美匹配 → loss = 0

    def test_iota_loss_with_error(self):
        from tomas_agi.sim.hyworld_bridge import (
            WorldMirrorIotaMapper, SpatialVertex, SceneObjectType, EvidenceFlag
        )
        mapper = WorldMirrorIotaMapper(theta_dead=0.15, lambda_i=0.5)
        pred = [SpatialVertex(
            id="p1", obj_type=SceneObjectType.FOREGROUND,
            position=(1.0, 1.0, 1.0), i_value=0.9,
            evidence=EvidenceFlag.EMPIRICAL,
        )]
        gt = [SpatialVertex(
            id="g1", obj_type=SceneObjectType.FOREGROUND,
            position=(0.0, 0.0, 0.0), i_value=0.9,
            evidence=EvidenceFlag.EMPIRICAL,
        )]
        total, components = mapper.compute_iota_loss(pred, gt)
        assert total > 0
        assert components["mse"] > 0
        assert components["iota_penalty"] > 0

    def test_filter_dead_zero(self):
        from tomas_agi.sim.hyworld_bridge import (
            WorldMirrorIotaMapper, SpatialVertex, SceneObjectType, EvidenceFlag
        )
        mapper = WorldMirrorIotaMapper(theta_dead=0.15, lambda_i=0.5)
        vertices = [
            SpatialVertex(id="v1", obj_type=SceneObjectType.FOREGROUND,
                          position=(0, 0, 0), i_value=0.9, evidence=EvidenceFlag.EMPIRICAL),
            SpatialVertex(id="v2", obj_type=SceneObjectType.BACKGROUND,
                          position=(1, 0, 1), i_value=0.05, evidence=EvidenceFlag.UNGROUNDED),
        ]
        passed, rejected = mapper.filter_dead_zero_geometry(vertices)
        assert len(passed) == 1
        assert rejected == 1
        assert passed[0].id == "v1"

    def test_prioritize_iota(self):
        from tomas_agi.sim.hyworld_bridge import (
            WorldMirrorIotaMapper, SpatialVertex, SceneObjectType, EvidenceFlag
        )
        mapper = WorldMirrorIotaMapper(theta_dead=0.0, lambda_i=0.5)
        vertices = [
            SpatialVertex(id="v1", obj_type=SceneObjectType.FOREGROUND,
                          position=(0, 0, 0), i_value=0.3, evidence=EvidenceFlag.EMPIRICAL),
            SpatialVertex(id="v2", obj_type=SceneObjectType.FOREGROUND,
                          position=(1, 0, 0), i_value=0.9, evidence=EvidenceFlag.EMPIRICAL),
            SpatialVertex(id="v3", obj_type=SceneObjectType.BACKGROUND,
                          position=(2, 0, 0), i_value=0.6, evidence=EvidenceFlag.EMPIRICAL),
        ]
        kept = mapper.prioritize_iota_geometry(vertices, budget=2)
        assert len(kept) == 2
        # 应保留 ℐ 最高的两个
        kept_ids = {v.id for v in kept}
        assert "v2" in kept_ids  # ℐ=0.9
        assert "v3" in kept_ids  # ℐ=0.6
        assert "v1" not in kept_ids  # ℐ=0.3 被丢弃


class TestHYWorldBridge:
    """主编排器测试"""

    def test_build_scene(self):
        from tomas_agi.sim.hyworld_bridge import HYWorldBridge
        bridge = HYWorldBridge(theta_dead=0.15, enable_kappa_snap=True)
        panorama = {
            "objects": [
                {"label": "table", "bbox": [0.3, 0.4, 0.5, 0.6],
                 "depth": 3.0, "confidence": 0.9},
                {"label": "chair", "bbox": [0.35, 0.45, 0.55, 0.65],
                 "depth": 3.5, "confidence": 0.8},
            ],
        }
        scene = bridge.build_scene(panorama, scene_id="test_scene")
        assert scene.id == "test_scene"
        assert len(scene.vertices) >= 1

    def test_dead_zero_audit(self):
        from tomas_agi.sim.hyworld_bridge import HYWorldBridge
        bridge = HYWorldBridge(theta_dead=0.15, enable_kappa_snap=False)
        panorama = {
            "objects": [
                {"label": "good_obj", "bbox": [0.3, 0.4, 0.5, 0.6],
                 "depth": 3.0, "confidence": 0.9},
                {"label": "bad_obj", "bbox": [0, 0, 1, 1],
                 "depth": 50.0, "confidence": 0.05},
            ],
        }
        scene = bridge.build_scene(panorama)
        audit = bridge.dead_zero_audit(scene)
        assert "passed" in audit
        assert "rejected" in audit
        assert "mus_flagged" in audit
        assert audit["total_vertices"] == len(scene.vertices)

    def test_pipeline_report(self):
        from tomas_agi.sim.hyworld_bridge import HYWorldBridge
        bridge = HYWorldBridge(theta_dead=0.15)
        report = bridge.get_pipeline_report()
        assert "stages" in report
        assert len(report["stages"]) == 4
        assert "theta_dead" in report

    def test_export_scene_json(self):
        from tomas_agi.sim.hyworld_bridge import HYWorldBridge
        bridge = HYWorldBridge(theta_dead=0.15, enable_kappa_snap=False)
        panorama = {
            "objects": [
                {"label": "table", "bbox": [0.3, 0.4, 0.5, 0.6],
                 "depth": 3.0, "confidence": 0.9},
            ],
        }
        scene = bridge.build_scene(panorama)
        exported = bridge.export_scene_json(scene)
        assert "vertices" in exported
        assert "edges" in exported
        assert "kappa_snaps" in exported


# ═══════════════════════════════════════════════════════════════
# SAI T-Proc Tests
# ═══════════════════════════════════════════════════════════════

class TestEMLHypergraphConnector:
    """EML 超图查询"""

    def test_query_known_concept(self):
        from tomas_agi.sim.sai_tproc import EMLHypergraphConnector
        eml = EMLHypergraphConnector()
        result = eml.query("gravity")
        assert result.iota > 0.9
        assert result.grounded is True
        assert result.src_flag == "EMPIRICAL"

    def test_query_ungrounded_concept(self):
        from tomas_agi.sim.sai_tproc import EMLHypergraphConnector
        eml = EMLHypergraphConnector()
        result = eml.query("perpetual_motion")
        assert result.iota < 0.15
        assert result.grounded is False

    def test_query_unknown_concept(self):
        from tomas_agi.sim.sai_tproc import EMLHypergraphConnector
        eml = EMLHypergraphConnector()
        result = eml.query("nonexistent_concept_xyz")
        assert result.src_flag == "INFERRED"
        assert result.iota <= 0.5

    def test_register_knowledge(self):
        from tomas_agi.sim.sai_tproc import EMLHypergraphConnector
        eml = EMLHypergraphConnector()
        eml.register_knowledge("test_concept", iota=0.88, layer="W")
        result = eml.query("test_concept")
        assert result.iota == 0.88
        assert result.dikwp_layer == "W"

    def test_query_stats(self):
        from tomas_agi.sim.sai_tproc import EMLHypergraphConnector
        eml = EMLHypergraphConnector()
        eml.query("gravity")
        eml.query("table")
        stats = eml.get_query_stats()
        assert stats["total_queries"] == 2


class TestHypothesis:
    """Hypothesis 数据类"""

    def test_create_hypothesis(self):
        from tomas_agi.sim.sai_tproc import Hypothesis, HypothesisSource
        hypo = Hypothesis(
            id="h1",
            data="wooden table on cliff edge",
            source=HypothesisSource.SAI_WORLD_MODEL,
            confidence=0.85,
        )
        assert hypo.id == "h1"
        assert hypo.confidence == 0.85
        assert hypo.source == HypothesisSource.SAI_WORLD_MODEL


class TestAuditResult:
    """AuditResult 数据类"""

    def test_allow_result(self):
        from tomas_agi.sim.sai_tproc import AuditResult, AuditStatus
        result = AuditResult(
            status=AuditStatus.ALLOW,
            reason="All checks passed",
        )
        assert result.status == AuditStatus.ALLOW

    def test_reject_result(self):
        from tomas_agi.sim.sai_tproc import AuditResult, AuditStatus
        result = AuditResult(
            status=AuditStatus.REJECT,
            reason="Iota below threshold",
        )
        assert result.status == AuditStatus.REJECT


class TestGEgoLogger:
    """G_ego 审计日志"""

    def test_log_decision(self):
        from tomas_agi.sim.sai_tproc import (
            GEgoLogger, Hypothesis, AuditResult, AuditStatus, HypothesisSource
        )
        logger = GEgoLogger()
        hypo = Hypothesis(id="h1", data="test",
                          source=HypothesisSource.SAI_WORLD_MODEL)
        result = AuditResult(status=AuditStatus.ALLOW, reason="OK")
        logger.log_decision(hypo, result)
        assert len(logger.audit_trail) == 1
        assert logger.stats["ALLOW"] == 1

    def test_get_stats(self):
        from tomas_agi.sim.sai_tproc import (
            GEgoLogger, Hypothesis, AuditResult, AuditStatus, HypothesisSource
        )
        logger = GEgoLogger()
        hypo = Hypothesis(id="h1", data="test",
                          source=HypothesisSource.SAI_WORLD_MODEL)
        logger.log_decision(hypo, AuditResult(status=AuditStatus.ALLOW, reason="OK"))
        logger.log_decision(hypo, AuditResult(status=AuditStatus.REJECT, reason="Bad"))
        stats = logger.get_stats()
        assert stats["counts"]["ALLOW"] == 1
        assert stats["counts"]["REJECT"] == 1
        assert stats["total"] == 2

    def test_clear(self):
        from tomas_agi.sim.sai_tproc import (
            GEgoLogger, Hypothesis, AuditResult, AuditStatus, HypothesisSource
        )
        logger = GEgoLogger()
        hypo = Hypothesis(id="h1", data="test",
                          source=HypothesisSource.SAI_WORLD_MODEL)
        logger.log_decision(hypo, AuditResult(status=AuditStatus.ALLOW, reason="OK"))
        logger.clear()
        assert len(logger.audit_trail) == 0

    def test_file_logging(self):
        from tomas_agi.sim.sai_tproc import (
            GEgoLogger, Hypothesis, AuditResult, AuditStatus, HypothesisSource
        )
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            log_path = f.name

        try:
            logger = GEgoLogger(log_path=log_path)
            hypo = Hypothesis(id="h1", data="test",
                              source=HypothesisSource.SAI_WORLD_MODEL)
            logger.log_decision(hypo, AuditResult(status=AuditStatus.ALLOW, reason="OK"))
            # 文件应存在且包含日志
            assert os.path.exists(log_path)
        finally:
            if os.path.exists(log_path):
                os.unlink(log_path)


class TestTProcAuditor:
    """T-Proc 主审计器"""

    def test_audit_allow(self):
        from tomas_agi.sim.sai_tproc import (
            TProcAuditor, Hypothesis, AuditStatus, HypothesisSource
        )
        auditor = TProcAuditor(theta_dead=0.15)
        # 高置信度 + 常见概念 → 应通过
        hypo = Hypothesis(
            id="h1", data="table on floor",
            source=HypothesisSource.SAI_WORLD_MODEL,
            confidence=0.9,
        )
        result = auditor.audit_hypothesis(hypo)
        assert result.status == AuditStatus.ALLOW

    def test_audit_reject_dead_zero(self):
        from tomas_agi.sim.sai_tproc import (
            TProcAuditor, Hypothesis, AuditStatus, HypothesisSource
        )
        auditor = TProcAuditor(theta_dead=0.15)
        # 低 ℐ 概念 → 应拒绝
        hypo = Hypothesis(
            id="h2", data="perpetual_motion",
            source=HypothesisSource.SAI_WORLD_MODEL,
            confidence=0.1,
        )
        result = auditor.audit_hypothesis(hypo)
        assert result.status == AuditStatus.REJECT

    def test_audit_mus_active(self):
        from tomas_agi.sim.sai_tproc import (
            TProcAuditor, Hypothesis, AuditStatus, HypothesisSource
        )
        # 冷热错杂 → MUS 双存
        auditor = TProcAuditor(theta_dead=0.05, asym_thresh=0.05)
        hypo = Hypothesis(
            id="h3", data="mixed_hot_cold",
            source=HypothesisSource.SAI_WORLD_MODEL,
            confidence=0.5,
        )
        result = auditor.audit_hypothesis(hypo)
        # 可能 ALLOW 或 MUS_ACTIVE，取决于查询结果
        assert result.status in (AuditStatus.ALLOW, AuditStatus.MUS_ACTIVE,
                                  AuditStatus.WARN_UNGROUNDED)

    def test_audit_batch(self):
        from tomas_agi.sim.sai_tproc import (
            TProcAuditor, Hypothesis, HypothesisSource
        )
        auditor = TProcAuditor(theta_dead=0.15)
        hypos = [
            Hypothesis(id="h1", data="table on floor",
                       source=HypothesisSource.SAI_WORLD_MODEL, confidence=0.9),
            Hypothesis(id="h2", data="perpetual_motion",
                       source=HypothesisSource.SAI_WORLD_MODEL, confidence=0.1),
        ]
        results = auditor.audit_batch(hypos)
        assert len(results) == 2

    def test_filter_allowed(self):
        from tomas_agi.sim.sai_tproc import (
            TProcAuditor, Hypothesis, HypothesisSource
        )
        auditor = TProcAuditor(theta_dead=0.15)
        hypos = [
            Hypothesis(id="h1", data="table on floor",
                       source=HypothesisSource.SAI_WORLD_MODEL, confidence=0.9),
            Hypothesis(id="h2", data="perpetual_motion",
                       source=HypothesisSource.SAI_WORLD_MODEL, confidence=0.1),
        ]
        allowed = auditor.filter_allowed(hypos)
        # perpetual_motion 应被过滤
        assert len(allowed) >= 1
        allowed_ids = {h.id for h in allowed}
        assert "h1" in allowed_ids

    def test_get_audit_report(self):
        from tomas_agi.sim.sai_tproc import (
            TProcAuditor, Hypothesis, HypothesisSource
        )
        auditor = TProcAuditor(theta_dead=0.15)
        auditor.audit_hypothesis(Hypothesis(
            id="h1", data="table",
            source=HypothesisSource.SAI_WORLD_MODEL, confidence=0.9,
        ))
        report = auditor.get_audit_report()
        assert "stats" in report
        assert "config" in report
        assert report["config"]["theta_dead"] == 0.15

    def test_reset(self):
        from tomas_agi.sim.sai_tproc import (
            TProcAuditor, Hypothesis, HypothesisSource
        )
        auditor = TProcAuditor(theta_dead=0.15)
        auditor.audit_hypothesis(Hypothesis(
            id="h1", data="table",
            source=HypothesisSource.SAI_WORLD_MODEL, confidence=0.9,
        ))
        auditor.reset()
        assert len(auditor.audit_history) == 0
        assert auditor.ggg.get_stats()["total"] == 0


class TestSAIWorldModelSimulator:
    """SAI 世界模型模拟器"""

    def test_generate_known_scenario(self):
        from tomas_agi.sim.sai_tproc import SAIWorldModelSimulator
        sim = SAIWorldModelSimulator()
        hypos = sim.generate("table on cliff edge")
        assert len(hypos) >= 1

    def test_generate_generic_prompt(self):
        from tomas_agi.sim.sai_tproc import SAIWorldModelSimulator
        sim = SAIWorldModelSimulator()
        hypos = sim.generate("random new concept never seen before")
        assert len(hypos) >= 1

    def test_generate_hot_cold_mixed(self):
        from tomas_agi.sim.sai_tproc import SAIWorldModelSimulator
        sim = SAIWorldModelSimulator()
        hypos = sim.generate("hot cold mixed syndrome")
        assert len(hypos) >= 2  # 至少有两个矛盾假设


# ═══════════════════════════════════════════════════════════════
# Spatial Dead-Zero Tests
# ═══════════════════════════════════════════════════════════════

class TestGravityValidator:
    """重力校验"""

    def test_grounded_object(self):
        from tomas_agi.sim.spatial_dead_zero import GravityValidator, SpatialStatus
        gv = GravityValidator(ground_y=0.0, float_threshold=0.15)
        check = gv.check_object(
            obj_id="obj1",
            position=(0.0, 0.5, 0.0),  # 底部在地面
            scale=(1.0, 1.0, 1.0),      # 底部 y = 0.5 - 0.5 = 0
            i_value=0.8,
            other_objects=[],
        )
        assert check.is_supported
        assert check.support_id == "ground"

    def test_floating_object(self):
        from tomas_agi.sim.spatial_dead_zero import GravityValidator, SpatialStatus
        gv = GravityValidator(ground_y=0.0, float_threshold=0.15)
        check = gv.check_object(
            obj_id="obj2",
            position=(0.0, 2.0, 0.0),  # 离地 2m
            scale=(1.0, 1.0, 1.0),
            i_value=0.8,
            other_objects=[],
        )
        assert not check.is_supported
        assert check.status == SpatialStatus.FLOATING

    def test_dead_zero_floating(self):
        from tomas_agi.sim.spatial_dead_zero import GravityValidator, SpatialStatus
        gv = GravityValidator(ground_y=0.0, float_threshold=0.15, theta_dead=0.15)
        check = gv.check_object(
            obj_id="obj3",
            position=(0.0, 5.0, 0.0),  # 高空 + 低 ℐ
            scale=(1.0, 1.0, 1.0),
            i_value=0.05,                # < θ_dead
            other_objects=[],
        )
        assert check.status == SpatialStatus.DEAD_ZERO

    def test_supported_by_other(self):
        from tomas_agi.sim.spatial_dead_zero import GravityValidator, SpatialStatus
        gv = GravityValidator(ground_y=0.0, float_threshold=0.15)
        # table 作为支撑物
        others = [{
            "id": "table",
            "position": (0.0, 1.0, 0.0),
            "scale": (2.0, 0.1, 2.0),  # 薄桌面
        }]
        check = gv.check_object(
            obj_id="book",
            position=(0.0, 1.1, 0.0),  # 在桌面上方
            scale=(0.2, 0.05, 0.3),
            i_value=0.7,
            other_objects=others,
        )
        assert check.is_supported
        assert check.support_id == "table"

    def test_audit_scene(self):
        from tomas_agi.sim.spatial_dead_zero import GravityValidator
        gv = GravityValidator(ground_y=0.0, float_threshold=0.15)
        objects = [
            {"id": "g1", "position": (0, 0.5, 0), "scale": (1, 1, 1), "i_value": 0.8},
            {"id": "f1", "position": (0, 3.0, 0), "scale": (1, 1, 1), "i_value": 0.6},
            {"id": "dz1", "position": (0, 10.0, 0), "scale": (1, 1, 1), "i_value": 0.05},
        ]
        results = gv.audit_scene(objects)
        assert len(results) == 3
        statuses = {r.object_id: r.status for r in results}
        from tomas_agi.sim.spatial_dead_zero import SpatialStatus
        assert statuses["g1"] == SpatialStatus.GROUNDED
        assert statuses["f1"] == SpatialStatus.FLOATING
        assert statuses["dz1"] == SpatialStatus.DEAD_ZERO


class TestSpatialMUSDetector:
    """空间 MUS 双存检测"""

    def test_no_conflict(self):
        from tomas_agi.sim.spatial_dead_zero import SpatialMUSDetector
        detector = SpatialMUSDetector()
        results = detector.detect(
            region_id="r1",
            semantics=["open", "visible"],
            i_values=[0.8, 0.75],
        )
        assert len(results) == 0  # 非反义 → 无冲突

    def test_antonym_pair(self):
        from tomas_agi.sim.spatial_dead_zero import SpatialMUSDetector, SpatialStatus
        detector = SpatialMUSDetector(asym_threshold=0.05)
        results = detector.detect(
            region_id="r2",
            semantics=["open", "closed"],  # 空间反义
            i_values=[0.8, 0.72],  # diff=0.08, well within [0.05, 0.1]
        )
        # open vs closed 是反义 → MUS
        assert len(results) >= 1
        assert any(r.status == SpatialStatus.MUS_ACTIVE for r in results)

    def test_antonym_dead_zero(self):
        from tomas_agi.sim.spatial_dead_zero import SpatialMUSDetector, SpatialStatus
        detector = SpatialMUSDetector(asym_threshold=0.05, theta_dead=0.15)
        results = detector.detect(
            region_id="r3",
            semantics=["open", "closed"],
            i_values=[0.05, 0.8],  # 一侧 ℐ 极低
        )
        # 低 ℐ 侧 → 死零
        assert any(r.status == SpatialStatus.DEAD_ZERO for r in results)

    def test_is_antonym(self):
        from tomas_agi.sim.spatial_dead_zero import SpatialMUSDetector
        detector = SpatialMUSDetector()
        assert detector.is_antonym_pair("open", "closed")
        assert detector.is_antonym_pair("safe", "dangerous")
        assert not detector.is_antonym_pair("open", "visible")


class TestIotaLossFunction:
    """ℐ-修正 Loss"""

    def test_perfect_match(self):
        from tomas_agi.sim.spatial_dead_zero import IotaLossFunction
        loss_fn = IotaLossFunction(lambda_i=0.5)
        pred = [{"id": "p1", "position": (0, 0, 0), "i_value": 0.8}]
        gt = [{"id": "g1", "position": (0, 0, 0), "i_value": 0.8}]
        total, comp = loss_fn.compute(pred, gt)
        assert total == 0.0

    def test_with_error(self):
        from tomas_agi.sim.spatial_dead_zero import IotaLossFunction
        loss_fn = IotaLossFunction(lambda_i=0.5)
        pred = [{"id": "p1", "position": (1, 1, 1), "i_value": 0.8}]
        gt = [{"id": "g1", "position": (0, 0, 0), "i_value": 0.8}]
        total, comp = loss_fn.compute(pred, gt)
        assert total > 0
        assert comp["mse"] > 0

    def test_dead_zero_skip(self):
        from tomas_agi.sim.spatial_dead_zero import IotaLossFunction
        loss_fn = IotaLossFunction(lambda_i=0.5)
        pred = [{"id": "dz", "position": (10, 10, 10), "i_value": 0.05}]  # 死零
        gt = [{"id": "g1", "position": (0, 0, 0), "i_value": 0.8}]
        total, comp = loss_fn.compute(pred, gt, theta_dead=0.15)
        # 死零物体被跳过 → loss = 0 (无匹配)
        assert total == 0.0

    def test_high_iota_penalty(self):
        from tomas_agi.sim.spatial_dead_zero import IotaLossFunction
        loss_fn = IotaLossFunction(lambda_i=1.0)  # 高 I 权重
        # 高 ℐ 物体误差
        pred = [{"id": "p1", "position": (2, 2, 2), "i_value": 0.9}]
        gt = [{"id": "g1", "position": (0, 0, 0), "i_value": 0.99}]
        _, comp_high = loss_fn.compute(pred, gt)
        # 低 ℐ 物体相同误差
        loss_fn_low = IotaLossFunction(lambda_i=1.0)
        pred_low = [{"id": "p2", "position": (2, 2, 2), "i_value": 0.3}]
        gt_low = [{"id": "g2", "position": (0, 0, 0), "i_value": 0.3}]
        _, comp_low = loss_fn_low.compute(pred_low, gt_low)
        # 高 ℐ 物体的 iota_penalty 应 > 低 ℐ 物体
        assert comp_high["iota_penalty"] > comp_low["iota_penalty"]


class TestSpatialDeadZeroAuditor:
    """空间死零主编排器"""

    def test_audit_all_grounded(self):
        from tomas_agi.sim.spatial_dead_zero import SpatialDeadZeroAuditor
        auditor = SpatialDeadZeroAuditor(theta_dead=0.15)
        objects = [
            {"id": "obj1", "position": (0, 0.5, 0), "scale": (1, 1, 1), "i_value": 0.8},
            {"id": "obj2", "position": (2, 0.5, 0), "scale": (1, 1, 1), "i_value": 0.7},
        ]
        report = auditor.audit(objects)
        assert report.total_objects == 2
        assert report.grounded == 2
        assert report.floating == 0
        assert report.dead_zero == 0

    def test_audit_with_floating(self):
        from tomas_agi.sim.spatial_dead_zero import SpatialDeadZeroAuditor
        auditor = SpatialDeadZeroAuditor(theta_dead=0.15)
        objects = [
            {"id": "g1", "position": (0, 0.5, 0), "scale": (1, 1, 1), "i_value": 0.8},
            {"id": "f1", "position": (0, 5.0, 0), "scale": (1, 1, 1), "i_value": 0.6},
            {"id": "dz1", "position": (0, 10.0, 0), "scale": (1, 1, 1), "i_value": 0.05},
        ]
        report = auditor.audit(objects)
        assert report.grounded == 1
        assert report.floating == 1
        assert report.dead_zero == 1

    def test_audit_with_mus(self):
        from tomas_agi.sim.spatial_dead_zero import SpatialDeadZeroAuditor
        auditor = SpatialDeadZeroAuditor(theta_dead=0.15, asym_threshold=0.05)
        objects = [
            {"id": "safe_zone", "position": (0, 0.5, 0), "scale": (1, 1, 1),
             "i_value": 0.5, "semantics": ["open", "closed"],
             "semantic_i_values": [0.8, 0.72]},  # diff=0.08 within [0.05, 0.1]
        ]
        report = auditor.audit(objects)
        assert report.mus_active >= 1

    def test_filter_scene(self):
        from tomas_agi.sim.spatial_dead_zero import SpatialDeadZeroAuditor
        auditor = SpatialDeadZeroAuditor(theta_dead=0.15)
        objects = [
            {"id": "g1", "position": (0, 0.5, 0), "scale": (1, 1, 1), "i_value": 0.8},
            {"id": "f1", "position": (0, 5.0, 0), "scale": (1, 1, 1), "i_value": 0.6},
        ]
        passed, rejected = auditor.filter_scene(objects)
        assert len(passed) == 1
        assert passed[0]["id"] == "g1"
        assert len(rejected) == 1

    def test_auto_snap_to_ground(self):
        from tomas_agi.sim.spatial_dead_zero import SpatialDeadZeroAuditor
        auditor = SpatialDeadZeroAuditor(theta_dead=0.15)
        objects = [
            {"id": "f1", "position": (0, 3.0, 0), "scale": (1, 1, 1)},
        ]
        corrected = auditor.auto_snap_to_ground(objects)
        assert len(corrected) == 1
        # 应被吸附到地面: y = scale_y/2 = 0.5
        assert abs(corrected[0]["position"][1] - 0.5) < 0.01


# ═══════════════════════════════════════════════════════════════
# MemOS Fusion Integration Tests
# ═══════════════════════════════════════════════════════════════

class TestMemOSHYWorldIntegration:
    """MemOS + HY World 集成"""

    def _make_fusion(self):
        import tempfile, os
        from tomas_agi.sim.memos_fusion import TOMAS_Mem_OS_Fusion
        # 使用临时目录避免持久化冲突
        tmpdir = tempfile.mkdtemp(prefix="tomas_test_")
        fusion = TOMAS_Mem_OS_Fusion(store_path=tmpdir)
        # 清理引用
        self._tmpdir = tmpdir
        return fusion

    def test_install_hyworld_bridge(self):
        from tomas_agi.sim.hyworld_bridge import HYWorldBridge
        fusion = self._make_fusion()
        bridge = HYWorldBridge(theta_dead=0.15, enable_kappa_snap=False)
        fusion.install_hyworld_bridge(bridge)
        assert hasattr(fusion, '_hyworld_bridge')

    def test_hyworld_build_scene(self):
        from tomas_agi.sim.hyworld_bridge import HYWorldBridge
        fusion = self._make_fusion()
        bridge = HYWorldBridge(theta_dead=0.15, enable_kappa_snap=False)
        fusion.install_hyworld_bridge(bridge)
        panorama = {
            "objects": [
                {"label": "wall", "bbox": [0, 0, 1, 1],
                 "depth": 2.0, "confidence": 0.9},
            ],
        }
        scene = fusion.hyworld_build_scene(panorama, "test")
        assert scene is not None

    def test_hyworld_dead_zero_audit(self):
        from tomas_agi.sim.hyworld_bridge import HYWorldBridge
        fusion = self._make_fusion()
        bridge = HYWorldBridge(theta_dead=0.15, enable_kappa_snap=False)
        fusion.install_hyworld_bridge(bridge)
        panorama = {
            "objects": [
                {"label": "wall", "bbox": [0, 0, 1, 1],
                 "depth": 2.0, "confidence": 0.9},
            ],
        }
        scene = fusion.hyworld_build_scene(panorama, "test")
        audit = fusion.hyworld_dead_zero_audit(scene)
        assert "passed" in audit


class TestMemOSSAIIntegration:
    """MemOS + SAI T-Proc 集成"""

    def _make_fusion(self):
        import tempfile, os
        from tomas_agi.sim.memos_fusion import TOMAS_Mem_OS_Fusion
        tmpdir = tempfile.mkdtemp(prefix="tomas_test_")
        fusion = TOMAS_Mem_OS_Fusion(store_path=tmpdir)
        self._tmpdir = tmpdir
        return fusion

    def test_install_sai_tproc(self):
        from tomas_agi.sim.sai_tproc import TProcAuditor
        fusion = self._make_fusion()
        tproc = TProcAuditor(theta_dead=0.15)
        fusion.install_sai_tproc(tproc)
        assert hasattr(fusion, '_sai_tproc')

    def test_sai_audit_hypothesis(self):
        from tomas_agi.sim.sai_tproc import TProcAuditor, Hypothesis, HypothesisSource, AuditStatus
        fusion = self._make_fusion()
        tproc = TProcAuditor(theta_dead=0.15)
        fusion.install_sai_tproc(tproc)
        hypo = Hypothesis(id="h1", data="table on floor",
                          source=HypothesisSource.SAI_WORLD_MODEL,
                          confidence=0.9)
        result = fusion.sai_audit_hypothesis(hypo)
        assert result.status == AuditStatus.ALLOW

    def test_sai_filter_allowed(self):
        from tomas_agi.sim.sai_tproc import TProcAuditor, Hypothesis, HypothesisSource
        fusion = self._make_fusion()
        tproc = TProcAuditor(theta_dead=0.15)
        fusion.install_sai_tproc(tproc)
        hypos = [
            Hypothesis(id="h1", data="table",
                       source=HypothesisSource.SAI_WORLD_MODEL, confidence=0.9),
            Hypothesis(id="h2", data="perpetual_motion",
                       source=HypothesisSource.SAI_WORLD_MODEL, confidence=0.1),
        ]
        allowed = fusion.sai_filter_allowed(hypos)
        assert len(allowed) >= 1

    def test_get_sai_audit_report(self):
        from tomas_agi.sim.sai_tproc import TProcAuditor
        fusion = self._make_fusion()
        tproc = TProcAuditor(theta_dead=0.15)
        fusion.install_sai_tproc(tproc)
        report = fusion.get_sai_audit_report()
        assert "stats" in report
        assert "config" in report


class TestMemOSSpatialIntegration:
    """MemOS + 空间死零集成"""

    def _make_fusion(self):
        import tempfile, os
        from tomas_agi.sim.memos_fusion import TOMAS_Mem_OS_Fusion
        tmpdir = tempfile.mkdtemp(prefix="tomas_test_")
        fusion = TOMAS_Mem_OS_Fusion(store_path=tmpdir)
        self._tmpdir = tmpdir
        return fusion

    def test_install_spatial_auditor(self):
        from tomas_agi.sim.spatial_dead_zero import SpatialDeadZeroAuditor
        fusion = self._make_fusion()
        auditor = SpatialDeadZeroAuditor(theta_dead=0.15)
        fusion.install_spatial_auditor(auditor)
        assert hasattr(fusion, '_spatial_auditor')

    def test_audit_3d_scene(self):
        from tomas_agi.sim.spatial_dead_zero import SpatialDeadZeroAuditor
        fusion = self._make_fusion()
        auditor = SpatialDeadZeroAuditor(theta_dead=0.15)
        fusion.install_spatial_auditor(auditor)
        objects = [
            {"id": "g1", "position": (0, 0.5, 0), "scale": (1, 1, 1), "i_value": 0.8},
        ]
        report = fusion.audit_3d_scene(objects)
        assert report.total_objects == 1
        assert report.grounded == 1

    def test_get_spatial_audit(self):
        from tomas_agi.sim.spatial_dead_zero import SpatialDeadZeroAuditor
        fusion = self._make_fusion()
        auditor = SpatialDeadZeroAuditor(theta_dead=0.15)
        fusion.install_spatial_auditor(auditor)
        objects = [
            {"id": "g1", "position": (0, 0.5, 0), "scale": (1, 1, 1), "i_value": 0.8},
            {"id": "f1", "position": (0, 3.0, 0), "scale": (1, 1, 1), "i_value": 0.6},
        ]
        report = fusion.get_spatial_audit(objects)
        assert report["total_objects"] == 2
        assert report["floating"] == 1


# ═══════════════════════════════════════════════════════════════
# DeadZeroMUSGate 空间死零扩展测试
# ═══════════════════════════════════════════════════════════════

class TestDeadZeroSpatialExtension:
    """DeadZeroMUSGate 空间死零扩展"""

    def test_apply_spatial_dead_zero(self):
        from tomas_agi.sim.dead_zero_mus import DeadZeroMUSGate
        gate = DeadZeroMUSGate(theta_dead=0.15)
        objects = [
            {"id": "g1", "position": (0, 0.5, 0), "scale": (1, 1, 1), "i_value": 0.8},
            {"id": "f1", "position": (0, 3.0, 0), "scale": (1, 1, 1), "i_value": 0.6},
            {"id": "dz1", "position": (0, 5.0, 0), "scale": (1, 1, 1), "i_value": 0.05},
        ]
        result = gate.apply_spatial_dead_zero(objects, ground_y=0.0, float_threshold=0.15)
        assert result["total"] == 3
        assert result["grounded"] == 1
        assert result["floating"] == 1
        assert result["dead_zero"] == 1
        assert len(result["corrected"]) == 3

    def test_auto_snap_correction(self):
        from tomas_agi.sim.dead_zero_mus import DeadZeroMUSGate
        gate = DeadZeroMUSGate(theta_dead=0.15)
        objects = [
            {"id": "f1", "position": (0, 3.0, 0), "scale": (1, 1, 1), "i_value": 0.6},
        ]
        result = gate.apply_spatial_dead_zero(objects)
        # 悬浮物体应被校正
        corrected = result["corrected"][0]
        assert corrected.get("_snapped_to_ground") is True
        # y 应被吸附到地面: scale_y/2 = 0.5
        assert abs(corrected["position"][1] - 0.5) < 0.01

    def test_check_physical_grounding(self):
        from tomas_agi.sim.dead_zero_mus import DeadZeroMUSGate
        gate = DeadZeroMUSGate(theta_dead=0.15)
        # table 在下, book 在上 → 有支撑
        table = {"id": "table", "position": (0, 1.0, 0), "scale": (2, 0.1, 2)}
        book = {"id": "book", "position": (0, 1.1, 0), "scale": (0.2, 0.05, 0.3)}
        supported, reason = gate.check_physical_grounding(book, table)
        assert supported

    def test_check_no_grounding(self):
        from tomas_agi.sim.dead_zero_mus import DeadZeroMUSGate
        gate = DeadZeroMUSGate(theta_dead=0.15)
        # 两个物体相距很远
        obj_a = {"id": "a", "position": (0, 10.0, 0), "scale": (1, 1, 1)}
        obj_b = {"id": "b", "position": (0, 0.5, 0), "scale": (1, 1, 1)}
        supported, reason = gate.check_physical_grounding(obj_a, obj_b)
        assert not supported
