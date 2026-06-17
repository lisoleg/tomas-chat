import { useState } from 'react';
import { useApi } from '@/hooks/useApi';
import { fetchTProcessorStats } from '@/api/endpoints';
import type { TProcessorStats, AuditEvent } from '@/types';
import Loading from '@/components/ui/Loading';
import EmptyState from '@/components/ui/EmptyState';

function mockAuditEvents(): AuditEvent[] {
  return [
    { id: 'a1', timestamp: new Date().toISOString(), source: 'tproc', event: 'Dead-Zero 比较器触发：激活值 0.0003 低于阈值', severity: 'high' },
    { id: 'a2', timestamp: new Date(Date.now() - 120000).toISOString(), source: 'spatial', event: '空间一致性检查通过：ℐ=0.94', severity: 'low' },
    { id: 'a3', timestamp: new Date(Date.now() - 300000).toISOString(), source: 'g_ego', event: 'G_ego 自我审计：偏离基线 0.02', severity: 'medium' },
    { id: 'a4', timestamp: new Date(Date.now() - 600000).toISOString(), source: 'tproc', event: 'MUS 歧义仲裁：2 对歧义框已标记', severity: 'medium' },
    { id: 'a5', timestamp: new Date(Date.now() - 900000).toISOString(), source: 'spatial', event: '3D 空间验证：重力矢量一致性 OK', severity: 'low' },
  ];
}

const tabs = [
  { key: 'tproc' as const, label: 'T-Proc 死零审计' },
  { key: 'spatial' as const, label: 'Spatial Dead-Zero' },
  { key: 'g_ego' as const, label: 'G_ego 自审' },
];

export default function Audit() {
  const [activeTab, setActiveTab] = useState<'tproc' | 'spatial' | 'g_ego'>('tproc');
  const { data: stats, loading, error } = useApi<TProcessorStats>(() => fetchTProcessorStats() as ReturnType<typeof fetchTProcessorStats>);

  const events = mockAuditEvents().filter((e) => e.source === activeTab);
  const severityColors: Record<string, string> = {
    low: 'badge-info',
    medium: 'badge-warning',
    high: 'badge-danger',
    critical: 'text-white bg-red-600',
  };

  return (
    <div className="space-y-6">
      {/* Stats Bar */}
      {loading ? <Loading count={3} /> : stats && (
        <div className="grid grid-cols-3 gap-4">
          <div className="status-card text-center" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <p className="text-3xl font-bold" style={{ color: 'var(--accent-red)' }}>{stats.dead_zero_trigger_count}</p>
            <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>死零触发</p>
          </div>
          <div className="status-card text-center" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <p className="text-3xl font-bold" style={{ color: 'var(--accent-yellow)' }}>{stats.mus_arbitration_count}</p>
            <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>MUS 仲裁</p>
          </div>
          <div className="status-card text-center" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <p className="text-3xl font-bold" style={{ color: 'var(--accent-purple)' }}>{stats.kappa_snap_latency_ms}ms</p>
            <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>κ-Snap 延迟</p>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg p-1" style={{ background: 'var(--bg-hover)' }}>
        {tabs.map((t) => (
          <button key={t.key} onClick={() => setActiveTab(t.key)}
            className={`flex-1 py-2 text-sm rounded-md transition-colors ${
              activeTab === t.key ? 'font-semibold' : ''
            }`}
            style={{
              background: activeTab === t.key ? 'var(--bg-card)' : 'transparent',
              color: activeTab === t.key ? 'var(--text-primary)' : 'var(--text-muted)',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Event List */}
      {error && <p className="text-red-400 text-sm">{error}</p>}
      {events.length === 0 ? (
        <EmptyState icon="📋" title="无审计事件" />
      ) : (
        <div className="status-card space-y-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
          {events.map((e) => (
            <div key={e.id} className="flex items-start gap-3 p-2 rounded-lg" style={{ background: 'var(--bg-hover)' }}>
              <span className={`badge ${severityColors[e.severity] || 'badge-muted'} flex-shrink-0 mt-0.5`}>
                {e.severity.toUpperCase()}
              </span>
              <div className="min-w-0">
                <p className="text-sm" style={{ color: 'var(--text-primary)' }}>{e.event}</p>
                <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                  {new Date(e.timestamp).toLocaleString('zh-CN')}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
