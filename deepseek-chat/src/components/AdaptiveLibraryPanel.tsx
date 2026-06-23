import { useState, useEffect } from 'react'
import { IconAdaptiveLib } from './icons'

/** 最近注册的原语 */
interface PrimitiveEntry {
  name: string
  gain: number
  mdl: number
}

/** 历史增益记录 */
interface GainRecord {
  step: number
  gain: number
}

/** fallback 原语列表 */
const fallbackPrimitives: PrimitiveEntry[] = [
  { name: 'map_grid', gain: 0.82, mdl: 3.5 },
  { name: 'rotate_obj', gain: 0.65, mdl: 4.2 },
  { name: 'color_match', gain: 0.71, mdl: 3.8 },
  { name: 'symmetry_check', gain: 0.55, mdl: 5.1 },
  { name: 'flood_fill', gain: 0.88, mdl: 2.9 },
]

/** LLM Rice 定理上界 */
const LLM_RICE_CEILING = 0.35
/** TOMAS 理论上限 */
const TOMAS_THEORETICAL_CEILING = 1.0

/**
 * 自适应库学习面板 — α/β在线学习、Sleep-Step、Rice定理上界
 *
 * 对应后端: sim/adaptive_library.py
 */
export function AdaptiveLibraryPanel() {
  const [alpha, setAlpha] = useState(1.0)
  const [beta, setBeta] = useState(1.0)
  const [mdlCost, setMdlCost] = useState(3.5)
  const [freq, setFreq] = useState(10)
  const [closureSize, setClosureSize] = useState(5)
  const [primitives, setPrimitives] = useState<PrimitiveEntry[]>(fallbackPrimitives)
  const [gains, setGains] = useState<GainRecord[]>([
    { step: 1, gain: 0.3 },
    { step: 2, gain: 0.45 },
    { step: 3, gain: 0.62 },
    { step: 4, gain: 0.71 },
    { step: 5, gain: 0.82 },
  ])

  /** 计算预算 B = b_base + α*MDL + β*log2(freq+1) */
  const budget = 1.0 + alpha * mdlCost + beta * Math.log2(freq + 1)

  /** 从 API 获取库状态 */
  useEffect(() => {
    const fetchLib = async () => {
      try {
        const resp = await fetch('/api/v3/adaptive-library/status')
        if (resp.ok) {
          const data = await resp.json()
          if (data.closure_size) setClosureSize(data.closure_size)
          if (data.primitives) setPrimitives(data.primitives)
          if (data.gains) setGains(data.gains)
        }
      } catch {
        // 使用 fallback 数据
      }
    }
    fetchLib()
  }, [])

  const maxGain = Math.max(...gains.map(g => g.gain), 0.01)

  return (
    <div className="h-full overflow-y-auto p-6 bg-chatBg text-textPrimary">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-amber-500/20 flex items-center justify-center">
          <IconAdaptiveLib size={22} className="text-amber-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">自适应库学习</h1>
          <p className="text-xs text-textSecondary">α/β在线学习 · Sleep-Step · Rice定理上界</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: 参数控制面板 */}
        <div className="bg-sidebar rounded-xl p-4 border border-white/5">
          <h2 className="text-sm font-semibold mb-3">参数控制</h2>

          {/* Alpha slider */}
          <div className="mb-4">
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs text-textSecondary">α (MDL权重)</label>
              <span className="text-xs font-medium text-amber-400">{alpha.toFixed(2)}</span>
            </div>
            <input
              type="range"
              min={0.1}
              max={5.0}
              step={0.1}
              value={alpha}
              onChange={e => setAlpha(parseFloat(e.target.value))}
              className="w-full accent-amber-500"
            />
          </div>

          {/* Beta slider */}
          <div className="mb-4">
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs text-textSecondary">β (频率权重)</label>
              <span className="text-xs font-medium text-amber-400">{beta.toFixed(2)}</span>
            </div>
            <input
              type="range"
              min={0.1}
              max={5.0}
              step={0.1}
              value={beta}
              onChange={e => setBeta(parseFloat(e.target.value))}
              className="w-full accent-amber-500"
            />
          </div>

          {/* MDL + Freq inputs */}
          <div className="grid grid-cols-2 gap-3 mb-4">
            <div>
              <label className="text-xs text-textSecondary block mb-1">MDL代价</label>
              <input
                type="number"
                step={0.1}
                value={mdlCost}
                onChange={e => setMdlCost(parseFloat(e.target.value) || 0)}
                className="w-full px-2 py-1.5 bg-white/5 border border-white/10 rounded-lg text-sm text-center focus:outline-none focus:border-accent"
              />
            </div>
            <div>
              <label className="text-xs text-textSecondary block mb-1">频率</label>
              <input
                type="number"
                value={freq}
                onChange={e => setFreq(parseInt(e.target.value) || 0)}
                className="w-full px-2 py-1.5 bg-white/5 border border-white/10 rounded-lg text-sm text-center focus:outline-none focus:border-accent"
              />
            </div>
          </div>

          {/* Budget */}
          <div className="bg-white/5 rounded-lg p-3 border border-white/10 mb-4">
            <div className="text-xs text-textSecondary mb-1">计算预算 B</div>
            <div className="text-lg font-bold text-amber-400">{budget.toFixed(4)}</div>
            <div className="text-[10px] text-textSecondary mt-1">B = b_base + α·MDL + β·log₂(freq+1)</div>
          </div>

          {/* 历史增益 */}
          <div>
            <div className="text-xs text-textSecondary mb-2">历史增益</div>
            <div className="space-y-1.5">
              {gains.map((g, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="text-[10px] text-textSecondary w-8">#{g.step}</span>
                  <div className="flex-1 h-4 bg-white/5 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-amber-500 to-emerald-500 rounded-full transition-all"
                      style={{ width: `${(g.gain / maxGain) * 100}%` }}
                    />
                  </div>
                  <span className="text-[10px] text-amber-400 w-10 text-right">{g.gain.toFixed(2)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right: Sleep-Step + Rice 定理 */}
        <div className="space-y-4">
          {/* Library info */}
          <div className="bg-sidebar rounded-xl p-4 border border-white/5">
            <h2 className="text-sm font-semibold mb-3">Sleep-Step 结果</h2>
            <div className="grid grid-cols-2 gap-3 mb-4">
              <div className="bg-white/5 rounded-lg p-3 border border-white/10 text-center">
                <div className="text-xs text-textSecondary mb-1">库中原语</div>
                <div className="text-2xl font-bold text-accent">{closureSize}</div>
              </div>
              <div className="bg-white/5 rounded-lg p-3 border border-white/10 text-center">
                <div className="text-xs text-textSecondary mb-1">平均增益</div>
                <div className="text-2xl font-bold text-emerald-400">
                  {(primitives.reduce((s, p) => s + p.gain, 0) / primitives.length).toFixed(2)}
                </div>
              </div>
            </div>

            <div className="text-xs text-textSecondary mb-2">最近注册的原语:</div>
            <div className="space-y-1">
              {primitives.map((p, i) => (
                <div key={i} className="flex items-center justify-between px-3 py-1.5 bg-white/5 rounded text-xs">
                  <span className="text-amber-400">{p.name}</span>
                  <span className="text-textSecondary">MDL: {p.mdl}</span>
                  <span className="text-emerald-400">gain: {p.gain.toFixed(2)}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Rice 定理上界对比 */}
          <div className="bg-sidebar rounded-xl p-4 border border-white/5">
            <h2 className="text-sm font-semibold mb-3">Rice 定理上界</h2>
            <div className="space-y-3">
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-textSecondary">LLM 天花板</span>
                  <span className="text-xs font-medium text-rose-400">{LLM_RICE_CEILING}</span>
                </div>
                <div className="h-3 bg-white/5 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-rose-500 rounded-full"
                    style={{ width: `${LLM_RICE_CEILING * 100}%` }}
                  />
                </div>
              </div>
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-textSecondary">TOMAS 理论上限</span>
                  <span className="text-xs font-medium text-emerald-400">{TOMAS_THEORETICAL_CEILING.toFixed(2)}</span>
                </div>
                <div className="h-3 bg-white/5 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-emerald-500 to-cyan-500 rounded-full"
                    style={{ width: `${TOMAS_THEORETICAL_CEILING * 100}%` }}
                  />
                </div>
              </div>
            </div>
            <p className="text-[10px] text-textSecondary mt-3">
              Rice 定理：非平凡语义性质不可判定 → LLM 受限于归纳偏置天花板
            </p>
          </div>

          {/* 阴龙积 */}
          <div className="bg-sidebar rounded-xl p-4 border border-white/5">
            <h2 className="text-sm font-semibold mb-3">阴龙积</h2>
            <div className="text-xs text-textSecondary leading-relaxed">
              <p className="mb-2">
                <span className="text-amber-400 font-medium">八元数乘法</span>：非结合代数 —
                (a·b)·c ≠ a·(b·c)，保留高维纠缠信息
              </p>
              <p>
                <span className="text-amber-400 font-medium">虚部投影</span>：将 8 维八元数向量投影到 3 维虚部，
                恢复标准叉积/外积结构
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
