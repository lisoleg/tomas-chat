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

### 📄 技术文档
- 内置技术文档 Tab，实时查看系统架构
- 涵盖：项目概述、系统架构、EML 知识图谱原理、双环治理、技术栈

---

## 🚀 快速开始

### 前端（deepseek-chat）

```bash
cd deepseek-chat
npm install
npm run dev
# 默认启动在 http://localhost:5173
```

生产构建：
```bash
npm run build
npm run preview   # 预览生产构建
```

### 后端（tomas-agi）

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

---

## 📝 更新日志

### v3.1（最新）
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
