import { useState, useEffect, useCallback } from 'react';
import { useApi } from '@/hooks/useApi';
import { fetchKnowledgeSubjects } from '@/api/endpoints';
import type { MemoryRecord, KnowledgeTriple } from '@/types';
import Loading from '@/components/ui/Loading';
import EmptyState from '@/components/ui/EmptyState';

const MOCK_MEMORIES: MemoryRecord[] = [
  { id: 'm1', subject: '量子纠缠', predicate: 'is_a', object: '量子现象', timestamp: new Date().toISOString(), psi_anchor: 'ψ-001', mus_dual: false },
  { id: 'm2', subject: '贝尔不等式', predicate: 'refutes', object: '局域实在论', timestamp: new Date(Date.now() - 60000).toISOString(), psi_anchor: 'ψ-002', mus_dual: true },
  { id: 'm3', subject: '波函数', predicate: 'describes', object: '量子态', timestamp: new Date(Date.now() - 120000).toISOString(), psi_anchor: 'ψ-003', mus_dual: false },
  { id: 'm4', subject: '薛定谔方程', predicate: 'governs', object: '量子演化', timestamp: new Date(Date.now() - 180000).toISOString(), psi_anchor: 'ψ-004', mus_dual: true },
  { id: 'm5', subject: '自旋', predicate: 'property_of', object: '基本粒子', timestamp: new Date(Date.now() - 300000).toISOString(), psi_anchor: 'ψ-005', mus_dual: false },
];

export default function Memory() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<MemoryRecord[]>(MOCK_MEMORIES);
  const [selected, setSelected] = useState<MemoryRecord | null>(null);

  // Try API first, fallback to mock
  const { data: subjects, loading } = useApi<string[]>(
    () => fetchKnowledgeSubjects(query || undefined)
  );

  const handleSearch = useCallback(() => {
    const q = query.toLowerCase();
    setResults(MOCK_MEMORIES.filter(
      (m) => m.subject.toLowerCase().includes(q) || m.object.toLowerCase().includes(q) || m.predicate.toLowerCase().includes(q)
    ));
  }, [query]);

  useEffect(() => { if (query) handleSearch(); else setResults(MOCK_MEMORIES); }, [query, handleSearch]);

  return (
    <div className="space-y-6">
      {/* Search */}
      <div className="flex gap-3">
        <input
          type="text" value={query} onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          placeholder="搜索主体/谓词/客体..."
          className="flex-1 px-4 py-3 rounded-xl border outline-none text-sm"
          style={{ background: 'var(--bg-input)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
        />
        <button onClick={handleSearch} className="btn-primary">搜索</button>
      </div>

      {loading ? <Loading count={4} /> : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* List */}
          <div className="status-card max-h-[60vh] overflow-y-auto" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <h3 className="text-lg font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
              记忆记录 ({results.length})
            </h3>
            {results.length === 0 ? (
              <EmptyState icon="🔍" title="无匹配记录" />
            ) : (
              results.map((m) => (
                <div
                  key={m.id}
                  onClick={() => setSelected(m)}
                  className={`p-3 rounded-lg mb-2 cursor-pointer border transition-colors ${
                    selected?.id === m.id ? 'border-accent-blue' : 'hover:border-tomas-750'
                  }`}
                  style={{ background: 'var(--bg-hover)', borderColor: selected?.id === m.id ? 'var(--accent-blue)' : 'var(--border)' }}
                >
                  <div className="flex justify-between items-start">
                    <span className="font-medium text-sm" style={{ color: 'var(--text-primary)' }}>{m.subject}</span>
                    {m.mus_dual && <span className="badge badge-warning text-xs">MUS 双存</span>}
                  </div>
                  <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
                    {m.predicate} → {m.object}
                  </p>
                </div>
              ))
            )}
            {subjects && subjects.length > 0 && (
              <p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
                API 返回 {subjects.length} 个主体
              </p>
            )}
          </div>

          {/* Detail */}
          <div className="status-card" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <h3 className="text-lg font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>ψ-锚详情</h3>
            {selected ? (
              <div className="space-y-4">
                <div className="p-3 rounded-lg" style={{ background: 'var(--bg-hover)' }}>
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>锚点 ID</p>
                  <p className="font-mono text-sm" style={{ color: 'var(--accent-cyan)' }}>{selected.psi_anchor}</p>
                </div>
                <div className="p-3 rounded-lg" style={{ background: 'var(--bg-hover)' }}>
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>三元组</p>
                  <p className="text-sm" style={{ color: 'var(--text-primary)' }}>
                    <span style={{ color: 'var(--accent-blue)' }}>{selected.subject}</span>
                    {' '}—{selected.predicate}—{' '}
                    <span style={{ color: 'var(--accent-green)' }}>{selected.object}</span>
                  </p>
                </div>
                <div className="p-3 rounded-lg" style={{ background: 'var(--bg-hover)' }}>
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>MUS 双存储</p>
                  <p className="text-sm" style={{ color: selected.mus_dual ? 'var(--accent-yellow)' : 'var(--accent-green)' }}>
                    {selected.mus_dual ? '已激活 (歧义双存)' : '未激活 (确定性存储)'}
                  </p>
                </div>
                <div className="p-3 rounded-lg" style={{ background: 'var(--bg-hover)' }}>
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>时间戳</p>
                  <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>{new Date(selected.timestamp).toLocaleString('zh-CN')}</p>
                </div>
              </div>
            ) : (
              <EmptyState icon="👈" title="选择一条记忆记录" description="点击左侧记录查看 ψ-锚详情" />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
