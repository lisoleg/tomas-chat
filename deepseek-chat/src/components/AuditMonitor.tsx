import React, { useState } from 'react';

// ── Types ──────────────────────────────────────────────

type AuditStatus = 'ALLOW' | 'REJECT' | 'MUS_ACTIVE' | 'WARN_UNGROUNDED' | 'NEEDS_HUMAN';

interface AuditRecord {
  id: string;
  timestamp: Date;
  hypothesis: string;
  iValue: number;
  status: AuditStatus;
  reason: string;
  musPairs?: string[];
}

interface SpatialAuditItem {
  id: string;
  object: string;
  position: [number, number, number];
  grounded: boolean;
  deadZero: boolean;
  supportedBy?: string;
  antonymAlert?: string;
}

// ── Mock Data ──────────────────────────────────────────

function generateMockAudits(): AuditRecord[] {
  const base = Date.now();
  return [
    { id: 'a1', timestamp: new Date(base - 60000), hypothesis: '量子纠缠是超距作用', iValue: 0.72, status: 'ALLOW', reason: 'ℐ=0.72 > θ_dead=0.15, 证据链充足' },
    { id: 'a2', timestamp: new Date(base - 180000), hypothesis: '牛顿是科学家', iValue: 0.45, status: 'MUS_ACTIVE', reason: '悖论检测: 牛顿=科学家 ∧ 牛顿=炼金术士', musPairs: ['科学家', '炼金术士'] },
    { id: 'a3', timestamp: new Date(base - 300000), hypothesis: '意识存在于量子层面', iValue: 0.08, status: 'REJECT', reason: '[DEAD_ZERO_REJECT] ℐ=0.08 < θ_dead=0.15, 无可靠证据' },
    { id: 'a4', timestamp: new Date(base - 420000), hypothesis: '心主神明', iValue: 0.55, status: 'MUS_ACTIVE', reason: 'MUS 跨概念对: (心,神明) ⊗ (脑,神明)', musPairs: ['心→神明', '脑→神明'] },
    { id: 'a5', timestamp: new Date(base - 540000), hypothesis: 'DNA双螺旋结构', iValue: 0.88, status: 'ALLOW', reason: 'ℐ=0.88, 实证充分, 无矛盾' },
    { id: 'a6', timestamp: new Date(base - 660000), hypothesis: 'AI在未来5年达到AGI', iValue: 0.12, status: 'REJECT', reason: '[DEAD_ZERO_REJECT] ℐ=0.12, 推测性陈述, 无EML支撑' },
    { id: 'a7', timestamp: new Date(base - 780000), hypothesis: '光子无静止质量', iValue: 0.91, status: 'ALLOW', reason: 'ℐ=0.91, 物理定律级确认' },
    { id: 'a8', timestamp: new Date(base - 900000), hypothesis: '人类自由意志是幻觉', iValue: 0.18, status: 'WARN_UNGROUNDED', reason: 'ℐ=0.18 > θ_dead, 但证据源 UNGROUNDED' },
  ];
}

function generateMockSpatialAudits(): SpatialAuditItem[] {
  return [
    { id: 's1', object: '地板', position: [0, -2, 0], grounded: true, deadZero: false },
    { id: 's2', object: '沙发', position: [0, -1, 2], grounded: true, deadZero: false, supportedBy: '地板' },
    { id: 's3', object: '茶几', position: [0, -1.2, 0.5], grounded: true, deadZero: false, supportedBy: '地板' },
    { id: 's4', object: '浮空球', position: [0, 0.8, 1], grounded: false, deadZero: true },
    { id: 's5', object: '花瓶', position: [0, -1.1, 0.5], grounded: true, deadZero: true, antonymAlert: '陶器→易碎, 地面→坚硬 → MUS' },
  ];
}

// ── Component ──────────────────────────────────────────

export default function AuditMonitor() {
  const [audits] = useState<AuditRecord[]>(generateMockAudits());
  const [spatialAudits] = useState<SpatialAuditItem[]>(generateMockSpatialAudits());
  const [activeTab, setActiveTab] = useState<'tproc' | 'spatial' | 'gego'>('tproc');
  const [expandedLog, setExpandedLog] = useState<string | null>(null);

  const statusBadge = (s: AuditStatus) => {
    const map: Record<AuditStatus, { bg: string; text: string }> = {
      ALLOW: { bg: 'bg-emerald-900/30', text: 'text-emerald-400' },
      REJECT: { bg: 'bg-red-900/30', text: 'text-red-400' },
      MUS_ACTIVE: { bg: 'bg-amber-900/30', text: 'text-amber-400' },
      WARN_UNGROUNDED: { bg: 'bg-orange-900/30', text: 'text-orange-400' },
      NEEDS_HUMAN: { bg: 'bg-purple-900/30', text: 'text-purple-400' },
    };
    const style = map[s];
    return <span className={`text-[10px] px-1.5 py-0.5 rounded ${style.bg} ${style.text} font-medium`}>{s}</span>;
  };

  const statusLabel = (s: AuditStatus) => {
    const map: Record<AuditStatus, string> = {
      ALLOW: '放行', REJECT: '拒绝', MUS_ACTIVE: 'MUS', WARN_UNGROUNDED: '悬空', NEEDS_HUMAN: '需人工',
    };
    return map[s];
  };

  const allowed = audits.filter(a => a.status === 'ALLOW').length;
  const rejected = audits.filter(a => a.status === 'REJECT').length;
  const musActive = audits.filter(a => a.status === 'MUS_ACTIVE').length;

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-4 md:px-6 pt-4 pb-2">
        <h1 className="text-xl font-semibold text-textPrimary">审计监控</h1>
        <p className="text-sm text-textSecondary mt-1">
          T-Proc 死零审计 · 空间物理接地 · G_ego 日志
        </p>
      </div>

      {/* Summary Cards */}
      <div className="px-4 md:px-6 pb-3">
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-chatBgAlt rounded-xl border border-borderSubtle/30 p-3 text-center">
            <p className="text-2xl font-bold text-emerald-400">{allowed}</p>
            <p className="text-[10px] text-textSecondary mt-0.5">放行</p>
          </div>
          <div className="bg-chatBgAlt rounded-xl border border-borderSubtle/30 p-3 text-center">
            <p className="text-2xl font-bold text-red-400">{rejected}</p>
            <p className="text-[10px] text-textSecondary mt-0.5">拒绝</p>
          </div>
          <div className="bg-chatBgAlt rounded-xl border border-borderSubtle/30 p-3 text-center">
            <p className="text-2xl font-bold text-amber-400">{musActive}</p>
            <p className="text-[10px] text-textSecondary mt-0.5">MUS</p>
          </div>
        </div>
      </div>

      {/* Tab Bar */}
      <div className="px-4 md:px-6">
        <div className="flex border-b border-borderSubtle/30">
          {[
            { key: 'tproc', label: 'T-Proc 审计' },
            { key: 'spatial', label: '空间死零' },
            { key: 'gego', label: 'G_ego 日志' },
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
        {activeTab === 'tproc' && (
          <div className="space-y-2">
            {audits.map(audit => (
              <div
                key={audit.id}
                className="bg-chatBgAlt rounded-lg border border-borderSubtle/30 p-3"
              >
                <div className="flex items-start justify-between mb-1">
                  <p className="text-sm text-textPrimary font-medium truncate flex-1 mr-2">
                    "{audit.hypothesis}"
                  </p>
                  {statusBadge(audit.status)}
                </div>
                <p className="text-xs text-textSecondary mb-2">{audit.reason}</p>
                <div className="flex items-center gap-3 text-[10px] text-textSecondary">
                  <span>ℐ: <span className="text-textPrimary">{audit.iValue.toFixed(2)}</span></span>
                  <span>{formatTime(audit.timestamp)}</span>
                  {audit.musPairs && (
                    <span className="text-amber-400">
                      MUS: {audit.musPairs.join(' ⊗ ')}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'spatial' && (
          <div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mb-4">
              {spatialAudits.map(item => (
                <div
                  key={item.id}
                  className={`rounded-lg border p-3 ${
                    item.deadZero
                      ? 'bg-red-900/10 border-red-900/30'
                      : item.grounded
                      ? 'bg-emerald-900/10 border-emerald-900/30'
                      : 'bg-amber-900/10 border-amber-900/30'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium text-textPrimary">{item.object}</span>
                    {item.deadZero ? (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-900/30 text-red-400">死零</span>
                    ) : item.grounded ? (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-900/30 text-emerald-400">接地</span>
                    ) : (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-900/30 text-amber-400">悬浮</span>
                    )}
                  </div>
                  <div className="text-[10px] text-textSecondary space-y-0.5">
                    <p>位置: ({item.position.map(v => v.toFixed(1)).join(', ')})</p>
                    {item.supportedBy && <p>支撑: {item.supportedBy}</p>}
                    {item.antonymAlert && <p className="text-amber-400">⚠ {item.antonymAlert}</p>}
                  </div>
                </div>
              ))}
            </div>
            <div className="bg-chatBgAlt rounded-xl border border-borderSubtle/30 p-4">
              <h3 className="text-sm font-medium text-textPrimary mb-2">空间 MUS 词典</h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {[
                  ['开 ↔ 闭', 'open ↔ closed'],
                  ['透明 ↔ 不透明', 'transparent ↔ opaque'],
                  ['安全 ↔ 危险', 'safe ↔ dangerous'],
                  ['热 ↔ 冷', 'hot ↔ cold'],
                  ['硬 ↔ 软', 'hard ↔ soft'],
                  ['光 ↔ 暗', 'light ↔ dark'],
                  ['静 ↔ 动', 'static ↔ dynamic'],
                  ['满 ↔ 空', 'full ↔ empty'],
                ].map(([cn, en]) => (
                  <div key={cn} className="text-[10px] text-textSecondary bg-chatBg rounded px-2 py-1.5">
                    <span className="text-textPrimary">{cn.split('↔')[0]}</span>
                    <span className="mx-1 text-accent">↔</span>
                    <span className="text-textPrimary">{cn.split('↔')[1]}</span>
                    <span className="block text-[9px] text-textSecondary/60">{en}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'gego' && (
          <div className="space-y-2">
            {audits.map(audit => (
              <div key={audit.id} className="bg-chatBgAlt rounded-lg border border-borderSubtle/30 overflow-hidden">
                <button
                  onClick={() => setExpandedLog(expandedLog === audit.id ? null : audit.id)}
                  className="w-full p-3 text-left flex items-center justify-between hover:bg-chatBg/50 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <span className={`w-1.5 h-1.5 rounded-full ${
                      audit.status === 'ALLOW' ? 'bg-emerald-400' :
                      audit.status === 'REJECT' ? 'bg-red-400' :
                      audit.status === 'MUS_ACTIVE' ? 'bg-amber-400' : 'bg-slate-400'
                    }`} />
                    <span className="text-xs text-textPrimary truncate max-w-[300px]">{audit.hypothesis}</span>
                    <span className="text-[10px] text-textSecondary">{statusLabel(audit.status)}</span>
                  </div>
                  <span className="text-textSecondary text-xs">{expandedLog === audit.id ? '▲' : '▼'}</span>
                </button>
                {expandedLog === audit.id && (
                  <div className="border-t border-borderSubtle/20 px-3 py-2 bg-chatBg/50">
                    <div className="text-[10px] font-mono text-textSecondary space-y-1">
                      <p>timestamp: {audit.timestamp.toISOString()}</p>
                      <p>hypothesis: "{audit.hypothesis}"</p>
                      <p>i_value: {audit.iValue}</p>
                      <p>theta_dead: 0.15</p>
                      <p>status: {audit.status}</p>
                      <p>reason: {audit.reason}</p>
                      {audit.musPairs && <p>mus_pairs: [{audit.musPairs.join(', ')}]</p>}
                      <p>trace_id: gego_{audit.id}_{Date.now()}</p>
                    </div>
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

function formatTime(date: Date): string {
  const diff = Date.now() - date.getTime();
  if (diff < 60000) return '刚刚';
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h`;
  return date.toLocaleDateString('zh-CN');
}
