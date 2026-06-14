# DeepSeek Chat — EML 知识图谱混合推理前端

> 版本：V3 | TOMAS-AGI 前端 | 2026-06-14 | Apache 2.0

基于 Vite + React + TypeScript 构建，集成 EML 知识图谱路由 + DeepSeek LLM 的"翻译官 + 作家"混合推理架构。

---

## 快速开始

```bash
cd deepseek-chat
npm install
npm run dev
```

浏览器打开 **http://localhost:5173**

### 环境要求

- Node.js >= 22
- DeepSeek API Key（可选，无 Key 时走模板回退模式）

### 配置 API Key

在 `.env` 文件中设置：

```
VITE_DEEPSEEK_API_KEY=sk-xxxxxxxx
```

或在界面的设置面板中输入。

---

## 核心功能

### 1. EML 知识图谱自动加载

启动时自动加载 `public/` 目录下所有 `.eml` 文件，合并为统一知识图谱：

| EML 文件 | 领域 | 知识条数（V+E） |
|----------|------|----------------|
| `physics_distilled.eml` | 物理学 | ~50 |
| `chemistry_distilled.eml` | 化学 | ~40 |
| `medicine_distilled.eml` | 医学 | ~35 |
| `test_ai_distilled.eml` | AI 基础 | ~30 |
| `general_knowledge_distilled.eml` | 通用知识 | ~100 |

### 2. "翻译官 + 作家" 混合推理

```
用户提问 → EML 图谱检索 → 置信度裁决
                              │
                    ┌─────────┴─────────┐
                    ↓                   ↓
            翻译官（≥0.5）        作家（<0.5）
            EML 注入 LLM        DeepSeek 直接回复
```

- **V** = 概念（顶点）数
- **E** = 关系（边）数
- **K** = 知识条数（V + E）
- **𝕀̄** = 平均信息存在度
- **置信度** = EML 匹配强度（0-1）

### 3. 蒸馏模式

在蒸馏面板中：
1. 输入文本语料
2. 自动提取概念和关系
3. 构建 EML 知识图谱
4. 下载 `.eml` 文件

**重叠/冲突检测**：新蒸馏结果与已加载图谱自动对比：
- 重叠概念 → 保留高 𝕀 值方
- 冲突关系 → 保留高强度方
- 冗余关系 → 自动去重

### 4. 太乙互博推理链路

每个 EML 路由回复附带 5 阶段 LEAN 推理链路：
1. φ-Gate 编码
2. 概念匹配
3. BFS 子图提取
4. 太乙路由裁决
5. 执行模式

点击消息气泡中的 **▸ 太乙互博 · 推理链路** 展开查看。

### 5. LLM Prompt 透明化

点击 **▸ LLM Prompt** 展开查看发送给 DeepSeek 的完整 Prompt：
- 系统指令 · 行为约束
- 知识图谱上下文 · EML 注入
- 当前提问

### 6. 直连重试

对 EML 路由回复不满意？点击 **🔄 不满意？让 DeepSeek 直接回答** 按钮，绕过 EML 直接提问。

---

## 项目结构

```
deepseek-chat/
├── public/                  # 静态资源 + EML 知识图谱文件
├── src/
│   ├── api/
│   │   ├── distiller.ts     # EML 加载/序列化/图谱查询/合并
│   │   └── deepseek.ts      # DeepSeek API 流式调用
│   ├── components/
│   │   ├── ChatArea.tsx      # 聊天主区域
│   │   ├── DistillPanel.tsx  # 蒸馏面板（含合并 UI）
│   │   ├── EMLGraphVisualization.tsx  # 知识图谱可视化
│   │   ├── MessageBubble.tsx # 消息气泡（推理链路+Prompt+重试）
│   │   └── ...
│   ├── hooks/
│   │   └── useChat.ts        # EML 路由 + LLM 流式
│   ├── App.tsx               # 入口：自动加载合并 EML
│   └── types.ts              # 类型定义
├── scripts/
│   └── generate-general-knowledge.ts  # 通用知识 EML 生成
└── package.json
```

---

## 技术栈

| 技术 | 用途 |
|------|------|
| Vite | 构建工具 |
| React 18 | UI 框架 |
| TypeScript | 类型安全 |
| Tailwind CSS | 样式 |
| D3.js | 知识图谱可视化 |
| DeepSeek API | LLM 推理 |

---

## 相关文档

- [架构设计文档](../docs/ARCHITECTURE.md)
- [产品需求文档](../docs/PRD.md)
- [交付总览](../overview.md)
