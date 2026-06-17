# TOMAS Dashboard — 系统架构设计

## 1. 项目概述

将 `tomas-dashboard/index.html`（1943 行，9 页面设计稿）迁移为 **Vite + React 18 + TypeScript + Tailwind CSS** 正式工程，对接 `server.py` Flask 后端 API。

## 2. 技术栈

| 层 | 选型 | 说明 |
|----|------|------|
| 构建工具 | Vite 5 | 快速 HMR |
| 框架 | React 18 | 函数组件 + Hooks |
| 语言 | TypeScript 5.5 | 严格模式 |
| 样式 | Tailwind CSS 3.4 | 自定义主题（dark/light） |
| 路由 | React Router v6 | Hash 路由 |
| 状态管理 | Zustand | 轻量、无 boilerplate |
| 3D 渲染 | Three.js | WorldModel 页面 |
| 图表 | D3.js (force graph) + SVG 自绘 | 仪表盘圆环 |
| HTTP 客户端 | fetch (封装) | 统一错误处理 |
| 测试 | Vitest + RTL | 组件 + API 测试 |

## 3. 项目结构

```
tomas-dashboard/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.js
├── postcss.config.js
├── index.html
├── .env                          # VITE_API_BASE=http://localhost:5000
├── src/
│   ├── main.tsx                  # 入口
│   ├── App.tsx                   # 路由 + Layout
│   ├── index.css                 # Tailwind + 自定义主题变量
│   ├── types/
│   │   └── index.ts              # 全部 TypeScript 类型
│   ├── api/
│   │   ├── client.ts             # fetch 封装（超时/重试/错误处理）
│   │   └── endpoints.ts          # 按功能分组的 API 调用函数
│   ├── store/
│   │   ├── appStore.ts           # 全局状态（主题、侧边栏、页面）
│   │   ├── dashboardStore.ts     # 仪表盘数据
│   │   ├── chatStore.ts          # 聊天会话
│   │   └── tshieldStore.ts       # T-Shield 监控数据
│   ├── hooks/
│   │   ├── useApi.ts             # 通用 API hook（loading/error/data）
│   │   └── usePolling.ts         # 轮询 hook
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Layout.tsx        # 主布局（侧边栏+内容）
│   │   │   ├── Sidebar.tsx       # 侧边栏导航（三区+折叠）
│   │   │   └── Header.tsx        # 顶栏（标题+时间+主题切换）
│   │   └── ui/
│   │       ├── StatusCard.tsx     # 状态卡片（彩色左边框+label+value）
│   │       ├── StatusBadge.tsx    # 状态徽章（online/offline/warning）
│   │       ├── Loading.tsx        # 加载骨架屏
│   │       ├── EmptyState.tsx     # 空状态
│   │       └── ErrorBoundary.tsx  # 错误边界
│   └── pages/
│       ├── Dashboard.tsx          # 仪表盘主页（8卡片+时间线）
│       ├── Chat.tsx               # 聊天（EML路由+LLM双模式）
│       ├── Distill.tsx            # 蒸馏（语料+冲突+图谱）
│       ├── WorldModel.tsx         # 3D 世界模型（Three.js）
│       ├── TShield.tsx            # T-Shield 监控（DZ/MUS/κ-Snap SVG圆环）
│       ├── Audit.tsx              # 审计监控（三标签）
│       ├── Memory.tsx             # 记忆浏览器（搜索+ψ锚）
│       ├── Firewall.tsx           # 防火墙+路由
│       ├── Zynq.tsx               # Zynq 板卡监控
│       └── Settings.tsx           # 系统设置
└── tests/
    ├── setup.ts                   # 测试配置
    ├── components.test.tsx        # 组件测试
    └── api.test.ts                # API 客户端测试
```

## 4. 路由设计

| 路径 | 页面 | 对接 API |
|------|------|----------|
| `/` | Dashboard | `GET /api/health`, `GET /api/tprocessor/stats` |
| `/chat` | Chat | `GET/POST /api/sessions` |
| `/distill` | Distill | `GET/POST /api/corpus`, `GET/POST /api/conflicts` |
| `/world` | WorldModel | `GET /api/knowledge/graph` |
| `/tshield` | TShield | `GET /api/tshield/demo`, `POST /api/tshield/infer` |
| `/audit` | Audit | `GET /api/tprocessor/stats` |
| `/memory` | Memory | `GET /api/knowledge/triples`, `GET /api/knowledge/subjects` |
| `/firewall` | Firewall | `GET /api/ido/stats`, `GET /api/itot/kpi` |
| `/zynq` | Zynq | `GET /api/tprocessor/stats`, `GET /api/tshield/demo` |
| `/settings` | Settings | `GET/POST /api/apikey`, `GET/POST /api/settings` |

## 5. 组件树

```
App
├── BrowserRouter
│   └── Layout
│       ├── Sidebar
│       │   ├── LogoButton
│       │   ├── NavSection("核心功能") → [Dashboard, Chat, Distill, WorldModel]
│       │   ├── NavSection("TOMAS引擎") → [TShield, Audit, Memory, Firewall, Zynq]
│       │   └── NavSection("系统") → [Settings]
│       ├── Header
│       │   ├── PageTitle
│       │   ├── Clock
│       │   └── ThemeToggle
│       └── <Routes>
│           ├── / → Dashboard
│           │   ├── StatusCard x8
│           │   └── Timeline
│           ├── /chat → Chat
│           │   ├── MessageList
│           │   ├── MessageBubble (含EML路由标签+置信度)
│           │   └── ChatInput
│           ├── /distill → Distill
│           │   ├── CorpusList
│           │   ├── ConflictPanel
│           │   └── GraphView (D3 force)
│           ├── /world → WorldModel
│           │   └── ThreeScene (Three.js)
│           ├── /tshield → TShield
│           │   ├── DZGauge (SVG圆环)
│           │   ├── MUSGauge
│           │   └── KSnapGauge
│           ├── /audit → Audit
│           │   ├── TabBar [T-Proc, Spatial, G_ego]
│           │   └── AuditLog
│           ├── /memory → Memory
│           │   ├── SearchBar
│           │   └── MemoryList
│           ├── /firewall → Firewall
│           │   ├── AdcGrid (6模式)
│           │   └── RouterTable (12模型)
│           ├── /zynq → Zynq
│           │   ├── ResourceBars (LUT/FF/BRAM/DSP)
│           │   └── TelemetryCards (温度/功耗/延迟)
│           └── /settings → Settings
│               ├── ApiKeyForm
│               ├── ModelPoolConfig
│               └── ThemeSelector
```

## 6. API 客户端设计

```typescript
// src/api/client.ts
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:5000';

interface ApiResponse<T> {
  data: T;
  error?: string;
  status: number;
}

class ApiClient {
  private baseUrl: string;
  private timeout: number;

  constructor(baseUrl: string, timeout = 10000) {
    this.baseUrl = baseUrl;
    this.timeout = timeout;
  }

  async request<T>(path: string, options?: RequestInit): Promise<ApiResponse<T>> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeout);
    
    try {
      const res = await fetch(`${this.baseUrl}${path}`, {
        ...options,
        signal: controller.signal,
        headers: { 'Content-Type': 'application/json', ...options?.headers },
      });
      const data = await res.json();
      return { data, status: res.status };
    } catch (e) {
      return { data: null as T, error: (e as Error).message, status: 0 };
    } finally {
      clearTimeout(timer);
    }
  }

  get<T>(path: string) { return this.request<T>(path); }
  post<T>(path: string, body: unknown) { return this.request<T>(path, { method: 'POST', body: JSON.stringify(body) }); }
  delete<T>(path: string) { return this.request<T>(path, { method: 'DELETE' }); }
}

export const api = new ApiClient(API_BASE);
```

## 7. 状态管理

```typescript
// src/store/appStore.ts
import { create } from 'zustand';

interface AppState {
  theme: 'dark' | 'light';
  sidebarCollapsed: boolean;
  currentPage: string;
  toggleTheme: () => void;
  toggleSidebar: () => void;
  setPage: (page: string) => void;
}

export const useAppStore = create<AppState>((set) => ({
  theme: 'dark',
  sidebarCollapsed: false,
  currentPage: 'dashboard',
  toggleTheme: () => set((s) => ({ theme: s.theme === 'dark' ? 'light' : 'dark' })),
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setPage: (page) => set({ currentPage: page }),
}));
```

## 8. 设计 Token 映射

| CSS 变量 | Tailwind 扩展 | 用途 |
|----------|-------------|------|
| `--bg-primary: #0a0e1a` | `bg-tomas-950` | 主背景 |
| `--bg-secondary: #111827` | `bg-tomas-900` | 侧边栏/卡片 |
| `--bg-card: #1a2035` | `bg-tomas-800` | 卡片背景 |
| `--border: #1e2d4a` | `border-tomas-700` | 边框 |
| `--text-primary: #e2e8f0` | `text-tomas-100` | 主文字 |
| `--text-secondary: #94a3b8` | `text-tomas-400` | 副文字 |
| `--accent-blue: #3b82f6` | `text-accent-blue` | 强调蓝 |
| `--accent-cyan: #06b6d4` | `text-accent-cyan` | 强调青 |

## 9. 任务分解（实现顺序）

### Task 1: 项目脚手架（无依赖）
**涉及文件**: package.json, vite.config.ts, tsconfig.json, tailwind.config.js, postcss.config.js, index.html, .env, src/main.tsx, src/index.css, src/App.tsx
**验收**: `npm run dev` 启动成功，页面显示 "TOMAS Dashboard"

### Task 2: 类型定义 + API 客户端 + 状态管理（依赖 Task 1）
**涉及文件**: src/types/index.ts, src/api/client.ts, src/api/endpoints.ts, src/store/*.ts
**验收**: import 无报错，API 客户端可实例化

### Task 3: Layout 组件（依赖 Task 2）
**涉及文件**: src/components/layout/Layout.tsx, Sidebar.tsx, Header.tsx
**验收**: 侧边栏可折叠/展开，主题切换生效

### Task 4: UI 共享组件（依赖 Task 2）
**涉及文件**: src/components/ui/StatusCard.tsx, StatusBadge.tsx, Loading.tsx, EmptyState.tsx, ErrorBoundary.tsx
**验收**: 各组件在 Storybook/页面中渲染正常

### Task 5: Dashboard 页面（依赖 Task 3, 4）
**涉及文件**: src/pages/Dashboard.tsx, src/store/dashboardStore.ts
**对接 API**: GET /api/health, GET /api/tprocessor/stats
**验收**: 8 张状态卡片 + 时间线渲染，loading/error 状态正确

### Task 6: Chat 页面（依赖 Task 3, 4）
**涉及文件**: src/pages/Chat.tsx, src/store/chatStore.ts
**对接 API**: GET/POST /api/sessions
**验收**: 消息列表渲染，输入发送后显示回复，EML路由标签+置信度

### Task 7: Distill 页面（依赖 Task 3, 4）
**涉及文件**: src/pages/Distill.tsx
**对接 API**: GET/POST /api/corpus, GET/POST /api/conflicts
**验收**: 语料列表、冲突面板、D3 力导向图渲染

### Task 8: WorldModel 页面（依赖 Task 3）
**涉及文件**: src/pages/WorldModel.tsx
**对接 API**: GET /api/knowledge/graph
**验收**: Three.js 场景渲染，DIKWP 颜色节点 + 边

### Task 9: T-Shield 页面（依赖 Task 3, 4）
**涉及文件**: src/pages/TShield.tsx, src/store/tshieldStore.ts
**对接 API**: GET /api/tshield/demo, POST /api/tshield/infer
**验收**: 3 个 SVG 圆环仪表盘渲染，demo 按钮触发推理

### Task 10: Audit + Memory + Firewall + Zynq + Settings 页面（依赖 Task 3, 4）
**涉及文件**: src/pages/Audit.tsx, Memory.tsx, Firewall.tsx, Zynq.tsx, Settings.tsx
**对接 API**: 参见路由表
**验收**: 每个页面渲染正确，API 数据接入

### Task 11: 全局一致性审查 + 修复（依赖 Task 5-10）
**验收**: 所有页面无 TypeScript 错误，CSS 无闪烁，暗色/亮色主题全页面一致

### Task 12: 测试编写 + 运行（依赖 Task 11）
**涉及文件**: tests/*.ts, tests/*.tsx
**验收**: `npm run test` 通过，覆盖率 > 60%

## 10. 共享约定

1. **所有页面组件**必须处理三种状态：loading（骨架屏）、error（错误卡片）、正常数据
2. **API 调用**统一通过 `useApi` hook，不在组件中直接调用 fetch
3. **主题**通过 `<html class="dark|light">` + CSS 变量实现，Tailwind 提供 dark: 变体
4. **页面文件**只负责布局和数据组装，业务逻辑放在 hooks 和 store 中
5. **文件命名**: 组件 PascalCase，store camelCase，API 函数 camelCase
6. **环境变量**: VITE_API_BASE 控制后端地址，默认 http://localhost:5000
