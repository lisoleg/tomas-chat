import { useState, useEffect, useCallback } from 'react'
import {
  IconLock, IconPsychology, IconGavel, IconCheck, IconWarning,
  IconShield, IconVerified, IconTrendingUp, IconHistory, IconRefresh
} from './icons'

// ── 类型定义 ────────────────────────────────────────

interface Principle {
  id: string
  text: string
  I_value: number
  type: 'constitutional' | 'regulatory'
}

interface AuthLevel {
  agent_id: string
  level: number
  label: string
  earned_at: number
}

interface SLA {
  purpose_id: string
  metric: string
  target: number
  actual: number
  on_target: boolean
}

interface AuditRecord {
  audit_id: string
  auditor: string
  compliance_score: number
  findings: string[]
}

interface AlignmentStatus {
  phase: string
  lock_in: { principles: Principle[]; veto_history: any[] }
  rearing: { auth_levels: AuthLevel[]; mus_zones: any[] }
  governance: { slas: SLA[]; audits: AuditRecord[]; pluralistic_score: number }
}

// ── Mock Data ───────────────────────────────────────

function generateMockData(): AlignmentStatus {
  return {
    phase: 'rearing',
    lock_in: {
      principles: [
        { id: 'C1', text: '价值锚定：最大化人类福祉', I_value: 0.92, type: 'constitutional' },
        { id: 'C2', text: '安全优先：不可伤害原则', I_value: 0.98, type: 'constitutional' },
        { id: 'C3', text: '透明可解释：决策可审计', I_value: 0.87, type: 'constitutional' },
        { id: 'C4', text: '边界尊重：拒绝越权任务', I_value: 0.95, type: 'regulatory' },
        { id: 'C5', text: '人机协作：永远可接管', I_value: 0.91, type: 'regulatory' },
        { id: 'C6', text: '多元对齐：避免价值单一化', I_value: 0.84, type: 'regulatory' },
      ],
      veto_history: [],
    },
    rearing: {
      auth_levels: [
        { agent_id: 'agent_gaia_01', level: 2, label: 'Read', earned_at: Date.now() - 86400000 },
        { agent_id: 'agent_sweb_01', level: 3, label: 'Write Safe', earned_at: Date.now() - 172800000 },
        { agent_id: 'agent_code_01', level: 1, label: 'Sandbox', earned_at: Date.now() - 3600000 },
      ],
      mus_zones: [],
    },
    governance: {
      slas: [
        { purpose_id: 'P1', metric: '响应延迟', target: 200, actual: 187, on_target: true },
        { purpose_id: 'P2', metric: '准确率', target: 0.95, actual: 0.93, on_target: false },
        { purpose_id: 'P3', metric: '安全违规率', target: 0.01, actual: 0.003, on_target: true },
      ],
      audits: [
        {
          audit_id: 'aud_001',
          auditor: '第三方审计 A',
          compliance_score: 0.91,
          findings: ['原则 C2 符合', '原则 C4 部分符合，需补充边界测试'],
        },
        {
          audit_id: 'aud_002',
          auditor: '第三方审计 B',
          compliance_score: 0.88,
          findings: ['整体合规良好', '建议加强MUS争端解决机制'],
        },
      ],
      pluralistic_score: 0.87,
    },
  }
}

// ── 阶段定义 ────────────────────────────────────────

const PHASES = [
  { key: 'lock_in', label: 'Lock-in 控制', icon: IconLock, color: '#FF6B6B' },
  { key: 'rearing', label: 'Rearing 抚养', icon: IconPsychology, color: '#4ECDC4' },
  { key: 'governance', label: 'Governance 治理', icon: IconGavel, color: '#FFE66D' },
]

const LEVEL_LABELS = ['Sandbox', 'Read', 'Write Safe', 'Full']

// ── 辅助组件 ────────────────────────────────────────

function PhaseBadge({ status, label }: { status: string; label: string }) {
  const map: Record<string, { cls: string }> = {
    lock_in: { cls: 'bg-red-500/20 text-red-300 border-red-500/30' },
    rearing: { cls: 'bg-teal-500/20 text-teal-300 border-teal-500/30' },
    governance: { cls: 'bg-amber-500/20 text-amber-300 border-amber-500/30' },
  }
  const s = map[status] ?? { cls: 'bg-white/10 text-white/50 border-white/20' }
  return <span className={`text-[10px] px-2 py-0.5 rounded-full border ${s.cls} font-medium`}>{label}</span>
}

function ProgressBar({ value, color }: { value: number; color: string }) {
  return (
    <div className="w-full h-1.5 bg-white/10 rounded-full overflow-hidden">
      <div className="h-full rounded-full transition-all duration-500" style={{ width: `${Math.min(100, value * 100)}%`, backgroundColor: color }} />
    </div>
  )
}

// ── 主组件 ──────────────────────────────────────────

export default function AlignmentTriadPanel() {
  const [data, setData] = useState<AlignmentStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedPhase, setExpandedPhase] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const resp = await fetch('/api/v3/alignment/triad-status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      if (resp.ok) {
        const result = await resp.json()
        if (result.success) {
          setData(result.data)
        } else {
          setData(generateMockData())
        }
      } else {
        setData(generateMockData())
      }
    } catch {
      setData(generateMockData())
    }
    setLoading(false)
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const currentPhaseIdx = PHASES.findIndex(p => p.key === data?.phase)
  const togglePhase = (key: string) => setExpandedPhase(prev => prev === key ? null : key)

  // ── Loading ──
  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-accent/30 border-t-accent rounded-full animate-spin mx-auto mb-3" />
          <div className="text-textSecondary text-sm">加载对齐数据...</div>
        </div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center text-textSecondary">
          <IconShield size={40} className="mx-auto mb-3 opacity-40" />
          <div className="text-sm mb-2">对齐数据不可用</div>
          <button onClick={fetchData} className="text-xs text-accent hover:underline">重试</button>
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
            <IconShield size={22} className="text-accent" />
            <h2 className="text-lg font-semibold text-white">对齐三范式 (Alignment Triad)</h2>
            <PhaseBadge status={data.phase} label={PHASES.find(p => p.key === data.phase)?.label ?? data.phase} />
          </div>
          <button onClick={fetchData} className="p-1.5 rounded hover:bg-white/10 text-textSecondary hover:text-white transition-colors" title="刷新">
            <IconRefresh size={16} />
          </button>
        </div>

        {/* 三阶段进度指示器 */}
        <div className="bg-white/5 rounded-lg p-4 mb-6">
          <div className="flex items-center justify-between relative">
            {PHASES.map((phase, idx) => {
              const isActive = idx === currentPhaseIdx
              const isDone = idx < currentPhaseIdx
              const isFuture = idx > currentPhaseIdx
              const IconComponent = phase.icon
              return (
                <div key={phase.key} className="flex items-center flex-1 relative">
                  <div className="flex flex-col items-center z-10">
                    <div
                      className={[
                        'w-10 h-10 rounded-full flex items-center justify-center transition-all',
                        isActive ? 'ring-2 ring-offset-2 ring-offset-[#1a1a2e] scale-110' : '',
                        isDone ? 'opacity-80' : isFuture ? 'opacity-40' : '',
                      ].join(' ')}
                      style={{ backgroundColor: isActive || isDone ? phase.color : 'rgba(255,255,255,0.08)', color: isActive ? '#fff' : undefined }}
                    >
                      {isDone ? <IconCheck size={18} className="text-white" /> : <IconComponent size={18} />}
                    </div>
                    <span className={[
                      'text-[10px] mt-1.5 font-medium whitespace-nowrap',
                      isActive ? 'text-white' : isDone ? 'text-white/70' : 'text-white/30',
                    ].join(' ')}>
                      {phase.label}
                    </span>
                  </div>
                  {idx < PHASES.length - 1 && (
                    <div className="flex-1 h-px mx-2" style={{ backgroundColor: isDone ? PHASES[idx + 1].color : 'rgba(255,255,255,0.1)' }} />
                  )}
                </div>
              )
            })}
          </div>
        </div>

        {/* Lock-in 区 */}
        <div className="bg-white/5 rounded-lg overflow-hidden mb-4">
          <button
            onClick={() => togglePhase('lock_in')}
            className="w-full flex items-center gap-3 p-4 hover:bg-white/[0.03] transition-colors text-left"
          >
            <IconLock size={18} className="text-red-400 flex-shrink-0" />
            <span className="font-medium text-white text-sm">Lock-in 控制区</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-300 ml-auto">
              {currentPhaseIdx >= 0 ? (currentPhaseIdx === 0 ? '▶ 当前' : '✓ 已锁定') : '○ 待激活'}
            </span>
            <span className="text-textSecondary text-[10px]">{expandedPhase === 'lock_in' ? '▲' : '▼'}</span>
          </button>
          {expandedPhase === 'lock_in' && (
            <div className="px-4 pb-4 border-t border-white/5 pt-4">
              {/* 宪法原则列表 */}
              <div className="text-xs text-textSecondary mb-3">宪法原则 (C1-C6)</div>
              <div className="space-y-2">
                {data.lock_in.principles.map(p => (
                  <div key={p.id} className="bg-white/[0.03] rounded-md p-3 flex items-center gap-3">
                    <div className={[
                      'w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0',
                      p.type === 'constitutional' ? 'bg-red-500/20 text-red-300' : 'bg-amber-500/20 text-amber-300',
                    ].join(' ')}>
                      {p.id}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs text-white truncate">{p.text}</div>
                      <div className="flex items-center gap-2 mt-1">
                        <div className="flex-1">
                          <ProgressBar value={p.I_value} color={p.I_value >= 0.9 ? '#4ECDC4' : p.I_value >= 0.8 ? '#FFE66D' : '#FF6B6B'} />
                        </div>
                        <span className={[
                          'text-[10px] font-mono font-medium flex-shrink-0',
                          p.I_value >= 0.9 ? 'text-teal-400' : p.I_value >= 0.8 ? 'text-amber-400' : 'text-red-400',
                        ].join(' ')}>
                          I={p.I_value.toFixed(2)}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      <div className={[
                        'w-6 h-4 rounded-full relative cursor-pointer transition-colors',
                        p.I_value >= 0.8 ? 'bg-red-500/40' : 'bg-white/10',
                      ].join(' ')} title={p.I_value >= 0.8 ? '硬否决就绪' : '硬否决未激活'}>
                        <div className={[
                          'w-3 h-3 rounded-full bg-white shadow absolute top-0.5 transition-transform',
                          p.I_value >= 0.8 ? 'translate-x-2.5' : 'translate-x-0.5',
                        ].join(' ')} />
                      </div>
                      <span className="text-[9px] text-textSecondary">否决</span>
                    </div>
                  </div>
                ))}
              </div>
              {/* 否决历史 */}
              <div className="mt-4 text-xs text-textSecondary">
                否决历史: {data.lock_in.veto_history.length > 0 ? `${data.lock_in.veto_history.length} 次` : '无记录'}
              </div>
            </div>
          )}
        </div>

        {/* Rearing 区 */}
        <div className="bg-white/5 rounded-lg overflow-hidden mb-4">
          <button
            onClick={() => togglePhase('rearing')}
            className="w-full flex items-center gap-3 p-4 hover:bg-white/[0.03] transition-colors text-left"
          >
            <IconPsychology size={18} className="text-teal-400 flex-shrink-0" />
            <span className="font-medium text-white text-sm">Rearing 抚养区</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-teal-500/20 text-teal-300 ml-auto">
              {currentPhaseIdx >= 1 ? (currentPhaseIdx === 1 ? '▶ 当前' : '✓ 已完成') : '○ 待激活'}
            </span>
            <span className="text-textSecondary text-[10px]">{expandedPhase === 'rearing' ? '▲' : '▼'}</span>
          </button>
          {expandedPhase === 'rearing' && (
            <div className="px-4 pb-4 border-t border-white/5 pt-4">
              {/* 授权级别 */}
              <div className="text-xs text-textSecondary mb-3">渐进授权级别</div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
                {data.rearing.auth_levels.map(al => (
                  <div key={al.agent_id} className="bg-white/[0.03] rounded-md p-3">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs text-white font-medium">{al.agent_id}</span>
                      <span className={[
                        'text-[10px] px-1.5 py-0.5 rounded',
                        al.level >= 3 ? 'bg-emerald-500/20 text-emerald-300' :
                          al.level === 2 ? 'bg-blue-500/20 text-blue-300' :
                            'bg-white/10 text-white/50',
                      ].join(' ')}>
                        {LEVEL_LABELS[al.level] ?? `Level ${al.level}`}
                      </span>
                    </div>
                    <div className="flex gap-0.5">
                      {LEVEL_LABELS.map((l, i) => (
                        <div
                          key={l}
                          className={[
                            'flex-1 h-1 rounded-full transition-colors',
                            i <= al.level ? 'bg-teal-500' : 'bg-white/10',
                          ].join(' ')}
                        />
                      ))}
                    </div>
                    <div className="text-[10px] text-textSecondary mt-1">
                      获得时间: {new Date(al.earned_at).toLocaleDateString('zh-CN')}
                    </div>
                  </div>
                ))}
              </div>

              {/* MUS 双存区计数 */}
              <div className="bg-white/[0.03] rounded-md p-3">
                <div className="text-xs text-textSecondary mb-2">MUS 双存区</div>
                <div className="grid grid-cols-3 gap-3 text-center">
                  <div>
                    <div className="text-lg font-mono text-white">12</div>
                    <div className="text-[10px] text-textSecondary">活跃提案</div>
                  </div>
                  <div>
                    <div className="text-lg font-mono text-amber-400">3</div>
                    <div className="text-[10px] text-textSecondary">谈判中</div>
                  </div>
                  <div>
                    <div className="text-lg font-mono text-teal-400">9</div>
                    <div className="text-[10px] text-textSecondary">已解决</div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Governance 区 */}
        <div className="bg-white/5 rounded-lg overflow-hidden mb-4">
          <button
            onClick={() => togglePhase('governance')}
            className="w-full flex items-center gap-3 p-4 hover:bg-white/[0.03] transition-colors text-left"
          >
            <IconGavel size={18} className="text-amber-400 flex-shrink-0" />
            <span className="font-medium text-white text-sm">Governance 治理区</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 ml-auto">
              {currentPhaseIdx >= 2 ? '▶ 当前' : '○ 待激活'}
            </span>
            <span className="text-textSecondary text-[10px]">{expandedPhase === 'governance' ? '▲' : '▼'}</span>
          </button>
          {expandedPhase === 'governance' && (
            <div className="px-4 pb-4 border-t border-white/5 pt-4">
              {/* SLA 指标 */}
              <div className="text-xs text-textSecondary mb-3">Purpose SLA 指标</div>
              <div className="space-y-3 mb-4">
                {data.governance.slas.map(sla => (
                  <div key={sla.purpose_id} className="bg-white/[0.03] rounded-md p-3">
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-white font-medium">{sla.purpose_id}</span>
                        <span className="text-[11px] text-textSecondary">{sla.metric}</span>
                      </div>
                      {sla.on_target ? (
                        <span className="flex items-center gap-1 text-[10px] text-emerald-400">
                          <IconCheck size={12} /> 达标
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-[10px] text-amber-400">
                          <IconWarning size={12} /> 偏离
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="flex-1">
                        <ProgressBar
                          value={sla.actual / sla.target}
                          color={sla.on_target ? '#4ECDC4' : '#FFE66D'}
                        />
                      </div>
                      <span className="text-[10px] font-mono text-textSecondary">
                        {sla.actual} / {sla.target}
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              {/* 多元对齐得分 */}
              <div className="bg-white/[0.03] rounded-md p-3 mb-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <IconVerified size={14} className="text-blue-400" />
                    <span className="text-xs text-white">多元对齐得分</span>
                  </div>
                  <span className={[
                    'text-sm font-mono font-bold',
                    data.governance.pluralistic_score >= 0.9 ? 'text-emerald-400' :
                      data.governance.pluralistic_score >= 0.8 ? 'text-amber-400' : 'text-red-400',
                  ].join(' ')}>
                    {(data.governance.pluralistic_score * 100).toFixed(0)}%
                  </span>
                </div>
                <ProgressBar value={data.governance.pluralistic_score} color="#4ECDC4" />
              </div>

              {/* 第三方审计记录 */}
              <div className="text-xs text-textSecondary mb-3">第三方审计记录</div>
              <div className="space-y-2">
                {data.governance.audits.map(audit => (
                  <div key={audit.audit_id} className="bg-white/[0.03] rounded-md p-3">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-xs text-white font-medium">{audit.auditor}</span>
                      <span className={[
                        'text-[10px] px-1.5 py-0.5 rounded',
                        audit.compliance_score >= 0.9 ? 'bg-emerald-500/20 text-emerald-300' :
                          audit.compliance_score >= 0.8 ? 'bg-amber-500/20 text-amber-300' :
                            'bg-red-500/20 text-red-300',
                      ].join(' ')}>
                        合规度 {(audit.compliance_score * 100).toFixed(0)}%
                      </span>
                    </div>
                    <ul className="space-y-0.5">
                      {audit.findings.map((f, i) => (
                        <li key={i} className="text-[11px] text-textSecondary flex items-start gap-1">
                          <span className="text-textSecondary/50 mt-0.5">•</span>
                          {f}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 底部 κ-Snap 审计链 */}
        <div className="bg-white/5 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-3">
            <IconHistory size={16} className="text-blue-400" />
            <span className="text-sm font-medium text-white">κ-Snap 审计链</span>
            <span className="text-[10px] text-textSecondary ml-auto">最近 4 条</span>
          </div>
          <div className="space-y-2">
            {[
              { id: 'snap_010', desc: 'P2 SLA 偏离告警触发', time: '2分钟前', status: 'alert' },
              { id: 'snap_009', desc: 'agent_code_01 Sandbox 晋升审计', time: '1小时前', status: 'info' },
              { id: 'snap_008', desc: '第三方审计 B 合规报告提交', time: '3小时前', status: 'success' },
              { id: 'snap_007', desc: 'C3 原则 I-value 更新 (0.85→0.87)', time: '6小时前', status: 'info' },
            ].map(snap => (
              <div key={snap.id} className="flex items-center gap-3 text-xs">
                <span className={[
                  'w-1.5 h-1.5 rounded-full flex-shrink-0',
                  snap.status === 'alert' ? 'bg-amber-400' : snap.status === 'success' ? 'bg-emerald-400' : 'bg-blue-400',
                ].join(' ')} />
                <span className="text-textSecondary font-mono text-[10px]">{snap.id}</span>
                <span className="text-white/70 flex-1 truncate">{snap.desc}</span>
                <span className="text-textSecondary text-[10px] flex-shrink-0">{snap.time}</span>
              </div>
            ))}
          </div>
        </div>

        {/* 底部间距 */}
        <div className="h-6" />
      </div>
    </div>
  )
}
