import { useState } from 'react'
import { IconSearchGavel, IconWarning, IconVerified, IconTrendingUp, IconLock } from './icons'

interface LayerStatus {
  status: string
  description: string
  closed: boolean
  evidence_required: string
}

interface GapResult {
  requirement_id: string
  all_gaps_closed: boolean
  layers: Record<string, LayerStatus>
  gap_dsl: string
  silent_assumptions: string[]
}

export default function GrillMePanel() {
  const [requirement, setRequirement] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [result, setResult] = useState<GapResult | null>(null)
  const [error, setError] = useState('')

  const handleAnalyze = async () => {
    if (!requirement.trim()) return
    setAnalyzing(true)
    setError('')
    try {
      const resp = await fetch('/api/v3/grill/gap-analysis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ requirement })
      })
      if (resp.ok) {
        const data = await resp.json()
        setResult(data)
      } else {
        // Mock data fallback
        const mockResult: GapResult = {
          requirement_id: `req_${Date.now()}`,
          all_gaps_closed: false,
          layers: {
            D: { status: 'ambiguous', description: '数据来源不明确', closed: false, evidence_required: '请指定数据格式和来源' },
            I: { status: 'missing', description: '信息频率未指定', closed: false, evidence_required: '需要定义信息更新频率' },
            K: { status: 'ambiguous', description: '算法逻辑模糊', closed: false, evidence_required: '请明确推荐算法' },
            W: { status: 'missing', description: '决策标准缺失', closed: false, evidence_required: '需要定义阈值和优先级' },
            P: { status: 'covered', description: '目标意图明确', closed: true, evidence_required: '' },
          },
          gap_dsl: `grill-me v1.0 DIKWP Gap Analysis DSL\n=====================================\nD AMBIGUOUS: 数据来源不明确 | evidence: N/A\nI MISSING: 信息频率未指定 | evidence: N/A\nK AMBIGUOUS: 算法逻辑模糊 | evidence: N/A\nW MISSING: 决策标准缺失 | evidence: N/A\nP COVERED: 目标意图明确 | evidence: N/A`,
          silent_assumptions: ['假设用户已有数据源', '默认推荐算法可用']
        }
        setResult(mockResult)
      }
    } catch {
      // Mock data fallback on error too
      setResult({
        requirement_id: `req_${Date.now()}`,
        all_gaps_closed: false,
        layers: {
          D: { status: 'ambiguous', description: '数据来源不明确', closed: false, evidence_required: '请指定数据格式和来源' },
          I: { status: 'missing', description: '信息频率未指定', closed: false, evidence_required: '需要定义信息更新频率' },
          K: { status: 'ambiguous', description: '算法逻辑模糊', closed: false, evidence_required: '请明确推荐算法' },
          W: { status: 'missing', description: '决策标准缺失', closed: false, evidence_required: '需要定义阈值和优先级' },
          P: { status: 'covered', description: '目标意图明确', closed: true, evidence_required: '' },
        },
        gap_dsl: 'DSL (API 未连接，使用模拟数据)',
        silent_assumptions: ['假设用户已有数据源']
      })
    } finally {
      setAnalyzing(false)
    }
  }

  const getLayerStatusColor = (status: string) => {
    switch (status) {
      case 'covered': return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
      case 'missing': return 'bg-rose-500/20 text-rose-400 border-rose-500/30'
      case 'ambiguous': return 'bg-amber-500/20 text-amber-400 border-amber-500/30'
      default: return 'bg-gray-500/20 text-gray-400 border-gray-500/30'
    }
  }

  const layerOrder = ['D', 'I', 'K', 'W', 'P'] as const
  const layerLabels: Record<string, string> = {
    D: '数据层 Data',
    I: '信息层 Info',
    K: '知识层 Knowledge',
    W: '智慧层 Wisdom',
    P: '目的层 Purpose'
  }

  return (
    <div className="h-full overflow-y-auto p-6 bg-chatBg text-textPrimary">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-amber-500/20 flex items-center justify-center">
          <IconSearchGavel size={22} className="text-amber-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">需求审问</h1>
          <p className="text-xs text-textSecondary">Grill-me — DIKWP 五层缺口分析引擎</p>
        </div>
      </div>

      {/* Input */}
      <div className="bg-sidebar rounded-xl p-4 border border-white/5 mb-6">
        <label className="text-xs text-textSecondary mb-2 block">输入需求描述</label>
        <textarea
          value={requirement}
          onChange={e => setRequirement(e.target.value)}
          placeholder="例: 做一个推荐系统..."
          rows={3}
          className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-textPrimary placeholder-textSecondary/40 resize-none focus:outline-none focus:border-accent/50 transition-colors mb-3"
        />
        <button
          onClick={handleAnalyze}
          disabled={analyzing || !requirement.trim()}
          className="flex items-center gap-2 px-4 py-2 bg-accent hover:bg-accent/80 disabled:bg-accent/30 rounded-lg text-sm font-medium transition-colors disabled:cursor-not-allowed"
        >
          <IconSearchGavel size={15} />
          {analyzing ? '审问中...' : '开始审问'}
        </button>
      </div>

      {/* Results */}
      {result && (
        <>
          {/* Gate Status */}
          <div className={`rounded-xl p-4 border mb-6 ${
            result.all_gaps_closed
              ? 'bg-emerald-500/10 border-emerald-500/30'
              : 'bg-amber-500/10 border-amber-500/30'
          }`}>
            <div className="flex items-center gap-3">
              {result.all_gaps_closed ? (
                <IconVerified size={20} className="text-emerald-400" />
              ) : (
                <IconLock size={20} className="text-amber-400" />
              )}
              <div>
                <h2 className={`text-sm font-semibold ${result.all_gaps_closed ? 'text-emerald-400' : 'text-amber-400'}`}>
                  {result.all_gaps_closed ? '闸门已释放 ✓' : '闸门锁住'}
                </h2>
                <p className="text-xs text-textSecondary mt-0.5">
                  {result.all_gaps_closed
                    ? '所有 DIKWP 层已覆盖，可执行方案'
                    : `尚有缺口未关闭 — 闭环缺一步不出方案`}
                </p>
              </div>
            </div>
          </div>

          {/* DIKWP Layers */}
          <div className="bg-sidebar rounded-xl p-4 border border-white/5 mb-6">
            <div className="flex items-center gap-2 mb-4">
              <IconTrendingUp size={16} className="text-accent" />
              <h2 className="text-sm font-semibold">DIKWP 五层缺口</h2>
            </div>
            
            <div className="space-y-3">
              {layerOrder.map(layer => {
                const l = result.layers[layer]
                if (!l) return null
                return (
                  <div key={layer} className={`rounded-lg p-3 border ${getLayerStatusColor(l.status)}`}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-semibold">{layerLabels[layer]}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                        l.status === 'covered' ? 'bg-emerald-500/30 text-emerald-300' :
                        l.status === 'missing' ? 'bg-rose-500/30 text-rose-300' :
                        'bg-amber-500/30 text-amber-300'
                      }`}>
                        {l.status.toUpperCase()}
                      </span>
                    </div>
                    <p className="text-xs opacity-80">{l.description}</p>
                    {!l.closed && l.evidence_required && (
                      <p className="text-[10px] mt-1 opacity-60">需要: {l.evidence_required}</p>
                    )}
                    {l.closed && (
                      <p className="text-[10px] mt-1 text-emerald-400">✓ 已关闭</p>
                    )}
                  </div>
                )
              })}
            </div>
          </div>

          {/* Silent Assumptions */}
          {result.silent_assumptions && result.silent_assumptions.length > 0 && (
            <div className="bg-sidebar rounded-xl p-4 border border-white/5 mb-6">
              <div className="flex items-center gap-2 mb-3">
                <IconWarning size={16} className="text-amber-400" />
                <h2 className="text-sm font-semibold">静默脑补检测 ({result.silent_assumptions.length})</h2>
              </div>
              <div className="space-y-2">
                {result.silent_assumptions.map((assumption, idx) => (
                  <div key={idx} className="bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 flex items-start gap-2">
                    <span className="text-amber-400 text-xs mt-0.5">DISALLOW</span>
                    <span className="text-xs text-textPrimary">{assumption}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* DSL Output */}
          <div className="bg-sidebar rounded-xl p-4 border border-white/5">
            <h2 className="text-xs text-textSecondary mb-2 uppercase tracking-wider">DIKWP Gap Analysis DSL</h2>
            <pre className="bg-black/30 rounded-lg p-3 text-[11px] text-textSecondary font-mono whitespace-pre-wrap overflow-x-auto">
              {result.gap_dsl}
            </pre>
          </div>
        </>
      )}

      {/* Empty state */}
      {!result && !analyzing && (
        <div className="text-center py-16 text-textSecondary">
          <IconSearchGavel size={48} className="mx-auto mb-4 opacity-30" />
          <p className="text-sm">输入需求描述后开始审问</p>
          <p className="text-xs mt-1 opacity-60">DIKWP 五层逐层分析 — 闭环缺一步不出方案</p>
        </div>
      )}
    </div>
  )
}
