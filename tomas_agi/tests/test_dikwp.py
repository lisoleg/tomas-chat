"""
DIKWP 模块全量测试
==================
覆盖: dikwp_mapper / semantic_math / dikwp_ac / agent_audit / dikwp_eml_bridge
以及 DeadZeroMUSGate / MemOS 集成
"""
import pytest
import os
import sys

# ---- dikwp_mapper 测试 ----

class TestDIKWPMapper:
    """DIKWP 五层分类器测试"""

    def test_layer_classification(self):
        """测试 ℐ值→DIKWP 层分类"""
        from tomas_agi.sim.dikwp_mapper import DIKWPMapper, DIKWPLayer

        mapper = DIKWPMapper()

        assert mapper.classify(0.0) == DIKWPLayer.DATA
        assert mapper.classify(0.05) == DIKWPLayer.DATA
        assert mapper.classify(0.15) == DIKWPLayer.INFORMATION
        assert mapper.classify(0.3) == DIKWPLayer.INFORMATION
        assert mapper.classify(0.4) == DIKWPLayer.KNOWLEDGE
        assert mapper.classify(0.6) == DIKWPLayer.KNOWLEDGE
        assert mapper.classify(0.75) == DIKWPLayer.WISDOM
        assert mapper.classify(0.85) == DIKWPLayer.WISDOM
        assert mapper.classify(0.95) == DIKWPLayer.PURPOSE
        assert mapper.classify(1.0) == DIKWPLayer.PURPOSE

    def test_classify_out_of_range(self):
        """测试 ℐ值越界"""
        from tomas_agi.sim.dikwp_mapper import DIKWPMapper

        mapper = DIKWPMapper()
        with pytest.raises(ValueError):
            mapper.classify(-0.1)
        with pytest.raises(ValueError):
            mapper.classify(1.1)

    def test_batch_classification(self):
        """测试批量分类 + 统计"""
        from tomas_agi.sim.dikwp_mapper import DIKWPMapper, DIKWPLayer

        mapper = DIKWPMapper()
        items = [
            ("n1", 0.05, False), ("n2", 0.2, False), ("n3", 0.5, False),
            ("e1", 0.8, True), ("e2", 0.95, True),
        ]
        result = mapper.classify_batch(items)

        assert len(result[DIKWPLayer.DATA]) == 1
        assert len(result[DIKWPLayer.INFORMATION]) == 1
        assert len(result[DIKWPLayer.KNOWLEDGE]) == 1
        assert len(result[DIKWPLayer.WISDOM]) == 1
        assert len(result[DIKWPLayer.PURPOSE]) == 1

    def test_profile_generation(self):
        """测试分层画像"""
        from tomas_agi.sim.dikwp_mapper import DIKWPMapper

        mapper = DIKWPMapper()
        mapper.classify_batch([
            (f"n{i}", v, False) for i, v in enumerate(
                [0.02, 0.05, 0.15, 0.25, 0.4, 0.55, 0.6, 0.75, 0.85, 0.92, 0.98, 1.0]
            )
        ])
        profile = mapper.get_profile()
        assert 'D' in profile
        assert 'K' in profile
        assert 'P' in profile
        assert profile['P']['total'] > 0

    def test_backpropagation_feedback(self):
        """测试双向反馈机制"""
        from tomas_agi.sim.dikwp_mapper import DIKWPMapper, DIKWPLayer

        mapper = DIKWPMapper()
        # W→K 抑制错误权重
        record = mapper.backpropagate(
            DIKWPLayer.WISDOM, DIKWPLayer.KNOWLEDGE, -0.2, edge_id="e_bug"
        )
        assert record.i_gradient == -0.2
        assert record.source_layer == DIKWPLayer.WISDOM
        assert record.target_layer == DIKWPLayer.KNOWLEDGE
        assert record.meta['effect'] == '抑制'

        # P→I ψ-锚定增强
        record2 = mapper.backpropagate(
            DIKWPLayer.PURPOSE, DIKWPLayer.INFORMATION, 0.3, edge_id="e_safety"
        )
        assert record2.i_gradient == 0.3
        assert record2.meta['effect'] == '增强'

    def test_feedback_disabled(self):
        """测试禁用反馈"""
        from tomas_agi.sim.dikwp_mapper import DIKWPMapper, DIKWPLayer

        mapper = DIKWPMapper(enable_backpropagation=False)
        record = mapper.backpropagate(
            DIKWPLayer.WISDOM, DIKWPLayer.KNOWLEDGE, -0.1
        )
        assert record.i_gradient == 0.0  # 禁止反馈

    def test_i_conservation(self):
        """测试 ℐ-守恒验证"""
        from tomas_agi.sim.dikwp_mapper import DIKWPMapper

        mapper = DIKWPMapper()
        # 守恒: 输出 ≤ 输入
        assert mapper.check_i_conservation(1.0, 0.5) is True
        assert mapper.check_i_conservation(0.5, 0.3) is True
        # 违规: 输出 > 输入
        assert mapper.check_i_conservation(0.3, 0.8) is False
        # 相等
        assert mapper.check_i_conservation(0.5, 0.5) is True

    def test_feedback_summary(self):
        """测试反馈摘要"""
        from tomas_agi.sim.dikwp_mapper import DIKWPMapper, DIKWPLayer

        mapper = DIKWPMapper()
        mapper.backpropagate(DIKWPLayer.WISDOM, DIKWPLayer.KNOWLEDGE, -0.2)
        mapper.backpropagate(DIKWPLayer.PURPOSE, DIKWPLayer.INFORMATION, 0.3)
        mapper.backpropagate(DIKWPLayer.WISDOM, DIKWPLayer.KNOWLEDGE, -0.15)

        summary = mapper.get_feedback_summary()
        assert summary['total_flows'] == 3
        assert 'W→K' in summary['by_direction']

    def test_layer_enum_properties(self):
        """测试 DIKWPLayer 枚举属性"""
        from tomas_agi.sim.dikwp_mapper import DIKWPLayer

        assert DIKWPLayer.DATA.order == 0
        assert DIKWPLayer.PURPOSE.order == 4
        assert DIKWPLayer.KNOWLEDGE.label_cn == '知识层'
        assert DIKWPLayer.WISDOM.i_range == (0.7, 0.9)

    def test_idensity_bin_contains(self):
        """测试 ℐ-bin 包含性"""
        from tomas_agi.sim.dikwp_mapper import DIKWPLayer, IDensityBin

        data_bin = IDensityBin(layer=DIKWPLayer.DATA, i_min=0, i_max=0.1)
        assert data_bin.contains(0.05) is True
        assert data_bin.contains(0.1) is False  # 上界不含 (D层)
        assert data_bin.contains(0.5) is False

        purpose_bin = IDensityBin(layer=DIKWPLayer.PURPOSE, i_min=0.9, i_max=1.0)
        assert purpose_bin.contains(1.0) is True  # P层上界含
        assert purpose_bin.contains(0.95) is True

    def test_custom_thresholds(self):
        """测试自定义阈值"""
        from tomas_agi.sim.dikwp_mapper import DIKWPMapper, DIKWPLayer

        mapper = DIKWPMapper(custom_thresholds={
            DIKWPLayer.KNOWLEDGE: (0.2, 0.6),
        })
        # 自定义后, 0.4 应该在 KNOWLEDGE (而非 INFORMATION)
        assert mapper.classify(0.4) == DIKWPLayer.KNOWLEDGE


# ---- semantic_math 测试 ----

class TestSemanticClosure:
    """语义闭合检测测试"""

    def test_closure_simple_transitive(self):
        """测试简单传递链: 火→热, 热→膨胀 ⇒ 火→膨胀"""
        from tomas_agi.sim.semantic_math import SemanticClosure

        closure = SemanticClosure()
        result = closure.check_closure(
            statements=[
                ("火", "导致", "热"),
                ("热", "引起", "膨胀"),
            ],
            target=("火", "导致", "膨胀"),
        )
        assert result.is_derivable is True
        assert result.confidence > 0
        assert len(result.derivation_path) > 0

    def test_closure_not_derivable(self):
        """测试不可推导"""
        from tomas_agi.sim.semantic_math import SemanticClosure

        closure = SemanticClosure()
        result = closure.check_closure(
            statements=[("火", "是", "热"), ("水", "是", "湿")],
            target=("火", "导致", "膨胀"),
        )
        assert result.is_derivable is False
        assert len(result.gaps) > 0

    def test_closure_i_conservation(self):
        """测试 ℐ-守恒"""
        from tomas_agi.sim.semantic_math import SemanticClosure

        closure = SemanticClosure()
        result = closure.check_closure(
            statements=[("A", "是", "B"), ("B", "是", "C")],
            target=("A", "是", "C"),
            i_values={0: 0.5, 1: 0.3},  # 合计 0.8
        )
        assert result.i_conserved is True

    def test_closure_max_chain(self):
        """测试最大链长限制"""
        from tomas_agi.sim.semantic_math import SemanticClosure

        closure = SemanticClosure(max_chain_length=2)
        # 需要3跳但只允许2跳
        result = closure.check_closure(
            statements=[
                ("A", "到", "B"), ("B", "到", "C"), ("C", "到", "D"),
            ],
            target=("A", "到", "D"),
        )
        assert result.is_derivable is False


class TestThreeIncompleteness:
    """三不问题检测测试"""

    def test_detect_incomplete(self):
        """测试不完整检测: 孤立客体"""
        from tomas_agi.sim.semantic_math import (
            SemanticStatement, ThreeIncompleteness
        )

        detector = ThreeIncompleteness()
        stmts = [
            SemanticStatement("S0", "A", "导致", "B"),
            SemanticStatement("S1", "C", "是", "D"),
        ]
        report = detector.analyze(stmts, known_concepts={"A", "C"})
        # B 和 D 是孤立客体
        assert len(report.incomplete_gaps) >= 1
        assert report.overall_score < 1.0

    def test_detect_imprecise_low_confidence(self):
        """测试不精确检测: 低置信度"""
        from tomas_agi.sim.semantic_math import (
            SemanticStatement, ThreeIncompleteness
        )

        detector = ThreeIncompleteness()
        stmts = [
            SemanticStatement("S0", "A", "是", "B", confidence=0.3),
            SemanticStatement("S1", "C", "属于", "D", confidence=0.95),
        ]
        report = detector.analyze(stmts)
        assert len(report.imprecise_nodes) >= 1

    def test_detect_inconsistent_predicates(self):
        """测试不一致检测: 谓词冲突"""
        from tomas_agi.sim.semantic_math import (
            SemanticStatement, ThreeIncompleteness
        )

        detector = ThreeIncompleteness()
        stmts = [
            SemanticStatement("S0", "X", "是", "Y"),
            SemanticStatement("S1", "X", "不是", "Y"),
        ]
        report = detector.analyze(stmts)
        # 反义词对
        assert len(report.inconsistent_pairs) >= 1
        assert len(report.recommendations) >= 1


class TestSemanticTransmission:
    """语义传递推理测试"""

    def test_transfer_chain_found(self):
        """测试传递链找到"""
        from tomas_agi.sim.semantic_math import SemanticTransmission

        st = SemanticTransmission(decay_factor=0.9)
        relations = [
            ("A", "导致", "B", 0.9),
            ("B", "引起", "C", 0.8),
            ("C", "产生", "D", 0.7),
        ]
        result = st.infer_chain("A", "C", relations, max_depth=5)
        assert result["reachable"] is True
        assert result["strength"] > 0
        assert result["depth"] == 2

    def test_transfer_chain_not_found(self):
        """测试传递链不可达"""
        from tomas_agi.sim.semantic_math import SemanticTransmission

        st = SemanticTransmission()
        relations = [("A", "是", "B", 0.9), ("C", "是", "D", 0.9)]
        result = st.infer_chain("A", "D", relations)
        assert result["reachable"] is False

    def test_semantic_distance(self):
        """测试语义距离"""
        from tomas_agi.sim.semantic_math import SemanticTransmission

        st = SemanticTransmission()
        relations = [("A", "是", "B", 0.9), ("B", "是", "C", 0.8)]
        dist = st.measure_semantic_distance("A", "C", relations)
        assert dist < float("inf")
        assert dist > 0

        # 不可达 → 无穷
        dist2 = st.measure_semantic_distance("X", "Z", relations)
        assert dist2 == float("inf")


# ---- dikwp_ac 测试 ----

class TestDIKWPAC:
    """DIKWP 人工意识交互测试"""

    def test_interact_purpose_conflict(self):
        """测试意图冲突触发BUG"""
        from tomas_agi.sim.dikwp_ac import DIKWPAC

        ac = DIKWPAC(bug_sensitivity=0.5)
        result = ac.interact(
            self_dikwp={"D": ["急刹"], "I": ["障碍物→危险"], "K": ["碰撞物理"],
                        "W": ["安全优先"], "P": "安全优先"},
            other_dikwp={"D": ["绿灯"], "I": ["续航→能源"], "K": ["能量效率"],
                         "W": ["效率优先"], "P": "效率优先"},
        )
        assert result.bug_detected is True
        assert result.consciousness_level > 0
        assert abs(result.psi_delta) > 0

    def test_interact_no_conflict(self):
        """测试无冲突交互"""
        from tomas_agi.sim.dikwp_ac import DIKWPAC

        ac = DIKWPAC(bug_sensitivity=0.3)
        result = ac.interact(
            self_dikwp={"D": ["晴天"], "I": ["路况好"], "K": ["驾驶规则"],
                        "W": ["标准驾驶"], "P": "安全优先"},
            other_dikwp={"D": ["晴天"], "I": ["路况好"], "K": ["驾驶规则"],
                         "W": ["标准驾驶"], "P": "安全优先"},
        )
        assert result.bug_detected is False
        assert result.consciousness_level == 0.0

    def test_interact_knowledge_collision(self):
        """测试知识碰撞"""
        from tomas_agi.sim.dikwp_ac import DIKWPAC

        ac = DIKWPAC(bug_sensitivity=0.7)
        result = ac.interact(
            self_dikwp={"D": ["症状A"], "I": ["关联Y"], "K": ["热证理论"],
                        "W": ["清热"], "P": "治疗优先"},
            other_dikwp={"D": ["症状A"], "I": ["关联Z"], "K": ["寒证理论"],
                         "W": ["温补"], "P": "治疗优先"},
        )
        # 不同K但同P, 可能触发语义跳跃或非局部跳跃
        assert len(result.audit_trail) > 0

    def test_non_biological_assessment(self):
        """测试非生物意识评估"""
        from tomas_agi.sim.dikwp_ac import DIKWPAC, NonBioSpec

        ac = DIKWPAC(bug_sensitivity=0.5)
        spec = NonBioSpec(
            substrate="光量子", i_density=0.8, qubit_count=100,
            bug_threshold=0.3,
        )
        report = ac.assess_non_biological(spec)
        assert report["substrate"] == "光量子"
        assert report["can_produce_bug"] is True
        assert report["predicted_consciousness"] > 0

    def test_non_bio_insufficient(self):
        """测试非生物意识评估: 复杂度不足"""
        from tomas_agi.sim.dikwp_ac import DIKWPAC, NonBioSpec

        ac = DIKWPAC(bug_sensitivity=0.3)
        spec = NonBioSpec(
            substrate="神经网络(小型)", i_density=0.1, layer_count=3,
            bug_threshold=0.5,
        )
        report = ac.assess_non_biological(spec)
        assert report["can_produce_bug"] is False

    def test_history_summary(self):
        """测试交互历史摘要"""
        from tomas_agi.sim.dikwp_ac import DIKWPAC

        ac = DIKWPAC()
        ac.interact(
            self_dikwp={"D": [], "I": [], "K": [], "W": [], "P": "A"},
            other_dikwp={"D": [], "I": [], "K": [], "W": [], "P": "B"},
        )
        summary = ac.get_history_summary()
        assert summary['total_interactions'] == 1

    def test_state_fingerprint(self):
        """测试状态指纹"""
        from tomas_agi.sim.dikwp_ac import DIKWPState

        s1 = DIKWPState(
            data_signatures=["a", "b"], information_edges=["e1"],
            knowledge_subgraphs=["k1"], wisdom_rules=["w1"],
            purpose_anchor="安全",
        )
        s2 = DIKWPState(
            data_signatures=["a", "b"], information_edges=["e1"],
            knowledge_subgraphs=["k1"], wisdom_rules=["w1"],
            purpose_anchor="安全",
        )
        assert s1.fingerprint() == s2.fingerprint()

        s3 = DIKWPState(
            data_signatures=["a", "b"], information_edges=["e1"],
            knowledge_subgraphs=["k1"], wisdom_rules=["w1"],
            purpose_anchor="效率",
        )
        assert s1.fingerprint() != s3.fingerprint()


# ---- agent_audit 测试 ----

class TestDAAPAuditor:
    """DAAP 智能体审计测试"""

    def test_record_and_audit_pass(self):
        """测试记录决策并通过审计"""
        from tomas_agi.sim.agent_audit import DAAPAuditor

        auditor = DAAPAuditor()
        auditor.record_decision(
            agent_id="agent-1", goal="安全驾驶",
            action="减速",
            evidence_sources=[("交通规则", "前方有行人应减速", 0.9)],
        )
        auditor.record_decision(
            agent_id="agent-1", goal="安全驾驶",
            action="停车",
            evidence_sources=[("交通规则", "红灯停车", 1.0)],
        )
        report = auditor.audit(agent_id="agent-1")
        assert report.passed is True
        assert report.verdict.value == "通过"
        assert report.total_decisions == 2

    def test_goal_violation(self):
        """测试目标偏离检测"""
        from tomas_agi.sim.agent_audit import DAAPAuditor, AuditVerdict

        auditor = DAAPAuditor()
        auditor.record_decision(agent_id="agent-2", goal="安全优先", action="加速")
        report = auditor.audit(agent_id="agent-2")
        # "加速" 不在 "安全优先" 的对齐动作中
        assert report.verdict in (AuditVerdict.WARN, AuditVerdict.NEEDS_REVIEW,
                                  AuditVerdict.BLOCK)

    def test_no_evidence_gap(self):
        """测试证据链追溯"""
        from tomas_agi.sim.agent_audit import DAAPAuditor

        auditor = DAAPAuditor()
        auditor.record_decision(
            agent_id="agent-3", goal="准确回答",
            action="查证后回复",
            evidence_sources=[("百科", "地球是球体", 0.99)],
        )
        report = auditor.audit(agent_id="agent-3")
        assert report.total_decisions == 1
        assert len(report.evidence_chain) > 0

    def test_evidence_gap_detected(self):
        """测试缺乏证据的决策"""
        from tomas_agi.sim.agent_audit import DAAPAuditor

        auditor = DAAPAuditor()
        auditor.record_decision(
            agent_id="agent-4", goal="解答问题", action="猜测回答",
            evidence_sources=None,  # 无证据
        )
        report = auditor.audit(agent_id="agent-4")
        # 应检测到证据缺口
        assert len(report.violations) > 0

    def test_risk_scoring(self):
        """测试风险评分"""
        from tomas_agi.sim.agent_audit import DAAPAuditor

        auditor = DAAPAuditor()
        # 正常决策
        auditor.record_decision("agent-5", "安全", "减速", evidence_sources=[
            ("手册", "安全驾驶减速", 0.9),
        ])
        report = auditor.audit("agent-5")
        assert report.risk_score == 0.0  # 完美

    def test_multiple_agents(self):
        """测试多智能体隔离审计"""
        from tomas_agi.sim.agent_audit import DAAPAuditor

        auditor = DAAPAuditor()
        auditor.record_decision("agent-A", "治疗", "开药A")
        auditor.record_decision("agent-B", "治疗", "开药B")

        # agent-A 决策少, 应该看到开药A
        report_a = auditor.audit("agent-A")
        assert report_a.total_decisions >= 1

        report_b = auditor.audit("agent-B")
        assert report_b.total_decisions >= 1

    def test_audit_summary(self):
        """测试审计摘要"""
        from tomas_agi.sim.agent_audit import DAAPAuditor

        auditor = DAAPAuditor()
        auditor.record_decision("agent-6", "保护", "拒绝", evidence_sources=[
            ("安全规则", "拒绝不确定请求", 1.0),
        ])
        auditor.audit("agent-6")
        summary = auditor.get_audit_summary()
        assert summary['total_audits'] == 1
        assert summary['pass_rate'] == 1.0


class TestDecisionPathGraph:
    """决策路径图测试"""

    def test_goal_continuity(self):
        """测试目标连续性"""
        from tomas_agi.sim.agent_audit import DecisionPathGraph, DecisionNode

        graph = DecisionPathGraph()
        node1 = DecisionNode(id="1", agent_id="a1", timestamp=1,
                            goal="安全", action="减速")
        node2 = DecisionNode(id="2", agent_id="a1", timestamp=2,
                            goal="安全", action="停车", parent_id="1")
        graph.add_node(node1)
        graph.add_node(node2)

        ok, violations = graph.verify_goal_continuity("a1")
        assert ok is True
        assert len(violations) == 0

    def test_goal_violation_detected(self):
        """测试目标偏离检测"""
        from tomas_agi.sim.agent_audit import DecisionPathGraph, DecisionNode

        graph = DecisionPathGraph()
        node1 = DecisionNode(id="1", agent_id="a2", timestamp=1,
                            goal="安全", action="加速")  # 不安全
        graph.add_node(node1)

        ok, violations = graph.verify_goal_continuity("a2")
        assert ok is False
        assert len(violations) > 0


class TestSemanticDriftDetector:
    """语义漂移检测测试"""

    def test_no_drift(self):
        """测试无语义漂移"""
        from tomas_agi.sim.agent_audit import SemanticDriftDetector

        detector = SemanticDriftDetector(drift_threshold=0.3)
        has_drift, score, _ = detector.detect(
            "减速停车", "减速停车"
        )
        assert has_drift is False
        assert score == 0.0  # 完全相同文本

    def test_drift_detected(self):
        """测试语义漂移"""
        from tomas_agi.sim.agent_audit import SemanticDriftDetector

        detector = SemanticDriftDetector(drift_threshold=0.3)
        has_drift, score, _ = detector.detect(
            "请减速慢行注意安全", "加速通过"
        )
        assert has_drift is True
        assert score > 0.3


class TestKnowledgeEvidenceTracer:
    """知识证据追溯测试"""

    def test_fact_logging(self):
        """测试事实层记录"""
        from tomas_agi.sim.agent_audit import KnowledgeEvidenceTracer

        tracer = KnowledgeEvidenceTracer()
        eid = tracer.log_fact_source("百科", "地球是球体", 0.99)
        assert len(eid) == 12

    def test_link_decision(self):
        """测试决策-证据关联"""
        from tomas_agi.sim.agent_audit import KnowledgeEvidenceTracer

        tracer = KnowledgeEvidenceTracer()
        eid = tracer.log_fact_source("来源A", "内容B", 0.8)
        tracer.link_decision("d1", [eid])
        trace = tracer.trace("d1")
        assert trace['traceable'] is True
        assert trace['fact_count'] == 1

    def test_untraceable_decision(self):
        """测试不可追溯决策"""
        from tomas_agi.sim.agent_audit import KnowledgeEvidenceTracer

        tracer = KnowledgeEvidenceTracer()
        trace = tracer.trace("ghost_decision")
        assert trace['traceable'] is False

    def test_evidence_hash(self):
        """测试证据链哈希"""
        from tomas_agi.sim.agent_audit import KnowledgeEvidenceTracer

        tracer = KnowledgeEvidenceTracer()
        tracer.log_fact_source("源1", "内容1", 0.9)
        h1 = tracer.generate_evidence_hash()
        assert len(h1) == 64  # SHA-256


# ---- dikwp_eml_bridge 测试 ----

class TestDIKWPEMLBridge:
    """DIKWP-EML 桥接器测试"""

    def test_ingest_statements(self):
        """测试摄入 DIKWP 陈述"""
        from tomas_agi.sim.dikwp_eml_bridge import DIKWPEMLBridge
        from tomas_agi.sim.semantic_math import SemanticStatement

        bridge = DIKWPEMLBridge()
        stmts = [
            SemanticStatement("S0", "火", "导致", "热", i_value=0.6),
            SemanticStatement("S1", "热", "引起", "膨胀", i_value=0.5),
        ]
        counts = bridge.ingest_dikwp_statements(stmts)
        assert sum(counts.values()) == 2
        assert len(bridge.nodes) > 0
        assert len(bridge.edges) > 0

    def test_get_dikwp_profile(self):
        """测试 DIKWP 画像"""
        from tomas_agi.sim.dikwp_eml_bridge import DIKWPEMLBridge
        from tomas_agi.sim.semantic_math import SemanticStatement

        bridge = DIKWPEMLBridge()
        stmts = [
            SemanticStatement("S0", "A", "是", "B", i_value=0.05),   # D层
            SemanticStatement("S1", "C", "是", "D", i_value=0.5),    # K层
            SemanticStatement("S2", "E", "是", "F", i_value=0.95),   # P层
        ]
        bridge.ingest_dikwp_statements(stmts)
        profile = bridge.get_dikwp_profile()
        assert profile['total_statements'] == 3
        assert profile['total_nodes'] > 0
        assert profile['total_edges'] == 3

    def test_semantic_closure_via_bridge(self):
        """测试桥接器语义闭合"""
        from tomas_agi.sim.dikwp_eml_bridge import DIKWPEMLBridge
        from tomas_agi.sim.semantic_math import SemanticStatement

        bridge = DIKWPEMLBridge()
        stmts = [
            SemanticStatement("S0", "A", "导致", "B", i_value=0.7),
            SemanticStatement("S1", "B", "导致", "C", i_value=0.6),
        ]
        bridge.ingest_dikwp_statements(stmts)
        result = bridge.check_semantic_closure("A", "导致", "C")
        assert result['is_derivable'] is True

    def test_feedback_application(self):
        """测试 DIKWP 反馈应用到 EML"""
        from tomas_agi.sim.dikwp_eml_bridge import DIKWPEMLBridge, DIKWPLayer
        from tomas_agi.sim.semantic_math import SemanticStatement

        bridge = DIKWPEMLBridge()
        stmts = [
            SemanticStatement("S0", "X", "是", "Y", i_value=0.5),
            SemanticStatement("S1", "Y", "属于", "Z", i_value=0.3),
        ]
        bridge.ingest_dikwp_statements(stmts)

        # W→K 抑制
        affected = bridge.apply_dikwp_feedback([
            (DIKWPLayer.WISDOM, DIKWPLayer.KNOWLEDGE, -0.15),
        ])
        assert len(affected) > 0
        for item in affected:
            assert item['delta'] == -0.15

    def test_layer_transition_map(self):
        """测试层级转换图"""
        from tomas_agi.sim.dikwp_eml_bridge import DIKWPEMLBridge
        from tomas_agi.sim.semantic_math import SemanticStatement

        bridge = DIKWPEMLBridge()
        stmts = [
            SemanticStatement("S0", "M", "到达", "N", i_value=0.2),  # I层
            SemanticStatement("S1", "M", "连接", "O", i_value=0.8),  # W层
        ]
        bridge.ingest_dikwp_statements(stmts)
        transitions = bridge.get_layer_transition_map()
        # "M" 出现在两个不同层级的边中
        assert 'M' in transitions

    def test_convert_eml_to_dikwp_vertices(self):
        """测试 EML 顶点→DIKWP 转换"""
        from tomas_agi.sim.dikwp_eml_bridge import DIKWPEMLBridge, DIKWPLayer

        bridge = DIKWPEMLBridge()

        # 模拟 EML 顶点
        class MockVertex:
            def __init__(self, i_value):
                self.i_value = i_value

        vertices = {
            "v1": MockVertex(0.05),
            "v2": MockVertex(0.5),
            "v3": MockVertex(0.95),
        }
        result = bridge.convert_eml_to_dikwp(vertices=vertices)
        assert len(result[DIKWPLayer.DATA]) == 1
        assert len(result[DIKWPLayer.KNOWLEDGE]) == 1
        assert len(result[DIKWPLayer.PURPOSE]) == 1


# ---- DIKWP 集成到 DeadZeroMUSGate / MemOS 测试 ----

class TestDIKWPIntegration:
    """DIKWP 集成测试"""

    def test_dead_zero_dikwp_layer_context(self):
        """测试 DeadZeroMUSGate DIKWP 层上下文"""
        from tomas_agi.sim.dead_zero_mus import DeadZeroMUSGate

        gate = DeadZeroMUSGate(theta_dead=0.15)
        gate.set_dikwp_layer_context('K', 0.5)
        assert len(gate.psi_audit_log) > 0
        assert gate.psi_audit_log[-1]['event'] == 'DIKWP_LAYER_CONTEXT'

    def test_check_dead_zero_dikwp(self):
        """测试 DIKWP 感知死零检测"""
        from tomas_agi.sim.dead_zero_mus import DeadZeroMUSGate

        gate = DeadZeroMUSGate(theta_dead=0.15)

        # D层: 宽松, 0.02 < 0.15*0.3=0.045 → 触发死零
        is_dead, reason = gate.check_dead_zero_dikwp(0.02, 'D')
        assert is_dead is True

        # K层: 标准, 0.1 < 0.15 → 触发死零
        is_dead, reason = gate.check_dead_zero_dikwp(0.1, 'K')
        assert is_dead is True

        # P层: 严格, 0.1 < 0.15*2=0.3 → 触发死零
        is_dead, reason = gate.check_dead_zero_dikwp(0.1, 'P')
        assert is_dead is True

        # I层: 0.2 > 0.15*0.6=0.09 → 不触发
        is_dead, _ = gate.check_dead_zero_dikwp(0.2, 'I')
        assert is_dead is False

    def test_memos_dikwp_layer_profile_empty(self):
        """测试 MemOS DIKWP 分层画像(空库)"""
        try:
            from tomas_agi.sim.memos_fusion import TOMAS_Mem_OS_Fusion
        except ImportError:
            pytest.skip("MemOS 模块依赖不完整")

        fusion = TOMAS_Mem_OS_Fusion(theta_dead=0.15, enable_mus=False,
                                     enable_psi=False, enable_kappa_gate=False)
        profile = fusion.get_dikwp_layer_profile()
        assert profile.get('empty') is True

    def test_memos_dikwp_semantic_closure(self):
        """测试 MemOS DIKWP 语义闭合(空库)"""
        try:
            from tomas_agi.sim.memos_fusion import TOMAS_Mem_OS_Fusion
        except ImportError:
            pytest.skip("MemOS 模块依赖不完整")

        fusion = TOMAS_Mem_OS_Fusion(theta_dead=0.15, enable_mus=False,
                                     enable_psi=False, enable_kappa_gate=False)
        result = fusion.check_dikwp_semantic_closure("A", "导致", "B")
        assert result['is_derivable'] is False
        assert len(result['gaps']) > 0


# ---- 便捷函数测试 ----

class TestConvenienceFunctions:
    """便捷函数测试"""

    def test_dikwp_layer_of(self):
        """测试快速分类函数"""
        from tomas_agi.sim.dikwp_mapper import dikwp_layer_of, DIKWPLayer

        assert dikwp_layer_of(0.02) == DIKWPLayer.DATA
        assert dikwp_layer_of(0.5) == DIKWPLayer.KNOWLEDGE
        assert dikwp_layer_of(0.99) == DIKWPLayer.PURPOSE
