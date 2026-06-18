import React, { useState } from 'react';
import { IconLayers, IconBrain } from './icons';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:5000';

interface EventLog { t: number; event: string }
interface CogEventLog { tau: number; attention: number; event: string }

export default function DualTimelinePanel() {
  const [extEvents, setExtEvents] = useState<EventLog[]>([]);
  const [intEvents, setIntEvents] = useState<CogEventLog[]>([]);
  const [evtName, setEvtName] = useState('sensor_update');
  const [cogName, setCogName] = useState('perceive_threat');
  const [loading, setLoading] = useState(false);
  const [alignResult, setAlignResult] = useState<any>(null);
  const [error, setError] = useState('');

  const doTick = async () => {
    setError('');
    try {
      const r = await fetch(`${API_BASE}/api/dual-timeline/tick`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event: evtName, timestamp: new Date().toISOString() }),
      });
      const j = await r.json();
      if (j.success) {
        setExtEvents(prev => [...prev.slice(-49), { t: j.data.t, event: evtName }]);
      } else setError(j.error || 'tick failed');
    } catch (e: any) { setError(e.message || 'Network error'); }
  };

  const doStep = async () => {
    setError('');
    try {
      const r = await fetch(`${API_BASE}/api/dual-timeline/step`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cognitive_event: cogName }),
      });
      const j = await r.json();
      if (j.success) {
        setIntEvents(prev => [...prev.slice(-49), { tau: j.data.tau, attention: j.data.attention, event: cogName }]);
      } else setError(j.error || 'step failed');
    } catch (e: any) { setError(e.message || 'Network error'); }
  };

  const doAlign = async () => {
    setLoading(true); setError('');
    try {
      const r = await fetch(`${API_BASE}/api/dual-timeline/align`, { method: 'POST' });
      const j = await r.json();
      setAlignResult(j.success ? j.data : null);
      if (!j.success) setError(j.error || 'align failed');
    } catch (e: any) { setError(e.message || 'Network error'); }
    finally { setLoading(false); }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      <h2 className="text-xl font-bold text-textPrimary mb-4">双时间维度引擎</h2>

      <div className="grid grid-cols-2 gap-4">
        {/* External Timeline */}
        <div className="bg-chatBgAlt rounded-xl p-5 border border-borderSubtle/30 space-y-3">
          <h3 className="text-sm font-semibold text-blue-400 flex items-center gap-2">
            <IconLayers className="w-4 h-4" /> 外时间 (因果流)
          </h3>
          <div className="flex gap-2">
            <input value={evtName} onChange={e => setEvtName(e.target.value)}
              className="flex-1 bg-chatBg border border-borderSubtle/30 rounded-lg px-3 py-1.5 text-xs text-textPrimary focus:outline-none focus:border-blue-500" />
            <button onClick={doTick}
              className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded-lg text-xs text-textPrimary font-medium transition-all">
              Tick
            </button>
          </div>
          <div className="h-48 overflow-y-auto space-y-1 bg-chatBg/50 rounded-lg p-2">
            {extEvents.map((e, i) => (
              <div key={i} className="flex justify-between text-xs">
                <span className="text-blue-300 font-mono">t={e.t}</span>
                <span className="text-textSecondary">{e.event}</span>
              </div>
            ))}
            {extEvents.length === 0 && <div className="text-xs text-textSecondary text-center py-8">等待 Tick...</div>}
          </div>
        </div>

        {/* Internal Timeline */}
        <div className="bg-chatBgAlt rounded-xl p-5 border border-borderSubtle/30 space-y-3">
          <h3 className="text-sm font-semibold text-violet-400 flex items-center gap-2">
            <IconBrain className="w-4 h-4" /> 内时间 (认知流)
          </h3>
          <div className="flex gap-2">
            <input value={cogName} onChange={e => setCogName(e.target.value)}
              className="flex-1 bg-chatBg border border-borderSubtle/30 rounded-lg px-3 py-1.5 text-xs text-textPrimary focus:outline-none focus:border-violet-500" />
            <button onClick={doStep}
              className="px-3 py-1.5 bg-violet-600 hover:bg-violet-500 rounded-lg text-xs text-textPrimary font-medium transition-all">
              Step
            </button>
          </div>
          <div className="h-48 overflow-y-auto space-y-1 bg-chatBg/50 rounded-lg p-2">
            {intEvents.map((e, i) => (
              <div key={i} className="flex justify-between text-xs">
                <span className="text-violet-300 font-mono">τ={e.tau}</span>
                <span className="text-textSecondary">{e.event}</span>
                <span className="text-amber-400">{e.attention.toFixed(2)}</span>
              </div>
            ))}
            {intEvents.length === 0 && <div className="text-xs text-textSecondary text-center py-8">等待 Step...</div>}
          </div>
        </div>
      </div>

      {/* Align */}
      <div className="bg-chatBgAlt rounded-xl p-5 border border-borderSubtle/30 space-y-3">
        <button onClick={doAlign} disabled={loading}
          className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 rounded-lg text-sm text-textPrimary font-medium transition-all">
          {loading ? '对齐中...' : '对齐双时间线'}
        </button>
        {alignResult && (
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-textSecondary">对齐状态</span>
              <span className={alignResult.aligned ? 'text-emerald-400' : 'text-amber-400'}>
                {alignResult.aligned ? '已对齐' : '未对齐'}
              </span>
            </div>
            {alignResult.singularities?.length > 0 && (
              <div className="mt-2 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
                <span className="text-xs text-amber-400 font-medium">检测到奇点:</span>
                <ul className="mt-1 space-y-0.5">{alignResult.singularities.map((s: string, i: number) => (
                  <li key={i} className="text-xs text-amber-300 font-mono">{s}</li>
                ))}</ul>
              </div>
            )}
          </div>
        )}
      </div>

      {error && <div className="text-red-400 text-xs bg-red-500/10 rounded-lg px-3 py-2">{error}</div>}
    </div>
  );
}
