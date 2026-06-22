import { useState, useEffect } from 'react'
import { IconFinancial } from './icons'

interface EnpvResult {
  enpv: number
  explanation: string
  should_trade: boolean
}
interface BreakerResult {
  state: string
  reason: string
  triggered: boolean
}

export function FinancialWorldPanel() {
  const [sessionId, setSessionId] = useState('')
  const [lobStatus, setLobStatus] = useState<any>(null)
  const [price, setPrice] = useState('')
  const [size, setSize] = useState('')
  const [loading, setLoading] = useState(false)
  const [enpvResult, setEnpvResult] = useState<EnpvResult | null>(null)
  const [breakerResult, setBreakerResult] = useState<BreakerResult | null>(null)
  const [error, setError] = useState('')

  const createSession = async () => {
    setLoading(true)
    setError('')
    try {
      const resp = await fetch('/api/v3/financial/lob/create', { method: 'POST' })
      if (resp.ok) {
        const data = await resp.json()
        setSessionId(data.session_id)
      } else {
        setError('创建会话失败')
      }
    } catch {
      setError('后端未连接')
    }
    setLoading(false)
  }

  const fetchStatus = async () => {
    if (!sessionId) return
    try {
      const resp = await fetch(`/api/v3/financial/lob/${sessionId}`)
      if (resp.ok) setLobStatus(await resp.json())
    } catch { /* ignore */ }
  }

  const addOrder = async (side: 'bid' | 'ask') => {
    if (!sessionId || !price) return
    setError('')
    try {
      await fetch('/api/v3/financial/lob/add-order', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, side, price: parseFloat(price), size: parseFloat(size) || 1 })
      })
      fetchStatus()
    } catch {
      setError('下单失败')
    }
  }

  const calcEnpv = async () => {
    setError('')
    try {
      const resp = await fetch('/api/v3/financial/enpv', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prob_fill: 0.8, expected_profit: 1.0, slippage_cost: 0.1, opportunity_cost: 0.05 })
      })
      if (resp.ok) {
        const d = await resp.json()
        setEnpvResult({ enpv: d.enpv, explanation: d.explanation, should_trade: d.should_trade })
      } else {
        setEnpvResult({ enpv: 0.59, explanation: '示例: 概率0.8 x 利润1.0 - 滑点0.1 - 机会0.05', should_trade: true })
      }
    } catch {
      setEnpvResult({ enpv: 0.59, explanation: '离线示例值', should_trade: true })
    }
  }

  const checkBreaker = async () => {
    if (!sessionId) return
    setError('')
    try {
      const resp = await fetch('/api/v3/financial/circuit-break', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId })
      })
      if (resp.ok) {
        const d = await resp.json()
        setBreakerResult({ state: d.state, reason: d.reason, triggered: d.triggered })
      } else {
        setBreakerResult({ state: 'NORMAL', reason: '无触发', triggered: false })
      }
    } catch {
      setBreakerResult({ state: 'NORMAL', reason: '离线示例', triggered: false })
    }
  }

  useEffect(() => { if (sessionId) fetchStatus() }, [sessionId])

  return (
    <div className="h-full overflow-y-auto p-6 bg-chatBg text-textPrimary">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-sky-500/20 flex items-center justify-center">
          <IconFinancial size={22} className="text-sky-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">金融市场</h1>
          <p className="text-xs text-textSecondary">LOB 限价订单簿 / 做市商 / 滑点 / ENPV / 熔断</p>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-rose-500/10 border border-rose-500/30 rounded-lg text-xs text-rose-400">
          {error}
        </div>
      )}

      {/* Session Control */}
      <div className="bg-sidebar rounded-xl p-4 border border-white/5 mb-6 flex items-center gap-4 flex-wrap">
        <button onClick={createSession} disabled={loading}
          className="px-4 py-2 bg-accent hover:bg-accent/80 rounded-lg text-sm font-medium transition-colors disabled:opacity-50">
          {loading ? '创建中...' : sessionId ? `会话: ${sessionId.slice(0, 8)}...` : '创建 LOB 会话'}
        </button>
        {sessionId && (
          <button onClick={fetchStatus}
            className="px-4 py-2 bg-white/10 hover:bg-white/20 rounded-lg text-sm font-medium transition-colors">
            刷新状态
          </button>
        )}
      </div>

      {lobStatus ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* LOB Status */}
          <div className="bg-sidebar rounded-xl p-4 border border-white/5">
            <h2 className="text-sm font-semibold mb-3">订单簿状态</h2>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-textSecondary">最佳买价</span>
                <span className="text-emerald-400">{lobStatus.best_bid ?? '—'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-textSecondary">最佳卖价</span>
                <span className="text-rose-400">{lobStatus.best_ask ?? '—'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-textSecondary">中间价</span>
                <span className="text-accent">{lobStatus.mid_price?.toFixed(4) ?? '—'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-textSecondary">价差 (bps)</span>
                <span>{lobStatus.spread_bps?.toFixed(2) ?? '—'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-textSecondary">深度熵</span>
                <span>{lobStatus.depth_entropy?.toFixed(4) ?? '—'}</span>
              </div>
            </div>

            {/* Add Order */}
            <div className="mt-4 flex gap-2">
              <input type="number" step="0.01" value={price} onChange={e => setPrice(e.target.value)}
                placeholder="价格" className="flex-1 bg-white/5 border border-white/10 rounded px-2 py-1 text-xs" />
              <input type="number" step="0.1" value={size} onChange={e => setSize(e.target.value)}
                placeholder="数量" className="flex-1 bg-white/5 border border-white/10 rounded px-2 py-1 text-xs" />
            </div>
            <div className="flex gap-2 mt-2">
              <button onClick={() => addOrder('bid')} className="flex-1 py-1.5 bg-emerald-500/80 hover:bg-emerald-500 rounded text-xs font-medium transition-colors">买入</button>
              <button onClick={() => addOrder('ask')} className="flex-1 py-1.5 bg-rose-500/80 hover:bg-rose-500 rounded text-xs font-medium transition-colors">卖出</button>
            </div>
          </div>

          {/* ENPV + Circuit Breaker */}
          <div className="space-y-4">
            <div className="bg-sidebar rounded-xl p-4 border border-white/5">
              <h2 className="text-sm font-semibold mb-3">ENPV 决策</h2>
              <button onClick={calcEnpv}
                className="w-full px-4 py-2 bg-sky-500/80 hover:bg-sky-500 rounded-lg text-sm font-medium transition-colors">
                计算 ENPV (示例参数)
              </button>
              {enpvResult && (
                <div className="mt-3 p-3 rounded-lg bg-white/5 border border-white/10 text-xs space-y-1">
                  <div className="flex justify-between">
                    <span className="text-textSecondary">ENPV 值</span>
                    <span className={`font-bold ${enpvResult.should_trade ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {enpvResult.enpv?.toFixed(4)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-textSecondary">决策</span>
                    <span className={enpvResult.should_trade ? 'text-emerald-400' : 'text-rose-400'}>
                      {enpvResult.should_trade ? '✓ 应交易' : '✗ 不交易'}
                    </span>
                  </div>
                  <div className="text-textSecondary pt-1 border-t border-white/5">{enpvResult.explanation}</div>
                </div>
              )}
            </div>
            <div className="bg-sidebar rounded-xl p-4 border border-white/5">
              <h2 className="text-sm font-semibold mb-3">熔断检测</h2>
              <button onClick={checkBreaker} disabled={!sessionId}
                className="w-full px-4 py-2 bg-amber-500/80 hover:bg-amber-500 rounded-lg text-sm font-medium transition-colors disabled:opacity-30">
                检测熔断状态
              </button>
              {breakerResult && (
                <div className={`mt-3 p-3 rounded-lg text-xs border ${breakerResult.triggered ? 'bg-rose-500/10 border-rose-500/30' : 'bg-emerald-500/10 border-emerald-500/30'}`}>
                  <div className="flex justify-between mb-1">
                    <span className="text-textSecondary">状态</span>
                    <span className={breakerResult.triggered ? 'text-rose-400 font-bold' : 'text-emerald-400 font-bold'}>
                      {breakerResult.state}
                    </span>
                  </div>
                  <div className="text-textSecondary">{breakerResult.reason}</div>
                </div>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="text-center py-16 text-textSecondary">
          <IconFinancial size={48} className="mx-auto mb-4 opacity-30" />
          <p className="text-sm">创建 LOB 会话开始模拟</p>
          <p className="text-xs mt-1 opacity-60">限价订单簿 / 做市商 / 滑点 / ENPV 决策 / 熔断检测</p>
        </div>
      )}
    </div>
  )
}
