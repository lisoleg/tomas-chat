import type { SubsystemStatus } from '@/types';

const accentBorders: Record<string, string> = {
  blue: 'border-l-accent-blue',
  cyan: 'border-l-accent-cyan',
  green: 'border-l-accent-green',
  yellow: 'border-l-accent-yellow',
  red: 'border-l-accent-red',
  purple: 'border-l-accent-purple',
  orange: 'border-l-accent-orange',
};

export default function StatusCard({ name, label, status, health, description, accent }: SubsystemStatus) {
  const statusColors: Record<string, string> = {
    online: 'bg-green-500',
    offline: 'bg-red-500',
    degraded: 'bg-yellow-500',
    unknown: 'bg-tomas-600',
  };

  return (
    <div className={`status-card border-l-4 ${accentBorders[accent] || 'border-l-accent-blue'}`}
      style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold" style={{ color: 'var(--text-primary)' }}>{label}</h3>
        <span className={`w-2.5 h-2.5 rounded-full ${statusColors[status] || 'bg-gray-500'}`} />
      </div>
      <div className="flex items-baseline gap-2 mb-2">
        <span className="text-2xl font-bold" style={{ color: 'var(--accent-blue)' }}>{health}%</span>
        <span className="badge badge-info">{status === 'online' ? '正常' : status === 'degraded' ? '降级' : status === 'offline' ? '离线' : '未知'}</span>
      </div>
      <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>{description}</p>
    </div>
  );
}
