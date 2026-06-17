"""
测试新升级的 TOMAS 模块
==================

测试从文章和竞光AGI升级的模块：
1. g_ego.py — G_ego 双向算子
2. epiplexity_engine.py — 认知复杂度引擎
3. eml_semzip.py — EML语义压缩

作者: TOMAS 团队
日期: 2026-06-17
"""

import sys
import os
import pytest

# 确保 sim/ 在 Python 路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'sim'))


class TestGEgoEngine:
    """测试 G_egoEngine"""

    def setup_method(self):
        """设置测试固件"""
        from g_ego import G_egoEngine, G_egoState, DMNMapping, G_egoStatus

        self.engine = G_egoEngine.get_instance(i_threshold=0.3)
        self.engine.reset_state()

    def test_mode_switching(self):
        """测试模式切换"""
        # 设置ℐ值高于阈值
        self.engine._status.i_value = 0.8

        r = self.engine.switch_mode("afferent")
        assert r["success"]
        assert r["new_mode"] == "afferent"

        r = self.engine.switch_mode("efferent")
        assert r["success"]
        assert r["new_mode"] == "efferent"

        r = self.engine.switch_mode("idle")
        assert r["success"]
        assert r["new_mode"] == "idle"

    def test_afferent_mapping(self):
        """测试 Afferent DMN 映射"""
        self.engine._status.i_value = 0.8
        self.engine.switch_mode("afferent")

        perceptual_input = {"features": [0.1, 0.5, 0.3, 0.8, 0.2]}
        mapping = self.engine.afferent_mapping(perceptual_input)

        assert mapping.mapping_type == "afferent"
        assert 0.0 <= mapping.info_loss <= 1.0
        assert 0.0 <= mapping.consistency <= 1.0

    def test_efferent_mapping(self):
        """测试 Efferent DMN 映射"""
        self.engine._status.i_value = 0.8
        self.engine.switch_mode("efferent")

        semantic_query = {"concept": "G_ego", "type": "theory"}
        mapping = self.engine.efferent_mapping(semantic_query)

        assert mapping.mapping_type == "efferent"
        assert 0.0 <= mapping.info_loss <= 1.0

    def test_t_shield_monitor(self):
        """测试 T-Shield 监控"""
        # 模拟异常：频繁切换
        self.engine._status.i_value = 0.8
        self.engine.switch_mode("afferent")
        self.engine.afferent_mapping({"features": [1, 2, 3]})
        self.engine.switch_mode("efferent")
        self.engine.efferent_mapping({"concept": "test"})
        self.engine.switch_mode("afferent")
        self.engine.afferent_mapping({"features": [4, 5, 6]})

        result = self.engine.t_shield_monitor(n_recent_steps=3)
        # 可能不会触发重置（取决于实现）
        assert "status" in result
        assert "reset_triggered" in result

    def test_get_status(self):
        """测试获取状态"""
        status = self.engine.get_status()
        assert "mode" in status
        assert "is_active" in status
        assert "i_value" in status

    def test_singleton(self):
        """测试单例模式"""
        from g_ego import G_egoEngine

        inst1 = G_egoEngine.get_instance()
        inst2 = G_egoEngine.get_instance()
        assert inst1 is inst2


class TestEpiplexityEngine:
    """测试 EpiplexityEngine"""

    def setup_method(self):
        """设置测试固件"""
        from epiplexity_engine import EpiplexityEngine, SemanticDistribution

        self.engine = EpiplexityEngine.get_instance()
        self.engine.reset_state()

        # 创建测试分布
        self.dist = SemanticDistribution(
            probs=[0.2, 0.3, 0.15, 0.25, 0.1],
            concepts=["quantum", "classical", "tomas", "mus", "gr"],
            features=[[0.1 * i, 0.2 * i, 0.3 * i, 0.4 * i, 0.5 * i, 0.6 * i, 0.7 * i, 0.8 * i]
                      for i in range(5)],
        )

    def test_entropy(self):
        """测试信息熵 H(p)"""
        H = self.engine.compute_entropy(self.dist)
        assert H >= 0.0

    def test_semantic_distance(self):
        """测试语义距离 D(p)"""
        D = self.engine.compute_semantic_distance(self.dist)
        assert D >= 0.0

    def test_complexity(self):
        """测试组合复杂度 C(p)"""
        C = self.engine.compute_complexity(self.dist)
        assert C >= 0.0

    def test_epiplexity_score(self):
        """测试 Epiplexity 总分"""
        result = self.engine.epiplexity_score(self.dist)
        assert result.epiplexity >= 0.0
        assert abs(result.epiplexity - (result.entropy + result.distance + result.complexity)) < 1e-10

    def test_information_bottleneck(self):
        """测试信息瓶颈优化"""
        result = self.engine.information_bottleneck(self.dist, target_compression_rate=0.8)
        assert result.compression_rate >= 0.80
        assert 0.0 <= result.information_loss <= 1.0

    def test_get_state(self):
        """测试获取状态"""
        state = self.engine.get_state()
        assert state["engine"] == "EpiplexityEngine"
        assert "total_entropy_calls" in state

    def test_singleton(self):
        """测试单例模式"""
        from epiplexity_engine import EpiplexityEngine

        inst1 = EpiplexityEngine.get_instance()
        inst2 = EpiplexityEngine.get_instance()
        assert inst1 is inst2


class TestEMLSemZipEngine:
    """测试 EMLSemZipEngine"""

    def setup_method(self):
        """设置测试固件"""
        from eml_semzip import EMLSemZipEngine

        self.engine = EMLSemZipEngine.get_instance(i_threshold=0.3)
        self.engine.reset_state()

        # 创建测试 EML 图
        self.n_vertices = 50
        self.vertices = {}
        for vid in range(self.n_vertices):
            self.vertices[vid] = {
                "i_value": 0.5 + 0.5 * (vid / self.n_vertices),
                "semantic_distance": 0.1 * (vid % 10),
                "importance": 1.0,
            }

        self.edges = []
        for i in range(self.n_vertices):
            for j in range(i + 1, min(i + 5, self.n_vertices)):
                self.edges.append({
                    "src": i,
                    "dst": j,
                    "weight": 1.0,
                })

    def test_stage1_pruning(self):
        """测试 Stage 1: Dead-Zero 剪枝"""
        v1, e1 = self.engine.stage1_dead_zero_pruning(self.vertices, self.edges)
        assert len(v1) <= len(self.vertices)

    def test_stage2_merging(self):
        """测试 Stage 2: EML-Lite 合并"""
        # 先剪枝
        v1, e1 = self.engine.stage1_dead_zero_pruning(self.vertices, self.edges)
        # 再合并
        v2, e2 = self.engine.stage2_eml_lite_merging(v1, e1)
        assert len(v2) <= len(v1)

    def test_stage3_weighting(self):
        """测试 Stage 3: Mao Rui 加权"""
        v1, e1 = self.engine.stage1_dead_zero_pruning(self.vertices, self.edges)
        v2, e2 = self.engine.stage2_eml_lite_merging(v1, e1)
        v3, e3 = self.engine.stage3_mao_rui_weighting(v2, e2)
        assert len(v3) == len(v2)

    def test_stage4_selection(self):
        """测试 Stage 4: κ-Snap 选择"""
        v1, e1 = self.engine.stage1_dead_zero_pruning(self.vertices, self.edges)
        v2, e2 = self.engine.stage2_eml_lite_merging(v1, e1)
        v3, e3 = self.engine.stage3_mao_rui_weighting(v2, e2)
        v4, e4, kappa = self.engine.stage4_kappa_snap_selection(v3, e3)
        assert kappa in self.engine.kappa_candidates

    def test_stage5_encoding(self):
        """测试 Stage 5: ANS 编码"""
        v1, e1 = self.engine.stage1_dead_zero_pruning(self.vertices, self.edges)
        v2, e2 = self.engine.stage2_eml_lite_merging(v1, e1)
        v3, e3 = self.engine.stage3_mao_rui_weighting(v2, e2)
        v4, e4, kappa = self.engine.stage4_kappa_snap_selection(v3, e3)
        ans_bytes = self.engine.stage5_ans_encoding(v4, e4)
        assert len(ans_bytes) > 0

    def test_compress(self):
        """测试端到端压缩"""
        result = self.engine.compress(self.vertices, self.edges)
        assert result.compression_ratio >= 1.0
        assert 0.0 <= result.information_loss <= 1.0
        assert len(result.stages_applied) == 5

    def test_get_state(self):
        """测试获取状态"""
        state = self.engine.get_state()
        assert state["engine"] == "EMLSemZipEngine"
        assert "total_pruning_calls" in state

    def test_singleton(self):
        """测试单例模式"""
        from eml_semzip import EMLSemZipEngine

        inst1 = EMLSemZipEngine.get_instance()
        inst2 = EMLSemZipEngine.get_instance()
        assert inst1 is inst2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
