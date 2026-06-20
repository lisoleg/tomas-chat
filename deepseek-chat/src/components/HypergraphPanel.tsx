import React, { useState, useEffect, useCallback } from 'react';
import { IconGraph, IconDatabase, IconCpu, IconDownload, IconRefresh } from './icons';

// ── Types ─────────────────────────────────────

interface HypergraphStats {
  vertexCount: number;
  edgeCount: number;
  numShards: number;
  cacheHitRate: number;
}

interface SubgraphVertex {
  vid: number;
  concept: string;
  i_val: number;
}

interface SubgraphEdge {
  eid: number;
  nodes: number[];
  i_val: number;
  edge_type?: string;
}

interface SubgraphResult {
  vertices: SubgraphVertex[];
  edges: SubgraphEdge[];
}

interface MatroidResult {
  base: { eid: number; i_val: number; nodes: number[] }[];
  stats: { original_count: number; pruned_count: number; compression_ratio: number; mus_circuits: number; paradox_circuits: number };
  algorithm: string;
}

interface ShardInfo {
  shard_id: number;
  vertex_count: number;
  edge_count: number;
  ftel: number;
  state: string;
}

// ── API helpers ─────────────────────────────────────

const API = import.meta.env.PROD ? '' : 'http://localhost:5000';

async function apiFetch(path: string, options?: RequestInit) {
  const res = await fetch(`${API}${path}`, options);
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

// ── Component ─────────────────────────────────────

export default function HypergraphPanel() {
  const [activeTab, setActiveTab] = useState<'overview' | 'khop' | 'matroid' | 'distributed' | 'export'>('overview');
  const [stats, setStats] = useState<HypergraphStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // k-hop query state
  const [seeds, setSeeds] = useState('');
  const [kHop, setKHop] = useState(2);
  const [kHopResult, setKHopResult] = useState<SubgraphResult | null>(null);
  const [kHopLoading, setKHopLoading] = useState(false);

  // matroid state
  const [matroidSeeds, setMatroidSeeds] = useState('');
  const [matroidResult, setMatroidResult] = useState<MatroidResult | null>(null);
  const [matroidLoading, setMatroidLoading] = useState(false);

  // distributed state
  const [distSeeds, setDistSeeds] = useState('');
  const [distResult, setDistResult] = useState<any>(null);
  const [distLoading, setDistLoading] = useState(false);
  const [shardInfos, setShardInfos] = useState<ShardInfo[]>([]);

  // export state
  const [exportConcept, setExportConcept] = useState('');
  const [exportK, setExportK] = useState(2);
  const [exportResult, setExportResult] = useState<any>(null);
  const [exportLoading, setExportLoading] = useState(false);

  // load overview stats
  const loadStats = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [vRes, eRes, shardRes] = await Promise.all([
        apiFetch('/api/hypergraph/vertices?limit=1'),
        apiFetch('/api/hypergraph/hyperedges?limit=1'),
        apiFetch('/api/hypergraph/distributed/shards').catch(() => ({ success: true, data: { total_vertices: 0, total_edges: 0, num_shards: 0 } })),
      ]);
      setStats({
        vertexCount: vRes.total || 0,
        edgeCount: eRes.total || 0,
        numShards: shardRes.data?.num_shards || 0,
        cacheHitRate: 0,
      });
      if (shardRes.data?.shards) {
        setShardInfos(Object.values(shardRes.data.shards));
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadStats(); }, [loadStats]);

  // ── k-hop query ──
  const runKHop = async () => {
    if (!seeds.trim()) return;
    setKHopLoading(true);
    setError(null);
    try {
      const seedList = seeds.split(/[,\n]/).map(s => s.trim()).filter(Boolean);
      const res = await apiFetch('/api/hypergraph/k-hop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ seeds: seedList, k: kHop }),
      });
      if (res.success) {
        setKHopResult(res.data);
      } else {
        setError(res.error || 'k-hop query failed');
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setKHopLoading(false);
    }
  };

  // ── matroid pruning ──
  const runMatroid = async () => {
    if (!matroidSeeds.trim()) return;
    setMatroidLoading(true);
    setError(null);
    try {
      const seedList = matroidSeeds.split(/[,\n]/).map(s => s.trim()).filter(Boolean);
      // first get vids by concept names
      const vRes = await apiFetch(`/api/hypergraph/vertices?limit=200`);
      const vids = vRes.data
        ?.filter((v: any) => seedList.some((s: string) => v.concept.includes(s)))
        ?.map((v: any) => v.vid) || [];
      if (vids.length === 0) {
        setError('No matching vertices found for: ' + matroidSeeds);
        setMatroidLoading(false);
        return;
      }
      const res = await apiFetch('/api/hypergraph/matroid-unionfind', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vids }),
      });
      if (res.success) {
        setMatroidResult(res.data);
      } else {
        setError(res.error || 'matroid query failed');
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setMatroidLoading(false);
    }
  };

  // ── distributed query ──
  const runDistributed = async () => {
    if (!distSeeds.trim()) return;
    setDistLoading(true);
    setError(null);
    try {
      const seedList = distSeeds.split(/[,\n]/).map(s => s.trim()).filter(Boolean);
      const res = await apiFetch('/api/hypergraph/distributed/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ seeds: seedList, k: 2 }),
      });
      if (res.success) {
        setDistResult(res.data);
      } else {
        setError(res.error || 'distributed query failed');
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setDistLoading(false);
    }
  };

  // ── EML v2.0 export ──
  const runExport = async () => {
    if (!exportConcept.trim()) return;
    setExportLoading(true);
    setError(null);
    try {
      const res = await apiFetch('/api/hypergraph/export-eml-v2', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ concept: exportConcept, k: exportK }),
      });
      if (res.success) {
        setExportResult(res.data);
      } else {
        setError(res.error || 'export failed');
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setExportLoading(false);
    }
  };

  // ── Render ──

  const tabClass = (tab: string) =>
    `px-3 py-1.5 rounded text-xs font-medium cursor-pointer transition-colors ${
      activeTab === tab
        ? 'bg-cyan-600 text-white'
        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
    }`;

  return (
    <div className="flex flex-col h-full bg-gray-900 text-gray-100 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700 flex-shrink-0">
        <div className="flex items-center gap-2">
          <IconGraph className="w-5 h-5 text-cyan-400" />
          <h2 className="text-sm font-semibold text-gray-100">超图数据库 v2.0</h2>
        </div>
        <button
          onClick={loadStats}
          className="p-1.5 rounded hover:bg-gray-700 text-gray-400 hover:text-gray-200"
          title="刷新统计"
        >
          <IconRefresh className="w-4 h-4" />
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="mx-4 mt-2 p-2 bg-red-900/50 border border-red-700 rounded text-xs text-red-300">
          {error}
        </div>
      )}

      {/* Stats bar */}
      <div className="flex gap-3 px-4 py-2 border-b border-gray-700 flex-shrink-0 overflow-x-auto">
        <StatCard label="顶点" value={stats ? stats.vertexCount.toLocaleString() : '...'} color="cyan" />
        <StatCard label="超边" value={stats ? stats.edgeCount.toLocaleString() : '...'} color="purple" />
        <StatCard label="分片" value={stats ? String(stats.numShards) : '...'} color="green" />
        <StatCard label="缓存命中" value={stats ? stats.cacheHitRate.toFixed(1) + '%' : '...'} color="yellow" />
      </div>

      {/* Tabs */}
      <div className="flex gap-2 px-4 py-2 border-b border-gray-700 flex-shrink-0">
        <button className={tabClass('overview')} onClick={() => setActiveTab('overview')}>总览</button>
        <button className={tabClass('khop')} onClick={() => setActiveTab('khop')}>k-hop 查询</button>
        <button className={tabClass('matroid')} onClick={() => setActiveTab('matroid')}>拟阵剪枝</button>
        <button className={tabClass('distributed')} onClick={() => setActiveTab('distributed')}>分布式</button>
        <button className={tabClass('export')} onClick={() => setActiveTab('export')}>EML v2.0</button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {activeTab === 'overview' && (
          <OverviewTab
            stats={stats}
            loading={loading}
            shardInfos={shardInfos}
            onRefresh={loadStats}
          />
        )}
        {activeTab === 'khop' && (
          <KHopTab
            seeds={seeds}
            setSeeds={setSeeds}
            kHop={kHop}
            setKHop={setKHop}
            result={kHopResult}
            loading={kHopLoading}
            onRun={runKHop}
          />
        )}
        {activeTab === 'matroid' && (
          <MatroidTab
            seeds={matroidSeeds}
            setSeeds={setMatroidSeeds}
            result={matroidResult}
            loading={matroidLoading}
            onRun={runMatroid}
          />
        )}
        {activeTab === 'distributed' && (
          <DistributedTab
            seeds={distSeeds}
            setSeeds={setDistSeeds}
            result={distResult}
            loading={distLoading}
            onRun={runDistributed}
            shardInfos={shardInfos}
          />
        )}
        {activeTab === 'export' && (
          <ExportTab
            concept={exportConcept}
            setConcept={setExportConcept}
            k={exportK}
            setK={setExportK}
            result={exportResult}
            loading={exportLoading}
            onRun={runExport}
          />
        )}
      </div>
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────

function StatCard({ label, value, color }: { label: string; value: string; color: string }) {
  const colorMap: Record<string, string> = {
    cyan: 'text-cyan-400 bg-cyan-900/30',
    purple: 'text-purple-400 bg-purple-900/30',
    green: 'text-green-400 bg-green-900/30',
    yellow: 'text-yellow-400 bg-yellow-900/30',
  };
  return (
    <div className={`flex-1 min-w-[100px] rounded-lg p-2 ${colorMap[color] || colorMap.cyan}`}>
      <div className="text-[10px] uppercase tracking-wider opacity-70">{label}</div>
      <div className="text-lg font-bold mt-0.5">{value}</div>
    </div>
  );
}

// ── Overview Tab ──

function OverviewTab({ stats, loading, shardInfos, onRefresh }: any) {
  return (
    <div className="space-y-4">
      <div className="text-xs text-gray-400">
        HyperIndex v2.0 · UnionFind 拟阵 · 分布式超图 · EML v2.0 n元超边
      </div>
      <div className="bg-gray-800 rounded-lg p-3">
        <h3 className="text-xs font-semibold text-gray-300 mb-2">系统能力</h3>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <CapabilityItem label="HyperIndex v2.0" desc="LRU 缓存 + 批量预取，消除 N+1 查询" />
          <CapabilityItem label="UnionFind 拟阵" desc="O(|E|·α) 回路检测，替代 O(|E|²)" />
          <CapabilityItem label="分布式超图" desc="ChainDB RelationIndex + HyperShard" />
          <CapabilityItem label="EML v2.0" desc="n元超边二进制格式，向后兼容 v1.0" />
        </div>
      </div>
      {shardInfos.length > 0 && (
        <div className="bg-gray-800 rounded-lg p-3">
          <h3 className="text-xs font-semibold text-gray-300 mb-2">分片状态</h3>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500">
                <th className="text-left p-1">分片</th>
                <th className="text-right p-1">顶点</th>
                <th className="text-right p-1">超边</th>
                <th className="text-right p-1">Ftel</th>
                <th className="text-left p-1">状态</th>
              </tr>
            </thead>
            <tbody>
              {shardInfos.map((s: any) => (
                <tr key={s.shard_id} className="border-t border-gray-700">
                  <td className="p-1 text-cyan-400">shard_{s.shard_id}</td>
                  <td className="p-1 text-right text-gray-300">{s.vertex_count?.toLocaleString() || 0}</td>
                  <td className="p-1 text-right text-gray-300">{s.edge_count?.toLocaleString() || 0}</td>
                  <td className="p-1 text-right text-gray-300">{s.ftel?.toFixed(2) || '0.00'}</td>
                  <td className="p-1">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                      s.state === 'intelligent' ? 'bg-green-900/50 text-green-400' :
                      s.state === 'transitioning' ? 'bg-yellow-900/50 text-yellow-400' :
                      'bg-gray-700 text-gray-400'
                    }`}>
                      {s.state || 'unknown'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="bg-gray-800 rounded-lg p-3">
        <h3 className="text-xs font-semibold text-gray-300 mb-2">API 端点</h3>
        <div className="space-y-1 text-xs font-mono">
          <EndpointRow method="POST" path="/api/hypergraph/k-hop" desc="HyperIndex v2.0 k-hop 子图" />
          <EndpointRow method="POST" path="/api/hypergraph/matroid-unionfind" desc="UnionFind 拟阵剪枝" />
          <EndpointRow method="POST" path="/api/hypergraph/distributed/query" desc="分布式跨分片查询" />
          <EndpointRow method="GET" path="/api/hypergraph/distributed/shards" desc="分片状态查询" />
          <EndpointRow method="POST" path="/api/hypergraph/export-eml-v2" desc="导出 EML v2.0 文件" />
        </div>
      </div>
    </div>
  );
}

function CapabilityItem({ label, desc }: { label: string; desc: string }) {
  return (
    <div className="bg-gray-750 rounded p-2">
      <div className="text-cyan-400 font-medium">{label}</div>
      <div className="text-gray-500 mt-0.5">{desc}</div>
    </div>
  );
}

function EndpointRow({ method, path, desc }: { method: string; path: string; desc: string }) {
  const methodColor = method === 'GET' ? 'text-green-400' : 'text-blue-400';
  return (
    <div className="flex items-center gap-2">
      <span className={`${methodColor} font-bold w-10`}>{method}</span>
      <span className="text-gray-400">{path}</span>
      <span className="text-gray-500 ml-auto">{desc}</span>
    </div>
  );
}

// ── k-hop Tab ──

function KHopTab({ seeds, setSeeds, kHop, setKHop, result, loading, onRun }: any) {
  return (
    <div className="space-y-3">
      <div className="bg-gray-800 rounded-lg p-3 space-y-2">
        <div>
          <label className="block text-xs text-gray-400 mb-1">种子概念（逗号或换行分隔）</label>
          <textarea
            value={seeds}
            onChange={e => setSeeds(e.target.value)}
            placeholder={'例如：人工智能, 机器学习, 深度学习'}
            className="w-full h-16 bg-gray-900 border border-gray-700 rounded p-2 text-xs text-gray-200 resize-none focus:outline-none focus:border-cyan-600"
          />
        </div>
        <div className="flex items-center gap-3">
          <label className="text-xs text-gray-400">跳数 k:</label>
          <select
            value={kHop}
            onChange={e => setKHop(Number(e.target.value))}
            className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200"
          >
            {[1, 2, 3, 4, 5].map(k => <option key={k} value={k}>{k}</option>)}
          </select>
          <button
            onClick={onRun}
            disabled={loading || !seeds.trim()}
            className="ml-auto px-3 py-1.5 bg-cyan-700 hover:bg-cyan-600 disabled:bg-gray-700 disabled:text-gray-500 rounded text-xs font-medium text-white transition-colors"
          >
            {loading ? '查询中...' : '查询子图'}
          </button>
        </div>
      </div>

      {result && (
        <div className="bg-gray-800 rounded-lg p-3">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xs font-semibold text-gray-300">
              子图结果：{result.vertices?.length || 0} 顶点，{result.edges?.length || 0} 超边
            </h3>
          </div>
          {/* vertices list */}
          <div className="mb-2">
            <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">顶点</div>
            <div className="max-h-40 overflow-y-auto space-y-0.5">
              {(result.vertices || []).slice(0, 50).map((v: any) => (
                <div key={v.vid} className="flex items-center gap-2 text-xs bg-gray-900/50 rounded px-2 py-0.5">
                  <span className="text-cyan-400 w-10 text-right">{v.vid}</span>
                  <span className="text-gray-200 flex-1">{v.concept}</span>
                  <span className="text-yellow-400 text-[10px]">i={v.i_val?.toFixed(3)}</span>
                </div>
              ))}
            </div>
          </div>
          {/* edges list */}
          <div>
            <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">超边</div>
            <div className="max-h-40 overflow-y-auto space-y-0.5">
              {(result.edges || []).slice(0, 50).map((e: any) => (
                <div key={e.eid} className="flex items-center gap-2 text-xs bg-gray-900/50 rounded px-2 py-0.5">
                  <span className="text-purple-400 w-10 text-right">{e.eid}</span>
                  <span className="text-gray-300 flex-1">[{e.nodes?.join(', ')}]</span>
                  <span className="text-yellow-400 text-[10px]">i={e.i_val?.toFixed(3)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Matroid Tab ──

function MatroidTab({ seeds, setSeeds, result, loading, onRun }: any) {
  return (
    <div className="space-y-3">
      <div className="bg-gray-800 rounded-lg p-3 space-y-2">
        <div>
          <label className="block text-xs text-gray-400 mb-1">种子概念（用于定位顶点范围）</label>
          <textarea
            value={seeds}
            onChange={e => setSeeds(e.target.value)}
            placeholder={'例如：人工智能, 神经网络'}
            className="w-full h-16 bg-gray-900 border border-gray-700 rounded p-2 text-xs text-gray-200 resize-none focus:outline-none focus:border-cyan-600"
          />
        </div>
        <button
          onClick={onRun}
          disabled={loading || !seeds.trim()}
          className="px-3 py-1.5 bg-purple-700 hover:bg-purple-600 disabled:bg-gray-700 disabled:text-gray-500 rounded text-xs font-medium text-white transition-colors"
        >
          {loading ? '剪枝中...' : '运行 UnionFind 拟阵剪枝'}
        </button>
      </div>

      {result && (
        <div className="bg-gray-800 rounded-lg p-3 space-y-2">
          <h3 className="text-xs font-semibold text-gray-300">剪枝结果</h3>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <StatMini label="原始超边数" value={result.stats?.original_count || 0} />
            <StatMini label="剪枝后基数" value={result.stats?.pruned_count || 0} />
            <StatMini label="压缩比" value={(result.stats?.compression_ratio || 0).toFixed(3)} />
            <StatMini label="MUS 回路" value={result.stats?.mus_circuits || 0} />
          </div>
          <div className="text-[10px] text-gray-500 mt-1">算法：{result.algorithm}</div>
          {result.stats?.paradox_circuits > 0 && (
            <div className="text-xs text-yellow-400">Paradox 回路：{result.stats.paradox_circuits}</div>
          )}
          <div>
            <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">基 B（最大权独立集）</div>
            <div className="max-h-48 overflow-y-auto space-y-0.5">
              {(result.base || []).map((e: any) => (
                <div key={e.eid} className="flex items-center gap-2 text-xs bg-gray-900/50 rounded px-2 py-0.5">
                  <span className="text-purple-400 w-10 text-right">{e.eid}</span>
                  <span className="text-gray-300 flex-1">[{e.nodes?.join(', ')}]</span>
                  <span className="text-yellow-400 text-[10px]">i={e.i_val?.toFixed(3)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function StatMini({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="bg-gray-900/50 rounded p-2">
      <div className="text-[10px] text-gray-500">{label}</div>
      <div className="text-sm font-bold text-gray-200">{value}</div>
    </div>
  );
}

// ── Distributed Tab ──

function DistributedTab({ seeds, setSeeds, result, loading, onRun, shardInfos }: any) {
  return (
    <div className="space-y-3">
      <div className="bg-gray-800 rounded-lg p-3 space-y-2">
        <div>
          <label className="block text-xs text-gray-400 mb-1">种子概念（跨分片查询）</label>
          <textarea
            value={seeds}
            onChange={e => setSeeds(e.target.value)}
            placeholder={'例如：量子计算, 人工智能'}
            className="w-full h-16 bg-gray-900 border border-gray-700 rounded p-2 text-xs text-gray-200 resize-none focus:outline-none focus:border-cyan-600"
          />
        </div>
        <button
          onClick={onRun}
          disabled={loading || !seeds.trim()}
          className="px-3 py-1.5 bg-green-700 hover:bg-green-600 disabled:bg-gray-700 disabled:text-gray-500 rounded text-xs font-medium text-white transition-colors"
        >
          {loading ? '查询中...' : '分布式查询'}
        </button>
      </div>

      {result && (
        <div className="bg-gray-800 rounded-lg p-3">
          <h3 className="text-xs font-semibold text-gray-300 mb-2">
            分布式结果：{result.vertices?.length || 0} 顶点，{result.edges?.length || 0} 超边
          </h3>
          {result.fallback && (
            <div className="text-xs text-yellow-400 mb-2">{result.fallback}</div>
          )}
          {result.distributed_stats && (
            <div className="mb-2 text-xs text-gray-400">
              分片数：{result.distributed_stats.total_shards || '?'}，
              总顶点：{result.distributed_stats.total_vertices?.toLocaleString() || '?'}
            </div>
          )}
          <div className="max-h-60 overflow-y-auto space-y-0.5">
            {(result.vertices || []).slice(0, 100).map((v: any) => (
              <div key={v.vid} className="flex items-center gap-2 text-xs bg-gray-900/50 rounded px-2 py-0.5">
                <span className="text-cyan-400">{v.concept}</span>
                <span className="text-yellow-400 text-[10px] ml-auto">i={v.i_val?.toFixed(3)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Export Tab ──

function ExportTab({ concept, setConcept, k, setK, result, loading, onRun }: any) {
  const handleDownload = () => {
    if (!result?.data?.file) return;
    // In a real app, the backend would return a download URL
    alert('文件已生成：' + result.data.file + '\n大小：' + (result.data.size_bytes || 0) + ' 字节');
  };

  return (
    <div className="space-y-3">
      <div className="bg-gray-800 rounded-lg p-3 space-y-2">
        <div>
          <label className="block text-xs text-gray-400 mb-1">中心概念</label>
          <input
            value={concept}
            onChange={e => setConcept(e.target.value)}
            placeholder="例如：量子力学"
            className="w-full bg-gray-900 border border-gray-700 rounded p-2 text-xs text-gray-200 focus:outline-none focus:border-cyan-600"
          />
        </div>
        <div className="flex items-center gap-3">
          <label className="text-xs text-gray-400">k-hop 展开：</label>
          <select
            value={k}
            onChange={e => setK(Number(e.target.value))}
            className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200"
          >
            {[1, 2, 3, 4].map(kk => <option key={kk} value={kk}>{kk}</option>)}
          </select>
          <button
            onClick={onRun}
            disabled={loading || !concept.trim()}
            className="ml-auto px-3 py-1.5 bg-blue-700 hover:bg-blue-600 disabled:bg-gray-700 disabled:text-gray-500 rounded text-xs font-medium text-white transition-colors"
          >
            {loading ? '导出中...' : '导出 EML v2.0'}
          </button>
        </div>
      </div>

      {result && result.success && (
        <div className="bg-gray-800 rounded-lg p-3 space-y-2">
          <h3 className="text-xs font-semibold text-gray-300">导出成功 ✅</h3>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <StatMini label="顶点数" value={result.data?.vertices || 0} />
            <StatMini label="超边数" value={result.data?.edges || 0} />
            <StatMini label="格式" value={result.data?.format || 'EML v2.0'} />
            <StatMini label="文件大小" value={((result.data?.size_bytes || 0) / 1024).toFixed(1) + ' KB'} />
          </div>
          <button
            onClick={handleDownload}
            className="w-full mt-2 px-3 py-1.5 bg-blue-700 hover:bg-blue-600 rounded text-xs font-medium text-white flex items-center justify-center gap-1"
          >
            <IconDownload className="w-3.5 h-3.5" />
            下载 .eml2 文件
          </button>
        </div>
      )}
    </div>
  );
}
