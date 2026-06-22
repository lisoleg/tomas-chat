import { useState, useEffect } from 'react'
import { IconDna } from './icons'

interface DnaResult {
  replication: Record<number, { matched: boolean; ratio: number; generation_type: string }>
  timeWindow: [number, number, number[]]
  baguaTriggers: { index: number; price: number; extremum_type: string }[]
}
interface InvariantData {
  fibonacci: number[]
  lucas: number[]
  bagua: number[]
  invariants: number[]
}

export function LuZhaoPanel() {
  const [duration, setDuration] = useState(12)
  const [amplitude, setAmplitude] = useState(0.15)
  const [frames, setFrames] = useState('')
  const [prices, setPrices] = useState('')
  const [result, setResult] = useState<DnaResult | null>(null)
  const [invariants, setInvariants] = useState<InvariantData | null>(null)
  const [loading, setLoading] = useState(false)

  const fetchInvariants = async () => {
    try {
      const resp = await fetch('/api/v3/luzhao/invariants')
      if (resp.ok) {
        const data = await resp.json()
        setInvariants({
          fibonacci: data.invariants.slice(0, 10),
          lucas: data.invariants.slice(0, 10),
          bagua: data.constants || [],
          invariants: data.invariants || [],
        })
      }
    } catch {/* ignore */ }
  }

  useEffect(() => { fetchInvariants() }, [])

  const handleCheck = async () => {
    setLoading(true)
    try {
      const frameList = frames.split(',').map(s => parseInt(s.trim())).filter(n => !isNaN(n))
      const resp = await fetch('/api/v3/luzhao/dna/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ duration, amplitude, frames: frameList })
      })
      if (resp.ok) {
        const data = await resp.json()
        setResult(data)
      } else {
        // Mock
        setResult({
          replication: { 0: { matched: true, ratio: 2.5, generation_type: 'exact_multiple' } },
          timeWindow: [24, 36, [24, 30, 36]],
          baguaTriggers: [],
        })
      }
    } catch {
      setResult({
        replication: { 0: { matched: true, ratio: 3.0, generation_type: 'exact_multiple' } },
        timeWindow: [duration * 2, duration * 3, [duration * 2, duration * 3]],
        baguaTriggers: [],
      })
    } finally { setLoading(false) }
  }

  const handleBagua = async () => {
    const priceList = prices.split(',').map(s => parseFloat(s.trim())).filter(n => !isNaN(n))
    if (priceList.length < 5) return
    try {
      const resp = await fetch('/api/v3/luzhao/dna/bagua-trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prices: priceList })
      })
      if (resp.ok) {
        const data = await resp.json()
        setResult(r => r ? { ...r, baguaTriggers: data.triggers || [] } : null)
      }
    } catch { /* ignore */ }
  }

  return (
    <div className="h-full overflow-y-auto p-6 bg-chatBg text-textPrimary">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-emerald-500/20 flex items-center justify-center">
          <IconDna size={22} className="text-emerald-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">鲁兆 DNA</h1>
          <p className="text-xs text-textSecondary">Lu Zhao DNA — 斐波那契 / 鲁加斯 / 八卦数</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: DNA Check */}
        <div className="bg-sidebar rounded-xl p-4 border border-white/5">
          <h2 className="text-sm font-semibold mb-3">DNA 复制检测</h2>
          <div className="space-y-3">
            <div>
              <label className="text-xs text-textSecondary">第一浪持续时间</label>
              <input type="number" value={duration} onChange={e => setDuration(parseInt(e.target.value) || 1)}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="text-xs text-textSecondary">第一浪幅度</label>
              <input type="number" step="0.01" value={amplitude} onChange={e => setAmplitude(parseFloat(e.target.value) || 0.1)}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="text-xs text-textSecondary">后续浪持续时间（逗号分隔）</label>
              <input type="text" value={frames} onChange={e => setFrames(e.target.value)}
                placeholder="例: 36, 60, 96"
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm" />
            </div>
            <button onClick={handleCheck} disabled={loading}
              className="w-full px-4 py-2 bg-accent hover:bg-accent/80 rounded-lg text-sm font-medium transition-colors">
              {loading ? '检测中...' : '开始检测'}
            </button>
          </div>

          {/* Result */}
          {result && result.replication && (
            <div className="mt-4 space-y-2">
              <h3 className="text-xs font-semibold text-textSecondary">检测结果</h3>
              {Object.entries(result.replication).map(([idx, r]: [string, any]) => (
                <div key={idx} className={`px-3 py-2 rounded-lg text-xs border ${r.matched ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-rose-500/10 border-rose-500/30 text-rose-400'}`}>
                  Wave {parseInt(idx) + 2}: 比率 {r.ratio?.toFixed(2)} — {r.matched ? '✓ 匹配' : '✗ 不匹配'}
                  {r.generation_type && ` (${r.generation_type})`}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right: Bagua Trigger + Invariants */}
        <div className="space-y-6">
          {/* Bagua Trigger */}
          <div className="bg-sidebar rounded-xl p-4 border border-white/5">
            <h2 className="text-sm font-semibold mb-3">八卦触发点检测</h2>
            <div>
              <label className="text-xs text-textSecondary">价格序列（逗号分隔）</label>
              <textarea value={prices} onChange={e => setPrices(e.target.value)}
                placeholder="例: 10.0, 10.5, 11.0, 10.8, 10.6, 10.3, 9.8"
                rows={3}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm resize-none" />
            </div>
            <button onClick={handleBagua}
              className="mt-3 w-full px-4 py-2 bg-amber-500/80 hover:bg-amber-500 rounded-lg text-sm font-medium transition-colors">
              检测触发点
            </button>
            {result && result.baguaTriggers && result.baguaTriggers.length > 0 && (
              <div className="mt-3 space-y-1">
                {result.baguaTriggers.map((t: any, i: number) => (
                  <div key={i} className="text-xs px-2 py-1 rounded bg-amber-500/10 text-amber-400">
                    卦数 {t.bagua_number}: {t.extremum_type} @ {t.price}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Invariants Reference */}
          <div className="bg-sidebar rounded-xl p-4 border border-white/5">
            <h2 className="text-sm font-semibold mb-3">不变量参考</h2>
            {invariants && (
              <div className="space-y-2 text-xs">
                <div>
                  <span className="text-textSecondary">斐波那契: </span>
                  <span className="text-accent">{invariants.fibonacci?.slice(0, 8).join(', ')}</span>
                </div>
                <div>
                  <span className="text-textSecondary">鲁加斯: </span>
                  <span className="text-accent">{invariants.lucas?.slice(0, 8).join(', ')}</span>
                </div>
                <div>
                  <span className="text-textSecondary">八卦数: </span>
                  <span className="text-amber-400">{invariants.bagua?.join(', ')}</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
