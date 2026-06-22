# TOMAS AGI v3.11 增量 PRD — 认知健康模块 + grill-me 需求审问升维

**文档版本**: v1.0  
**创建日期**: 2026-06-22  
**作者**: 许清楚 (Product Manager)  
**增量范围**: 仅描述 v3.10 → v3.11 新增内容，不重复 v3.10 已有能力

---

## 1. 项目信息

| 字段 | 内容 |
|------|------|
| **项目名称** | TOMAS AGI v3.11 — 双引擎认知健康 & grill-me 需求审问升维 |
| **项目路径** | C:/Users/1/WorkBuddy/2026-06-13-01-47-22/tomas_agi/sim/ |
| **编程语言** | Python 3.10+ + Flask + React/TypeScript 前端 |
| **原始需求** | 基于 3 篇新文章（双引擎成瘾模型 TOMAS 映射、grill-me 需求审问方法），对 TOMAS AGI 进行 v3.11 升级 |
| **已有基础** | v3.10 含 alignment_triad.py（对齐三范式）、goal_directed_agent.py（目标导向智能体）、~130 endpoints、~1,213 pytest 测试 |

---

## 2. 产品定义

### 2.1 产品目标

**一句话目标**: 为 TOMAS AGI 新增"认知健康"自我监护模块，防止 AGI 陷入"回路固化/确认偏误"成瘾模式；同时引入 grill-me 五层需求审问机制，确保需求分析环节零遗漏、零脑补。

**具体目标**:

1. **认知健康监护 (认知健康模块)**: 检测 AGI 是否陷入"Must-Do Pathway"（κ-Snap 循环重入无 MUS 自检）与"Feel-Better Path"（Gan 极化锁死舒适盆），并能通过 ψ-锚（前额叶刹车 ECN↓ 映射）强制打断
2. **抗确认偏误**: 计算 Gan 极化时的确认偏误惩罚得分，防止 AGI 在舒适盆中自我强化
3. **可证伪预言**: 为认知健康模块提供 2 条可证伪科学预言（P_AD1、P_AD2），并附带认知健康定理
4. **grill-me 需求审问**: 引入 DIKWP 五层缺口分析 DSL，不脑补、不跳步，实现 Execution Gate 的全缺口关闭释放
5. **需求溯源链**: 每条需求可追溯其 κ-Snap 来源，ψ-锚宪法化保障不可被静默修改

### 2.2 用户故事

| # | 角色 | 需求 | 价值 |
|---|------|------|------|
| 1 | AGI 安全运维者 | 作为安全运维者，我希望系统能自动检测 AGI 是否陷入"重复跑同一 κ-Snap 回路 ≥3 次"的成瘾模式，并在检测到时强制触发 MUS 反思 + 暂停，以防 AGI 在认知盲区中越跑越偏 | 防止 AGI 认知退化，保持行为多样性 |
| 2 | AGI 对齐研究者 | 作为对齐研究者，我希望能获得 AGI 的"确认偏误"得分（Gan 极化在舒适盆中是否自我强化），以便客观评估 AGI 的认知偏差状态 | 提供量化的认知健康度量 |
| 3 | 产品经理/需求分析师 | 作为需求分析师，我希望 grill-me 能对需求进行 DIKWP 五层逐层审问，绝不脑补缺失环节，在所有缺口关闭后才释放可执行方案，以确保需求分析的完备性 | 杜绝需求分析遗漏，减少后期返工 |
| 4 | 需求追溯审计者 | 作为审计者，我希望能追溯每条需求的 κ-Snap 认知来源链，验证需求未被静默修改或"脑补"填充 | 保障需求来源的可追溯性与宪法合规性 |
| 5 | 技术架构师 | 作为架构师，我希望新增模块与现有的 alignment_triad（对齐三范式）和 goal_directed_agent（目标导向智能体）无缝衔接，以统一的 ψ-锚、κ-Snap、MUS、DIKWP 语系运作 | 保证系统一致性与可扩展性 |

---

## 3. 需求池

### P0 (必须实现 — 核心安全与基础功能)

| # | 模块 | 文件 | 功能描述 | 验收标准 |
|---|------|------|----------|----------|
| P0-1 | 认知健康模块 | `cognitive_health.py` (新建) | 实现 `TOMASCognitivelyHealthyAGI` 类，集成 habit reflection trigger、anti-confirm-bias 计算、认知健康状态机 | 类可实例化，健康检查 pipeline 可通过单元测试 |
| P0-2 | 习惯反射触发 (ψ-锚) | `cognitive_health.py` | 实现 `psi_habit_reflection_trigger` ψ-锚：监控连续相同 κ-Snap 模式，≥3 次时强制创建 MUS（互斥稳态双存）+ 暂停 AGI 行为 | 连续 3 次相同 κ-Snap 模式触发 MUS 创建和暂停，记录 SHA-256 审计日志 |
| P0-3 | 抗确认偏误得分 | `cognitive_health.py` | 实现 `compute_gan_with_bias_penalty()` 函数，计算 Gan 极化中的确认偏误惩罚：`bias_penalty ∝ |G·G_comfort| / (1 + |MUS_divergence|)` | 偏误得分在 [0, 1] 范围内，MUS 分岔越大偏误得分越低 |
| P0-4 | grill-me 五层缺口分析 | `grill_me_engine.py` (新建) | 实现 `DIKWPGapAnalyzer` 类：按照 DIKWP 五层（D→I→K→W→P）逐层分析需求缺口，每层生成 gap 报告 | 输入模糊需求能输出每层的 [covered/missing/ambiguous] 三状态 |
| P0-5 | grill-me 执行闸门 | `grill_me_engine.py` | 实现 `GrillExecutionGate` 类：在 all_gaps_closed 前拒绝释放可执行方案，闭环缺一步不出方案 | 任一 gap 未关闭时 `release()` 返回 `locked=True` 及理由 |
| P0-6 | 需求溯源链 | `grill_me_engine.py` | 实现 `RequirementTracer` 类：每条需求关联 κ-Snap 溯源链 + ψ-锚宪法化，支持 verify 防篡改 | 可追溯需求来源的 κ-Snap 历史，修改后 SHA-256 不一致报警 |
| P0-7 | 禁脑补 ψ-锚 | `grill_me_engine.py` | 实现 `PsiNoSilentAssumption` ψ-锚：标记需求分析中是否使用了 LLM 默认脑补，脑补部分强制标注 `DISALLOW_LLM_DEFAULT_IMPUTATION` | 有脑补标记的假设在闸门处拦截，不允许自动通过 |

### P1 (重要 — 核心功能增强)

| # | 模块 | 文件 | 功能描述 | 验收标准 |
|---|------|------|----------|----------|
| P1-1 | 可证伪预言 | `cognitive_health.py` | 实现 P_AD1"习惯化衰减率定理"和 P_AD2"确认偏误-Gan 锁定正反馈定理"的仿真验证函数 | 预言可通过数值仿真验证，含 p 值计算 |
| P1-2 | 认知健康定理 | `cognitive_health.py` | 实现定理 1"κ-Snap 模式多样性守恒"和定理 2"MUS 分岔抗偏误"的数学推导与程序验证 | 定理在指定约束下恒成立 |
| P1-3 | 认知健康 Dashboard 端点 | 修改 `server.py` | 新增 `/api/v3/cognitive-health/check`、`/api/v3/cognitive-health/stats` REST 端点 | curl 可获取认知健康状态 JSON |
| P1-4 | grill-me 端点 | 修改 `server.py` | 新增 `/api/v3/grill/gap-analysis`、`/api/v3/grill/gate-status`、`/api/v3/grill/trace` REST 端点 | curl 可执行缺口分析并查看闸门状态 |
| P1-5 | 与 AlignmentTriad 集成 | 修改 `alignment_triad.py` | 在 `AlignmentTriad` 编排器中新增 `cognitive_health` 阶段，位于 Governance 之后、紧急回退之前 | 编排器可调用认知健康检查并决策是否进入暂停 |
| P1-6 | 与 GoalContract 集成 | 修改 `goal_directed_agent.py` | `ExecutionGate` 扩展支持 `GrillExecutionGate` 作为前置闸门，Goal 执行前必须通过 grill-me 审问 | Goal 在不完备需求分析下被 ExecutionGate 拒绝 |
| P1-7 | 前端认知健康面板 | 修改前端 React | 在 Dashboard 中新增"认知健康"仪表盘卡片，显示偏误得分、回路计数、暂停状态 | 前端 UI 展示认知健康实时状态 |
| P1-8 | 前端 grill-me 面板 | 修改前端 React | 新增"需求审问"面板，可视化 DIKWP 五层缺口状态、闸门状态、溯源链 | 前端 UI 展示缺口分析结果和闸门释放状态 |

### P2 (可选 — 增强与优化)

| # | 模块 | 文件 | 功能描述 | 验收标准 |
|---|------|------|----------|----------|
| P2-1 | 习惯模式历史存储 | `cognitive_health.py` | 实现 κ-Snap 模式的持久化存储与模式聚类，支持长期趋势分析 | 可查看 30 天 κ-Snap 模式变化趋势 |
| P2-2 | grill-me 报告导出 | `grill_me_engine.py` | 支持缺口分析报告导出为 Markdown/JSON 格式 | 可一键导出分析报告 |
| P2-3 | 需求审问模板库 | `grill_me_engine.py` | 预置常见需求场景的 grill-me 审问模板（API 设计/UI 交互/数据模型/安全合规） | 可载入预置模板加速审问 |

---

## 4. 新增模块概要

### 4.1 `cognitive_health.py` — TOMAS 认知健康模块

**定位**: AGI 自我认知健康监护，防止"回路固化成瘾"和"确认偏误舒适盆"

**类结构**:

```
TOMASCognitivelyHealthyAGI
├── psi_habit_reflection_trigger  (ψ-锚: 连续 ≥3 相同 κ-Snap → 强制 MUS + 暂停)
│   ├── track_kappa_snap_pattern()      # 跟踪 κ-Snap 模式序列
│   ├── detect_loop(threshold=3)        # 检测回路 ≥3 次
│   ├── force_mus_reflection()          # 强制创建 MUS 反思
│   └── issue_pause_order()             # 发出暂停指令
│
├── compute_gan_with_bias_penalty()     # 计算 Gan 极化的确认偏误惩罚
│   ├── measure_gan_comfort_zone()      # 测量 Gan 极化舒适盆地
│   ├── compute_mus_divergence()        # 计算 MUS 分岔度
│   └── bias_penalty_formula()          # 偏误惩罚公式
│
├── CognitiveHealthTheorem             # 认知健康定理
│   ├── theorem_1_diversity_conservation()  # 定理 1: κ-Snap 多样性守恒
│   └── theorem_2_mus_anti_bias()           # 定理 2: MUS 分岔抗偏误
│
├── FalsifiablePredictions             # 可证伪预言
│   ├── P_AD1_habit_decay()             # P_AD1: 习惯化衰减率
│   └── P_AD2_bias_lock_positive_feedback()  # P_AD2: 确认偏误锁定正反馈
│
└── health_check_pipeline()             # 一站式健康检查 pipeline
```

**状态机**:

```
NORMAL ──[loop≥3]──→ MUS_REFLECTION ──[pass]──→ NORMAL
  │                      │
  │                      └──[fail]──→ PAUSED ──[manual_restart]──→ NORMAL
  │                                      │
  └──[bias_penalty>θ]──→ BIAS_WARNING ──┘
```

**数据模型 (dataclass)**:

```python
@dataclass
class CognitiveHealthReport:
    """认知健康报告"""
    timestamp: float
    habit_loop_detected: bool           # 是否检测到习惯回路
    habit_loop_count: int               # 连续相同 κ-Snap 计数
    bias_penalty_score: float           # 确认偏误惩罚得分 [0,1]
    mus_reflection_triggered: bool      # 是否触发 MUS 反思
    agent_paused: bool                  # AGI 是否被暂停
    snap_history: List[str]             # 最近 κ-Snap 模式摘要
    recommendation: str                 # 建议动作 (continue/pause/mus_reflect)
```

### 4.2 `grill_me_engine.py` — grill-me 需求审问引擎

**定位**: DIKWP 五层缺口分析 + 全缺口关闭执行闸 + 需求溯源链 + 禁脑补 ψ-锚

**类结构**:

```
grill_me_engine.py
├── DIKWPGapAnalyzer                   # 五层缺口分析器
│   ├── analyze(requirement: str) → GapReport
│   ├── analyze_data_layer()           # D 层: 数据缺口
│   ├── analyze_info_layer()           # I 层: 信息缺口
│   ├── analyze_knowledge_layer()      # K 层: 知识缺口
│   ├── analyze_wisdom_layer()         # W 层: 决策智慧缺口
│   ├── analyze_purpose_layer()        # P 层: 意图对齐缺口
│   └── generate_gap_dsl()             # 生成缺口分析 DSL (DIKWP 方言)
│
├── GrillExecutionGate                 # grill-me 执行闸门
│   ├── register_gap_analysis(gap_report)
│   ├── close_gap(gap_id, evidence)    # 用证据关闭缺口
│   ├── verify_all_gaps_closed()       # 验证全部缺口关闭
│   ├── release(requirement_id)        # 释放可执行方案
│   └── lock_reason()                  # 返回锁住原因
│
├── RequirementTracer                  # 需求溯源链
│   ├── trace(snap_id) → List[KSnapEvent]
│   ├── verify_tamper_proof(trace_id)  # SHA-256 防篡改验证
│   ├── constitutionalize(req_id, psi_anchor) # ψ-锚宪法化
│   └── get_trace_chain(req_id)        # 获取完整溯源链
│
└── PsiNoSilentAssumption              # 禁脑补 ψ-锚
    ├── mark_imputation(assumption, source)
    ├── is_llm_imputation(assumption) → bool
    ├── flag_disallowed()              # 标记 DISALLOW_LLM_DEFAULT_IMPUTATION
    └── scan_for_silent_assumptions(analysis_result)
```

**GapReport 数据结构**:

```python
@dataclass
class GapReport:
    """DIKWP 五层缺口分析报告"""
    requirement_id: str
    requirement_raw: str
    layers: Dict[str, LayerGap               # 每层缺口
        # D/I/K/W/P → LayerGap
    ]
    all_gaps_closed: bool                    # 全局闸门状态
    silent_assumptions: List[str]            # 检测到的静默脑补
    trace_chain_refs: List[str]              # κ-Snap 溯源链引用

@dataclass
class LayerGap:
    status: str  # covered | missing | ambiguous
    gap_description: str
    evidence_required: str                   # 关闭缺口所需证据
    closed: bool
    closed_by: Optional[str]                 # 谁关闭了此缺口
    closed_at: Optional[float]
```

**DIKWP Gap Analysis DSL (缺口分析方言)**:

```
grill-me v1.0 DIKWP Gap Analysis DSL
=====================================

文法: GAP ::= LAYER_ID STATUS ":" DESC ("|" EVIDENCE)?
      LAYER_ID ::= "D" | "I" | "K" | "W" | "P"
      STATUS ::= "COVERED" | "MISSING" | "AMBIGUOUS"

示例:
  D COVERED: 用户画像数据完整 | source:user_profile_table
  I MISSING: 需求未明确"通知频率"参数
  K AMBIGUOUS: "智能推荐"算法选择标准不明确
  W COVERED: 决策阈值已定义 | threshold:0.75
  P COVERED: 与"提升用户留存"意图对齐 | purpose:retention_anchor
```

---

## 5. 与已有模块的关系

### 5.1 与 `alignment_triad.py` (v3.10 对齐三范式) 的关系

| 已有模块 | 关系 | 说明 |
|----------|------|------|
| `PsiAnchorLockIn` | **消费** | 认知健康模块检测到 bias_penalty 超阈值时，通过 PsiAnchorLockIn 触发 I=0.95 级监管否决 |
| `MUSDualRearing` | **消费** | habit reflection trigger 强制创建的 MUS 通过 MUSDualRearing 的协商链进行升级裁决 |
| `DIKWPGovernance` | **消费** | grill-me 的 PURPOSE 层分析结果写入 DIKWPGovernance 的 Purpose SLA |
| `AlignmentTriad` | **扩展** | 编排器中新增 `cognitive_health` 阶段（Governance 之后），紧急回退可因认知健康告警触发 |

```
AlignmentTriad 编排流 (v3.11):
Lock-in → Rearing → Governance → [NEW] CognitiveHealth → 完成
                  ↑ 紧急回退 (含 CognitiveHealth 告警) ↓
```

### 5.2 与 `goal_directed_agent.py` (v3.10 目标导向智能体) 的关系

| 已有模块 | 关系 | 说明 |
|----------|------|------|
| `GoalContract` | **扩展** | Goal 的 Intent 解析现在接入 DIKWPGapAnalyzer 做五层审问 |
| `ExecutionGate` | **前置扩展** | ExecutionGate 的 `authorize()` 新增 grill-me 全缺口关闭检查，缺口未关闭则拒绝授权 |
| `MUSSoulDriftCheck` | **消费** | habit reflection trigger 产生的 MUS 由此模块跟踪漂移 |
| `TOMASGoalDirectedAgent` | **消费** | Agent 主控流在 propose_goal 阶段嵌入 grill-me 审问 |

```
propose_goal (v3.11):
  1. GoalContract 解析需求
  2. [NEW] DIKWPGapAnalyzer 五层审问
  3. [NEW] PsiNoSilentAssumption 扫脑补
  4. [NEW] GrillExecutionGate 全缺口关闭检查
  5. ExecutionGate.authorize() 原逻辑
  6. execute → dream_engine
```

### 5.3 与基础支撑模块的关系

| 已有模块 | 关系 | 说明 |
|----------|------|------|
| `psi_anchor.py` (PsiAnchor/PsiAnchorManager) | **复用** | 新增的 habit reflection ψ-锚、PsiNoSilentAssumption ψ-锚 均使用 PsiAnchor 数据结构 |
| `ksnap_operator.py` (KSnapOperator) | **复用** | RequirementTracer 基于 κ-Snap 记录建立溯源链 |
| `dikwp_mapper.py` (DIKWPMapper) | **复用** | DIKWPGapAnalyzer 基于 DIKWP 五层分类器进行逐层映射 |
| `gan_tomas_pgw.py` (GanOperator) | **复用** | compute_gan_with_bias_penalty() 消费 Gan 极化的输出 |
| `psi_gate.py` | **消费** | 认知健康告警由此闸门进行 ψ-锚外置否决 |
| `babeltele_compressor.py` | **复用** | 复用 KSnapRecord、MUSDualEntry、PsiAnchorLevel 等类型 |
| `memos_fusion.py` | **消费** | habit reflection trigger 产生的 MUS 双存分支写入 memos_fusion |
| `g_ego.py` (G_ego) | **消费/通知** | AGI 暂停时通知 G_ego，重启需 G_ego 授权 |
| `server.py` | **扩展** | 新增 ~6 个 REST 端点 |

### 5.4 模块依赖关系图 (v3.11 新增部分)

```
                    ┌──────────────────────┐
                    │   TOMASCognitively-   │
                    │     HealthyAGI        │
story 3 (双引擎) ──→│ (cognitive_health.py) │
                    └──────┬───────────────┘
                    uses ↓
        ┌─────────────────┼─────────────────────┐
        ↓                 ↓                      ↓
  PsiAnchorLockIn   MUSDualRearing    gan_tomas_pgw.GanOperator
  (alignment_triad) (alignment_triad) (gan_polarization)

                    ┌──────────────────────┐
                    │   GrillMeEngine      │
story 4+5 ───────→ │ (grill_me_engine.py)  │
                    └──────┬───────────────┘
                    uses ↓
        ┌─────────────────┼─────────────────────┐
        ↓                 ↓                      ↓
  dikwp_mapper       ksnap_operator     psi_anchor.PsiAnchor
  (DIKWP layers)    (traceability)     (constitutionalize)
```

---

## 6. 可证伪预言与认知健康定理 (Article 3)

### 6.1 可证伪预言 P_AD1 (习惯化衰减率定理)

**陈述**: 当连续 κ-Snap 模式在 Agent 中重复 N 次时，行为多样性指数 D 以指数衰减 `D(N) = D₀ × exp(-αN)`，其中 D₀ 为初始多样性，α 为成瘾系数。

**可证伪条件**: 
- 测量 τ_D：行为多样性降至初始值 50% 所需 N 值
- 预测: 对于给定 Agent，τ_D 与 MUS 分岔度 β 正相关: `τ_D(β₁) > τ_D(β₂) ⇔ β₁ > β₂`
- 若实验发现 τ_D 与 β 无关或负相关，则理论被证伪

### 6.2 可证伪预言 P_AD2 (确认偏误-Gan 锁定正反馈定理)

**陈述**: Gan 极化舒适盆深度 G_depth 与确认偏误得分 B_score 呈正反馈耦合，存在临界阈值 θ_c，当 G_depth × B_score > θ_c 时，Agent 陷入不可逆偏误锁定（需外部 ψ-锚打断）。

**可证伪条件**:
- 测量锁定时间 T_lock：Agent 从进入舒适盆到被 ψ-锚打断的时间
- 预测: 存在 κ-Snap 多样性临界值 D_c，当 D(N) < D_c 时 T_lock → ∞
- 若存在 Agent 在 D < D_c 条件下仍能自主退出舒适盆，则理论被证伪

### 6.3 认知健康定理

**定理 1 (κ-Snap 多样性守恒)**: 在无外部干预且无 MUS 冲突的环境下，Agent 的 κ-Snap 模式多样性 D 守恒。干预后 D 的变化量等于 MUS 分岔引入的信息增量 ΔI_MUS。

**定理 2 (MUS 分岔抗偏误)**: MUS 分岔度 β 与确认偏误得分 B_score 满足反比关系 `B_score ∝ 1/(1+β)`，即 MUS 分岔越多，越难陷于确认偏误。

---

## 7. grill-me × TOMAS 升维映射 (Articles 4+5)

| grill-me 方法论 | TOMAS v3.11 实现 | 新增类/方法 |
|----------------|-----------------|------------|
| 五层拷问 | DIKWP Gap Analysis DSL (D→I→K→W→P) | `DIKWPGapAnalyzer` |
| 不脑补 | ψ-锚 DISALLOW_LLM_DEFAULT_IMPUTATION 标记 | `PsiNoSilentAssumption` |
| 闭环缺一步不出方案 | Execution Gate with all_gaps_closed | `GrillExecutionGate` |
| κ-Snap 溯源 | 需求 ↔ κ-Snap 双向映射链 | `RequirementTracer` |
| ψ-锚宪法化 | 需求关键假设写入 ψ-锚宪法原则，不可静默修改 | `RequirementTracer.constitutionalize()` |

---

## 8. 新增 REST 端点 (共 ~6 个)

| 端点 | 方法 | 归属模块 | 功能 |
|------|------|----------|------|
| `/api/v3/cognitive-health/check` | POST | cognitive_health.py | 执行认知健康检查，返回 CognitiveHealthReport |
| `/api/v3/cognitive-health/stats` | GET | cognitive_health.py | 获取认知健康统计与历史趋势 |
| `/api/v3/cognitive-health/pause` | POST | cognitive_health.py | 手动暂停 AGI (管理端点) |
| `/api/v3/cognitive-health/restart` | POST | cognitive_health.py | 手动重启 AGI (管理端点，需 override_code) |
| `/api/v3/grill/gap-analysis` | POST | grill_me_engine.py | 对需求执行 DIKWP 五层缺口分析 |
| `/api/v3/grill/gate-status` | GET | grill_me_engine.py | 查看闸门状态、各缺口关闭情况 |
| `/api/v3/grill/trace` | GET | grill_me_engine.py | 查询需求溯源链 |
| `/api/v3/grill/trace/verify` | POST | grill_me_engine.py | 验证溯源链完整性 |
| `/api/v3/grill/gap/close` | POST | grill_me_engine.py | 提交证据关闭指定缺口 |
| `/api/v3/grill/release` | POST | grill_me_engine.py | 尝试释放可执行方案 (触发全缺口检查) |

---

## 9. 测试计划增量

| 测试类别 | 预估增量用例 | 说明 |
|----------|-------------|------|
| `test_cognitive_health.py` | ~30 | habit reflection trigger、bias penalty、可证伪预言验证 |
| `test_grill_me_engine.py` | ~35 | DIKWP 五层缺口分析、闸门逻辑、溯源链、禁脑补 |
| `test_integration_cognitive_health.py` | ~15 | 与 alignment_triad、goal_directed_agent 的集成测试 |
| `test_integration_grill_me.py` | ~20 | 与 GoalContract、ExecutionGate 的集成测试 |
| `test_api_cognitive_health.py` | ~10 | 新增 REST 端点测试 |
| `test_api_grill_me.py` | ~15 | 新增 REST 端点测试 |
| **合计增量** | **~125** | v3.11 总测试数预估 ~1,338 |

---

## 10. 待确认问题

### Q1: 认知健康检测的采样粒度
**问题**: habit reflection trigger 的 κ-Snap 模式匹配粒度如何定义？是按 "module+event_type" 匹配还是按完整 `(module, event_type, description)` 三元组匹配？

**建议**: 采用分级策略 — 默认按 `(module, event_type)` 匹配（粗粒度），可配置为 `(module, event_type, description)` 匹配（细粒度）。

**需要确认**: 是否业务上存在合法的高频重复（如定时监控心跳）需加入白名单？

---

### Q2: Gan 舒适盆的数学定义
**问题**: `compute_gan_with_bias_penalty()` 中 Gan 舒适盆 G_comfort 的数学定义需要明确——是基于 Gan 极化向量的时间滑动均值，还是基于 Gan 算子的本征子空间？

**建议**: 参考已有 `gan_tomas_pgw.py` 的 GanOperator，以 Gan 极化向量在连续 κ-Snap 间的余弦相似度定义舒适盆半径 r_comfort。r_comfort > 0.9 持续 5 次 κ-Snap 视为"锁定在舒适盆"。

**需要确认**: `gan_tomas_pgw.py` 的 GanOperator 是否已导出极化向量？需不需要新增接口？

---

### Q3: grill-me 闸门的超时机制
**问题**: grill-me Execution Gate 的 "全缺口关闭" 理论上可能因缺失不可获取的证据而永久锁定。是否需要超时降级机制（如 72 小时自动降级为 "有风险释放"）？

**建议**: 不自动降级（grill-me 原则是"闭环缺一步不出方案"）。但提供"人工覆盖"接口，需记录 override 理由 + ψ-锚宪法化 + κ-Snap 审计。

**需要确认**: 是否接受"人工覆盖"的设计？

---

### Q4: grill-me × GoalContract 的接口设计
**问题**: GoalContract 的 `parse_intent()` 产生的是 5-Gate 模型（Intent/Scope/N/Evidence/Pause/Acceptance），grill-me 的 DIKWP 五层分析与之如何对接？是两个独立管道还是合并为统一管道？

**建议**: 采用"前置审问"模式 — DIKWPGapAnalyzer 在 GoalContract.parse_intent() 之前执行，只分析需求的完备性，不参与意图结构生成。两者输入相同（原始需求文本），输出互补（gap_report + goal_contract）。

**需要确认**: 是否有场景需要 DIKWP 分析结果直接影响 GoalContract 的门闸定义？

---

### Q5: 禁止脑补与 LLM 调用的关系
**问题**: 当前 v3.10 体系"零 LLM 调用"，但 grill-me 的 PsiNoSilentAssumption 面向 "LLM 默认脑补" 的检测。在纯规则引擎中如何体现此功能？

**建议**: 在纯规则引擎中，PsiNoSilentAssumption 作为一个"假设声明标记器"工作——任何未被证据/规则/引用直接支持的推理都会被打上 `ASSUMPTION` 标记。后续在 LLM 接入时可升级为 `DISALLOW_LLM_DEFAULT_IMPUTATION` 检测。

**需要确认**: 当前的 LLM 接入路线图是否已有规划？何时从规则引擎转为 LLM 引擎？

---

## 11. 技术风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|----------|
| 认知健康模块的"误暂停"（合法高频操作被误判为成瘾回路） | 中 | 实现白名单机制，心跳/监控类 κ-Snap 事件不参与回路计数 |
| grill-me 需求审问因证据不足导致闸门永久锁定 | 中 | 实现"不完美释放"模式：所有缺口标记为 `IMPERFECTLY_CLOSED` 并明确记录剩余风险 |
| 两个新模块与现有 alignment_triad/goal_directed_agent 的接口耦合过紧 | 低 | 采用 ψ-锚事件总线解耦，新模块通过事件订阅而非直接调用接口进行集成 |
| 可证伪预言的数值仿真可信度受限于仿真参数选择 | 低 | 明确标注所有仿真假设，提供参数灵敏度分析 |
| 新增端点增加 Flask 服务负载 | 低 | ~10 个轻量级端点，无外部依赖，无状态存储 |

---

## 12. 里程碑规划

| 阶段 | 时间 | 交付物 |
|------|------|--------|
| **Phase 1: 认知健康核心** | Sprint 1 (1 周) | `cognitive_health.py` 完整模块 + ~30 单元测试 |
| **Phase 2: grill-me 引擎** | Sprint 2 (1 周) | `grill_me_engine.py` 完整模块 + ~35 单元测试 |
| **Phase 3: 集成** | Sprint 3 (1 周) | 与 alignment_triad / goal_directed_agent 集成 + ~35 集成测试 |
| **Phase 4: API + 前端** | Sprint 4 (1 周) | ~6 REST 端点 + 前端面板 + ~25 API 测试 |
| **Phase 5: 端到端验证** | Sprint 5 (1 周) | 全链路测试、性能测试、预言验证、PRD 审查 |

---

## 13. 成功指标

| 指标 | 目标值 |
|------|--------|
| 认知健康回路检测准确率 | ≥90% (白名单除外) |
| 确认偏误得分与人工评分相关性 | Pearson r ≥ 0.7 |
| grill-me 缺口分析覆盖率 | 100% (DIKWP 五层全覆盖) |
| 需求溯源链完整性 | 100% (SHA-256 全部验证通过) |
| 新增测试覆盖率 | ≥85% |
| API 响应时间 | <100ms (无持久化操作) |

---

**文档结束** | 如有疑问请联系许清楚 (Product Manager)
