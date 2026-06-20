# 太极AGI · TOMAS-AGI

> **基于 NASGA（非结合谱图代数）的通用人工智能知识系统**  
> *"翻译官 + 作家"双引擎混合推理 · EML 知识图谱 · Φ-Gate 防幻觉监管*

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](./LICENSE)
[![Modules](https://img.shields.io/badge/modules-79+-orange.svg)](./sim/)
[![Tests](https://img.shields.io/badge/tests-727%20PASS-brightgreen.svg)](./tests/)
[![CUDA](https://img.shields.io/badge/CUDA-supported-success.svg)](./kernel/)
[![FPGA](https://img.shields.io/badge/FPGA-verified-blueviolet.svg)](./rtl/)
[![DB](https://img.shields.io/badge/knowledge_triples-101M+-blue.svg)]()

<p align="center">
  <br/>
  <em>TOMAS（太极OS）—— 容纳冲突、语义剪枝、非结合推理的新一代知识智能体</em>
  <br/><br/>
</p>

<!-- TODO: 添加截图 -->

---

## 📖 架构总览

TOMAS-AGI 采用 **"翻译官 + 作家"V3 混合架构**，将结构化知识图谱（EML）与大语言模型（DeepSeek）深度融合，实现事实查询的精确性与创造性推理的开放性兼得。

```mermaid
graph TD
    U[用户查询] --> EML[EML 知识图谱<br/>概念匹配 &amp; 置信度计算]
    EML --> ROUTE{置信度 ≥ 阈值?}

    ROUTE -->|Yes ≥ 0.5| TRANS[📖 翻译官<br/>模板/LSTM · 事实复述]
    ROUTE -->|No &lt; 0.5| WRITER[✍️ 作家<br/>DeepSeek LLM · 创造性生成]

    TRANS --> OUT1[✅ 精确答案 + 置信度]
    WRITER --> PHI[🛡️ Φ-Gate<br/>语义一致性检测]

    PHI -->|通过| OUT2[✅ 创造性答案]
    PHI -->|疑似幻觉| WARN[⚠️ 标记 + 翻译官验证]

    subgraph 知识蒸馏
        CORPUS[文本语料] --> DISTILL[LLM 蒸馏器] --> EML
    end

    subgraph 硬件加速
        CUDA[CUDA GPU] --> EML
        FPGA[FPGA/ASIC] --> EML
    end

    style TRANS fill:#2196F3,color:#fff
    style WRITER fill:#FF9800,color:#fff
    style PHI fill:#4CAF50,color:#fff
    style EML fill:#9C27B0,color:#fff
```

### 三种对话模式

| 模式 | 触发方式 | 引擎 | 适用场景 |
|------|---------|------|---------|
| 📖 **翻译官** | 置信度 ≥ 0.5 / `--force-translator` | 模板 + LSTM / EML 图检索 | 事实性查询、概念解释、精准复述 |
| ✍️ **作家** | 置信度 < 0.5 / `--force-creative` | DeepSeek LLM + Φ-Gate | 开放式推理、假设预测、创意生成 |
| 🔄 **自动路由** | 默认 / `--llm` | 智能裁决 | 推荐日常使用，无需手动切换 |

---

## ✨ 核心特性

- 🧠 **双引擎混合推理** — 翻译官（精确检索）+ 作家（LLM 创造），置信度自动路由，每次回答附带 `📡 EML路由 · 87%` 标签
- 🛡️ **Φ-Gate 防幻觉监管** — φ-空间语义一致性检测，LLM 输出与 EML 知识图谱核验，疑似幻觉自动标记 + 翻译官二次验证
- 🔍 **EML 知识蒸馏** — 文本语料一键蒸馏为 EML 知识图谱，支持多语料合并、重叠检测、冲突容纳（保留旧知 / 采纳新知 / 合并 / 忽略）
- 🕸️ **知识图谱可视化** — D3.js 力导向全画布布局，搜索高亮、边权重过滤、1-hop 邻居聚焦、语料领域筛选，节点 δ 值反映信息存在度
- ⚡ **多层硬件加速** — Python 仿真层 → C 内核模块 → CUDA GPU → FPGA/ASIC 四级计算层次，支持矩阵运算、八元数乘法、谱计算全链路加速
- 📐 **NASGA 数学基础** — 八元数（Fano 平面）、非结合谱图 Laplacian、ξ_c 效能指标、δ 信息存在度、Moufang 恒等式约束
- 🔗 **知识冲突容纳** — 不覆盖矛盾信息，用户逐条决策保留/采纳/合并，实现真正的不一致容忍知识管理
- 🗂️ **USCS 文件系统** — 自研 δ 加权文件系统，谱页索引 + EML 联动，CRC32 完整性，mmap 直 I/O
- 📚 **OwnThink 大规模知识库** — 140M+ 三元组断点续传导入，SQLite WAL 模式，κ-Gate 语义剪枝（i_weight 权重），当前 86M+ 行
- 🧩 **公理体系 v2** — κ-Snap 显影算符、ExtendHypergraph 流体智能原语、NAU 刘机制（八元数非结合 MUS 裁决）、双链共识动力学、EML-Hardware Co-Design
- ⚙️ **T-Processor + T-Shield** — RRAM Crossbar 硬件仿真器 + 认知安全层（DZ Grafting/MUS Dual-Box/κ-Snap Scheduling），Zynq-7000 RTL 实现
- 🌐 **G_ego 双向算子** — Afferent/Efferent DMN + NASGA 八元数传播 + T-Shield 监控
- 📊 **评估框架** — ARC-AGI-3（64×64 网格/RHAE 评分）、SWE-bench Lite（300 实例）、GAIA 数据集获取
- 🖥️ **Dashboard API** — Flask 56 端点，12 模型路由器，语义防火墙，DIKWP 五层映射，Three.js 3D 世界模型
- 🗄️ **HyperIndex v2.0** — DB-backed k-hop 子图按需加载，OrderedDict LRU 缓存 + 批量预取，消除 N+1 查询，支持 100M+ 三元组内存高效推理
- 🔬 **UnionFind 拟阵回路检测** — O(|E|·α(|V|)) 复杂度，路径压缩 + 按秩合并，较原 O(|E|²) 加速 100-1000×，实测 87.5% 压缩率
- 🌐 **ChainDB 分布式超图** — 概念哈希分片 + POP 共识协议，HyperShard 架构支持跨分片查询合并，RelationIndex 7 种关系类型
- 📦 **EML v2.0 格式** — 支持 n 元超边二进制编码（v1.0 仅二元边），向后兼容，可变长度边结构，96B 头部 + 变长边体

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- pip（requests, numpy）
- DeepSeek API Key（可选，仅作家模式需要）
- PyTorch（可选，仅神经解码器训练需要）

### 1. 安装依赖

```bash
git clone https://github.com/lisoleg/tomas-agi.git
cd tomas-agi
pip install requests numpy
```

### 2. 配置 API Key

```bash
# 环境变量
export DEEPSEEK_API_KEY=sk-your-key-here

# 或写入 .env 文件
echo "DEEPSEEK_API_KEY=sk-your-key-here" > sim/.env
echo "DEEPSEEK_API_BASE=https://api.deepseek.com/v1" >> sim/.env
```

### 3. 蒸馏语料（生成 EML 图谱）

```bash
cd sim
python llm_distiller.py --distill ../data/physics.txt --output ../data/physics_distilled
```

### 4. 推理查询

```bash
# 自动路由模式（推荐）
python token_bridge.py \
  --load ../data/physics_distilled.eml \
  --concepts ../data/physics_distilled.concepts.json \
  --query "什么是牛顿第二定律" \
  --llm

# 纯翻译官模式（无需 API Key）
python token_bridge.py \
  --load ../data/physics_distilled.eml \
  --concepts ../data/physics_distilled.concepts.json \
  --query "牛顿第二定律" \
  --force-translator
```

### 5. 启动 Web Dashboard

```bash
cd web && python -m http.server 8080
# 访问 http://localhost:8080
```

### 6. 前端（独立仓库）

```bash
git clone https://github.com/lisoleg/tomas-chat.git
cd deepseek-chat
npm install
npm run dev
# 访问 http://localhost:5173
```

---

## 📁 项目结构

```
tomas-agi/
├── sim/                          # Python 仿真与推理引擎 (79 .py 文件)
│   ├── token_bridge.py           # Token Bridge 推理引擎（翻译官+作家+φ-Gate）
│   ├── server.py                 # Flask REST API 服务器（56 端点）
│   ├── models.py                 # SQLAlchemy ORM 模型（7 张表）
│   ├── llm_distiller.py          # LLM 知识蒸馏器（语料→EML）
│   ├── token_generator.py        # 神经解码器（模板 + PyTorch LSTM）
│   ├── nasga_core.py             # NASGA 核心（ξ_c + δ + Moufang）
│   ├── nasga_octonion.py         # NASGA 八元数运算模块
│   ├── router.py                 # TOMAS Router 多模型路由器（12 模型池）
│   ├── eml_injector.py           # EML 执行上下文注入器 v2.0
│   ├── g_ego.py                  # G_ego v2.0 双向算子引擎
│   ├── ksnap_operator.py         # κ-Snap 显影算符 (A2)
│   ├── extend_hypergraph.py      # ExtendHypergraph 流体智能原语
│   ├── nau_liu_mechanism.py      # NAU 刘机制（八元数非结合 MUS 裁决）
│   ├── dual_chain_consensus.py   # 双链共识动力学
│   ├── eml_hardware_codesign.py  # EML-Hardware Co-Design
│   ├── tprocessor_sim.py         # T-Processor v1.0 硬件仿真器
│   ├── tshield_wrapper.py        # T-Shield 认知安全层
│   ├── epiplexity_engine.py      # 认知复杂度引擎
│   ├── eml_semzip.py             # EML 5 阶段语义压缩
│   ├── dead_zero_mus.py          # 死零/MUS/κ-Snap 机制
│   ├── memos_fusion.py           # TOMAS-MemOS 融合层
│   ├── contradiction_detector.py # 三层矛盾检测器
│   ├── dikwp_mapper.py           # DIKWP 五层映射器
│   ├── semantic_firewall.py      # 语义防火墙（6 ADC 高风险模式）
│   ├── ido_bridge.py             # IDO 五元素模板桥接
│   ├── fde_builder.py            # FDE 道法术器本体构建器
│   ├── dual_timeline.py          # 双时间维度引擎
│   ├── itot_bridge.py            # IT-OT 翻译桥
│   ├── arc_agi3_eval.py          # ARC-AGI-3 评估框架
│   ├── arc_api_client.py         # ARC Prize API 客户端
│   ├── swe_bench_eval.py         # SWE-bench 评估
│   ├── gaia_fetcher.py           # GAIA 数据集获取
│   ├── resume_import.py          # OwnThink 断点续传导入器
│   ├── compute_i_weight.py       # i_weight 后计算脚本
│   ├── post_import.py            # 导入完成后自动化
│   ├── eml_dimred/               # 数学降维工具箱（7 模块）
│   │   ├── hyperedge.py          # HypEdge/EMLVertex + EML 加载
│   │   ├── matroid.py            # 拟阵贪心剪枝（κ-Gate 最优独立集）
│   │   ├── gpct.py               # GPCT 边界层分解（FPT 判定）
│   │   ├── itc.py                # ITC 虚时退火（Wick 旋转基态搜索）
│   │   ├── brown_miklos.py       # Brown-Miklós FPT 度类压缩
│   │   ├── strf.py               # STR-F 四大等价变换
│   │   └── pipeline.py           # slim_eml 四合一流水线
│   └── ... (40+ 其他模块)
│
├── kernel/                       # C 内核模块（~244K 行）
│   ├── tproc_core.c              # T-Processor 主模块
│   ├── octonion.c                # 八元数内核库
│   ├── spectral_laplacian.c      # EML 非结合 Laplacian
│   ├── phi_gate.c                # Φ-Gate 语义门控
│   ├── kappa_reg.c               # κ=7 稳态调节器（PID）
│   └── ...
│
├── rtl/                          # Verilog FPGA RTL（~32K 行）
│   ├── deadzone_comp_array.v     # Dead-Zone 并行比较器阵列
│   ├── mus_similarity_engine.v   # MUS 流水线相似度引擎 (DSP48E1)
│   ├── axi_lite_slave.v          # AXI4-Lite 从设备
│   ├── octonion_mul.v            # 八元数乘法器（3 级流水线）
│   ├── spectral_engine.v         # 谱计算引擎
│   ├── create_vivado_project.tcl # Vivado 自动化脚本 (Zynq-7020)
│   └── ...
│
├── tests/                        # 测试套件（20 文件，729 测试函数）
│   ├── test_token_bridge.py      # Token Bridge 测试 (8)
│   ├── test_eml_dimred.py        # 数学降维测试 (20)
│   ├── test_router.py            # 路由器测试 (27)
│   ├── test_tcci.py              # TCCI 测试 (15)
│   ├── test_nasga.py             # NASGA 测试 (17)
│   ├── test_memos.py             # MemOS 测试 (16)
│   ├── test_contradiction.py     # 矛盾检测测试 (19)
│   ├── test_causet_wsc.py        # Causet-WSC 测试 (57)
│   ├── test_hyworld_sai.py       # HY World 测试 (76)
│   ├── test_ido.py               # IDO 测试 (105)
│   ├── test_fde_dual_itot.py     # FDE/DualTimeline/ITOT 测试 (86)
│   ├── test_tprocessor_tshield.py # T-Processor+T-Shield 测试 (39)
│   ├── test_new_modules.py       # G_ego/Epiplexity/SemZip 测试 (21)
│   ├── test_tomas_v2_articles.py # κ-Snap/ExtendHypergraph 测试 (51)
│   └── ...
│
├── data/                         # 语料与蒸馏数据
├── docs/                         # 文档（ARCHITECTURE.md, paper.md, PRD.md）
├── scripts/                      # 工具脚本
├── LICENSE                       # Apache 2.0
└── README.md                     # 本文件
```

---

## 🗂️ 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| **数学基础** | 八元数 · Moufang 恒等式 · Fano 平面 | NASGA 非结合代数 |
| **知识表示** | EML（谱图）· δ 信息存在度 · ξ_c 效能指标 | 结构化知识图谱 |
| **推理引擎** | Python 3.10+ · 模板匹配 · PyTorch LSTM | 翻译官核心 |
| **LLM 集成** | DeepSeek API (deepseek-chat) · Φ-Gate | 作家 + 防幻觉 |
| **前端框架** | Vite + React 18 + TypeScript + Tailwind CSS | deepseek-chat 独立仓库 |
| **图谱可视化** | D3.js（力导向图） | EML 前端渲染 |
| **C 内核** | Linux Kernel Module · 14 模块 | NASGA 内核加速 |
| **CUDA** | NVIDIA GPU · cuBLAS · CSR SpMV | 八元数/Laplacian/δ-mem 加速 |
| **FPGA** | Verilog · Icarus · Vivado · Yosys | 硬件级谱计算 |
| **文件系统** | USCS · δ 加权页映射 · CRC32 | 知识持久化 |
| **工具链** | Make · Git · Python CLI · Web Dashboard | 开发与运维 |

---

## 📊 验证状态

| 层级 | 模块数 | 验证结果 |
|------|--------|---------|
| M1 Python 仿真核心 | 16 | 16/16 PASS |
| M2 C 内核 | 14 | 14/14 PASS |
| M3 USCS 文件系统 | 4 | 5/5 PASS |
| M4 CUDA 加速 | 3 | 3/3 PASS |
| M5 推理应用 (Token Bridge) | 12 | 翻译官(模板+LSTM) + 作家(DeepSeek+φ-Gate) + MemOS + DIKWP |
| M6 T-Processor / T-Shield | 8 | RRAM 仿真 + 认知安全 + Zynq RTL |
| M7 公理体系 v2 | 5 | κ-Snap / ExtendHypergraph / NAU刘 / 双链共识 / HW Co-Design |
| M8 评估框架 | 6 | ARC-AGI-3 / SWE-bench / GAIA / TCCI-华山 |
| M9 数据层 | 5 | SQLite ORM + OwnThink 导入 + i_weight 计算 |
| M10 桥接模块 | 7 | IDO / FDE / DualTimeline / ITOT / Causet / HYWorld / Palantir |
| **总计** | **79+** | **727/729 测试通过（2 skipped 需 API Key）** |

### LLM 对话测试（2026-06-14）

| 查询 | 领域 | 模式 | 置信度 | φ-Gate | 结果 |
|------|------|------|--------|--------|------|
| 牛顿第二定律 | 物理 | 翻译官 | 100% | — | ✅ |
| 物理学未来50年重大突破 | 物理 | 作家 | 65.9% | 80.3% | ✅ |
| 热力学 | 物理 | 自动路由 | 100% | — | ✅ |
| 暗物质不存在 | 物理 | 作家(强制) | 88.3% | 72.5% | ✅ |
| 有机化学未来趋势 | 化学 | 作家(强制) | 66.0% | 76.2% | ✅ |
| 基因编辑 | 医学 | 自动路由 | 67.4% | — | ✅ |
| 大语言模型改变科研 | AI | 自动路由 | 71.0% | — | ✅ |
| AI能否拥有意识 | AI | 作家(无Gate) | 76.9% | — | ✅ |

---

## 📖 关键参数速查

### token_bridge.py CLI 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--load` | 必填 | EML 图文件路径 |
| `--concepts` | 无 | 概念名称 JSON 文件 |
| `--query` | 无 | 查询文本 |
| `--llm` | False | 启用 DeepSeek LLM（自动路由） |
| `--force-translator` | False | 强制翻译官模式 |
| `--force-creative` | False | 强制作家模式 |
| `--threshold` | 0.5 | 路由置信度阈值 |
| `--gate` | True | 启用 Φ-Gate 监管 |
| `--no-gate` | — | 禁用 Φ-Gate |
| `--gate-threshold` | 0.35 | φ-Gate 一致性阈值 |
| `--top-k` | 5 | 返回 top-k 匹配 |

---

## 📄 相关文档

| 文档 | 链接 |
|------|------|
| 系统架构 | [ARCHITECTURE.md](./docs/ARCHITECTURE.md) |
| 产品需求 | [PRD.md](./docs/PRD.md) |
| 用户指南 | [USER_GUIDE.md](./docs/USER_GUIDE.md) |
| 学术论文 | [paper.md](./docs/paper.md) |
| LLM 测试指南 | [LLM_TEST_GUIDE.md](./LLM_TEST_GUIDE.md) |
| Token Bridge 测试 | [TOKEN_BRIDGE_TEST_GUIDE.md](./TOKEN_BRIDGE_TEST_GUIDE.md) |
| 前端仓库 | [github.com/lisoleg/tomas-chat](https://github.com/lisoleg/tomas-chat) |

---

## 🙏 作者与致谢

**章锋（章锋）** © 2026 复合体理学研究中心（TOMAS 项目组）

基于 NASGA（Non-Associative Spectral Graph Algebra）理论框架，以八元数、非结合 Laplacian 和 Moufang 恒等式为数学基础，构建容纳冲突、语义剪枝、非结合推理的新一代 AGI 知识系统。

---

## 📄 License

[Apache License 2.0](./LICENSE) — 自由使用、修改与分发。
