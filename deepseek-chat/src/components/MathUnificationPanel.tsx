import { useState, useMemo } from 'react'
import { IconMathUnify } from './icons'

/** 太一几何全景定位表条目 */
interface GeometryBranch {
  branch: string
  role: string
  meaning: string
}

/** fallback 表数据 — 对应 MathUnificationTable.get_table() */
const geometryTable: GeometryBranch[] = [
  { branch: '八元数/Clifford代数', role: 'L1本体(未显化)', meaning: '全连态、非结合纠缠' },
  { branch: '代数几何(AG)', role: 'L1→L2投影', meaning: 'L2因果约束=特征重要性' },
  { branch: '热带几何', role: 'L2极限退化', meaning: '叠加态的PL-rule' },
  { branch: '高维球面堆积', role: 'L5离散投影', meaning: '近似正交向量存储特征' },
  { branch: '均匀多胞形', role: 'L2干扰最小化', meaning: 'Thomson问题的解' },
  { branch: '计算共形几何', role: 'L5光滑实现', meaning: '特征流形平滑嵌入' },
  { branch: '辛几何/镜像对称', role: 'L1配对结构', meaning: '特征间互信息' },
  { branch: '度规/洛伦兹几何', role: 'L5因果锥', meaning: '因果序保持' },
]

/** UV/IR 对偶自对偶不动点 */
const SELF_DUAL_FIXED_POINT = 0.5

/**
 * 数学大统一面板 — 热带几何、共形几何、UV/IR对偶
 *
 * 对应后端: sim/math_unification_ccg.py
 */
export function MathUnificationPanel() {
  const [a, setA] = useState(3)
  const [b, setB] = useState(5)
  const [coeffs, setCoeffs] = useState('2, 0, -1')

  /** 热带加法 = max */
  const tropicalAdd = (x: number, y: number): number => Math.max(x, y)
  /** 热带乘法 = 加法 */
  const tropicalMul = (x: number, y: number): number => x + y

  /** 热带多项式分片线性函数采样点 (useMemo 避免渲染期间 setState) */
  const { points: polyPoints, error: polyError } = useMemo(() => {
    const parts = coeffs.split(',').map(s => parseFloat(s.trim()))
    if (parts.some(isNaN)) {
      return { points: [] as { x: number; y: number }[], error: '系数格式错误，请用逗号分隔数字' }
    }
    const pts: { x: number; y: number }[] = []
    for (let x = -5; x <= 5; x += 0.5) {
      let maxY = -Infinity
      parts.forEach((c, i) => {
        const val = c + i * x
        if (val > maxY) maxY = val
      })
      if (maxY !== -Infinity) pts.push({ x, y: maxY })
    }
    return { points: pts, error: '' }
  }, [coeffs])
  const maxPolyY = polyPoints.length > 0 ? Math.max(...polyPoints.map(p => p.y)) : 1
  const minPolyY = polyPoints.length > 0 ? Math.min(...polyPoints.map(p => p.y)) : 0

  return (
    <div className="h-full overflow-y-auto p-6 bg-chatBg text-textPrimary">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-cyan-500/20 flex items-center justify-center">
          <IconMathUnify size={22} className="text-cyan-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">数学大统一</h1>
          <p className="text-xs text-textSecondary">热带几何 · 共形几何 · UV/IR对偶</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: 热带半环计算器 */}
        <div className="bg-sidebar rounded-xl p-4 border border-white/5">
          <h2 className="text-sm font-semibold mb-3">热带半环计算器</h2>
          <p className="text-xs text-textSecondary mb-4">
            热带加法 ⊕ = max(a, b) · 热带乘法 ⊗ = a + b
          </p>

          {/* Inputs */}
          <div className="flex items-center gap-3 mb-4">
            <input
              type="number"
              value={a}
              onChange={e => setA(parseFloat(e.target.value) || 0)}
              className="w-20 px-2 py-1.5 bg-white/5 border border-white/10 rounded-lg text-sm text-center focus:outline-none focus:border-accent"
            />
            <span className="text-textSecondary text-sm">,</span>
            <input
              type="number"
              value={b}
              onChange={e => setB(parseFloat(e.target.value) || 0)}
              className="w-20 px-2 py-1.5 bg-white/5 border border-white/10 rounded-lg text-sm text-center focus:outline-none focus:border-accent"
            />
          </div>

          {/* Results */}
          <div className="space-y-2 mb-4">
            <div className="bg-white/5 rounded-lg p-3 border border-white/10">
              <span className="text-xs text-textSecondary">a ⊕ b = max({a}, {b}) = </span>
              <span className="text-sm font-medium text-cyan-400">{tropicalAdd(a, b)}</span>
            </div>
            <div className="bg-white/5 rounded-lg p-3 border border-white/10">
              <span className="text-xs text-textSecondary">a ⊗ b = {a} + {b} = </span>
              <span className="text-sm font-medium text-cyan-400">{tropicalMul(a, b)}</span>
            </div>
          </div>

          {/* Tropical polynomial visualization */}
          <div className="mt-4">
            <label className="text-xs text-textSecondary mb-2 block">热带多项式系数 (c₀, c₁, c₂, ...)</label>
            <input
              type="text"
              value={coeffs}
              onChange={e => setCoeffs(e.target.value)}
              className="w-full px-3 py-1.5 bg-white/5 border border-white/10 rounded-lg text-sm focus:outline-none focus:border-accent"
              placeholder="2, 0, -1"
            />
            {polyError && <div className="text-xs text-rose-400 mt-1">{polyError}</div>}
            {polyPoints.length > 0 && (
              <div className="mt-3 bg-white/5 rounded-lg p-3 border border-white/10">
                <div className="text-xs text-textSecondary mb-2">分片线性函数 max(cᵢ + i·x):</div>
                <div className="relative h-32 bg-chatBg rounded overflow-hidden">
                  <svg viewBox="0 0 200 120" className="w-full h-full">
                    {/* Axes */}
                    <line x1="0" y1="60" x2="200" y2="60" stroke="rgba(255,255,255,0.1)" strokeWidth="1" />
                    <line x1="100" y1="0" x2="100" y2="120" stroke="rgba(255,255,255,0.1)" strokeWidth="1" />
                    {/* Polyline */}
                    <polyline
                      points={polyPoints.map(p => {
                        const sx = ((p.x + 5) / 10) * 200
                        const sy = maxPolyY === minPolyY ? 60 : 100 - ((p.y - minPolyY) / (maxPolyY - minPolyY)) * 100
                        return `${sx},${sy}`
                      }).join(' ')}
                      fill="none"
                      stroke="#22d3ee"
                      strokeWidth="2"
                    />
                  </svg>
                </div>
                <div className="flex justify-between text-[10px] text-textSecondary mt-1">
                  <span>x=-5</span>
                  <span>x=0</span>
                  <span>x=5</span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right: 太一几何全景定位表 */}
        <div className="space-y-4">
          <div className="bg-sidebar rounded-xl p-4 border border-white/5">
            <h2 className="text-sm font-semibold mb-3">太一几何全景定位表</h2>
            <div className="space-y-2">
              {geometryTable.map((item, i) => (
                <div key={i} className="bg-white/5 rounded-lg p-3 border border-white/10">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-medium text-cyan-400">{item.branch}</span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-violet-500/20 text-violet-400">{item.role}</span>
                  </div>
                  <div className="text-[11px] text-textSecondary">{item.meaning}</div>
                </div>
              ))}
            </div>
          </div>

          {/* UV/IR 对偶 */}
          <div className="bg-sidebar rounded-xl p-4 border border-white/5">
            <h2 className="text-sm font-semibold mb-3">UV/IR 对偶</h2>
            <div className="bg-white/5 rounded-lg p-4 border border-white/10 text-center">
              <div className="text-xs text-textSecondary mb-2">自对偶不动点</div>
              <div className="text-2xl font-bold text-cyan-400">s = {SELF_DUAL_FIXED_POINT}</div>
              <div className="text-[10px] text-textSecondary mt-2">高频(UV) ↔ 低频(IR) 在 s=½ 处对偶</div>
            </div>
          </div>

          {/* 柏拉图收敛 */}
          <div className="bg-sidebar rounded-xl p-4 border border-white/5">
            <h2 className="text-sm font-semibold mb-3">柏拉图收敛</h2>
            <div className="text-xs text-textSecondary leading-relaxed">
              <p className="mb-2">Gromov-Wasserstein 距离衡量经验分布与柏拉图理想形态的收敛程度。</p>
              <p>随着 TOMAS L1→L5 层级提升，GW 距离单调递减 → 系统趋向柏拉图理想。</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
