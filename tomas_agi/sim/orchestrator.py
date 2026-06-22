"""
TOMAS Orchestrator — Conductor 式多智能体编排层
====================================================

受 Sakana AI Fugu 启发（2026-06），将 TOMAS 从"翻译官+作家"二路路由
升级为动态多智能体编排：

  Query → Orchestrator（分析/分解）→ 动态调度 N 个专家智能体 → 合成响应

核心升级：
  1. 自适应任务分解：复杂查询自动拆为子任务
  2. 动态智能体选择：每次根据子任务特征选择最合适的智能体
  3. 自然语言协调：Orchestrator 用自然语言为每个智能体编写针对性指令
  4. 失败自愈：智能体失败时自动切换备选，不中断整个流程
  5. 两阶段训练接口：SFT（单步）→ RL（多轮工作流）

Author: Zhang Feng (inspired by Sakana AI Fugu)
Version: 1.0
Date: 2026-06-23
"""

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("tomas.orchestrator")


# ── 枚举定义 ────────────────────────────────────────────────────────────────────

class TaskComplexity(Enum):
    """任务复杂度"""
    SIMPLE = "simple"       # 单步，直接路由到单个智能体
    COMPOSITE = "composite"  # 可分解为多个子任务
    ITERATIVE = "iterative"  # 需要多轮迭代（代码调试、研究等）


class AgentRole(Enum):
    """智能体角色（受 Fugu TRINITY 启发，3 种角色动态分配）"""
    PRIMARY = "primary"     # 主执行者：直接处理子任务
    CRITIC = "critic"       # 评审者：检查 PRIMARY 输出，标记问题
    SYNTHESIZER = "synthesizer"  # 合成者：整合多智能体输出


# ── 数据结构 ────────────────────────────────────────────────────────────────────

@dataclass
class SubTask:
    """分解后的子任务"""
    id: str
    description: str
    task_type: str           # reason / code_gen / extract / fact_query / ...
    required_capabilities: List[str]
    dependencies: List[str] = field(default_factory=list)  # 依赖的其他 subtask id
    assigned_agent: Optional[str] = None
    result: Optional[str] = None
    critic_feedback: Optional[str] = None
    status: str = "pending"   # pending / running / done / failed


@dataclass
class OrchestrationPlan:
    """Orchestrator 生成的执行计划"""
    query: str
    complexity: TaskComplexity
    subtasks: List[SubTask]
    coordination_strategy: str   # "sequential" / "parallel" / "iterative"
    synthesis_instruction: str   # 给合成智能体的指令
    estimated_steps: int = 1


@dataclass
class OrchestrationResult:
    """编排执行结果"""
    query: str
    plan: OrchestrationPlan
    agent_outputs: Dict[str, str]    # agent_name → output
    synthesis: Optional[str] = None
    total_latency_ms: float = 0.0
    agents_used: List[str] = field(default_factory=list)
    fallback_used: bool = False
    trace: List[Dict] = field(default_factory=list)  # 执行追踪


# ── 智能体描述 ──────────────────────────────────────────────────────────────────

AGENT_PROFILES = {
    "translator": {
        "label": "翻译官（事实检索）",
        "role": "factual_retrieval",
        "best_for": ["fact_query", "definition", "lookup"],
        "capabilities": ["eml_graph_query", "fast_response", "high_precision"],
        "cost_level": "low",
        "latency_ms": 50,
    },
    "writer": {
        "label": "作家（创造性生成）",
        "role": "creative_generation",
        "best_for": ["open_ended", "brainstorm", "story", "explanation"],
        "capabilities": ["deep_reasoning", "long_form_generation", "nuanced_tone"],
        "cost_level": "high",
        "latency_ms": 3000,
    },
    "coder": {
        "label": "程序员（代码生成）",
        "role": "code_generation",
        "best_for": ["code_gen", "debug", "refactor", "test_gen"],
        "capabilities": ["code_syntax", "multi_language", "debugging"],
        "cost_level": "high",
        "latency_ms": 5000,
    },
    "mathematician": {
        "label": "数学家（数理推理）",
        "role": "mathematical_reasoning",
        "best_for": ["math", "proof", "calculation", "formal_logic"],
        "capabilities": ["symbolic_reasoning", "step_by_step", "formal_verification"],
        "cost_level": "medium",
        "latency_ms": 2000,
    },
    "researcher": {
        "label": "研究员（信息整合）",
        "role": "research_synthesis",
        "best_for": ["compare", "summarize", "literature_review", "multi_source"],
        "capabilities": ["information_integration", "source_comparison", "structured_output"],
        "cost_level": "medium",
        "latency_ms": 4000,
    },
    "critic": {
        "label": "评审员（质量把关）",
        "role": "quality_assurance",
        "best_for": ["verify", "fact_check", "consistency_check"],
        "capabilities": ["critical_thinking", "error_detection", "improvement_suggestion"],
        "cost_level": "low",
        "latency_ms": 1000,
    },
}


# ── 关键词 → 任务类型映射 ────────────────────────────────────────────────────────

_TASK_TYPE_KEYWORDS = {
    "code_gen": [
        "代码", "code", "函数", "function", "bug", "调试", "debug",
        "编写", "编程", "programming",
        "算法", "algorithm", "refactor", "重构", "test", "测试",
    ],
    "math": [
        "数学", "math", "证明", "prove", "计算", "calculate",
        "公式", "formula", "方程", "equation", "积分", "微分",
        "线性代数", "概率", "statistics",
    ],
    "fact_query": [
        "什么是", "what is", "是谁", "where is", "when did",
        "定义", "definition", "概念", "concept", "解释一下",
        "查一下", "告诉我", "请问",
    ],
    "compare": [
        "比较", "compare", "对比", "vs", "区别", "difference",
        "优缺点", "pros and cons", "更好", "better",
    ],
    "extract": [
        "提取", "extract", "总结", "summary", "归纳", "summarize",
        "从文中", "根据上文", "关键信息",
    ],
    "open_ended": [
        "你觉得", "what do you think", "如何看", "opinion",
        "创意", "creative", "想法", "idea", "建议", "suggest",
    ],
}


# ── Orchestrator 主体 ────────────────────────────────────────────────────────────

class TOMASOrchestrator:
    """
    TOMAS Conductor 式多智能体编排器

    受 Fugu/Conductor 启发：
      - 动态任务分解（而非固定 translator/writer 二路）
      - 自然语言协调指令（每个智能体收到针对性 prompt）
      - 自适应智能体选择（基于任务特征，而非固定规则）
      - 失败自愈（智能体失败时自动切换）

    与现有架构的关系：
      - 包装 token_bridge.InferenceEngine（翻译官+作家）
      - 包装 router.TOMASRouter（多模型路由）
      - 新增：任务分解 + 动态智能体编排
    """

    def __init__(
        self,
        router=None,          # TOMASRouter instance
        inference_engine=None,  # InferenceEngine instance
        enable_decomposition: bool = True,
        max_agents_per_query: int = 3,
        enable_critic: bool = True,
    ):
        self.router = router
        self.engine = inference_engine
        self.enable_decomposition = enable_decomposition
        self.max_agents_per_query = max_agents_per_query
        self.enable_critic = enable_critic
        self._decomposition_cache: Dict[str, OrchestrationPlan] = {}

        # 统计
        self.stats = {
            "total_queries": 0,
            "decomposed_queries": 0,
            "critic_triggered": 0,
            "fallback_used": 0,
            "agent_usage": {},   # agent_name → count
        }
        logger.info("[Orchestrator] 初始化完成 (decomposition=%s, critic=%s)",
                    enable_decomposition, enable_critic)

    # ── 主入口 ─────────────────────────────────────────────────────────────────

    def orchestrate(
        self,
        query: str,
        context: Optional[Dict] = None,
        force_agents: Optional[List[str]] = None,  # 强制使用指定智能体
    ) -> OrchestrationResult:
        """
        主导一次多智能体编排响应

        Args:
            query: 用户输入
            context: 额外上下文（concepts, edges, session_id 等）
            force_agents: 强制使用指定智能体（跳过自适应选择）

        Returns:
            OrchestrationResult
        """
        t0 = time.time()
        self.stats["total_queries"] += 1
        trace: List[Dict] = []

        # Step 1: 分析查询，生成执行计划
        plan = self._analyze_and_plan(query, force_agents)
        trace.append({"step": "plan", "complexity": plan.complexity.value,
                      "num_subtasks": len(plan.subtasks)})

        # Step 2: 执行计划（按依赖顺序）
        agent_outputs: Dict[str, str] = {}
        for subtask in plan.subtasks:
            subtask.assigned_agent = subtask.assigned_agent or self._select_agent(subtask)
            output, fallback = self._execute_subtask(subtask, context)
            agent_outputs[subtask.assigned_agent] = output
            subtask.result = output
            if fallback:
                self.stats["fallback_used"] += 1
            self.stats["agent_usage"][subtask.assigned_agent] = \
                self.stats["agent_usage"].get(subtask.assigned_agent, 0) + 1
            trace.append({
                "step": "execute",
                "subtask_id": subtask.id,
                "agent": subtask.assigned_agent,
                "status": subtask.status,
                "output_len": len(output) if output else 0,
            })

        # Step 3: Critic 评审（如果启用且任务复杂）
        if self.enable_critic and plan.complexity != TaskComplexity.SIMPLE:
            critic_output = self._run_critic(query, agent_outputs)
            if critic_output:
                self.stats["critic_triggered"] += 1
                agent_outputs["critic"] = critic_output
                trace.append({"step": "critic", "output_len": len(critic_output)})

        # Step 4: 合成最终响应
        synthesis = self._synthesize(query, plan, agent_outputs)
        trace.append({"step": "synthesis", "output_len": len(synthesis)})

        total_latency = (time.time() - t0) * 1000
        return OrchestrationResult(
            query=query,
            plan=plan,
            agent_outputs=agent_outputs,
            synthesis=synthesis,
            total_latency_ms=total_latency,
            agents_used=list(agent_outputs.keys()),
            fallback_used=any(t.status == "failed" for t in plan.subtasks),
            trace=trace,
        )

    # ── Step 1: 查询分析与计划生成 ────────────────────────────────────────────

    def _analyze_and_plan(self, query: str, force_agents: Optional[List[str]]) -> OrchestrationPlan:
        """
        分析查询，决定是简单路由还是任务分解

        升级点（vs 旧版 translator/writer 二路）：
          - 不再只用 confidence >= 0.5 硬阈值
          - 分析查询语义特征，决定复杂度
          - 复杂查询自动分解为多个子任务
        """
        if force_agents:
            # 强制模式：跳过分析，直接用指定智能体
            subtasks = [
                SubTask(
                    id=f"st_{i}",
                    description=f"由 {agent} 处理查询",
                    task_type="custom",
                    required_capabilities=[],
                    assigned_agent=agent,
                )
                for i, agent in enumerate(force_agents)
            ]
            return OrchestrationPlan(
                query=query,
                complexity=TaskComplexity.COMPOSITE,
                subtasks=subtasks,
                coordination_strategy="parallel",
                synthesis_instruction=f"综合 {len(force_agents)} 个智能体的回答",
            )

        # 1A. 任务类型识别
        task_type = self._detect_task_type(query)

        # 1B. 复杂度判断
        complexity = self._assess_complexity(query, task_type)

        if complexity == TaskComplexity.SIMPLE or not self.enable_decomposition:
            # 简单查询：单步，直接路由
            agent = self._map_task_to_agent(task_type, query)
            subtasks = [SubTask(
                id="st_0",
                description=query,
                task_type=task_type,
                required_capabilities=AGENT_PROFILES.get(agent, {}).get("capabilities", []),
                assigned_agent=agent,
            )]
            return OrchestrationPlan(
                query=query,
                complexity=TaskComplexity.SIMPLE,
                subtasks=subtasks,
                coordination_strategy="single",
                synthesis_instruction="",
            )

        if complexity == TaskComplexity.COMPOSITE:
            # 复合查询：分解
            subtasks = self._decompose_composite(query, task_type)
            return OrchestrationPlan(
                query=query,
                complexity=TaskComplexity.COMPOSITE,
                subtasks=subtasks,
                coordination_strategy="parallel" if all(not s.dependencies for s in subtasks) else "sequential",
                synthesis_instruction=self._generate_synthesis_instruction(query, subtasks),
                estimated_steps=len(subtasks) + 1,
            )

        # ITERATIVE: 多轮迭代
        return self._plan_iterative(query, task_type)

    def _detect_task_type(self, query: str) -> str:
        """识别查询的任务类型（基于关键词 + 启发式规则）"""
        query_lower = query.lower()
        scores: Dict[str, int] = {}
        for tt, keywords in _TASK_TYPE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in query_lower)
            if score > 0:
                scores[tt] = score
        if scores:
            return max(scores, key=scores.get)

        # 默认：根据查询长度判断
        if len(query) < 30:
            return "fact_query"
        return "open_ended"

    def _assess_complexity(self, query: str, task_type: str) -> TaskComplexity:
        """
        评估查询复杂度

        判断依据（受 Fugu 自适应路由启发）：
          - 多问题（有换行、分号、多个问号）→ COMPOSITE
          - 代码调试/研究类 → ITERATIVE
          - 单问题 → SIMPLE
        """
        # 多问题检测
        num_questions = query.count("？") + query.count("?")
        has_newline = "\n" in query or "\\n" in query
        has_comma_separator = "；" in query or ";" in query
        # 列举比较模式：比较 A、B、C 或 A vs B vs C
        has_enumeration = bool(re.search(r"[、,，]\s*[A-Za-z]", query)) or "vs" in query.lower() or "对比" in query or "比较" in query

        if num_questions > 1 or (has_newline and len(query) > 100) or has_comma_separator or has_enumeration:
            return TaskComplexity.COMPOSITE

        # 迭代任务检测
        iterative_keywords = ["调试", "debug", "迭代", "iterate", "多次", "一步一步",
                              "step by step", "研究", "research", "调查", "investigate"]
        if any(kw in query.lower() for kw in iterative_keywords):
            return TaskComplexity.ITERATIVE

        return TaskComplexity.SIMPLE

    def _map_task_to_agent(self, task_type: str, query: str) -> str:
        """将任务类型映射到最合适的智能体（自适应选择）"""
        mapping = {
            "code_gen": "coder",
            "math": "mathematician",
            "fact_query": "translator",
            "compare": "researcher",
            "extract": "researcher",
            "open_ended": "writer",
        }
        agent = mapping.get(task_type, "writer")

        # 检查该智能体是否可用（通过 router 判断）
        if self.router and agent not in self.router._available_backends:
            # 回退到 writer（DeepSeek，通常都可用）
            logger.info("[Orchestrator] %s 不可用，回退到 writer", agent)
            agent = "writer"

        return agent

    # ── 任务分解（Fugu 核心思想：动态拆任务）────────────────────────────────

    def _decompose_composite(self, query: str, task_type: str) -> List[SubTask]:
        """
        将复合查询分解为子任务

        这是 Fugu 的核心能力之一：不让单个模型处理所有子问题，
        而是拆开，每个子问题交给最合适的专家。

        当前实现：基于规则的分解（未来可升级为 LLM 辅助分解）
        """
        subtasks: List[SubTask] = []

        # 按换行符或分号分割
        parts = re.split(r"[；;\n]+", query)
        parts = [p.strip() for p in parts if p.strip()]

        if len(parts) <= 1:
            # 无法规则分解，作为单个任务交给 researcher（擅长整合）
            return [SubTask(
                id="st_0",
                description=query,
                task_type="compare",
                required_capabilities=AGENT_PROFILES["researcher"]["capabilities"],
                assigned_agent="researcher",
            )]

        for i, part in enumerate(parts[: self.max_agents_per_query]):
            part_type = self._detect_task_type(part)
            agent = self._map_task_to_agent(part_type, part)
            subtasks.append(SubTask(
                id=f"st_{i}",
                description=part,
                task_type=part_type,
                required_capabilities=AGENT_PROFILES.get(agent, {}).get("capabilities", []),
                assigned_agent=agent,
            ))

        return subtasks

    def _plan_iterative(self, query: str, task_type: str) -> OrchestrationPlan:
        """为迭代任务生成执行计划（ PRIMARY → CRITIC → PRIMARY ... ）"""
        subtasks = [
            SubTask(
                id="st_0_primary",
                description=query,
                task_type=task_type,
                required_capabilities=[],
                assigned_agent=self._map_task_to_agent(task_type, query),
            ),
            SubTask(
                id="st_1_critic",
                description=f"评审以下回答，标记问题：{query}",
                task_type="verify",
                required_capabilities=AGENT_PROFILES["critic"]["capabilities"],
                dependencies=["st_0_primary"],
                assigned_agent="critic",
            ),
        ]
        return OrchestrationPlan(
            query=query,
            complexity=TaskComplexity.ITERATIVE,
            subtasks=subtasks,
            coordination_strategy="iterative",
            synthesis_instruction="基于评审反馈改进回答",
            estimated_steps=3,
        )

    def _generate_synthesis_instruction(self, query: str, subtasks: List[SubTask]) -> str:
        """生成合成指令（Conductor 模式：为每个智能体编写针对性指令）"""
        agent_list = ", ".join(set(st.assigned_agent for st in subtasks))
        return (
            f"以下是多个专家智能体（{agent_list}）对不同子问题的回答。"
            f"请整合这些回答，生成一个完整、连贯、直接回答用户问题的响应。"
            f"如果存在不一致，请指出并给出你的判断。"
        )

    # ── Step 2: 执行子任务 ─────────────────────────────────────────────────────

    def _select_agent(self, subtask: SubTask) -> str:
        """为子任务选择最合适的智能体（如果尚未分配）"""
        if subtask.assigned_agent:
            return subtask.assigned_agent
        return self._map_task_to_agent(subtask.task_type, subtask.description)

    def _execute_subtask(
        self,
        subtask: SubTask,
        context: Optional[Dict],
    ) -> Tuple[str, bool]:
        """
        执行单个子任务，调用对应的智能体

        智能体调用优先级：
          1. router（如果可用且智能体对应某个模型后端）
          2. engine（InferenceEngine，翻译官/作家模式）
          3. 直接调用 LLM API（fallback）

        Returns:
            (output, used_fallback)
        """
        agent = subtask.assigned_agent
        prompt = subtask.description

        # 构造针对性的协调指令（Conductor 模式核心）
        coordinated_prompt = self._build_coordinated_prompt(subtask)

        fallback = False
        output = ""

        try:
            # 路径 1: 通过 router 调用（多模型支持）
            if self.router and agent in ("writer", "coder", "mathematician", "researcher"):
                task_type_map = {
                    "writer": "reason",
                    "coder": "code_gen",
                    "mathematician": "reason",
                    "researcher": "rag",
                }
                output = self.router.route(
                    task_type=task_type_map.get(agent, "reason"),
                    prompt=coordinated_prompt,
                    eml_ctx=context.get("eml_ctx") if context else None,
                )
            # 路径 2: 通过 engine 调用（翻译官/作家混合架构）
            elif self.engine and agent in ("translator", "writer"):
                # 使用 token_bridge 的推理引擎
                result = self.engine.run(coordinated_prompt)
                output = result.get("response", "") if isinstance(result, dict) else str(result)
            else:
                # Fallback: 直接调用（通过 router 的 fallback）
                if self.router:
                    output = self.router.route("fallback", coordinated_prompt)
                    fallback = True
                else:
                    output = f"[Orchestrator] 无法执行子任务：{agent} 不可用"
                    subtask.status = "failed"

            subtask.status = "done" if output else "failed"

        except Exception as e:
            logger.warning("[Orchestrator] 智能体 %s 执行失败: %s", agent, e)
            # 自愈：尝试 fallback
            try:
                if self.router:
                    output = self.router.route("fallback", coordinated_prompt)
                    fallback = True
                    subtask.status = "done"
                else:
                    subtask.status = "failed"
            except Exception:
                subtask.status = "failed"
                output = f"[{agent} 执行失败]"

        return output, fallback

    def _build_coordinated_prompt(self, subtask: SubTask) -> str:
        """
        为每个智能体构造针对性指令（Conductor 模式）

        这是 Fugu Conductor 的核心思想：
          不是简单地把用户查询转发给智能体，
          而是 Orchestrator 用自然语言给每个智能体写"工作说明"，
          包括：角色定义、输出格式、注意事项。
        """
        agent = subtask.assigned_agent
        profile = AGENT_PROFILES.get(agent, {})

        # 基础指令模板
        role_desc = profile.get("label", agent)
        capabilities = ", ".join(profile.get("capabilities", []))

        prompt = f"""【任务分配给：{role_desc}】

你的核心能力：{capabilities}

子任务描述：
{subtask.description}

要求：
- 充分发挥你作为 {role_desc} 的专业优势
- 回答要精确、有条理
- 如果信息不足，明确说明而非编造
"""
        # 根据角色加针对性指令
        if agent == "translator":
            prompt += "\n注意：这是一个事实性问题，请只基于已知知识回答，不要添加推测。"
        elif agent == "writer":
            prompt += "\n注意：这是一个开放性/创造性问题，可以充分发挥，给出有深度的回答。"
        elif agent == "coder":
            prompt += "\n注意：请给出完整、可运行的代码，并附上必要说明。"
        elif agent == "critic":
            prompt += "\n注意：请仔细审查以下内容，标记错误、不一致或遗漏，并给出改进建议。"

        return prompt

    # ── Step 3: Critic 评审 ───────────────────────────────────────────────────

    def _run_critic(self, query: str, agent_outputs: Dict[str, str]) -> Optional[str]:
        """运行 Critic 智能体评审输出质量"""
        if not agent_outputs:
            return None
        # 构造评审提示
        review_prompt = f"请评审以下回答的质量（准确性、完整性、一致性）：\n\n用户问题：{query}\n\n"
        for agent, output in agent_outputs.items():
            if agent != "critic":
                review_prompt += f"\n── {agent} 的回答 ──\n{output[:500]}\n"
        review_prompt += "\n请指出任何问题，并给出综合评分（1-10分）。"

        try:
            if self.router:
                return self.router.route("fallback", review_prompt)
        except Exception:
            pass
        return None

    # ── Step 4: 合成最终响应 ─────────────────────────────────────────────────

    def _synthesize(
        self,
        query: str,
        plan: OrchestrationPlan,
        agent_outputs: Dict[str, str],
    ) -> str:
        """
        合成多智能体输出为最终响应

        如果只有一个智能体输出：直接返回
        如果多个：用 synthesizer 模式整合
        """
        if len(agent_outputs) == 1:
            return list(agent_outputs.values())[0]

        # 多智能体输出：整合
        if plan.complexity == TaskComplexity.SIMPLE:
            return list(agent_outputs.values())[0]

        # 构造合成提示
        synthesis_prompt = f"{plan.synthesis_instruction}\n\n"
        for agent, output in agent_outputs.items():
            if agent != "critic":
                synthesis_prompt += f"\n── {AGENT_PROFILES.get(agent, {}).get('label', agent)} 的回答 ──\n{output}\n"

        if "critic" in agent_outputs:
            synthesis_prompt += f"\n── 评审意见 ──\n{agent_outputs['critic']}\n"

        synthesis_prompt += f"\n请给出最终回答，直接回应用户的问题：{query}"

        # 调用 synthesizer（通常是 writer/deepseek）
        try:
            if self.router:
                return self.router.route("reason", synthesis_prompt)
        except Exception:
            pass

        # 如果合成失败，返回所有输出的拼接
        return "\n\n---\n\n".join(agent_outputs.values())

    # ── 训练接口（Fugu 两阶段训练）────────────────────────────────────────────

    def sft_train_step(self, task: dict) -> dict:
        """
        SFT 训练步骤（单步任务）

        Args:
            task: {"query": ..., "task_type": ..., "expected_agent": ..., "expected_output": ...}

        Returns:
            {"loss": ..., "accuracy": ...}
        """
        # 占位：记录路由决策是否正确
        predicted_agent = self._map_task_to_agent(task["task_type"], task["query"])
        correct = predicted_agent == task.get("expected_agent", predicted_agent)
        return {
            "predicted_agent": predicted_agent,
            "expected_agent": task.get("expected_agent"),
            "correct": correct,
            "note": "SFT step: single-step task routing accuracy",
        }

    def rl_train_step(self, trajectory: dict) -> dict:
        """
        RL 训练步骤（多轮工作流）

        受 Fugu Conductor RL 训练启发：
          - 输入：一个完整多轮交互轨迹
          - 奖励：最终响应质量（由评估模型或人工标注）

        Args:
            trajectory: {
                "query": ...,
                "plan": [...],      # 执行的子任务序列
                "agent_outputs": [...],
                "final_quality_score": 0.0-1.0,  # 奖励信号
                "latency_ms": ...,
                "cost": ...,
            }

        Returns:
            {"policy_gradient": ..., "reward": ...}
        """
        score = trajectory.get("final_quality_score", 0.0)
        # 占位：更新路由策略（未来可实现为可学习参数）
        return {
            "reward": score,
            "note": "RL step: update orchestration policy based on trajectory reward",
        }

    # ── 统计与配置 ────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """返回编排器统计信息"""
        return dict(self.stats)

    def set_agent_enabled(self, agent_name: str, enabled: bool):
        """启用/禁用某个智能体"""
        # 占位：未来可实现动态智能体池管理
        pass

    def list_agents(self) -> List[dict]:
        """列出所有可用智能体"""
        return [
            {"name": name, "label": p["label"], "role": p["role"],
             "best_for": p["best_for"], "cost": p["cost_level"]}
            for name, p in AGENT_PROFILES.items()
        ]
