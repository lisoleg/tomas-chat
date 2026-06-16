import React, { useState, useMemo } from 'react';

// ── Types ──────────────────────────────────────────────

interface MemoryRecord {
  id: string;
  concept: string;
  content: string;
  iValue: number;
  kappa: number;
  psiAnchor: {
    egoState: string;
    timestamp: Date;
    focus: string;
  };
  isMUS: boolean;
  musPartner?: string;
  dikwpLayer: 'Data' | 'Info' | 'Knowledge' | 'Wisdom' | 'Purpose';
  tags: string[];
}

// ── Mock Data ──────────────────────────────────────────

function generateMockMemories(): MemoryRecord[] {
  const now = Date.now();
  return [
    {
      id: 'm1', concept: '量子力学', content: '量子力学是描述微观粒子行为的物理学分支，核心概念包括波粒二象性、量子叠加和量子纠缠。', iValue: 0.82, kappa: 0.75,
      psiAnchor: { egoState: '专注学习', timestamp: new Date(now - 3600000), focus: '物理学' },
      isMUS: false, dikwpLayer: 'Knowledge', tags: ['物理', '量子'],
    },
    {
      id: 'm2', concept: '牛顿', content: '牛顿是英国物理学家、数学家，提出万有引力定律和三大运动定律，奠定了经典力学基础。', iValue: 0.78, kappa: 0.68,
      psiAnchor: { egoState: '专注学习', timestamp: new Date(now - 3600000), focus: '物理学' },
      isMUS: true, musPartner: '牛顿=炼金术士',
      dikwpLayer: 'Knowledge', tags: ['物理', '历史'],
    },
    {
      id: 'm3', concept: '牛顿=炼金术士', content: '牛顿晚年沉迷于炼金术和神学研究，留下了大量炼金术手稿，展现了他作为神秘主义者的另一面。', iValue: 0.65, kappa: 0.71,
      psiAnchor: { egoState: '批判性思维', timestamp: new Date(now - 5400000), focus: '历史' },
      isMUS: true, musPartner: '牛顿=科学家',
      dikwpLayer: 'Knowledge', tags: ['历史', '炼金术'],
    },
    {
      id: 'm4', concept: '心主神明', content: '中医理论认为心主神明，心为君主之官，神明出焉，主导人的精神意识和思维活动。', iValue: 0.55, kappa: 0.62,
      psiAnchor: { egoState: '传统文化探索', timestamp: new Date(now - 7200000), focus: '中医学' },
      isMUS: true, musPartner: '脑主神明',
      dikwpLayer: 'Wisdom', tags: ['中医', '哲学'],
    },
    {
      id: 'm5', concept: '脑主神明', content: '现代神经科学认为脑是意识和思维的物质基础，大脑皮层和海马体等结构负责认知功能。', iValue: 0.71, kappa: 0.58,
      psiAnchor: { egoState: '科学探索', timestamp: new Date(now - 9000000), focus: '神经科学' },
      isMUS: true, musPartner: '心主神明',
      dikwpLayer: 'Knowledge', tags: ['神经科学', '现代医学'],
    },
    {
      id: 'm6', concept: 'DNA双螺旋', content: 'DNA由两条反平行的多核苷酸链组成，通过碱基互补配对形成双螺旋结构。', iValue: 0.89, kappa: 0.82,
      psiAnchor: { egoState: '专注学习', timestamp: new Date(now - 10800000), focus: '生物学' },
      isMUS: false, dikwpLayer: 'Knowledge', tags: ['生物', '分子'],
    },
    {
      id: 'm7', concept: '熵增原理', content: '孤立系统的熵永不减少，热力学第二定律揭示了时间的方向性和不可逆性。', iValue: 0.85, kappa: 0.79,
      psiAnchor: { egoState: '深度思考', timestamp: new Date(now - 14400000), focus: '热力学' },
      isMUS: false, dikwpLayer: 'Wisdom', tags: ['物理', '热力学'],
    },
    {
      id: 'm8', concept: 'AI对齐问题', content: '确保AI系统的目标和行为与人类价值观保持一致，是AI安全研究的核心课题之一。', iValue: 0.48, kappa: 0.55,
      psiAnchor: { egoState: '前瞻思考', timestamp: new Date(now - 18000000), focus: 'AI伦理' },
      isMUS: false, dikwpLayer: 'Purpose', tags: ['AI', '伦理'],
    },
  ];
}

// ── Component ──────────────────────────────────────────

export default function MemoryBrowser() {
  const [memories] = useState<MemoryRecord[]>(generateMockMemories());
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filterMUS, setFilterMUS] = useState<boolean | null>(null);
  const [filterLayer, setFilterLayer] = useState<string | null>(null);

  const filtered = useMemo(() => {
    return memories.filter(m => {
      if (search && !m.concept.includes(search) && !m.content.includes(search) && !m.tags.some(t => t.includes(search))) return false;
      if (filterMUS !== null && m.isMUS !== filterMUS) return false;
      if (filterLayer && m.dikwpLayer !== filterLayer) return false;
      return true;
    });
  }, [memories, search, filterMUS, filterLayer]);

  const dikwpColors: Record<string, string> = {
    Data: '#f59e0b', Info: '#06b6d4', Knowledge: '#8b5cf6', Wisdom: '#ec4899', Purpose: '#10b981',
  };

  const selected = memories.find(m => m.id === selectedId);

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-4 md:px-6 pt-4 pb-2">
        <h1 className="text-xl font-semibold text-textPrimary">记忆浏览器</h1>
        <p className="text-sm text-textSecondary mt-1">
          MemOS 五点升维记忆 — {memories.length} 条记录, {memories.filter(m => m.isMUS).length} 组 MUS 双存
        </p>
      </div>

      {/* Filters */}
      <div className="px-4 md:px-6 pb-3 flex flex-wrap gap-2">
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="搜索概念/内容/标签..."
          className="flex-1 min-w-[200px] bg-chatBgAlt border border-borderSubtle/30 rounded-lg px-3 py-1.5 text-sm text-textPrimary placeholder-textSecondary focus:outline-none focus:border-accent/50"
        />
        <select
          value={filterMUS === null ? '' : filterMUS ? 'mus' : 'normal'}
          onChange={e => {
            const v = e.target.value;
            setFilterMUS(v === '' ? null : v === 'mus');
          }}
          className="bg-chatBgAlt border border-borderSubtle/30 rounded-lg px-2 py-1.5 text-xs text-textPrimary"
        >
          <option value="">全部类型</option>
          <option value="mus">MUS 双存</option>
          <option value="normal">普通记忆</option>
        </select>
        <select
          value={filterLayer || ''}
          onChange={e => setFilterLayer(e.target.value || null)}
          className="bg-chatBgAlt border border-borderSubtle/30 rounded-lg px-2 py-1.5 text-xs text-textPrimary"
        >
          <option value="">全部层级</option>
          {['Data', 'Info', 'Knowledge', 'Wisdom', 'Purpose'].map(l => (
            <option key={l} value={l}>{l}</option>
          ))}
        </select>
      </div>

      {/* Content: split view */}
      <div className="flex-1 overflow-hidden flex flex-col md:flex-row px-4 md:px-6 pb-4 gap-3">
        {/* List */}
        <div className="flex-1 overflow-y-auto space-y-1.5 min-h-0">
          {filtered.length === 0 ? (
            <div className="p-8 text-center text-textSecondary text-sm">无匹配记忆记录</div>
          ) : (
            filtered.map(m => (
              <button
                key={m.id}
                onClick={() => setSelectedId(m.id)}
                className={`w-full text-left p-2.5 rounded-lg transition-colors border ${
                  selectedId === m.id
                    ? 'bg-accent/10 border-accent/30'
                    : 'bg-chatBgAlt border-borderSubtle/20 hover:border-borderSubtle/40'
                }`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{ backgroundColor: dikwpColors[m.dikwpLayer] || '#888' }}
                  />
                  <span className="text-xs font-medium text-textPrimary truncate">{m.concept}</span>
                  {m.isMUS && (
                    <span className="text-[9px] px-1 py-0.5 rounded bg-amber-900/30 text-amber-400 flex-shrink-0">MUS</span>
                  )}
                </div>
                <p className="text-[11px] text-textSecondary line-clamp-2 mb-1">{m.content}</p>
                <div className="flex items-center gap-2 text-[10px] text-textSecondary">
                  <span>ℐ: {m.iValue.toFixed(2)}</span>
                  <span>κ: {m.kappa.toFixed(2)}</span>
                  <span className="text-textSecondary/60">{formatTime(m.psiAnchor.timestamp)}</span>
                </div>
              </button>
            ))
          )}
        </div>

        {/* Detail Panel */}
        <div className="w-full md:w-80 flex-shrink-0 overflow-y-auto min-h-0">
          {selected ? (
            <div className="bg-chatBgAlt rounded-xl border border-borderSubtle/30 p-4">
              <div className="flex items-center gap-2 mb-3">
                <span
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: dikwpColors[selected.dikwpLayer] || '#888' }}
                />
                <h3 className="text-sm font-semibold text-textPrimary">{selected.concept}</h3>
                {selected.isMUS && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-900/40 text-amber-400">MUS 双存</span>
                )}
              </div>

              <p className="text-xs text-textPrimary leading-relaxed mb-3">{selected.content}</p>

              {/* Stats */}
              <div className="grid grid-cols-2 gap-2 mb-3">
                <div className="bg-chatBg rounded-lg p-2">
                  <p className="text-[10px] text-textSecondary">ℐ 值</p>
                  <p className="text-sm font-mono text-accent">{selected.iValue.toFixed(2)}</p>
                </div>
                <div className="bg-chatBg rounded-lg p-2">
                  <p className="text-[10px] text-textSecondary">κ-Gate</p>
                  <p className="text-sm font-mono text-textPrimary">{selected.kappa.toFixed(2)}</p>
                </div>
                <div className="bg-chatBg rounded-lg p-2">
                  <p className="text-[10px] text-textSecondary">DIKWP</p>
                  <p className="text-sm font-mono text-textPrimary">{selected.dikwpLayer}</p>
                </div>
                <div className="bg-chatBg rounded-lg p-2">
                  <p className="text-[10px] text-textSecondary">标签</p>
                  <p className="text-xs text-textPrimary">{selected.tags.join(', ')}</p>
                </div>
              </div>

              {/* ψ-Anchor */}
              <div className="bg-chatBg rounded-lg p-3 mb-3 border border-borderSubtle/20">
                <p className="text-[10px] text-textSecondary mb-1.5">ψ-锚 (自我状态快照)</p>
                <div className="space-y-1 text-[11px]">
                  <p>状态: <span className="text-textPrimary">{selected.psiAnchor.egoState}</span></p>
                  <p>聚焦: <span className="text-textPrimary">{selected.psiAnchor.focus}</span></p>
                  <p>时间: <span className="text-textSecondary">{selected.psiAnchor.timestamp.toLocaleString('zh-CN')}</span></p>
                </div>
              </div>

              {/* MUS Partner */}
              {selected.isMUS && selected.musPartner && (
                <div className="bg-amber-900/10 rounded-lg p-3 border border-amber-900/20">
                  <p className="text-[10px] text-amber-400 mb-1">MUS 悖论对</p>
                  <p className="text-xs text-textPrimary">{selected.concept} ⊗ {selected.musPartner}</p>
                </div>
              )}
            </div>
          ) : (
            <div className="bg-chatBgAlt rounded-xl border border-borderSubtle/30 p-6 text-center">
              <p className="text-sm text-textSecondary">选择一条记忆查看详情</p>
              <p className="text-[11px] text-textSecondary/60 mt-1">左侧列表中选择后，这里将显示 ψ-锚 和 MUS 状态</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function formatTime(date: Date): string {
  const diff = Date.now() - date.getTime();
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`;
  return `${Math.floor(diff / 86400000)}天前`;
}
