# 太极AGI · TOMAS-AGI

> 基于 NASGA（非结合谱图代数）的通用人工智能框架  
> **翻译官 + 作家** 双引擎混合推理 · EML 知识图谱 · D3.js 可视化

[![deepseek-chat](https://img.shields.io/badge/frontend-deepseek--chat-cyan?style=flat)](https://github.com/lisoleg/tomas-chat)
[![tomas-agi](https://img.shields.io/badge/backend-tomas--agi-orange?style=flat)](https://github.com/lisoleg/tomas-agi)

---

## 🌟 项目简介

太极AGI 是一款将**结构化知识图谱（EML）** 与 **大语言模型（LLM）** 深度融合的 AI 系统。核心创新是"翻译官 + 作家"混合架构：

| 模式 | 触发条件 | 行为 |
|------|------------|------|
| **翻译官** | 置信度 ≥ 0.5 | 从 EML 知识图谱中精确检索答案（事实性查询） |
| **作家** | 置信度 < 0.5 | 交由 DeepSeek LLM 创造性回答（辅以 EML 上下文增强） |

系统自动计算置信度并完成路由裁决，用户无需手动切换。

---

## 📦 仓库结构

本项目采用**两个独立仓库**，分别对应前端和后端：

```
tomas-agi/              ← 后端（Python）：LLM 蒸馏器、Token Bridge 推理引擎
├── sim/                ← Python 仿真环境（llm_distiller.py, token_bridge.py ...）
├── kernel/             ← C 内核模块（八元数、δ-记忆、Φ-Gate ...）
├── rtl/                ← Verilog 硬件加速
├── data/               ← 语料文件 + 蒸馏后的 EML 图谱
└── docs/               ← 系统架构、PRD、用户指南

deepseek-chat/          ← 前端（TypeScript + React）：聊天 UI、知识图谱可视化
├── src/components/      ← React 组件（蒸馏面板、EML 图谱、知识浏览 ...）
├── src/api/            ← TokenBridgeClient + DeepSeek API
├── public/             ← 预蒸馏的 EML 图谱（*.eml）
└── docs/               ← 前端架构文档
```

- 🔗 前端仓库：[github.com/lisoleg/tomas-chat](https://github.com/lisoleg/tomas-chat)
- 🔗 后端仓库：[github.com/lisoleg/tomas-agi](https://github.com/lisoleg/tomas-agi)

---

## ✨ 核心功能

### 💬 双引擎推理
- 自动路由：置信度 ≥ 0.5 → 翻译官（EML 精确检索），< 0.5 → 作家（LLM 创造性回答）
- **对话意图检测**：自动识别问候/身份/闲聊查询，强制走LLM作家路径（避免无意义EML检索）
- 置信度透明化：每次回答附带置信度标签（如 `📡 EML路由 · 87%`）
- 用户反馈：点赞/点踩按钮，用于改进路由策略

### 🔍 EML 知识蒸馏
- 文本语料 → EML 知识图谱一键蒸馏
- 自动检测新语料与已有知识的**重叠和冲突**
- 冲突处理：**容纳冲突而非覆盖**——用户逐条决策（保留旧知 / 采纳新知 / 合并 / 忽略）

### 🕸️ 知识图谱可视化
- D3.js 力导向图，实时展示 EML 知识图谱
- **全画布布局**：图谱铺满整个可视区域
- **搜索高亮**：输入关键词实时高亮匹配节点
- **边权重过滤**：滑块动态过滤弱关联边，降低视觉干扰
- **点击高亮邻居**：点击某节点，聚焦其 1-hop 邻居子图
- **语料过滤**：多语料场景下，切换查看特定领域的子图
- 节点大小反映信息存在度（δ 值），悬浮查看详细信息

### 📚 知识浏览
- 概念与关系分列为**两个独立列表**
- 点击任一知识项，图谱自动聚焦对应的子图
- **概念名称优化**：从OwnThink数据库自动加载中文概念名称（修复EML二进制格式不存储名称的问题）

### 📄 技术文档
- 内置技术文档 Tab，实时查看系统架构
- 涵盖：项目概述、系统架构、EML 知识图谱原理、双环治理、技术栈

### 🖥️ 系统监控面板
- **T-Processor面板**：监控T-Processor硬件仿真器（死零审计/MUS触发/κ-Snap切片）
- **T-Shield面板**：监控T-Shield认知安全层（ℐ-Scene场景/G_ego模式切换/处理流）
- **AEGIS面板**：监控AEGIS演进引擎（Digester/Planner/Evolver/Critic+Gate流水线状态）
- **Dashboard仪表盘**：8子系统状态卡片 + 活动时间线 + 面板跳转

---

## 🚀 快速开始

### 系统要求

- **前端**：Node.js 22+（推荐 22.22.2）
- **后端**：Python 3.10+（推荐 3.13）
- **数据库**：SQLite 3（内置）

### 1. 启动后端（Flask API 服务器）

```bash
cd tomas_agi/sim
pip install flask flask-cors  # 首次使用需安装依赖
python server.py
# 服务器启动在 http://localhost:5000
```

**验证后端是否正常运行**：
```bash
curl http://localhost:5000/api/health
# 预期输出：{"status": "ok", "db": "..."}
```

### 2. 启动前端（Vite + React）

```bash
cd deepseek-chat
npm install
npm run dev
# 默认启动在 http://localhost:5173
```

**注意**：前端依赖后端 API，请确保后端已先启动。

### 3. 验证系统

1. 打开浏览器访问 `http://localhost:5173`
2. 系统会自动加载默认 EML 图谱（如已蒸馏）
3. 在聊天框输入问题，测试双引擎推理

生产构建：
```bash
cd deepseek-chat
npm run build
npm run preview   # 预览生产构建
```

#### 蒸馏语料（生成 EML 图谱）

```bash
cd tomas_agi
python sim/llm_distiller.py \
  --distill data/physics.txt \
  --output data/physics_distilled.eml \
  --api-key sk-your-key
```

#### 启动 Token Bridge 推理

```bash
python sim/token_bridge.py \
  --load data/physics_distilled.eml \
  --concepts data/physics_distilled.concepts.json \
  --query "什么是牛顿第二定律" \
  --llm --api-key sk-your-key
```

---

## ⚙️ 配置

### DeepSeek API Key

在 `tomas_agi/sim/.env` 中配置：
```
DEEPSEEK_API_KEY=sk-your-key-here
```

或在前端蒸馏面板的设置面板中填写。

### 路由置信度阈值

默认阈值 0.5，可在 `deepseek-chat/src/hooks/useChat.ts` 中调整：
```typescript
const CONFIDENCE_THRESHOLD = 0.5
```

---

## 📖 使用指南

### 第一次使用
1. 启动前端后，系统会自动加载默认的 EML 图谱（如已蒸馏）
2. 在聊天框输入问题，系统会自动路由到翻译官或作家
3. 查看消息下方的置信度标签，了解答案来源

### 蒸馏新语料
1. 点击左侧边栏的 **蒸馏器** 标签
2. 粘贴文本语料（或上传 `.txt` 文件）
3. 点击 **蒸馏** 按钮，等待处理完成
4. 如有冲突，系统会提示决策（默认可忽略，不影响使用）
5. 蒸馏完成后，图谱可视化自动更新

### 查看知识图谱
1. 在蒸馏面板中切换到 **🕸️ 图谱可视化** Tab
2. 鼠标拖动可平移，滚轮缩放
3. 点击节点选中，右侧知识浏览面板显示详细信息
4. 使用搜索框高亮特定节点
5. 调节边权重阈值滑块过滤弱关联边

### 监控系统状态
1. 点击左侧边栏的 **仪表盘** 标签查看系统整体状态
2. 点击 **T-Processor** 标签监控硬件仿真器
3. 点击 **T-Shield** 标签监控认知安全层
4. 查看各子系统的实时统计信息和活动日志

---

## 💾 数据存储（v3.2+）

系统已将数据存储从浏览器 `localStorage` 迁移至 **SQLite 数据库**，提供更可靠、可扩展的持久化方案。

### 存储架构

| 数据类型 | 存储位置 | 说明 |
|----------|----------|------|
| 语料条目 | SQLite `corpus_entries` 表 | 替代 `localStorage['tomas_corpus_entries']` |
| 知识三元组 | SQLite `knowledge_triples` 表 | OwnThink 格式（subject, predicate, object） |
| 聊天会话 | SQLite `chat_sessions` 表 | 替代 `localStorage['tomas_chat_sessions']` |
| 设置项 | SQLite `settings` 表 | 替代 `localStorage['tomas_settings']` |
| EML 图谱 | 文件系统 `data/*.eml` | 保持不变 |

### 后端 API

数据通过 **Flask RESTful API**（`localhost:5000`）与前端的通信：

```bash
# 启动后端服务器
cd tomas_agi/sim
python server.py
# API 文档：http://localhost:5000/api/health
```

**主要端点**：
- `GET/POST/DELETE /api/corpus` — 语料管理
- `GET/POST/DELETE /api/knowledge/triples` — 知识三元组
- `GET/POST/DELETE /api/sessions` — 聊天会话
- `GET/POST /api/settings` — 设置

### 批量数据导入

支持大规模知识图谱数据（如 OwnThink 141M 行）的高效导入：

```bash
# 导入样本数据
python sim/batch_import.py --input data/ownthink_sample.csv

# 导入全量数据（141M 行）
python sim/batch_import.py --input D:/ownthink_v2/ownthink_v2.csv --batch-size 5000

# 验证导入结果
python sim/batch_import.py --verify
```

**性能**：
- 批量 INSERT（默认 1000 行/批）
- 流式读取（不加载整个文件到内存）
- 实时进度显示（已处理/总行数、速度、ETA）
- 导入速度：~20,000 行/秒（HDD），~50,000 行/秒（SSD）

### 数据库文件

- 路径：`tomas_agi/data/tomas.db`
- 格式：SQLite 3
- 可手动备份/恢复（直接复制 `.db` 文件）
- 支持 SQLite 命令行工具查询

```bash
# 查询数据库
sqlite3 tomas_agi/data/tomas.db "SELECT COUNT(*) FROM knowledge_triples;"

# 备份数据库
cp tomas_agi/data/tomas.db tomas_agi/data/tomas_backup.db
```

---

## 🗂️ 技术栈

| 层级 | 技术 |
|------|------|
| **前端框架** | Vite + React 18 + TypeScript |
| **前端样式** | Tailwind CSS |
| **图谱可视化** | D3.js（力导向图） |
| **LLM** | DeepSeek API (v1) |
| **后端语言** | Python 3.10+ |
| **后端内核** | C (八元数、δ-记忆、Φ-Gate) |
| **硬件加速** | CUDA GPU → FPGA/ASIC |
| **状态管理** | React Hooks（useReducer + useRef） |
| **构建工具** | Vite（HMR + TypeScript 编译） |

---

## 📄 相关文档

- [前端架构](https://github.com/lisoleg/tomas-chat/blob/main/docs/ARCHITECTURE.md)
- [前端 PRD](https://github.com/lisoleg/tomas-chat/blob/main/docs/PRD.md)
- [后端架构](https://github.com/lisoleg/tomas-agi/blob/main/docs/ARCHITECTURE.md)
- [后端 PRD](https://github.com/lisoleg/tomas-agi/blob/main/docs/PRD.md)
- [用户指南](https://github.com/lisoleg/tomas-agi/blob/main/docs/USER_GUIDE.md)
- [学术论文](https://github.com/lisoleg/tomas-agi/blob/main/docs/paper.md)

---

## 🧠 AEGIS 演进引擎（v3.5 新增）

AEGIS = **ExtendHypergraph on Config Space**，是 TOMAS 的自动演进引擎，基于微信公众号文章《HarnessX作为太乙互搏 AGI 具身壳与 PG-Gate 可编程接口》（章锋，2026-06-19）。

### 核心能力

| 能力 | 说明 |
|------|------|
| **四阶段流水线** | Digester → Planner → Evolver → Critic+Gate |
| **MUS 变体隔离** | 维护 E_var = {e_h_1,...,e_h_K}（K≤5），路由 r(τ) → 用 e_h_k，CRR > 95% |
| **κ-Gate 双轨协同进化** | harness_ver 与 model_weight 同 snap_session UUID 绑定，协同进化额外增益 +4.7% avg |
| **ψ-Alignment 检查** | G_ego ψ-anchor 对齐验证，防深层 semantic reward hack |

### 前端 AEGIS 控制面板

在左侧边栏点击 **AEGIS** 标签，可监控：
- **流水线状态**：四阶段运行指示（Digester → Planner → Evolver → Critic+Gate）
- **MUS 变体隔离**：已注册簇数、CRR 实时值（目标 > 95%）
- **κ-Gate 双轨**：harness_ver 与 model_weight 协同状态、CompatManifest 列表
- **CausalLog 查看器**：κ-Snap 因果日志（按 session_id / subject 过滤）
- **ψ-Alignment 检查**：G_ego ψ-anchor 对齐状态、std_ref 验证结果
- **性能基准**：一键运行 `bench_aegis.py`，查看 RPS / P50-P99 延迟 / CRR

### 运行基准测试

```bash
# 标准测试（100 次迭代，3 个变体）
cd tomas_agi/sim
python bench_aegis.py --iterations 100 --variants 3

# 快速测试
python bench_aegis.py --quick

# 保存报告
python bench_aegis.py --output data/aegis_bench.json

# 使用模拟数据测试 GAIA 管道
python download_gaia.py --method mock --num-mock 100
```

### 后端 API 端点（新增）

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/aegis/status` | GET | AEGIS 引擎状态（流水线阶段、MUS 簇数、CRR） |
| `/api/aegis/bench` | POST | 触发基准测试，返回 RPS / 延迟 / CRR |
| `/api/aegis/causal-log` | GET | 查询 κ-Snap 因果日志（支持 session_id 过滤） |
| `/api/aegis/psi-align` | POST | ψ-Alignment 检查 |
| `/api/aegis/variants` | GET | 查询已注册的 MUS 变体簇 |

---

## 📝 更新日志

### v3.12（最新 · 鲁兆DNA + GAT公理 + 金融市场 + 代币经济）
- ✅ **鲁兆DNA基因库** (`luzhao_dna.py`): 斐波那契/鲁加斯/八卦数拓扑不变量, DNA复制检测, 35自测
- ✅ **GAT广义代数理论** (`gat_axioms.py`): GATTheory/ArcDSL_GAT/OctonionGAT, 公理验证, 自由模型, 30自测
- ✅ **金融市场世界模型** (`financial_world_model.py`): LOB/做市商/滑点/ENPV/熔断, 17自测
- ✅ **代币化经济** (`tokenized_economy.py`): Token/AgentEconomy/UBI/Gini系数, 66自测
- ✅ **Flask API**: +25端点 (165总计)
- ✅ **前端4面板**: LuZhaoPanel/GATPanel/FinancialWorldPanel/TokenizedEconomyPanel
- ✅ **Dashboard增强**: +8子系统卡片, +8 panelMap映射
- ✅ **全量测试**: 1368 passed, 2 skipped, 0 failed

### v3.11（认知健康 + Grill-Me需求审问）
- ✅ **认知健康监测** (`cognitive_health.py`, 1550行): 双引擎成瘾模型, HealthAgentState状态机, 104自测
- ✅ **Grill-Me需求审问** (`grill_me_engine.py`, 1954行): DIKWP五层缺口分析, κ-Snap链追踪, 135自测
- ✅ **Flask API**: +10端点 (cognitive-health + grill-me)
- ✅ **前端2面板**: CognitiveHealthPanel + GrillMePanel

### v3.10（对齐三范式 + Goal导向智能体）
- ✅ **对齐三范式** (`alignment_triad.py`): ψ-Gate语义门控 + 语义防火墙 + Grill-Me审问, 114自测
- ✅ **Goal导向智能体** (`goal_directed_agent.py`): 目标分解→执行→验证, 非阻塞Grill集成

### v3.9（BabelTele + 超图范畴 + KernelCAT + ConstitutionalAI）
- ✅ **BabelTele语义压缩器** (`babeltele_compressor.py`): 跨语言语义压缩
- ✅ **超图范畴论** (`hypergraph_categories.py`): 范畴论框架下超图操作
- ✅ **KernelCAT调度器** (`kernelcat_scheduler.py`): 内核级任务调度
- ✅ **Constitutional AI** (`constitutional_agi.py`): 宪法式AI对齐, 116自测

### v3.6-v3.8（ψ-Gate + HTD仿真 + 认知压缩）
- ✅ v3.6: 8模块+57测试 (ψ-Gate/EML本体/解释坩埚/WM超边/DIKWP桥接/太极周期/MNQ冻结核/治疗师)
- ✅ v3.7: 3模块+108测试 (HTD仿真/拓扑孤子/Gan-PGW)
- ✅ v3.8: 2模块+110测试 (GaussEx-EML/认知压缩)

### v3.5（AEGIS演进引擎）
- ✅ **AEGIS**: ExtendHypergraph on Config Space, 四阶段流水线(Digester→Planner→Evolver→Critic+Gate)
- ✅ **MUS变体隔离**: K≤5变体簇, CRR>95%
- ✅ **κ-Gate双轨**: harness_ver与model_weight协同进化
- ✅ **ψ-Alignment**: G_ego ψ-anchor对齐验证

### v3.4（缓存优化 + 数据接入 + 代码质量）
- ✅ **DistillPanel三级缓存**：新增 `distillCache.ts` 模块，实现缓存→API→兜底三级数据加载
- ✅ **Flask服务脚本**：新增 `start_flask.bat`（Windows）和 `flask.service`（Linux systemd）
- ✅ **T-Processor真实数据**：`TProcessorPanel.tsx` 从 `/api/tprocessor/stats` 获取真实统计数据
- ✅ **T-Shield真实数据**：`TShieldPanel.tsx` 从 `/api/tshield/stats` 获取真实统计数据
- ✅ **Flask API扩展**：新增 `/api/tshield/stats` 端点返回T-Shield统计信息
- ✅ **ESLint配置**：新增 `.eslintrc.cjs` 和 `.prettierrc.cjs`，代码质量检查
- ✅ **构建验证**：tsc --noEmit ✓（0错误），vite build ✓
- ✅ **Meta描述更新**：`index.html` meta description 更新为"太极AGI"

### v3.3（UI修复 + 构建优化）
- ✅ **T-ShieldPanel修复**：修复JSX解析错误（ℹ️ emoji导致Babel崩溃），闭合未闭合的`<span>`标签
- ✅ **IconCpu图标**：新增CPU芯片SVG图标导出（用于T-Processor/T-Shield导航）
- ✅ **CRLF规范化**：修复distiller.ts/useChat.ts/TShieldPanel.tsx中的CRLF换行符（esbuild对CRLF处理有bug）
- ✅ **DistillPanel修复**：回退到已知好版本（5b1a580），修复第1061行未闭合`<div>`导致的82+级联TS错误
- ✅ **构建验证**：tsc --noEmit ✓（0错误），vite build ✓（1082模块）
- ✅ **路由优化**：对话意图检测 — 问候/身份/闲聊查询强制走LLM作家路径

### v3.2（SQLite迁移 + 前端重构）
- ✅ **数据存储迁移**：从 `localStorage` 全面迁移至 **SQLite 数据库**
- ✅ **后端 API 服务器**：新增 Flask + SQLite 后端（`tomas_agi/sim/server.py`）
- ✅ **批量数据导入**：支持大规模知识图谱数据导入（OwnThink 141M 行）
- ✅ **错误处理改进**：前端添加加载状态、错误提示、重试机制
- ✅ **统一 API 客户端**：创建 `apiClient.ts`，提供一致的 API 调用接口
- ✅ **知识三元组查询 API**：新增 `/api/knowledge/triples` 等端点
- ✅ **数据处理性能**：批量 INSERT（1000 行/批），导入速度 ~20K-50K 行/秒
- ✅ **TOMAS Dashboard**：全新Vite + React + TypeScript + Tailwind前端架构
- ✅ **T-Processor面板**：新增T-Processor硬件仿真器监控面板
- ✅ **T-Shield面板**：新增T-Shield认知安全层监控面板
- ✅ **概念名称显示**：修复EML二进制格式不存储概念名称的问题，使用OwnThink DB中文名称

### v3.1
- ✅ 知识浏览：概念与关系分列为两个独立列表
- ✅ 图谱搜索框：实时高亮匹配节点
- ✅ 边权重阈值滑块：动态过滤弱关联边
- ✅ 节点点击高亮邻居：1-hop 子图聚焦
- ✅ 图谱渲染错误捕获：避免黑屏
- ✅ 语料过滤降级机制
- ✅ Escape 快捷键清除高亮

### v3.0
- ✅ 置信度显示 + 用户反馈
- ✅ 知识冲突用户决策
- ✅ 图谱全屏布局 + 领域过滤
- ✅ 技术文档 Tab
- ✅ 概念真实名称显示

### v2.0
- ✅ "翻译官 + 作家" 混合推理架构
- ✅ EML 知识图谱可视化
- ✅ 多语料合并 + 冲突检测

### v1.0
- ✅ 基础聊天功能
- ✅ DeepSeek API 接入

---

## 📄 License

MIT License

---

## 🙏 作者

章锋（章锋）© 2026 复合体理学研究中心（TOMAS 项目组）
