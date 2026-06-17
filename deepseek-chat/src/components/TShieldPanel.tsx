import React, { useState } from 'react';
import { IconShield, IconActivity, IconBrain, IconCpu } from './icons';

// ── Types ─────────────────────────────────────

interface ShieldStats {
  totalInferences: number;
  deadZeroCount: number;
  musCount: number;
  snapSwitches: number;
  avgIScene: number;
  gEgoSwitches: number;
}

interface ProcessingStage {
  id: string;
  name: string;
  description: string;
  status: 'active' | 'idle' | 'warning';
  lastRuntime: number; // ms
}

interface InferenceLog {
  id: string;
  timestamp: Date;
  iScene: number;
  isDeadZone: boolean;
  gEgoMode: 'afferent' | 'efferent' | 'none';
  stagesRun: string[];
  result: 'pass' | 'dead_zone' | 'mus_ambiguous';
}

// ── Mock Data ─────────────────────────────────────

function generateMockStats(): ShieldStats {
  return {
    totalInferences: 256,
    deadZeroCount: 18,
    musCount: 7,
    snapSwitches: 3,
    avgIScene: 0.68,
    gEgoSwitches: 5,
  };
}

function generateMockStages(): ProcessingStage[] {
  return [
    { id: 'i_scene', name: 'I-Scene 估计', description: '图像特征 → ℐ向量 → 死零判定', status: 'active', lastRuntime: 2.1 },
    { id: 'dz_graft', name: 'Dead-Zero Grafting', description: '死零盒子检测 + 嫁接修复', status: 'active', lastRuntime: 1.3 },
    { id: 'mus_mark', name: 'MUS 双盒标记', description: '相似度计算 + 矛盾对标记', status: 'idle', lastRuntime: 3.7 },
    { id: 'snap_sched', name: 'κ-Snap 调度', description: '场景复杂度 → 配置选择', status: 'active', lastRuntime: 0.8 },
  ];
}

function generateMockLogs(): InferenceLog[] {
  const base = Date.now();
  return [
    { id: 'i1', timestamp: new Date(base - 10000), iScene: 0.72, isDeadZone: false, gEgoMode: 'afferent', stagesRun: ['i_scene', 'dz_graft', 'snap_sched'], result: 'pass' },
    { id: 'i2', timestamp: new Date(base - 30000), iScene: 0.08, isDeadZone: true, gEgoMode: 'none', stagesRun: ['i_scene'], result: 'dead_zone' },
    { id: 'i3', timestamp: new Date(base - 60000), iScene: 0.55, isDeadZone: false, gEgoMode: 'efferent', stagesRun: ['i_scene', 'dz_graft', 'mus_mark'], result: 'mus_ambiguous' },
    { id: 'i4', timestamp: new Date(base - 120000), iScene: 0.91, isDeadZone: false, gEgoMode: 'afferent', stagesRun: ['i_scene', 'dz_graft', 'snap_sched'], result: 'pass' },
    { id: 'i5', timestamp: new Date(base - 180000), iScene: 0.35, isDeadZone: false, gEgoMode: 'afferent', stagesRun: ['i_scene', 'dz_graft', 'mus_mark', 'snap_sched'], result: 'pass' },
    { id: 'i6', timestamp: new Date(base - 240000), iScene: 0.15, isDeadZone: true, gEgoMode: 'none', stagesRun: ['i_scene'], result: 'dead_zone' },
  ];
}

// ── Component ─────────────────────────────────────

export default function TShieldPanel() {
  const [stats] = useState<ShieldStats>(generateMockStats());
  const [stages, setStages] = useState<ProcessingStage[]>(generateMockStages());
  const [logs] = useState<InferenceLog[]>(generateMockLogs());
  const [activeTab, setActiveTab] = useState<'overview' | 'processing' | 'logs'>('overview');
  const [gEgoMode, setGEgoMode] = useState<'afferent' | 'efferent' | 'auto'>('auto');

  const resultBadge = (r: InferenceLog['result']) => {
    const map: Record<InferenceLog['result'], { bg: string; text: string; label: string }> = {
      pass: { bg: 'bg-emerald-900/30', text: 'text-emerald-400', label: '通过' },
      dead_zone: { bg: 'bg-red-900/30', text: 'text-red-400', label: '死零拒绝' },
      mus_ambiguous: { bg: 'bg-amber-900/30', text: 'text-amber-400', label: 'MUS 歧义' },
    };
    const style = map[r];
    return <span className={`text-[10px] px-1.5 py-0.5 rounded ${style.bg} ${style.text} font-medium`}>{style.label}</span>;
  };

  const stageStatusColor = (s: ProcessingStage['status']) => {
    switch (s) {
      case 'active': return 'bg-emerald-500';
      case 'idle': return 'bg-slate-500';
      case 'warning': return 'bg-amber-500';
    }
  };

  function formatTime(d: Date): string {
    const diff = Date.now() - d.getTime();
    if (diff < 60000) return '刚刚';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
    return d.toLocaleDateString('zh-CN');
  }

  const toggleStage = (id: string) => {
    setStages(prev => prev.map(s => s.id === id ? { ...s, status: s.status === 'active' ? 'idle' : 'active' } : s));
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-4 md:px-6 pt-4 pb-2">
        <h1 className="text-xl font-semibold text-textPrimary">T-Shield 认知安全层</h1>
        <p className="text-sm text-textSecondary mt-1">
          I-Scene 估计 · Dead-Zero Grafting · MUS 双盒 · κ-Snap 调度 · G_ego 监控
        </p>
      </div>

      {/* Summary Cards */}
      <div className="px-4 md:px-6 pb-3">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
          <div className="bg-chatBgAlt rounded-xl border border-borderSubtle/30 p-3 text-center">
            <p className="text-2xl font-bold text-accent">{stats.totalInferences}</p>
            <p className="text-[10px] text-textSecondary mt-0.5">总推理</p>
          </div>
          <div className="bg-chatBgAlt rounded-xl border border-borderSubtle/30 p-3 text-center">
            <p className="text-2xl font-bold text-red-400">{stats.deadZeroCount}</p>
            <p className="text-[10px] text-textSecondary mt-0.5">死零拒绝</p>
          </div>
          <div className="bg-chatBgAlt rounded-xl border border-borderSubtle/30 p-3 text-center">
            <p className="text-2xl font-bold text-amber-400">{stats.musCount}</p>
            <p className="text-[10px] text-textSecondary mt-0.5">MUS 触发</p>
          </div>
          <div className="bg-chatBgAlt rounded-xl border border-borderSubtle/30 p-3 text-center">
            <p className="text-2xl font-bold text-cyan-400">{stats.snapSwitches}</p>
            <p className="text-[10px] text-textSecondary mt-0.5">κ-Snap 切换</p>
          </div>
          <div className="bg-chatBgAlt rounded-xl border border-borderSubtle/30 p-3 text-center">
            <p className="text-2xl font-bold text-violet-400">{stats.avgIScene.toFixed(2)}</p>
            <p className="text-[10px] text-textSecondary mt-0.5">ℐ-Scene 均值</p>
          </div>
          <div className="bg-chatBgAlt rounded-xl border border-borderSubtle/30 p-3 text-center">
            <p className="text-2xl font-bold text-emerald-400">{stats.gEgoSwitches}</p>
            <p className="text-[10px] text-textSecondary mt-0.5">G_ego 切换</p>
          </div>
        </div>
      </div>

      {/* Tab Bar */}
      <div className="px-4 md:px-6">
        <div className="flex border-b border-borderSubtle/30">
          {[
            { key: 'overview', label: '总览' },
            { key: 'processing', label: '处理流程' },
            { key: 'logs', label: '推理日志' },
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key as typeof activeTab)}
              className={`px-4 py-2 text-xs font-medium transition-colors border-b-2 -mb-[1px] ${
                activeTab === tab.key
                  ? 'text-accent border-accent'
                  : 'text-textSecondary border-transparent hover:text-textPrimary'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 md:px-6 py-3">
        {activeTab === 'overview' && (
          <div className="space-y-4">
            {/* G_ego Status */}
            <div className="bg-chatBgAlt rounded-xl border border-borderSubtle/30 p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-xs font-medium text-textSecondary uppercase tracking-wider">G_ego 双向算子状态</h3>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setGEgoMode(m => m === 'afferent' ? 'efferent' : m === 'efferent' ? 'auto' : 'afferent')}
                    className="text-[10px] px-2 py-0.5 rounded bg-accent/20 text-accent border border-accent/30 hover:bg-accent/30 transition-colors"
                  >
                    切换: {gEgoMode === 'afferent' ? 'Afferent' : gEgoMode === 'efferent' ? 'Efferent' : 'Auto'}
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="bg-chatBg rounded-lg p-3 text-center">
                  <p className="text-lg font-bold text-emerald-400">Afferent</p>
                  <p className="text-[9px] text-textSecondary mt-0.5">外部感知 → 内部语义</p>
                </div>
                <div className="bg-chatBg rounded-lg p-3 text-center">
                  <p className="text-lg font-bold text-violet-400">Efferent</p>
                  <p className="text-[9px] text-textSecondary mt-0.5">内部语义 → 外部行动</p>
                </div>
                <div className="bg-chatBg rounded-lg p-3 text-center">
                  <p className="text-lg font-bold text-accent">{stats.avgIScene.toFixed(2)}</p>
                  <p className="text-[9px] text-textSecondary mt-0.5">当前 ℐ-Scene</p>
                </div>
              </div>
              <div className="mt-3 text-[10px] text-textSecondary bg-chatBg/50 rounded p-2">
                ℹ️ G_ego 根据 ℐ-Scene 自动切换模式：ℐ ≥ 0.3 → Afferent（感知主导）；ℐ < 0.3 → Efferent（行动主导）。异常监控持续运行。
              </div>
            </div>

            {/* I-Scene Estimator Mini Status */}
            <div className="bg-chatBgAlt rounded-xl border border-borderSubtle/30 p-4">
              <h3 className="text-xs font-medium text-textSecondary uppercase tracking-wider mb-3">ℐ-Scene 估计器</h3>
              <div className="flex items-center gap-4">
                <div className="flex-1">
                  <div className="w-full h-2 bg-chatBg rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${
                        stats.avgIScene > 0.7 ? 'bg-emerald-400' : stats.avgIScene > 0.3 ? 'bg-amber-400' : 'bg-red-400'
                      }`}
                      style={{ width: `${stats.avgIScene * 100}%` }}
                    />
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-sm font-bold text-textPrimary">{stats.avgIScene.toFixed(2)}</p>
                  <p className="text-[9px] text-textSecondary">均值 (θ_dead=0.15)</p>
                </div>
              </div>
              <div className="mt-2 flex justify-between text-[9px] text-textSecondary">
                <span>死零区 &lt; 0.15</span>
                <span className="text-amber-400">过渡带 0.15-0.5</span>
                <span className="text-emerald-400">安全区 &gt; 0.5</span>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'processing' && (
          <div className="space-y-2">
            {stages.map(stage => (
              <div
                key={stage.id}
                className="bg-chatBgAlt rounded-lg border border-borderSubtle/30 p-3 cursor-pointer hover:border-borderSubtle/50 transition-colors"
                onClick={() => toggleStage(stage.id)}
              >
                <div className="flex items-start justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${stageStatusColor(stage.status)} ring-2 ring-chatBgAlt`} />
                    <h4 className="text-xs font-medium text-textPrimary">{stage.name}</h4>
                  </div>
                  <span className={`text-[9px] px-1.5 py-0.5 rounded font-medium ${
                    stage.status === 'active' ? 'bg-emerald-900/30 text-emerald-400' :
                    stage.status === 'idle' ? 'bg-slate-900/30 text-slate-400' :
                    'bg-amber-900/30 text-amber-400'
                  }`}>
                    {stage.status === 'active' ? '运行中' : stage.status === 'idle' ? '空闲' : '警告'}
                  </span>
                </div>
                <p className="text-[10px] text-textSecondary mb-1.5">{stage.description}</p>
                <div className="flex items-center gap-3 text-[9px] text-textSecondary">
                  <span>耗时: {stage.lastRuntime}ms</span>
                  <span>·</span>
                  <span className={stage.status === 'active' ? 'text-emerald-400' : ''}>
                    {stage.status === 'active' ? '● 活跃' : stage.status === 'idle' ? '○ 待机' : '⚠ 异常'}
                  </span>
                </div>
              </div>
            ))}

            {/* Pipeline Diagram (simplified) */}
            <div className="bg-chatBgAlt rounded-xl border border-borderSubtle/30 p-4 mt-3">
              <h4 className="text-[10px] font-medium text-textSecondary uppercase tracking-wider mb-2">处理流水线</h4>
              <div className="flex items-center justify-between text-[10px]">
                {stages.map((s, i) => (
                  <React.Fragment key={s.id}>
                    <div className={`px-2 py-1 rounded border text-center ${
                      s.status === 'active' ? 'border-emerald-500/50 bg-emerald-900/10 text-emerald-400' :
                      s.status === 'idle' ? 'border-slate-500/50 bg-slate-900/10 text-slate-400' :
                      'border-amber-500/50 bg-amber-900/10 text-amber-400'
                    }`}>
                      {s.name.replace(' ', '\n')}
                    </div>
                    {i < stages.length - 1 && (
                      <div className="text-textSecondary/40">→</div>
                    )}
                  </React.Fragment>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'logs' && (
          <div className="space-y-2">
            {logs.map(entry => (
              <div
                key={entry.id}
                className="bg-chatBgAlt rounded-lg border border-borderSubtle/30 p-3"
              >
                <div className="flex items-start justify-between mb-1">
                  <div className="flex items-center gap-2">
                    {resultBadge(entry.result)}
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-900/30 text-violet-400 font-medium">
                      {entry.gEgoMode === 'afferent' ? 'Afferent' : entry.gEgoMode === 'efferent' ? 'Efferent' : 'None'}
                    </span>
                  </div>
                  <span className="text-[10px] text-textSecondary">{formatTime(entry.timestamp)}</span>
                </div>
                <div className="flex items-center gap-3 text-[10px] text-textSecondary mb-1">
                  <span>ℐ-Scene: <span className={`font-medium ${
                    entry.iScene > 0.5 ? 'text-emerald-400' : entry.iScene > 0.15 ? 'text-amber-400' : 'text-red-400'
                  }`}>{entry.iScene.toFixed(4)}</span>
                  <span>·</span>
                  <span>阶段: {entry.stagesRun.length}/4</span>
                </div>
                <div className="flex flex-wrap gap-1">
                  {entry.stagesRun.map(s => (
                    <span key={s} className="text-[9px] px-1 py-0.5 rounded bg-chatBg text-textSecondary">
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
