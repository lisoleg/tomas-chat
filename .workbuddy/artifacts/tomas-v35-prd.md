# TOMAS AGI v3.5 增量 PRD

> 版本：v0.1 | 作者：许清楚（Xu）| 日期：2026-06-21 | 基线：v3.4

---

## 1. 产品目标

**一句话：** v3.5 完成 MNQ-Deep 训练体系落地 + 三层安全防御上线 + v3.4 遗留缺陷清零，使 TOMAS AGI 具备生产级确定性推理与对抗鲁棒性。

---

## 2. 用户故事

| # | 用户故事 | 来源主题 |
|---|---------|---------|
| US-1 | 作为 **AGI 研究者**，我想要 MNQ-Deep Ω-φ Transformer 集成到 TOMAS 训练管线，以便训练 Loss 降低 **74.9%** 并获得基于 IWPU 离散网格的确定性推理。 | 主题二：MNQ-Deep |
| US-2 | 作为 **系统运维人员**，我想要部署**三层对抗补丁防御体系**（多模态交叉验证 + κ-Gate 异常检测 + 物理一致性过滤），以便在生产环境中可靠拦截对抗样本。 | 主题四：安全防御 |
| US-3 | 作为 **硬件验证工程师**，我想要 T-Processor 仿真器支持 **Moufang-ALU Fano Plane LUT**，以便在 RTL 流片前验证八元数阴龙积 ⊙ 的计算正确性。 | 主题一：硬件 |
| US-4 | 作为 **模拟实验工程师**，我想要 **金灵球仿真器 v3.1** 与 TOMAS 仿真管线连通，以便在 TOMAS 生态内直接运行完整的 MNQ 实验体系（2500+ 行实验代码）。 | 主题二：工具 |
| US-5 | 作为 **智能体开发者**，我想要 **Reasonix 编程智能体**基于 TOMAS 五同构设计点集成，以便编程智能体可复用 TOMAS 的 AGI 核心能力。 | 主题五：工具生态 |

---

## 3. 需求池

### P0：必须完成（核心功能可运行 / 安全基线 / 缺陷修复）

#### P0-1：v3.4 已知缺陷修复

| 属性 | 内容 |
|------|------|
| **来源** | v3.4 系统审查 |
| **描述** | 修复三个已知阻断缺陷 |
| **子任务** | |
| | 3.1 完成 OWNTHINK 知识库导入管线 |
| | 3.2 `g_ego.py` 补全 ψ-alignment 一致性检查 |
| | 3.3 Flask `server.py` 支持热重载（消除手动重启） |

**涉及文件：**

| 文件 | 改动类型 | 要点 |
|------|---------|------|
| `sim/g_ego.py` | 修改 | 添加 `ψ_alignment_check()` 方法，在 self-loop 前校验 ψ 向量一致性 |
| `sim/server.py` | 修改 | 引入 `debug=True` + `use_reloader=True`（生产环境加环境变量开关） |
| 待定（OWNTHINK） | 修改/新建 | 补全 OWNTHINK API 对接 + EML 注入管线 |

---

#### P0-2：MNQ-Deep Ω-φ Transformer 集成

| 属性 | 内容 |
|------|------|
| **来源** | 主题二：MNQ-Deep Ω-φ Transformer + MNQ 数值优势 |
| **描述** | 将 MNQ-Deep 训练框架集成到 TOMAS，实现：训练-推理分离架构、三驱动力注意力（保护/服务/稳定）、跨层 Ω 累积 + 衰减残差、离散 IWPU 网格（无浮点误差）、刘机制 δS_Rel=0 替代 BP、Frozen Kernel 确定性 |

**技术要点：**
- **三驱动力注意力**：Protect-Attn / Serve-Attn / Stabilize-Attn 三头并行，通过 Ω 门控融合
- **跨层 Ω 累积**：每层输出 Ω_l = α·Ω_{l-1} + (1-α)·Ω_l，衰减因子 α ∈ (0,1)
- **IWPU 离散网格**：整数权重处理单元，消除浮点累积误差
- **刘机制 δS_Rel=0**：以熵增约束替代反向传播梯度计算
- **Frozen Kernel**：训练完成后冻结核参数，保证推理确定性

**涉及文件：**

| 文件 | 改动类型 | 要点 |
|------|---------|------|
| `sim/mnq_deep.py` | **新建** | MNQ-Deep 核心实现：`OmegaPhiTransformer`, `TriDriveAttention`, `IWPUGrid`, `LiuMechanism` |
| `sim/nasga_core.py` | 修改 | `NASGATrainer` 增加 MNQ-Deep 优化器分支，`train()` 支持 `optimizer='mnq_deep'` |
| `sim/causal_world_model_tomas.py` | 修改 | 因果世界模型接入 MNQ-Deep 前向推理 |
| `sim/hodge_operator.py` | 修改 | Hodge Laplacian 算子适配 Ω 累积 + 衰减残差 |
| `sim/server.py` | 修改 | 新增 endpoint：`POST /api/v2/mnq_deep/train`, `GET /api/v2/mnq_deep/status` |
| `sim/models.py` | 修改 | 新增 `MNQTrainingRun` 数据库模型 |

---

#### P0-3：三层对抗补丁防御上线

| 属性 | 内容 |
|------|------|
| **来源** | 主题四：对抗补丁防御 |
| **描述** | 构建 L1→L2→L3 级联防御管线，对外提供统一 API |

**技术要点：**
- **L1 多模态交叉验证**：文本+视觉+结构三通道一致性校验，任一通道置信度 < τ₁ 则触发告警
- **L2 κ-Gate 异常检测**：基于 Kappa 算子的拓扑异常检测，κ > τ₂ 则拦截
- **L3 物理一致性过滤器**：检查输入是否符合物理世界约束（如光照一致性、几何合理性）
- **Red-team 认证入口**：提供红队测试 API，用于持续验证防御有效性

**涉及文件：**

| 文件 | 改动类型 | 要点 |
|------|---------|------|
| `sim/tshield_wrapper.py` | 修改 | 重构为三层防御管线 `DefensePipeline(L1, L2, L3)` |
| `sim/processor_tshield_integration.py` | 修改 | 新增 κ-Gate 异常检测模块 `KappaGateDetector` |
| `sim/harness_aegis.py` | 修改 | 新增多模态交叉验证模块 `MultiModalCrossValidator` |
| `sim/mina_kappa_bridge.py` | 修改 | 新增物理一致性过滤器 `PhysicalConsistencyFilter` |
| `sim/server.py` | 修改 | 新增 endpoint：`POST /api/v2/defense/check`, `POST /api/v2/defense/redteam` |

---

### P1：应该完成（显著提升 / 能力补齐）

#### P1-4：T-Processor Moufang-ALU 仿真扩展

| 属性 | 内容 |
|------|------|
| **来源** | 主题一：T-Processor Moufang-ALU |
| **描述** | 在现有 `tprocessor_sim.py` 基础上，新增 Moufang-ALU 模块的 Python 仿真，支持 Fano Plane LUT 查找表实现八元数阴龙积 ⊙，以及 CGD 约束引擎 A1-A5 五条约束的仿真验证 |

**技术要点：**
- Fano Plane 七点三线结构 → 7×7 查找表
- 八元数乘法 e_i ⊙ e_j = LUT[i][j]，阴龙积定义在 Fano Plane 循环顺序上
- CGD 约束 A1（单位保持）/ A2（闭合性）/ A3（结合律偏差）/ A4（分配律偏差）/ A5（范数保持）

**涉及文件：**

| 文件 | 改动类型 | 要点 |
|------|---------|------|
| `sim/tprocessor_sim.py` | 修改 | 新增 `MoufangALU` 类，`FanoPlaneLUT` 类，`CGDConstraintEngine` 类 |
| `sim/octonion_py.py` | 修改 | 如有需要，添加阴龙积 ⊙ 运算重载 |

---

#### P1-5：金灵球仿真器 v3.1 桥接

| 属性 | 内容 |
|------|------|
| **来源** | 主题二：金灵球仿真器 v3.1 |
| **描述** | 连通外部 GitHub 仓库 `lisoleg/mnq-golden-spirit-ball-simulator` (2500+行 Python) 与 TOMAS 仿真管线，支持 TOMAS 直接调用金灵球的完整实验体系 |

**技术要点：**
- 作为 Git submodule 或 pip 包引入
- 桥接层将金灵球输出转换为 TOMAS EML 格式
- 支持批量实验调度（通过 Flask endpoint）

**涉及文件：**

| 文件 | 改动类型 | 要点 |
|------|---------|------|
| `sim/mnq_sim_bridge.py` | **新建** | `GoldenSpiritBallBridge`：子进程调用、结果解析、EML 格式转换 |
| `sim/server.py` | 修改 | 新增 endpoint：`POST /api/v2/mnq/gsb/run`, `GET /api/v2/mnq/gsb/results/{run_id}` |
| `requirements.txt` | 修改 | 添加金灵球依赖声明 |

---

#### P1-6：Reasonix 编程智能体集成

| 属性 | 内容 |
|------|------|
| **来源** | 主题五：Reasonix 编程智能体 |
| **描述** | 基于 TOMAS 五同构设计点集成 Reasonix 编程智能体，补齐 4 个缺失能力 |

**TOMAS 五同构设计点：**
1. EML 超图 → 代码抽象语法树 (AST) 同构映射
2. NASGA 搜索 → 代码生成搜索空间
3. Goedel Agent 自指 → 代码自修复循环
4. Kappa 算子 → 代码复杂度度量
5. Dead Zero → 死代码检测

**4 个缺失能力补齐：**
- 缺失 1：跨文件上下文感知（通过 EML 超图跨文件边实现）
- 缺失 2：增量编译验证（通过 Token Bridge 差分注入）
- 缺失 3：运行时反馈闭环（通过 Goedel Agent 自指循环）
- 缺失 4：多语言泛化（通过 LLM Distiller 蒸馏）

**涉及文件：**

| 文件 | 改动类型 | 要点 |
|------|---------|------|
| `sim/goedel_agent_tomas.py` | 修改 | 新增 `CodeSelfRepairLoop` 类（缺失3） |
| `sim/aether_bridge.py` | 修改 | 新增 `ReasonixBridge` 类，封装五同构 + 四补齐 |
| `sim/eml_ehnn.py` | 修改 | 新增 `ASTtoEMLMapper`（同构1） |
| `sim/token_bridge.py` | 修改 | 新增 `DiffInjector`（缺失2） |
| `sim/llm_distiller.py` | 修改 | 新增 `MultiLangAdapter`（缺失4） |
| `sim/server.py` | 修改 | 新增 endpoint：`POST /api/v2/reasonix/generate`, `POST /api/v2/reasonix/repair` |

---

### P2：可以完成（锦上添花 / 远期规划）

#### P2-7：T-Core 智能网卡仿真

| 属性 | 内容 |
|------|------|
| **来源** | 主题一：T-Core 智能网卡 |
| **描述** | 在仿真器中增加 T-Core SmartNIC 行为模型，模拟 IPv6→通信-计算-存储一体化 |

**涉及文件：**

| 文件 | 改动类型 | 要点 |
|------|---------|------|
| `sim/tprocessor_sim.py` | 修改 | 新增 `TCoreSmartNIC` 类：IPv6 地址映射、EML 缓存模拟、ASIL-D 等级标记 |

---

#### P2-8：Base-12 EML 超图周期域

| 属性 | 内容 |
|------|------|
| **来源** | 主题三：十二进制 EML 超图周期域 |
| **描述** | EML 超图编码引入 Base-12 优选基，支持周期性边界条件 |

**涉及文件：**

| 文件 | 改动类型 | 要点 |
|------|---------|------|
| `sim/eml_ehnn.py` | 修改 | 新增 `Base12Encoder`：将 EML 边标签编码为十二进制 |
| `sim/extend_hypergraph.py` | 修改 | 新增 `PeriodicBoundaryExtension`：周期域超图扩展算子 |

---

#### P2-9：AstraBrain-WBC 小脑模块原型

| 属性 | 内容 |
|------|------|
| **来源** | 主题六：AstraBrain-WBC 0.5 |
| **描述** | 基于 Causal Transformer 实现类人小脑模块，用于具身智能运动协调 |

**涉及文件：**

| 文件 | 改动类型 | 要点 |
|------|---------|------|
| `sim/astrabrain.py` | **新建** | `CerebellumModule`：Causal Transformer → 小脑前向模型 → 运动指令预测 |
| `sim/causal_world_model_tomas.py` | 修改 | 可选引入小脑模块作为世界模型先验 |

---

#### P2-10：CHLT 四重同构文档化

| 属性 | 内容 |
|------|------|
| **来源** | 主题三：CHLT 四重同构 + 主题七：AGI 同构于 TOMAS |
| **描述** | 将 Curry-Howard-Lambek-Tropical 四重同构与 TOMAS 的对应关系撰写为体系文档，指导后续架构设计 |
| **类型** | 纯文档，无代码改动 |

---

## 4. 需求交叉依赖

```
P0-1 (缺陷修复)
  ├──> P0-2 (MNQ-Deep) ──依赖──> P0-1 (g_ego.py ψ-alignment 是训练前置条件)
  ├──> P0-3 (安全防御) ──依赖──> P0-1 (Flask 热重载影响防御 API 可用性)
  │
P0-2 (MNQ-Deep)
  └──> P1-5 (金灵球桥接) ──扩展──> P0-2 (共用 MNQ 实验体系)
       └──> P1-6 (Reasonix) ──依赖──> P0-2 (MNQ-Deep 作为代码生成优化器)

P1-4 (Moufang-ALU)
  └──> P2-7 (T-Core) ──扩展──> P1-4 (共用 tprocessor_sim.py)
```

---

## 5. 待确认问题

| # | 问题 | 影响范围 |
|---|------|---------|
| Q1 | MNQ-Deep Ω-φ Transformer 的**训练-推理分离架构**，与现有 `nasga_core.py` 的训练循环如何对接？是否需要在 `NASGATrainer` 中新增一套独立的训练入口，还是以插件形式注入？ | P0-2 |
| Q2 | 金灵球仿真器 v3.1 (`lisoleg/mnq-golden-spirit-ball-simulator`) 的**开源许可协议**是什么？是否允许作为 submodule 引入商用项目？ | P1-5 |
| Q3 | T-Processor Moufang-ALU 的 **CGD 约束引擎 A1-A5** 五条约束的具体数学定义是否已有正式文档？仿真器需要精确的形式化定义才能实现。 | P1-4 |
| Q4 | 三层防御体系中的 **κ-Gate 异常检测阈值 τ₂** 如何标定？需要多少正/负标注样本用于阈值校准？ | P0-3 |
| Q5 | Reasonix 五同构设计点是否需要**新增独立的 API endpoint**，还是复用现有 84 个 endpoint？如果新增，是否需要独立鉴权？ | P1-6 |
| Q6 | OWNTHINK 知识库导入**未完成的具体环节**是什么？API 对接问题、数据格式问题还是 EML 注入逻辑问题？ | P0-1 |
| Q7 | T-Core SmartNIC 的仿真精度要求是什么？**行为级仿真**（功能验证）还是**周期精确仿真**（性能评估）？ | P2-7 |
| Q8 | v3.5 的**发布时间窗口**和**可投入人力**是多少？这将直接影响 P1/P2 的分级调整。 | 全局 |

---

## 6. 附录：主题-需求映射表

| 主题 | 文章 | 映射需求 | 优先级 |
|------|------|---------|--------|
| 硬件升级 | T-Processor Moufang-ALU | P1-4 | P1 |
| 硬件升级 | 光量子-忆阻异构芯片 | — (RTL 阶段，本版不纳入) | — |
| 硬件升级 | T-Core 智能网卡 | P2-7 | P2 |
| 硬件升级 | 非冯·诺依曼架构 | — (定位文档) | — |
| MNQ-Deep | Ω-φ Transformer | P0-2 | P0 |
| MNQ-Deep | MNQ 数值优势 | P0-2（IWPU/Liu 机制子模块）| P0 |
| MNQ-Deep | 金灵球仿真器 v3.1 | P1-5 | P1 |
| 理论桥接 | TOMAS vs 标准模型 | — (理论文档) | — |
| 理论桥接 | Base-12 EML 周期域 | P2-8 | P2 |
| 理论桥接 | CHLT 四重同构 | P2-10 | P2 |
| 安全防御 | 三层对抗补丁防御 | P0-3 | P0 |
| 工具生态 | Reasonix 编程智能体 | P1-6 | P1 |
| 工具生态 | Loop 工程 | — (方法论，融入 Reasonix) | — |
| 工具生态 | DAQ 中间件 | — (基础设施，后续版本) | — |
| 具身智能 | AstraBrain-WBC 0.5 | P2-9 | P2 |
| 具身智能 | 果蝇连接组 | — (基准数据集) | — |
| 具身智能 | EBRAINS/HBP | — (外部参考) | — |
| 具身智能 | CCF YOCSEF 白皮书 | — (方向参考) | — |
| 体系方法论 | TOMAS 架构全景 | — (架构文档) | — |
| 体系方法论 | DL/RL 算法全景 | — (路线图) | — |
| 体系方法论 | MBSE 本体论 | — (理论文档) | — |
| 体系方法论 | AGI 同构于 TOMAS | P2-10（与 CHLT 合并文档化）| P2 |
| 缺陷修复 | v3.4 系统审查 | P0-1 | P0 |
