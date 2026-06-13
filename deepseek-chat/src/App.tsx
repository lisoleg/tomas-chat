// App 根组件：整合侧边栏、聊天主区域、蒸馏面板、API Key 弹窗
// 聊天模式支持 EML 路由（翻译官/作家），蒸馏模式不变
import { useCallback, useEffect, useRef, useState } from 'react'
import { loadEMLFromBuffer, mergeEMLGraphs, TokenBridgeClient } from './api/distiller'
import { ApiKeyModal } from './components/ApiKeyModal'
import { ChatArea } from './components/ChatArea'
import { DistillPanel } from './components/DistillPanel'
import { TechDocs } from './components/TechDocs'
import { Sidebar } from './components/Sidebar'
import { useChat } from './hooks/useChat'
import { useToast } from './components/Toast'
import type { AppMode, ChatEMLState, EMLGraphData } from './types'

export default function App() {
  const { error: toastError } = useToast()
  const [apiKeyModalOpen, setApiKeyModalOpen] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [mode, setMode] = useState<AppMode>('chat')

  // EML 状态（聊天模式用）
  const [emlState, setEmlState] = useState<ChatEMLState>({
    loaded: false, fileName: '', fileSize: 0, vertexCount: 0, edgeCount: 0, avgDelta: 0
  })
  // bridgeKey 变化时，useChat 重新同步 bridgeClient 引用
  const [bridgeKey, setBridgeKey] = useState(0)

  // Token Bridge 客户端（持久化实例）
  const bridgeClient = useRef(new TokenBridgeClient())

  // 加载 EML 文件到 Token Bridge
  const handleLoadEML = useCallback(async (file: File) => {
    try {
      const buffer = await file.arrayBuffer()
      const graph = loadEMLFromBuffer(buffer)
      bridgeClient.current.loadEML(buffer)

      const avgDelta = graph.vertices.length > 0
        ? graph.vertices.reduce((s, v) => s + v.delta, 0) / graph.vertices.length
        : 0

      setEmlState({
        loaded: true,
        fileName: file.name,
        fileSize: buffer.byteLength,
        vertexCount: graph.vertices.length,
        edgeCount: graph.edges.length,
        avgDelta
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : '加载失败'
      toastError('加载 EML 失败', message)
    }
  }, [])

  // 清除 EML
  const handleClearEML = useCallback(() => {
    bridgeClient.current = new TokenBridgeClient()
    setBridgeKey((k) => k + 1)
    setEmlState({
      loaded: false, fileName: '', fileSize: 0, vertexCount: 0, edgeCount: 0, avgDelta: 0
    })
  }, [])

  // 创建 useChat，传入 bridgeClient 和 emlState + bridgeKey 保证 ref 同步
  const chat = useChat({ bridgeClient: bridgeClient.current, emlState, bridgeKey })

  // 首次访问时若未配置 Key，自动弹出配置弹窗
  useEffect(() => {
    if (!chat.apiKey) {
      setApiKeyModalOpen(true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 启动时自动加载 public/ 下所有已有 EML 文件 + 概念名 JSON，默认进入 EML 路由模式
  useEffect(() => {
    const emlPaths = [
      '/ownthink_sample.eml'
    ]

    async function autoLoadAll() {
      const graphs: EMLGraphData[] = []
      const allConceptNames = new Map<number, string>()
      const conceptJsonDataList: Array<{ data: any; idOffset: number }> = []
      let idOffset = 0

      for (const path of emlPaths) {
        try {
          // 拉取 EML 二进制
          const resp = await fetch(path)
          if (!resp.ok) continue
          const buffer = await resp.arrayBuffer()
          const graph = loadEMLFromBuffer(buffer)
          graphs.push(graph)

          // 拉取对应的概念名 JSON（EML 二进制不存文本）
          const jsonPath = path.replace('.eml', '.concepts.json')
          try {
            const jsonResp = await fetch(jsonPath)
            if (jsonResp.ok) {
              const data = await jsonResp.json()
              for (const c of data.concepts) {
                allConceptNames.set(c.id + idOffset, c.concept)
              }
              // 收集 JSON data（含 domain 字段），供后续设置 corpusName
              conceptJsonDataList.push({ data, idOffset })
            }
          } catch {
            // 概念名文件不存在则跳过
          }

          idOffset += graph.vertices.length
        } catch {
          // 个别文件不存在或损坏则跳过
        }
      }

      if (graphs.length === 0) return

      const merged = mergeEMLGraphs(graphs)
      bridgeClient.current.loadEML(merged)
      // 注入真实概念名（替换 concept_0 等占位符）
      if (allConceptNames.size > 0) {
        bridgeClient.current.loadConceptNames(allConceptNames)
      }

      // 同时设置 corpusName（领域标签，来自 concepts.json 的 domain 字段）
      for (const { data, idOffset } of conceptJsonDataList) {
        const adjustedData = {
          ...data,
          concepts: data.concepts.map((c: any) => ({
            ...c,
            id: c.id + idOffset,
          })),
        }
        bridgeClient.current.loadConceptNamesFromJson(adjustedData)
      }
      
      const avgDelta = merged.vertices.length > 0
        ? merged.vertices.reduce((s, v) => s + v.delta, 0) / merged.vertices.length
        : 0

      setEmlState({
        loaded: true,
        fileName: `合并知识库 (${graphs.length} 个 EML)`,
        fileSize: 0,  // 合并后不单独记录大小
        vertexCount: merged.vertices.length,
        edgeCount: merged.edges.length,
        avgDelta
      })
      setBridgeKey((k) => k + 1)
    }

    autoLoadAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="h-screen w-screen overflow-hidden bg-chatBg text-textPrimary flex">
      <Sidebar
        sessions={chat.sessions}
        currentSessionId={chat.currentSessionId}
        onSwitch={chat.switchSession}
        onNew={chat.newSession}
        onDelete={chat.deleteSession}
        onRename={chat.renameSession}
        onOpenApiKey={() => setApiKeyModalOpen(true)}
        hasApiKey={chat.apiKey.trim() !== ''}
        open={sidebarOpen}
        onCloseMobile={() => setSidebarOpen(false)}
        mode={mode}
        onSwitchMode={setMode}
        loading={chat.loading}
      />

      <main className="flex-1 flex flex-col min-w-0 min-h-0">
        {/* 模式切换标签栏 */}
        <div className="h-10 flex items-center justify-center gap-1 border-b border-white/5 bg-chatBg/95 backdrop-blur flex-shrink-0">
          <button
            onClick={() => setMode('chat')}
            className={[
              'px-4 py-1.5 rounded-md text-sm font-medium transition-colors',
              mode === 'chat'
                ? 'bg-accent/20 text-accent'
                : 'text-textSecondary hover:text-textPrimary hover:bg-white/5'
            ].join(' ')}
          >
            💬 聊天模式{emlState.loaded ? ' + EML' : ''}
          </button>
          <button
            onClick={() => setMode('distill')}
            className={[
              'px-4 py-1.5 rounded-md text-sm font-medium transition-colors',
              mode === 'distill'
                ? 'bg-accent/20 text-accent'
                : 'text-textSecondary hover:text-textPrimary hover:bg-white/5'
            ].join(' ')}
          >
            🔬 蒸馏模式
          </button>
          <button
            onClick={() => setMode('docs')}
            className={[
              'px-4 py-1.5 rounded-md text-sm font-medium transition-colors',
              mode === 'docs'
                ? 'bg-accent/20 text-accent'
                : 'text-textSecondary hover:text-textPrimary hover:bg-white/5'
            ].join(' ')}
          >
            📄 技术文档
          </button>
        </div>

        {/* 根据模式渲染不同内容 */}
        {mode === 'chat' ? (
          <ChatArea
            currentSession={chat.currentSession}
            isLoading={chat.isLoading}
            hasApiKey={chat.apiKey.trim() !== ''}
            onSend={chat.sendMessage}
            onAbort={chat.abort}
            onClear={chat.clearCurrentSession}
            onOpenApiKey={() => setApiKeyModalOpen(true)}
            onToggleSidebar={() => setSidebarOpen((s) => !s)}
            onSwitchToDistill={() => setMode('distill')}
            emlState={emlState}
            onLoadEML={handleLoadEML}
            onClearEML={handleClearEML}
            onRetryDirect={chat.retryDirectLLM}
            onFeedback={(msgId, fb) => chat.setFeedback(chat.currentSessionId ?? '', msgId, fb)}
          />
        ) : mode === 'docs' ? (
          <TechDocs />
        ) : (
          <DistillPanel apiKey={chat.apiKey} externalBridgeClient={bridgeClient.current} externalEMLState={emlState} />
        )}
      </main>

      <ApiKeyModal
        open={apiKeyModalOpen}
        initialValue={chat.apiKey}
        onSave={(k) => {
          chat.setApiKey(k)
          setApiKeyModalOpen(false)
        }}
        onClose={() => setApiKeyModalOpen(false)}
      />
    </div>
  )
}
