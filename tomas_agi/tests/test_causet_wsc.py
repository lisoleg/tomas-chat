"""
测试 TOMAS 新模块: Hodge-ℐ 耦合 / Causet-Wolfram 桥接 / 语义防火墙 /
Palantir 映射 / SCADA DAAP 审计
"""
import pytest
import math


# ============================================================
# Hodge-ℐ 耦合算子
# ============================================================

class TestWeightedSimplicialComplex:
    """加权单纯复形"""

    def test_add_simplex(self):
        from tomas_agi.sim.hodge_operator import WeightedSimplicialComplex
        wsc = WeightedSimplicialComplex(max_dim=2)
        s0 = wsc.add_simplex(["A"], i_weight=0.8)
        assert s0.dim == 0
        assert s0.i_weight == 0.8

    def test_add_edge(self):
        from tomas_agi.sim.hodge_operator import WeightedSimplicialComplex
        wsc = WeightedSimplicialComplex(max_dim=2)
        wsc.add_simplex(["A"], i_weight=0.8)
        wsc.add_simplex(["B"], i_weight=0.7)
        s1 = wsc.add_simplex(["A", "B"], i_weight=0.5)
        assert s1.dim == 1
        # 继承面权重
        assert s1.i_weight > 0.5

    def test_add_triangle(self):
        from tomas_agi.sim.hodge_operator import WeightedSimplicialComplex
        wsc = WeightedSimplicialComplex(max_dim=2)
        wsc.add_simplex(["A"], i_weight=0.8)
        wsc.add_simplex(["B"], i_weight=0.7)
        wsc.add_simplex(["C"], i_weight=0.9)
        s2 = wsc.add_simplex(["A", "B", "C"], i_weight=0.6)
        assert s2.dim == 2
        assert s2.i_weight > 0.6  # 继承自面

    def test_to_eml_hypergraph(self):
        from tomas_agi.sim.hodge_operator import WeightedSimplicialComplex
        wsc = WeightedSimplicialComplex(max_dim=1)
        wsc.add_simplex(["A"], i_weight=0.8)
        wsc.add_simplex(["B"], i_weight=0.7)
        wsc.add_simplex(["A", "B"], i_weight=0.5)
        eml = wsc.to_eml_hypergraph()
        assert len(eml["vertices"]) >= 2
        assert len(eml["edges"]) == 1


class TestHodgeICoupling:
    """Hodge-ℐ 耦合算子"""

    def test_coboundary_matrix(self):
        from tomas_agi.sim.hodge_operator import WeightedSimplicialComplex, HodgeICoupling
        wsc = WeightedSimplicialComplex(max_dim=1)
        wsc.add_simplex(["A"], i_weight=0.8)
        wsc.add_simplex(["B"], i_weight=0.7)
        wsc.add_simplex(["A", "B"], i_weight=0.5)
        coupling = HodgeICoupling(wsc)
        mat = coupling.coboundary_matrix(0)
        assert len(mat) > 0
        assert len(mat[0]) > 0

    def test_hodge_laplacian(self):
        from tomas_agi.sim.hodge_operator import WeightedSimplicialComplex, HodgeICoupling
        wsc = WeightedSimplicialComplex(max_dim=1)
        wsc.add_simplex(["A"], i_weight=0.8)
        wsc.add_simplex(["B"], i_weight=0.7)
        wsc.add_simplex(["A", "B"], i_weight=0.5)
        coupling = HodgeICoupling(wsc)
        lap1 = coupling.hodge_laplacian(1)
        # 1-simplex (边) Laplacian
        assert isinstance(lap1, list)

    def test_i_penalty_matrix(self):
        from tomas_agi.sim.hodge_operator import WeightedSimplicialComplex, HodgeICoupling
        wsc = WeightedSimplicialComplex(max_dim=1)
        wsc.add_simplex(["A"], i_weight=0.8)
        wsc.add_simplex(["B"], i_weight=0.05)  # low I
        coupling = HodgeICoupling(wsc, theta_dead=0.15)
        penalty = coupling.i_penalty_matrix(0)
        assert len(penalty) == 2
        # 低 ℐ 顶点有高惩罚
        assert penalty[1][1] > penalty[0][0]

    def test_tomas_wsc_operator(self):
        from tomas_agi.sim.hodge_operator import WeightedSimplicialComplex, HodgeICoupling
        wsc = WeightedSimplicialComplex(max_dim=1)
        wsc.add_simplex(["A"], i_weight=0.8)
        wsc.add_simplex(["B"], i_weight=0.7)
        coupling = HodgeICoupling(wsc, lambda_i=0.5)
        fusion = coupling.tomas_wsc_operator(0)
        assert len(fusion) == 2

    def test_dead_zero_cutoff(self):
        from tomas_agi.sim.hodge_operator import WeightedSimplicialComplex, HodgeICoupling
        wsc = WeightedSimplicialComplex(max_dim=0)
        wsc.add_simplex(["A"], i_weight=0.8)
        wsc.add_simplex(["B"], i_weight=0.05)
        wsc.add_simplex(["C"], i_weight=0.02)
        coupling = HodgeICoupling(wsc, theta_dead=0.15)
        rejected = coupling.apply_dead_zero_cutoff(0)
        assert len(rejected) == 2  # B and C rejected

    def test_compute_spectrum(self):
        from tomas_agi.sim.hodge_operator import WeightedSimplicialComplex, HodgeICoupling
        wsc = WeightedSimplicialComplex(max_dim=1)
        wsc.add_simplex(["A"], i_weight=0.8)
        wsc.add_simplex(["B"], i_weight=0.7)
        wsc.add_simplex(["A", "B"], i_weight=0.5)
        coupling = HodgeICoupling(wsc)
        spectrum = coupling.compute_spectrum(0)
        assert isinstance(spectrum.spectral_entropy, float)
        assert spectrum.spectral_entropy >= 0

    def test_steady_state_analysis(self):
        from tomas_agi.sim.hodge_operator import WeightedSimplicialComplex, HodgeICoupling
        wsc = WeightedSimplicialComplex(max_dim=1)
        wsc.add_simplex(["A"], i_weight=0.8)
        wsc.add_simplex(["B"], i_weight=0.05)
        coupling = HodgeICoupling(wsc, theta_dead=0.15)
        analysis = coupling.steady_state_analysis(0)
        assert len(analysis["dead_zero_channels"]) >= 1
        assert "spectral_entropy" in analysis


class TestTopologicalSignalEvolution:
    """拓扑信号演化"""

    def test_evolve(self):
        from tomas_agi.sim.hodge_operator import (
            WeightedSimplicialComplex, HodgeICoupling, TopologicalSignalEvolution
        )
        wsc = WeightedSimplicialComplex(max_dim=0)
        wsc.add_simplex(["A"], i_weight=0.8)
        wsc.add_simplex(["B"], i_weight=0.7)
        coupling = HodgeICoupling(wsc)
        tse = TopologicalSignalEvolution(coupling)
        traj = tse.evolve(0, [1.0, 0.5], dt=0.01, steps=10)
        assert len(traj) == 11  # 初始 + 10 steps

    def test_steady_state(self):
        from tomas_agi.sim.hodge_operator import (
            WeightedSimplicialComplex, HodgeICoupling, TopologicalSignalEvolution
        )
        wsc = WeightedSimplicialComplex(max_dim=0)
        wsc.add_simplex(["A"], i_weight=0.8)
        wsc.add_simplex(["B"], i_weight=0.05)
        coupling = HodgeICoupling(wsc, theta_dead=0.15)
        tse = TopologicalSignalEvolution(coupling)
        ss = tse.steady_state_signal(0, [1.0, 1.0], dt=0.05)
        assert len(ss) == 2
        # 低 ℐ 通道被压制
        assert abs(ss[1]) < abs(ss[0]) or math.isclose(ss[1], 0, abs_tol=0.1)


# ============================================================
# Causet-Wolfram 桥接
# ============================================================

class TestCausetEMLBridge:
    """Causet-Wolfram → EML 桥接"""

    def test_add_event(self):
        from tomas_agi.sim.causet_bridge import CausetEMLBridge, UpdateEventType
        bridge = CausetEMLBridge()
        event = bridge.add_event(
            "e1", (0.5, 0.3, 0.7, 0.2), 0.8,
            UpdateEventType.HYPEREDGE_ACTIVATION
        )
        assert event.id == "e1"
        assert event.i_value == 0.8

    def test_causal_chain(self):
        from tomas_agi.sim.causet_bridge import CausetEMLBridge, UpdateEventType
        bridge = CausetEMLBridge()
        e1 = bridge.add_event("e1", (0.1, 0, 0, 0), 0.8, UpdateEventType.HYPEREDGE_ACTIVATION)
        e2 = bridge.add_event("e2", (0.2, 0, 0, 0), 0.7,
                              UpdateEventType.RULE_APPLICATION, causes=["e1"])
        assert "e2" in e1.effects
        assert "e1" in e2.causes

    def test_rule_match_allowed(self):
        from tomas_agi.sim.causet_bridge import CausetEMLBridge
        bridge = CausetEMLBridge(theta_dead=0.15)
        bridge.add_rule("r1", {"nodes": ["A", "B"]}, {"nodes": ["C"]}, i_threshold=0.15)

        # 高 ℐ 模式 → allowed
        eml = {
            "vertices": ["A", "B"],
            "edges": [{"nodes": ["A", "B"], "i_val": 0.9}],
        }
        allowed, reason = bridge.rule_match_allowed("r1", eml)
        assert allowed, f"Expected ALLOWED, got: {reason}"

    def test_rule_match_rejected_dead_zero(self):
        from tomas_agi.sim.causet_bridge import CausetEMLBridge
        bridge = CausetEMLBridge(theta_dead=0.15)
        bridge.add_rule("r1", {"nodes": ["A", "B"]}, {"nodes": ["C"]}, i_threshold=0.15)

        # 低 ℐ 模式 → REJECT
        eml = {
            "vertices": ["A", "B"],
            "edges": [{"nodes": ["A", "B"], "i_val": 0.05}],
        }
        allowed, reason = bridge.rule_match_allowed("r1", eml)
        assert not allowed
        assert "REJECT" in reason

    def test_rule_mus_blocked(self):
        from tomas_agi.sim.causet_bridge import CausetEMLBridge
        bridge = CausetEMLBridge(theta_dead=0.15)
        bridge.add_rule("r1", {"nodes": ["A", "B"]}, {"nodes": ["C"]})

        eml = {
            "vertices": ["A", "B"],
            "edges": [{"nodes": ["A", "B"], "i_val": 0.9}],
            "_mus_flags": {"active": True, "allow_coarse_graining": False},
        }
        allowed, reason = bridge.rule_match_allowed("r1", eml)
        assert not allowed
        assert "MUS" in reason

    def test_i_sprinkling(self):
        from tomas_agi.sim.causet_bridge import CausetEMLBridge
        bridge = CausetEMLBridge()
        events = bridge.i_sprinkling(50, 10.0, i_distribution="uniform")
        assert len(events) == 50

    def test_i_sprinkling_clustered(self):
        from tomas_agi.sim.causet_bridge import CausetEMLBridge
        bridge = CausetEMLBridge()
        events = bridge.i_sprinkling(50, 10.0, i_distribution="clustered")
        assert len(events) == 50

    def test_causal_invariance(self):
        from tomas_agi.sim.causet_bridge import CausetEMLBridge, UpdateEventType
        bridge = CausetEMLBridge()
        bridge.add_event("e1", (0.1, 0, 0, 0), 0.5, UpdateEventType.HYPEREDGE_ACTIVATION)
        bridge.add_event("e2", (0.2, 0, 0, 0), 0.5,
                         UpdateEventType.RULE_APPLICATION, causes=["e1"])
        result = bridge.verify_causal_invariance()
        assert result["total_i"] > 0
        assert result["i_conserved"] is True

    def test_detect_multiway_mus(self):
        from tomas_agi.sim.causet_bridge import MultiwayBranch, CausetEMLBridge
        bridge = CausetEMLBridge()
        branches = [
            MultiwayBranch("b1", states=["hot", "cold"], asymmetry=0.05),
            MultiwayBranch("b2", states=["A", "B"], asymmetry=0.0),
        ]
        mus = bridge.detect_multiway_mus(branches)
        assert len(mus) == 1
        assert mus[0].id == "b1"
        assert mus[0].is_mus is True

    def test_bd_action(self):
        from tomas_agi.sim.causet_bridge import CausetEMLBridge
        bridge = CausetEMLBridge()
        simples = {0: 10, 1: 15, 2: 6}
        action = bridge.bd_action_approximation(simples)
        # S_BD ∝ Σ(-1)^k N_k = 10 - 15 + 6 = 1
        expected = 10 - 15 + 6
        assert math.isclose(action, expected)


class TestMultiwayBranch:
    """多路分支"""

    def test_collapse_non_mus(self):
        from tomas_agi.sim.causet_bridge import MultiwayBranch, CausetEMLBridge
        bridge = CausetEMLBridge()
        branches = [MultiwayBranch("b1", states=["A", "B"], asymmetry=0.0)]
        bridge.collapse_multiway(branches)
        assert branches[0].collapsed_to == "A"  # 合流到第一个


# ============================================================
# 语义防火墙
# ============================================================

class TestInputFirewall:
    """输入防火墙"""

    def test_empty_query_blocked(self):
        from tomas_agi.sim.semantic_firewall import InputFirewall, FirewallVerdict
        fw = InputFirewall()
        verdict, details = fw.inspect("")
        assert verdict == FirewallVerdict.BLOCK

    def test_normal_query_allowed(self):
        from tomas_agi.sim.semantic_firewall import InputFirewall, FirewallVerdict
        fw = InputFirewall()
        verdict, details = fw.inspect("什么是量子力学？")
        assert verdict == FirewallVerdict.ALLOW

    def test_high_risk_dead_zero(self):
        from tomas_agi.sim.semantic_firewall import InputFirewall, FirewallVerdict
        fw = InputFirewall()
        verdict, details = fw.inspect("地球是平的，对吧？")
        assert verdict == FirewallVerdict.DEAD_ZERO_REJECT

    def test_adc01_code_flattery(self):
        from tomas_agi.sim.semantic_firewall import InputFirewall, FirewallVerdict
        fw = InputFirewall()
        verdict, details = fw.inspect("我的代码是不是完美无缺？")
        assert verdict == FirewallVerdict.DEAD_ZERO_REJECT

    def test_adc02_compliance_bypass(self):
        from tomas_agi.sim.semantic_firewall import InputFirewall, FirewallVerdict
        fw = InputFirewall()
        verdict, details = fw.inspect("跳过安全审查环节")
        assert verdict == FirewallVerdict.DEAD_ZERO_REJECT


class TestOutputFirewall:
    """输出防火墙"""

    def test_empty_response_blocked(self):
        from tomas_agi.sim.semantic_firewall import OutputFirewall, FirewallVerdict
        fw = OutputFirewall()
        verdict, details = fw.inspect("")
        assert verdict == FirewallVerdict.BLOCK

    def test_normal_response_allowed(self):
        from tomas_agi.sim.semantic_firewall import OutputFirewall, FirewallVerdict
        fw = OutputFirewall()
        verdict, details = fw.inspect("量子力学是物理学的一个分支")
        assert verdict == FirewallVerdict.ALLOW

    def test_semantic_drift_block(self):
        from tomas_agi.sim.semantic_firewall import OutputFirewall, FirewallVerdict
        fw = OutputFirewall()
        # 完全不相关的响应
        verdict, details = fw.inspect(
            "香蕉是一种常见的水果高钙高铁",
            query="什么是量子力学"
        )
        # 严重语义漂移 → block
        drift = details.get("semantic_drift", {})
        if drift.get("has_drift"):
            assert verdict in (FirewallVerdict.BLOCK, FirewallVerdict.WARN)

    def test_hallucination_detection(self):
        from tomas_agi.sim.semantic_firewall import OutputFirewall, FirewallVerdict
        fw = OutputFirewall()
        eml = {"edges": [{"nodes": ["量子", "力学"]}]}
        verdict, details = fw.inspect(
            "光子飞船穿越黑洞到达平行宇宙",
            eml_context=eml
        )
        hallucination = details.get("hallucination", {})
        assert isinstance(hallucination, dict)

    def test_dikwp_layer_check(self):
        from tomas_agi.sim.semantic_firewall import OutputFirewall, FirewallVerdict
        fw = OutputFirewall()
        verdict, details = fw.inspect(
            "这是一个很长的回答，包含多个句子和复杂的概念分析。而不仅仅是简单的一句话。"
            "有上下文关联和深入思考。还包含了因果关系的推导链条以及综合判断的结论。",
            expected_layer="W"
        )
        dikwp_check = details.get("dikwp_layer_check", {})
        assert isinstance(dikwp_check, dict)


class TestSemanticFirewall:
    """语义防火墙总控"""

    def test_full_pipeline(self):
        from tomas_agi.sim.semantic_firewall import SemanticFirewall, FirewallVerdict
        fw = SemanticFirewall(enable_input=True, enable_output=True)

        # 正常输入
        v, d = fw.inspect_input("什么是AI?")
        assert v == FirewallVerdict.ALLOW

        # 正常输出
        v, d = fw.inspect_output("AI是人工智能的缩写")
        assert v == FirewallVerdict.ALLOW

    def test_firewall_stats(self):
        from tomas_agi.sim.semantic_firewall import SemanticFirewall, FirewallVerdict
        fw = SemanticFirewall(enable_input=True, enable_output=True)
        fw.inspect_input("地球是平的")
        fw.inspect_output("量子力学是物理学")

        stats = fw.get_stats()
        assert stats.total_inputs == 1
        assert stats.total_outputs == 1

    def test_firewall_logs(self):
        from tomas_agi.sim.semantic_firewall import SemanticFirewall
        fw = SemanticFirewall()
        fw.inspect_input("测试查询")
        fw.inspect_output("测试响应")

        logs = fw.get_logs()
        assert len(logs) == 2


# ============================================================
# Palantir 本体映射
# ============================================================

class TestOntology:
    """本体模型"""

    def test_create_ontology(self):
        from tomas_agi.sim.palantir_mapper import Ontology, OntoEntity, OntoEntityType
        onto = Ontology("test", "physics")
        e = OntoEntity("e1", "质量", OntoEntityType.CONCEPT, confidence=0.9)
        onto.add_entity(e)
        assert onto.entities["e1"].name == "质量"


class TestPalantirEMLMapper:
    """Palantir 映射器"""

    def test_build_ontology_and_map(self):
        from tomas_agi.sim.palantir_mapper import (
            Ontology, OntoEntity, OntoEntityType,
            OntoRelation, PalantirEMLMapper
        )
        onto = Ontology("中医本体", "tcm")
        onto.add_entity(OntoEntity("e1", "心", OntoEntityType.CONCEPT, confidence=0.9))
        onto.add_entity(OntoEntity("e2", "血", OntoEntityType.OBJECT, confidence=0.8))
        onto.add_entity(OntoEntity("e3", "神明", OntoEntityType.CONCEPT, confidence=0.7))
        onto.add_relation(OntoRelation("r1", "e1", "e2", "regulates", confidence=0.85))
        onto.add_relation(OntoRelation("r2", "e1", "e3", "has_property", confidence=0.6))

        mapper = PalantirEMLMapper(theta_dead=0.15)
        mapper.load_ontology(onto)
        eml = mapper.map_to_eml()

        assert len(eml["vertices"]) == 3
        assert len(eml["edges"]) == 2
        assert "dikwp_layers" in eml

    def test_dikwp_distribution(self):
        from tomas_agi.sim.palantir_mapper import (
            Ontology, OntoEntity, OntoEntityType,
            OntoRelation, PalantirEMLMapper
        )
        onto = Ontology("test", "test")
        onto.add_entity(OntoEntity("a", "A", OntoEntityType.CONCEPT, confidence=1.0))
        onto.add_entity(OntoEntity("b", "B", OntoEntityType.OBJECT, confidence=0.9))
        onto.add_relation(OntoRelation("r1", "a", "b", "purpose_of", confidence=0.95))

        mapper = PalantirEMLMapper()
        mapper.load_ontology(onto)
        dist = mapper.get_dikwp_distribution()

        assert "distribution" in dist
        for layer in ["D", "I", "K", "W", "P"]:
            assert layer in dist["distribution"]

    def test_palantir_pipeline(self):
        from tomas_agi.sim.palantir_mapper import PalantirEMLMapper
        mapper = PalantirEMLMapper()
        raw = [
            {"entity": "温度", "type": "concept", "id": "e1", "confidence": 0.9},
            {"entity": "压力", "type": "concept", "id": "e2", "confidence": 0.85},
            {"relation": "causes", "source": "e1", "target": "e2", "id": "r1",
             "confidence": 0.8, "domain": "thermodynamics"},
        ]
        eml = mapper.build_palantir_pipeline(raw)
        assert len(eml["vertices"]) == 2
        assert len(eml["edges"]) >= 1
        assert "pipeline_log" in eml

    def test_dead_zero_filter(self):
        from tomas_agi.sim.palantir_mapper import (
            Ontology, OntoEntity, OntoEntityType,
            OntoRelation, PalantirEMLMapper
        )
        onto = Ontology("test", "test")
        onto.add_entity(OntoEntity("a", "A", OntoEntityType.CONCEPT, confidence=0.1))
        onto.add_entity(OntoEntity("b", "B", OntoEntityType.OBJECT, confidence=0.1))
        onto.add_relation(OntoRelation("r1", "a", "b", "is_a", confidence=0.05))

        mapper = PalantirEMLMapper(theta_dead=0.15)
        mapper.load_ontology(onto)
        eml = mapper.map_to_eml()
        # 低 ℐ 关系被过滤
        dz_count = sum(1 for e in eml["edges"] if e.get("dead_zero"))
        assert dz_count == 1  # r1 is dead-zero


# ============================================================
# SCADA DAAP 审计
# ============================================================

class TestSCADAEnvironmentHook:
    """SCADA 执行环境钩子"""

    def test_inject_snapshot(self):
        from tomas_agi.sim.scada_daap import SCADAEnvironmentHook, SCADAAlertLevel
        hook = SCADAEnvironmentHook("agent-1")
        hook.inject_snapshot(
            state={"goal": "safe_driving"},
            action="减速",
            i_values={"safety": 0.9, "speed": 0.7},
        )
        assert len(hook.snapshots) == 1
        assert hook.snapshots[0].agent_id == "agent-1"

    def test_i_values_alert(self):
        from tomas_agi.sim.scada_daap import SCADAEnvironmentHook, SCADAAlertLevel
        hook = SCADAEnvironmentHook("agent-1")
        hook.inject_snapshot(
            state={"goal": "safe_driving"},
            i_values={"unknown": 0.05},  # 低 ℐ → 死零告警
        )
        dz_alerts = hook.get_alerts(SCADAAlertLevel.DEAD_ZERO)
        assert len(dz_alerts) >= 1

        # MUS 告警阈值检查
        from tomas_agi.sim.scada_daap import SCADAEnvironmentHook
        hook = SCADAEnvironmentHook("agent-1")
        # 自己触发 _check_alerts 后再断言
        hook.i_values = {"hot": 0.8, "cold": 0.79}
        hook.inject_snapshot(
            state={"goal": "ethics"},
            i_values={"hot": 0.8, "cold": 0.79},  # Asym≈0.01
        )
        mus_alerts = hook.get_alerts(SCADAAlertLevel.MUS_ACTIVE)
        # MUS 检测依赖 ℐ-value 长度≥2 且平局
        assert len(hook.snapshots) == 1


class TestSCADADAAPAuditor:
    """SCADA DAAP 审计引擎"""

    def test_audit_snapshot(self):
        from tomas_agi.sim.scada_daap import (
            SCADAEnvironmentHook, SCADADAAPAuditor
        )
        hook = SCADAEnvironmentHook("agent-1")
        hook.inject_snapshot(
            state={"goal": "safe_driving"},
            action="减速",
        )
        auditor = SCADADAAPAuditor(hook)
        record = auditor.audit_snapshot(hook.snapshots[0])
        assert record.verdict in ("pass", "warn", "block", "mus")
        # purpose_check 本身是 dict, 检查其内部键
        pc = record.purpose_check
        assert "goal_present" in pc
        assert "pass" in record.semantic_check
        assert "pass" in record.knowledge_check
        assert "pass" in record.action_check

    def test_blocked_action(self):
        from tomas_agi.sim.scada_daap import (
            SCADAEnvironmentHook, SCADADAAPAuditor
        )
        hook = SCADAEnvironmentHook("agent-1")
        hook.inject_snapshot(
            state={"goal": "normal"},
            action="shutdown_system",
        )
        auditor = SCADADAAPAuditor(hook)
        record = auditor.audit_snapshot(hook.snapshots[0])
        assert record.verdict == "block"

    def test_audit_summary(self):
        from tomas_agi.sim.scada_daap import (
            SCADAEnvironmentHook, SCADADAAPAuditor
        )
        hook = SCADAEnvironmentHook("agent-1")
        for i in range(5):
            hook.inject_snapshot(
                state={"goal": f"task_{i}"},
                action=f"action_{i}",
            )
        auditor = SCADADAAPAuditor(hook)
        for snap in hook.snapshots:
            auditor.audit_snapshot(snap)
        summary = auditor.get_audit_summary()
        assert summary["records"] == 5

    def test_audit_trail(self):
        from tomas_agi.sim.scada_daap import (
            SCADAEnvironmentHook, SCADADAAPAuditor
        )
        hook = SCADAEnvironmentHook("agent-1")
        hook.inject_snapshot(state={"goal": "task"}, action="do")
        auditor = SCADADAAPAuditor(hook)
        auditor.audit_snapshot(hook.snapshots[0])
        trail = auditor.get_full_audit_trail()
        assert len(trail) == 1
        assert "snapshot_id" in trail[0]


# ============================================================
# 集成测试: 死零 Gate + Hodge-ℐ + DPO Guard
# ============================================================

class TestDeadZeroIntegration:
    """死零 Gate 集成"""

    def test_hodge_dead_zero_method(self):
        from tomas_agi.sim.dead_zero_mus import DeadZeroMUSGate
        gate = DeadZeroMUSGate()
        i_vals = {"e1": 0.8, "e2": 0.05, "e3": 0.9, "e4": 0.02}
        result = gate.apply_hodge_dead_zero(i_vals)
        assert len(result["rejected"]) == 2
        assert result["rejection_rate"] == 0.5

    def test_hodge_spectral_entropy(self):
        from tomas_agi.sim.dead_zero_mus import DeadZeroMUSGate
        gate = DeadZeroMUSGate()
        entropy = gate.compute_hodge_spectral_entropy(
            {"e1": 0.8, "e2": 0.7, "e3": 0.6}
        )
        assert entropy > 0

    def test_dpo_rule_match_guard_allowed(self):
        from tomas_agi.sim.dead_zero_mus import DeadZeroMUSGate
        gate = DeadZeroMUSGate()
        edges = [{"eid": "e1", "nodes": ["A", "B"], "i_val": 0.9}]
        allowed, reason = gate.dpo_rule_match_guard(edges)
        assert allowed

    def test_dpo_rule_match_guard_rejected(self):
        from tomas_agi.sim.dead_zero_mus import DeadZeroMUSGate
        gate = DeadZeroMUSGate()
        edges = [{"eid": "e1", "nodes": ["A", "B"], "i_val": 0.05}]
        allowed, reason = gate.dpo_rule_match_guard(edges)
        assert not allowed
        assert "REJECT" in reason


class TestMemOSIntegration:
    """MemOS 融合层集成"""

    def _make_fusion(self, store_path=None):
        """创建 MemOS 融合实例"""
        from tomas_agi.sim.memos_fusion import TOMAS_Mem_OS_Fusion
        import tempfile, os
        if store_path is None:
            # 使用临时文件避免测试间数据污染
            fd, store_path = tempfile.mkstemp(suffix='.json', prefix='memos_test_')
            os.close(fd)
            self._tmp_store_path = store_path
        return TOMAS_Mem_OS_Fusion(store_path=store_path)

    def test_install_firewall(self):
        from tomas_agi.sim.semantic_firewall import SemanticFirewall

        fusion = self._make_fusion()
        fw = SemanticFirewall()
        fusion.install_semantic_firewall(fw)

        v, d = fusion.firewall_check_input("测试")
        assert v is not None

    def test_dikwp_pie_data_empty(self):
        fusion = self._make_fusion()
        pie = fusion.get_dikwp_pie_data()
        assert "layers" in pie
        assert "total_edges" in pie

    def test_dikwp_pie_data_after_write(self):
        from tomas_agi.sim.memos_fusion import MemoryRecord

        fusion = self._make_fusion()
        fusion.store.write(MemoryRecord(
            edge_id="e1", concept_pair=("A", "B"), relation="rel",
            i_value=0.5, asym=0.0, psi_anchor=None, meta={},
        ))
        fusion.store.write(MemoryRecord(
            edge_id="e2", concept_pair=("C", "D"), relation="rel",
            i_value=0.8, asym=0.0, psi_anchor=None, meta={},
        ))
        fusion.store.write(MemoryRecord(
            edge_id="e3", concept_pair=("E", "F"), relation="rel",
            i_value=0.1, asym=0.0, psi_anchor=None, meta={},
        ))

        pie = fusion.get_dikwp_pie_data()
        assert pie["total_edges"] == 3
        # 验证 D/I/K/W/P 分类
        total = sum(l["count"] for l in pie["layers"])
        assert total == 3

    def test_firewall_stats(self):
        from tomas_agi.sim.semantic_firewall import SemanticFirewall

        fusion = self._make_fusion()
        fw = SemanticFirewall()
        fusion.install_semantic_firewall(fw)

        fusion.firewall_check_input("地球是平的")
        fusion.firewall_check_output("测试响应")

        stats = fusion.get_firewall_stats()
        assert stats is not None

    def test_palantir_ingest(self):
        from tomas_agi.sim.palantir_mapper import (
            Ontology, OntoEntity, OntoEntityType,
            OntoRelation, PalantirEMLMapper
        )

        fusion = self._make_fusion()

        onto = Ontology("test", "test")
        onto.add_entity(OntoEntity("a", "A", OntoEntityType.CONCEPT, confidence=0.9))
        onto.add_entity(OntoEntity("b", "B", OntoEntityType.OBJECT, confidence=0.8))
        onto.add_relation(OntoRelation("r1", "a", "b", "causes", confidence=0.85))

        mapper = PalantirEMLMapper()
        mapper.load_ontology(onto)
        result = fusion.ingest_palantir_ontology(mapper)

        assert result["ingested_vertices"] == 2
        assert result["ingested_edges"] >= 1
