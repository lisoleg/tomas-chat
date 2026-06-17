# TOMAS Dashboard 修复报告

**日期**: 2026-06-18 | **Commit**: `93b85ac`

---

## TL;DR
修复了 TShieldPanel.tsx 的两个 JSX 语法错误、添加缺失的 IconCpu 图标、解决了 DistillPanel.tsx 的 JSX 结构破坏问题，构建从 82+ 错误恢复到零错误通过。

## 修复的问题

### 1. TShieldPanel.tsx — Babel `Unexpected token` (line 200)
- **症状**: `ℹ️` emoji 作为 `<p>` 元素的直接文本子节点时，Babel JSX 解析器报错
- **根因**: 某些 Unicode emoji 组合在 JSX 文本位置会触发解析器边界问题
- **修复**: 用 JS 表达式 `{''}` 包裹：`{'ℹ️ G_ego 根据...'}`

### 2. TShieldPanel.tsx — 未闭合 `<span>` (line 304)
- **症状**: `Expected corresponding JSX closing tag for <span>`
- **根因**: 嵌套 `<span>ℐ-Scene: <span>{value}</span>` 缺少外层 `</span>`
- **修复**: 在内层 span 后补上 `</span>` 闭合标签

### 3. DistillPanel.tsx — JSX 结构破坏 (82+ 级联错误)
- **症状**: TypeScript 报 `JSX element 'div' has no corresponding closing tag`（第 1061 行），esbuild/Vite/Rolludown 全部报 "Unterminated regular expression"
- **根因**: commit `86bd973`（三级数据缓存改动）引入了未配对的 JSX 标签，div 嵌套深度最终为 -5
- **诊断过程**:
  - 初步怀疑 CRLF 换行符 → 排除（LF 后仍失败）
  - esbuild `transform()` 通过但 `build()` 失败 → 发现是不同代码路径
  - Vite 8 (Rolldown) 同位置报错 → 确认文件本身有结构问题
  - tsc 明确报出 line 1061 unclosed div → **找到真正根因**
- **修复**: 回退到 git `5b1a580`（上一已知好版本）

### 4. icons.tsx — 缺失 IconCpu 导出
- **症状**: rollup 打包报 `"IconCpu" is not exported by "src/components/icons.tsx"`
- **根因**: Dashboard/Sidebar 引入 IconCpu 用于 T-Processor/T-Shield 面板导航图标，但 icons.tsx 未导出
- **修复**: 新增 IconCpu SVG 组件（CPU 芯片图标，含芯片/引脚路径）

### 5. CRLF 换行符规范化
- distiller.ts (1572 CRLF → LF)
- useChat.ts (705 CRLF → LF)
- TShieldPanel.tsx (已为 LF)

## 构建验证
| 检查项 | 结果 |
|--------|------|
| `tsc --noEmit` | ✅ 0 errors |
| `vite build` | ✅ 1082 modules, 2.09 MB JS + 53 KB CSS |
| Git push (backend) | ✅ lisoleg/tomas-agi master |
| Git push (frontend) | ✅ lisoleg/tomas-chat master |

## 待办
- [ ] **DistillPanel 三级缓存功能需要重新实现** — 在已恢复的 5b1a580 版本基础上谨慎应用以下改动：
  - localStorage 缓存层（TTL 5min）
  - Flask API 加载（带重试）
  - 内置 TOMAS 示例数据兜底
  - DIKWP 迷你图始终可见
  - 数据来源标签显示
  - ⚠️ 必须保持 div 标签完美平衡，每步用 tsc --noEmit 验证
- [ ] 更新技术文档（tomas_dashboard_arch.md, tshield_zynq_arch.md 等）反映新面板
