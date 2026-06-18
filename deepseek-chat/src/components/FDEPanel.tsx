import React, { useState } from 'react';
import { IconFlame, IconShield } from './icons';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:5000';

interface FDEResult {
  type: 'build' | 'calibrate' | 'asym';
  [key: string]: unknown;
}

export default function FDEPanel() {
  const [tab, setTab] = useState<'build' | 'calibrate' | 'asym'>('build');

  // Build
  const [echoIT, setEchoIT] = useState('');
  const [echoOT, setEchoOT] = useState('');
  const [echoET, setEchoET] = useState('');
  const [standard, setStandard] = useState('IEC62443');

  // Calibrate
  const [calConcept, setCalConcept] = useState('');
  const [calIValue, setCalIValue] = useState(0.5);

  // Asym
  const [asymText, setAsymText] = useState('');

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<FDEResult | null>(null);
  const [error, setError] = useState('');

  const doBuild = async () => {
    setLoading(true); setError(''); setResult(null);
    try {
      const r = await fetch(`${API_BASE}/api/fde/build`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          echo_context: { it: echoIT, ot: echoOT, et: echoET },
          standard_ref: standard,
        }),
      });
      const j = await r.json();
      if (j.success) setResult({ type: 'build', ...j.data });
      else setError(j.error || 'build failed');
    } catch (e: any) { setError(e.message || 'Network error'); }
    finally { setLoading(false); }
  };

  const doCalibrate = async () => {
    setLoading(true); setError(''); setResult(null);
    try {
      const r = await fetch(`${API_BASE}/api/fde/calibrate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_concept: calConcept, i_value: calIValue }),
      });
      const j = await r.json();
      if (j.success) setResult({ type: 'calibrate', ...j.data });
      else setError(j.error || 'calibrate failed');
    } catch (e: any) { setError(e.message || 'Network error'); }
    finally { setLoading(false); }
  };

  const doCheckAsym = async () => {
    setLoading(true); setError(''); setResult(null);
    try {
      const r = await fetch(`${API_BASE}/api/fde/check-asym`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ skill_description: asymText }),
      });
      const j = await r.json();
      if (j.success) setResult({ type: 'asym', ...j.data });
      else setError(j.error || 'assym check failed');
    } catch (e: any) { setError(e.message || 'Network error'); }
    finally { setLoading(false); }
  };

  const tabs = [
    { id: 'build' as const, label: '构建本体' },
    { id: 'calibrate' as const, label: 'ℐ 标定' },
    { id: 'asym' as const, label: 'MUS 检测' },
  ];

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      <h2 className="text-xl font-bold text-textPrimary mb-4">FDE 道法术器本体构建器</h2>

      {/* Tab nav */}
      <div className="flex gap-1 bg-chatBgAlt rounded-lg p-1 border border-borderSubtle/30">
        {tabs.map(t => (
          <button key={t.id} onClick={() => { setTab(t.id); setResult(null); setError(''); }}
            className={`flex-1 px-3 py-2 rounded-md text-xs font-medium transition-all ${
              tab === t.id ? 'bg-indigo-600 text-textPrimary' : 'text-textSecondary hover:text-textPrimary'
            }`}>{t.label}</button>
        ))}
      </div>

      {/* Build tab */}
      {tab === 'build' && (
        <div className="bg-chatBgAlt rounded-xl p-5 border border-borderSubtle/30 space-y-4">
          <div>
            <label className="block text-xs text-textSecondary mb-1">IT 上下文</label>
            <textarea value={echoIT} onChange={e => setEchoIT(e.target.value)} rows={2}
              className="w-full bg-chatBg border border-borderSubtle/30 rounded-lg px-3 py-2 text-sm text-textPrimary focus:outline-none focus:border-accent resize-none"
              placeholder="IT domain context..." />
          </div>
          <div>
            <label className="block text-xs text-textSecondary mb-1">OT 上下文</label>
            <textarea value={echoOT} onChange={e => setEchoOT(e.target.value)} rows={2}
              className="w-full bg-chatBg border border-borderSubtle/30 rounded-lg px-3 py-2 text-sm text-textPrimary focus:outline-none focus:border-accent resize-none"
              placeholder="OT domain context..." />
          </div>
          <div>
            <label className="block text-xs text-textSecondary mb-1">ET 上下文</label>
            <textarea value={echoET} onChange={e => setEchoET(e.target.value)} rows={2}
              className="w-full bg-chatBg border border-borderSubtle/30 rounded-lg px-3 py-2 text-sm text-textPrimary focus:outline-none focus:border-accent resize-none"
              placeholder="Emerging tech context..." />
          </div>
          <div>
            <label className="block text-xs text-textSecondary mb-1">工业标准</label>
            <select value={standard} onChange={e => setStandard(e.target.value)}
              className="w-full bg-chatBg border border-borderSubtle/30 rounded-lg px-3 py-2 text-sm text-textPrimary focus:outline-none focus:border-accent">
              <option value="IEC62443">IEC 62443 (工控安全)</option>
              <option value="ISO26262">ISO 26262 (汽车功能安全)</option>
              <option value="IEC61508">IEC 61508 (功能安全)</option>
            </select>
          </div>
          <button onClick={doBuild} disabled={loading}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-sm text-textPrimary font-medium transition-all">
            {loading ? '构建中...' : '构建 FDE 本体'}
          </button>
        </div>
      )}

      {/* Calibrate tab */}
      {tab === 'calibrate' && (
        <div className="bg-chatBgAlt rounded-xl p-5 border border-borderSubtle/30 space-y-4">
          <div>
            <label className="block text-xs text-textSecondary mb-1">目标概念</label>
            <input value={calConcept} onChange={e => setCalConcept(e.target.value)}
              className="w-full bg-chatBg border border-borderSubtle/30 rounded-lg px-3 py-2 text-sm text-textPrimary focus:outline-none focus:border-accent"
              placeholder="e.g. momentum, entropy, attention" />
          </div>
          <div>
            <label className="block text-xs text-textSecondary mb-1">ℐ 值: {calIValue.toFixed(2)}</label>
            <input type="range" min="0" max="1" step="0.01" value={calIValue}
              onChange={e => setCalIValue(Number(e.target.value))}
              className="w-full accent-indigo-500" />
          </div>
          <button onClick={doCalibrate} disabled={loading}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 rounded-lg text-sm text-textPrimary font-medium transition-all">
            {loading ? '标定中...' : '执行标定'}
          </button>
        </div>
      )}

      {/* Asym tab */}
      {tab === 'asym' && (
        <div className="bg-chatBgAlt rounded-xl p-5 border border-borderSubtle/30 space-y-4">
          <div>
            <label className="block text-xs text-textSecondary mb-1">技能描述</label>
            <textarea value={asymText} onChange={e => setAsymText(e.target.value)} rows={3}
              className="w-full bg-chatBg border border-borderSubtle/30 rounded-lg px-3 py-2 text-sm text-textPrimary focus:outline-none focus:border-accent resize-none"
              placeholder="Describe a skill to check for semantic asymmetry..." />
          </div>
          <button onClick={doCheckAsym} disabled={loading}
            className="px-4 py-2 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 rounded-lg text-sm text-textPrimary font-medium transition-all">
            {loading ? '检测中...' : 'MUS 不对称检测'}
          </button>
        </div>
      )}

      {/* Error */}
      {error && <div className="text-red-400 text-xs bg-red-500/10 rounded-lg px-3 py-2">{error}</div>}

      {/* Result */}
      {result && (
        <div className="bg-chatBgAlt rounded-xl p-5 border border-borderSubtle/30 space-y-3">
          <h3 className="text-sm font-semibold text-textPrimary flex items-center gap-2">
            <IconShield className="w-4 h-4 text-emerald-400" /> 结果
          </h3>
          <pre className="text-xs text-textPrimary bg-chatBg/50 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap">
            {JSON.stringify(result, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
