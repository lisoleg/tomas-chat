import { useState, useEffect } from 'react'
import { IconGat } from './icons'

interface TheoryInfo {
  name: string
  sorts: number
  operations: number
  axioms: number
}
interface FreeModel {
  theory_name: string
  sorts: Record<string, string>
  operations: string[]
  axioms: string[]
}

export function GATPanel() {
  const [theories, setTheories] = useState<TheoryInfo[]>([])
  const [selected, setSelected] = useState('')
  const [freeModel, setFreeModel] = useState<FreeModel | null>(null)
  const [loading, setLoading] = useState(false)

  const fetchTheories = async () => {
    try {
      const resp = await fetch('/api/v3/gat/theories')
      if (resp.ok) {
        setTheories(await resp.json())
      } else {
        setTheories([
          { name: 'ARC_DSL_GAT', sorts: 5, operations: 10, axioms: 3 },
          { name: 'Octonion_GAT', sorts: 3, operations: 11, axioms: 15 },
        ])
      }
    } catch {
      setTheories([
        { name: 'ARC_DSL_GAT', sorts: 5, operations: 10, axioms: 3 },
        { name: 'Octonion_GAT', sorts: 3, operations: 11, axioms: 15 },
      ])
    }
  }

  useEffect(() => { fetchTheories() }, [])

  const handleFreeModel = async () => {
    if (!selected) return
    setLoading(true)
    try {
      const resp = await fetch('/api/v3/gat/theory/free-model', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theory_name: selected })
      })
      if (resp.ok) {
        const data = await resp.json()
        setFreeModel(data.free_model || data)
      }
    } catch { /* ignore */ }
    setLoading(false)
  }

  return (
    <div className="h-full overflow-y-auto p-6 bg-chatBg text-textPrimary">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-violet-500/20 flex items-center justify-center">
          <IconGat size={22} className="text-violet-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">GAT 公理</h1>
          <p className="text-xs text-textSecondary">广义代数理论 — DSL 原语形式化</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: Theory List + Free Model */}
        <div className="bg-sidebar rounded-xl p-4 border border-white/5">
          <h2 className="text-sm font-semibold mb-3">预定义理论</h2>
          <div className="space-y-2 mb-4">
            {theories.map(t => (
              <div key={t.name}
                onClick={() => setSelected(t.name)}
                className={`px-3 py-2 rounded-lg cursor-pointer border transition-colors ${selected === t.name ? 'bg-accent/20 border-accent/50' : 'bg-white/5 border-white/10 hover:bg-white/10'}`}>
                <div className="font-medium text-sm">{t.name}</div>
                <div className="text-xs text-textSecondary mt-1">
                  Sorts: {t.sorts} | Ops: {t.operations} | Axioms: {t.axioms}
                </div>
              </div>
            ))}
          </div>
          <button onClick={handleFreeModel} disabled={!selected || loading}
            className="w-full px-4 py-2 bg-accent hover:bg-accent/80 rounded-lg text-sm font-medium transition-colors disabled:opacity-30">
            {loading ? '构造中...' : '构造自由模型'}
          </button>

          {freeModel && (
            <div className="mt-4 space-y-2 text-xs">
              <div className="font-semibold text-emerald-400">自由模型: {freeModel.theory_name}</div>
              {freeModel.sorts && (
                <div>
                  <span className="text-textSecondary">Sorts: </span>
                  {Object.keys(freeModel.sorts).join(', ')}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right: Theory Map + Info */}
        <div className="bg-sidebar rounded-xl p-4 border border-white/5">
          <h2 className="text-sm font-semibold mb-3">理论态射 (Theory Map)</h2>
          <p className="text-xs text-textSecondary mb-4">
            GAT 理论之间的态射：ARC DSL ↔ 八元数代数
          </p>
          <div className="flex items-center gap-3 mb-4">
            <div className="flex-1 bg-white/5 rounded-lg p-3 text-center text-xs">
              <div className="text-accent font-medium">ARC_DSL_GAT</div>
              <div className="text-textSecondary mt-1">DSL 操作</div>
            </div>
            <div className="text-lg">↔</div>
            <div className="flex-1 bg-white/5 rounded-lg p-3 text-center text-xs">
              <div className="text-violet-400 font-medium">Octonion_GAT</div>
              <div className="text-textSecondary mt-1">八元数</div>
            </div>
          </div>
          <button onClick={async () => {
            try {
              const resp = await fetch('/api/v3/gat/theory/map', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source: 'ArcDSL_GAT', target: 'OctonionGAT', mapping: {} })
              })
            } catch { /* ignore */ }
          }}
            className="w-full px-4 py-2 bg-violet-500/80 hover:bg-violet-500 rounded-lg text-sm font-medium transition-colors">
            计算态射
          </button>
        </div>
      </div>
    </div>
  )
}
