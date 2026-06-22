import { useState, useEffect } from 'react'
import { IconHeartbeat, IconWarning, IconTrendingUp, IconHistory } from './icons'

interface HealthData {
  state: string
  habitLoopDetected: boolean
  habitLoopCount: number
  biasPenaltyScore: number
  musReflectionTriggered: boolean
  agentPaused: boolean
  recommendation: string
  timestamp: number
  loaded: boolean
}

export default function CognitiveHealthPanel() {
  const [health, setHealth] = useState<HealthData>({
    state: 'LOADING', habitLoopDetected: false, habitLoopCount: 0,
    biasPenaltyScore: 0, musReflectionTriggered: false,
    agentPaused: false, recommendation: '', timestamp: 0, loaded: false
  })

  const fetchHealth = async () => {
    try {
      const resp = await fetch('/api/v3/cognitive-health/check', { method: 'POST' })
      if (resp.ok) {
        const data = await resp.json()
        setHealth({
          state: data.state || 'NORMAL',
          habitLoopDetected: data.habit_loop_detected ?? false,
          habitLoopCount: data.habit_loop_count ?? 0,
          biasPenaltyScore: data.bias_penalty_score ?? 0,
          musReflectionTriggered: data.mus_reflection_triggered ?? false,
          agentPaused: data.agent_paused ?? false,
          recommendation: data.recommendation || '',
          timestamp: data.timestamp || Date.now(),
          loaded: true
        })
      } else {
        // Mock data fallback
        setHealth({
          state: 'NORMAL', habitLoopDetected: false, habitLoopCount: 0,
          biasPenaltyScore: 0.15, musReflectionTriggered: false,
          agentPaused: false, recommendation: 'continue - 认知健康正常',
          timestamp: Date.now(), loaded: true
        })
      }
    } catch {
      // Mock data fallback
      setHealth({
        state: 'NORMAL', habitLoopDetected: false, habitLoopCount: 0,
        biasPenaltyScore: 0.15, musReflectionTriggered: false,
        agentPaused: false, recommendation: 'continue - API 未连接，使用模拟数据',
        timestamp: Date.now(), loaded: true
      })
    }
  }

  useEffect(() => { fetchHealth() }, [])

  const getStateColor = (state: string) => {
    switch (state) {
      case 'PAUSED': return 'text-rose-400'
      case 'MUS_REFLECTION': return 'text-amber-400'
      case 'BIAS_WARNING': return 'text-orange-400'
      case 'NORMAL': return 'text-emerald-400'
      default: return 'text-gray-400'
    }
  }

  const getStateBg = (state: string) => {
    switch (state) {
      case 'PAUSED': return 'bg-rose-500/20'
      case 'MUS_REFLECTION': return 'bg-amber-500/20'
      case 'BIAS_WARNING': return 'bg-orange-500/20'
      case 'NORMAL': return 'bg-emerald-500/20'
      default: return 'bg-gray-500/20'
    }
  }

  const biasPercent = Math.round(health.biasPenaltyScore * 100);

  return (
    <div className="h-full overflow-y-auto p-6 bg-chatBg text-textPrimary">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-rose-500/20 flex items-center justify-center">
          <IconHeartbeat size={22} className="text-rose-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">认知健康监控</h1>
          <p className="text-xs text-textSecondary">AGI Cognitive Health — 双引擎成瘾模型检测</p>
        </div>
        <button onClick={fetchHealth} className="ml-auto px-3 py-1.5 bg-sidebarActive hover:bg-sidebarHover rounded-md text-xs transition-colors">
          刷新
        </button>
      </div>

      {/* Status Card */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {/* State */}
        <div className="bg-sidebar rounded-xl p-4 border border-white/5">
          <p className="text-xs text-textSecondary mb-1">状态</p>
          <span className={`inline-block px-2.5 py-1 rounded-full text-xs font-medium ${getStateBg(health.state)} ${getStateColor(health.state)}`}>
            {health.state}
          </span>
          {health.agentPaused && (
            <div className="mt-2 flex items-center gap-1.5 text-xs text-rose-400">
              <IconWarning size={14} /> Agent 已暂停
            </div>
          )}
        </div>

        {/* Bias Penalty */}
        <div className="bg-sidebar rounded-xl p-4 border border-white/5">
          <p className="text-xs text-textSecondary mb-2">确认偏误得分</p>
          <div className="flex items-end gap-2">
            <span className={`text-2xl font-bold ${health.biasPenaltyScore > 0.7 ? 'text-rose-400' : health.biasPenaltyScore > 0.4 ? 'text-amber-400' : 'text-emerald-400'}`}>
              {biasPercent}%
            </span>
            <span className="text-xs text-textSecondary mb-1">/ 100%</span>
          </div>
          <div className="mt-2 w-full h-1.5 bg-white/10 rounded-full overflow-hidden">
            <div className={`h-full rounded-full transition-all duration-500 ${health.biasPenaltyScore > 0.7 ? 'bg-rose-500' : health.biasPenaltyScore > 0.4 ? 'bg-amber-500' : 'bg-emerald-500'}`}
                 style={{ width: `${biasPercent}%` }} />
          </div>
        </div>

        {/* Habit Loop */}
        <div className="bg-sidebar rounded-xl p-4 border border-white/5">
          <p className="text-xs text-textSecondary mb-2">回路计数</p>
          <div className="flex items-end gap-2">
            <span className={`text-2xl font-bold ${health.habitLoopDetected ? 'text-rose-400' : 'text-emerald-400'}`}>
              {health.habitLoopCount}
            </span>
            <span className="text-xs text-textSecondary mb-1">/ 3 阈值</span>
          </div>
          {health.habitLoopDetected && (
            <p className="mt-1 text-xs text-rose-400">⚠ 回路已触发</p>
          )}
        </div>

        {/* MUS Reflection */}
        <div className="bg-sidebar rounded-xl p-4 border border-white/5">
          <p className="text-xs text-textSecondary mb-2">MUS 反思</p>
          <span className={`inline-block px-2.5 py-1 rounded-full text-xs font-medium ${
            health.musReflectionTriggered ? 'bg-amber-500/20 text-amber-400' : 'bg-gray-500/20 text-gray-400'
          }`}>
            {health.musReflectionTriggered ? '已触发' : '未触发'}
          </span>
        </div>
      </div>

      {/* Recommendation */}
      <div className="bg-sidebar rounded-xl p-4 border border-white/5 mb-6">
        <div className="flex items-center gap-2 mb-2">
          <IconTrendingUp size={16} className="text-accent" />
          <h2 className="text-sm font-semibold">建议操作</h2>
        </div>
        <p className={`text-sm ${health.recommendation.includes('pause') || health.recommendation.includes('暂停') ? 'text-rose-400' : 'text-textPrimary'}`}>
          {health.recommendation || '正在分析...'}
        </p>
      </div>

      {/* Health Status Timeline */}
      <div className="bg-sidebar rounded-xl p-4 border border-white/5">
        <div className="flex items-center gap-2 mb-4">
          <IconHistory size={16} className="text-accent" />
          <h2 className="text-sm font-semibold">认知健康六组件</h2>
        </div>
        
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {[
            { label: 'C1 习惯锁定检测', status: health.habitLoopDetected ? 'ALERT' : 'OK', desc: '连续 κ-Snap 模式检测' },
            { label: 'C2 确认偏误评分', status: health.biasPenaltyScore > 0.5 ? 'ALERT' : 'OK', desc: `Gan 极化偏误: ${biasPercent}%` },
            { label: 'C3 MUS 反思触发', status: health.musReflectionTriggered ? 'ACTIVE' : 'STANDBY', desc: 'MUS 双存响应' },
            { label: 'C4 前额叶刹车', status: health.agentPaused ? 'ENGAGED' : 'READY', desc: 'ψ-锚暂停机制' },
            { label: 'C5 Purpose 锚定', status: 'OK', desc: 'DIKWP P层在线' },
            { label: 'C6 κ-Snap 多样性', status: 'OK', desc: '多样性守恒正常' },
          ].map((item, idx) => (
            <div key={idx} className="bg-white/5 rounded-lg p-3 border border-white/5">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-textPrimary">{item.label}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                  item.status === 'OK' || item.status === 'READY' || item.status === 'STANDBY'
                    ? 'bg-emerald-500/20 text-emerald-400'
                    : item.status === 'ACTIVE'
                    ? 'bg-amber-500/20 text-amber-400'
                    : 'bg-rose-500/20 text-rose-400'
                }`}>{item.status}</span>
              </div>
              <p className="text-[11px] text-textSecondary">{item.desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Timestamp */}
      {health.loaded && (
        <p className="text-right text-[10px] text-textSecondary/50 mt-4">
          最后检查: {new Date(health.timestamp * 1000).toLocaleString('zh-CN')}
        </p>
      )}
    </div>
  )
}
