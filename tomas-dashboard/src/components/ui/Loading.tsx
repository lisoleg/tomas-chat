export default function Loading({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="status-card animate-pulse" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
          <div className="h-4 w-2/3 rounded mb-3" style={{ background: 'var(--bg-hover)' }} />
          <div className="h-8 w-1/3 rounded mb-2" style={{ background: 'var(--bg-hover)' }} />
          <div className="h-3 w-4/5 rounded" style={{ background: 'var(--bg-hover)' }} />
        </div>
      ))}
    </div>
  );
}
