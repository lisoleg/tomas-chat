// 聊天状态管理 Hook：封装会话增删改查 + 消息发送/流式接收 + EML 路由
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { streamChatCompletion } from '../api/deepseek'
import type { TokenBridgeClient } from '../api/distiller'
import {
  loadApiKey,
  loadSessions,
  saveApiKey as persistApiKey,
  saveSessions
} from '../store/sessionStore'
import type { ChatEMLState, ChatMessage, ChatSession, MessageRole } from '../types'

/** 生成唯一 ID（crypto.randomUUID 优先，回退到时间戳） */
function genId(prefix = 'id'): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return `${prefix}_${crypto.randomUUID()}`
    }
  } catch {
    // 忽略
  }
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

/** 取首条用户消息前 20 字作为默认标题 */
function deriveTitle(text: string): string {
  const cleaned = text.replace(/\s+/g, ' ').trim()
  if (!cleaned) return '新对话'
  return cleaned.length > 50 ? `${cleaned.slice(0, 50)}…` : cleaned
}

/** 创建空白会话 */
function createSession(): ChatSession {
  const now = Date.now()
  return {
    id: genId('session'),
    title: '新对话',
    messages: [],
    createdAt: now,
    updatedAt: now
  }
}

export interface UseChatOptions {
  /** Token Bridge 客户端（EML 路由用，可选） */
  bridgeClient?: TokenBridgeClient | null
  /** EML 加载状态 */
  emlState?: ChatEMLState
  /** bridgeKey 变化时强制同步 bridgeClient 引用 */
  bridgeKey?: number
}

export interface UseChatReturn {
  /** 全部会话 */
  sessions: ChatSession[]
  /** 当前激活会话 */
  currentSession: ChatSession | null
  /** 当前会话 ID */
  currentSessionId: string | null
  /** 是否正在加载会话 */
  loading: boolean
  /** 是否正在流式接收 */
  isLoading: boolean
  /** API Key */
  apiKey: string
  /** 设置 API Key */
  setApiKey: (key: string) => void
  /** 切换会话 */
  switchSession: (id: string) => void
  /** 新建会话 */
  newSession: () => void
  /** 删除会话 */
  deleteSession: (id: string) => void
  /** 重命名会话 */
  renameSession: (id: string, newTitle: string) => void
  /** 清空当前会话消息 */
  clearCurrentSession: () => void
  /** 发送消息 */
  sendMessage: (text: string) => Promise<void>
  /** 对某条 EML 路由回复不满意，用同一问题直连 LLM 重试 */
  retryDirectLLM: (assistantMessageId: string) => Promise<void>
  /** 设置消息的用户反馈 */
  setFeedback: (sessionId: string, messageId: string, feedback: 'like' | 'dislike' | null) => void
  /** 中止当前流式请求 */
  abort: () => void
}

/** 聊天核心 Hook */
export function useChat(options: UseChatOptions = {}): UseChatReturn {
  const { bridgeClient, emlState, bridgeKey } = options

  // 1. 初始化状态：从后端 API 恢复（异步）
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [apiKey, setApiKeyState] = useState<string>('')
  const [isLoading, setIsLoading] = useState<boolean>(false)
  const [loading, setLoading] = useState<boolean>(true)

  // 加载会话和 API Key
  useEffect(() => {
    async function loadInitialData() {
      try {
        const loadedSessions = await loadSessions()
        setSessions(loadedSessions)
        if (loadedSessions.length > 0) {
          setCurrentSessionId(loadedSessions[0].id)
        }
        const loadedApiKey = await loadApiKey()
        setApiKeyState(loadedApiKey)
      } finally {
        setLoading(false)
      }
    }
    loadInitialData()
  }, [])  // 空依赖数组，只在挂载时执行一次

  // 2. 会话列表变化时持久化
  useEffect(() => {
    saveSessions(sessions)
  }, [sessions])

  // 3. 当前会话（派生）
  const currentSession = useMemo<ChatSession | null>(() => {
    if (!currentSessionId) return null
    return sessions.find((s) => s.id === currentSessionId) ?? null
  }, [sessions, currentSessionId])

  // 4. 始终引用最新的 sessions / currentSessionId（避免闭包陷阱）
  const sessionsRef = useRef<ChatSession[]>(sessions)
  const currentIdRef = useRef<string | null>(currentSessionId)
  useEffect(() => {
    sessionsRef.current = sessions
  }, [sessions])
  useEffect(() => {
    currentIdRef.current = currentSessionId
  }, [currentSessionId])

  // 5. AbortController 引用，用于中止流式请求
  const abortRef = useRef<AbortController | null>(null)

  // 用 ref 持有 bridgeClient 和 emlState 以在 sendMessage 闭包中拿到最新值
  const bridgeRef = useRef(bridgeClient)
  const emlRef = useRef(emlState)
  useEffect(() => {
    bridgeRef.current = bridgeClient
  }, [bridgeClient, bridgeKey])
  useEffect(() => {
    emlRef.current = emlState
  }, [emlState])

  /** 设置 API Key 并持久化 */
  const setApiKey = useCallback((key: string) => {
    setApiKeyState(key)
    persistApiKey(key)
  }, [])

  /** 新建会话并切换过去 */
  const newSession = useCallback(() => {
    const session = createSession()
    setSessions((prev) => [session, ...prev])
    setCurrentSessionId(session.id)
  }, [])

  /** 切换会话 */
  const switchSession = useCallback((id: string) => {
    setCurrentSessionId(id)
  }, [])

  /** 删除会话（若删除的是当前会话，自动切换到列表中第一个或新建） */
  const deleteSession = useCallback((id: string) => {
    setSessions((prev) => {
      const next = prev.filter((s) => s.id !== id)
      if (id === currentIdRef.current) {
        setCurrentSessionId(next.length > 0 ? next[0].id : null)
      }
      return next
    })
  }, [])

  /** 重命名会话 */
  const renameSession = useCallback((id: string, newTitle: string) => {
    const trimmed = newTitle.trim()
    if (!trimmed) return
    setSessions((prev) =>
      prev.map((s) =>
        s.id === id ? { ...s, title: trimmed, updatedAt: Date.now() } : s
      )
    )
  }, [])

  /** 清空当前会话消息（保留会话本身） */
  const clearCurrentSession = useCallback(() => {
    const id = currentIdRef.current
    if (!id) return
    setSessions((prev) =>
      prev.map((s) =>
        s.id === id ? { ...s, messages: [], title: '新对话', updatedAt: Date.now() } : s
      )
    )
  }, [])

  /** 中止当前请求 */
  const abort = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
  }, [])

  /** 设置消息的用户反馈 */
  const setFeedback = useCallback((sessionId: string, messageId: string, feedback: 'like' | 'dislike' | null) => {
    setSessions(prev => prev.map(s => {
      if (s.id !== sessionId) return s
      return {
        ...s,
        messages: s.messages.map(m => {
          if (m.id !== messageId) return m
          return { ...m, feedback }
        })
      }
    }))
  }, [])

  /** 更新助手消息：增量追加文本 */
  const appendDelta = useCallback(
    (activeId: string, assistantId: string, delta: string, meta?: { mode?: string; confidence?: number }) => {
      setSessions((prev) =>
        prev.map((s) => {
          if (s.id !== activeId) return s
          return {
            ...s,
            updatedAt: Date.now(),
            messages: s.messages.map((m) => {
              if (m.id !== assistantId) return m
              const updated: ChatMessage = { ...m, content: m.content + delta }
              if (meta?.mode) updated.mode = meta.mode
              if (meta?.confidence !== undefined) updated.confidence = meta.confidence
              return updated
            })
          }
        })
      )
    },
    []
  )

  /** 标记助手消息结束 */
  const finishAssistant = useCallback(
    (activeId: string, assistantId: string, meta?: { mode?: string; confidence?: number; leanTrace?: string; promptTrace?: string }) => {
      setSessions((prev) =>
        prev.map((s) => {
          if (s.id !== activeId) return s
          return {
            ...s,
            updatedAt: Date.now(),
            messages: s.messages.map((m) => {
              if (m.id !== assistantId) return m
              const updated: ChatMessage = { ...m, streaming: false }
              if (meta?.mode) updated.mode = meta.mode
              if (meta?.confidence !== undefined) updated.confidence = meta.confidence
              if (meta?.leanTrace) updated.leanTrace = meta.leanTrace
              if (meta?.promptTrace) updated.promptTrace = meta.promptTrace
              return updated
            })
          }
        })
      )
    },
    []
  )

  /** 标记助手消息出错 */
  const errorAssistant = useCallback(
    (activeId: string, assistantId: string, errMsg: string, meta?: { mode?: string; confidence?: number; leanTrace?: string; promptTrace?: string }) => {
      setSessions((prev) =>
        prev.map((s) => {
          if (s.id !== activeId) return s
          return {
            ...s,
            updatedAt: Date.now(),
            messages: s.messages.map((m) => {
              if (m.id !== assistantId) {
                return m
              }
              const updated: ChatMessage = {
                ...m,
                streaming: false,
                error: true,
                content: m.content || `⚠️ ${errMsg}`
              }
              if (meta?.mode) updated.mode = meta.mode
              if (meta?.confidence !== undefined) updated.confidence = meta.confidence
              if (meta?.leanTrace) updated.leanTrace = meta.leanTrace
              if (meta?.promptTrace) updated.promptTrace = meta.promptTrace
              return updated
            })
          }
        })
      )
    },
    []
  )

  /** 将 messages 数组格式化为可读的 prompt 文本 */
  const formatPromptTrace = (msgs: Array<{ role: string; content: string }>) => {
    let systemIdx = 0
    return msgs.map((m, i) => {
      let label = ''
      if (m.role === 'system') {
        // 第一条 system = 行为指令，后续 system = 知识图谱注入上下文
        label = systemIdx === 0 ? '系统指令 · 行为约束' : '知识图谱上下文 · EML 注入'
        systemIdx++
      } else if (m.role === 'user') {
        // 只有最后一条 user 是当前提问，之前的 user 是历史对话（仅回退模式可能出现）
        const isLastUser = i === msgs.length - 1
        label = isLastUser ? '当前提问' : '历史提问 (⚠️ 不应出现)'
      } else {
        label = m.role === 'assistant' ? '助手回复' : m.role
      }
      return `── ${m.role.toUpperCase()} · ${label} ──\n${m.content.length > 800 ? m.content.slice(0, 800) + '\n…(截断)' : m.content}`
    }).join('\n\n')
  }

  /**
   * EML 路由发送：通过 Token Bridge 智能路由（翻译官/作家）
   */
  const sendViaEMLBridge = useCallback(
    async (trimmed: string, activeId: string, assistantId: string) => {
      const bc = bridgeRef.current
      if (!bc || !bc.getGraph()) {
        // 回退：无 EML 时不应该走到这里，但做防御
        return false
      }

      // Step 1: EML 搜索 + 获取上下文
      const { matched, confidence, emlContext, phi } = await bc.searchAndGetContext(trimmed)

      if (matched.length === 0) {
        // 无匹配概念，回退
        return false
      }

      // Step 2: 路由判断 — 置信度 ≥ 0.5 → 翻译官，< 0.5 → 作家
      const isTranslator = confidence >= 0.5

      if (isTranslator) {
        // —— 翻译官模式 ——
        // 有 API Key：用 LLM 将 EML 概念组织成自然语言
        // 无 API Key：回退到模板（概念名已修正）
        if (apiKey.trim()) {
          const mode = 'translator'
          const controller = new AbortController()
          abortRef.current = controller

          const messages: Array<{ role: MessageRole; content: string }> = [
            {
              role: 'system',
              content: `你是 TOMAS/太极OS 的翻译官（📖 知识复述引擎）。你的任务是将知识图谱中的概念和关系组织成自然、流畅的中文回答。

规则：
1. 严格基于下方提供的 EML 知识图谱上下文回答，不要凭空发挥
2. 用自然的口语化中文组织，像在给朋友讲解知识
3. 如果问"是谁"，介绍其身份、贡献、相关人物/概念
4. 如果问"是什么"，定义概念并说明关联知识
5. 保持回答简洁但不失完整，不超过 500 字
6. 绝对不要输出代码块、不要提及"概念ID"或"δ值"等内部术语`
            },
            {
              role: 'system',
              content: `以下是 EML 知识图谱中的相关概念和关系，请严格基于此回答：\n\n${emlContext}`
            },
            { role: 'user', content: trimmed }
          ]

          let firstChunk = true
          await streamChatCompletion({
            apiKey,
            messages,
            signal: controller.signal,
            temperature: 0.3,  // 低温度，保持事实准确
            onDelta: (delta) => {
              appendDelta(activeId, assistantId, delta,
                firstChunk ? { mode, confidence } : undefined
              )
              firstChunk = false
            },
            onComplete: () => {
              const leanTrace = bc.buildLeanTrace(trimmed, matched, confidence, mode, phi ?? undefined)
              const promptTrace = formatPromptTrace(messages as Array<{ role: string; content: string }>)
              finishAssistant(activeId, assistantId, { mode, confidence, leanTrace, promptTrace })
            },
            onError: (err) => {
              const leanTrace = bc.buildLeanTrace(trimmed, matched, confidence, 'error', phi ?? undefined)
              const promptTrace = formatPromptTrace(messages as Array<{ role: string; content: string }>)
              errorAssistant(activeId, assistantId, err.message, { mode: 'error', confidence, leanTrace, promptTrace })
            }
          })
        } else {
          // 无 API Key：模板生成（概念名已从 JSON 加载）
          const result = bc.translatorResponse(trimmed, matched, 2000)
          const mode = 'translator'

          const chars = result.text.split('')
          const batchSize = 4
          for (let i = 0; i < chars.length; i += batchSize) {
            if (abortRef.current?.signal.aborted) {
              finishAssistant(activeId, assistantId, { mode, confidence })
              return true
            }
            const chunk = chars.slice(i, i + batchSize).join('')
            appendDelta(activeId, assistantId, chunk, i === 0 ? { mode, confidence } : undefined)
            await new Promise((r) => setTimeout(r, 8))
          }
          const leanTrace = bc.buildLeanTrace(trimmed, matched, confidence, mode, phi ?? undefined)
          finishAssistant(activeId, assistantId, { mode, confidence, leanTrace })
        }
        return true
      }

      // —— 作家模式：DeepSeek LLM + EML 上下文，流式输出 ——
      if (!apiKey.trim()) {
        // 无 API Key，回退到翻译官
        const result = bc.translatorResponse(trimmed, matched, 2000)
        const mode = 'fallback'
        const chars = result.text.split('')
        const batchSize = 4
        for (let i = 0; i < chars.length; i += batchSize) {
          if (abortRef.current?.signal.aborted) break
          const chunk = chars.slice(i, i + batchSize).join('')
          appendDelta(activeId, assistantId, chunk, i === 0 ? { mode, confidence } : undefined)
          await new Promise((r) => setTimeout(r, 8))
        }
        const leanTrace = bc.buildLeanTrace(trimmed, matched, confidence, mode, phi ?? undefined)
        finishAssistant(activeId, assistantId, { mode, confidence, leanTrace })
        return true
      }

      // 构建带 EML 上下文的消息
      const messages: Array<{ role: MessageRole; content: string }> = [
        {
          role: 'system',
          content: `你是 TOMAS/太极OS 的创造性引擎（✍️ 作家模式）。你的回答应基于提供的 EML 知识图谱上下文。

规则：
1. 如果上下文提供了明确信息，优先基于上下文回答
2. 如果上下文不足，可以基于你的知识进行创造性扩展，但需注明来源
3. 保持回答专业、准确、简洁，有层次感
4. 用中文回答
5. 不要编造不存在的概念或事实`
        },
        {
          role: 'system',
          content: `以下是 EML 知识图谱中的相关概念和关系，请优先参考：\n\n${emlContext}`
        },
        { role: 'user', content: trimmed }
      ]

      const mode = 'creative'
      const controller = new AbortController()
      abortRef.current = controller

      let firstChunk = true
      await streamChatCompletion({
        apiKey,
        messages,
        signal: controller.signal,
        onDelta: (delta) => {
          appendDelta(
            activeId, assistantId, delta,
            firstChunk ? { mode, confidence } : undefined
          )
          firstChunk = false
        },
        onComplete: () => {
          const leanTrace = bc.buildLeanTrace(trimmed, matched, confidence, mode, phi ?? undefined)
          const promptTrace = formatPromptTrace(messages as Array<{ role: string; content: string }>)
          finishAssistant(activeId, assistantId, { mode, confidence, leanTrace, promptTrace })
        },
        onError: (err) => {
          const leanTrace = bc.buildLeanTrace(trimmed, matched, confidence, 'error', phi ?? undefined)
          const promptTrace = formatPromptTrace(messages as Array<{ role: string; content: string }>)
          errorAssistant(activeId, assistantId, err.message, { mode: 'error', confidence, leanTrace, promptTrace })
        }
      })

      return true
    },
    [apiKey, appendDelta, finishAssistant, errorAssistant]
  )

  /** 对某条 EML 路由回复不满意，找到原问题直连 LLM 重新回答 */
  const retryDirectLLM = useCallback(
    async (assistantMessageId: string) => {
      const activeId = currentIdRef.current
      const target = sessionsRef.current.find((s) => s.id === activeId)
      if (!target) return

      // 找到该助手消息和它之前的用户消息
      const msgIdx = target.messages.findIndex((m) => m.id === assistantMessageId)
      if (msgIdx < 1) return
      const prevMsg = target.messages[msgIdx - 1]
      if (prevMsg.role !== 'user') return
      const originalText = prevMsg.content.trim()
      if (!originalText) return

      // 创建新的用户 + 助手消息对（追加在末尾）
      const userMsg: ChatMessage = {
        id: genId('msg'),
        role: 'user',
        content: originalText,
        createdAt: Date.now()
      }
      const newAssistantId = genId('msg')
      const assistantMsg: ChatMessage = {
        id: newAssistantId,
        role: 'assistant',
        content: '',
        createdAt: Date.now(),
        streaming: true
      }

      setSessions((prev) =>
        prev.map((s) => {
          if (s.id !== activeId) return s
          return {
            ...s,
            messages: [...s.messages, userMsg, assistantMsg],
            updatedAt: Date.now()
          }
        })
      )

      // 直连 LLM（完全不经过 EML），仅发送原问题 + 系统指令，不堆历史
      setIsLoading(true)

      const messages: Array<{ role: MessageRole; content: string }> = [
        {
          role: 'system',
          content: '你是 DeepSeek，一个知识渊博的 AI 助手。请直接、准确地回答用户的问题。用中文回复。'
        },
        { role: 'user', content: originalText }
      ]

      const controller = new AbortController()
      abortRef.current = controller

      await streamChatCompletion({
        apiKey,
        messages,
        signal: controller.signal,
        onDelta: (delta) => {
          appendDelta(activeId!, newAssistantId!, delta, { mode: 'direct_retry' })
        },
        onComplete: () => {
          const promptTrace = formatPromptTrace(messages as Array<{ role: string; content: string }>)
          finishAssistant(activeId!, newAssistantId!, { mode: 'direct_retry', promptTrace })
          setIsLoading(false)
          abortRef.current = null
        },
        onError: (err) => {
          const promptTrace = formatPromptTrace(messages as Array<{ role: string; content: string }>)
          errorAssistant(activeId!, newAssistantId!, err.message ?? '', { mode: 'error', promptTrace })
          setIsLoading(false)
          abortRef.current = null
        }
      })
    },
    [apiKey, appendDelta, finishAssistant, errorAssistant]
  )

  /** 发送消息（含流式响应 + EML 路由） */
  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim()
      if (!trimmed || isLoading) return

      // 1) 确保有当前会话；没有则创建
      let activeId = currentIdRef.current
      if (!activeId) {
        const session = createSession()
        activeId = session.id
        setSessions((prev) => [session, ...prev])
        setCurrentSessionId(session.id)
      }

      // 2) 用户消息 + 助手占位消息
      const userMsg: ChatMessage = {
        id: genId('msg'),
        role: 'user',
        content: trimmed,
        createdAt: Date.now()
      }
      const assistantId = genId('msg')
      const assistantMsg: ChatMessage = {
        id: assistantId,
        role: 'assistant',
        content: '',
        createdAt: Date.now(),
        streaming: true
      }

      // 3) 推入会话（同时计算是否首条用户消息以决定是否重命名）
      setSessions((prev) =>
        prev.map((s) => {
          if (s.id !== activeId) return s
          const userCount = s.messages.filter((m) => m.role === 'user').length
          const isFirstUser = userCount === 0
          return {
            ...s,
            title: isFirstUser ? deriveTitle(trimmed) : s.title,
            messages: [...s.messages, userMsg, assistantMsg],
            updatedAt: Date.now()
          }
        })
      )

      // 4) 判断是否走 EML 路由
      setIsLoading(true)
      const eml = emlRef.current

      if (eml?.loaded && bridgeRef.current?.getGraph()) {
        // 🔗 EML 路由：翻译官/作家智能路由
        const handled = await sendViaEMLBridge(trimmed, activeId, assistantId)
        if (handled) {
          setIsLoading(false)
          abortRef.current = null
          return
        }
        // EML 路由未处理（无匹配概念），回退到普通聊天
      }

      // 5) 普通聊天：仅发当前问题 + 简洁系统指令，不堆历史消息
      const messages: Array<{ role: MessageRole; content: string }> = [
        {
          role: 'system',
          content: '你是 DeepSeek，一个知识渊博的 AI 助手。请直接、准确地回答用户的问题。用中文回复。'
        },
        { role: 'user', content: trimmed }
      ]

      const controller = new AbortController()
      abortRef.current = controller

      await streamChatCompletion({
        apiKey,
        messages,
        signal: controller.signal,
        onDelta: (delta) => {
          appendDelta(activeId, assistantId, delta)
        },
        onComplete: () => {
          const promptTrace = formatPromptTrace(messages as Array<{ role: string; content: string }>)
          finishAssistant(activeId, assistantId, { promptTrace })
          setIsLoading(false)
          abortRef.current = null
        },
        onError: (err) => {
          const promptTrace = formatPromptTrace(messages as Array<{ role: string; content: string }>)
          errorAssistant(activeId, assistantId, err.message, { leanTrace: '', promptTrace })
          setIsLoading(false)
          abortRef.current = null
        }
      })
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [apiKey, isLoading, sendViaEMLBridge, appendDelta, finishAssistant, errorAssistant]
  )

  return {
    sessions,
    currentSession,
    currentSessionId,
    loading,
    isLoading,
    apiKey,
    setApiKey,
    switchSession,
    newSession,
    deleteSession,
    renameSession,
    clearCurrentSession,
    sendMessage,
    retryDirectLLM,
    setFeedback,
    abort
  }
}
