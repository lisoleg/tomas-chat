// App v2 — TOMAS Web UI 全面升级
// 集成仪表盘、HY World 3D、审计监控、记忆浏览器、防火墙/路由面板
// 代码分割：首屏必需组件静态导入，其余面板 React.lazy 按需加载
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { loadEMLFromBuffer, TokenBridgeClient } from './api/distiller'
import { ApiKeyModal } from './components/ApiKeyModal'
import { ChatArea } from './components/ChatArea'
import Dashboard from './components/Dashboard'
import { Sidebar } from './components/Sidebar'
import { useChat } from './hooks/useChat'
import { useToast } from './components/Toast'
import type { AppMode, ChatEMLState } from './types'
import { ErrorBoundary } from './components/ErrorBoundary'

// ── 按需加载的面板 (React.lazy) ──────────────────────
// 具名导出的组件需要 .then(m => ({ default: m.X }))
const DistillPanel = lazy(() => import('./components/DistillPanel').then(m => ({ default: m.DistillPanel })))
const TechDocs = lazy(() => import('./components/TechDocs').then(m => ({ default: m.TechDocs })))
// 默认导出的组件直接 import
const WorldModelViewer = lazy(() => import('./components/WorldModelViewer'))
const AuditMonitor = lazy(() => import('./components/AuditMonitor'))
const MemoryBrowser = lazy(() => import('./components/MemoryBrowser'))
const LogsAndRouterPanel = lazy(() => import('./components/LogsAndRouterPanel'))
const IDOPanel = lazy(() => import('./components/IDOPanel'))
const FDEPanel = lazy(() => import('./components/FDEPanel'))
const DualTimelinePanel = lazy(() => import('./components/DualTimelinePanel'))
const ITOTPanel = lazy(() => import('./components/ITOTPanel'))
const TProcessorPanel = lazy(() => import('./components/TProcessorPanel'))
const TShieldPanel = lazy(() => import('./components/TShieldPanel'))
const AEGISPanel = lazy(() => import('./components/AEGISPanel'))
const HypergraphPanel = lazy(() => import('./components/HypergraphPanel'))
const V2Panel = lazy(() => import('./components/V2Panel'))
const AlignmentTriadPanel = lazy(() => import('./components/AlignmentTriadPanel'))
const GoalAgentPanel = lazy(() => import('./components/GoalAgentPanel'))
const CognitiveHealthPanel = lazy(() => import('./components/CognitiveHealthPanel'))
const GrillMePanel = lazy(() => import('./components/GrillMePanel'))
// v3.12 新面板（具名导出）
const LuZhaoPanel = lazy(() => import('./components/LuZhaoPanel').then(m => ({ default: m.LuZhaoPanel })))
const GATPanel = lazy(() => import('./components/GATPanel').then(m => ({ default: m.GATPanel })))
const FinancialWorldPanel = lazy(() => import('./components/FinancialWorldPanel').then(m => ({ default: m.FinancialWorldPanel })))
const TokenizedEconomyPanel = lazy(() => import('./components/TokenizedEconomyPanel').then(m => ({ default: m.TokenizedEconomyPanel })))

// 默认自动加载的 EML 文件（设为空字符串则禁用自动加载，改由聊天时直接查 DB）
const DEFAULT_EML_URL = ''
const DEFAULT_EML_NAME = ''

export default function App() {
  const { error: toastError } = useToast()
  const [apiKeyModalOpen, setApiKeyModalOpen] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [mode, setMode] = useState<AppMode>('dashboard')

  // EML 状态（聊天模式用）
  const [emlState, setEmlState] = useState<ChatEMLState>({
    loaded: false, fileName: '', fileSize: 0, vertexCount: 0, edgeCount: 0, avgDelta: 0
  })
  const [bridgeKey, setBridgeKey] = useState(0)
  const bridgeClient = useRef(new TokenBridgeClient())

  // Listen for navigation events from Dashboard cards
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail
      if (detail?.panel) setMode(detail.panel as AppMode)
    }
    window.addEventListener('tomas-nav', handler)
    return () => window.removeEventListener('tomas-nav', handler)
  }, [])

  // 加载 EML
  const handleLoadEML = useCallback(async (file: File) => {
    try {
      const buffer = await file.arrayBuffer()
      const graph = loadEMLFromBuffer(buffer)
      bridgeClient.current.loadEML(buffer)
      const avgDelta = graph.vertices.length > 0
        ? graph.vertices.reduce((s, v) => s + v.delta, 0) / graph.vertices.length : 0
      setEmlState({
        loaded: true, fileName: file.name, fileSize: buffer.byteLength,
        vertexCount: graph.vertices.length, edgeCount: graph.edges.length, avgDelta
      })
    } catch (err) {
      toastError('加载 EML 失败', err instanceof Error ? err.message : '加载失败')
    }
  }, [])

  // 清除 EML
  const handleClearEML = useCallback(() => {
    bridgeClient.current = new TokenBridgeClient()
    setBridgeKey(k => k + 1)
    setEmlState({ loaded: false, fileName: '', fileSize: 0, vertexCount: 0, edgeCount: 0, avgDelta: 0 })
  }, [])

  const chat = useChat({ bridgeClient: bridgeClient.current, emlState, bridgeKey })

  // 首次自动弹出 API Key 弹窗
  useEffect(() => {
    if (!chat.apiKey) setApiKeyModalOpen(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 自动加载默认 EML 知识库（OwnThink 蒸馏数据）
  useEffect(() => {
    let cancelled = false
    async function autoLoadDefaultEML() {
      try {
        const resp = await fetch(DEFAULT_EML_URL)
        if (!resp.ok) {
          console.warn(`[App] 默认 EML 加载失败: ${resp.status}`)
          return
        }
        const buffer = await resp.arrayBuffer()
        if (cancelled) return

        const graph = loadEMLFromBuffer(buffer)
        bridgeClient.current.loadEML(buffer)

        const avgDelta = graph.vertices.length > 0
          ? graph.vertices.reduce((s, v) => s + v.delta, 0) / graph.vertices.length : 0

        setEmlState({
          loaded: true,
          fileName: DEFAULT_EML_NAME,
          fileSize: buffer.byteLength,
          vertexCount: graph.vertices.length,
          edgeCount: graph.edges.length,
          avgDelta
        })
        console.log(`[App] 自动加载默认 EML 成功: ${DEFAULT_EML_NAME}, ${graph.vertices.length} 顶点, ${graph.edges.length} 边`)
      } catch (err) {
        // 静默失败，不影响主流程（用户可手动上传）
        console.warn('[App] 自动加载默认 EML 失败（非致命）:', err)
      }
    }
    autoLoadDefaultEML()
    return () => { cancelled = true }
  }, [])

  // ── Render active panel ──────────────────────────────

  const renderPanel = () => {
    switch (mode) {
      case 'dashboard':
        return <Dashboard />
      case 'chat':
        return (
          <ChatArea
            currentSession={chat.currentSession}
            isLoading={chat.isLoading}
            hasApiKey={chat.apiKey.trim() !== ''}
            onSend={chat.sendMessage}
            onAbort={chat.abort}
            onClear={chat.clearCurrentSession}
            onOpenApiKey={() => setApiKeyModalOpen(true)}
            onToggleSidebar={() => setSidebarOpen(s => !s)}
            onSwitchToDistill={() => setMode('distill')}
            emlState={emlState}
            onLoadEML={handleLoadEML}
            onClearEML={handleClearEML}
            onRetryDirect={chat.retryDirectLLM}
            onFeedback={(msgId, fb) => chat.setFeedback(chat.currentSessionId ?? '', msgId, fb)}
          />
        )
      case 'distill':
        return (
          <ErrorBoundary>
            <DistillPanel apiKey={chat.apiKey} externalBridgeClient={bridgeClient.current} externalEMLState={emlState} />
          </ErrorBoundary>
        )
      case 'world-model':
        return (
          <ErrorBoundary>
            <WorldModelViewer />
          </ErrorBoundary>
        )
      case 'audit':
        return (
          <ErrorBoundary>
            <AuditMonitor />
          </ErrorBoundary>
        )
      case 'memory':
        return (
          <ErrorBoundary>
            <MemoryBrowser />
          </ErrorBoundary>
        )
      case 'firewall-router':
        return (
          <ErrorBoundary>
            <LogsAndRouterPanel />
          </ErrorBoundary>
        )
      case 'ido':
        return (
          <ErrorBoundary>
            <IDOPanel />
          </ErrorBoundary>
        )
      case 'fde':
        return (
          <ErrorBoundary>
            <FDEPanel />
          </ErrorBoundary>
        )
      case 'dual':
        return (
          <ErrorBoundary>
            <DualTimelinePanel />
          </ErrorBoundary>
        )
      case 'itot':
        return (
          <ErrorBoundary>
            <ITOTPanel />
          </ErrorBoundary>
        )
      case 'tprocessor':
        return (
          <ErrorBoundary>
            <TProcessorPanel />
          </ErrorBoundary>
        )
      case 'tshield':
        return (
          <ErrorBoundary>
            <TShieldPanel />
          </ErrorBoundary>
        )
      case 'aegis':
        return (
          <ErrorBoundary>
            <AEGISPanel />
          </ErrorBoundary>
        )
      case 'hypergraph':
        return (
          <ErrorBoundary>
            <HypergraphPanel />
          </ErrorBoundary>
        )
      case 'v2':
        return (
          <ErrorBoundary>
            <V2Panel />
          </ErrorBoundary>
        )
      case 'alignment-triad':
        return (
          <ErrorBoundary>
            <AlignmentTriadPanel />
          </ErrorBoundary>
        )
      case 'goal-agent':
        return (
          <ErrorBoundary>
            <GoalAgentPanel />
          </ErrorBoundary>
        )
      case 'cognitive-health':
        return (
          <ErrorBoundary>
            <CognitiveHealthPanel />
          </ErrorBoundary>
        )
      case 'grill-me':
        return (
          <ErrorBoundary>
            <GrillMePanel />
          </ErrorBoundary>
        )
      case 'luzhao-dna':
        return (
          <ErrorBoundary>
            <LuZhaoPanel />
          </ErrorBoundary>
        )
      case 'gat-axioms':
        return (
          <ErrorBoundary>
            <GATPanel />
          </ErrorBoundary>
        )
      case 'financial-world':
        return (
          <ErrorBoundary>
            <FinancialWorldPanel />
          </ErrorBoundary>
        )
      case 'tokenized-economy':
        return (
          <ErrorBoundary>
            <TokenizedEconomyPanel />
          </ErrorBoundary>
        )
      case 'docs':
        return <TechDocs />
      default:
        return <Dashboard />
    }
  }

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

      {/* Main content — full height, no top tab bar */}
      <main className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
        <Suspense fallback={<div className="flex items-center justify-center h-full text-textSecondary text-sm">加载中...</div>}>
          {renderPanel()}
        </Suspense>
      </main>

      <ApiKeyModal
        open={apiKeyModalOpen}
        initialValue={chat.apiKey}
        onSave={k => { chat.setApiKey(k); setApiKeyModalOpen(false) }}
        onClose={() => setApiKeyModalOpen(false)}
      />
    </div>
  )
}
