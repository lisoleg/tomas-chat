// 单条消息气泡：用户 / 助手区分；Markdown 渲染 + 代码高亮 + 复制按钮
import React, { useCallback, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import hljs from 'highlight.js'
import type { ChatMessage } from '../types'
import { IconBot, IconCheck, IconCopy, IconUser } from './icons'

interface MessageBubbleProps {
  message: ChatMessage
  /** 对该 EML 路由回复不满意时，用同一问题直连 LLM 重试 */
  onRetryDirect?: (messageId: string) => void
  /** 用户反馈（点赞/不满意） */
  onFeedback?: (messageId: string, feedback: 'like' | 'dislike' | null) => void
}

/** 使用 highlight.js 对代码高亮，返回 HTML 字符串 */
function highlightCode(code: string, lang: string): string {
  const language = lang && hljs.getLanguage(lang) ? lang : 'plaintext'
  try {
    return hljs.highlight(code, { language }).value
  } catch {
    return hljs.highlightAuto(code).value
  }
}

/** 抽取 markdown 中的 code 子节点，附加复制按钮 */
function CodeBlock({ language, value }: { language: string; value: string }) {
  const [copied, setCopied] = useState(false)
  const highlighted = useMemo(() => highlightCode(value, language), [value, language])

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      try {
        const ta = document.createElement('textarea')
        ta.value = value
        ta.style.position = 'fixed'
        ta.style.opacity = '0'
        document.body.appendChild(ta)
        ta.select()
        document.execCommand('copy')
        document.body.removeChild(ta)
        setCopied(true)
        setTimeout(() => setCopied(false), 1500)
      } catch {
        // 静默失败
      }
    }
  }, [value])

  return (
    <div className="my-3 rounded-md overflow-hidden border border-white/10 bg-[#0d1117]">
      <div className="flex items-center justify-between px-3 py-1.5 bg-white/5 text-xs text-gray-300">
        <span className="font-mono">{language || 'text'}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-white/10 transition-colors"
          title="复制代码"
        >
          {copied ? <IconCheck size={12} /> : <IconCopy size={12} />}
          <span>{copied ? '已复制' : '复制'}</span>
        </button>
      </div>
      <pre className="overflow-x-auto m-0">
        <code
          className="hljs block px-4 py-3 text-[0.85rem] leading-relaxed"
          dangerouslySetInnerHTML={{ __html: highlighted }}
        />
      </pre>
    </div>
  )
}

/** 模式标签映射 */
function getModeBadge(mode: string): { label: string; color: string; bg: string } | null {
  const config: Record<string, { label: string; color: string; bg: string }> = {
    translator: { label: '📖 翻译官', color: 'text-blue-300', bg: 'bg-blue-600/20 border-blue-600/30' },
    creative: { label: '✍️ 作家', color: 'text-purple-300', bg: 'bg-purple-600/20 border-purple-600/30' },
    creative_gated: { label: '⚠️ φ监管', color: 'text-amber-300', bg: 'bg-amber-600/20 border-amber-600/30' },
    fallback: { label: '🔄 回退', color: 'text-orange-300', bg: 'bg-orange-600/20 border-orange-600/30' },
    error: { label: '❌ 错误', color: 'text-red-300', bg: 'bg-red-600/20 border-red-600/30' },
    direct_retry: { label: '🔄 直连重试', color: 'text-cyan-300', bg: 'bg-cyan-600/20 border-cyan-600/30' },
  }
  return config[mode] || null
}

function MessageBubbleInner({ message, onRetryDirect, onFeedback }: MessageBubbleProps) {
  const isUser = message.role === 'user'
  // 用户消息右对齐气泡；助手消息左对齐
  const wrapperCls = isUser
    ? 'bg-chatBg'
    : 'bg-chatBgAlt border-y border-white/5'

  // 模式标签配置（与 DistillPanel 的 ModeBadge 一致）
  const modeBadge = !isUser && message.mode ? getModeBadge(message.mode) : null

  // 太乙互博推理展开/折叠
  const [leanOpen, setLeanOpen] = useState(false)
  // LLM Prompt 展开/折叠
  const [promptOpen, setPromptOpen] = useState(false)

  return (
    <div className={wrapperCls}>
      <div className="max-w-3xl mx-auto px-4 py-6 flex gap-3 md:gap-4">
        {/* 头像 */}
        <div className="flex-shrink-0">
          {isUser ? (
            <div className="w-8 h-8 rounded-sm bg-[#5436DA] flex items-center justify-center">
              <IconUser size={18} className="text-white" />
            </div>
          ) : (
            <div className="w-8 h-8 rounded-sm bg-accent flex items-center justify-center">
              <IconBot size={18} className="text-white" />
            </div>
          )}
        </div>

        {/* 内容区 */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 text-sm font-semibold mb-1.5 text-textPrimary">
            <span>{isUser ? '你' : 'DeepSeek'}</span>
            {modeBadge && (
              <span className={`text-[11px] px-1.5 py-0.5 rounded-full border ${modeBadge.bg} ${modeBadge.color}`}>
                {modeBadge.label}
              </span>
            )}
            {message.confidence !== undefined && !isUser && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium
                bg-cyan-900/30 text-cyan-300 border border-cyan-600/25">
                <span className="text-[10px]">📡</span>
                <span>{message.subgraphVertexCount != null && message.subgraphEdgeCount != null
                  ? `V:${message.subgraphVertexCount} E:${message.subgraphEdgeCount} · EML路由 · ${Math.round(message.confidence * 100)}%`
                  : `EML路由 · ${Math.round(message.confidence * 100)}%`
                }</span>
              </span>
            )}
          </div>
          <div className="text-[15px] leading-7 text-gray-100 break-words">
            {message.content === '' && message.streaming ? (
              <TypingDots />
            ) : (
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  // 自定义 code 渲染：有 language 走 CodeBlock，否则行内 code
                  code({ inline, className, children, ...props }: {
                    inline?: boolean
                    className?: string
                    children?: React.ReactNode
                  } & React.HTMLAttributes<HTMLElement>) {
                    const match = /language-(\w+)/.exec(className || '')
                    const value = String(children ?? '').replace(/\n$/, '')
                    if (!inline && match) {
                      return <CodeBlock language={match[1]} value={value} />
                    }
                    return (
                      <code
                        className="px-1.5 py-0.5 mx-0.5 rounded bg-black/30 text-[0.9em] font-mono text-rose-200"
                        {...props}
                      >
                        {children}
                      </code>
                    )
                  },
                  // 链接
                  a({ children, ...props }) {
                    return (
                      <a
                        className="text-accent hover:underline"
                        target="_blank"
                        rel="noopener noreferrer"
                        {...props}
                      >
                        {children}
                      </a>
                    )
                  },
                  // 段落
                  p({ children }) {
                    return <p className="my-2 first:mt-0 last:mb-0">{children}</p>
                  },
                  // 列表
                  ul({ children }) {
                    return <ul className="list-disc pl-6 my-2 space-y-1">{children}</ul>
                  },
                  ol({ children }) {
                    return <ol className="list-decimal pl-6 my-2 space-y-1">{children}</ol>
                  },
                  // 引用
                  blockquote({ children }) {
                    return (
                      <blockquote className="border-l-4 border-white/20 pl-3 my-2 text-gray-300 italic">
                        {children}
                      </blockquote>
                    )
                  },
                  // 标题
                  h1({ children }) {
                    return <h1 className="text-2xl font-semibold my-3">{children}</h1>
                  },
                  h2({ children }) {
                    return <h2 className="text-xl font-semibold my-2.5">{children}</h2>
                  },
                  h3({ children }) {
                    return <h3 className="text-lg font-semibold my-2">{children}</h3>
                  },
                  // 表格（gfm）
                  table({ children }) {
                    return (
                      <div className="my-3 overflow-x-auto">
                        <table className="border-collapse border border-white/15 text-sm">
                          {children}
                        </table>
                      </div>
                    )
                  },
                  th({ children }) {
                    return (
                      <th className="border border-white/15 px-3 py-1.5 bg-white/5 text-left">
                        {children}
                      </th>
                    )
                  },
                  td({ children }) {
                    return <td className="border border-white/15 px-3 py-1.5">{children}</td>
                  }
                }}
              >
                {message.content || ''}
              </ReactMarkdown>
            )}
            {/* 太乙互博推理链路：折叠式 LEAN 代码面板 */}
            {!isUser && message.leanTrace && !message.streaming && (
              <div className="mt-3">
                <button
                  onClick={() => setLeanOpen(!leanOpen)}
                  className="flex items-center gap-1.5 text-xs font-mono text-emerald-400/80 hover:text-emerald-300 transition-colors"
                >
                  <span className={`inline-block transition-transform ${leanOpen ? 'rotate-90' : ''}`}>
                    ▸
                  </span>
                  <span>太乙互博 · 推理链路</span>
                  {message.mode && (
                    <span className={`text-[10px] px-1 py-0.5 rounded ${modeBadge?.bg || ''} ${modeBadge?.color || ''}`}>
                      {modeBadge?.label || message.mode}
                    </span>
                  )}
                </button>
                {leanOpen && (
                  <div className="mt-2 rounded-md overflow-hidden border border-emerald-600/20 bg-[#0a0f14]">
                    <div className="flex items-center justify-between px-3 py-1.5 bg-emerald-900/20 border-b border-emerald-600/20">
                      <span className="text-[11px] font-mono text-emerald-400/70">
                        ;; φ-空间推理 · 八元数匹配 · 太乙路由裁决
                      </span>
                      <button
                        onClick={() => {
                          try {
                            navigator.clipboard.writeText(message.leanTrace || '')
                          } catch { /* ignore */ }
                        }}
                        className="text-[10px] text-emerald-500/60 hover:text-emerald-400"
                      >
                        复制 LEAN
                      </button>
                    </div>
                    <pre className="overflow-x-auto m-0 px-4 py-3 text-[0.78rem] leading-relaxed font-mono text-emerald-100/90">
                      <code>{message.leanTrace}</code>
                    </pre>
                  </div>
                )}
              </div>
            )}

            {/* LLM Prompt：发给 DeepSeek 的原始 prompt */}
            {!isUser && message.promptTrace && !message.streaming && (
              <div className="mt-2">
                <button
                  onClick={() => setPromptOpen(!promptOpen)}
                  className="flex items-center gap-1.5 text-xs font-mono text-violet-400/80 hover:text-violet-300 transition-colors"
                >
                  <span className={`inline-block transition-transform ${promptOpen ? 'rotate-90' : ''}`}>
                    ▸
                  </span>
                  <span>LLM Prompt</span>
                  <span className="text-[10px] text-violet-500/50">发给 DeepSeek 的原文</span>
                </button>
                {promptOpen && (
                  <div className="mt-2 rounded-md overflow-hidden border border-violet-600/20 bg-[#0d0a14]">
                    <div className="flex items-center justify-between px-3 py-1.5 bg-violet-900/20 border-b border-violet-600/20">
                      <span className="text-[11px] font-mono text-violet-400/70">
                        system → user 消息序列
                      </span>
                      <button
                        onClick={() => {
                          try {
                            navigator.clipboard.writeText(message.promptTrace || '')
                          } catch { /* ignore */ }
                        }}
                        className="text-[10px] text-violet-500/60 hover:text-violet-400"
                      >
                        复制 Prompt
                      </button>
                    </div>
                    <pre className="overflow-x-auto m-0 px-4 py-3 text-[0.75rem] leading-relaxed font-mono text-violet-100/85 whitespace-pre-wrap">
                      <code>{message.promptTrace}</code>
                    </pre>
                  </div>
                )}
              </div>
            )}

            {/* 用户反馈按钮 */}
            {!isUser && !message.streaming && onFeedback && (
              <div className="mt-3 pt-3 border-t border-white/5 flex items-center gap-2">
                <span className="text-[10px] text-textSecondary/50 mr-1">评价:</span>
                <button
                  onClick={() => onFeedback(message.id, message.feedback === 'like' ? null : 'like')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all border
                    ${message.feedback === 'like'
                      ? 'bg-green-900/30 text-green-300 border-green-600/40 shadow-[0_0_8px_rgba(34,197,94,0.15)]'
                      : 'bg-white/5 text-textSecondary/60 border-white/10 hover:border-green-600/30 hover:text-green-300/70'
                    }`}
                >
                  👍 有帮助
                </button>
                <button
                  onClick={() => onFeedback(message.id, message.feedback === 'dislike' ? null : 'dislike')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all border
                    ${message.feedback === 'dislike'
                      ? 'bg-red-900/30 text-red-300 border-red-600/40 shadow-[0_0_8px_rgba(239,68,68,0.15)]'
                      : 'bg-white/5 text-textSecondary/60 border-white/10 hover:border-red-600/30 hover:text-red-300/70'
                    }`}
                >
                  👎 不满意
                </button>
              </div>
            )}

            {/* 不满意？直连 LLM 重试 */}
            {!isUser && message.mode && message.leanTrace && !message.streaming && onRetryDirect && (
              <div className="mt-3 pt-3 border-t border-white/5">
                <button
                  onClick={() => onRetryDirect(message.id)}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium
                    bg-gradient-to-r from-cyan-900/25 to-blue-900/20
                    border border-cyan-600/25 hover:border-cyan-500/40
                    text-cyan-300/90 hover:text-cyan-200
                    transition-all hover:shadow-[0_0_12px_rgba(6,182,212,0.15)]"
                  title="对 EML 路由的回答不满意？用同一问题直连 DeepSeek 重新回答"
                >
                  <span className="text-base">🔄</span>
                  <span>不满意？让 DeepSeek 直接回答</span>
                  <span className="text-[10px] text-cyan-400/50 ml-1">跳过知识图谱</span>
                </button>
              </div>
            )}

            {/* 流式光标：助手消息且正在流式时显示 */}
            {message.streaming && message.content !== '' && (
              <span className="inline-block w-1.5 h-4 ml-0.5 align-middle bg-gray-200 animate-pulse" />
            )}
            {/* 错误提示 */}
            {message.error && (
              <div className="mt-2 text-rose-300 text-sm">⚠️ 消息获取失败，可重新发送</div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

/** 输入中三点动画 */
function TypingDots() {
  return (
    <div className="flex items-center gap-1.5 py-1">
      <span
        className="w-2 h-2 rounded-full bg-gray-300 animate-pulse-dot"
        style={{ animationDelay: '0s' }}
      />
      <span
        className="w-2 h-2 rounded-full bg-gray-300 animate-pulse-dot"
        style={{ animationDelay: '0.2s' }}
      />
      <span
        className="w-2 h-2 rounded-full bg-gray-300 animate-pulse-dot"
        style={{ animationDelay: '0.4s' }}
      />
    </div>
  )
}

export const MessageBubble = React.memo(MessageBubbleInner, (prev, next) => {
  return prev.message === next.message
    && prev.onRetryDirect === next.onRetryDirect
    && prev.onFeedback === next.onFeedback
})
