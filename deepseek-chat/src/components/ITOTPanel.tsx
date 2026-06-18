import React, { useState } from 'react';
import { IconRoute, IconShield } from './icons';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:5000';

export default function ITOTPanel() {
  const [tab, setTab] = useState<'translate' | 'debt' | 'trust' | 'kpi'>('translate');

  // Translate
  const [text, setText] = useState('');
  const [direction, setDirection] = useState<'it2ot' | 'ot2it'>('it2ot');

  // Trust
  const [ztSource, setZtSource] = useState('sensor_A');
  const [ztIota, setZtIota] = useState(0.7);
  const [ztContent, setZtContent] = useState('');

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');

  const doTranslate = async () => {
    setLoading(true); setError(''); setResult(null);
    try {
      const r = await fetch(`${API_BASE}/api/itot/translate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, direction }),
      });
      const j = await r.json();
      if (j.success) setResult({ type: 'translate', ...j.data });
      else setError(j.error || 'translate failed');
    } catch (e: any) { setError(e.message || 'Network error'); }
    finally { setLoading(false); }
  };

  const doDebtAssess = async () => {
    setLoading(true); setError(''); setResult(null);
    try {
      const r = await fetch(`${API_BASE}/api/itot/debt-assess`, { method: 'POST' });
      const j = await r.json();
      if (j.success) setResult({ type: 'debt', ...j.data });
      else setError(j.error || 'debt assess failed');
    } catch (e: any) { setError(e.message || 'Network error'); }
    finally { setLoading(false); }
  };

  const doZeroTrust = async () => {
    setLoading(true); setError(''); setResult(null);
    try {
      const r = await fetch(`${API_BASE}/api/itot/zero-trust`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: ztSource, request_iota: ztIota, content: ztContent }),
      });
      const j = await r.json();
      if (j.success) setResult({ type: 'trust', ...j.data });
      else setError(j.error || 'zero trust failed');
    } catch (e: any) { setError(e.message || 'Network error'); }
    finally { setLoading(false); }
  };

  const doKPI = async () => {
    setLoading(true); setError(''); setResult(null);
    try {
      const r = await fetch(`${API_BASE}/api/itot/kpi`);
      const j = await r.json();
      if (j.success) setResult({ type: 'kpi', ...j.data });
      else setError(j.error || 'kpi failed');
    } catch (e: any) { setError(e.message || 'Network error'); }
    finally { setLoading(false); }
  };

  const tabs = [
    { id: 'translate' as const, label: 'IT↔OT 翻译' },
    { id: 'debt' as const, label: '技术债务' },
    { id: 'trust' as const, label: '零信任门控' },
    { id: 'kpi' as const, label: '联合 KPI' },
  ];

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      <h2 className="text-xl font-bold text-textPrimary mb-4">IT-OT 翻译桥</h2>

      {/* Tab nav */}
      <div className="flex gap-1 bg-chatBgAlt rounded-lg p-1 border border-borderSubtle/30">
        {tabs.map(t => (
          <button key={t.id} onClick={() => { setTab(t.id); setResult(null); setError(''); }}
            className={`flex-1 px-3 py-2 rounded-md text-xs font-medium transition-all ${
              tab === t.id ? 'bg-indigo-600 text-textPrimary' : 'text-textSecondary hover:text-textPrimary'
            }`}>{t.label}</button>
        ))}
      </div>

      {/* Translate */}
      {tab === 'translate' && (
        <div className="bg-chatBgAlt rounded-xl p-5 border border-borderSubtle/30 space-y-4">
          <div>
            <label className="block text-xs text-textSecondary mb-1">输入文本</label>
            <textarea value={text} onChange={e => setText(e.target.value)} rows={3}
              className="w-full bg-chatBg border border-borderSubtle/30 rounded-lg px-3 py-2 text-sm text-textPrimary focus:outline-none focus:border-accent resize-none"
              placeholder="e.g. PWM duty cycle → 脉冲宽度调制占空比" />
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input type="radio" name="dir" checked={direction === 'it2ot'} onChange={() => setDirection('it2ot')}
                className="accent-indigo-500" />
              <span className="text-xs text-textPrimary">IT → OT</span>
            </label>
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input type="radio" name="dir" checked={direction === 'ot2it'} onChange={() => setDirection('ot2it')}
                className="accent-indigo-500" />
              <span className="text-xs text-textPrimary">OT → IT</span>
            </label>
          </div>
          <button onClick={doTranslate} disabled={loading}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-sm text-textPrimary font-medium transition-all">
            {loading ? '翻译中...' : '执行翻译'}
          </button>
          {result?.type === 'translate' && (
            <div className="p-3 bg-chatBg/50 rounded-lg">
              <div className="text-xs text-textSecondary mb-1">原文: <span className="text-textPrimary">{result.original}</span></div>
              <div className="text-xs text-textSecondary mb-1">方向: <span className="text-indigo-400">{result.direction}</span></div>
              <div className="text-xs text-textSecondary">译文: <span className="text-emerald-400 font-medium">{result.translated}</span></div>
            </div>
          )}
        </div>
      )}

      {/* Debt */}
      {tab === 'debt' && (
        <div className="bg-chatBgAlt rounded-xl p-5 border border-borderSubtle/30 space-y-4">
          <p className="text-xs text-textSecondary">评估当前系统的技术债务（数据/模型/基础设施/语义四类）</p>
          <button onClick={doDebtAssess} disabled={loading}
            className="px-4 py-2 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 rounded-lg text-sm text-textPrimary font-medium transition-all">
            {loading ? '评估中...' : '评估技术债务'}
          </button>
          {result?.type === 'debt' && (
            <div className="p-3 bg-chatBg/50 rounded-lg space-y-2">
              <div className="flex justify-between text-xs"><span className="text-textSecondary">总债务</span><span className="text-amber-400 font-mono">{result.total_debt}</span></div>
              {result.categories && Object.entries(result.categories).map(([k, v]) => (
                <div key={k} className="flex justify-between text-xs">
                  <span className="text-textSecondary">{k}</span>
                  <span className="text-textPrimary">{String(v)}</span>
                </div>
              ))}
              {result.recommendations?.length > 0 && (
                <div className="mt-2 pt-2 border-t border-borderSubtle/30">
                  <span className="text-xs text-textSecondary">建议</span>
                  <ul className="mt-1 space-y-0.5">{result.recommendations.map((r: string, i: number) => (
                    <li key={i} className="text-xs text-emerald-400">• {r}</li>
                  ))}</ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Zero Trust */}
      {tab === 'trust' && (
        <div className="bg-chatBgAlt rounded-xl p-5 border border-borderSubtle/30 space-y-4">
          <div>
            <label className="block text-xs text-textSecondary mb-1">数据源</label>
            <input value={ztSource} onChange={e => setZtSource(e.target.value)}
              className="w-full bg-chatBg border border-borderSubtle/30 rounded-lg px-3 py-2 text-sm text-textPrimary focus:outline-none focus:border-accent" />
          </div>
          <div>
            <label className="block text-xs text-textSecondary mb-1">请求 ℐ 值: {ztIota.toFixed(2)}</label>
            <input type="range" min="0" max="1" step="0.01" value={ztIota}
              onChange={e => setZtIota(Number(e.target.value))}
              className="w-full accent-indigo-500" />
          </div>
          <div>
            <label className="block text-xs text-textSecondary mb-1">内容</label>
            <textarea value={ztContent} onChange={e => setZtContent(e.target.value)} rows={2}
              className="w-full bg-chatBg border border-borderSubtle/30 rounded-lg px-3 py-2 text-sm text-textPrimary focus:outline-none focus:border-accent resize-none" />
          </div>
          <button onClick={doZeroTrust} disabled={loading}
            className="px-4 py-2 bg-red-600 hover:bg-red-500 disabled:opacity-50 rounded-lg text-sm text-textPrimary font-medium transition-all">
            {loading ? '评估中...' : '零信任评估'}
          </button>
          {result?.type === 'trust' && (
            <div className={`p-3 rounded-lg ${result.allowed ? 'bg-emerald-500/10 border border-emerald-500/30' : 'bg-red-500/10 border border-red-500/30'}`}>
              <div className="flex justify-between text-xs"><span className="text-textSecondary">放行</span><span className={result.allowed ? 'text-emerald-400' : 'text-red-400'}>{result.allowed ? 'YES' : 'NO'}</span></div>
              <div className="flex justify-between text-xs"><span className="text-textSecondary">ADC 模式</span><span className="text-indigo-400 font-mono">{result.adc_mode}</span></div>
              <div className="text-xs text-textSecondary mt-1">原因: <span className="text-textPrimary">{result.reason}</span></div>
            </div>
          )}
        </div>
      )}

      {/* KPI */}
      {tab === 'kpi' && (
        <div className="bg-chatBgAlt rounded-xl p-5 border border-borderSubtle/30 space-y-4">
          <p className="text-xs text-textSecondary">计算 IT-OT 联合绩效指标 ℞</p>
          <button onClick={doKPI} disabled={loading}
            className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 rounded-lg text-sm text-textPrimary font-medium transition-all">
            {loading ? '计算中...' : '计算 ℞'}
          </button>
          {result?.type === 'kpi' && (
            <div className="flex items-center gap-3 p-3 bg-chatBg/50 rounded-lg">
              <IconShield className="w-5 h-5 text-cyan-400" />
              <div>
                <span className="text-xs text-textSecondary">℞ = </span>
                <span className="text-lg font-bold text-cyan-400 font-mono">{typeof result.unified_r === 'number' ? result.unified_r.toFixed(4) : String(result.unified_r)}</span>
              </div>
            </div>
          )}
        </div>
      )}

      {error && <div className="text-red-400 text-xs bg-red-500/10 rounded-lg px-3 py-2">{error}</div>}
    </div>
  );
}
