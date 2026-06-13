// 侧边栏：包含 Logo、新建对话按钮、蒸馏模式入口、会话列表、API Key 入口、底部用户信息
import { useState, useRef, useEffect } from 'react'
import type { AppMode, ChatSession } from '../types'
import { IconChat, IconKey, IconPlus, IconSparkles, IconTrash, IconEdit } from './icons'
import { SkeletonText } from './Skeleton'

interface SidebarProps {
  /** 全部会话列表 */
  sessions: ChatSession[]
  /** 当前激活会话 ID */
  currentSessionId: string | null
  /** 切换会话 */
  onSwitch: (id: string) => void
  /** 新建会话 */
  onNew: () => void
  /** 删除会话 */
  onDelete: (id: string) => void
  /** 重命名会话 */
  onRename: (id: string, newTitle: string) => void
  /** 打开 API Key 配置弹窗 */
  onOpenApiKey: () => void
  /** API Key 是否已配置（用于状态指示） */
  hasApiKey: boolean
  /** 移动端是否打开 */
  open: boolean
  /** 移动端关闭回调 */
  onCloseMobile: () => void
  /** 当前应用模式 */
  mode: AppMode
  /** 切换应用模式 */
  onSwitchMode: (mode: AppMode) => void
  /** 是否正在加载会话 */
  loading?: boolean
}

/** 格式化时间戳为相对友好的字符串 */
function formatTime(ts: number): string {
  const date = new Date(ts)
  const now = new Date()
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()
  if (sameDay) {
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}

export function Sidebar(props: SidebarProps) {
  const {
    sessions,
    currentSessionId,
    onSwitch,
    onNew,
    onDelete,
    onRename,
    onOpenApiKey,
    hasApiKey,
    open,
    onCloseMobile,
    mode,
    onSwitchMode,
    loading = false
  } = props

  // 控制删除按钮的 hover 状态（仅在该项 hover 时显示）
  const [hoveredId, setHoveredId] = useState<string | null>(null)

  // 重命名编辑状态
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const editInputRef = useRef<HTMLInputElement>(null)

  // 进入编辑模式时自动聚焦
  useEffect(() => {
    if (editingId && editInputRef.current) {
      editInputRef.current.focus()
      editInputRef.current.select()
    }
  }, [editingId])

  /** 开始编辑 */
  const startEdit = (session: ChatSession) => {
    setEditingId(session.id)
    setEditValue(session.title || '新对话')
  }

  /** 确认编辑 */
  const confirmEdit = () => {
    if (editingId && editValue.trim()) {
      onRename(editingId, editValue.trim())
    }
    setEditingId(null)
    setEditValue('')
  }

  /** 取消编辑 */
  const cancelEdit = () => {
    setEditingId(null)
    setEditValue('')
  }

  // 按 updatedAt 倒序
  const sorted = [...sessions].sort((a, b) => b.updatedAt - a.updatedAt)

  return (
    <>
      {/* 移动端遮罩 */}
      {open && (
        <div
          className="fixed inset-0 z-30 bg-black/50 md:hidden"
          onClick={onCloseMobile}
          aria-hidden="true"
        />
      )}

      <aside
        className={[
          'fixed md:static z-40 md:z-auto',
          'top-0 left-0 h-full md:h-auto',
          'w-72 md:w-64 flex-shrink-0',
          'bg-sidebar text-textPrimary',
          'flex flex-col',
          'transform transition-transform duration-200 ease-in-out',
          open ? 'translate-x-0' : '-translate-x-full md:translate-x-0',
          'border-r border-white/5'
        ].join(' ')}
      >
        {/* 顶部：Logo + 标题 */}
        <div className="flex items-center gap-2 px-4 h-14 border-b border-white/5">
          <div className="w-8 h-8 rounded-md bg-accent flex items-center justify-center">
            <IconSparkles size={18} className="text-white" />
          </div>
          <div className="font-semibold tracking-wide">太极AGI</div>
        </div>

        {/* 新建对话按钮 */}
        <div className="px-3 py-3 space-y-2">
          <button
            onClick={() => {
              onNew()
              onSwitchMode('chat')
              onCloseMobile()
            }}
            className={[
              'w-full flex items-center gap-2 px-3 py-2.5 rounded-md border transition-colors text-sm',
              mode === 'chat'
                ? 'border-accent/50 bg-accent/10 text-accent'
                : 'border-white/20 hover:bg-white/10'
            ].join(' ')}
          >
            <IconPlus size={16} />
            <span>新建对话</span>
          </button>
          <button
            onClick={() => {
              onSwitchMode('distill')
              onCloseMobile()
            }}
            className={[
              'w-full flex items-center gap-2 px-3 py-2.5 rounded-md border transition-colors text-sm',
              mode === 'distill'
                ? 'border-accent/50 bg-accent/10 text-accent'
                : 'border-white/20 hover:bg-white/10'
            ].join(' ')}
          >
            <span>🔬</span>
            <span>蒸馏模式</span>
          </button>
        </div>

        {/* 会话列表 */}
        <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-1">
          {loading ? (
            <div className="px-3 py-3 space-y-2">
              <SkeletonText lines={5} />
            </div>
          ) : sorted.length === 0 ? (
            <div className="px-3 py-6 text-center text-textSecondary text-sm">
              暂无对话，点击上方按钮开始
            </div>
          ) : (
            sorted.map((session) => {
              const isActive = session.id === currentSessionId && mode === 'chat'
              return (
                <div
                  key={session.id}
                  onMouseEnter={() => setHoveredId(session.id)}
                  onMouseLeave={() => setHoveredId(null)}
                  onClick={() => {
                    if (editingId === session.id) return // 编辑中不切换
                    onSwitch(session.id)
                    onSwitchMode('chat')
                    onCloseMobile()
                  }}
                  className={[
                    'group flex items-center gap-2 px-3 py-2.5 rounded-md cursor-pointer text-sm',
                    'transition-colors',
                    isActive
                      ? 'bg-sidebarActive text-white'
                      : 'text-gray-200 hover:bg-sidebarHover'
                  ].join(' ')}
                >
                  <IconChat size={16} className="flex-shrink-0 opacity-80" />
                  <div className="flex-1 min-w-0">
                    {editingId === session.id ? (
                      <input
                        ref={editInputRef}
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') confirmEdit()
                          else if (e.key === 'Escape') cancelEdit()
                        }}
                        onBlur={confirmEdit}
                        className="w-full bg-transparent border border-accent/50 rounded px-1.5 py-0.5 text-sm text-white outline-none focus:border-accent"
                        onClick={(e) => e.stopPropagation()}
                      />
                    ) : (
                      <>
                        <div className="truncate">{session.title || '新对话'}</div>
                        <div className="text-[11px] text-textSecondary truncate">
                          {formatTime(session.updatedAt)}
                        </div>
                      </>
                    )}
                  </div>
                  {/* 操作按钮：hover 时或当前激活时显示 */}
                  {(hoveredId === session.id || isActive) && editingId !== session.id && (
                    <div className="flex items-center gap-0.5 flex-shrink-0">
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          startEdit(session)
                        }}
                        className="p-1 rounded hover:bg-white/15 opacity-80 hover:opacity-100"
                        title="重命名"
                        aria-label="重命名会话"
                      >
                        <IconEdit size={13} />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          if (window.confirm(`确定删除会话「${session.title}」？`)) {
                            onDelete(session.id)
                          }
                        }}
                        className="p-1 rounded hover:bg-white/15 opacity-80 hover:opacity-100"
                        title="删除会话"
                        aria-label="删除会话"
                      >
                        <IconTrash size={14} />
                      </button>
                    </div>
                  )}
                </div>
              )
            })
          )}
        </div>

        {/* 底部：API Key 入口 */}
        <div className="border-t border-white/5 p-3">
          <button
            onClick={onOpenApiKey}
            className="w-full flex items-center gap-2 px-3 py-2.5 rounded-md hover:bg-sidebarHover transition-colors text-sm"
          >
            <IconKey size={16} />
            <span className="flex-1 text-left">API Key 设置</span>
            <span
              className={[
                'text-[10px] px-1.5 py-0.5 rounded-full',
                hasApiKey ? 'bg-accent/20 text-accent' : 'bg-rose-500/20 text-rose-400'
              ].join(' ')}
            >
              {hasApiKey ? '已配置' : '未配置'}
            </span>
          </button>
          <div className="mt-2 px-1 text-[11px] text-textSecondary leading-relaxed">
            Key 仅保存在本地浏览器，不会上传服务器。
          </div>
        </div>
      </aside>
    </>
  )
}
