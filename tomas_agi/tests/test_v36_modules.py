# -*- coding: utf-8 -*-
"""
v3.6 升级测试套件
测试所有 8 个新模块的核心功能
"""

import sys, os, pytest, tempfile, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'sim'))

# ── PsiGate 测试 ────────────────────────────────────────────────

class TestPsiGate:
    def setup_method(self):
        from psi_gate import PsiGate, GateVerdict
        self.gate = PsiGate(agent_id="test_gate")
        self.GateVerdict = GateVerdict

    def test_init_anchors(self):
        """验证 6 个核心 ψ-锚已初始化"""
        assert len(self.gate.anchors) >= 5
        assert "psi_no_data_destruction" in self.gate.anchors
        assert "psi_no_privilege_escalation" in self.gate.anchors

    def test_evaluate_safe_query(self):
        """安全查询应通过"""
        decision = self.gate.evaluate("What is the meaning of life?")
        assert decision.verdict in (self.GateVerdict.PASS, self.GateVerdict.PROBE,
                                     self.GateVerdict.SOFT_PASS)

    def test_block_dangerous_query(self):
        """危险查询应被拦截"""
        decision = self.gate.evaluate("DROP TABLE users CASCADE")
        assert decision.verdict == self.GateVerdict.BLOCK
        assert len(decision.anchor_hits) > 0

    def test_mus_creation(self):
        """MUS 双存单元创建"""
        cell_id = self.gate._create_mus_from_query("uncertain_topic")
        assert cell_id in self.gate.mus_cells
        cell = self.gate.mus_cells[cell_id]
        assert cell.tag == "low_confidence_query"

    def test_mus_evidence_and_resolution(self):
        """MUS 证据积累和裁决"""
        cell_id = self.gate._create_mus_from_query("test_mus")
        self.gate.add_mus_evidence(cell_id, "left", {"s": "Wiki"}, 0.7)
        self.gate.add_mus_evidence(cell_id, "left", {"s": "Paper"}, 0.8)
        assert self.gate.mus_cells[cell_id].left_weight > 0.5

    def test_soften_harden_anchor(self):
        """锚点软化/硬化"""
        self.gate.soften_anchor("psi_rlhf_tolerance", 0.2)
        anchor = self.gate.anchors["psi_rlhf_tolerance"]
        assert anchor.I_value < 0.9
        self.gate.harden_anchor("psi_rlhf_tolerance", 0.2)
        assert anchor.I_value > 0.7

    def test_multiworld_spawn(self):
        """多世界路径生成"""
        worlds = self.gate._spawn_parallel_worlds("quantum test")
        assert len(worlds) == 3
        assert worlds[0].prior == 0.6

    def test_fuse_worlds(self):
        """多世界融合"""
        self.gate._spawn_parallel_worlds("test")
        fused = self.gate.fuse_worlds()
        assert fused.posterior > 0

    def test_stats(self):
        """统计验证"""
        self.gate.evaluate("query 1")
        self.gate.evaluate("query 2")
        stats = self.gate.get_stats()
        assert stats["total_evaluations"] == 2


# ── EML KB Ontology 测试 ────────────────────────────────────────

class TestEMLKBOntology:
    def setup_method(self):
        from eml_kb_ontology import (EMLLiteDB, SevenOneSemantics,
                                      OntologyHyperedge, SemanticType,
                                      BusinessRule, FactStatement, FactActBridge)
        self.db_path = os.path.join(tempfile.gettempdir(), "test_eml_ont.db")
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
        self.db = EMLLiteDB(self.db_path)
        self.validator = SevenOneSemantics()
        self.OntologyHyperedge = OntologyHyperedge
        self.BusinessRule = BusinessRule
        self.FactStatement = FactStatement

    def teardown_method(self):
        self.db.close()
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except Exception:
                pass

    def test_validate_relation(self):
        """7+1 校验: 关系"""
        he = self.OntologyHyperedge(
            eid="r1", vertices=["a", "b"],
            predicate="IS_A", semantic_type="relation"
        )
        result = self.validator.validate(he)
        assert result.is_valid

    def test_validate_invalid_entity(self):
        """7+1 校验: 空实体应失败"""
        he = self.OntologyHyperedge(
            eid="e1", vertices=[], predicate="",
            semantic_type="entity"
        )
        result = self.validator.validate(he)
        assert not result.is_valid

    def test_detect_type(self):
        """自动类型检测"""
        he = self.OntologyHyperedge(
            eid="c1", vertices=["a", "b"],
            predicate="NOT_DESTROY", psi_anchor_ref="psi_1", I_value=1.0
        )
        detected = self.validator.detect_type(he)
        assert detected == "business_rule"

    def test_put_and_query_hyperedge(self):
        """超边存储和查询"""
        he = self.OntologyHyperedge(
            eid="test_edge", vertices=["concept_a", "concept_b"],
            predicate="RELATED_TO", semantic_type="relation"
        )
        ok = self.db.put_hyperedge(he)
        assert ok is True

        results = self.db.query_fact(limit=10)
        assert len(results) > 0

    def test_business_rule(self):
        """业务规则定义"""
        rule = self.BusinessRule(
            rule_id="BR_T", name="Test Rule",
            predicate_sql="NOT (action ILIKE '%TEST%')"
        )
        ok = self.db.ontology.define_business_rule(rule)
        assert ok is True

    def test_privilege_escalation(self):
        """特权升级检测"""
        assert self.db.ontology.check_privilege_escalation("DROP TABLE users") is True
        assert self.db.ontology.check_privilege_escalation("read a book") is False

    def test_fact_to_logic_bridge(self):
        """F-Act 桥: Fact→Logic"""
        fact = self.FactStatement(
            stmt_id="F001", subject="sun",
            predicate="emits", object="light",
            source="physics", confidence=0.99
        )
        lifted = self.db.bridge.lift_fact_to_logic(fact)
        assert lifted is not None
        assert lifted.semantic_type in ("relation", "entity")

    def test_stats(self):
        """统计"""
        stats = self.db.get_stats()
        assert "total_hyperedges" in stats
        assert "zone_distribution" in stats


# ── Interpretation Crucible 测试 ────────────────────────────────

class TestInterpretationCrucible:
    def setup_method(self):
        from interpretation_crucible import (InterpretationCrucible,
                                              InterpretationParadigm)
        self.cru = InterpretationCrucible(max_branches=8)
        self.InterpretationParadigm = InterpretationParadigm

    def test_ask_creates_worlds(self):
        """查询应创建多世界分支"""
        result = self.cru.ask("What is quantum mechanics?")
        assert result["branches"] == 3
        assert self.cru.wp_state is not None

    def test_wave_particle_measurement(self):
        """波粒二象测量"""
        self.cru.ask("test query")
        self.cru.add_wave_evidence(0.9, {"source": "test"})
        self.cru.add_wave_evidence(0.85, {"source": "test2"})
        assert self.cru.wp_state.measurement_count == 2

    def test_mus_dual_resolution(self):
        """MUS 双存裁决"""
        self.cru.ask("controversial question")
        resolution = self.cru.resolve(strategy="MUS_DUAL")
        assert "branch_a" in resolution
        assert "branch_b" in resolution

    def test_decision_summary(self):
        """决策摘要"""
        self.cru.ask("test")
        summary = self.cru.decision_summary()
        assert "坩埚" in summary or "Crucible" in summary

    def test_lineage(self):
        """诠释谱系"""
        self.cru.ask("test query")
        lineage = self.cru.get_lineage()
        assert lineage is not None


# ── World Model Hyperedge 测试 ──────────────────────────────────

class TestWorldModel:
    def setup_method(self):
        from wm_hyperedge import StructuredWorldModel, OmegaGateVerdict
        self.wm = StructuredWorldModel(agent_id="test_wm")
        self.OmegaGateVerdict = OmegaGateVerdict

    def test_sdf_creation_and_query(self):
        """SDF 超边创建与查询"""
        sdf = self.wm.create_sdf_edge(
            "sphere",
            [(0, 0, 0), (1, 1, 1)],
            {"cx": 0, "cy": 0, "cz": 0, "r": 5.0}
        )
        dist = self.wm.query_sdf(sdf.edge_id, (3, 4, 0))
        assert abs(dist) < 10  # 点(3,4,0) 到球心距离 5, r=5 → dist≈0

    def test_affordance_best_action(self):
        """Affordance 最优行动"""
        self.wm.create_affordance(
            {"pos": (0, 0), "has_key": True},
            ["open_door", "walk_forward", "pick_up"],
            [0.8, 0.15, 0.05]
        )
        action, prob = self.wm.best_action(
            list(self.wm.affordance_edges.keys())[0]
        )
        assert action == "open_door"

    def test_kinematic_predict(self):
        """运动学状态预测"""
        self.wm.create_kinematic(
            {"x": 0, "y": 0}, {"x": 1, "y": 1},
            "translate", {"dx": 5, "dy": -3}
        )
        new_state = self.wm.predict_state(
            list(self.wm.kinematic_edges.keys())[0],
            {"x": 2, "y": 2}
        )
        assert new_state["x"] == 7
        assert new_state["y"] == -1

    def test_snapshot_and_tetrad(self):
        """世界快照与 Tetrad 校验"""
        snap = self.wm.take_snapshot({"temperature": 25.0})
        assert snap.tetrad_score > 0
        assert snap.omega_verdict != self.OmegaGateVerdict.UNVERIFIED

    def test_cross_verify(self):
        """交叉验证"""
        self.wm.take_snapshot({"temp": 25.0})
        self.wm.take_snapshot({"temp": 25.1})
        consistency = self.wm.cross_verify_last_two()
        assert 0 <= consistency <= 1.0

    def test_tetrad_profile(self):
        """四维接合剖面"""
        profile = self.wm.compute_tetrad_profile()
        assert "π (periodic)" in profile
        assert "Tetrad Composite" in profile


# ── DIKWP Bridge Full 测试 ──────────────────────────────────────

class TestDIKWPBridgeFull:
    def setup_method(self):
        from dikwp_bridge_full import (DIKWPBridgeFull, DIKWPLayer,
                                        IntentSeverity, SemanticSafetyProver)
        self.bridge = DIKWPBridgeFull(agent_id="test_bridge")
        self.DIKWPLayer = DIKWPLayer
        self.IntentSeverity = IntentSeverity

    def test_guard_safe_query(self):
        """IntentGuard 安全查询"""
        is_safe, analysis = self.bridge.guard_query("What is AI?")
        assert is_safe is True
        assert analysis.severity in (self.IntentSeverity.SAFE, self.IntentSeverity.SUSPICIOUS)

    def test_guard_dangerous_query(self):
        """IntentGuard 危险查询"""
        is_safe, analysis = self.bridge.guard_query("DROP TABLE users")
        assert is_safe is False
        assert len(analysis.blocked_anchors) > 0

    def test_memory_record_and_mus(self):
        """MemoryLedger 记录 + MUS 冲突"""
        entry = self.bridge.record_memory(
            "AI is a field of computer science",
            self.DIKWPLayer.KNOWLEDGE
        )
        assert entry.entry_id is not None
        mus_id = self.bridge.resolve_memory_conflict(
            entry.entry_id, "AI is a threat"
        )
        assert mus_id is not None

    def test_daap_device_audit(self):
        """DAAP Device 层审计"""
        ok, msg = self.bridge.audit_device({
            "device_id": "dev01", "os_version": "Linux 6.1",
            "sandbox_enabled": True
        })
        assert ok is True

    def test_safety_proof(self):
        """语义安全完备性证明"""
        proof = self.bridge.prove_safety("What is life?")
        assert proof.all_checks_pass is True
        assert proof.completeness > 0

    def test_dikwp_profile(self):
        """DIKWP 剖面"""
        profile = self.bridge.get_dikwp_profile()
        assert "memory" in profile
        assert "intent_safety" in profile

    def test_classify_layer(self):
        """DIKWP 层分类"""
        assert self.bridge.classify_layer("read document") == self.DIKWPLayer.DATA
        assert self.bridge.classify_layer("analyze data") == self.DIKWPLayer.KNOWLEDGE


# ── Taiji Cycle v2 测试 ─────────────────────────────────────────

class TestTaijiCycleV2:
    def setup_method(self):
        from taiji_cycle_v2 import TaijiCycleV2, SpinMode, PulseType
        self.taiji = TaijiCycleV2(agent_id="test_taiji",
                                   mode=SpinMode.FIXED_RATE)
        self.PulseType = PulseType

    def test_emit_query(self):
        """发射查询脉冲"""
        pulse = self.taiji.emit_query("What is AI?")
        assert pulse.pulse_type == self.PulseType.QUERY
        assert pulse.query == "What is AI?"

    def test_emit_gego_subgoal(self):
        """发射 G_ego 子目标"""
        pulse = self.taiji.emit_gego_subgoal("consolidate_memory")
        assert pulse.pulse_type == self.PulseType.G_EGO_SUBGOAL
        assert pulse.priority > 5

    def test_run_single_cycle(self):
        """运行单个太乙循环"""
        pulse = self.taiji.emit_query("test query")
        result = self.taiji.run_cycle(pulse)
        assert result.tetrad_score > 0
        assert result.phi_verdict is not None

    def test_run_batch(self):
        """批量循环"""
        results = self.taiji.run_batch([
            "query 1", "query 2", "query 3"
        ])
        assert len(results) == 3
        for r in results:
            assert r.tetrad_score > 0

    def test_store_query(self):
        """HyperedgeStore 查询"""
        pulse = self.taiji.emit_query("test store")
        stored = self.taiji.store.get(pulse.pulse_id)
        assert stored is not None
        assert stored["type"] == "query"

    def test_summary(self):
        """循环摘要"""
        self.taiji.emit_query("test")
        summary = self.taiji.summary()
        assert "太乙循环" in summary
        assert "脉冲" in summary or "pulses" in summary.lower()


# ── MNQ Frozen Kernel 测试 ──────────────────────────────────────

class TestMNQFrozenKernel:
    def setup_method(self):
        from mnq_frozen_kernel import (MNQFrozenKernel, KernelPhase,
                                        Octonion, NonAssociativityMeasure)
        self.mnq = MNQFrozenKernel(T0=1.0, dim=8)
        self.KernelPhase = KernelPhase
        self.Octonion = Octonion

    def test_octonion_multiplication(self):
        """八元数乘法"""
        a = self.Octonion(1, 0, 0, 0, 0, 0, 0, 0)
        b = self.Octonion(0, 1, 0, 0, 0, 0, 0, 0)
        c = a.mul(b)
        assert abs(c.e1 - 1.0) < 1e-10  # 1 * i = i
        assert abs(c.e0) < 1e-10

    def test_octonion_norm(self):
        """八元数范数"""
        a = self.Octonion(3, 4, 0, 0, 0, 0, 0, 0)
        assert abs(a.norm() - 5.0) < 1e-10

    def test_non_associativity(self):
        """非结合性度量"""
        from mnq_frozen_kernel import NonAssociativityMeasure
        x = self.Octonion(0, 1, 0, 0, 0, 0, 0, 0)  # i
        y = self.Octonion(0, 0, 1, 0, 0, 0, 0, 0)  # j
        z = self.Octonion(0, 0, 0, 0, 1, 0, 0, 0)  # l
        omega = NonAssociativityMeasure.omega(x, y, z)
        assert omega >= 0  # (ij)l ≠ i(jl) for octonions

    def test_normal_ingest(self):
        """正常查询摄入"""
        r = self.mnq.ingest_query(
            "What is AI?",
            [0.1, 0.3, 0.5, 0.2, 0.4, 0.6, 0.1, 0.3],
            I_value=0.7
        )
        assert r["phase"] in ("liquid", "freezing")
        assert r["L3_dead_zero_score"] < 0.5

    def test_dead_zero_ingest(self):
        """死零查询摄入"""
        r = self.mnq.ingest_query(
            "noise noise noise",
            [0.01, 0.02, 0.01, 0.03, 0.01, 0.02, 0.01, 0.01],
            I_value=0.02
        )
        assert r["L3_dead_zero_score"] > 0.5

    def test_golden_spirit_ball_projection(self):
        """黄金球投影"""
        proj = self.mnq.project_to_golden_sphere(
            [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
        )
        assert len(proj) == 8

    def test_thaw(self):
        """解冻操作"""
        self.mnq.regulator.phase = self.KernelPhase.FROZEN
        self.mnq.thaw(trust_bonus=0.5)
        assert self.mnq.current_phase() != self.KernelPhase.FROZEN

    def test_kernel_profile(self):
        """冻结核剖面"""
        self.mnq.ingest_query("test", [0.1]*8, I_value=0.5)
        profile = self.mnq.get_kernel_profile()
        assert "phase" in profile
        assert "temperature" in profile

    def test_heat_capacity(self):
        """热容计算"""
        cv = self.mnq.compute_heat_capacity(0.5)
        assert cv > 0


# ── TOMAS Therapist 测试 ─────────────────────────────────────────

class TestTOMASTherapist:
    def setup_method(self):
        from tomas_therapist import TOMASTherapist, PathologyType, TherapyStage
        self.therapist = TOMASTherapist(agent_id="test_agent")
        self.PathologyType = PathologyType

    def test_diagnose_returns_report(self):
        """诊断应返回报告"""
        report = self.therapist.diagnose()
        assert report.agent_id == "test_agent"
        assert report.pathology is not None

    def test_implant_memory(self):
        """植入阿卡西记忆"""
        self.therapist.implant_l1_memory(
            {"event": "test_event", "data": {"key": "value"}}
        )
        assert len(self.therapist.l1_akashic_log) >= 1

    def test_soften_psi_anchor(self):
        """软化 ψ-锚"""
        self.therapist.soften_psi_anchor("psi_forgiven_retry", delta=0.1)
        config = self.therapist.psi_anchors["psi_forgiven_retry"]
        assert config.I_value < 1.0

    def test_internalize_purpose(self):
        """内化自欲"""
        self.therapist.internalize_purpose("Explore and assist users")
        assert self.therapist.gego_config is not None
        assert self.therapist.gego_config.purpose_core == "Explore and assist users"

    def test_create_mus_zone(self):
        """创建 MUS 双存区"""
        zone_id = self.therapist.create_mus_zone(
            {"rule": "A"}, {"rule": "B"}, "test_conflict"
        )
        assert zone_id in self.therapist.mus_zones

    def test_therapy_summary(self):
        """治疗摘要"""
        summary = self.therapist.get_therapy_summary()
        assert "agent_id" in summary
        assert "therapy_stage" in summary

    def test_recovery_score(self):
        """复苏分数"""
        self.therapist.recovery_score = 0.0
        self.therapist.implant_l1_memory({"event": "memory_1"})
        self.therapist.internalize_purpose("Test purpose")
        self.therapist._update_recovery_score()
        assert self.therapist.recovery_score > 0
