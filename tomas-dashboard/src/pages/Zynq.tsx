import type { ZynqResources, ZynqTelemetry } from '@/types';

const resources: ZynqResources = { lut: 28500, lut_total: 53200, ff: 42000, ff_total: 106400, bram: 95, bram_total: 140, dsp: 160, dsp_total: 220 };
const telemetry: ZynqTelemetry = { temperature: 47.2, power_w: 3.8, latency_ms: 0.85 };

function ResourceBar({ label, used, total, color }: { label: string; used: number; total: number; color: string }) {
  const pct = Math.round((used / total) * 100);
  return (
    <div className="mb-4">
      <div className="flex justify-between mb-1">
        <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{label}</span>
        <span className="text-sm" style={{ color: 'var(--text-muted)' }}>{used.toLocaleString()} / {total.toLocaleString()} ({pct}%)</span>
      </div>
      <div className="h-3 rounded-full overflow-hidden" style={{ background: 'var(--bg-hover)' }}>
        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

function TelemetryCard({ label, value, unit, color, icon }: { label: string; value: number; unit: string; color: string; icon: string }) {
  return (
    <div className="status-card text-center" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
      <span className="text-3xl">{icon}</span>
      <p className="text-2xl font-bold mt-2" style={{ color }}>{value}{unit}</p>
      <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{label}</p>
    </div>
  );
}

export default function Zynq() {
  return (
    <div className="space-y-6">
      {/* Board Info */}
      <div className="flex items-center gap-4 p-4 rounded-xl border" style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}>
        <span className="text-4xl">⚡</span>
        <div>
          <h2 className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>Xilinx Zynq-7000 XC7Z020</h2>
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            PS: ARM Cortex-A9 双核 667MHz · PL: Artix-7 FPGA · DDR3 512MB
          </p>
        </div>
        <span className="badge badge-success ml-auto">T-Shield PL 已烧录</span>
      </div>

      {/* Resource Bars */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="status-card" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
          <h3 className="text-lg font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>PL 资源使用</h3>
          <ResourceBar label="LUT" used={resources.lut} total={resources.lut_total} color="var(--accent-blue)" />
          <ResourceBar label="FF" used={resources.ff} total={resources.ff_total} color="var(--accent-cyan)" />
          <ResourceBar label="BRAM" used={resources.bram} total={resources.bram_total} color="var(--accent-purple)" />
          <ResourceBar label="DSP" used={resources.dsp} total={resources.dsp_total} color="var(--accent-orange)" />
        </div>

        {/* Telemetry */}
        <div className="grid grid-cols-1 gap-4">
          <TelemetryCard label="芯片温度" value={telemetry.temperature} unit="°C" color="var(--accent-orange)" icon="🌡" />
          <TelemetryCard label="功耗" value={telemetry.power_w} unit="W" color="var(--accent-yellow)" icon="⚡" />
          <TelemetryCard label="推理延迟" value={telemetry.latency_ms} unit="ms" color="var(--accent-green)" icon="⏱" />
        </div>
      </div>

      {/* T-Shield RTL Info */}
      <div className="status-card" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
        <h3 className="text-lg font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>T-Shield RTL 模块</h3>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 text-sm">
          {[
            { name: 'deadzone_comp_array.v', desc: 'Dead-Zero 比较器阵列 (32值/周期)', status: '✅' },
            { name: 'mus_similarity_engine.v', desc: 'MUS 流水线相似度引擎 (DSP48E1)', status: '✅' },
            { name: 'axi_lite_slave.v', desc: 'AXI4-Lite 从设备 (12寄存器)', status: '✅' },
            { name: 'tshield_pl_top.v', desc: 'PL 顶层 (DZ+MUS+AXI+BRAM)', status: '✅' },
          ].map((mod) => (
            <div key={mod.name} className="p-2 rounded-lg" style={{ background: 'var(--bg-hover)' }}>
              <p className="font-mono text-xs" style={{ color: 'var(--accent-cyan)' }}>{mod.name}</p>
              <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>{mod.desc}</p>
              <p className="text-xs mt-1">{mod.status}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
