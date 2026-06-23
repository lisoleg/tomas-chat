import { useState, useEffect } from 'react'
import { IconTaiyi } from './icons'

/** 博弈对话记录 */
interface DuelEntry {
  strategy: string
  counter: string
  result: 'wall' | 'trap' | 'death' | 'success'
}

/** L3 差分感知状态 */
interface L3State {
  detectedRow: number
  detectedCol: number
  confidence: number
}

/** L2 DFS 回溯状态 */
interface L2State {
  searchDepth: number
  backtrackCount: number
  pathLength: number
}

/** L4 贝叶斯熔断状态 */
interface L4State {
  efficiency: number
  status: 'EXECUTE' | 'ABORT'
}

/** fallback 对话历史 */
const fallbackDuelHistory: DuelEntry[] = [
  { strategy: 'move_right', counter: 'wall', result: 'wall' },
  { strategy: 'move_up', counter: 'open_path', result: 'success' },
  { strategy: 'move_left', counter: 'trap', result: 'trap' },
  { strategy: 'move_down', counter: 'death_pit', result: 'death' },
  { strategy: 'move_right_2', counter: 'open_path', result: 'success' },
]

/** 反驳类型颜色映射 */
const resultColors: Record<DuelEntry['result'], string> = {
  wall: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  trap: 'bg-violet-500/20 text-violet-400 border-violet-500/30',
  death: 'bg-rose-500/20 text-rose-400 border-rose-500/30',
  success: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
}

const resultLabels: Record<DuelEntry['result'], string> = {
  wall: '墙壁 (Wall)',
  trap: '陷阱 (Trap)',
  death: '死亡 (Death)',
  success: '成功 (Success)',
}

/** RHAE 评分 */
const rhaeScore = 72

/**
 * 太一互搏 Agent 面板 — Physical AI、L3差分、L2回溯、L4熔断
 *
 * 对应后端: sim/taiyi_mutual_duel.py
 */
export function TaiyiDuelPanel() {
  const [duelHistory, setDuelHistory] = useState<DuelEntry[]>(fallbackDuelHistory)
  const [l3, setL3] = useState<L3State>({ detectedRow: 3, detectedCol: 5, confidence: 0.87 })
  const [l2, setL2] = useState<L2State>({ searchDepth: 7, backtrackCount: 12, pathLength: 15 })
  const [l4, setL4] = useState<L4State>({ efficiency: 0.72, status: 'EXECUTE' })

  /** 从 API 获取状态 */
  useEffect(() => {
    const fetchDuel = async () => {
      try {
        const resp = await fetch('/api/v3/taiyi-duel/status')
        if (resp.ok) {
          const data = await resp.json()
          if (data.history) setDuelHistory(data.history)
          if (data.l3) setL3(data.l3)
          if (data.l2) setL2(data.l2)
          if (data.l4) setL4(data.l4)
        }
      } catch {
        // 使用 fallback 数据
      }
    }
    fetchDuel()
  }, [])

  /** 证实者策略列表 */
  const verifierStrategies = duelHistory.map(h => h.strategy)
  /** 证伪者反驳列表 */
  const falsifierCounters = duelHistory.map(h => h.counter)

  return (
    <div className="h-full overflow-y-auto p-6 bg-chatBg text-textPrimary">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-rose-500/20 flex items-center justify-center">
          <IconTaiyi size={22} className="text-rose-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">太一互搏 Agent</h1>
          <p className="text-xs text-textSecondary">Physical AI · L3差分 · L2回溯 · L4熔断</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: 博弈语义引擎 */}
        <div className="bg-sidebar rounded-xl p-4 border border-white/5">
          <h2 className="text-sm font-semibold mb-3">博弈语义引擎</h2>
          <p className="text-xs text-textSecondary mb-4">
            证实者 (Player) vs 证伪者 (Environment)
          </p>

          {/* Strategy lists */}
          <div className="grid grid-cols-2 gap-3 mb-4">
            <div className="bg-white/5 rounded-lg p-3 border border-white/10">
              <div className="text-xs font-medium text-emerald-400 mb-2">证实者策略</div>
              <div className="space-y-1">
                {verifierStrategies.map((s, i) => (
                  <div key={i} className="text-[11px] text-textSecondary">→ {s}</div>
                ))}
              </div>
            </div>
            <div className="bg-white/5 rounded-lg p-3 border border-white/10">
              <div className="text-xs font-medium text-rose-400 mb-2">证伪者反驳</div>
              <div className="space-y-1">
                {falsifierCounters.map((c, i) => (
                  <div key={i} className="text-[11px] text-textSecondary">→ {c}</div>
                ))}
              </div>
            </div>
          </div>

          {/* Duel history timeline */}
          <div className="text-xs text-textSecondary mb-2">博弈对话历史:</div>
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {duelHistory.map((entry, i) => (
              <div key={i} className="flex items-center gap-2">
                <div className="w-6 h-6 rounded-full bg-white/5 flex items-center justify-center text-[10px] text-textSecondary flex-shrink-0">
                  {i + 1}
                </div>
                <div className="flex-1 flex items-center gap-2 px-3 py-1.5 bg-white/5 rounded-lg">
                  <span className="text-[11px] text-emerald-400">{entry.strategy}</span>
                  <span className="text-textSecondary text-[10px]">→</span>
                  <span className={`text-[10px] px-2 py-0.5 rounded border ${resultColors[entry.result]}`}>
                    {resultLabels[entry.result]}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right: L3/L2/L4 Status */}
        <div className="space-y-4">
          {/* L3 Differential Perception */}
          <div className="bg-sidebar rounded-xl p-4 border border-white/5">
            <h2 className="text-sm font-semibold mb-3">L3 差分感知</h2>
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-white/5 rounded-lg p-3 border border-white/10 text-center">
                <div className="text-[10px] text-textSecondary mb-1">Row</div>
                <div className="text-lg font-bold text-cyan-400">{l3.detectedRow}</div>
              </div>
              <div className="bg-white/5 rounded-lg p-3 border border-white/10 text-center">
                <div className="text-[10px] text-textSecondary mb-1">Col</div>
                <div className="text-lg font-bold text-cyan-400">{l3.detectedCol}</div>
              </div>
              <div className="bg-white/5 rounded-lg p-3 border border-white/10 text-center">
                <div className="text-[10px] text-textSecondary mb-1">置信度</div>
                <div className="text-lg font-bold text-emerald-400">{(l3.confidence * 100).toFixed(0)}%</div>
              </div>
            </div>
          </div>

          {/* L2 DFS Backtrack */}
          <div className="bg-sidebar rounded-xl p-4 border border-white/5">
            <h2 className="text-sm font-semibold mb-3">L2 DFS 回溯</h2>
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-white/5 rounded-lg p-3 border border-white/10 text-center">
                <div className="text-[10px] text-textSecondary mb-1">搜索深度</div>
                <div className="text-lg font-bold text-violet-400">{l2.searchDepth}</div>
              </div>
              <div className="bg-white/5 rounded-lg p-3 border border-white/10 text-center">
                <div className="text-[10px] text-textSecondary mb-1">回溯次数</div>
                <div className="text-lg font-bold text-amber-400">{l2.backtrackCount}</div>
              </div>
              <div className="bg-white/5 rounded-lg p-3 border border-white/10 text-center">
                <div className="text-[10px] text-textSecondary mb-1">路径长度</div>
                <div className="text-lg font-bold text-cyan-400">{l2.pathLength}</div>
              </div>
            </div>
          </div>

          {/* L4 Bayesian Fuse */}
          <div className="bg-sidebar rounded-xl p-4 border border-white/5">
            <h2 className="text-sm font-semibold mb-3">L4 贝叶斯熔断</h2>
            <div className="flex items-center gap-4">
              <div className="flex-1">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-textSecondary">效率 (efficiency)</span>
                  <span className="text-xs font-medium text-cyan-400">{l4.efficiency.toFixed(2)}</span>
                </div>
                <div className="h-3 bg-white/5 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${l4.efficiency > 0.5 ? 'bg-emerald-500' : 'bg-rose-500'}`}
                    style={{ width: `${l4.efficiency * 100}%` }}
                  />
                </div>
              </div>
              <div className={`px-4 py-2 rounded-lg border font-bold text-sm ${
                l4.status === 'EXECUTE'
                  ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                  : 'bg-rose-500/20 text-rose-400 border-rose-500/30'
              }`}>
                {l4.status}
              </div>
            </div>
            <p className="text-[10px] text-textSecondary mt-2">
              efficiency &gt; 0.5 → EXECUTE · efficiency ≤ 0.5 → ABORT
            </p>
          </div>

          {/* RHAE Score */}
          <div className="bg-sidebar rounded-xl p-4 border border-white/5">
            <h2 className="text-sm font-semibold mb-3">RHAE 评分</h2>
            <div className="flex items-center gap-3">
              <div className="flex-1 h-3 bg-white/5 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-rose-500 via-amber-500 to-emerald-500 rounded-full transition-all"
                  style={{ width: `${rhaeScore}%` }}
                />
              </div>
              <span className="text-lg font-bold text-amber-400">{rhaeScore}</span>
            </div>
            <p className="text-[10px] text-textSecondary mt-2">0-100 · 综合推理健康度评估</p>
          </div>

          {/* Physical AI Theorem */}
          <div className="bg-sidebar rounded-xl p-4 border border-white/5">
            <h2 className="text-sm font-semibold mb-2">Physical AI 定理</h2>
            <div className="text-center bg-white/5 rounded-lg p-4 border border-white/10">
              <div className="text-base font-bold text-rose-400">内思即外作</div>
              <div className="text-[10px] text-textSecondary mt-2">
                内部推理 (L3差分→L2回溯→L4熔断) ↔ 外部物理行动 — 同构映射
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
