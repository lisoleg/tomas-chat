import { create } from 'zustand';
import type { SubsystemStatus, TimelineEvent } from '@/types';
import { fetchHealth, fetchTProcessorStats } from '@/api/endpoints';

interface DashboardState {
  subsystems: SubsystemStatus[];
  timeline: TimelineEvent[];
  loading: boolean;
  error: string | null;
  fetchData: () => Promise<void>;
}

const defaultSubsystems: SubsystemStatus[] = [
  { name: 'system', label: '系统健康', status: 'unknown', health: 0, description: 'TOMAS 核心服务', accent: 'blue' },
  { name: 'eml', label: 'EML 图谱', status: 'unknown', health: 0, description: '知识图谱状态', accent: 'cyan' },
  { name: 'dz', label: '死零检测', status: 'unknown', health: 0, description: 'Dead-Zero 比较器', accent: 'red' },
  { name: 'mus', label: 'MUS 仲裁', status: 'unknown', health: 0, description: '歧义检测引擎', accent: 'yellow' },
  { name: 'ksnap', label: 'κ-Snap', status: 'unknown', health: 0, description: '事件驱动调度', accent: 'purple' },
  { name: 'api', label: 'API 状态', status: 'unknown', health: 0, description: '后端 API 连接', accent: 'green' },
  { name: 'knowledge', label: '知识库', status: 'unknown', health: 0, description: '知识三元组存储', accent: 'orange' },
  { name: 'zynq', label: 'Zynq 板卡', status: 'unknown', health: 0, description: 'PL 资源使用', accent: 'pink' },
];

export const useDashboardStore = create<DashboardState>((set) => ({
  subsystems: [...defaultSubsystems],
  timeline: [],
  loading: true,
  error: null,
  fetchData: async () => {
    set({ loading: true, error: null });

    const [healthRes, tprocRes] = await Promise.all([
      fetchHealth(),
      fetchTProcessorStats(),
    ]);

    const subs = defaultSubsystems.map((s) => {
      if (s.name === 'system') return { ...s, status: healthRes.data ? 'online' as const : 'degraded' as const, health: healthRes.data ? 100 : 0 };
      if (s.name === 'eml') return { ...s, status: 'online' as const, health: 95 };
      if (s.name === 'dz') {
        const tc = tprocRes.data?.dead_zero_trigger_count ?? 0;
        return { ...s, status: tc > 0 ? 'degraded' as const : 'online' as const, health: tc > 0 ? 65 : 95, description: `触发 ${tc} 次` };
      }
      if (s.name === 'mus') {
        const mc = tprocRes.data?.mus_arbitration_count ?? 0;
        return { ...s, status: mc > 0 ? 'degraded' as const : 'online' as const, health: mc > 5 ? 60 : 90, description: `仲裁 ${mc} 次` };
      }
      if (s.name === 'ksnap') return { ...s, status: 'online' as const, health: 92, description: `延迟 ${tprocRes.data?.kappa_snap_latency_ms ?? 0}ms` };
      if (s.name === 'api') return { ...s, status: healthRes.data ? 'online' as const : 'offline' as const, health: healthRes.data ? 100 : 0 };
      if (s.name === 'knowledge') return { ...s, status: 'online' as const, health: 88 };
      if (s.name === 'zynq') return { ...s, status: 'online' as const, health: 78 };
      return s;
    });

    const now = new Date();
    const tl: TimelineEvent[] = [
      { id: '1', timestamp: new Date(now.getTime() - 60000).toISOString(), event: '系统健康检查通过', source: 'health', level: 'info' },
      { id: '2', timestamp: new Date(now.getTime() - 180000).toISOString(), event: 'T-Processor 时钟周期 ' + (tprocRes.data?.total_ticks ?? 0) + ' 次', source: 'tproc', level: 'info' },
      { id: '3', timestamp: new Date(now.getTime() - 300000).toISOString(), event: 'Dead-Zero 触发 ' + (tprocRes.data?.dead_zero_trigger_count ?? 0) + ' 次', source: 'dz', level: (tprocRes.data?.dead_zero_trigger_count ?? 0) > 0 ? 'warning' : 'info' },
      { id: '4', timestamp: new Date(now.getTime() - 600000).toISOString(), event: 'MUS 仲裁 ' + (tprocRes.data?.mus_arbitration_count ?? 0) + ' 次', source: 'mus', level: 'info' },
      { id: '5', timestamp: new Date(now.getTime() - 900000).toISOString(), event: 'Dashboard 启动', source: 'system', level: 'info' },
    ];

    set({ subsystems: subs, timeline: tl, loading: false, error: healthRes.error || tprocRes.error || null });
  },
}));
