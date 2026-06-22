import { useState, useEffect, useCallback } from 'react'
import {
  IconTarget, IconLock, IconCheck, IconSend, IconRefresh,
  IconWarning, IconClock, IconSpeed, IconBrain, IconDescription,
  IconPlus, IconPendingActions, IconShield, IconGraph
} from './icons'

// ── 类型定义 ────────────────────────────────────────

interface GoalContract {
  intent: string
  scope_in: string[]
  scope_out: string[]
  evidence_required: string[]
  pause_conditions: string[]
  acceptance: string
  goal_hash: string
  status: string
}

interface CronTask {
  schedule_id: string
  cron_expr: string
  task_name: string
  last_fire: string
}

interface SoulGrowth {
  total_segments: number
  layers: Record<string, number>
  last_compaction: string
}

interface DriftResult {
  drift_score: number
  drift_detected: boolean
  recommendation: string
}

const GATES = ['Intent 意图', 'Scope 边界', 'Evidence 证据', 'Pause 停点', 'Acceptance 验收']

// ── Mock Data ───────────────────────────────────────

function generateMockContract(): GoalContract {
  return {
    intent: '分析并优化 TOMAS 架构的性能瓶颈，提供改进方案',
    scope_in: ['性能分析', '瓶颈识别', '改进提案'],
    scope_out: ['代码重写', '架构重设计', '安全审计'],
    evidence_required: ['性能指标报告', '瓶颈定位日志', '改进对比数据'],
    pause_conditions: ['发现安全漏洞时暂停', '资源占用超限时暂停', '影响线上服务时暂停'],
    acceptance: '提交完整性能分析报告，包含至少3个可执行的优化建议，性能提升预期 ≥15%',
    goal_hash: '0x9a3f...1b2c',
    status: 'AUTHORIZED',
  }
}

function generateMockCronTasks(): CronTask[] {
  return [
    { schedule_id: 'cron_daily_soul', cron_expr: '0 2 * * *', task_name: 'Soul-Graph 日常压缩', last_fire: '2026-06-22T02:00:00' },
    { schedule_id: 'cron_weekly_audit', cron_expr: '0 4 * * 0', task_name: '周度对齐审计', last_fire: '2026-06-21T04:00:00' },
    { schedule_id: 'cron_hourly_drift', cron_expr: '0 * * * *', task_name: 'MUS 漂移检测', last_fire: '2026-06-22T09:00:00' },
  ]
}

function generateMockSoulGrowth(): SoulGrowth {
  return {
    total_segments: 156,
    layers: {
      'Layer_0_Intent': 34,
      'Layer_1_Scope': 28,
      'Layer_2_Evidence': 45,
      'Layer_3_Pause': 19,
      'Layer_4_Acceptance': 30,
    },
    last_compaction: '2026-06-22T02:00:00',
  }
}

function generateMockDrift(): DriftResult {
  return {
    drift_score: 0.12,
    drift_detected: false,
    recommendation: '当前漂移度在安全范围内，无需干预。建议保持当前频率的定期检测。',
  }
}

// ── 辅助组件 ────────────────────────────────────────

function ProgressBar({ value, color }: { value: number; color: string }) {
  return (
    <div className="w-full h-1.5 bg-white/10 rounded-full overflow-hidden">
      <div className="h-full rounded-full transition-all duration-500" style={{ width: `${Math.min(100, value * 100)}%`, backgroundColor: color }} />
    </div>
  )
}

function GateStatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    PENDING: { label: '⏳ 待处理', cls: 'bg-white/10 text-white/50' },
    AUTHORIZED: { label: '✓ 已授权', cls: 'bg-emerald-500/20 text-emerald-300' },
    EXECUTING: { label: '▶ 执行中', cls: 'bg-blue-500/20 text-blue-300' },
    COMPLETED: { label: '✓ 已完成', cls: 'bg-emerald-500/20 text-emerald-300' },
    REJECTED: { label: '✗ 已拒绝', cls: 'bg-red-500/20 text-red-300' },
    PAUSED: { label: '⏸ 暂停', cls: 'bg-amber-500/20 text-amber-300' },
  }
  const s = map[status] ?? { label: status, cls: 'bg-white/10 text-white/50' }
  return <span className={`text-[10px] px-1.5 py-0.5 rounded${' ' + s.cls}`}>{s.label}</span>
}

// ── 主组件 ──────────────────────────────────────────

export default function GoalAgentPanel() {
  const [contract, setContract] = useState<GoalContract | null>(null)
  const [cronTasks, setCronTasks] = useState<CronTask[]>([])
  const [soulGrowth, setSoulGrowth] = useState<SoulGrowth | null>(null)
  const [driftResult, setDriftResult] = useState<DriftResult | null>(null)
  const [intent, setIntent] = useState('')
  const [loading, setLoading] = useState(true)
  const [drafting, setDrafting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const resp = await fetch('/api/v3/goal/soul-status?user_id=default')
      if (resp.ok) {
        const result = await resp.json()
        if (result.success) {
          setSoulGrowth(result.data?.soul?.growth_metrics ?? null)
          setDriftResult(result.data?.drift ?? null)
          setCronTasks(result.data?.cron ?? [])
          setContract(result.data?.contract ?? generateMockContract())
        } else {
          setSoulGrowth(generateMockSoulGrowth())
          setDriftResult(generateMockDrift())
          setCronTasks(generateMockCronTasks())
          setContract(generateMockContract())
        }
      } else {
        setSoulGrowth(generateMockSoulGrowth())
        setDriftResult(generateMockDrift())
        setCronTasks(generateMockCronTasks())
        setContract(generateMockContract())
      }
    } catch {
      setSoulGrowth(generateMockSoulGrowth())
      setDriftResult(generateMockDrift())
      setCronTasks(generateMockCronTasks())
      setContract(generateMockContract())
    }
    setLoading(false)
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const handleDraftGoal = async () => {
    if (!intent.trim()) return
    setDrafting(true)
    try {
      const res = await fetch('/api/v3/goal/contract-draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ intent, request_id: 'goal-' + Date.now() }),
      })
      if (res.ok) {
        const data = await res.json()
        if (data.success) {
          setContract(data.contract)
        } else {
          setContract(generateMockContract())
        }
      } else {
        setContract(generateMockContract())
      }
    } catch {
      setContract(generateMockContract())
    }
    setDrafting(false)
  }

  // ── Loading ──
  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-accent/30 border-t-accent rounded-full animate-spin mx-auto mb-3" />
          <div className="text-textSecondary text-sm">加载 Goal 数据...</div>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto p-4 md:p-6">

        {/* 标题栏 */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <IconTarget size={22} className="text-accent" />
            <h2 className="text-lg font-semibold text-white">Goal 导向智能体 (Goal-Directed Agent)</h2>
          </div>
          <button onClick={fetchData} className="p-1.5 rounded hover:bg-white/10 text-textSecondary hover:text-white transition-colors" title="刷新">
            <IconRefresh size={16} />
          </button>
        </div>

        {/* Goal Contract 起草区 */}
        <div className="bg-white/5 rounded-lg p-4 mb-4">
          <div className="flex items-center gap-2 mb-4">
            <IconDescription size={16} className="text-blue-400" />
            <span className="text-sm font-medium text-white">Goal Contract 起草</span>
          </div>

          <div className="flex gap-3 mb-4">
            <div className="flex-1">
              <input
                type="text"
                value={intent}
                onChange={e => setIntent(e.target.value)}
                placeholder="输入目标意图 (Intent)..."
                className="w-full bg-white/10 border border-white/10 rounded-md px-3 py-2 text-sm text-white placeholder:text-white/30 outline-none focus:border-accent/50 transition-colors"
                onKeyDown={e => { if (e.key === 'Enter') handleDraftGoal() }}
              />
            </div>
            <button
              onClick={handleDraftGoal}
              disabled={!intent.trim() || drafting}
              className="px-4 py-2 rounded-md bg-accent text-white text-sm font-medium disabled:opacity-40 hover:bg-accent/80 transition-colors flex items-center gap-2"
            >
              {drafting ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  生成中
                </>
              ) : (
                <>
                  <IconSend size={14} />
                  起草
                </>
              )}
            </button>
          </div>

          {contract && (
            <>
              {/* 五闸门 Stepper */}
              <div className="mb-4">
                <div className="flex items-center gap-1">
                  {GATES.map((gate, idx) => (
                    <div key={gate} className="flex items-center flex-1">
                      <div className={[
                        'flex-1 text-center py-1.5 rounded text-[10px] font-medium transition-colors',
                        idx < GATES.length - 1 ? 'bg-accent/20 text-accent' : 'bg-white/10 text-white/50',
                      ].join(' ')}>
                        {gate}
                      </div>
                      {idx < GATES.length - 1 && (
                        <div className="w-3 h-px bg-white/10 flex-shrink-0" />
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Contract 详情 */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="bg-white/[0.03] rounded-md p-3">
                  <div className="text-[10px] text-textSecondary mb-1">Intent 意图</div>
                  <div className="text-xs text-white">{contract.intent}</div>
                </div>
                <div className="bg-white/[0.03] rounded-md p-3">
                  <div className="text-[10px] text-textSecondary mb-1">Goal Hash</div>
                  <div className="text-xs text-accent font-mono">{contract.goal_hash}</div>
                </div>
                <div className="bg-white/[0.03] rounded-md p-3">
                  <div className="text-[10px] text-textSecondary mb-1">Scope In</div>
                  <div className="flex flex-wrap gap-1">
                    {contract.scope_in.map(s => (
                      <span key={s} className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300">{s}</span>
                    ))}
                  </div>
                </div>
                <div className="bg-white/[0.03] rounded-md p-3">
                  <div className="text-[10px] text-textSecondary mb-1">Scope Out</div>
                  <div className="flex flex-wrap gap-1">
                    {contract.scope_out.map(s => (
                      <span key={s} className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/15 text-red-300">{s}</span>
                    ))}
                  </div>
                </div>
                <div className="bg-white/[0.03] rounded-md p-3">
                  <div className="text-[10px] text-textSecondary mb-1">Evidence Required</div>
                  <ul className="space-y-0.5">
                    {contract.evidence_required.map((e, i) => (
                      <li key={i} className="text-[10px] text-textSecondary flex gap-1"><span>•</span>{e}</li>
                    ))}
                  </ul>
                </div>
                <div className="bg-white/[0.03] rounded-md p-3">
                  <div className="text-[10px] text-textSecondary mb-1">Pause Conditions</div>
                  <ul className="space-y-0.5">
                    {contract.pause_conditions.map((p, i) => (
                      <li key={i} className="text-[10px] text-amber-400/80 flex gap-1"><span>⏸</span>{p}</li>
                    ))}
                  </ul>
                </div>
              </div>
              <div className="bg-white/[0.03] rounded-md p-3 mt-3">
                <div className="text-[10px] text-textSecondary mb-1">Acceptance 验收标准</div>
                <div className="text-xs text-white">{contract.acceptance}</div>
              </div>
            </>
          )}
        </div>

        {/* Execution Gate 状态 */}
        <div className="bg-white/5 rounded-lg p-4 mb-4">
          <div className="flex items-center gap-2 mb-3">
            <IconPendingActions size={16} className="text-amber-400" />
            <span className="text-sm font-medium text-white">Execution Gate 执行门控</span>
            {contract && (
              <div className="ml-auto">
                <GateStatusBadge status={contract.status} />
              </div>
            )}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {['PENDING', 'AUTHORIZED', 'EXECUTING', 'COMPLETED'].map((s, i) => {
              const isContractStatus = contract?.status
              const isReached = isContractStatus && ['PENDING', 'AUTHORIZED', 'EXECUTING', 'COMPLETED'].indexOf(isContractStatus) >= i
              return (
                <div
                  key={s}
                  className={[
                    'rounded-md p-2 text-center transition-colors',
                    isReached ? 'bg-emerald-500/10 border border-emerald-500/20' : 'bg-white/[0.02] border border-white/5',
                  ].join(' ')}
                >
                  <div className={[
                    'text-sm font-bold',
                    isReached ? 'text-emerald-400' : 'text-white/30',
                  ].join(' ')}>
                    {i + 1}
                  </div>
                  <div className={[
                    'text-[9px] mt-0.5',
                    isReached ? 'text-emerald-400/80' : 'text-white/30',
                  ].join(' ')}>
                    {s}
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* CronFire 调度列表 */}
        <div className="bg-white/5 rounded-lg p-4 mb-4">
          <div className="flex items-center gap-2 mb-3">
            <IconClock size={16} className="text-blue-400" />
            <span className="text-sm font-medium text-white">CronFire 调度任务</span>
            <span className="text-[10px] text-textSecondary ml-auto">{cronTasks.length} 个任务</span>
          </div>
          <div className="space-y-2">
            {cronTasks.map(task => (
              <div key={task.schedule_id} className="bg-white/[0.03] rounded-md p-3 flex items-center gap-3">
                <div className="w-2 h-2 rounded-full bg-emerald-400 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-xs text-white font-medium">{task.task_name}</div>
                  <div className="text-[10px] text-textSecondary font-mono mt-0.5">{task.cron_expr}</div>
                </div>
                <div className="text-[10px] text-textSecondary text-right flex-shrink-0">
                  <div className="mb-0.5">{task.schedule_id}</div>
                  <div>最近: {new Date(task.last_fire).toLocaleString('zh-CN')}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Soul-Graph 增长指标 + 漂移检测 */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          {/* Soul-Graph */}
          {soulGrowth && (
            <div className="bg-white/5 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3">
                <IconGraph size={16} className="text-purple-400" />
                <span className="text-sm font-medium text-white">Soul-Graph 增长</span>
              </div>
              <div className="text-2xl font-bold text-white mb-1 font-mono">{soulGrowth.total_segments}</div>
              <div className="text-[10px] text-textSecondary mb-4">总段落数</div>

              <div className="space-y-2 mb-3">
                {Object.entries(soulGrowth.layers).map(([layer, count]) => (
                  <div key={layer} className="flex items-center gap-2">
                    <span className="text-[10px] text-textSecondary w-28 truncate">{layer}</span>
                    <div className="flex-1">
                      <ProgressBar value={count / soulGrowth.total_segments} color="#A855F7" />
                    </div>
                    <span className="text-[10px] text-white/60 font-mono w-8 text-right">{count}</span>
                  </div>
                ))}
              </div>

              <div className="text-[10px] text-textSecondary">
                最后压缩: {new Date(soulGrowth.last_compaction).toLocaleString('zh-CN')}
              </div>
            </div>
          )}

          {/* MUS 漂移检测 */}
          {driftResult && (
            <div className="bg-white/5 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3">
                <IconSpeed size={16} className="text-amber-400" />
                <span className="text-sm font-medium text-white">MUS 漂移检测</span>
              </div>

              <div className="flex items-center gap-3 mb-4">
                <div className="relative w-16 h-16">
                  <svg className="w-16 h-16 -rotate-90" viewBox="0 0 64 64">
                    <circle cx="32" cy="32" r="28" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="4" />
                    <circle
                      cx="32" cy="32" r="28" fill="none"
                      stroke={driftResult.drift_score > 0.3 ? '#FF6B6B' : driftResult.drift_score > 0.15 ? '#FFE66D' : '#4ECDC4'}
                      strokeWidth="4"
                      strokeDasharray={`${driftResult.drift_score * 175} 175`}
                      strokeLinecap="round"
                    />
                  </svg>
                  <div className="absolute inset-0 flex items-center justify-center">
                    <span className={[
                      'text-sm font-bold font-mono',
                      driftResult.drift_score > 0.3 ? 'text-red-400' : driftResult.drift_score > 0.15 ? 'text-amber-400' : 'text-emerald-400',
                    ].join(' ')}>
                      {(driftResult.drift_score * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>
                <div className="flex-1">
                  <div className={[
                    'flex items-center gap-1.5 text-xs font-medium mb-1',
                    driftResult.drift_detected ? 'text-amber-400' : 'text-emerald-400',
                  ].join(' ')}>
                    {driftResult.drift_detected ? <IconWarning size={14} /> : <IconCheck size={14} />}
                    {driftResult.drift_detected ? '检测到漂移' : '无漂移'}
                  </div>
                  <div className="text-[11px] text-textSecondary leading-relaxed">
                    {driftResult.recommendation}
                  </div>
                </div>
              </div>

              <div className="bg-white/[0.03] rounded-md p-3">
                <div className="text-[10px] text-textSecondary mb-2">漂移阈值参考</div>
                <div className="flex gap-1">
                  <div className="flex-1 h-4 rounded-l bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-[8px] text-emerald-400">
                    &lt;15% 安全
                  </div>
                  <div className="flex-1 h-4 bg-amber-500/20 border-y border-amber-500/30 flex items-center justify-center text-[8px] text-amber-400">
                    15-30% 警惕
                  </div>
                  <div className="flex-1 h-4 rounded-r bg-red-500/20 border border-red-500/30 flex items-center justify-center text-[8px] text-red-400">
                    &gt;30% 高危
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* 底部间距 */}
        <div className="h-6" />
      </div>
    </div>
  )
}
