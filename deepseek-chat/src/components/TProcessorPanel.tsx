import React, { useState, useEffect } from 'react';
import { IconCpu, IconActivity, IconShield, IconClock } from './icons';

// ── Types ─────────────────────────────────────────────

interface ModuleStatus {
  name: string;
  id: string;
  status: 'active' | 'idle' | 'warning' | 'offline';
  utilization: number;  // 0-100%
  cycles: number;
}

interface TProcessorStats {
  totalCycles: number;
  deadZeroCount: number;
  musCount: number;
  snapCount: number;
  avgUtilization: number;
}

interface AuditLogEntry {
  id: string;
  timestamp: Date;
  module: string;
  event: string;
  status: 'pass' | 'fail' | 'warn';
  detail: string;
}

// ── Mock Data ─────────────────────────────────────────

function generateMockModules(): ModuleStatus[] {
  return [
    { name: 'RRAM Crossbar', id: 'rram', status: 'active', utilization: 78, cycles: 1420 },
    { name: 'DZ Comparator', id: 'dz_comp', status: 'active', utilization: 92, cycles: 1420 },
    { name: 'MUS Arbiter', id: 'mus_arb', status: 'idle', utilization: 34, cycles: 1380 },
    { name: 'κ-Snap Scheduler', id: 'kappa_snap', status: 'active', utilization: 61, cycles: 1420 },
  ];
}

function generateMockStats(): TProcessorStats {
  return {
    totalCycles: 1420,
    deadZeroCount: 47,
    musCount: 12,
    snapCount: 8,
    avgUtilization: 66.25,
  };
}

function generateMockAuditLogs(): AuditLogEntry[] {
  const base = Date.now();
  return [
    { id: 't1', timestamp: new Date(base - 30000), module: 'DZ Comparator', event: 'Dead-Zero 检测', status: 'pass', detail: 'ℐ=0.08 < θ_dead=0.15 → REJECT' },
    { id: 't2', timestamp: new Date(base - 90000), module: 'MUS Arbiter', event: 'MUS 仲裁', status: 'warn', detail: '悖论对: (科学家, 炼金术士) → 双存' },
    { id: 't3', timestamp: new Date(base - 150000), module: 'κ-Snap Scheduler', event: 'κ-Snap 调度', status: 'pass', detail: 'scene_complexity=0.72 → config=C' },
    { id: 't4', timestamp: new Date(base - 210000), module: 'RRAM Crossbar', event: '记忆路由', status: 'pass', detail: 'write: 128 cells, hit_rate=94%' },
    { id: 't5', timestamp: new Date(base - 300000), module: 'DZ Comparator', event: '批量比较', status: 'pass', detail: '32 values/cycle, latency=2.1μs' },
    { id: 't6', timestamp: new Date(base - 420000), module: 'T-Processor', event: '仿真启动', status: 'pass', detail: 'T-Processor v1.0 硬件仿真器初始化完成' },
    { id: 't7', timestamp: new Date(base - 600000), module: 'MUS Arbiter', event: '相似度计算', status: 'fail', detail: '相似度=0.97 > θ_mus=0.95 → 触发 MUS' },
    { id: 't8', timestamp: new Date(base - 900000), module: 'κ-Snap Scheduler', event: '配置切换', status: 'warn', detail: 'config: B → C, reason: complexity 跳变' },
  ];
}

// ── Component ──────────────────────────────────────────

export default function TProcessorPanel() {
  const [modules, setModules] = useState<ModuleStatus[]>(generateMockModules());
  const [stats] = useState<TProcessorStats>(generateMockStats());
  const [logs] = useState<AuditLogEntry[]>(generateMockAuditLogs());
  const [expandedLog, setExpandedLog] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'modules' | 'logs'>('overview');

  const statusColor = (s: ModuleStatus['status']) => {
    switch (s) {
      case 'active': return 'bg-emerald-500';
      case 'idle': return 'bg-slate-500';
      case 'warning': return 'bg-amber-500';
      case 'offline': return 'bg-red-500';
    }
  };

  const statusLabel = (s: ModuleStatus['status']) => {
    switch (s) {
      case 'active': return '运行中';
      case 'idle': return '空闲';
      case 'warning': return '警告';
      case 'offline': return '离线';
    }
  };

  const statusBadge = (status: AuditLogEntry['status']) => {
    const map: Record<AuditLogEntry['status'], { bg: string; text: string; label: string }> = {
      pass: { bg: 'bg-emerald-900/30', text: 'text-emerald-400', label: '通过' },
      fail: { bg: 'bg-red-900/30', text: 'text-red-400', label: '失败' },
      warn: { bg: 'bg-amber-900/30', text: 'text-amber-400', label: '警告' },
    };
    const style = map[status];
    return (
      <span className={`text-[10px] px-1.5 py-0.5 rounded ${style.bg} ${style.text} font-medium`}>
        {style.label}
      </span>
    );
  };

  function formatTime(d: Date): string {
    const diff = Date.now() - d.getTime();
    if (diff < 60000) return '刚刚';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`;
    return d.toLocaleDateString('zh-CN');
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-4 md:px-6 pt-4 pb-2">
        <h1 className="text-xl font-semibold text-textPrimary">T-Processor 硬件仿真器</h1>
        <p className="text-sm text-textSecondary mt-1">
          RRAM Crossbar · DZ Comparator · MUS Arbiter · κ-Snap Scheduler
        </p>
      </div>

      {/* Tab Bar */}
      <div className="px-4 md:px-6">
        <div className="flex border-b border-borderSubtle/30">
          {[
            { key: 'overview', label: '总览' },
            { key: 'modules', label: '硬件模块' },
            { key: 'logs', label: '审计日志' },
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
            {/* Stats Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="bg-chatBgAlt rounded-xl border border-borderSubtle/30 p-3 text-center">
                <p className="text-2xl font-bold text-accent">{stats.totalCycles}</p>
                <p className="text-[10px] text-textSecondary mt-0.5">总周期</p>
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
                <p className="text-2xl font-bold text-cyan-400">{stats.snapCount}</p>
                <p className="text-[10px] text-textSecondary mt-0.5">κ-Snap 切片</p>
              </div>
            </div>

            {/* Module Status Overview */}
            <div>
              <h3 className="text-xs font-medium text-textSecondary uppercase tracking-wider mb-2">硬件模块状态</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {modules.map(m => (
                  <div key={m.id} className="bg-chatBgAlt rounded-lg border border-borderSubtle/30 p-3 flex items-center gap-3">
                    <span className={`w-2 h-2 rounded-full ${statusColor(m.status)} ring-2 ring-chatBgAlt`} />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium text-textPrimary">{m.name}</p>
                      <p className="text-[10px] text-textSecondary">{statusLabel(m.status)} · 利用率 {m.utilization}% · {m.cycles} 周期</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Quick Info */}
            <div className="bg-chatBgAlt rounded-xl border border-borderSubtle/30 p-4">
              <h3 className="text-xs font-medium text-textSecondary uppercase tracking-wider mb-2">T-Processor v1.0 说明</h3>
              <div className="space-y-1.5 text-xs text-textSecondary leading-relaxed">
                <p>〈 <strong className="text-textPrimary">RRAM Crossbar</strong> — 记忆路由矩阵，128×128 单元，读写延迟 2.1μs</p>
                <p>〈 <strong className="text-textPrimary">DZ Comparator</strong> — 死零比较器阵列，32 值/周期并行比较</p>
                <p>〈 <strong className="text-textPrimary">MUS Arbiter</strong> — MUS 相似度仲裁器，DSP48E1 优化</p>
                <p>〈 <strong className="text-textPrimary">κ-Snap Scheduler</strong> — κ-快照调度器，4 档配置 (A/B/C/D)</p>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'modules' && (
          <div className="space-y-3">
            {modules.map(m => (
              <div key={m.id} className="bg-chatBgAlt rounded-xl border border-borderSubtle/30 p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className={`w-2.5 h-2.5 rounded-full ${statusColor(m.status)}`} />
                    <h3 className="text-sm font-medium text-textPrimary">{m.name}</h3>
                  </div>
                  {statusBadge(m.status === 'active' ? 'pass' : m.status === 'warning' ? 'warn' : 'fail')}
                </div>
                <div className="grid grid-cols-3 gap-3 mb-3">
                  <div className="bg-chatBg rounded-lg p-2 text-center">
                    <p className="text-lg font-bold text-accent">{m.utilization}%</p>
                    <p className="text-[9px] text-textSecondary">利用率</p>
                  </div>
                  <div className="bg-chatBg rounded-lg p-2 text-center">
                    <p className="text-lg font-bold text-textPrimary">{m.cycles}</p>
                    <p className="text-[9px] text-textSecondary">周期数</p>
                  </div>
                  <div className="bg-chatBg rounded-lg p-2 text-center">
                    <p className="text-lg font-bold text-emerald-400">{statusLabel(m.status)}</p>
                    <p className="text-[9px] text-textSecondary">状态</p>
                  </div>
                </div>
                {/* Utilization Bar */}
                <div className="w-full h-1.5 bg-chatBg rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      m.utilization > 80 ? 'bg-red-400' : m.utilization > 50 ? 'bg-amber-400' : 'bg-emerald-400'
                    }`}
                    style={{ width: `${m.utilization}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'logs' && (
          <div className="space-y-2">
            {logs.map(entry => (
              <div
                key={entry.id}
                className="bg-chatBgAlt rounded-lg border border-borderSubtle/30 p-3 cursor-pointer hover:border-borderSubtle/50 transition-colors"
                onClick={() => setExpandedLog(expandedLog === entry.id ? null : entry.id)}
              >
                <div className="flex items-start justify-between mb-1">
                  <p className="text-xs text-textPrimary font-medium truncate flex-1 mr-2">
                    [{entry.module}] {entry.event}
                  </p>
                  {statusBadge(entry.status)}
                </div>
                <p className="text-xs text-textSecondary mb-1.5">{entry.detail}</p>
                <p className="text-[10px] text-textSecondary">{formatTime(entry.timestamp)}</p>
                {expandedLog === entry.id && (
                  <div className="mt-2 pt-2 border-t border-borderSubtle/20 text-[10px] text-textSecondary font-mono bg-chatBg/50 rounded p-2">
                    id: {entry.id} · module: {entry.module} · status: {entry.status}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
