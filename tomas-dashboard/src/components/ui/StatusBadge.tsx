type StatusType = 'online' | 'offline' | 'degraded' | 'unknown' | 'active' | 'standby';

const labels: Record<StatusType, string> = {
  online: '在线',
  offline: '离线',
  degraded: '降级',
  unknown: '未知',
  active: '活跃',
  standby: '待命',
};

const colors: Record<StatusType, string> = {
  online: 'bg-green-500/20 text-green-400',
  offline: 'bg-red-500/20 text-red-400',
  degraded: 'bg-yellow-500/20 text-yellow-400',
  unknown: 'bg-tomas-600/50 text-tomas-400',
  active: 'bg-green-500/20 text-green-400',
  standby: 'bg-tomas-600/50 text-tomas-400',
};

export default function StatusBadge({ status, label }: { status: StatusType; label?: string }) {
  return (
    <span className={`badge ${colors[status] || colors.unknown}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {label || labels[status] || status}
    </span>
  );
}
