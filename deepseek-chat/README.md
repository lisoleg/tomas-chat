# 太极AGI · TOMAS-AGI Frontend

> 基于 EML（Enhanced Memory Language）知识图谱 + LLM 双引擎混合推理的前端系统

## 🌟 简介

太极AGI 是一款将**结构化知识图谱（EML）**与**大语言模型（LLM）**深度融合的 AI 对话系统。核心创新是"翻译官 + 作家"混合架构：

- **翻译官模式**：当 EML 图谱中有高置信度匹配时，从知识图谱中精确检索答案（事实性查询）
- **作家模式**：当 EML 覆盖不足时，交由 DeepSeek LLM 创造性回答（辅以 EML 上下文增强）
- **路由裁决**：系统自动计算置信度（confidence），≥0.5 走翻译官，<0.5 走作家

## ✨ 核心功能

### 0. 💬 AI 对话（双引擎推理）

- **翻译官模式**：EML 图谱高置信度匹配 → 精确检索答案（事实性查询）
- **作家模式**：EML 覆盖不足 → DeepSeek LLM 创造性回答（辅以 EML 上下文增强）
- **路由裁决**：系统自动计算置信度，≥0.5 走翻译官，<0.5 走作家
- **置信度透明化**：每次回答附带置信度标签，用户可点赞/点踩反馈

### 1. 🔍 EML 知识蒸馏
- 支持文本语料 → EML 知识图谱的一键蒸馏
- 自动检测新语料与已有知识的**重叠和冲突**
- 冲突处理哲学：**容纳冲突而非覆盖**——用户可逐条决策（保留旧知/采纳新知/合并/忽略）

### 2. 🕸️ 知识图谱可视化
- D3.js 力导向图，实时展示 EML 知识图谱
- **全画布布局**：图谱铺满整个可视区域，节点自然散开
- **领域过滤**：多语料场景下，可切换查看特定领域（如"物理"或"化学"）的子图
- 节点大小反映信息存在度（δ 值），悬浮查看详细信息

### 3. 📊 置信度透明化
- 每次回答附带**置信度标签**（如 `📡 EML路由 · 87%`）
- 用户可对每个回答**点赞/点踩**，反馈用于改进路由策略
- 推理链路全透明：展开消息可查看 EML 匹配详情

### 4. 📄 技术文档
- 内置技术文档 Tab，实时查看系统架构
- 涵盖：项目概述、系统架构、EML 知识图谱原理、双环治理、技术栈

### 5. 💾 多语料管理
- 支持加载多个语料蒸馏后的 EML 文件
- 自动合并图谱，冲突自动检测
- 语料列表持久化（localStorage）

## 🚀 快速开始

### 环境要求
- Node.js ≥ 18
- DeepSeek API Key（用于作家模式）

### 安装依赖
```bash
cd deepseek-chat
npm install
```

### 启动开发服务器
```bash
npm run dev
# 默认启动在 http://localhost:5173
```

### 生产构建
```bash
npm run build
npm run preview   # 预览生产构建
```

## ⚙️ 配置

### DeepSeek API Key
在 `tomas_agi/sim/.env` 中配置：
```
DEEPSEEK_API_KEY=sk-your-key-here
```

或在运行时通过蒸馏面板的设置面板填写。

### 路由置信度阈值
默认阈值 0.5，可在 `src/hooks/useChat.ts` 中调整：
```typescript
const CONFIDENCE_THRESHOLD = 0.5
```

## 📖 使用指南

### 第一次使用
1. 启动应用后，系统会自动加载默认的 EML 图谱（如已蒸馏）
2. 在聊天框输入问题，系统会自动路由到翻译官或作家
3. 查看消息下方的置信度标签，了解答案来源

### 蒸馏新语料
1. 点击左侧边栏的**蒸馏器**标签
2. 粘贴文本语料（或上传 `.txt` 文件）
3. 点击**蒸馏**按钮，等待处理完成
4. 如有冲突，系统会提示决策（默认可忽略，不影响使用）
5. 蒸馏完成后，图谱可视化自动更新

### 查看知识图谱
1. 在蒸馏面板中切换到**🕸️ 图谱可视化** Tab
2. 鼠标拖动可平移，滚轮缩放
3. 点击节点选中，右侧知识浏览面板显示详细信息
4. 如有多个领域，左上角下拉框可过滤

### 技术文档
点击左侧边栏的**📄 技术文档**标签，查看：
- 系统架构图
- EML 知识图谱原理
- 双引擎推理流程
- 技术栈说明

## 🗂️ 项目结构

```
deepseek-chat/
├── src/
│   ├── api/
│   │   ├── distiller.ts          # TokenBridgeClient + EML 序列化
│   │   ├── deepseek.ts          # DeepSeek API 调用
│   │   └── knowledgeStore.ts   # 前端知识图谱状态管理
│   ├── components/
│   │   ├── DistillPanel.tsx     # 蒸馏面板（含图谱可视化 Tab）
│   │   ├── EMLGraphVisualization.tsx  # D3.js 知识图谱（搜索/高亮/边过滤）
│   │   ├── KnowledgeBrowser.tsx # 知识浏览（概念+关系两个独立列表）
│   │   ├── MessageBubble.tsx   # 消息气泡（含置信度+反馈）
│   │   ├── TechDocs.tsx         # 技术文档组件
│   │   └── ...
│   ├── hooks/
│   │   └── useChat.ts          # 核心推理 Hook（路由裁决）
│   ├── types.ts
│   └── App.tsx
├── public/
│   └── *_distilled.eml          # 预蒸馏的 EML 图谱
└── package.json
```

## 🔧 后端依赖

前端需要与 `tomas_agi/` 后端配合使用：

```bash
# 蒸馏语料（生成 .eml 文件）
cd tomas_agi
python llm_distiller.py \
  --distill data/physics.txt \
  --output data/physics_distilled.eml \
  --api-key sk-xxx

# 启动 Token Bridge 推理（可选，前端可直连 DeepSeek）
python token_bridge.py \
  --load data/physics_distilled.eml \
  --concepts data/physics_distilled.concepts.json \
  --query "什么是牛顿第二定律" \
  --llm --api-key sk-xxx
```

## 📌 技术栈

| 层级 | 技术 |
|------|------|
| 框架 | Vite + React 18 + TypeScript |
| 样式 | Tailwind CSS |
| 图谱可视化 | D3.js（力导向图） |
| LLM | DeepSeek API (v1) |
| 状态管理 | React Hooks（useReducer + useRef） |
| 构建 | Vite（HMR + TypeScript 编译） |

## 📄 相关文档

- [系统架构设计](./docs/ARCHITECTURE.md) — 完整的系统架构和文件树
- [产品需求文档](./docs/PRD.md) — PRD（面向后端系统）

## 📝 更新日志

### v3.4（最新） — 2026-06-18
- ✅ ESLint 配置：统一代码风格，0 errors, 170 warnings
- ✅ Prettier 代码格式化配置
- ✅ distillCache 三级缓存：localStorage → Flask API → fallback（16 单元测试全通过）
- ✅ T-Processor/T-Shield 真实数据接入（替换 mock 数据，5 秒自动刷新）
- ✅ Flask 关键端点测试脚本（14 个端点覆盖）
- ✅ 源码 bug 修复：sessionStore dikwDistribution 字段名一致性、retryFetch 不重试逻辑
- ✅ DIKWPPieChart hooks 顺序修复、AuditMonitor 引号转义修复

### v3.4.1（最新）
- ✅ **UI 审查修复** — 全面打磨用户界面一致性
  - TProcessorPanel / TShieldPanel 添加 loading skeleton 和 error 横幅提示
  - IDO/FDE/DualTimeline/ITOT 4 引擎面板统一为设计系统颜色 tokens
  - Dashboard 清理冗余 nasga 映射
  - FDEPanel 移除 `any` 类型，使用具体接口
- ✅ TypeScript 零错误，ESLint 零 error

### v3.4
- ✅ ESLint + Prettier 代码质量配置（零 error，170 warnings）
- ✅ distillCache 三级缓存（localStorage → API → fallback）
- ✅ T-Processor / T-Shield 面板真实 API 数据接入
- ✅ Flask 14 端点测试脚本（test_endpoints.py）
- ✅ distillCache 单元测试 16/16 通过（Vitest）
- ✅ Flask 服务器开机自启脚本（Windows .bat + Linux systemd）
- ✅ 3 个源码 Bug 修复（dikwDistribution 字段名、retryFetch 400/401/403 逻辑、空块语句）

### v3.3
- ✅ 对话意图检测：避免无意义 EML 检索
- ✅ JSX Unicode 语法修复（Babel 解析器兼容）
- ✅ CRLF→LF 规范化：修复 esbuild 构建误报
- ✅ TShieldPanel 未闭合标签修复
- ✅ IconCpu 图标补全
- ✅ TypeScript 0 错误，Vite 构建 1082 模块通过

### v3.2
- ✅ 全新独立 Web UI（tomas-dashboard/）：9 页面深色主题交互式设计稿
- ✅ G_ego / Epiplexity / EMLSemZip 新模块
- ✅ T-Processor v1.0 硬件仿真器（RRAM Crossbar）
- ✅ T-Shield 认知安全层（DZ Grafting / MUS Dual-Box）
- ✅ IDO 五元素模板 + FDE 道法术器本体 + 双时间维度引擎 + IT-OT 翻译桥
- ✅ Flask API 服务器扩展（16+7 REST 端点）
- ✅ RTL 代码：T-Shield Zynq-7000 架构（5 模块 + Vivado 自动化脚本）

### v3.1
- ✅ 知识浏览面板：概念与关系分列为两个独立列表
- ✅ 图谱搜索框：实时高亮匹配节点
- ✅ 边权重阈值滑块：动态过滤弱关联边，降低视觉干扰
- ✅ 节点点击高亮邻居：点击某节点，只高亮其 1-hop 邻居子图
- ✅ 图谱渲染错误捕获：renderError 状态，出错时显示提示而非黑屏
- ✅ 语料过滤降级机制：EML 数据缺少 corpusName 时自动显示全部并提示
- ✅ Escape 快捷键：清除搜索高亮和点击高亮

### v3.0
- ✅ 置信度显示 + 用户反馈（点赞/点踩）
- ✅ 知识冲突用户决策（四选一：保留旧知/采纳新知/合并/忽略）
- ✅ 图谱可视化全屏布局 + 领域过滤
- ✅ 技术文档 Tab
- ✅ 概念名称真实显示（替换 `concept_xx` 占位符）
- ✅ 太极AGI 品牌更新

### v2.0
- ✅ "翻译官 + 作家" 混合推理架构
- ✅ EML 知识图谱可视化
- ✅ 多语料合并 + 冲突检测

### v1.0
- ✅ 基础聊天功能
- ✅ DeepSeek API 接入

## 📄 License

Apache License 2.0 — see [LICENSE](./LICENSE) for details.
