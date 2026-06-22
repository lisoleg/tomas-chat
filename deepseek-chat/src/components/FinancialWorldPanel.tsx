import { useState, useEffect } from 'react'
import { IconFinancial } from './icons'

export function FinancialWorldPanel() {
  const [sessionId, setSessionId] = useState('')
  const [lobStatus, setLobStatus] = useState<any>(null)
  const [price, setPrice] = useState('')
  const [size, setSize] = useState('')
  const [loading, setLoading] = useState(false)

  const createSession = async () => {
    setLoading(true)
    try {
      const resp = await fetch('/api/v3/financial/lob/create', { method: 'POST' })
      if (resp.ok) {
        const data = await resp.json()
        setSessionId(data.session_id)
      }
    } catch { /* ignore */ }
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
    try {
      await fetch('/api/v3/financial/lob/add-order', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, side, price: parseFloat(price), size: parseFloat(size) || 1 })
      })
      fetchStatus()
    } catch { /* ignore */ }
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
          <p className="text-xs text-textSecondary">LOB 限价订单簿 / 做市商 / 滑点 / ENPV</p>
        </div>
      </div>

      {/* Session Control */}
      <div className="bg-sidebar rounded-xl p-4 border border-white/5 mb-6 flex items-center gap-4 flex-wrap">
        <button onClick={createSession} disabled={loading}
          className="px-4 py-2 bg-accent hover:bg-accent/80 rounded-lg text-sm font-medium">
          {sessionId ? `会话: ${sessionId}` : '创建 LOB 会话'}
        </button>
        {sessionId && (
          <button onClick={fetchStatus}
            className="px-4 py-2 bg-white/10 hover:bg-white/20 rounded-lg text-sm font-medium">
            刷新状态
          </button>
        )}
      </div>

      {lobStatus && (
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
                <span className="text-accent">{lobStatus.mid_price?.toFixed(4)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-textSecondary">价差 (bps)</span>
                <span>{lobStatus.spread_bps?.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-textSecondary">深度熵</span>
                <span>{lobStatus.depth_entropy?.toFixed(4)}</span>
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
              <button onClick={() => addOrder('bid')} className="flex-1 py-1 bg-emerald-500/80 hover:bg-emerald-500 rounded text-xs">买单</button>
              <button onClick={() => addOrder('ask')} className="flex-1 py-1 bg-rose-500/80 hover:bg-rose-500 rounded text-xs">卖单</button>
            </div>
          </div>

          {/* ENPV + Circuit Breaker */}
          <div className="space-y-4">
            <div className="bg-sidebar rounded-xl p-4 border border-white/5">
              <h2 className="text-sm font-semibold mb-3">ENPV 决策</h2>
              <button onClick={async () => {
                try {
                  const resp = await fetch('/api/v3/financial/enpv', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prob_fill: 0.8, expected_profit: 1.0, slippage_cost: 0.1, opportunity_cost: 0.05 })
                  })
                  if (resp.ok) { const d = await resp.json(); alert(`ENPV: ${d.enpv?.toFixed(4)} — ${d.explanation}`) }
                } catch { /* ignore */ }
              }}
                className="w-full px-4 py-2 bg-sky-500/80 hover:bg-sky-500 rounded-lg text-sm font-medium">
                计算 ENPV (示例)
              </button>
            </div>
            <div className="bg-sidebar rounded-xl p-4 border border-white/5">
              <h2 className="text-sm font-semibold mb-3">熔断检测</h2>
              <button onClick={async () => {
                if (!sessionId) return
                try {
                  const resp = await fetch('/api/v3/financial/circuit-break', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ session_id: sessionId })
                  })
                  if (resp.ok) { const d = await resp.json(); alert(`状态: ${d.state}\n${d.reason}`) }
                } catch { /* ignore */ }
              }}
                className="w-full px-4 py-2 bg-amber-500/80 hover:bg-amber-500 rounded-lg text-sm font-medium">
                检测熔断
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
