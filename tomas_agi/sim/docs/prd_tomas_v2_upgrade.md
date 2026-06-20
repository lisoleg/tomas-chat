# TOMAS v2.0 六文章代码升级 PRD

**文档版本**: v1.0  
**创建日期**: 2026-06-20  
**作者**: 许清楚 (Product Manager)  
**基于**: 章锋"复合体理学"公众号2026年6月20日发布的6篇技术文章

---

## 1. 项目信息

| 字段 | 内容 |
|------|------|
| **项目名称** | TOMAS v2.0 六文章代码升级 |
| **项目路径** | C:/Users/1/WorkBuddy/2026-06-13-01-47-22/tomas_agi/sim/ |
| **编程语言** | Python 3.13 + Flask + DeepSeek API |
| **原始需求** | 基于6篇技术文章（HNC同构映射、Mina+哥德尔机、哥德尔智能体安全架构、Aether因果世界模型、AgentWeb分布式时序、EML-EHNN等变超图），对现有TOMAS AGI系统进行代码升级 |
| **现有基础** | 79个.py文件，已支持κ-Snap链、MUS模块、ψ-锚、ℐ计算、GPCT边界层、HarnessX+AEGIS |

---

## 2. 产品定义

### 2.1 产品目标

**一句话目标**: 将6篇前沿理论文章的核心创新（HNC自然语言理解、Mina密码学快照、哥德尔智能体安全升维、Aether因果世界模型、AgentWeb分布式时序、EML-EHNN等变超图）工程化实现，打造具备因果一致性、自改进安全性和分布式协作能力的TOMAS AGI v2.0系统。

**具体目标**:

1. **自然语言理解升维**: 实现HNC概念基元→EML超边Schema的同构映射，支持24字母概念体系与句类模板的端到端NLU管道
2. **密码学因果审计**: 集成Mina递归SNARK实现κ-Snap的恒定22KB密码学压缩，支持Celo支付层+Mina存证层的AgentWeb经济结算
3. **哥德尔智能体安全架构**: 实现硬锚点H_hard否决权、ℐ(e)信息存在度替代标量奖赏、MUS双存互斥稳态、κ-Snap代码演化审计链的四重封边
4. **因果世界模型**: 融合Aether SCM结构因果模型与TOMAS裁决层，支持反事实推理与物理守恒律硬锚检查
5. **分布式时序一致性**: 实现AgentWeb架构（Fediverse+向量时钟+区块链快照），支持因果交付与光锥因果偏序
6. **等变超图神经网络**: 实现EML-EHNN等变超图神经网络，支持ℐ(e)加权、MUS-Aware Pooling、κ-Snap一致性损失、GPCT动态维度扩展

### 2.2 用户故事

| # | 角色 | 需求 | 价值 |
|---|------|------|------|
| 1 | AI研究者 | 作为AI研究者，我希望系统能解析自然语言的HNC概念基元并映射为EML超图结构，以便进行可解释的符号-神经混合推理 | 支持深层语言理解与安全推理 |
| 2 | 智能体开发者 | 作为智能体开发者，我希望哥德尔智能体能在ℐ(e)评估和H_hard硬锚保护下进行自我改进，以便安全地迭代升级而不会破坏核心安全约束 | 确保自改进过程的安全性与可控性 |
| 3 | 分布式系统架构师 | 作为分布式系统架构师，我希望AgentWeb节点能基于向量时钟实现因果一致性，并通过Mina快照上链存证，以便在多智能体协作中保证因果顺序和可审计性 | 实现分布式环境下的因果一致性与可信审计 |
| 4 | 机器学习工程师 | 作为机器学习工程师，我希望EML-EHNN等变超图神经网络能基于ℐ(e)加权学习，并保留MUS冲突分支进行双存，以便提升模型的因果推理能力和鲁棒性 | 提升模型的可解释性与因果推理能力 |
| 5 | 系统运维人员 | 作为系统运维人员，我希望所有关键操作（代码自改、知识更新、跨节点通信）都有κ-Snap审计链记录并支持Mina上链存证，以便进行事后的安全审计与因果追溯 | 确保系统行为可追溯、可审计、可回滚 |

---

## 3. 需求池

### P0 (必须实现 - 核心安全与功能)

| # | 模块 | 文件 | 功能描述 | 验收标准 |
|---|------|------|----------|----------|
| P0-1 | HNC NLU管道 | `hnc_parser_wrapper.py` (新建) | 实现HNC概念基元编码器（24字母体系），支持v/g/u/p/m/f/c/j/q/r等概念类型的编码与解析 | 能正确解析"我吃苹果"并返回概念基元码[v, p, p] |
| P0-2 | HNC NLU管道 | `tomas_nlu_pipeline.py` (新建) | 实现端到端NLU管道（TOMAS_NLU_Pipeline类），含MUS冲突检查/ψ-锚检查/κ-Snap写入/ℐ初始计算 | 输入句子能输出template_id/chunks/concept_codes/cited_rule |
| P0-3 | 哥德尔智能体 | `goedel_agent_tomas.py` (新建) | 实现TOMASGodelAgent类，含self_improve_loop、PG-囚禁（SELF_UPDATE前拦截H_hard修改）、Bayesian ℐ接受律 | 自改进代码必须通过H_hard检查才能生效 |
| P0-4 | 哥德尔智能体 | 修改`g_ego.py` | 添加SELF_INSPECT阴敛读ψ-锚能力，支持代码自改前的安全审查 | G_ego能读取并验证ψ-锚完整性 |
| P0-5 | 哥德尔智能体 | 修改`ksnap_operator.py` | 支持代码演化SnapEvent，新增new_code_hash/trigger_obs_id/llm_version字段 | κ-Snap能记录每次代码修改的完整上下文 |
| P0-6 | 硬锚点保护 | 修改`pg_gate`相关模块 | 扩展硬锚点集包含代码安全原语（内存安全/类型安全/并发安全），禁止自改代码删除H_hard中符号 | H_hard中的物理守恒律和代码安全原语不可被删除 |
| P0-7 | 向量时钟 | `vector_clock.py` (新建) | 实现向量时钟VC合并与happened_before判断，支持分布式节点的因果顺序检测 | 能正确判断两个事件的因果关系 |
| P0-8 | AgentWeb运行时 | `agentweb_runtime.py` (新建) | 实现AgentWeb节点运行时（G_ego Runtime+因果检查+κ-Snap日志），支持多智能体协作的因果一致性 | 节点能基于向量时钟拒绝因果前置未到齐的消息 |

### P1 (重要 - 核心功能增强)

| # | 模块 | 文件 | 功能描述 | 验收标准 |
|---|------|------|----------|----------|
| P1-1 | HNC-EML映射 | 修改`eml_injector.py` | 支持HNC句类模板→EML超边Schema映射（BC_TransEvi→transitive_action等） | HNC句类能正确映射为EML超边 |
| P1-2 | HNC-EML映射 | 修改`g_ego.py` | 添加aligned_with_purpose接口供NLU管道调用，支持目的对齐检查 | NLU输出能通过G_ego的目的对齐验证 |
| P1-3 | Mina桥接 | `mina_kappa_bridge.py` (新建) | 实现MinaTOMASSnap类，支持Mina风格κ-Snap密码学封装（递归SNARK证明） | κ-Snap能生成恒定22KB的递归证明 |
| P1-4 | Celo桥接 | `celo_bridge.py` (新建) | 实现Celo支付结算层桥接（稳定币cUSD/cEUR，BLS聚合签名），支持AgentWeb经济激励 | 智能体协作能通过Celo进行微支付结算 |
| P1-5 | 因果世界模型 | `causal_world_model_tomas.py` (新建) | 实现TOMASCausalWorldModel类（learn_from_data/predict_next_state），融合Aether SCM与TOMAS裁决层 | 世界模型能进行反事实推理 |
| P1-6 | 因果世界模型 | `aether_bridge.py` (新建) | 实现Aether SCM编码器桥接，支持物理关系提取与因果边编码 | Aether的SCM能正确导入TOMAS |
| P1-7 | 因果世界模型 | 修改`hodge_operator.py` | 添加物理守恒律H_hard硬锚检查，支持能量/动量/角动量守恒验证 | 违反物理守恒律的预测会被H_hard否决 |
| P1-8 | Fediverse桥接 | `fediverse_bridge.py` (新建) | 实现ActivityPub扩展（含vector_clock/snap_ref字段）、因果交付缓冲与排序 | Fediverse消息能携带因果上下文 |
| P1-9 | κ-Snap上链 | 修改`ksnap_operator.py` | 支持Merkle Root上链批提交，减少链上交易成本 | 多个κ-Snap能批量提交到Mina/Celo |
| P1-10 | EML-EHNN | `eml_ehnn.py` (新建) | 实现EMLEHNN类（含ℐ-weighted等变层、MUS-Aware Pooling、κ-Snap一致性损失） | EHNN能基于ℐ(e)进行加权学习 |

### P2 (可选 - 增强与优化)

| # | 模块 | 文件 | 功能描述 | 验收标准 |
|---|------|------|----------|----------|
| P2-1 | EHNN等变层 | `equivariant_layers.py` (新建) | 实现EHNN等变线性层（基于\|i∩j\|分权重），支持k阶均匀超图的邻接张量序列处理 | 等变层能满足E(n)等变性测试 |
| P2-2 | EHNN-GPCT集成 | 修改`gpct`相关模块 | 支持GPCT动态输出维度扩展（范式转移时自动扩展），TOMASKBManager类on_new_data触发层创 | GPCT能根据知识增长动态扩展 |
| P2-3 | EHNN-SEMZIP集成 | 修改`eml_semzip.py` | 集成ℐ-weighted EHNN特征提取，替代原有特征提取器 | SEMZIP能利用EHNN的等变特征 |
| P2-4 | 因果交付 | `causal_delivery.py` (新建) | 实现因果交付缓冲与排序（收端缓冲并发消息直到因果前置到齐），支持AgentWeb的因果一致性保证 | 并发消息能按因果顺序交付 |
| P2-5 | NLU ℐ计算增强 | 修改`tomas_nlu_pipeline.py` | 增强ℐ初始计算（depth_factor + cite_factor），支持上限0.95的贝叶斯更新 | ℐ(e)能准确反映概念的信息存在度 |
| P2-6 | GPTC层创触发 | 修改`gpct`相关模块 | 支持因果边层创触发、GPCT边界层重划，响应世界模型的范式转移 | 因果发现能触发GPCT的层创扩展 |
| P2-7 | MUS双存增强 | 修改`memos_fusion.py` | 增强MUS双存能力，支持波粒二象性等互斥稳态的保留（而非强制平均） | MUS能同时保留冲突的因果假设 |

---

## 4. 待确认问题

### Q1: HNC概念基元码表的完备性
**问题**: 文章1提到HNC的24字母体系，但是否需要完整实现全部24个字母的概念基元编码？还是优先实现核心的v/g/u/p/m/f/c/j/q/r等10个？

**建议**: 优先实现文章明确提到的10个核心概念类型，其余14个作为P2延期实现。

**需要确认**: 是否有HNC完整的24字母概念定义文档？

---

### Q2: Mina递归SNARK的工程可行性
**问题**: 文章2提到Mina的恒定22KB递归证明，但在Python环境中如何实现Mina的SNARK证明生成？是否需要依赖Mina节点的RPC接口？

**建议**: 先实现Mina桥接的API调用层（类似`mina_kappa_bridge.py`的封装），真实证明生成委托给外部Mina节点。

**需要确认**: 是否有可用的Mina测试网节点供集成测试？

---

### Q3: 哥德尔智能体的热替换安全性
**问题**: 文章3提到哥德尔智能体能"热替换"改进版代码，但Python运行时如何实现安全的代码热替换？是否使用importlib.reload()还是进程重启？

**建议**: 采用"影子沙箱+验收测试+原子切换"策略，新代码在沙箱中运行验收通过后才原子切换到主进程。

**需要确认**: 现有`g_ego.py`是否已有沙箱执行环境？

---

### Q4: AgentWeb的Fediverse扩展兼容性
**问题**: 文章5提到扩展ActivityPub协议（新增vector_clock/snap_ref字段），但标准Fediverse服务器（如Mastodon）可能不识别扩展字段。是否需要部署专用Fediverse实例？

**建议**: 先实现兼容模式（扩展字段存到扩展JSON-LD对象中），确保与标准Fediverse服务器的互操作性。

**需要确认**: 目标部署环境是否包含自建Fediverse实例？

---

### Q5: EML-EHNN的计算复杂度
**问题**: 文章6提到EHNN的k阶均匀超图邻接张量序列，当超图规模较大时（如10^5节点），EHNN的等变线性层计算复杂度是否可接受？是否需要稀疏化优化？

**建议**: 先实现稠密版本验证功能正确性，然后针对大规模场景实现稀疏近似（基于\|i∩j\|阈值截断）。

**需要确认**: 目标应用场景的超图规模预期是多少？

---

## 5. 技术风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|----------|
| HNC概念体系与EML的映射规则复杂，可能映射不完全 | 中 | 先进行小规模概念映射验证（如100个概念），迭代完善映射规则 |
| Mina SNARK证明生成依赖外部节点，可能成为单点故障 | 中 | 实现证明生成的异步队列，节点故障时降级为本地κ-Snap（暂不证明） |
| 哥德尔智能体自改进可能绕过H_hard检查 | 高 | 实施"三重检查"（静态分析+动态沙箱+κ-Snap审计），确保H_hard不可绕过 |
| AgentWeb向量时钟在大规模节点下性能下降 | 中 | 采用"向量时钟+摘要哈希"混合方案，定期压缩历史向量时钟 |
| EML-EHNN等变层实现复杂，可能引入数值不稳定 | 中 | 参考E(n)-Equivariant Neural Networks论文实现，添加梯度裁剪与数值稳定策略 |

---

## 6. 里程碑规划

| 阶段 | 时间 | 交付物 |
|------|------|--------|
| **Phase 1: HNC NLU管道** | Week 1-2 | `hnc_parser_wrapper.py`, `tomas_nlu_pipeline.py`, 修改`eml_injector.py` |
| **Phase 2: 哥德尔智能体安全架构** | Week 3-4 | `goedel_agent_tomas.py`, 修改`g_ego.py`/`ksnap_operator.py`/`pg_gate` |
| **Phase 3: Mina+Celo桥接** | Week 5 | `mina_kappa_bridge.py`, `celo_bridge.py` |
| **Phase 4: 因果世界模型** | Week 6-7 | `causal_world_model_tomas.py`, `aether_bridge.py`, 修改`hodge_operator.py` |
| **Phase 5: AgentWeb分布式时序** | Week 8-9 | `agentweb_runtime.py`, `vector_clock.py`, `fediverse_bridge.py`, `causal_delivery.py` |
| **Phase 6: EML-EHNN等变超图** | Week 10-11 | `eml_ehnn.py`, `equivariant_layers.py`, 修改`eml_semzip.py`/`gpct` |
| **Phase 7: 集成测试与优化** | Week 12 | 端到端测试、性能优化、文档完善 |

---

## 7. 成功指标

| 指标 | 目标值 |
|------|--------|
| HNC NLU管道解析准确率 | ≥85% (基于标准HNC测试集) |
| 哥德尔智能体自改进安全性 | 100% H_hard违规代码被拦截 |
| κ-Snap Mina证明生成时间 | <5秒/快照 |
| 向量时钟因果判断准确率 | 100% (无因果顺序错误) |
| EML-EHNN等变性测试通过率 | 100% (E(n)等变性验证) |
| 端到端系统响应时间 | <200ms (非证明生成操作) |

---

**文档结束** | 如有疑问请联系许清楚 (Product Manager)
