import { useEffect } from 'react';
import StatusCard from '@/components/ui/StatusCard';
import Loading from '@/components/ui/Loading';
import { useDashboardStore } from '@/store/dashboardStore';

export default function Dashboard() {
  const { subsystems, timeline, loading, error, fetchData } = useDashboardStore();

  useEffect(() => { fetchData(); }, [fetchData]);

  if (loading) return <Loading count={8} />;

  if (error && subsystems.every((s) => s.status === 'unknown')) {
    return (
      <div className="text-center py-20" style={{ color: 'var(--accent-red)' }}>
        <p className="text-2xl mb-2">⚠️</p>
        <p>连接后端失败: {error}</p>
        <p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>请确保 server.py 已启动 (http://localhost:5000)</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Status Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {subsystems.map((sub) => (
          <StatusCard key={sub.name} {...sub} />
        ))}
      </div>

      {/* Timeline */}
      <div className="status-card" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
        <h2 className="text-lg font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>最近活动</h2>
        <div className="space-y-3">
          {timeline.map((event) => (
            <div key={event.id} className="flex items-start gap-3 pb-3 border-b" style={{ borderColor: 'var(--border)' }}>
              <span className={`w-2 h-2 mt-1.5 rounded-full flex-shrink-0 ${
                event.level === 'error' ? 'bg-red-500' : event.level === 'warning' ? 'bg-yellow-500' : 'bg-accent-blue'
              }`} />
              <div className="flex-1 min-w-0">
                <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>{event.event}</p>
                <div className="flex gap-3 mt-1">
                  <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    {new Date(event.timestamp).toLocaleTimeString('zh-CN')}
                  </span>
                  <span className="text-xs badge badge-muted">{event.source}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
