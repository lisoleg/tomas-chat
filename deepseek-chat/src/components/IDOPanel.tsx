import React, { useState } from 'react';
import { IconLayers, IconFlame } from './icons';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:5000';

interface EvalResult { domain: string; tier: string; audit: string; i_value: number; evidence: string[] }
interface FlowResult { steps: number; final_i: number; converged: boolean }

export default function IDOPanel() {
  const [problem, setProblem] = useState('Poincare Conjecture');
  const [domain, setDomain] = useState('mathematics');
  const [axioms, setAxioms] = useState({ A1: true, A2: true, A3: true, A4: true });
  const [iSupport, setISupport] = useState(0.7);
  const [loading, setLoading] = useState(false);
  const [evalResult, setEvalResult] = useState<EvalResult | null>(null);
  const [flowResult, setFlowResult] = useState<FlowResult | null>(null);
  const [error, setError] = useState('');

  const toggleAxiom = (a: string) => setAxioms(prev => ({ ...prev, [a]: !prev[a as keyof typeof prev] }));

  const doEvaluate = async () => {
    setLoading(true); setError(''); setEvalResult(null);
    try {
      const r = await fetch(`${API_BASE}/api/ido/evaluate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ problem_name: problem, domain, axioms, i_support: iSupport }),
      });
      const j = await r.json();
      if (j.success) setEvalResult(j.data);
      else setError(j.error || 'evaluate failed');
    } catch (e: any) { setError(e.message || 'Network error'); }
    finally { setLoading(false); }
  };

  const doFlow = async () => {
    setLoading(true); setError(''); setFlowResult(null);
    try {
      const r = await fetch(`${API_BASE}/api/ido/flow`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ problem_name: problem, domain, i_support: iSupport, max_steps: 80 }),
      });
      const j = await r.json();
      if (j.success) setFlowResult(j.data);
      else setError(j.error || 'flow failed');
    } catch (e: any) { setError(e.message || 'Network error'); }
    finally { setLoading(false); }
  };

  const auditBadge = (status: string) => {
    const map: Record<string, string> = {
      ALLOW: 'bg-emerald-500/20 text-emerald-400',
      REJECT: 'bg-red-500/20 text-red-400',
      MUS_ACTIVE: 'bg-amber-500/20 text-amber-400',
      WARN_UNGROUNDED: 'bg-orange-500/20 text-orange-400',
      NEEDS_HUMAN: 'bg-blue-500/20 text-blue-400',
    };
    return map[status] || 'bg-slate-500/20 text-textSecondary';
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      <h2 className="text-xl font-bold text-white mb-4">IDO 信息最优化桥接</h2>

      {/* Input card */}
      <div className="bg-chatBgAlt rounded-xl p-5 border border-borderSubtle/30 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-textSecondary mb-1">问题名称</label>
            <input value={problem} onChange={e => setProblem(e.target.value)}
              className="w-full bg-chatBg border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-accent" />
          </div>
          <div>
            <label className="block text-xs text-textSecondary mb-1">领域</label>
            <select value={domain} onChange={e => setDomain(e.target.value)}
              className="w-full bg-chatBg border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-accent">
              <option value="mathematics">Mathematics</option>
              <option value="physics">Physics</option>
              <option value="computer-science">Computer Science</option>
              <option value="general">General</option>
            </select>
          </div>
        </div>

        <div>
          <label className="block text-xs text-textSecondary mb-2">公理状态 (A1-A4)</label>
          <div className="flex gap-3">
            {['A1', 'A2', 'A3', 'A4'].map(a => (
              <label key={a} className="flex items-center gap-1.5 cursor-pointer">
                <input type="checkbox" checked={axioms[a as keyof typeof axioms]} onChange={() => toggleAxiom(a)}
                  className="w-3.5 h-3.5 accent-indigo-500" />
                <span className="text-xs text-textPrimary">{a}</span>
              </label>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-xs text-textSecondary mb-1">ℐ 支持度: {iSupport.toFixed(2)}</label>
          <input type="range" min="0" max="1" step="0.01" value={iSupport}
            onChange={e => setISupport(Number(e.target.value))}
            className="w-full accent-indigo-500" />
        </div>

        <div className="flex gap-3">
          <button onClick={doEvaluate} disabled={loading}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-sm text-white font-medium transition-all">
            {loading ? '评估中...' : '逐条评估'}
          </button>
          <button onClick={doFlow} disabled={loading}
            className="px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 rounded-lg text-sm text-white font-medium transition-all">
            {loading ? '流搜索中...' : '运行 IDO 流'}
          </button>
        </div>

        {error && <div className="text-red-400 text-xs bg-red-500/10 rounded-lg px-3 py-2">{error}</div>}
      </div>

      {/* Results */}
      {(evalResult || flowResult) && (
        <div className="grid grid-cols-2 gap-4">
          {evalResult && (
            <div className="bg-chatBgAlt rounded-xl p-5 border border-borderSubtle/30 space-y-3">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <IconLayers className="w-4 h-4 text-indigo-400" /> 评估结果
              </h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between"><span className="text-textSecondary">领域</span><span className="text-white">{evalResult.domain}</span></div>
                <div className="flex justify-between"><span className="text-textSecondary">分级</span><span className="text-indigo-400 font-mono">{evalResult.tier}</span></div>
                <div className="flex justify-between items-center">
                  <span className="text-textSecondary">审计</span>
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${auditBadge(evalResult.audit)}`}>{evalResult.audit}</span>
                </div>
                <div className="flex justify-between"><span className="text-textSecondary">ℐ 值</span><span className="text-emerald-400 font-mono">{evalResult.i_value.toFixed(4)}</span></div>
              </div>
              {evalResult.evidence.length > 0 && (
                <div className="mt-2 pt-3 border-t border-borderSubtle/30">
                  <span className="text-xs text-textSecondary">证据链</span>
                  <ul className="mt-1 space-y-1">{evalResult.evidence.map((e, i) => <li key={i} className="text-xs text-textPrimary">• {e}</li>)}</ul>
                </div>
              )}
            </div>
          )}
          {flowResult && (
            <div className="bg-chatBgAlt rounded-xl p-5 border border-borderSubtle/30 space-y-3">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <IconFlame className="w-4 h-4 text-violet-400" /> IDO 流状态
              </h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between"><span className="text-textSecondary">步数</span><span className="text-white font-mono">{flowResult.steps}</span></div>
                <div className="flex justify-between"><span className="text-textSecondary">最终 ℐ</span><span className="text-emerald-400 font-mono">{flowResult.final_i.toFixed(4)}</span></div>
                <div className="flex justify-between items-center">
                  <span className="text-textSecondary">收敛</span>
                  <span className={flowResult.converged ? 'text-emerald-400' : 'text-amber-400'}>
                    {flowResult.converged ? 'YES' : 'NO'}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
