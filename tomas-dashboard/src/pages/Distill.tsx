import { useEffect } from 'react';
import { useApi } from '@/hooks/useApi';
import { fetchCorpus, fetchConflicts } from '@/api/endpoints';
import type { CorpusEntry, ConflictRecord } from '@/types';
import Loading from '@/components/ui/Loading';
import EmptyState from '@/components/ui/EmptyState';

export default function Distill() {
  const { data: corpus, loading: cl, error: ce } = useApi<CorpusEntry[]>(() => fetchCorpus() as ReturnType<typeof fetchCorpus>);
  const { data: conflicts, loading: cfl, error: cfe } = useApi<ConflictRecord[]>(() => fetchConflicts() as ReturnType<typeof fetchConflicts>);

  if (cl || cfl) return <Loading count={4} />;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Corpus */}
      <div className="status-card" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
        <h2 className="text-lg font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
          📚 语料库
          <span className="ml-2 text-sm font-normal" style={{ color: 'var(--text-muted)' }}>{(corpus || []).length} 条</span>
        </h2>
        {ce && <p className="text-red-400 text-sm">{ce}</p>}
        {(corpus || []).length === 0 ? (
          <EmptyState icon="📂" title="暂无语料" description="通过 POST /api/corpus 添加语料" />
        ) : (
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {(corpus || []).map((entry) => (
              <div key={entry.id} className="p-3 rounded-lg border" style={{ background: 'var(--bg-hover)', borderColor: 'var(--border)' }}>
                <div className="flex justify-between items-start">
                  <span className="font-medium text-sm" style={{ color: 'var(--text-primary)' }}>{entry.name}</span>
                  <span className="badge badge-info">{entry.domain}</span>
                </div>
                <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{entry.size} 字符 · {entry.created_at}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Conflicts */}
      <div className="status-card" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
        <h2 className="text-lg font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
          ⚡ 知识冲突
          <span className="ml-2 text-sm font-normal" style={{ color: 'var(--text-muted)' }}>{(conflicts || []).length} 条</span>
        </h2>
        {cfe && <p className="text-red-400 text-sm">{cfe}</p>}
        {(conflicts || []).length === 0 ? (
          <EmptyState icon="✅" title="无冲突" description="知识库一致" />
        ) : (
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {(conflicts || []).slice(0, 20).map((c) => (
              <div key={c.id} className="p-3 rounded-lg border" style={{ background: 'var(--bg-hover)', borderColor: 'var(--border)' }}>
                <div className="flex justify-between items-start">
                  <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                    {c.concept_a} ↔ {c.concept_b}
                  </span>
                  <span className="badge badge-warning">{(c.similarity * 100).toFixed(0)}%</span>
                </div>
                {c.resolution && <p className="text-xs mt-1" style={{ color: 'var(--accent-green)' }}>已解决: {c.resolution}</p>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
