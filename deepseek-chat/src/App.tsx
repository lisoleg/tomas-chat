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

  // ── 已禁用：启动时不再自动加载 public/ 下的 EML 文件 ──
  // 数据已迁移至 SQLite 后端 API，由 DistillPanel 按需加载
  // 如需恢复本地 EML 自动加载，取消下方注释即可
  //
  // useEffect(() => {
  //   const emlPaths = [
  //     '/ownthink_sample.eml'
  //   ]
  //   ... 原有自动加载逻辑 ...
  // }, [])

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
