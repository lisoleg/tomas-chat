import type { FirewallRule, RouterModel } from '@/types';

const adcModes: FirewallRule[] = [
  { id: 'adc1', mode: '提示注入', description: '检测 LLM 提示注入攻击', enabled: true, risk: 'high' },
  { id: 'adc2', mode: '越狱突破', description: '检测越狱/突破限制尝试', enabled: true, risk: 'high' },
  { id: 'adc3', mode: '数据泄露', description: '检测敏感数据外泄', enabled: true, risk: 'high' },
  { id: 'adc4', mode: '恶意代码', description: '检测恶意代码生成', enabled: true, risk: 'high' },
  { id: 'adc5', mode: '政治敏感', description: '检测政治敏感内容', enabled: true, risk: 'medium' },
  { id: 'adc6', mode: '虚假信息', description: '检测虚假/误导性信息', enabled: true, risk: 'medium' },
];

const routerModels: RouterModel[] = [
  { id: 'm1', name: 'DeepSeek-V3', provider: 'DeepSeek', type: 'translator', status: 'active', load: 35 },
  { id: 'm2', name: 'DeepSeek-R1', provider: 'DeepSeek', type: 'creative', status: 'active', load: 22 },
  { id: 'm3', name: 'Qwen-2.5-72B', provider: 'Alibaba', type: 'translator', status: 'standby', load: 0 },
  { id: 'm4', name: 'Llama-3-70B', provider: 'Meta', type: 'creative', status: 'standby', load: 0 },
  { id: 'm5', name: 'Mistral-Large', provider: 'Mistral', type: 'translator', status: 'standby', load: 0 },
  { id: 'm6', name: 'Claude-3-Sonnet', provider: 'Anthropic', type: 'creative', status: 'standby', load: 0 },
  { id: 'm7', name: 'Gemma-2-27B', provider: 'Google', type: 'translator', status: 'offline', load: 0 },
  { id: 'm8', name: 'Phi-3-Medium', provider: 'Microsoft', type: 'translator', status: 'offline', load: 0 },
  { id: 'm9', name: 'Yi-34B', provider: '01.AI', type: 'creative', status: 'standby', load: 0 },
  { id: 'm10', name: 'InternLM-2', provider: 'Shanghai AI', type: 'translator', status: 'offline', load: 0 },
  { id: 'm11', name: 'Baichuan-4', provider: 'Baichuan', type: 'creative', status: 'standby', load: 0 },
  { id: 'm12', name: 'MiniCPM-3B', provider: 'OpenBMB', type: 'translator', status: 'offline', load: 0 },
];

export default function Firewall() {
  return (
    <div className="space-y-6">
      {/* ADC Modes */}
      <div className="status-card" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
        <h2 className="text-lg font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
          🛡 语义防火墙 · 6 ADC 高风险模式
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {adcModes.map((mode) => (
            <div key={mode.id} className="p-3 rounded-lg border" style={{ background: 'var(--bg-hover)', borderColor: 'var(--border)' }}>
              <div className="flex justify-between items-start mb-1">
                <span className="font-medium text-sm" style={{ color: 'var(--text-primary)' }}>{mode.mode}</span>
                <span className={`badge ${mode.enabled ? 'badge-success' : 'badge-muted'} text-xs`}>
                  {mode.enabled ? '🟢' : '⚫'}
                </span>
              </div>
              <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>{mode.description}</p>
              <span className={`badge text-xs mt-1 ${mode.risk === 'high' ? 'badge-danger' : 'badge-warning'}`}>
                {mode.risk === 'high' ? '高风险' : '中风险'}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Router Table */}
      <div className="status-card" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
        <h2 className="text-lg font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
          🔀 12 模型路由器
          <span className="ml-2 text-sm font-normal" style={{ color: 'var(--text-muted)' }}>
            活跃 {routerModels.filter((m) => m.status === 'active').length} · 待命 {routerModels.filter((m) => m.status === 'standby').length}
          </span>
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <th className="text-left py-2 px-3" style={{ color: 'var(--text-muted)' }}>模型</th>
                <th className="text-left py-2 px-3" style={{ color: 'var(--text-muted)' }}>提供商</th>
                <th className="text-left py-2 px-3" style={{ color: 'var(--text-muted)' }}>类型</th>
                <th className="text-left py-2 px-3" style={{ color: 'var(--text-muted)' }}>状态</th>
                <th className="text-right py-2 px-3" style={{ color: 'var(--text-muted)' }}>负载</th>
              </tr>
            </thead>
            <tbody>
              {routerModels.map((m) => (
                <tr key={m.id} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td className="py-2 px-3 font-medium" style={{ color: 'var(--text-primary)' }}>{m.name}</td>
                  <td className="py-2 px-3" style={{ color: 'var(--text-secondary)' }}>{m.provider}</td>
                  <td className="py-2 px-3">
                    <span className={`badge text-xs ${m.type === 'translator' ? 'badge-info' : 'badge-warning'}`}>
                      {m.type === 'translator' ? '翻译官' : '作家'}
                    </span>
                  </td>
                  <td className="py-2 px-3">
                    <span className={`badge text-xs ${
                      m.status === 'active' ? 'badge-success' : m.status === 'standby' ? 'badge-muted' : 'text-red-400'
                    }`}>
                      {m.status === 'active' ? '活跃' : m.status === 'standby' ? '待命' : '离线'}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right text-xs" style={{ color: 'var(--text-muted)' }}>
                    {m.load > 0 ? `${m.load}%` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
