# TOMAS-AGI v2.0 — 产品需求文档（PRD）

> **状态**: 执行中 | **版本**: v2.0 (V3 混合推理) | **更新**: 2026-06-14
>
> 作者：章锋（章锋） | **许可证**: Apache 2.0
> © 2026 复合体理学研究中心（TOMAS 项目组）

---

## 1. 产品目标

构建基于 NASGA（非结合谱图代数）的通用人工智能框架，实现以下核心能力：

1. **悖论耐受推理**: 通过谱投影分歧态，系统能在矛盾信息共存时维持有界 δ 而不塌缩
2. **双分支协同**: 经典推理（Branch A）与量子推理（Branch B）并行运行，经由 κ=7 稳态融合
3. **万有理论替代**: 证明纯结合 TOE 不可能，提供基于信息存在度（I(X)）的互斥理论稳态（MUS）
4. **硬件加速**: 从 CPU 内核模块 → CUDA GPU → FPGA/ASIC 的完整硬件加速链

### 1.1 用户故事

- **研究者（章锋/李宗海）**: 需要能验证 δ 守恒（A1 公理）、谱图动力学、非结合代数计算正确性的完整仿真环境
- **OSDI 评审者**: 需要清晰展示从数学框架到工程实现的端到端论证链路
- **未来开发者**: 需要模块化的、接口清晰的代码库，支持增量开发和独立验证

---

## 2. 需求池

### P0（必须完成 — M1-M5 已完成）

| ID | 需求 | 状态 | 里程碑 |
|----|------|------|--------|
| P0-01 | δ 参数定义与计算 | ✅ fold_depth_py.py | M1 |
| P0-02 | A1 公理（δ 守恒）校验 | ✅ fold_depth_py.py | M1 |
| P0-03 | δ_threshold 条件（悖论耐受判断） | ✅ fold_depth_py.py | M1 |
| P0-04 | 八元数 Fano 乘法表（C 内核 + Python） | ✅ octonion.c + octonion_py.py | M1+M2 |
| P0-05 | 非结合 associator 计算 | ✅ nasga_core.py + octonion.c | M1+M2 |
| P0-06 | EML 非结合 Laplacian（含 associator 修正） | ✅ spectral_laplacian.c + .py | M1+M2 |
| P0-07 | T-Processor 主模块（δ 参数 + ioctl） | ✅ tproc_core.c | M2 |
| P0-08 | κ=7 稳态调节器（PID + 前馈 + I抗饱和） | ✅ kappa_reg.c | M2 |
| P0-09 | Φ-Gate 语义门控（八状态机） | ✅ phi_gate.c | M2 |
| P0-10 | δ-mem L1-L2 融合 | ✅ delta_mem.c | M2 |
| P0-11 | CI Gate 因果隔离 | ✅ ci_gate.c | M2 |
| P0-12 | ST Auditor 倾斜审计 | ✅ st_auditor.c | M2 |
| P0-13 | USCS 文件系统（挂载/inode/文件/mmap） | ✅ uscsfs/ | M3 |
| P0-14 | LLM 知识蒸馏器（语料→EML 图） | ✅ llm_distiller.py | M5 |
| P0-15 | Token Bridge 推理引擎 | ✅ token_bridge.py | M5 |
| P0-16 | CreativeEngine（DeepSeek LLM 作家） | ✅ token_bridge.py | M5 |
| P0-17 | PhiGate φ-监管器 | ✅ token_bridge.py | M5 |
| P0-18 | 翻译官/作家自动路由 | ✅ token_bridge.py | M5 |
| P0-19 | D3.js EML 图谱可视化 | ✅ EMLGraphVisualization.tsx | M5 |

### P1（高优先级 — 部分完成）

| ID | 需求 | 状态 | 里程碑 |
|----|------|------|--------|
| P1-01 | CUDA GPU 八元数乘法 | ✅ cuda_octonion.cu | M4 |
| P1-02 | CUDA GPU Laplacian 谱计算 | ✅ cuda_laplacian.cu | M4 |
| P1-03 | CUDA GPU δ-mem 融合加速 | ✅ cuda_delta_mem.cu | M4 |
| P1-04 | A6-BS v2.0 Cold-Start 基准测试 | ✅ a6_bs_benchmark.py --v2 | M1 |
| P1-05 | 系统架构文档 | ✅ docs/ARCHITECTURE.md | 文档 |
| P1-06 | 学术论文 | ✅ docs/paper.md | 文档 |
| P1-07 | 多领域语料蒸馏（物理+化学+医学） | ✅ llm_distiller.py | M5 |
| P1-08 | 神经解码器（LSTM φ→token） | ✅ token_generator.py | M5 |
| P1-09 | 浏览器端 Token Bridge SDK | ✅ distiller.ts | M5 |
| P1-10 | FPGA/ASIC 八元数硬件单元 RTL | ⬜ | M6 |
| P1-11 | 用户态 CLI 工具（uscsctl） | ⬜ | M7 |
| P1-12 | 完整内核编译/加载自动化脚本 | ⬜ | M2+ |

### P2（中等优先级 — 未来迭代）

| ID | 需求 | 状态 |
|----|------|------|
| P2-01 | CI/CD 自动测试流水线 | ⬜ |
| P2-02 | OSDI 论文 LaTeX 模板对齐 | ⬜ |
| P2-03 | 性能基准（CPU vs GPU vs FPGA 延迟对比） | ⬜ |
| P2-04 | 可视化 Dashboard（δ 演化、κ 锁定、域分类） | ⬜ |
| P2-05 | 分布式 T-Processor 集群调度 | ⬜ |
| P2-06 | DeepSeek API 集成回归测试 | ⬜ |

---

## 3. UI/交互设计

当前为纯命令行界面（CLI），不涉及 GUI：

```
$ python tomas_sim.py --mode full

============================================================
  太乙互搏 AGI（TOMAS-AGI）— 主模拟器 v2.0
============================================================
[OK] octonion_py
[OK] spectral_laplacian_py
[OK] nasga_core
[OK] fold_depth_py
[OK] a6_bs_benchmark
[OK] xi_c_measure

============================================================
[测试] Octonion（八元数）
============================================================
  Fano 乘法表: [PASS]
  范数乘积: [PASS]
  [PASS] Octonion 模块

...

总体: [6/6 通过]
```

---

## 4. 待确认问题

1. **OSDI 论文截稿日期** — 需要明确时间节点以便安排论文对码验证的优先级
2. **GPU 硬件环境** — M4 CUDA 模块需要 NVIDIA GPU（CC≥6.0），开发机是否具备？
3. **FPGA 开发板** — M5 RTL 需要 Xilinx/Altera 板卡，预算和选型？
4. **内核版本** — M2 内核模块的目标 Linux 内核版本（建议 5.10+ / 6.1+）？
5. **论文署名确认** — 当前署名为章锋、李宗海，是否需要增删？

---

## 5. 里程碑完成度

| 里程碑 | 描述 | 模块数 | 状态 | 代码量 |
|--------|------|--------|------|--------|
| M1 | Python 仿真层 | 7 文件 | ✅ v2.0 | ~80K |
| M2 | Linux 内核模块 | 10 模块 | ✅ | ~244K |
| M3 | USCS 文件系统 | 4 模块 | ✅ | ~70K |
| M4 | CUDA GPU 加速 | 3 模块 | ✅ | ~70K |
| **总计** | | **24** | **✅** | **~464K** |

---

## 6. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| CUDA 编译器不可用 | 中 | 低 | Python 等价测试可独立运行 |
| 内核模块在目标内核上编译失败 | 低 | 中 | 提供 Makefile + Kconfig 模板 |
| δ 理论推导与代码实现不一致 | 低 | 高 | Python 等价测试 + A1/A6 基准交叉验证 |
| OSDI 论文时间冲突 | 中 | 高 | 提前进行"对码验证"（理论↔实现对齐） |
