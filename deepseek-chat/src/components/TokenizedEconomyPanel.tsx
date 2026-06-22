import { useState, useEffect } from 'react'
import { IconToken } from './icons'

interface Snapshot {
  total_agents: number
  total_trades: number
  executed_trades: number
  gini_coefficient: number
  economic_phase: string
  avg_balance: number
}

export function TokenizedEconomyPanel() {
  const [economyId, setEconomyId] = useState('')
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [agentId, setAgentId] = useState('')
  const [balance, setBalance] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)

  const createEconomy = async () => {
    setLoading(true)
    try {
      const resp = await fetch('/api/v3/tokenized/economy/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ initial_supply: 1000000 })
      })
      if (resp.ok) {
        const data = await resp.json()
        setEconomyId(data.economy_id)
      }
    } catch { /* ignore */ }
    setLoading(false)
  }

  const fetchSnapshot = async () => {
    if (!economyId) return
    try {
      const resp = await fetch(`/api/v3/tokenized/economy/${economyId}/snapshot`)
      if (resp.ok) setSnapshot(await resp.json())
    } catch { /* ignore */ }
  }

  const registerAgent = async () => {
    if (!economyId || !agentId) return
    try {
      await fetch('/api/v3/tokenized/agent/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ economy_id: economyId, agent_id: agentId })
      })
      fetchSnapshot()
    } catch { /* ignore */ }
  }

  const fetchBalance = async () => {
    if (!economyId || !agentId) return
    try {
      const resp = await fetch(`/api/v3/tokenized/agent/${economyId}/${agentId}/balance`)
      if (resp.ok) { const d = await resp.json(); setBalance(d.balance) }
    } catch { /* ignore */ }
  }

  useEffect(() => { if (economyId) fetchSnapshot() }, [economyId])

  const getPhaseColor = (phase: string) => {
    if (phase?.includes('EXPANSION')) return 'text-emerald-400 bg-emerald-500/20'
    if (phase?.includes('CONTRACTION')) return 'text-rose-400 bg-rose-500/20'
    if (phase?.includes('SINGULARITY')) return 'text-red-400 bg-red-500/20'
    return 'text-amber-400 bg-amber-500/20'
  }

  return (
    <div className="h-full overflow-y-auto p-6 bg-chatBg text-textPrimary">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-amber-500/20 flex items-center justify-center">
          <IconToken size={22} className="text-amber-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">代币经济</h1>
          <p className="text-xs text-textSecondary">智能体市场经济 / UBI / Gini 系数</p>
        </div>
      </div>

      {/* Economy Control */}
      <div className="bg-sidebar rounded-xl p-4 border border-white/5 mb-6 flex items-center gap-4 flex-wrap">
        <button onClick={createEconomy} disabled={loading}
          className="px-4 py-2 bg-accent hover:bg-accent/80 rounded-lg text-sm font-medium">
          {economyId ? `经济体: ${economyId}` : '创建经济体'}
        </button>
        {economyId && (
          <button onClick={fetchSnapshot}
            className="px-4 py-2 bg-white/10 hover:bg-white/20 rounded-lg text-sm font-medium">
            刷新快照
          </button>
        )}
      </div>

      {snapshot && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Snapshot Dashboard */}
          <div className="bg-sidebar rounded-xl p-4 border border-white/5">
            <h2 className="text-sm font-semibold mb-4">经济快照</h2>
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-white/5 rounded-lg p-3 text-center">
                <div className="text-lg font-bold text-accent">{snapshot.total_agents}</div>
                <div className="text-xs text-textSecondary">智能体数</div>
              </div>
              <div className="bg-white/5 rounded-lg p-3 text-center">
                <div className="text-lg font-bold text-emerald-400">{snapshot.executed_trades}</div>
                <div className="text-xs text-textSecondary">已执行交易</div>
              </div>
              <div className="bg-white/5 rounded-lg p-3 text-center">
                <div className={`text-lg font-bold ${snapshot.gini_coefficient > 0.5 ? 'text-rose-400' : 'text-emerald-400'}`}>
                  {snapshot.gini_coefficient?.toFixed(3)}
                </div>
                <div className="text-xs text-textSecondary">Gini 系数</div>
              </div>
              <div className="bg-white/5 rounded-lg p-3 text-center">
                <span className={`text-xs px-2 py-1 rounded-full font-medium ${getPhaseColor(snapshot.economic_phase)}`}>
                  {snapshot.economic_phase}
                </span>
              </div>
            </div>
          </div>

          {/* Agent Management */}
          <div className="bg-sidebar rounded-xl p-4 border border-white/5">
            <h2 className="text-sm font-semibold mb-3">智能体管理</h2>
            <div className="flex gap-2 mb-3">
              <input type="text" value={agentId} onChange={e => setAgentId(e.target.value)}
                placeholder="智能体 ID" className="flex-1 bg-white/5 border border-white/10 rounded px-2 py-1 text-xs" />
            </div>
            <div className="flex gap-2 mb-3">
              <button onClick={registerAgent} className="flex-1 py-1 bg-accent/80 hover:bg-accent rounded text-xs">注册</button>
              <button onClick={fetchBalance} className="flex-1 py-1 bg-white/10 hover:bg-white/20 rounded text-xs">查余额</button>
            </div>
            {balance !== null && (
              <div className="px-3 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-center">
                <span className="text-xs text-emerald-400">余额: {balance.toFixed(2)} UBII</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!snapshot && !loading && (
        <div className="text-center py-16 text-textSecondary">
          <IconToken size={48} className="mx-auto mb-4 opacity-30" />
          <p className="text-sm">创建经济体开始模拟</p>
          <p className="text-xs mt-1 opacity-60">UBI 全民基本收入 + 智能体交易</p>
        </div>
      )}
    </div>
  )
}
