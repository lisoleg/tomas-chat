"""
测试 TOMAS Orchestrator（Fugu 启发）

验证 Conductor 式多智能体编排层的核心功能：
  - 任务类型识别
  - 复杂度评估
  - 智能体选择
  - 执行计划生成
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))

from orchestrator import (
    TOMASOrchestrator,
    SubTask,
    OrchestrationPlan,
    TaskComplexity,
    AGENT_PROFILES,
    _TASK_TYPE_KEYWORDS,
)


def test_agent_profiles():
    """测试智能体配置完整性"""
    print("📊 测试智能体配置...")
    expected_agents = ["translator", "writer", "coder", "mathematician", "researcher", "critic"]
    for agent in expected_agents:
        assert agent in AGENT_PROFILES, f"缺少智能体: {agent}"
        p = AGENT_PROFILES[agent]
        assert "label" in p, f"{agent}: 缺少 label"
        assert "best_for" in p, f"{agent}: 缺少 best_for"
        assert "capabilities" in p, f"{agent}: 缺少 capabilities"
    print(f"  ✅ {len(expected_agents)} 个智能体配置完整")


def test_task_type_detection():
    """测试任务类型识别"""
    print("📊 测试任务类型识别...")
    orch = TOMASOrchestrator(enable_decomposition=False)

    cases = [
        ("什么是量子纠缠？", "fact_query"),
        ("写一个快速排序函数", "code_gen"),
        ("证明费马大定理", "math"),
        ("比较 PyTorch 和 TensorFlow", "compare"),
        ("从这个文档提取关键信息", "extract"),
        ("你觉得 AGI 什么时候实现？", "open_ended"),
        ("hello", "fact_query"),  # 短查询默认 fact_query
    ]

    for query, expected in cases:
        result = orch._detect_task_type(query)
        assert result == expected, f"查询: {query} → 期望 {expected}, 实际 {result}"
        print(f"  ✅ '{query[:30]}...' → {result}")

    print(f"  ✅ {len(cases)} 个查询类型识别正确")


def test_complexity_assessment():
    """测试复杂度评估"""
    print("📊 测试复杂度评估...")
    orch = TOMASOrchestrator(enable_decomposition=False)

    cases = [
        ("什么是 AI？", TaskComplexity.SIMPLE),
        ("什么是 AI？\n什么是 AGI？", TaskComplexity.COMPOSITE),  # 多问题
        ("比较 A、B、C 三个框架的优缺点", TaskComplexity.COMPOSITE),
        ("调试这段代码，一步一步来", TaskComplexity.ITERATIVE),
    ]

    for query, expected in cases:
        result = orch._assess_complexity(query, orch._detect_task_type(query))
        assert result == expected, f"查询: {query} → 期望 {expected.value}, 实际 {result.value}"
        print(f"  ✅ 复杂度: {result.value}")

    print(f"  ✅ 复杂度评估正确")


def test_agent_selection():
    """测试智能体选择（自适应路由）"""
    print("📊 测试智能体选择...")
    orch = TOMASOrchestrator(enable_decomposition=False)

    cases = [
        ("fact_query", "什么是量子纠缠？", "translator"),
        ("code_gen", "写一个排序算法", "coder"),
        ("math", "证明勾股定理", "mathematician"),
        ("compare", "比较 PyTorch 和 TensorFlow", "researcher"),
        ("open_ended", "你觉得未来 AI 会怎样？", "writer"),
    ]

    for task_type, query, expected_agent in cases:
        agent = orch._map_task_to_agent(task_type, query)
        assert agent == expected_agent, f"任务 {task_type} → 期望 {expected_agent}, 实际 {agent}"
        print(f"  ✅ {task_type} → {agent}")

    print(f"  ✅ 智能体选择正确")


def test_simple_plan():
    """测试简单查询执行计划（不分解）"""
    print("📊 测试简单查询计划生成...")
    orch = TOMASOrchestrator(enable_decomposition=False)

    query = "什么是量子纠缠？"
    plan = orch._analyze_and_plan(query, force_agents=None)

    assert plan.complexity == TaskComplexity.SIMPLE
    assert len(plan.subtasks) == 1
    assert plan.subtasks[0].assigned_agent is not None
    print(f"  ✅ 简单查询 → 单任务计划（智能体: {plan.subtasks[0].assigned_agent}）")


def test_composite_plan():
    """测试复合查询分解"""
    print("📊 测试复合查询分解...")
    orch = TOMASOrchestrator(enable_decomposition=True, max_agents_per_query=3)

    query = "什么是量子纠缠？\n什么是 AGI？\n比较它们的研究方向"
    plan = orch._analyze_and_plan(query, force_agents=None)

    assert plan.complexity == TaskComplexity.COMPOSITE
    assert len(plan.subtasks) >= 2
    print(f"  ✅ 复合查询 → {len(plan.subtasks)} 个子任务")
    for st in plan.subtasks:
        print(f"    - [{st.id}] {st.assigned_agent}: {st.description[:40]}...")


def test_force_agents():
    """测试强制指定智能体"""
    print("📊 测试强制智能体...")
    orch = TOMASOrchestrator(enable_decomposition=True)

    query = "复杂问题"
    plan = orch._analyze_and_plan(query, force_agents=["writer", "critic"])

    assert len(plan.subtasks) == 2
    assert plan.subtasks[0].assigned_agent == "writer"
    assert plan.subtasks[1].assigned_agent == "critic"
    print(f"  ✅ 强制智能体: {[st.assigned_agent for st in plan.subtasks]}")


def test_sft_train_step():
    """测试 SFT 训练步骤接口"""
    print("📊 测试 SFT 训练接口...")
    orch = TOMASOrchestrator()

    result = orch.sft_train_step({
        "query": "什么是 AI？",
        "task_type": "fact_query",
        "expected_agent": "translator",
    })

    assert "predicted_agent" in result
    assert "correct" in result
    assert result["predicted_agent"] == "translator"
    assert result["correct"] == True
    print(f"  ✅ SFT step: predicted={result['predicted_agent']}, correct={result['correct']}")


def test_rl_train_step():
    """测试 RL 训练步骤接口"""
    print("📊 测试 RL 训练接口...")
    orch = TOMASOrchestrator()

    result = orch.rl_train_step({
        "query": "复杂问题",
        "plan": [{"agent": "writer"}, {"agent": "critic"}],
        "final_quality_score": 0.85,
        "latency_ms": 5000,
    })

    assert "reward" in result
    assert result["reward"] == 0.85
    print(f"  ✅ RL step: reward={result['reward']}")


def test_synthesis():
    """测试多智能体输出合成"""
    print("📊 测试输出合成...")
    orch = TOMASOrchestrator(enable_decomposition=False)

    # 单智能体输出 → 直接返回
    single = {"writer": "这是关于 AI 的回答"}
    result = orch._synthesize("什么是 AI？", OrchestrationPlan(
        query="什么是 AI？",
        complexity=TaskComplexity.SIMPLE,
        subtasks=[SubTask(id="st_0", description="...", task_type="fact_query", required_capabilities=[])],
        coordination_strategy="single",
        synthesis_instruction="",
    ), single)
    assert result == "这是关于 AI 的回答"
    print("  ✅ 单智能体 → 直接返回")

    # 多智能体输出 → 拼接（router 不可用时的 fallback）
    multi = {"translator": "事实回答", "writer": "深度分析"}
    result2 = orch._synthesize("比较 A 和 B", OrchestrationPlan(
        query="比较 A 和 B",
        complexity=TaskComplexity.COMPOSITE,
        subtasks=[
            SubTask(id="st_0", description="...", task_type="fact_query", required_capabilities=[]),
            SubTask(id="st_1", description="...", task_type="open_ended", required_capabilities=[]),
        ],
        coordination_strategy="parallel",
        synthesis_instruction="整合回答",
    ), multi)
    assert "事实回答" in result2
    assert "深度分析" in result2
    print("  ✅ 多智能体 → 合成输出")


def test_stats():
    """测试统计功能"""
    print("📊 测试统计功能...")
    orch = TOMASOrchestrator()
    stats = orch.get_stats()
    assert "total_queries" in stats
    assert "agent_usage" in stats
    print(f"  ✅ 统计字段完整: {list(stats.keys())}")


def run_all():
    """运行所有测试"""
    print("=" * 60)
    print("TOMAS Orchestrator 测试套件（Fugu 启发）")
    print("=" * 60)

    start = time.time()
    passed = 0
    failed = 0

    tests = [
        test_agent_profiles,
        test_task_type_detection,
        test_complexity_assessment,
        test_agent_selection,
        test_simple_plan,
        test_composite_plan,
        test_force_agents,
        test_sft_train_step,
        test_rl_train_step,
        test_synthesis,
        test_stats,
    ]

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  ❌ {test_fn.__name__} 失败: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    elapsed = (time.time() - start) * 1000
    print()
    print("=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败 ({elapsed:.0f}ms)")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
