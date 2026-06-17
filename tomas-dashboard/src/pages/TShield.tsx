import { useEffect } from 'react';
import { useTShieldStore } from '@/store/tshieldStore';
import Loading from '@/components/ui/Loading';

function RingGauge({ value, max, color, label, sub }: { value: number; max: number; color: string; label: string; sub: string }) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  const r = 48;
  const c = 2 * Math.PI * r;
  const dash = (pct / 100) * c;

  return (
    <div className="flex flex-col items-center">
      <svg width="140" height="140" viewBox="0 0 140 140">
        <circle cx="70" cy="70" r={r} fill="none" stroke="var(--bg-hover)" strokeWidth="8" />
        <circle cx="70" cy="70" r={r} fill="none" stroke={color} strokeWidth="8" strokeLinecap="round"
          strokeDasharray={`${dash} ${c}`} transform="rotate(-90 70 70)"
          style={{ transition: 'stroke-dasharray 0.8s ease' }} />
        <text x="70" y="62" textAnchor="middle" fill="var(--text-primary)" fontSize="22" fontWeight="bold">{pct}%</text>
        <text x="70" y="82" textAnchor="middle" fill="var(--text-muted)" fontSize="11">{value}/{max}</text>
      </svg>
      <span className="text-sm font-semibold mt-2" style={{ color: 'var(--text-primary)' }}>{label}</span>
      <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{sub}</span>
    </div>
  );
}

export default function TShield() {
  const { stats, loading, error, fetchStats } = useTShieldStore();

  useEffect(() => { fetchStats(); }, [fetchStats]);

  if (loading) return <Loading count={3} />;

  const s = stats || {
    dead_zone: { active: false, dead_count: 0, warning_count: 0, safe_count: 30, ratio: 0 },
    mus: { ambiguous_pairs: 0, total_boxes: 0, ratio: 0 },
    kappa_snap: { current_config: 'unknown', event_count: 0, latency_ms: 0 },
  };

  const totalDz = s.dead_zone.dead_count + s.dead_zone.warning_count + s.dead_zone.safe_count || 100;

  return (
    <div className="space-y-6">
      {error && (
        <div className="p-4 rounded-lg text-sm" style={{ background: 'rgba(239,68,68,0.1)', color: 'var(--accent-red)', border: '1px solid rgba(239,68,68,0.3)' }}>
          {error}
        </div>
      )}

      {/* Gauges */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="status-card flex justify-center" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
          <RingGauge value={s.dead_zone.dead_count} max={totalDz} color="var(--accent-red)" label="Dead-Zero" sub={`死零 ${s.dead_zone.dead_count} · 预警 ${s.dead_zone.warning_count}`} />
        </div>
        <div className="status-card flex justify-center" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
          <RingGauge value={s.mus.ambiguous_pairs} max={s.mus.total_boxes || 50} color="var(--accent-yellow)" label="MUS 仲裁" sub={`歧义 ${s.mus.ambiguous_pairs} 对`} />
        </div>
        <div className="status-card flex justify-center" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
          <RingGauge value={s.kappa_snap.event_count} max={200} color="var(--accent-purple)" label="κ-Snap" sub={`配置 ${s.kappa_snap.current_config} · ${s.kappa_snap.latency_ms}ms`} />
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-3">
        <button onClick={fetchStats} className="btn-primary">🔄 刷新数据</button>
        <span className="text-sm self-center" style={{ color: 'var(--text-muted)' }}>
          后端: GET /api/tshield/demo · POST /api/tshield/infer
        </span>
      </div>
    </div>
  );
}
