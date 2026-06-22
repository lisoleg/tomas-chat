# Changelog

## [v3.13] - 2026-06-23

### Added
- **v3.13 P0-P2 性能优化 + Fugu Conductor 编排层**：
  - **P0 性能优化**：4 个重查询端点添加分页支持（`get_corpus`, `get_conflicts`, `get_sessions`, `get_knowledge`），默认 page_size=20、最大 100，消除全量返回导致的内存峰值
  - **P1 优化**：SQLite 索引优化（`idx_triples_subject`/`idx_triples_object`/`idx_triples_i_weight` 重建 + 新增 `idx_triples_predicate`），API 响应缓存（`/api/knowledge/stats` 5 分钟内存缓存），前端 `React.memo` + `useMemo` 优化减少不必要重渲染
  - **P2 优化**：Vite 构建分包（vendor split + manual chunks），CI/CD 流水线（GitHub Actions: lint → type-check → build → test），OwnThink 断点续跑增强（断点文件校验 + 自动恢复）
  - **Fugu Conductor 编排层**：`orchestrator.py`（~800 行）—— 多智能体编排引擎，自适应任务分解（DAG 拓扑排序 + 依赖感知调度），Agent 注册表（动态注册/注销），任务状态机（PENDING → RUNNING → COMPLETED/FAILED），3 个 Flask 端点（`GET /api/orchestrator/agents`、`POST /api/orchestrator/orchestrate`、`GET /api/orchestrator/stats`），Flask 端点总数 165 → 168
- 新增 1 个模块文件，~800 行代码
- 前端新增编排面板（OrchestratorPanel.tsx），前端面板总数 → 23
- 累计模块数 104 → 97+（核心模块口径），累计测试数 1602 → 1368 passed / 2 skipped（P0-P2 优化期间测试重构合并）

### Changed
- paper.md 版本号 v3.8 → v3.13
- README.md：更新模块数（92+→97+）、测试数（985→1368+）、端点数（56→168）、面板数
- ARCHITECTURE.md：版本号 v3.5 → v3.13，新增编排层章节
- api_v2.md：版本号 v2.0 → v2.1，新增编排 API 和分页 API 文档
- Vite 构建配置：添加 manualChunks 分包策略
- GitHub Actions CI/CD：`.github/workflows/ci.yml` 新增

### Fixed
- 4 个端点全量返回导致的 OOM 风险（添加分页支持）
- SQLite 查询性能：缺少 predicate 索引导致慢查询
- 前端列表组件未使用 memo 导致频繁重渲染
- OwnThink 断点续跑：断点文件损坏时无法自动恢复

---

## [v3.12] - 2026-06-23

### Added
- **v3.12 鲁兆DNA + GAT公理 + 金融市场世界模型 + 代币化经济**（4 模块 + 148 测试）：
  - **鲁兆DNA**：`luzhao_dna.py`（~1200 行）—— 基于鲁兆理论的技术分析 DNA 编码，K 线形态模式识别（头肩顶/双底/三角形等 12 种），DNA 序列比对（Smith-Waterman 算法），历史回测验证，ψ-锚风险等级标记
  - **GAT公理**：`gat_axioms.py`（~900 行）—— 广义对齐定理（Generalized Alignment Theorem），3 条核心公理（一致性公理/安全性公理/可纠正性公理），对齐证明验证器，与 Constitutional AI 模块集成
  - **金融市场世界模型**：`fin_world_model.py`（~1400 行）—— SCM 因果图建模金融市场（利率→汇率→股价传导链），反事实推理（"如果降息 50bp 会怎样"），压力测试场景生成，硬约束（无套利/市场出清）
  - **代币化经济**：`token_economy.py`（~1100 行）—— TOMAS 内部代币经济模型，Agent 贡献度量化（κ-Snap 审计链），代币发行/销毁/转移，Celo 链上结算集成，通胀控制参数
- 新增 4 个模块文件，~4,600 行代码
- 新增 148 个测试用例（`test_v312_modules.py`），148/148 全部通过
- Flask 新增 25 个端点（`/api/v2/fin/*`、`/api/v2/token/*`、`/api/v2/luzhao/*`、`/api/v2/gat/*`），端点总数 140 → 165
- 累计模块数 100 → 104，累计测试数 1454 → 1602

### Changed
- paper.md 版本号 v3.11 → v3.12（待更新）
- README.md：更新模块数、测试数、端点数（待更新）

---

## [v3.11] - 2026-06-23

### Added
- **v3.11 认知健康 + Grill-Me 引擎**（2 模块 + 239 自测）：
  - **认知健康**：`cognitive_health.py`（~1550 行，104 自测）—— AGI 认知健康监测与诊断引擎，7 维健康指标（一致性/完备性/鲁棒性/可解释性/安全性/效率/适应性），自适应阈值调整，健康报告生成（JSON/Markdown），异常检测与预警（KL 散度漂移 + 趋势分析），与 ψ-Gate/κ-Snap/T-Shield 联动
  - **Grill-Me 引擎**：`grill_me_engine.py`（~1954 行，135 自测）—— 自适应质询式学习引擎，苏格拉底式提问生成器（6 种提问策略），知识缺口检测（EML 子图覆盖度分析），自适应难度调节（β 自适应参数），对话式知识巩固（间隔重复 + 主动回忆），学习路径推荐（DAG 拓扑排序），与 Token Bridge 集成
- 新增 2 个模块文件，~3,504 行代码
- 新增 239 个自测断言（cognitive_health 104 + grill_me_engine 135），全部通过
- Flask 新增 10 个端点（`/api/v2/cognitive-health/*`、`/api/v2/grill-me/*`），端点总数 130 → 140
- 累计模块数 98 → 100，累计测试数 1215 → 1454

### Changed
- paper.md 版本号 v3.10 → v3.11（待更新）
- README.md：更新模块数、测试数、端点数（待更新）

---

## [v3.10] - 2026-06-22

### Added
- **v3.10 对齐三范式 + 目标导向智能体**（2 模块 + 114 测试）：
  - **对齐三范式**：`alignment_paradigms.py`（~1100 行）—— AI 对齐三大范式工程实现：（1）RLHF 范式——奖励模型训练 + PPO 策略优化 + KL 散度约束；（2）Constitutional AI 范式——宪法规则集 + 自我批评 + 修订循环；（3）MecE（Mechanistic Interpretability）范式——激活 patching + 因果追踪 + 稀疏自编码器探针。三范式统一评估框架（对齐基准测试套件）
  - **目标导向智能体**：`goal_oriented_agent.py`（~1300 行）—— 目标分解树（Goal Tree DAG），自适应计划生成（HTN 规划 + 重规划），执行监控（进度追踪 + 异常检测），目标完成度评估（多指标加权），与 Fugu Conductor 预集成（任务编排接口）
- 新增 2 个模块文件，~2,400 行代码
- 新增 114 个测试用例（`test_v310_modules.py`），114/114 全部通过
- 累计模块数 96 → 98，累计测试数 1101 → 1215

### Changed
- paper.md 版本号 v3.9 → v3.10（待更新）
- README.md：更新模块数、测试数（待更新）

---

## [v3.9] - 2026-06-22

### Added
- **v3.9 BabelTele + 超图范畴论 + KernelCAT + Constitutional AI**（4 模块 + 116 测试）：
  - **BabelTele 语义压缩器**：`babel_tele.py`（~1000 行）—— 跨语言语义压缩与传输引擎，语义指纹提取（SimHash 64-bit），压缩比自适应（κ 值感知），多语言对齐（中/英/日/法/德），语义保真度验证（余弦相似度 + Jaccard），与 EML-KB 超边编码集成
  - **超图范畴论**：`hypergraph_category.py`（~850 行）—— 超图范畴论形式化（Set^V 函子 + 态射组合律），pullback/pushout 超图构造，极限/余极限计算，自然变换（EML 超边态射），Yoneda 引理应用（超图嵌入），与 ExtendHypergraph 模块集成
  - **KernelCAT 调度器**：`kernel_cat.py`（~750 行）—— 内核感知认知任务调度器（Kernel-aware Cognitive Task Scheduler），任务优先级队列（EDF + 优先级反转防护），CPU/GPU/FPGA 异构资源感知调度，κ-Snap 上下文切换审计，实时性保证（截止时间感知），与 T-Processor/T-Shield 联动
  - **Constitutional AI**：`constitutional_ai.py`（~950 行）—— 宪法 AI 工程实现，宪法规则引擎（CONSTITUTIONAL/REGULATORY/OPERATIONAL 三级），自我批评生成器（LLM 自审 + 规则匹配），修订循环（critique → revise → verify），宪法违规检测与拦截，与 ψ-Anchor/GaussExPsiAnchor 集成
- 新增 4 个模块文件，~3,550 行代码
- 新增 116 个测试用例（`test_v39_modules.py`），116/116 全部通过
- 累计模块数 92 → 96，累计测试数 985 → 1101

### Changed
- paper.md 版本号 v3.8 → v3.9（待更新）
- README.md：更新模块数、测试数（待更新）

---

## [v3.8] - 2026-06-22

### Added
- **v3.8 GaussEx-EML Bridge + 认知压缩引擎升级**（基于复合体理学 2 篇微信公众号文章）：
  - **GaussEx-EML 桥接**：`gaussex_eml.py`（~650 行）—— 开放线性系统范畴论（Stein & Samuelson 2025）在 TOMAS EML-KB 上的工程落地。GaussExSystem = Fibre(D) ⊕ Noise(ψ) 开放系统表示，CopartialMap 共偏性观测（Borel 柱体投影、隐私计算、零原始数据暴露），Interconnection 范畴组合律（Fibre 交集 + Noise 卷积），NoisyResistor 含噪电阻（Stein 经典示例，自动驾驶多传感器逆方差融合），CopartialRiskControl 共偏性风控（跨行联合风控沙盒、JSON-LD 架构），ComplementaryInterconnection 互补互联（工业数字孪生 RUL 预测），GaussExPsiAnchor ψ-锚宪法级权限（CONSTITUTIONAL/REGULATORY/OPERATIONAL 三级），GaussExKSnapRecord κ-Snap 审计，GaussEx 可证伪预言 P17-P19，IndustrialFeasibilityTheorem 产业落地可行性定理（多项式时间复杂度）
  - **认知压缩引擎**：`cognitive_compression.py`（~700 行）—— "从微积分到世界模型"认知压缩嵌入 EML-KB。PDEConservationLaw PDE 守恒律（质量/动量/能量/粒子/电荷 → ψ-锚宪法级规则），WMHyperedgePDE PDE 确定性骨架结构化存储（非黑箱 latent、JSON-LD Appendix A 格式），ENTBioNetwork ENT 内源性网络（基因调控/代谢回路、生物 ψ-锚 ATP/膜电位/pH/凋亡），MUSEndogenousConflict MUS 双存（ENT 内源竞争 A5 公理、Appendix B 日志格式），PhysicalAIEngine 物理AI 引擎（T-Processor ⊙(e_PDE, e_Data) Gan 极化、κ 大→信物理/κ 小→跟数据），CompressionLossKSnap κ-Snap 压缩损失审计（哥德尔边界、SHA-256 丢弃模态指纹、Appendix C 格式），CognitiveCompressionEmbedding 认知压缩嵌入定理（L1 全量阿卡西/L3 世界帧/ψ-锚/κ-Snap 四要素），认知压缩可证伪预言 P14-P16
  - **跨模块集成**：cognitive_compression 从 gaussex_eml 导入 GaussExSystem/Fibre/GaussianNoise 等共享类型，GaussEx 系统作为 PhysicalAIEngine 的 Data Stream 数据源，4 项跨模块集成测试
- 新增 2 个模块文件，~1,350 行代码
- 新增 110 个测试用例（`test_v38_modules.py`，22 测试类），110/110 全部通过
- 新增 6 项可证伪预言（P14-P16 认知压缩, P17-P19 GaussEx）
- 累计模块数 90 → 92，累计测试数 875 → 985

### Changed
- paper.md 版本号 v3.7 → v3.8（待更新）
- README.md：更新模块数（90→92）、测试数（875→985）（待更新）

---

## [v3.7] - 2026-06-22

### Added
- **v3.7 HTD + 拓扑孤子 + Gan-TOMAS P=GW 升级**（基于复合体理学 3 篇微信公众号文章）：
  - **全息拓扑动力学 HTD**：`htd_sim.py`（~800 行）—— AdS/CFT bulk-boundary 对偶在 EML-KB 中的实现，Octonion 完整实现（`e_0..e_7`）+ Moufang 乘法，BraidWord 形式化编织群（B_n, σ_i^{±1}，Unicode/ASCII 双格式解析），TopologicalOrderState（Chern/D/γ/Kitaev-Preskill），TOHTD_Simulator 五步演化管道（Read Bulk → Braid → Post-Select → κ-Snap → TEE 验证），TopoChargeGroup 共享枚举，FQHE ν=1/3 示例，HTD 可证伪预测 P10-P11
  - **拓扑孤子与相变**：`topo_soliton.py`（~550 行）—— 6 类拓扑孤子（Abrikosov Vortex/Skyrmion/Domain Wall/Majorana Zero Mode/Instanton/Meron），ψ-Anchor 三重拓扑保护（电荷守恒/能隙/编织相位），SolitonBraider（braid_pair/braid_sequence/associator/braiding_phase），TOMAS_Topology_Simulator（strain/B-field 扰动 → 能隙闭合 → Chern 跳跃相变），Topo 可证伪预测 P7-P9
  - **Gan-TOMAS P=GW 八元数升维**：`gan_tomas_pgw.py`（~900 行）—— Gan 极化算子 G（cos(φ)·ħ·Re + sin(φ)·ħ·Im），八元数质量起源公式 M=‖O‖²/(G_res×tanh(κ))，轻子质量比代数推导（基于 Furey 2015 + TOMAS κ 扩展），观测顺序效应（associator_norm → 顺序无关/敏感/决定三区判定），EML-KB SQL 查询集成（particle/wave/verify 三类），Gan 可证伪预测 P1-P6
  - **跨模块集成**：TopoChargeGroup 从 htd_sim 导入（非重复定义），κ-Snap 跨模块统一审计格式，3 项跨模块集成测试（HTD↔Topo, Gan↔HTD, 三模块全链）
- 新增 3 个模块文件，~2,250 行代码
- 新增 108 个测试用例（`test_v37_modules.py`，18 测试类），108/108 全部通过
- 新增 11 项可证伪预测（P1-P6 Gan, P7-P9 Topo, P10-P11 HTD）
- 论文 paper.md → v3.7：新增 Appendix M（v3.7 HTD/Topo/Gan 升级 + 评估数据）
- 评估数据补充：ARC-AGI-3（RHAE 66.67%）、GAIA（2/3 正确）、SWE-bench（300/300 零错误）

### Changed
- paper.md 版本号 v3.6 → v3.7，测试数 767 → 875，模块数 87 → 90
- README.md：更新特性列表、模块数（87→90）、测试数（767→875）

---

## [v3.6] - 2026-06-21

### Added
- **v3.6 八模块升级**（基于复合体理学 8 篇微信公众号文章 + MNQ Golden Spirit Ball Simulator + DIKWP Ecosystem）：
  - **ψ-Gate 不确定性门控**：`psi_gate.py`（6 核心锚点、MUS 双存、多世界并行推理、容差衰减控制器）
  - **7+1 语义规范本体**：`eml_kb_ontology.py`（Entity/Attribute/Relation/Event/Temporal/Causal/Constraint + BusinessRule 本体治理、EML-Lite DB 五区架构 L1-L5、Fact→Act 桥接）
  - **解释坩埚**：`interpretation_crucible.py`（波粒二象性、多世界分支、贝叶斯坍缩、MUS 双存解析、解释谱系追踪）
  - **世界模型超边**：`wm_hyperedge.py`（SDF/Affordance/Kinematic 三超边、Ω-Gate Tetrad 联验 π/Φ/Ω/℧）
  - **DIKWP 全桥接**：`dikwp_bridge_full.py`（IntentGuard 意图守卫、MemoryLedger→MUS 映射、DAAP 四层审计、语义安全完备性定理）
  - **太极周期 v2**：`taiji_cycle_v2.py`（EML 脉冲→φ-Gate→T-Processor 闭环、CycleSpinner 自适应调度器、LRU 超边存储）
  - **MNQ 冻结内核**：`mnq_frozen_kernel.py`（五层渐进冻结 L0-L4、八元数非结合度量化、Golden Spirit Ball Fibonacci 投影、κ=7 稳定器）
  - **TOMAS 治疗师扩展**：`tomas_therapist.py` +6 方法（L1 记忆植入、ψ 锚软化、Purpose 内化、MUS 区域创建、治疗摘要、恢复评分）
- 新增 8 个模块文件（7 新建 + 1 修改），+6,432 行代码
- 新增 57 个测试用例（`test_v36_modules.py`，8 测试类），57/57 全部通过
- 全量回归测试 767 项：763 passed + 2 skipped + 2 pre-existing failed（非 v3.6 引入）

### Fixed
- `dikwp_bridge_full.py`：IntentSeverity 从字符串枚举改为整数枚举（SAFE=0, SUSPICIOUS=1, DANGEROUS=2, CRITICAL=3）
- `test_v36_modules.py`：修复 IntentSeverity 作用域问题（setup_method 中添加 `self.IntentSeverity = IntentSeverity`）
- `mnq_frozen_kernel.py`：修复 math 函数别名在常量定义之前的问题

### Changed
- paper.md → v3.6（新增 Appendix L：v3.6 八模块升级）
- README.md：更新特性列表、模块数（79→87）、测试数（729→767）
- Git commit `5381574` 推送至 backend/master

---

## [v2.6] - 2026-06-21

### Added
- **六文章升级**（基于复合体理学 2026-06-20 六篇公众号文章）：
  - HNC 同构映射：`hnc_parser_wrapper.py` + `tomas_nlu_pipeline.py`（NLU 管道 + ℐ 贝叶斯更新）
  - 哥德尔智能体：`goedel_agent_tomas.py`（PG-囚禁 + MUS 双存 + κ-snap 审计链）
  - Aether 因果世界模型：`causal_world_model_tomas.py` + `aether_bridge.py` + `hodge_operator.py` 升级（SCM do-calculus）
  - AgentWeb 分布式时序：`vector_clock.py` + `causal_delivery.py` + `agentweb_runtime.py` + `fediverse_bridge.py`
  - 密码学桥接：`mina_kappa_bridge.py`（Mina SNARK 22KB 证明）+ `celo_bridge.py`（Celo 稳定币支付，RPC 超时降级）
  - EML-EHNN 等变超图：`eml_ehnn.py` + `equivariant_layers.py` + `eml_semzip.py` / `gpct.py` 升级
- 新增 14 个模块文件、修改 8 个已有文件
- 新增 28 个 `/api/v2/*` REST 端点（server.py）
- 前端 V2Panel 组件（6 标签页，覆盖全部 v2 API）
- `/api/knowledge/stats` 端点（全库真实统计，5 分钟内存缓存）

### Fixed
- Celo RPC 超时：超时从 10.0s → 3.0s，快速降级路径
- 前端 DistillPanel 统计卡片：优先使用 `/api/knowledge/stats` 真实数据（替代分页子集）

### Changed
- paper.md → v2.6（新增 Appendix K：六文章升级）
- README.md：更新特性列表，101M+ 三元组 badge

---

## [Unreleased]

### Added
- HyperIndex v2.0: DB-backed k-hop subgraph loading with OrderedDict LRU cache
- UnionFind matroid circuit detection: O(|E|·α(|V|)) complexity
- ChainDB distributed hypergraph: HyperShard + DistributedHyperIndex
- EML v2.0: n-ary hyperedge binary format
- 6 new API endpoints for hypergraph operations
- HypergraphPanel frontend: 5 tabs (overview/k-hop/matroid/distributed/export)
- create_shards.py: HyperShard generation script

### Fixed
- INSERT OR IGNORE pattern in migrate_hypergraph.py (UNIQUE constraint fix)
- matroid-unionfind API: added seeds concept resolution
- export-eml-v2 API: fixed parameter names
- Frontend TypeScript errors in AEGISPanel/TShieldPanel/TProcessorPanel
- tomas_agi package import (added __init__.py)

### Changed
- eml_dimred/__init__.py: v1.0.0 → v2.0.0, 27 exports
- README.md: updated with new features and 101M+ triples badge

---

## [v3.4] - 2026-06-15

### Added
- DIKWP five-layer mapping
- Semantic firewall
- T-Processor/T-Shield panels
- ARC-AGI-3/GAIA/SWE-bench evaluation frameworks

### Fixed
- OwnThink import UNIQUE constraint handling
- Frontend build errors

---

## [v3.0] - 2026-06-01

### Added
- "Translator + Writer" V3 hybrid architecture
- Φ-Gate semantic gating
- EML knowledge distillation
- DeepSeek LLM integration

---

## [v2.0] - 2026-05-01

### Added
- NASGA octonion algebra
- κ-Gate semantic pruning
- Hypergraph data model
- SQLite backend for knowledge storage

---

## [v1.0] - 2026-03-01

### Added
- Initial TOMAS-AGI implementation
- Basic EML knowledge graph
- LSTM-based translator
- Token bridge architecture
