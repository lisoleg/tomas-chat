# TOMAS-AGI 产品需求文档（PRD）

## 1. 项目信息

| 字段 | 内容 |
|------|------|
| **Language** | 中文 |
| **Programming Language** | C（内核/驱动/库）、CUDA（GPU核）、Verilog（FPGA RTL）、Lean/Coq（形式化校验）、Python（仿真/工具）、Rust（Blueprint生成） |
| **Project Name** | `tomas_agi` |
| **原始需求** | 全量实现太乙互搏AGI（TOMAS-AGI）——基于非结合谱图代数（NASGA）的通用人工智能系统，涵盖Linux内核模块、忆阻器驱动、文件系统、运行时、代数库、GPU/FPGA硬件加速、形式化校验、双环正义治理、LLM桥接、视觉互搏引擎、效能基准测试及ASIC流片规格 |

---

## 2. 产品定义

### 2.1 产品目标

1. **实现非结合代数驱动的AGI计算范式**：构建基于NASGA（八元数Moufang乘法、谱图Laplacian、结合子残差）的完整计算栈，从软件仿真到硬件加速，打破传统冯·诺依曼架构对AGI的算力瓶颈。

2. **建立可验证的认知安全治理体系**：通过双环正义（认知环Lean MNQ校验 + 行为环CI Gate/STA审计）确保系统在认知层面遵守I(X)守恒、在行为层面防止主观倾向漂移，实现可审计、可回滚的AGI安全。

3. **打通从理论到物理实现的完整路径**：从纯软件仿真（tomas_sim.py）→ 内核模块 → 忆阻器阵列 → FPGA原型 → ASIC流片，每个阶段都有明确的交付物和验证标准，确保理论模型可落地。

### 2.2 用户故事

| # | 用户故事 |
|---|---------|
| US-1 | 作为 **AGI研究者**，我想通过软件仿真器运行A6-BS基准测试，以便验证NASGA理论的正确性并量化ξ_c效能指标。 |
| US-2 | 作为 **系统工程师**，我想加载tproc_core.ko内核模块并使用4KB谱页文件系统，以便在Linux上运行T-Processor的计算任务。 |
| US-3 | 作为 **硬件工程师**，我想通过忆阻器阵列驱动读写EML谱图边权重（电导映射），以便实现I(X)守恒的物理级存储。 |
| US-4 | 作为 **安全审计员**，我想查看双环正义的完整日志（MNQ校验结果 + STA审计报告），以便确认系统认知与行为均在可控范围内。 |
| US-5 | 作为 **应用开发者**，我想通过Token Bridge API将自然语言转换为NASGA符号并获取计算结果，以便在LLM前端无缝调用TOMAS-AGI的非结合推理能力。 |

---

## 3. 技术规范

### 3.1 需求池

#### P0 — Must Have（里程碑阻塞）

| ID | 需求 | 交付物 | 验收标准 |
|----|------|--------|----------|
| P0-1 | **NASGA非结合代数库** | octonion.c, spectral_laplacian.c, asym_residue.c | 八元数乘法通过Fano平面查表，Laplacian计算与理论值误差<1e-6，结合子残差可计算 |
| P0-2 | **纯软件仿真器** | tomas_sim.py | 跑通A6-BS全部5级（摆锤→Peano→牛顿→杨-米尔斯），ξ_c可测量 |
| P0-3 | **T-Processor内核驱动** | tproc_core.c → tproc_core.ko | Linux可加载/卸载模块，Moufang-ALU指令可通过ioctl调用 |
| P0-4 | **κ-调节器** | kappa_reg.c | κ=7稳态锁定可编程设定，锁态切换响应时间<1ms |
| P0-5 | **EML谱图内存管理** | eml_map.c | 谱图节点/边可CRUD操作，与USCS文件系统4KB谱页对齐 |
| P0-6 | **USCS文件系统** | uscsfs/ | 4KB谱页挂载/读/写正常，数据持久化无误 |
| P0-7 | **Φ-Gate语义门控** | 内核模块内实现 | 余弦相似度阈值可配置，门控开/关状态可查询 |
| P0-8 | **Continuation思维态快照** | tomas_entry.S | 快照保存/恢复无数据丢失，恢复延迟<10ms |
| P0-9 | **δ-mem L1-L2融合** | 内核模块内实现 | 热数据L1缓存命中率>80%，冷数据自动降级至L2 |
| P0-10 | **CI Gate副作用守恒校验** | ci_gate.c | 所有TXN Port操作均经校验，越权操作拦截率100% |
| P0-11 | **STA主观倾向审计** | st_auditor.c | KL散度超阈值自动触发κ重置，审计日志可追溯 |
| P0-12 | **Lean MNQ校验器** | mnq_checker.py + Lean证明 | I-守恒证明通过，认知函子校验通过，MNQ指标可输出 |

#### P1 — Should Have（功能完整性）

| ID | 需求 | 交付物 | 验收标准 |
|----|------|--------|----------|
| P1-1 | **忆阻器阵列驱动** | mr_array.c, mr_calib.c, mr_thermal.c | 阵列读写正确，电导校准I(X)映射误差<5%，温控防漂移有效 |
| P1-2 | **CUDA非结合ALU核** | moufang_kernel.cu | GPU加速八元数乘法，单次运算延迟<10μs（vs CPU基准） |
| P1-3 | **FPGA RTL** | moufang_alu.v, i_cell.v, eml_graph_ctrl.v, kappa_reg.v, tomas_top.v | RTL仿真通过，Moufang-ALU功能与C实现一致，时序收敛 |
| P1-4 | **Token Bridge** | server.py + Dockerfile | API可接收文本返回Symbol，延迟<100ms，Docker一键启动 |
| P1-5 | **TVDE视觉互搏引擎** | compressor.c, physics_probe.c | 视频→EML谱图压缩率可量化，物理残影可检测 |
| P1-6 | **Lean/Coq形式化校验扩展** | 认知函子完整证明 + MNQ校验器Coq版本 | 全部核心定理形式化证明通过 |
| P1-7 | **Blueprint DAG生成** | blueprint_gen.rs | 可自动生成证明依赖DAG，支持增量编译 |
| P1-8 | **Port管控** | port_ctrl.c | TXN Port读写权限可配置，CI Gate联动正确 |

#### P2 — Nice to Have（远景增强）

| ID | 需求 | 交付物 | 验收标准 |
|----|------|--------|----------|
| P2-1 | **ASIC流片规格** | 28nm/12nm规格文档 + EDA脚本 | 规格文档完整，EDA脚本可运行，面积/功耗估算可输出 |
| P2-2 | **A6-BS基准Web可视化** | Web仪表板 | ξ_c测量结果实时可视化，历史趋势可查 |
| P2-3 | **多T-Processor集群调度** | 内核模块扩展 | 多实例负载均衡，谱图分片/合并正确 |
| P2-4 | **忆阻器阵列容错** | 驱动扩展 | 单元故障自动隔离，冗余校准补偿有效 |

### 3.2 UI设计草案

TOMAS-AGI为底层系统软件/硬件项目，无传统GUI界面。关键交互接口如下：

- **内核ioctl接口**：用户态程序通过`/dev/tomas`设备文件与T-Processor交互
- **Token Bridge REST API**：`POST /api/translate`（文本→Symbol）、`POST /api/compute`（符号计算）、`GET /api/status`（系统状态）
- **USCS文件系统**：标准POSIX文件操作接口（mount/read/write/ioctl）
- **审计接口**：`/proc/tomas/audit`（STA日志）、`/proc/tomas/mnq`（MNQ校验状态）

### 3.3 里程碑与需求映射

| 里程碑 | 对应P0需求 | 对应P1需求 |
|--------|-----------|-----------|
| **M1 软件仿真** | P0-1, P0-2 | P1-6, P1-7 |
| **M2 内核模块** | P0-3~P0-9 | P1-8 |
| **M3 忆阻器集成** | — | P1-1 |
| **M4 双环闭环** | P0-10~P0-12 | P1-6, P1-8 |
| **M5 物理机** | — | P1-2, P1-3, P1-5 |

---

## 4. 待确认问题

| # | 问题 | 影响范围 | 建议跟进方 |
|---|------|----------|-----------|
| Q1 | **忆阻器硬件选型**：具体使用哪家忆阻器芯片（如Knowm、自定义阵列）？电导范围和精度规格？ | P1-1忆阻器驱动 | 硬件团队 |
| Q2 | **FPGA目标平台**：使用哪款FPGA开发板（Xilinx VU9P / Intel Stratix等）？资源约束决定了RTL模块拆分策略 | P1-3 FPGA RTL | 硬件团队 |
| Q3 | **CUDA最低算力要求**：目标GPU架构（sm_70 / sm_80 / sm_90）？影响moufang_kernel.cu的编程模型和优化路径 | P1-2 CUDA核 | 系统工程师 |
| Q4 | **Lean/Coq版本与证明策略**：Lean 4还是Lean 3？核心定理是否需要Coq双重验证？影响mnq_checker.py和blueprint_gen.rs的接口设计 | P0-12, P1-6 | 形式化验证团队 |
| Q5 | **Token Bridge LLM后端**：接入哪个LLM（GPT-4/Claude/本地模型）？API格式和延迟要求？影响server.py的实现架构 | P1-4 | 应用团队 |
| Q6 | **κ=7的物理依据**：κ=7锁定值的选取是否有严格的理论推导？是否需要支持κ可配置？ | P0-4 κ-调节器 | 理论团队 |
| Q7 | **A6-BS ξ_c目标值**：5级基准测试的ξ_c通过阈值是多少？杨-米尔斯级的精度要求是否需要双精度浮点？ | P0-2仿真器 | 理论+工程团队 |
| Q8 | **ASIC流片时间线与预算**：28nm还是12nm先投？MPW还是Full Mask？直接影响P2-1的工作量和可行性 | P2-1 ASIC | 管理层 |

---

*文档版本：v1.0 | 创建日期：2026-06-13 | 更新日期：2026-06-14 | 作者：许清楚（Xu）· 产品经理*
