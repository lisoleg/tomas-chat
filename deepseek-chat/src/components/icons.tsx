// 内联 SVG 图标库：避免引入 react-icons 依赖
// 每个图标都是 React 组件，统一接收 className 与 size 属性

import type { SVGProps } from 'react'

interface IconProps extends Omit<SVGProps<SVGSVGElement>, 'children'> {
  size?: number
}

function baseProps(size: number = 18): SVGProps<SVGSVGElement> {
  return {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.8,
    strokeLinecap: 'round',
    strokeLinejoin: 'round'
  }
}

/** 加号图标（新建对话） */
export function IconPlus({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}

/** 聊天气泡图标 */
export function IconChat({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  )
}

/** 垃圾桶图标（删除） */
export function IconTrash({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6" />
      <path d="M14 11v6" />
      <path d="M9 6V4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" />
    </svg>
  )
}

/** 发送箭头图标 */
export function IconSend({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  )
}

/** 停止方块（中止） */
export function IconStop({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <rect x="6" y="6" width="12" height="12" rx="1" />
    </svg>
  )
}

/** 钥匙 / 钥匙孔（API Key） */
export function IconKey({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <circle cx="7.5" cy="15.5" r="3.5" />
      <path d="M10.3 12.7 21 2" />
      <path d="m18 5 3 3" />
      <path d="m15 8 3 3" />
    </svg>
  )
}

/** 关闭（X） */
export function IconClose({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}

/** 菜单（汉堡） */
export function IconMenu({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <line x1="3" y1="6" x2="21" y2="6" />
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="18" x2="21" y2="18" />
    </svg>
  )
}

/** 复制 */
export function IconCopy({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <rect x="9" y="9" width="13" height="13" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  )
}

/** 已复制（对勾） */
export function IconCheck({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

/** 刷新/重置 */
export function IconRefresh({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <polyline points="23 4 23 10 17 10" />
      <polyline points="1 20 1 14 7 14" />
      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10" />
      <path d="M20.49 15a9 9 0 0 1-14.85 3.36L1 14" />
    </svg>
  )
}

/** 火花/星（AI 标识） */
export function IconSparkles({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <path d="M12 2l1.5 4.5L18 8l-4.5 1.5L12 14l-1.5-4.5L6 8l4.5-1.5L12 2z" />
      <path d="M19 14l.8 2.4L22 17l-2.2.6L19 20l-.8-2.4L16 17l2.2-.6L19 14z" />
    </svg>
  )
}

/** 用户 */
export function IconUser({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  )
}

/** 机器人 */
export function IconBot({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <rect x="3" y="8" width="18" height="12" rx="2" />
      <line x1="12" y1="2" x2="12" y2="6" />
      <circle cx="8.5" cy="14" r="1" fill="currentColor" />
      <circle cx="15.5" cy="14" r="1" fill="currentColor" />
      <line x1="9" y1="18" x2="15" y2="18" />
    </svg>
  )
}

/** 编辑（铅笔） */
export function IconEdit({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
      <path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  )
}

/** 文件/知识库图标 */
export function IconFile({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
      <polyline points="10 9 9 9 8 9" />
    </svg>
  )
}

// ── TOMAS UI v2 新增图标 ─────────────────────────────

/** 仪表盘 */
export function IconDashboard({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </svg>
  )
}

/** 地球/世界模型 */
export function IconGlobe({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <circle cx="12" cy="12" r="10" />
      <line x1="2" y1="12" x2="22" y2="12" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  )
}

/** 审计日志/盾牌勾选 */
export function IconAuditLog({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <polyline points="9 12 11 14 15 10" />
    </svg>
  )
}

/** 大脑/AI */
export function IconBrain({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 1.98-1.04A2.5 2.5 0 0 1 9.5 2z" />
      <path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.98-1.04A2.5 2.5 0 0 0 14.5 2z" />
    </svg>
  )
}

/** 记忆/数据库 */
export function IconMemory({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <ellipse cx="12" cy="5" rx="9" ry="3" />
      <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
      <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
    </svg>
  )
}

/** 盾牌/防火墙 */
export function IconShield({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  )
}

/** 层次/DIKWP */
export function IconLayers({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <polygon points="12 2 22 8.5 12 15 2 8.5 12 2" />
      <polyline points="2 15.5 12 22 22 15.5" />
    </svg>
  )
}

/** 火焰/死零 */
export function IconFlame({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.07-2.14-.22-4.05 0-5.5.15-.9.8-1.5 1.5-1.5s1.35.6 1.5 1.5c.22 1.45 1.07 3.36 0 5.5-.5 1-.88 1.62-1 3a2.5 2.5 0 0 0 2.5 2.5c1.38 0 2.5-1.12 2.5-2.5 0-0.75-.33-1.42-.82-1.91" />
    </svg>
  )
}

/** 路由/分叉 */
export function IconRoute({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <circle cx="6" cy="6" r="1.5" />
      <circle cx="18" cy="18" r="1.5" />
      <circle cx="18" cy="6" r="1.5" />
      <path d="M6 6l6 6" />
      <path d="M18 6l-6 6" />
      <path d="M12 12l6 6" />
    </svg>
  )
}

export function IconDownload({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  )
}

export function IconGraph({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="4" cy="20" r="1.5" fill="currentColor" />
      <circle cx="12" cy="8" r="1.5" fill="currentColor" />
      <circle cx="20" cy="14" r="1.5" fill="currentColor" />
      <path d="M4 20L12 8" />
      <path d="M12 8L20 14" />
      <path d="M4 20L20 14" />
    </svg>
  )
}

export function IconDatabase({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="12" cy="5" rx="9" ry="3" />
      <path d="M3 5v6c0 1.66 4 3 9 3s9-1.34 9-3V5" />
      <path d="M3 11v6c0 1.66 4 3 9 3s9-1.34 9-3v-6" />
    </svg>
  )
}

/** CPU/芯片 */
export function IconCpu({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="4" y="4" width="16" height="16" rx="2" ry="2" />
      <rect x="9" y="9" width="6" height="6" />
      <line x1="9" y1="1" x2="9" y2="4" />
      <line x1="15" y1="1" x2="15" y2="4" />
      <line x1="9" y1="20" x2="9" y2="23" />
      <line x1="15" y1="20" x2="15" y2="23" />
      <line x1="20" y1="9" x2="23" y2="9" />
      <line x1="20" y1="14" x2="23" y2="14" />
      <line x1="1" y1="9" x2="4" y2="9" />
      <line x1="1" y1="14" x2="4" y2="14" />
    </svg>
  )
}

/** 活动/脉冲 */
export function IconActivity({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  )
}

/** 时钟 */
export function IconClock({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  )
}

/** X/关闭 */
export function IconX({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}

// ── v3.10 新增图标 ─────────────────────────────────

/** 锁 */
export function IconLock({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <rect x="3" y="11" width="18" height="11" rx="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  )
}

/** 心理学/思维 */
export function IconPsychology({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <path d="M12 2a2 2 0 0 1 2 2v4.5a1.5 1.5 0 0 0 1.5 1.5H20a2 2 0 0 1 0 4h-4.5a1.5 1.5 0 0 0-1.5 1.5V20a2 2 0 0 1-4 0v-4.5a1.5 1.5 0 0 0-1.5-1.5H4a2 2 0 0 1 0-4h4.5A1.5 1.5 0 0 0 10 8.5V4a2 2 0 0 1 2-2z" />
    </svg>
  )
}

/** 法槌 */
export function IconGavel({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <path d="M14 13l-8 8 3 3 8-8" />
      <path d="M4 19l-2 2" />
      <path d="M20 3l-5 5" />
      <path d="M15 3l6 6" />
      <line x1="6" y1="13" x2="15" y2="4" />
    </svg>
  )
}

/** 警告三角 */
export function IconWarning({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  )
}

/** 已验证/认证 */
export function IconVerified({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <path d="M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 22 12 18.56 5.82 22 7 14.14 2 9.27l6.91-1.01z" />
      <polyline points="9 12 11 14 15 10" />
    </svg>
  )
}

/** 趋势上升 */
export function IconTrendingUp({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
      <polyline points="17 6 23 6 23 12" />
    </svg>
  )
}

/** 历史 */
export function IconHistory({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <polyline points="1 4 1 10 7 10" />
      <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
    </svg>
  )
}

/** 描述/文档 */
export function IconDescription({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
      <line x1="10" y1="9" x2="8" y2="9" />
    </svg>
  )
}

/** 速度 */
export function IconSpeed({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <path d="M12 2a10 10 0 1 0 10 10" />
      <path d="M12 12l8-8" />
      <path d="M2 16a5 5 0 0 1 5-5" />
      <path d="M12 8a5 5 0 0 1 5 5" />
    </svg>
  )
}

/** 待处理 */
export function IconPendingActions({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z" />
      <line x1="12" y1="6" x2="12" y2="12" />
      <line x1="12" y1="12" x2="16" y2="14" />
    </svg>
  )
}

/** 目标/靶心 */
export function IconTarget({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <circle cx="12" cy="12" r="10" />
      <circle cx="12" cy="12" r="6" />
      <circle cx="12" cy="12" r="2" fill="currentColor" stroke="none" />
    </svg>
  )
}

/** 定锚 */
export function IconAnchor({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <circle cx="12" cy="5" r="3" />
      <line x1="12" y1="22" x2="12" y2="8" />
      <path d="M5 12H2a10 10 0 0 0 20 0h-3" />
    </svg>
  )
}

// ── v3.11 新增图标 ─────────────────────────────────

/** 心跳/认知健康 */
export function IconHeartbeat({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
      <polyline points="9 11 11 13 15 9" />
    </svg>
  )
}

/** 搜索放大镜/审问 */
export function IconSearchGavel({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
      <line x1="8" y1="11" x2="14" y2="11" />
      <line x1="11" y1="8" x2="11" y2="14" />
    </svg>
  )
}

// ── v3.12 新增图标 ─────────────────────────────────

/** DNA / 鲁兆 */
export function IconDna({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <path d="M12 2c-2 0-4 3-4 10s2 10 4 10 4-3 4-10-2-10-4-10z" fill="none" />
      <path d="M8 2v20" />
      <path d="M16 2v20" />
      <circle cx="12" cy="5" r="1" fill="currentColor" />
      <circle cx="12" cy="10" r="1" fill="currentColor" />
      <circle cx="12" cy="15" r="1" fill="currentColor" />
      <circle cx="12" cy="19" r="1" fill="currentColor" />
    </svg>
  )
}

/** 代数/公理 */
export function IconGat({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <path d="M4 4h16v16H4z" fill="none" />
      <text x="12" y="15" textAnchor="middle" fontSize="10" fontWeight="bold" fill="currentColor">∀</text>
    </svg>
  )
}

/** 金融/美元 */
export function IconFinancial({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <line x1="12" y1="1" x2="12" y2="23" />
      <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
    </svg>
  )
}

/** 代币/圆形 */
export function IconToken({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="4" />
      <line x1="12" y1="3" x2="12" y2="8" />
      <line x1="12" y1="16" x2="12" y2="21" />
      <line x1="3" y1="12" x2="8" y2="12" />
      <line x1="16" y1="12" x2="21" y2="12" />
    </svg>
  )
}

// ── v3.14 新增图标 ─────────────────────────────────

/** 叠加态几何 — 多个圆圈叠加 */
export function IconSuperposition({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <circle cx="9" cy="9" r="5" />
      <circle cx="15" cy="9" r="5" />
      <circle cx="12" cy="15" r="5" />
    </svg>
  )
}

/** 数学大统一 — 无穷符号∞ */
export function IconMathUnify({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <path d="M18.178 8c5.096 0 5.096 8 0 8-5.095 0-7.133-8-12.739-8-4.585 0-4.585 8 0 8 5.606 0 7.644-8 12.74-8z" />
    </svg>
  )
}

/** 自适应库 — 书本+齿轮 */
export function IconAdaptiveLib({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
      <circle cx="14" cy="10" r="2.5" />
      <path d="M14 7.5v-1M14 13.5v-1M16.5 10h1M10.5 10h1" />
    </svg>
  )
}

/** CHL同构 — 三角形 */
export function IconCHL({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <path d="M12 2L22 20H2L12 2z" />
      <circle cx="12" cy="2" r="1.5" fill="currentColor" />
      <circle cx="22" cy="20" r="1.5" fill="currentColor" />
      <circle cx="2" cy="20" r="1.5" fill="currentColor" />
      <line x1="12" y1="5" x2="6" y2="17" />
      <line x1="12" y1="5" x2="18" y2="17" />
      <line x1="7" y1="20" x2="17" y2="20" />
    </svg>
  )
}

/** 太一互搏 — 太极图/双圆 */
export function IconTaiyi({ size, ...rest }: IconProps) {
  return (
    <svg {...baseProps(size)} {...rest}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 3a4.5 4.5 0 0 1 0 9 4.5 4.5 0 0 0 0 9" fill="currentColor" opacity="0" />
      <path d="M12 3a4.5 4.5 0 0 1 0 9 4.5 4.5 0 0 0 0 9" />
      <circle cx="12" cy="7.5" r="1.2" fill="currentColor" />
      <circle cx="12" cy="16.5" r="1.2" fill="none" stroke="currentColor" />
    </svg>
  )
}

