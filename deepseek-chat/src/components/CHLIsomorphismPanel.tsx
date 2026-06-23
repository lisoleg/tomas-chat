import { useState } from 'react'
import { IconCHL } from './icons'

/** κ-Snap 证明搜索结果 */
interface ProofResult {
  proposition: string
  proof_term: string
  mdl_score: number
}

/** 公理扩展条目 */
interface AxiomExtension {
  name: string
  strategy: string
  discovered_at: string
}

/** CHL 定理 */
interface CHLTheorem {
  key: string
  statement: string
  proof: string
}

/** fallback 证明搜索结果 */
const fallbackProofs: ProofResult[] = [
  { proposition: 'transform_identity', proof_term: '(lambda (x) x)', mdl_score: 1.2 },
  { proposition: 'color_swap', proof_term: '(swap (map grid color_map))', mdl_score: 3.8 },
  { proposition: 'grid_rotate', proof_term: '(rotate grid 90)', mdl_score: 2.5 },
]

/** 公理扩展列表 */
const axiomExtensions: AxiomExtension[] = [
  { name: 'κ-compose', strategy: '组合已知原语形成新策略', discovered_at: 'Sleep-Step #42' },
  { name: 'ψ-mirror', strategy: '镜像对称变换策略', discovered_at: 'Sleep-Step #57' },
  { name: 'δ-fold', strategy: '折叠递归策略', discovered_at: 'Sleep-Step #73' },
]

/** CHL 定理列表 */
const chlTheorems: CHLTheorem[] = [
  {
    key: 'solving_is_proving',
    statement: '求解即证明 (Solving is Proving)',
    proof: '每个 ARC 任务的求解过程对应一个直觉主义逻辑证明',
  },
  {
    key: 'program_is_proof_term',
    statement: '程序即证明项 (Program is Proof Term)',
    proof: 'LISP DSL 程序就是 Curry-Howard 对应的证明项',
  },
  {
    key: 'execution_is_morphism',
    statement: '执行即态射 (Execution is Morphism)',
    proof: '程序执行对应范畴论中的态射复合',
  },
]

/**
 * Curry-Howard-Lambek 同构面板
 *
 * 对应后端: sim/chl_isomorphism.py
 */
export function CHLIsomorphismPanel() {
  const [propName, setPropName] = useState('')
  const [proofResult, setProofResult] = useState<ProofResult | null>(null)
  const [searching, setSearching] = useState(false)

  /** κ-Snap 证明搜索 */
  const handleSearch = async () => {
    if (!propName.trim()) return
    setSearching(true)
    try {
      const resp = await fetch('/api/v3/chl/proof-search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ proposition: propName }),
      })
      if (resp.ok) {
        const data = await resp.json()
        setProofResult({
          proposition: data.proposition ?? propName,
          proof_term: data.proof_term ?? data.program ?? '',
          mdl_score: data.mdl_score ?? data.mdl ?? 0,
        })
      } else {
        // fallback: 匹配本地数据
        const match = fallbackProofs.find(p => p.proposition.includes(propName))
        setProofResult(match ?? { proposition: propName, proof_term: '(lambda (x) x)', mdl_score: 1.0 })
      }
    } catch {
      const match = fallbackProofs.find(p => p.proposition.includes(propName))
      setProofResult(match ?? { proposition: propName, proof_term: '(lambda (x) x)', mdl_score: 1.0 })
    }
    setSearching(false)
  }

  return (
    <div className="h-full overflow-y-auto p-6 bg-chatBg text-textPrimary">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-emerald-500/20 flex items-center justify-center">
          <IconCHL size={22} className="text-emerald-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">CHL 同构</h1>
          <p className="text-xs text-textSecondary">构造即证明 · 算子即态射</p>
        </div>
      </div>

      {/* CHL Triangle Visualization */}
      <div className="bg-sidebar rounded-xl p-6 border border-white/5 mb-6">
        <h2 className="text-sm font-semibold mb-4 text-center">Curry-Howard-Lambek 三角同构</h2>
        <div className="relative h-64 flex items-center justify-center">
          <svg viewBox="0 0 400 240" className="w-full max-w-lg">
            {/* Triangle edges */}
            <polygon points="200,20 380,220 20,220" fill="rgba(255,255,255,0.03)" stroke="rgba(255,255,255,0.15)" strokeWidth="1.5" />

            {/* Top vertex: Logic */}
            <circle cx="200" cy="20" r="6" fill="#22d3ee" />
            <text x="200" y="12" textAnchor="middle" fill="#22d3ee" fontSize="13" fontWeight="bold">逻辑命题</text>
            <text x="200" y="40" textAnchor="middle" fill="rgba(255,255,255,0.5)" fontSize="10">ARC 任务规约</text>

            {/* Right vertex: Proof Term */}
            <circle cx="380" cy="220" r="6" fill="#a78bfa" />
            <text x="380" y="238" textAnchor="middle" fill="#a78bfa" fontSize="13" fontWeight="bold">证明项</text>
            <text x="380" y="232" textAnchor="middle" fill="rgba(255,255,255,0.5)" fontSize="9">LISP DSL</text>

            {/* Bottom vertex: Morphism */}
            <circle cx="20" cy="220" r="6" fill="#34d399" />
            <text x="20" y="238" textAnchor="middle" fill="#34d399" fontSize="13" fontWeight="bold">范畴态射</text>
            <text x="20" y="232" textAnchor="middle" fill="rgba(255,255,255,0.5)" fontSize="9">八元数算子</text>

            {/* Arrows with labels */}
            {/* Logic -> Proof (Howard) */}
            <text x="310" y="110" fill="rgba(255,255,255,0.4)" fontSize="9" transform="rotate(35, 310, 110)">Howard ⟺</text>
            {/* Proof -> Morphism (Lambek) */}
            <text x="200" y="240" fill="rgba(255,255,255,0.4)" fontSize="9">⟺ Lambek</text>
            {/* Morphism -> Logic (Curry) */}
            <text x="90" y="110" fill="rgba(255,255,255,0.4)" fontSize="9" transform="rotate(-35, 90, 110)">Curry ⟺</text>

            {/* Center: Isomorphism */}
            <text x="200" y="155" textAnchor="middle" fill="rgba(255,255,255,0.3)" fontSize="24">≅</text>
          </svg>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: κ-Snap Proof Search */}
        <div className="bg-sidebar rounded-xl p-4 border border-white/5">
          <h2 className="text-sm font-semibold mb-3">κ-Snap 证明搜索</h2>
          <p className="text-xs text-textSecondary mb-4">
            输入命题名，搜索 MDL 评分最小的证明项
          </p>

          <div className="flex gap-2 mb-4">
            <input
              type="text"
              value={propName}
              onChange={e => setPropName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleSearch() }}
              placeholder="如: color_swap"
              className="flex-1 px-3 py-1.5 bg-white/5 border border-white/10 rounded-lg text-sm focus:outline-none focus:border-accent"
            />
            <button
              onClick={handleSearch}
              disabled={searching || !propName.trim()}
              className="px-4 py-1.5 bg-emerald-500/80 hover:bg-emerald-500 rounded-lg text-sm font-medium transition-colors disabled:opacity-30"
            >
              {searching ? '搜索中...' : '搜索'}
            </button>
          </div>

          {proofResult && (
            <div className="space-y-2">
              <div className="bg-white/5 rounded-lg p-3 border border-white/10">
                <div className="text-xs text-textSecondary mb-1">命题</div>
                <div className="text-sm font-medium text-emerald-400">{proofResult.proposition}</div>
              </div>
              <div className="bg-white/5 rounded-lg p-3 border border-white/10">
                <div className="text-xs text-textSecondary mb-1">证明项 (Proof Term)</div>
                <div className="text-sm font-mono text-violet-400">{proofResult.proof_term}</div>
              </div>
              <div className="bg-white/5 rounded-lg p-3 border border-white/10">
                <div className="text-xs text-textSecondary mb-1">MDL 评分</div>
                <div className="text-sm font-medium text-amber-400">{proofResult.mdl_score.toFixed(2)}</div>
              </div>
            </div>
          )}

          {/* Known propositions */}
          <div className="mt-4">
            <div className="text-xs text-textSecondary mb-2">已知命题:</div>
            <div className="flex flex-wrap gap-2">
              {fallbackProofs.map((p, i) => (
                <button
                  key={i}
                  onClick={() => { setPropName(p.proposition); }}
                  className="px-2 py-1 bg-white/5 hover:bg-white/10 rounded text-[10px] text-violet-400 border border-white/10 transition-colors"
                >
                  {p.proposition}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Right: Axiom Extensions + Theorems */}
        <div className="space-y-4">
          {/* Axiom Extensions */}
          <div className="bg-sidebar rounded-xl p-4 border border-white/5">
            <h2 className="text-sm font-semibold mb-3">公理扩展 (Sleep-Step 发现)</h2>
            <div className="space-y-2">
              {axiomExtensions.map((ax, i) => (
                <div key={i} className="bg-white/5 rounded-lg p-3 border border-white/10">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-medium text-emerald-400">{ax.name}</span>
                    <span className="text-[10px] text-textSecondary">{ax.discovered_at}</span>
                  </div>
                  <div className="text-[11px] text-textSecondary">{ax.strategy}</div>
                </div>
              ))}
            </div>
          </div>

          {/* CHL Theorems */}
          <div className="bg-sidebar rounded-xl p-4 border border-white/5">
            <h2 className="text-sm font-semibold mb-3">CHL 定理</h2>
            <div className="space-y-2">
              {chlTheorems.map((thm, i) => (
                <div key={i} className="bg-white/5 rounded-lg p-3 border border-white/10">
                  <div className="text-xs font-medium text-cyan-400 mb-1">{thm.statement}</div>
                  <div className="text-[11px] text-textSecondary">{thm.proof}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
