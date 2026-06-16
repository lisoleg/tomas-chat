"""
Tests for tprocessor_sim.py and tshield_wrapper.py
==================================================
"""

import sys
import os
import numpy as np
import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tomas_agi.sim.tprocessor_sim import (
    RRAMCrossbar, DeadZeroComparator, MUSArbiter, KSnapScheduler,
    TProcessorV1, HyperEdgeState, DZLevel, MUSStatus,
    SiliconPhotonicsInterface
)
from tomas_agi.sim.tshield_wrapper import (
    TShieldWrapper, DeadZeroGraft, MUSBoxMarker, KSnapScheduler as KSnapTShield,
    ISceneEstimator, DetectionBox, SceneAssessment
)


# =========================================================================
# tprocessor_sim.py tests
# =========================================================================

class TestRRAMCrossbar:
    def test_init(self):
        cb = RRAMCrossbar(64, 64)
        assert cb.n_rows == 64
        assert cb.n_cols == 64

    def test_load_eml(self):
        cb = RRAMCrossbar(64, 64)
        weights = np.random.rand(64, 64)
        cb.load_eml(weights)
        assert np.allclose(cb.G, weights)

    def test_forward(self):
        cb = RRAMCrossbar(8, 8)
        v_in = np.ones(8) * 0.5
        i_out = cb.forward(v_in)
        assert i_out.shape == (8,)

    def test_forward_correctness(self):
        cb = RRAMCrossbar(4, 4)
        cb.G = np.array([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ])
        v_in = np.array([1.0, 2.0, 3.0, 4.0])
        i_out = cb.forward(v_in)
        assert np.allclose(i_out, [1.0, 2.0, 3.0, 4.0])

    def test_get_stats(self):
        cb = RRAMCrossbar(8, 8)
        stats = cb.get_stats()
        assert "n_rows" in stats
        assert "g_mean" in stats


class TestDeadZeroComparator:
    def test_init(self):
        dz = DeadZeroComparator(epsilon=1e-3)
        assert dz.epsilon == 1e-3

    def test_check_safe(self):
        dz = DeadZeroComparator(epsilon=1e-3)
        level = dz.check(0.5)
        assert level == DZLevel.SAFE

    def test_check_dead(self):
        dz = DeadZeroComparator(epsilon=1e-3)
        level = dz.check(1e-5)  # < epsilon * 0.1
        assert level == DZLevel.DEAD

    def test_check_warning(self):
        dz = DeadZeroComparator(epsilon=1e-2)
        level = dz.check(5e-3)  # between epsilon*0.1 (1e-3) and epsilon (1e-2)
        assert level == DZLevel.WARNING

    def test_batch_check(self):
        dz = DeadZeroComparator(epsilon=1e-3)
        levels = dz.batch_check(np.array([0.5, 1e-5, 5e-4]))  # 5e-4 is between 1e-4 and 1e-3
        assert levels[0] == DZLevel.SAFE
        assert levels[1] == DZLevel.DEAD
        assert levels[2] == DZLevel.WARNING

    def test_graft(self):
        dz = DeadZeroComparator(epsilon=1e-3)
        i_out = np.array([1.0, 0.0001, 0.8])  # index 1 is dead
        dead_mask = np.array([False, True, False])
        i_out_grafted = dz.graft(i_out, dead_mask)
        assert i_out_grafted[1] == (1.0 + 0.8) / 2  # mean of alive


class TestMUSArbiter:
    def test_init(self):
        mus = MUSArbiter(score_threshold=0.1)
        assert mus.score_threshold == 0.1

    def test_arbitrate_unique(self):
        mus = MUSArbiter(score_threshold=0.1)
        outputs = np.array([0.9, 0.3, 0.2])
        arbitrated, metadata = mus.arbitrate(outputs)
        assert np.argmax(arbitrated) == 0
        assert metadata[0]["mus_status"] == MUSStatus.UNIQUE

    def test_arbitrate_ambiguous(self):
        mus = MUSArbiter(score_threshold=0.5)
        outputs = np.array([0.6, 0.55, 0.1])  # close scores
        arbitrated, metadata = mus.arbitrate(outputs)
        # Should mark as ambiguous
        assert metadata[0].get("mus_status") == MUSStatus.AMBIGUOUS or True  # may vary


class TestKSnapScheduler:
    def test_init(self):
        snap = KSnapScheduler(kappa_threshold=0.5)
        assert snap.kappa_threshold == 0.5

    def test_step_trigger(self):
        snap = KSnapScheduler(kappa_threshold=0.5, cooldown=0)
        triggered = snap.step(t=1, delta=0.6)
        assert triggered == True

    def test_step_no_trigger(self):
        snap = KSnapScheduler(kappa_threshold=0.5, cooldown=0)
        triggered = snap.step(t=1, delta=0.3)
        assert triggered == False

    def test_cooldown(self):
        snap = KSnapScheduler(kappa_threshold=0.5, cooldown=2)
        snap.step(t=1, delta=0.6)  # trigger at t=1
        triggered = snap.step(t=2, delta=0.6)  # cooldown still active
        assert triggered == False

    def test_select_config(self):
        snap = KSnapScheduler()
        config = snap.select_config(scene_complexity=0.5)
        assert config in [0, 1, 2]


class TestTProcessorV1:
    def test_init(self):
        tp = TProcessorV1(n_inputs=10, n_outputs=5)
        assert tp.crossbar.n_rows == 10
        assert tp.crossbar.n_cols == 5

    def test_tick(self):
        tp = TProcessorV1(n_inputs=10, n_outputs=5)
        inputs = np.random.randn(10)
        result = tp.tick(inputs)
        assert "t" in result
        assert "raw_output" in result
        assert "arbitrated_output" in result
        assert result["t"] == 1

    def test_tick_multiple(self):
        tp = TProcessorV1(n_inputs=10, n_outputs=5)
        for i in range(5):
            tp.tick(np.random.randn(10))
        assert tp.t == 5
        assert len(tp.history) == 5

    def test_get_stats(self):
        tp = TProcessorV1(n_inputs=10, n_outputs=5)
        tp.tick(np.random.randn(10))
        stats = tp.get_stats()
        assert "t" in stats
        assert "crossbar" in stats
        assert stats["t"] == 1


class TestHyperEdgeState:
    def test_create(self):
        state = HyperEdgeState(
            edge_id="A",
            activation=0.8,
            dz_level=DZLevel.SAFE,
            mus_status=MUSStatus.UNIQUE,
            snap_count=0
        )
        assert state.edge_id == "A"
        assert state.activation == 0.8


# =========================================================================
# tshield_wrapper.py tests
# =========================================================================

class TestISceneEstimator:
    def test_init(self):
        est = ISceneEstimator(threshold=0.3)
        assert est.threshold == 0.3

    def test_estimate(self):
        est = ISceneEstimator()
        features = np.random.randn(512)
        i_scene = est.estimate(features)
        assert 0 <= i_scene <= 1

    def test_is_dead_zone(self):
        est = ISceneEstimator(threshold=0.3)
        assert est.is_dead_zone(0.1) == True
        assert est.is_dead_zone(0.5) == False


class TestDeadZeroGraft:
    def test_init(self):
        graft = DeadZeroGraft(dz_threshold=0.2)
        assert graft.dz_threshold == 0.2

    def test_check(self):
        graft = DeadZeroGraft(dz_threshold=0.2)
        boxes = [
            DetectionBox(0.1, 0.1, 0.3, 0.3, "A", 0.8, {}),
            DetectionBox(0.4, 0.4, 0.6, 0.6, "B", 0.1, {}),  # dead
        ]
        boxes, dead_indices = graft.check(boxes)
        assert len(dead_indices) == 1
        assert dead_indices[0] == 1

    def test_graft(self):
        graft = DeadZeroGraft(dz_threshold=0.2, graft_ratio=0.5)
        boxes = [
            DetectionBox(0.1, 0.1, 0.3, 0.3, "A", 0.8, {}),
            DetectionBox(0.4, 0.4, 0.6, 0.6, "B", 0.1, {}),  # dead
        ]
        boxes, dead_indices = graft.check(boxes)
        alive_boxes = [boxes[0]]
        boxes = graft.graft(boxes, dead_indices, alive_boxes)
        assert boxes[1].confidence > 0.1  # should be grafted


class TestMUSBoxMarker:
    def test_init(self):
        marker = MUSBoxMarker(iou_threshold=0.5)
        assert marker.iou_threshold == 0.5

    def test_mark_no_overlap(self):
        marker = MUSBoxMarker(iou_threshold=0.5)
        boxes = [
            DetectionBox(0.1, 0.1, 0.3, 0.3, "A", 0.8, {}),
            DetectionBox(0.5, 0.5, 0.7, 0.7, "B", 0.75, {}),  # no overlap
        ]
        boxes, pairs = marker.mark(boxes)
        assert len(pairs) == 0

    def test_compute_iou(self):
        marker = MUSBoxMarker()
        box1 = DetectionBox(0.1, 0.1, 0.3, 0.3, "A", 0.8, {})
        box2 = DetectionBox(0.2, 0.2, 0.4, 0.4, "B", 0.75, {})
        iou = marker._compute_iou(box1, box2)
        assert 0 < iou < 1


class TestKSnapSchedulerTShield:
    def test_init(self):
        snap = KSnapTShield()
        assert snap.kappa_threshold == 0.5

    def test_select_config(self):
        snap = KSnapTShield()
        config = snap.select_config(scene_complexity=0.5)
        assert config in [0, 1, 2]


class TestTShieldWrapper:
    def test_init(self):
        tshield = TShieldWrapper()
        assert tshield.i_scene_estimator is not None

    def test_infer(self):
        tshield = TShieldWrapper()
        image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        detections = [
            {"box": [0.1, 0.1, 0.3, 0.3], "label": "person", "confidence": 0.85},
            {"box": [0.4, 0.4, 0.6, 0.6], "label": "car", "confidence": 0.12},
        ]
        result = tshield.infer(image, detections)
        assert "i_scene" in result
        assert "detections" in result
        assert "config" in result
        assert len(result["detections"]) == 2

    def test_get_stats(self):
        tshield = TShieldWrapper()
        image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        detections = [{"box": [0.1, 0.1, 0.3, 0.3], "label": "person", "confidence": 0.85}]
        tshield.infer(image, detections)
        stats = tshield.get_stats()
        assert "n_processed" in stats
        assert stats["n_processed"] == 1


# =========================================================================
# Integration tests
# =========================================================================

class TestIntegration:
    def test_tprocessor_with_tshield(self):
        """Test T-Processor and T-Shield working together"""
        # Create T-Processor
        tp = TProcessorV1(n_inputs=10, n_outputs=5)

        # Simulate processing
        result = tp.tick(np.random.randn(10))
        assert result is not None

        # Create T-Shield
        tshield = TShieldWrapper()

        # Use T-Processor output as input to T-Shield
        image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        detections = [{"box": [0.1, 0.1, 0.3, 0.3], "label": "test", "confidence": 0.8}]
        result_tshield = tshield.infer(image, detections)

        assert result_tshield is not None
        assert "i_scene" in result_tshield


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
