// 侧边栏 v2：多面板导航（仪表盘/聊天/蒸馏/世界模型/审计/记忆/防火墙/文档）
// 含会话列表（聊天模式专用）和 API Key 入口
import { useState, useRef, useEffect } from 'react'
import type { AppMode, ChatSession } from '../types'
import {
  IconChat, IconKey, IconPlus, IconSparkles, IconTrash, IconEdit,
  IconDashboard, IconGlobe, IconAuditLog, IconBrain, IconMemory,
  IconShield, IconLayers, IconFlame, IconRoute, IconCpu, IconGraph,
  IconLock, IconDescription, IconTarget, IconAnchor,
  IconHeartbeat, IconSearchGavel, IconDna, IconGat, IconFinancial, IconToken,
  IconSuperposition, IconMathUnify, IconAdaptiveLib, IconCHL, IconTaiyi
} from './icons'
import { SkeletonText } from './Skeleton'

interface SidebarProps {
  sessions: ChatSession[]
  currentSessionId: string | null
  onSwitch: (id: string) => void
  onNew: () => void
  onDelete: (id: string) => void
  onRename: (id: string, newTitle: string) => void
  onOpenApiKey: () => void
  hasApiKey: boolean
  open: boolean
  onCloseMobile: () => void
  mode: AppMode
  onSwitchMode: (mode: AppMode) => void
  loading?: boolean
}

// ── Navigation items ──────────────────────────────────

interface NavItem {
  id: AppMode
  label: string
  icon: React.ReactNode
  section: 'core' | 'monitor' | 'engine' | 'info'
}

const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', label: '仪表盘', icon: <IconDashboard size={17} />, section: 'core' },
  { id: 'chat', label: '聊天', icon: <IconChat size={17} />, section: 'core' },
  { id: 'distill', label: '蒸馏', icon: <IconBrain size={17} />, section: 'core' },
  { id: 'world-model', label: '世界模型', icon: <IconGlobe size={17} />, section: 'monitor' },
  { id: 'audit', label: '审计监控', icon: <IconAuditLog size={17} />, section: 'monitor' },
  { id: 'tprocessor', label: 'T-Processor', icon: <IconCpu size={17} />, section: 'monitor' },
  { id: 'tshield', label: 'T-Shield', icon: <IconShield size={17} />, section: 'monitor' },
  { id: 'aegis', label: 'AEGIS', icon: <IconCpu size={17} />, section: 'monitor' },
  { id: 'memory', label: '记忆浏览器', icon: <IconMemory size={17} />, section: 'monitor' },
  { id: 'firewall-router', label: '防火墙·路由', icon: <IconShield size={17} />, section: 'monitor' },
  { id: 'ido', label: 'IDO 桥接', icon: <IconLayers size={17} />, section: 'engine' },
  { id: 'fde', label: 'FDE 本体', icon: <IconFlame size={17} />, section: 'engine' },
  { id: 'dual', label: '双时间维度', icon: <IconRoute size={17} />, section: 'engine' },
  { id: 'itot', label: 'IT-OT 翻译', icon: <IconGlobe size={17} />, section: 'engine' },
  { id: 'hypergraph', label: '超图数据库', icon: <IconGraph size={17} />, section: 'engine' },
  { id: 'v2', label: 'V2 升级', icon: <IconSparkles size={17} />, section: 'engine' },
  { id: 'alignment-triad', label: '对齐三范式', icon: <IconLock size={17} />, section: 'engine' },
  { id: 'goal-agent', label: 'Goal 导向', icon: <IconTarget size={17} />, section: 'engine' },
  { id: 'cognitive-health', label: '认知健康', icon: <IconHeartbeat size={17} />, section: 'engine' },
  { id: 'grill-me', label: '需求审问', icon: <IconSearchGavel size={17} />, section: 'engine' },
  { id: 'luzhao-dna', label: '鲁兆 DNA', icon: <IconDna size={17} />, section: 'engine' },
  { id: 'gat-axioms', label: 'GAT 公理', icon: <IconGat size={17} />, section: 'engine' },
  { id: 'financial-world', label: '金融市场', icon: <IconFinancial size={17} />, section: 'engine' },
  { id: 'tokenized-economy', label: '代币经济', icon: <IconToken size={17} />, section: 'engine' },
  { id: 'superposition-geometry', label: '叠加态几何', icon: <IconSuperposition size={17} />, section: 'engine' },
  { id: 'math-unification', label: '数学大统一', icon: <IconMathUnify size={17} />, section: 'engine' },
  { id: 'adaptive-library', label: '自适应库', icon: <IconAdaptiveLib size={17} />, section: 'engine' },
  { id: 'chl-isomorphism', label: 'CHL同构', icon: <IconCHL size={17} />, section: 'engine' },
  { id: 'taiyi-duel', label: '太一互搏', icon: <IconTaiyi size={17} />, section: 'engine' },
  { id: 'docs', label: '技术文档', icon: <IconFile size={17} />, section: 'info' },
]

// 简单文件图标（不依赖外部）
function IconFile({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
    </svg>
  )
}

// ── Helpers ────────────────────────────────────────────

function formatTime(ts: number): string {
  const date = new Date(ts)
  const now = new Date()
  const sameDay = date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth() && date.getDate() === now.getDate()
  if (sameDay) return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}

// ── Component ──────────────────────────────────────────

export function Sidebar(props: SidebarProps) {
  const {
    sessions, currentSessionId, onSwitch, onNew, onDelete, onRename,
    onOpenApiKey, hasApiKey, open, onCloseMobile, mode, onSwitchMode, loading = false
  } = props

  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const editInputRef = useRef<HTMLInputElement>(null)
  const [sessionsExpanded, setSessionsExpanded] = useState(true)

  useEffect(() => {
    if (editingId && editInputRef.current) {
      editInputRef.current.focus()
      editInputRef.current.select()
    }
  }, [editingId])

  const startEdit = (s: ChatSession) => { setEditingId(s.id); setEditValue(s.title || '新对话') }
  const confirmEdit = () => { if (editingId && editValue.trim()) onRename(editingId, editValue.trim()); setEditingId(null); setEditValue('') }
  const cancelEdit = () => { setEditingId(null); setEditValue('') }

  const sorted = [...sessions].sort((a, b) => b.updatedAt - a.updatedAt)

  const coreItems = NAV_ITEMS.filter(i => i.section === 'core')
  const monitorItems = NAV_ITEMS.filter(i => i.section === 'monitor')
  const engineItems = NAV_ITEMS.filter(i => i.section === 'engine')
  const infoItems = NAV_ITEMS.filter(i => i.section === 'info')

  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-black/50 md:hidden" onClick={onCloseMobile} aria-hidden="true" />}
      <aside className={[
        'fixed md:static z-40 md:z-auto top-0 left-0 h-full md:h-auto',
        'w-72 md:w-56 flex-shrink-0 bg-sidebar text-textPrimary flex flex-col',
        'transform transition-transform duration-200 ease-in-out',
        open ? 'translate-x-0' : '-translate-x-full md:translate-x-0',
        'border-r border-white/5'
      ].join(' ')}>

        {/* Logo */}
        <div className="flex items-center gap-2 px-3 h-12 border-b border-white/5 flex-shrink-0">
          <div className="w-7 h-7 rounded-md bg-accent flex items-center justify-center">
            <IconSparkles size={16} className="text-white" />
          </div>
          <span className="font-semibold tracking-wide text-sm">太极AGI</span>
        </div>

        {/* Navigation */}
        <div className="flex-1 overflow-y-auto py-2">
          {/* Core Section */}
          <div className="px-2 mb-1">
            <p className="px-2 py-1 text-[10px] text-textSecondary/60 uppercase tracking-wider">核心功能</p>
            {coreItems.map(item => (
              <button
                key={item.id}
                onClick={() => { onSwitchMode(item.id); onCloseMobile() }}
                className={[
                  'w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-xs font-medium transition-colors mb-0.5',
                  mode === item.id
                    ? 'bg-sidebarActive text-white'
                    : 'text-gray-300 hover:bg-sidebarHover hover:text-white'
                ].join(' ')}
              >
                <span className="flex-shrink-0 opacity-80">{item.icon}</span>
                <span>{item.label}</span>
              </button>
            ))}
          </div>

          {/* Divider */}
          <div className="px-3 py-1">
            <div className="border-t border-white/5" />
          </div>

          {/* Monitor Section */}
          <div className="px-2 mb-1">
            <p className="px-2 py-1 text-[10px] text-textSecondary/60 uppercase tracking-wider">TOMAS 监控</p>
            {monitorItems.map(item => (
              <button
                key={item.id}
                onClick={() => { onSwitchMode(item.id); onCloseMobile() }}
                className={[
                  'w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-xs font-medium transition-colors mb-0.5',
                  mode === item.id
                    ? 'bg-sidebarActive text-white'
                    : 'text-gray-300 hover:bg-sidebarHover hover:text-white'
                ].join(' ')}
              >
                <span className="flex-shrink-0 opacity-80">{item.icon}</span>
                <span>{item.label}</span>
              </button>
            ))}
          </div>

          {/* Divider */}
          <div className="px-3 py-1">
            <div className="border-t border-white/5" />
          </div>

          {/* Engine Section */}
          <div className="px-2 mb-1">
            <p className="px-2 py-1 text-[10px] text-textSecondary/60 uppercase tracking-wider">TOMAS 引擎</p>
            {engineItems.map(item => (
              <button
                key={item.id}
                onClick={() => { onSwitchMode(item.id); onCloseMobile() }}
                className={[
                  'w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-xs font-medium transition-colors mb-0.5',
                  mode === item.id
                    ? 'bg-sidebarActive text-white'
                    : 'text-gray-300 hover:bg-sidebarHover hover:text-white'
                ].join(' ')}
              >
                <span className="flex-shrink-0 opacity-80">{item.icon}</span>
                <span>{item.label}</span>
              </button>
            ))}
          </div>

          {/* Divider */}
          <div className="px-3 py-1">
            <div className="border-t border-white/5" />
          </div>

          {/* Chat Sessions (only in chat mode or expandable) */}
          <div className="px-2">
            <button
              onClick={() => setSessionsExpanded(!sessionsExpanded)}
              className="w-full flex items-center justify-between px-2 py-1 text-[10px] text-textSecondary/60 uppercase tracking-wider hover:text-textSecondary transition-colors"
            >
              <span>对话历史</span>
              <span className="text-[9px]">{sessionsExpanded ? '▼' : '▶'}</span>
            </button>
            {sessionsExpanded && (
              <div className="space-y-0.5 mt-1 mb-2">
                {loading ? (
                  <div className="px-3 py-2"><SkeletonText lines={3} /></div>
                ) : sorted.length === 0 ? (
                  <div className="px-3 py-4 text-center text-textSecondary text-[11px]">暂无对话</div>
                ) : (
                  sorted.map(session => {
                    const isActive = session.id === currentSessionId && mode === 'chat'
                    return (
                      <div
                        key={session.id}
                        onMouseEnter={() => setHoveredId(session.id)}
                        onMouseLeave={() => setHoveredId(null)}
                        onClick={() => { if (editingId !== session.id) { onSwitch(session.id); onSwitchMode('chat'); onCloseMobile() } }}
                        className={[
                          'group flex items-center gap-2 px-3 py-2 rounded-md cursor-pointer text-xs',
                          isActive ? 'bg-sidebarActive text-white' : 'text-gray-300 hover:bg-sidebarHover'
                        ].join(' ')}
                      >
                        <IconChat size={14} className="flex-shrink-0 opacity-60" />
                        <div className="flex-1 min-w-0">
                          {editingId === session.id ? (
                            <input
                              ref={editInputRef}
                              value={editValue}
                              onChange={e => setEditValue(e.target.value)}
                              onKeyDown={e => { if (e.key === 'Enter') confirmEdit(); else if (e.key === 'Escape') cancelEdit() }}
                              onBlur={confirmEdit}
                              className="w-full bg-transparent border border-accent/50 rounded px-1 py-0.5 text-xs text-white outline-none"
                              onClick={e => e.stopPropagation()}
                            />
                          ) : (
                            <>
                              <div className="truncate">{session.title || '新对话'}</div>
                              <div className="text-[10px] text-textSecondary">{formatTime(session.updatedAt)}</div>
                            </>
                          )}
                        </div>
                        {(hoveredId === session.id || isActive) && editingId !== session.id && (
                          <div className="flex items-center gap-0.5 flex-shrink-0">
                            <button onClick={e => { e.stopPropagation(); startEdit(session) }} className="p-0.5 rounded hover:bg-white/15 opacity-70 hover:opacity-100" title="重命名">
                              <IconEdit size={11} />
                            </button>
                            <button onClick={e => { e.stopPropagation(); if (window.confirm(`删除「${session.title}」？`)) onDelete(session.id) }} className="p-0.5 rounded hover:bg-white/15 opacity-70 hover:opacity-100" title="删除">
                              <IconTrash size={12} />
                            </button>
                          </div>
                        )}
                      </div>
                    )
                  })
                )}
              </div>
            )}
          </div>

          {/* Info section */}
          <div className="px-2 mt-1">
            {infoItems.map(item => (
              <button
                key={item.id}
                onClick={() => { onSwitchMode(item.id); onCloseMobile() }}
                className={[
                  'w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-xs font-medium transition-colors mb-0.5',
                  mode === item.id
                    ? 'bg-sidebarActive text-white'
                    : 'text-gray-300 hover:bg-sidebarHover hover:text-white'
                ].join(' ')}
              >
                <span className="flex-shrink-0 opacity-80">{item.icon}</span>
                <span>{item.label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Bottom: API Key */}
        <div className="border-t border-white/5 p-2 flex-shrink-0">
          <button
            onClick={onOpenApiKey}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-md hover:bg-sidebarHover transition-colors text-xs"
          >
            <IconKey size={14} />
            <span className="flex-1 text-left">API Key</span>
            <span className={[
              'text-[9px] px-1.5 py-0.5 rounded-full',
              hasApiKey ? 'bg-accent/20 text-accent' : 'bg-rose-500/20 text-rose-400'
            ].join(' ')}>
              {hasApiKey ? 'ON' : 'OFF'}
            </span>
          </button>
        </div>
      </aside>
    </>
  )
}
