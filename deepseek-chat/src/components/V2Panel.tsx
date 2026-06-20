/**
 * V2Panel — TOMAS v2.0 六文章升级综合面板
 *
 * 六大标签页覆盖全部 v2 API 端点：
 * 1. HNC NLU 管道 — HNC 解析 + NLU 统计
 * 2. 哥德尔智能体 — 状态查询 + 自改进触发
 * 3. AgentWeb 分布式 — 向量时钟 + 消息收发 + 因果交付
 * 4. 密码学桥接 — Mina SNARK + Celo 支付
 * 5. 因果世界模型 — 学习 + 预测 + 反事实 + SCM
 * 6. EHNN 等变超图 — 前向传播 + 维度扩展 + MUS 双存
 */
import { useState, useCallback } from 'react'
import { apiGet, apiPost, getErrorMessage } from '../api/apiClient'

// ── Types ────────────────────────────────────────────

interface ApiResult {
  success?: boolean
  data?: any
  error?: string
  [key: string]: any
}

type TabId = 'nlu' | 'godel' | 'agentweb' | 'crypto' | 'causal' | 'ehnn'

// ── Shared UI helpers ────────────────────────────────

function ResultBox({ result, error, loading }: { result: any; error: string | null; loading: boolean }) {
  if (loading) return <div className="text-xs text-textSecondary py-2">加载中...</div>
  if (error) return <pre className="text-xs text-rose-400 bg-rose-500/10 rounded-lg p-3 overflow-auto max-h-60 border border-rose-500/20">{error}</pre>
  if (!result) return <div className="text-xs text-textSecondary/50 py-2">等待操作...</div>
  return (
    <pre className="text-xs text-green-300 bg-black/30 rounded-lg p-3 overflow-auto max-h-60 border border-white/5">
      {JSON.stringify(result, null, 2)}
    </pre>
  )
}

function ActionButton({ label, onClick, loading, disabled }: { label: string; onClick: () => void; loading: boolean; disabled?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={loading || disabled}
      className={[
        'px-4 py-2 rounded-lg text-xs font-medium transition-colors flex-shrink-0',
        disabled
          ? 'bg-gray-600/30 text-gray-400 cursor-not-allowed'
          : 'bg-accent hover:bg-accent/80 text-white'
      ].join(' ')}
    >
      {loading ? '执行中...' : label}
    </button>
  )
}

function InputField({ label, value, onChange, placeholder, multiline }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string; multiline?: boolean }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-[10px] text-textSecondary/70 uppercase tracking-wider">{label}</label>
      {multiline ? (
        <textarea
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          rows={4}
          className="bg-black/30 border border-white/5 rounded-lg px-3 py-2 text-xs text-textPrimary outline-none focus:border-accent/50 resize-y font-mono"
        />
      ) : (
        <input
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          className="bg-black/30 border border-white/5 rounded-lg px-3 py-2 text-xs text-textPrimary outline-none focus:border-accent/50 font-mono"
        />
      )}
    </div>
  )
}

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-sidebar/50 rounded-xl border border-white/5 p-4 space-y-3">
      <h3 className="text-xs font-semibold text-textPrimary/90 tracking-wide">{title}</h3>
      {children}
    </div>
  )
}

// ── Tab definitions ──────────────────────────────────

const TABS: { id: TabId; label: string }[] = [
  { id: 'nlu', label: 'HNC NLU' },
  { id: 'godel', label: '哥德尔智能体' },
  { id: 'agentweb', label: 'AgentWeb' },
  { id: 'crypto', label: '密码学桥接' },
  { id: 'causal', label: '因果世界模型' },
  { id: 'ehnn', label: 'EHNN 超图' },
]

// ── Main Component ───────────────────────────────────

export default function V2Panel() {
  const [activeTab, setActiveTab] = useState<TabId>('nlu')

  return (
    <div className="h-full flex flex-col bg-chatBg text-textPrimary overflow-hidden">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-white/5 px-6 py-3">
        <div className="flex items-center gap-2 mb-1">
          <h2 className="text-sm font-bold tracking-wide">TOMAS v2.0 升级面板</h2>
          <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-accent/20 text-accent font-mono">v2.0</span>
        </div>
        <p className="text-[10px] text-textSecondary/60">六文章升级：HNC同构映射 · 哥德尔智能体 · AgentWeb分布式 · Mina+Celo密码学 · Aether因果世界模型 · EML-EHNN等变超图</p>
      </div>

      {/* Tab bar */}
      <div className="flex-shrink-0 flex items-center gap-1 px-6 py-2 border-b border-white/5 overflow-x-auto">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={[
              'px-3 py-1.5 rounded-md text-xs font-medium transition-colors whitespace-nowrap',
              activeTab === tab.id
                ? 'bg-accent/20 text-accent border border-accent/30'
                : 'text-textSecondary hover:text-textPrimary hover:bg-white/5 border border-transparent'
            ].join(' ')}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto p-6">
        {activeTab === 'nlu' && <NLUTab />}
        {activeTab === 'godel' && <GodelTab />}
        {activeTab === 'agentweb' && <AgentWebTab />}
        {activeTab === 'crypto' && <CryptoTab />}
        {activeTab === 'causal' && <CausalTab />}
        {activeTab === 'ehnn' && <EHNNTab />}
      </div>
    </div>
  )
}

// ── Tab 1: HNC NLU ───────────────────────────────────

function NLUTab() {
  const [text, setText] = useState('我吃苹果')
  const [result, setResult] = useState<any>(null)
  const [stats, setStats] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const parse = useCallback(async () => {
    setLoading(true); setError(null); setResult(null)
    try {
      const resp = await apiPost<ApiResult>('/v2/nlu/parse', { text })
      setResult(resp)
    } catch (e) { setError(getErrorMessage(e)) }
    finally { setLoading(false) }
  }, [text])

  const fetchStats = useCallback(async () => {
    setLoading(true); setError(null); setStats(null)
    try {
      const resp = await apiGet<ApiResult>('/v2/nlu/stats')
      setStats(resp)
    } catch (e) { setError(getErrorMessage(e)) }
    finally { setLoading(false) }
  }, [])

  return (
    <div className="space-y-4 max-w-3xl">
      <SectionCard title="HNC 句类解析">
        <InputField label="输入文本" value={text} onChange={setText} placeholder="输入中文句子进行 HNC 解析" />
        <div className="flex items-center gap-2">
          <ActionButton label="解析" onClick={parse} loading={loading} />
          <ActionButton label="管道统计" onClick={fetchStats} loading={loading} />
        </div>
        {result && <ResultBox result={result} error={null} loading={false} />}
        {stats && <ResultBox result={stats} error={null} loading={false} />}
        {error && <ResultBox result={null} error={error} loading={false} />}
      </SectionCard>
    </div>
  )
}

// ── Tab 2: Godel Agent ───────────────────────────────

function GodelTab() {
  const [observation, setObservation] = useState('Add input validation to payment handler')
  const [status, setStatus] = useState<any>(null)
  const [improveResult, setImproveResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchStatus = useCallback(async () => {
    setLoading(true); setError(null); setStatus(null)
    try {
      const resp = await apiGet<ApiResult>('/v2/godel/status')
      setStatus(resp)
    } catch (e) { setError(getErrorMessage(e)) }
    finally { setLoading(false) }
  }, [])

  const improve = useCallback(async () => {
    setLoading(true); setError(null); setImproveResult(null)
    try {
      const resp = await apiPost<ApiResult>('/v2/godel/improve', { observation })
      setImproveResult(resp)
    } catch (e) { setError(getErrorMessage(e)) }
    finally { setLoading(false) }
  }, [observation])

  return (
    <div className="space-y-4 max-w-3xl">
      <SectionCard title="哥德尔智能体状态">
        <ActionButton label="获取状态" onClick={fetchStatus} loading={loading} />
        {status && <ResultBox result={status} error={null} loading={false} />}
      </SectionCard>

      <SectionCard title="触发自改进循环">
        <InputField label="观测描述" value={observation} onChange={setObservation} placeholder="描述需要改进的观测" multiline />
        <ActionButton label="触发自改进" onClick={improve} loading={loading} />
        {improveResult && <ResultBox result={improveResult} error={null} loading={false} />}
        {error && <ResultBox result={null} error={error} loading={false} />}
      </SectionCard>
    </div>
  )
}

// ── Tab 3: AgentWeb ──────────────────────────────────

function AgentWebTab() {
  const [nodeId, setNodeId] = useState('api_node')
  const [tickResult, setTickResult] = useState<any>(null)
  const [vcA, setVcA] = useState('{"api_node": 3, "peer_1": 1}')
  const [vcB, setVcB] = useState('{"api_node": 2, "peer_1": 2}')
  const [compareResult, setCompareResult] = useState<any>(null)
  const [targetNode, setTargetNode] = useState('node-b')
  const [content, setContent] = useState('{"msg": "hello"}')
  const [sendResult, setSendResult] = useState<any>(null)
  const [pendingResult, setPendingResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const tick = useCallback(async () => {
    setLoading(true); setError(null); setTickResult(null)
    try {
      const resp = await apiPost<ApiResult>('/v2/vector-clock/tick', { node_id: nodeId })
      setTickResult(resp)
    } catch (e) { setError(getErrorMessage(e)) }
    finally { setLoading(false) }
  }, [nodeId])

  const compare = useCallback(async () => {
    setLoading(true); setError(null); setCompareResult(null)
    try {
      const resp = await apiPost<ApiResult>('/v2/vector-clock/compare', {
        vc_a: JSON.parse(vcA),
        vc_b: JSON.parse(vcB),
      })
      setCompareResult(resp)
    } catch (e) {
      setError(e instanceof SyntaxError ? 'JSON 解析错误: ' + e.message : getErrorMessage(e))
    } finally { setLoading(false) }
  }, [vcA, vcB])

  const send = useCallback(async () => {
    setLoading(true); setError(null); setSendResult(null)
    try {
      const resp = await apiPost<ApiResult>('/v2/agentweb/send', {
        target_node: targetNode,
        content: JSON.parse(content),
      })
      setSendResult(resp)
    } catch (e) {
      setError(e instanceof SyntaxError ? 'JSON 解析错误: ' + e.message : getErrorMessage(e))
    } finally { setLoading(false) }
  }, [targetNode, content])

  const fetchPending = useCallback(async () => {
    setLoading(true); setError(null); setPendingResult(null)
    try {
      const resp = await apiGet<ApiResult>('/v2/causal-delivery/pending')
      setPendingResult(resp)
    } catch (e) { setError(getErrorMessage(e)) }
    finally { setLoading(false) }
  }, [])

  return (
    <div className="space-y-4 max-w-3xl">
      <SectionCard title="向量时钟 — 本地事件 Tick">
        <InputField label="节点 ID" value={nodeId} onChange={setNodeId} />
        <ActionButton label="Tick" onClick={tick} loading={loading} />
        {tickResult && <ResultBox result={tickResult} error={null} loading={false} />}
      </SectionCard>

      <SectionCard title="向量时钟 — 比较">
        <div className="grid grid-cols-2 gap-3">
          <InputField label="时钟 A (JSON)" value={vcA} onChange={setVcA} multiline />
          <InputField label="时钟 B (JSON)" value={vcB} onChange={setVcB} multiline />
        </div>
        <ActionButton label="比较" onClick={compare} loading={loading} />
        {compareResult && <ResultBox result={compareResult} error={null} loading={false} />}
      </SectionCard>

      <SectionCard title="AgentWeb — 发送消息">
        <div className="grid grid-cols-2 gap-3">
          <InputField label="目标节点" value={targetNode} onChange={setTargetNode} />
          <InputField label="消息内容 (JSON)" value={content} onChange={setContent} multiline />
        </div>
        <div className="flex items-center gap-2">
          <ActionButton label="发送" onClick={send} loading={loading} />
          <ActionButton label="待交付消息" onClick={fetchPending} loading={loading} />
        </div>
        {sendResult && <ResultBox result={sendResult} error={null} loading={false} />}
        {pendingResult && <ResultBox result={pendingResult} error={null} loading={false} />}
        {error && <ResultBox result={null} error={error} loading={false} />}
      </SectionCard>
    </div>
  )
}

// ── Tab 4: Crypto (Mina + Celo) ──────────────────────

function CryptoTab() {
  const [snapEvent, setSnapEvent] = useState('{"snap_id": "test-1", "candidate_id": "c1", "reason": "test"}')
  const [snapResult, setSnapResult] = useState<any>(null)
  const [minaStats, setMinaStats] = useState<any>(null)
  const [fromAddr, setFromAddr] = useState('0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B')
  const [toAddr, setToAddr] = useState('0xBb5801a7D398351b8bE11C439e05C5B3259aeC9B')
  const [amount, setAmount] = useState('10.0')
  const [currency, setCurrency] = useState('cUSD')
  const [payResult, setPayResult] = useState<any>(null)
  const [txHash, setTxHash] = useState('')
  const [verifyResult, setVerifyResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const wrapSnap = useCallback(async () => {
    setLoading(true); setError(null); setSnapResult(null)
    try {
      const resp = await apiPost<ApiResult>('/v2/mina/wrap-snap', { snap_event: JSON.parse(snapEvent) })
      setSnapResult(resp)
    } catch (e) {
      setError(e instanceof SyntaxError ? 'JSON 解析错误: ' + e.message : getErrorMessage(e))
    } finally { setLoading(false) }
  }, [snapEvent])

  const fetchMinaStats = useCallback(async () => {
    setLoading(true); setError(null); setMinaStats(null)
    try {
      const resp = await apiGet<ApiResult>('/v2/mina/stats')
      setMinaStats(resp)
    } catch (e) { setError(getErrorMessage(e)) }
    finally { setLoading(false) }
  }, [])

  const pay = useCallback(async () => {
    setLoading(true); setError(null); setPayResult(null)
    try {
      const resp = await apiPost<ApiResult>('/v2/celo/pay', {
        from_addr: fromAddr, to_addr: toAddr, amount: parseFloat(amount), currency
      })
      setPayResult(resp)
    } catch (e) { setError(getErrorMessage(e)) }
    finally { setLoading(false) }
  }, [fromAddr, toAddr, amount, currency])

  const verify = useCallback(async () => {
    setLoading(true); setError(null); setVerifyResult(null)
    try {
      const resp = await apiPost<ApiResult>('/v2/celo/verify', { tx_hash: txHash })
      setVerifyResult(resp)
    } catch (e) { setError(getErrorMessage(e)) }
    finally { setLoading(false) }
  }, [txHash])

  return (
    <div className="space-y-4 max-w-3xl">
      <SectionCard title="Mina SNARK — 封装 κ-Snap 证明">
        <InputField label="Snap 事件 (JSON)" value={snapEvent} onChange={setSnapEvent} multiline />
        <div className="flex items-center gap-2">
          <ActionButton label="封装证明" onClick={wrapSnap} loading={loading} />
          <ActionButton label="Mina 统计" onClick={fetchMinaStats} loading={loading} />
        </div>
        {snapResult && <ResultBox result={snapResult} error={null} loading={false} />}
        {minaStats && <ResultBox result={minaStats} error={null} loading={false} />}
      </SectionCard>

      <SectionCard title="Celo — 稳定币支付">
        <div className="grid grid-cols-2 gap-3">
          <InputField label="发送方地址" value={fromAddr} onChange={setFromAddr} />
          <InputField label="接收方地址" value={toAddr} onChange={setToAddr} />
          <InputField label="金额" value={amount} onChange={setAmount} />
          <InputField label="币种" value={currency} onChange={setCurrency} />
        </div>
        <ActionButton label="支付" onClick={pay} loading={loading} />
        {payResult && <ResultBox result={payResult} error={null} loading={false} />}
      </SectionCard>

      <SectionCard title="Celo — 验证交易">
        <InputField label="交易哈希" value={txHash} onChange={setTxHash} placeholder="0x..." />
        <ActionButton label="验证" onClick={verify} loading={loading} />
        {verifyResult && <ResultBox result={verifyResult} error={null} loading={false} />}
        {error && <ResultBox result={null} error={error} loading={false} />}
      </SectionCard>
    </div>
  )
}

// ── Tab 5: Causal World Model ────────────────────────

function CausalTab() {
  const [learnData, setLearnData] = useState('{"pos": [0,0], "vel": [1,1], "force": [0,0]}')
  const [learnResult, setLearnResult] = useState<any>(null)
  const [currentState, setCurrentState] = useState('{"pos": [0,0], "vel": [1,0]}')
  const [action, setAction] = useState('{"force": [0,1]}')
  const [predictResult, setPredictResult] = useState<any>(null)
  const [cfState, setCfState] = useState('{"pos": [0,0], "vel": [1,0]}')
  const [cfIntervention, setCfIntervention] = useState('{"force": [0,5]}')
  const [cfResult, setCfResult] = useState<any>(null)
  const [scmSummary, setScmSummary] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const learn = useCallback(async () => {
    setLoading(true); setError(null); setLearnResult(null)
    try {
      const resp = await apiPost<ApiResult>('/v2/world-model/learn', { data: JSON.parse(learnData) })
      setLearnResult(resp)
    } catch (e) {
      setError(e instanceof SyntaxError ? 'JSON 解析错误: ' + e.message : getErrorMessage(e))
    } finally { setLoading(false) }
  }, [learnData])

  const predict = useCallback(async () => {
    setLoading(true); setError(null); setPredictResult(null)
    try {
      const resp = await apiPost<ApiResult>('/v2/world-model/predict', {
        current_state: JSON.parse(currentState),
        action: JSON.parse(action),
      })
      setPredictResult(resp)
    } catch (e) {
      setError(e instanceof SyntaxError ? 'JSON 解析错误: ' + e.message : getErrorMessage(e))
    } finally { setLoading(false) }
  }, [currentState, action])

  const counterfactual = useCallback(async () => {
    setLoading(true); setError(null); setCfResult(null)
    try {
      const resp = await apiPost<ApiResult>('/v2/world-model/counterfactual', {
        state: JSON.parse(cfState),
        intervention: JSON.parse(cfIntervention),
      })
      setCfResult(resp)
    } catch (e) {
      setError(e instanceof SyntaxError ? 'JSON 解析错误: ' + e.message : getErrorMessage(e))
    } finally { setLoading(false) }
  }, [cfState, cfIntervention])

  const fetchScmSummary = useCallback(async () => {
    setLoading(true); setError(null); setScmSummary(null)
    try {
      const resp = await apiGet<ApiResult>('/v2/aether/scm/summary')
      setScmSummary(resp)
    } catch (e) { setError(getErrorMessage(e)) }
    finally { setLoading(false) }
  }, [])

  return (
    <div className="space-y-4 max-w-3xl">
      <SectionCard title="因果学习 — 从数据学习因果结构">
        <InputField label="观测数据 (JSON)" value={learnData} onChange={setLearnData} multiline />
        <ActionButton label="学习" onClick={learn} loading={loading} />
        {learnResult && <ResultBox result={learnResult} error={null} loading={false} />}
      </SectionCard>

      <SectionCard title="状态预测 — H_hard 物理守恒律不可绕过">
        <div className="grid grid-cols-2 gap-3">
          <InputField label="当前状态 (JSON)" value={currentState} onChange={setCurrentState} multiline />
          <InputField label="动作 (JSON)" value={action} onChange={setAction} multiline />
        </div>
        <ActionButton label="预测" onClick={predict} loading={loading} />
        {predictResult && <ResultBox result={predictResult} error={null} loading={false} />}
      </SectionCard>

      <SectionCard title="反事实推理 — do-calculus">
        <div className="grid grid-cols-2 gap-3">
          <InputField label="状态 (JSON)" value={cfState} onChange={setCfState} multiline />
          <InputField label="干预 (JSON)" value={cfIntervention} onChange={setCfIntervention} multiline />
        </div>
        <ActionButton label="反事实推理" onClick={counterfactual} loading={loading} />
        {cfResult && <ResultBox result={cfResult} error={null} loading={false} />}
      </SectionCard>

      <SectionCard title="Aether SCM 图分析">
        <ActionButton label="SCM 摘要" onClick={fetchScmSummary} loading={loading} />
        {scmSummary && <ResultBox result={scmSummary} error={null} loading={false} />}
        {error && <ResultBox result={null} error={error} loading={false} />}
      </SectionCard>
    </div>
  )
}

// ── Tab 6: EHNN + MUS ────────────────────────────────

function EHNNTab() {
  const [hypergraph, setHypergraph] = useState('{"edges": [[0,1,2],[1,2,3]], "node_features": [[0.1],[0.2],[0.3],[0.4]]}')
  const [forwardResult, setForwardResult] = useState<any>(null)
  const [newDim, setNewDim] = useState('128')
  const [expandResult, setExpandResult] = useState<any>(null)
  const [musKey, setMusKey] = useState('wave_particle')
  const [musEntry, setMusEntry] = useState('{"description_a": "波", "description_b": "粒", "code_a": "wave_fn", "code_b": "particle_fn"}')
  const [musResult, setMusResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const forward = useCallback(async () => {
    setLoading(true); setError(null); setForwardResult(null)
    try {
      const resp = await apiPost<ApiResult>('/v2/ehnn/forward', { hypergraph: JSON.parse(hypergraph) })
      setForwardResult(resp)
    } catch (e) {
      setError(e instanceof SyntaxError ? 'JSON 解析错误: ' + e.message : getErrorMessage(e))
    } finally { setLoading(false) }
  }, [hypergraph])

  const expandDim = useCallback(async () => {
    setLoading(true); setError(null); setExpandResult(null)
    try {
      const resp = await apiPost<ApiResult>('/v2/ehnn/expand-dim', { new_dim: parseInt(newDim) })
      setExpandResult(resp)
    } catch (e) { setError(getErrorMessage(e)) }
    finally { setLoading(false) }
  }, [newDim])

  const storeMus = useCallback(async () => {
    setLoading(true); setError(null); setMusResult(null)
    try {
      const resp = await apiPost<ApiResult>('/v2/mus/dual-store', {
        key: musKey,
        entry: JSON.parse(musEntry),
      })
      setMusResult(resp)
    } catch (e) {
      setError(e instanceof SyntaxError ? 'JSON 解析错误: ' + e.message : getErrorMessage(e))
    } finally { setLoading(false) }
  }, [musKey, musEntry])

  return (
    <div className="space-y-4 max-w-3xl">
      <SectionCard title="EHNN 前向传播 — 等变超图推理">
        <InputField label="超图数据 (JSON)" value={hypergraph} onChange={setHypergraph} multiline />
        <ActionButton label="前向传播" onClick={forward} loading={loading} />
        {forwardResult && <ResultBox result={forwardResult} error={null} loading={false} />}
      </SectionCard>

      <SectionCard title="GPCT 动态维度扩展">
        <InputField label="新维度" value={newDim} onChange={setNewDim} />
        <ActionButton label="扩展维度" onClick={expandDim} loading={loading} />
        {expandResult && <ResultBox result={expandResult} error={null} loading={false} />}
      </SectionCard>

      <SectionCard title="MUS 双存 — 互斥稳态保留">
        <div className="grid grid-cols-2 gap-3">
          <InputField label="键名" value={musKey} onChange={setMusKey} />
          <InputField label="条目 (JSON)" value={musEntry} onChange={setMusEntry} multiline />
        </div>
        <ActionButton label="存储" onClick={storeMus} loading={loading} />
        {musResult && <ResultBox result={musResult} error={null} loading={false} />}
        {error && <ResultBox result={null} error={error} loading={false} />}
      </SectionCard>
    </div>
  )
}
