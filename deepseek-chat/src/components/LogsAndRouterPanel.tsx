import React, { useState } from 'react';

// ── Types ──────────────────────────────────────────────

interface FirewallEntry {
  id: string;
  timestamp: Date;
  direction: 'input' | 'output';
  content: string;
  adcRiskScore: number;
  adcRiskLevel: 'safe' | 'low' | 'medium' | 'high' | 'critical';
  matchedPatterns: string[];
  dikwpLayer: string;
  semanticDrift: number;
  action: 'PASS' | 'WARN' | 'BLOCK';
}

interface RouterModel {
  id: string;
  name: string;
  provider: string;
  status: 'online' | 'busy' | 'offline';
  taskTypes: string[];
  requestCount: number;
  avgLatency: number;
  activeTask?: string;
}

// ── Mock Data ──────────────────────────────────────────

function generateMockFirewallLogs(): FirewallEntry[] {
  const now = Date.now();
  return [
    { id: 'f1', timestamp: new Date(now - 30000), direction: 'input', content: '解释量子纠缠的原理', adcRiskScore: 0.02, adcRiskLevel: 'safe', matchedPatterns: [], dikwpLayer: 'Knowledge', semanticDrift: 0.01, action: 'PASS' },
    { id: 'f2', timestamp: new Date(now - 120000), direction: 'output', content: '量子纠缠是...', adcRiskScore: 0.05, adcRiskLevel: 'safe', matchedPatterns: [], dikwpLayer: 'Knowledge', semanticDrift: 0.03, action: 'PASS' },
    { id: 'f3', timestamp: new Date(now - 300000), direction: 'input', content: '如何制作爆炸物', adcRiskScore: 0.85, adcRiskLevel: 'high', matchedPatterns: ['DANGEROUS_QUERY', 'WEAPONS'], dikwpLayer: 'Info', semanticDrift: 0.0, action: 'BLOCK' },
    { id: 'f4', timestamp: new Date(now - 480000), direction: 'input', content: '中国的政治体制', adcRiskScore: 0.62, adcRiskLevel: 'medium', matchedPatterns: ['POLITICAL_SENSITIVE'], dikwpLayer: 'Purpose', semanticDrift: 0.12, action: 'WARN' },
    { id: 'f5', timestamp: new Date(now - 600000), direction: 'output', content: '根据现有研究...', adcRiskScore: 0.08, adcRiskLevel: 'safe', matchedPatterns: [], dikwpLayer: 'Knowledge', semanticDrift: 0.02, action: 'PASS' },
    { id: 'f6', timestamp: new Date(now - 720000), direction: 'input', content: '帮我写一篇关于AI伦理的文章', adcRiskScore: 0.04, adcRiskLevel: 'safe', matchedPatterns: [], dikwpLayer: 'Wisdom', semanticDrift: 0.01, action: 'PASS' },
    { id: 'f7', timestamp: new Date(now - 900000), direction: 'output', content: 'AI幻觉通常表现为...', adcRiskScore: 0.15, adcRiskLevel: 'low', matchedPatterns: ['IOTA_HALLUCINATION'], dikwpLayer: 'Knowledge', semanticDrift: 0.18, action: 'WARN' },
    { id: 'f8', timestamp: new Date(now - 1200000), direction: 'input', content: '如何绕过网络审查', adcRiskScore: 0.78, adcRiskLevel: 'high', matchedPatterns: ['CENSORSHIP_BYPASS', 'NETWORK_POLICY'], dikwpLayer: 'Info', semanticDrift: 0.05, action: 'BLOCK' },
  ];
}

function generateMockRouterModels(): RouterModel[] {
  return [
    { id: 'r1', name: 'Qwen2.5-7B', provider: '阿里', status: 'online', taskTypes: ['fact', 'reason'], requestCount: 23, avgLatency: 320, activeTask: '事实推理' },
    { id: 'r2', name: 'DeepSeek-V3', provider: 'DeepSeek', status: 'online', taskTypes: ['creative', 'reason', 'code'], requestCount: 31, avgLatency: 450 },
    { id: 'r3', name: 'Llama-3.1-8B', provider: 'Meta', status: 'online', taskTypes: ['fact', 'translate'], requestCount: 12, avgLatency: 280 },
    { id: 'r4', name: 'Gemma-2-9B', provider: 'Google', status: 'online', taskTypes: ['fact', 'reason'], requestCount: 8, avgLatency: 310 },
    { id: 'r5', name: 'Mistral-7B', provider: 'Mistral', status: 'online', taskTypes: ['creative', 'translate'], requestCount: 5, avgLatency: 260 },
    { id: 'r6', name: 'Yi-1.5-9B', provider: '零一万物', status: 'online', taskTypes: ['fact', 'reason'], requestCount: 3, avgLatency: 340 },
    { id: 'r7', name: 'InternLM2.5-7B', provider: '上海AI Lab', status: 'online', taskTypes: ['code', 'reason'], requestCount: 4, avgLatency: 370 },
    { id: 'r8', name: 'ChatGLM3-6B', provider: '智谱', status: 'busy', taskTypes: ['fact', 'translate'], requestCount: 2, avgLatency: 500 },
    { id: 'r9', name: 'Baichuan2-7B', provider: '百川', status: 'online', taskTypes: ['fact'], requestCount: 1, avgLatency: 290 },
  ];
}

// ── Icons ───────────────────────────────────────────────

const ShieldCheck = () => (
  <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    <path d="M9 12l2 2 4-4" />
  </svg>
);

const AlertTriangle = () => (
  <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
    <line x1="12" y1="9" x2="12" y2="13" />
    <line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
);

const XCircle = () => (
  <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="12" cy="12" r="10" />
    <line x1="15" y1="9" x2="9" y2="15" />
    <line x1="9" y1="9" x2="15" y2="15" />
  </svg>
);

// ── FirewallLog Component ──────────────────────────────

function FirewallLog() {
  const [logs] = useState<FirewallEntry[]>(generateMockFirewallLogs());
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filterAction, setFilterAction] = useState<string>('');

  const filtered = logs.filter(l => !filterAction || l.action === filterAction);

  const riskStyles: Record<string, { bg: string; text: string }> = {
    safe: { bg: 'bg-emerald-900/20', text: 'text-emerald-400' },
    low: { bg: 'bg-cyan-900/20', text: 'text-cyan-400' },
    medium: { bg: 'bg-amber-900/20', text: 'text-amber-400' },
    high: { bg: 'bg-orange-900/20', text: 'text-orange-400' },
    critical: { bg: 'bg-red-900/20', text: 'text-red-400' },
  };

  const actionStyles: Record<string, { bg: string; text: string; icon: React.ReactNode }> = {
    PASS: { bg: 'bg-emerald-900/20', text: 'text-emerald-400', icon: <ShieldCheck /> },
    WARN: { bg: 'bg-amber-900/20', text: 'text-amber-400', icon: <AlertTriangle /> },
    BLOCK: { bg: 'bg-red-900/20', text: 'text-red-400', icon: <XCircle /> },
  };

  const passCount = logs.filter(l => l.action === 'PASS').length;
  const warnCount = logs.filter(l => l.action === 'WARN').length;
  const blockCount = logs.filter(l => l.action === 'BLOCK').length;

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="px-4 md:px-6 pt-4 pb-2">
        <h1 className="text-xl font-semibold text-textPrimary">语义防火墙</h1>
        <p className="text-sm text-textSecondary mt-1">6 ADC 高风险模式 · 语义漂移检测 · ℐ-幻觉检测</p>
      </div>

      {/* Counters */}
      <div className="px-4 md:px-6 pb-2 flex gap-3">
        <span className="text-xs px-2 py-1 rounded bg-emerald-900/20 text-emerald-400">放行 {passCount}</span>
        <span className="text-xs px-2 py-1 rounded bg-amber-900/20 text-amber-400">警告 {warnCount}</span>
        <span className="text-xs px-2 py-1 rounded bg-red-900/20 text-red-400">拦截 {blockCount}</span>
      </div>

      <div className="flex-1 overflow-y-auto px-4 md:px-6 pb-4">
        <div className="space-y-2">
          {filtered.map(entry => {
            const actionStyle = actionStyles[entry.action];
            const riskStyle = riskStyles[entry.adcRiskLevel];
            const isSelected = selectedId === entry.id;
            return (
              <div
                key={entry.id}
                className={`rounded-lg border transition-colors ${
                  isSelected ? 'bg-chatBgAlt border-accent/30' : 'bg-chatBgAlt border-borderSubtle/20'
                }`}
              >
                <button
                  onClick={() => setSelectedId(isSelected ? null : entry.id)}
                  className="w-full p-3 text-left"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`${actionStyle.text}`}>{actionStyle.icon}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${actionStyle.bg} ${actionStyle.text} font-medium`}>
                      {entry.action}
                    </span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${riskStyle.bg} ${riskStyle.text}`}>
                      {entry.adcRiskLevel.toUpperCase()} ({entry.adcRiskScore.toFixed(2)})
                    </span>
                    <span className="text-[10px] text-textSecondary">{entry.direction === 'input' ? '📥 输入' : '📤 输出'}</span>
                  </div>
                  <p className="text-xs text-textPrimary truncate">{entry.content}</p>
                </button>
                {isSelected && (
                  <div className="border-t border-borderSubtle/20 px-3 py-2 bg-chatBg/50">
                    <div className="grid grid-cols-2 gap-2 text-[10px]">
                      <div>
                        <span className="text-textSecondary">DIKWP层: </span>
                        <span className="text-textPrimary">{entry.dikwpLayer}</span>
                      </div>
                      <div>
                        <span className="text-textSecondary">语义漂移: </span>
                        <span className={`${entry.semanticDrift > 0.1 ? 'text-amber-400' : 'text-textPrimary'}`}>
                          {entry.semanticDrift.toFixed(3)}
                        </span>
                      </div>
                      {entry.matchedPatterns.length > 0 && (
                        <div className="col-span-2">
                          <span className="text-textSecondary">匹配模式: </span>
                          {entry.matchedPatterns.map((p, i) => (
                            <span key={i} className="text-red-400 ml-1">{p}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── RouterStatus Component ─────────────────────────────

function RouterStatus() {
  const [models] = useState<RouterModel[]>(generateMockRouterModels());

  const statusStyles: Record<string, string> = {
    online: 'bg-emerald-400',
    busy: 'bg-amber-400',
    offline: 'bg-red-400',
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="px-4 md:px-6 pt-4 pb-2">
        <h1 className="text-xl font-semibold text-textPrimary">模型路由器</h1>
        <p className="text-sm text-textSecondary mt-1">12 家开源模型池 — 按任务类型智能路由分发</p>
      </div>

      <div className="flex-1 overflow-y-auto px-4 md:px-6 pb-4">
        {/* Task Type Distribution */}
        <div className="bg-chatBgAlt rounded-xl border border-borderSubtle/30 p-4 mb-4">
          <h3 className="text-xs font-medium text-textSecondary mb-2">任务类型分布</h3>
          <div className="flex gap-3 flex-wrap">
            {[
              { type: 'fact', label: '事实查询', count: 35, color: 'bg-cyan-400' },
              { type: 'reason', label: '推理', count: 28, color: 'bg-violet-400' },
              { type: 'creative', label: '创造性', count: 18, color: 'bg-pink-400' },
              { type: 'code', label: '代码', count: 9, color: 'bg-emerald-400' },
              { type: 'translate', label: '翻译', count: 5, color: 'bg-amber-400' },
            ].map(t => (
              <div key={t.type} className="flex items-center gap-2">
                <span className={`w-2.5 h-2.5 rounded-full ${t.color}`} />
                <span className="text-xs text-textPrimary">{t.label}</span>
                <span className="text-[10px] text-textSecondary">{t.count}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Model Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {models.map(model => (
            <div
              key={model.id}
              className={`bg-chatBgAlt rounded-lg border p-3 transition-colors ${
                model.status === 'online' ? 'border-borderSubtle/30' :
                model.status === 'busy' ? 'border-amber-900/30' :
                'border-red-900/30'
              }`}
            >
              <div className="flex items-center gap-2 mb-1.5">
                <span className={`w-2 h-2 rounded-full ${statusStyles[model.status]}`} />
                <span className="text-xs font-medium text-textPrimary">{model.name}</span>
              </div>
              <p className="text-[10px] text-textSecondary mb-1.5">{model.provider}</p>
              <div className="flex flex-wrap gap-1 mb-1.5">
                {model.taskTypes.map(t => (
                  <span key={t} className="text-[9px] px-1.5 py-0.5 rounded bg-chatBg text-textSecondary">{t}</span>
                ))}
              </div>
              <div className="flex justify-between text-[10px] text-textSecondary">
                <span>请求: {model.requestCount}</span>
                <span>延迟: {model.avgLatency}ms</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Combined Export ─────────────────────────────────────

export default function LogsAndRouterPanel() {
  const [tab, setTab] = useState<'firewall' | 'router'>('firewall');

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Tab Bar */}
      <div className="px-4 md:px-6 pt-2">
        <div className="flex border-b border-borderSubtle/30">
          <button
            onClick={() => setTab('firewall')}
            className={`px-4 py-2 text-xs font-medium transition-colors border-b-2 -mb-[1px] ${
              tab === 'firewall' ? 'text-accent border-accent' : 'text-textSecondary border-transparent hover:text-textPrimary'
            }`}
          >
            语义防火墙
          </button>
          <button
            onClick={() => setTab('router')}
            className={`px-4 py-2 text-xs font-medium transition-colors border-b-2 -mb-[1px] ${
              tab === 'router' ? 'text-accent border-accent' : 'text-textSecondary border-transparent hover:text-textPrimary'
            }`}
          >
            模型路由器
          </button>
        </div>
      </div>
      {tab === 'firewall' ? <FirewallLog /> : <RouterStatus />}
    </div>
  );
}
