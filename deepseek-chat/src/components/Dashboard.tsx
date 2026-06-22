import React, { useState, useEffect } from 'react';
import {
  IconBrain, IconShield, IconMemory, IconLayers,
  IconRoute, IconFlame, IconGlobe, IconAuditLog, IconCpu,
  IconLock, IconTarget, IconHeartbeat, IconSearchGavel,
  IconDna, IconGat, IconFinancial, IconToken
} from './icons';

// ── Types ──────────────────────────────────────────────

interface SubsystemCard {
  id: string;
  name: string;
  description: string;
  status: 'active' | 'idle' | 'warning' | 'offline';
  icon: React.ReactNode;
  stats: { label: string; value: string }[];
}

interface ActivityItem {
  id: string;
  timestamp: Date;
  type: 'audit' | 'memory' | 'distill' | 'route' | 'firewall' | 'hyworld';
  message: string;
  detail?: string;
}

// ── Component ──────────────────────────────────────────

export default function Dashboard() {
  const [subsystems, setSubsystems] = useState<SubsystemCard[]>([]);
  const [activities] = useState<ActivityItem[]>(generateMockActivities());
  const [activeFilters, setActiveFilters] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSubsystemStatus();
  }, []);

  const fetchSubsystemStatus = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await fetch('http://localhost:5000/api/subsystem-status');
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const result = await response.json();
      if (result.success && result.data && result.data.subsystems) {
        const cards: SubsystemCard[] = result.data.subsystems.map((sys: any) => ({
          id: sys.id,
          name: sys.name,
          description: sys.description,
          status: sys.status as SubsystemCard['status'],
          icon: getIcon(sys.icon),
          stats: sys.stats,
        }));
        
        setSubsystems(cards);
      } else {
        throw new Error(result.error || 'Failed to fetch subsystem status');
      }
    } catch (err) {
      console.error('Failed to fetch subsystem status:', err);
      setError(err instanceof Error ? err.message : 'Unknown error');
      // Fallback: use mock data
      setSubsystems(buildSubsystemCards());
    } finally {
      setLoading(false);
    }
  };

  const getIcon = (iconName: string): React.ReactNode => {
    switch (iconName) {
      case 'globe': return <IconGlobe className="w-5 h-5" />;
      case 'audit': return <IconAuditLog className="w-5 h-5" />;
      case 'shield': return <IconShield className="w-5 h-5" />;
      case 'flame': return <IconFlame className="w-5 h-5" />;
      case 'memory': return <IconMemory className="w-5 h-5" />;
      case 'layers': return <IconLayers className="w-5 h-5" />;
      case 'route': return <IconRoute className="w-5 h-5" />;
      case 'cpu': return <IconCpu className="w-5 h-5" />;
      case 'brain': return <IconBrain className="w-5 h-5" />;
      case 'lock': return <IconLock className="w-5 h-5" />;
      case 'target': return <IconTarget className="w-5 h-5" />;
      case 'heartbeat': return <IconHeartbeat className="w-5 h-5" />;
      case 'gavel': return <IconSearchGavel className="w-5 h-5" />;
      case 'dna': return <IconDna className="w-5 h-5" />;
      case 'gat': return <IconGat className="w-5 h-5" />;
      case 'financial': return <IconFinancial className="w-5 h-5" />;
      case 'token': return <IconToken className="w-5 h-5" />;
      default: return <IconCpu className="w-5 h-5" />;
    }
  };

  const toggleFilter = (type: string) => {
    const next = new Set(activeFilters);
    if (next.has(type)) next.delete(type);
    else next.add(type);
    setActiveFilters(next);
  };

  const filteredActivities = activeFilters.size === 0
    ? activities
    : activities.filter(a => activeFilters.has(a.type));

  const statusColor = (s: SubsystemCard['status']) => {
    switch (s) {
      case 'active': return 'bg-emerald-500';
      case 'idle': return 'bg-slate-500';
      case 'warning': return 'bg-amber-500';
      case 'offline': return 'bg-red-500';
    }
  };

  const activityIcon = (type: ActivityItem['type']) => {
    switch (type) {
      case 'audit': return <IconAuditLog className="w-3.5 h-3.5 text-amber-400" />;
      case 'memory': return <IconMemory className="w-3.5 h-3.5 text-violet-400" />;
      case 'distill': return <IconBrain className="w-3.5 h-3.5 text-cyan-400" />;
      case 'route': return <IconRoute className="w-3.5 h-3.5 text-blue-400" />;
      case 'firewall': return <IconFlame className="w-3.5 h-3.5 text-red-400" />;
      case 'hyworld': return <IconGlobe className="w-3.5 h-3.5 text-emerald-400" />;
    }
  };

  return (
      <div className="flex-1 overflow-y-auto p-4 md:p-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-textPrimary">TOMAS 仪表盘</h1>
        <p className="text-sm text-textSecondary mt-1">太极OS 子系统全集 — 实时状态监控与快速入口</p>
      </div>

      {/* Loading Indicator */}
      {loading && (
        <div className="mb-4 p-3 bg-chatBgAlt rounded-lg border border-borderSubtle/30 flex items-center gap-3">
          <div className="w-5 h-5 border-2 border-accent border-t-transparent rounded-full animate-spin" />
          <span className="text-sm text-textSecondary">正在加载子系统状态...</span>
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
          <p className="text-sm text-red-400">⚠️ 无法连接后端 API，已切换为离线模式</p>
          <p className="text-xs text-red-400/70 mt-1">{error}</p>
        </div>
      )}

      {/* Subsystem Grid */}
      <section className="mb-8">
        <h2 className="text-sm font-medium text-textSecondary uppercase tracking-wider mb-3">
          子系统状态
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {subsystems.map(sys => (
            <button
              key={sys.id}
              onClick={() => {
                const panelMap: Record<string, string> = {
                  hyworld: 'world-model',
                  tproc: 'audit',
                  spatial: 'audit',
                  deadzero: 'audit',
                  memos: 'memory',
                  dikwp: 'distill',
                  firewall: 'firewall-router',
                  router: 'firewall-router',
                  tprocessor: 'tprocessor',
                  tshield: 'tshield',
                  'alignment-triad': 'alignment-triad',
                  'goal-agent': 'goal-agent',
                  'cognitive-health': 'cognitive-health',
                  'grill-me': 'grill-me',
                  'luzhao-dna': 'luzhao-dna',
                  'gat-axioms': 'gat-axioms',
                  'financial-world': 'financial-world',
                  'tokenized-economy': 'tokenized-economy',
                };
                const target = panelMap[sys.id] || sys.id;
                window.dispatchEvent(new CustomEvent('tomas-nav', { detail: { panel: target } }));
              }}
              className="bg-chatBgAlt hover:bg-[#4a4b5e] transition-colors rounded-xl p-4 text-left border border-borderSubtle/30 group cursor-pointer"
            >
              <div className="flex items-start justify-between mb-2">
                <div className="w-8 h-8 rounded-lg bg-chatBg flex items-center justify-center text-textSecondary group-hover:text-accent transition-colors">
                  {sys.icon}
                </div>
                <span className={`w-2 h-2 rounded-full ${statusColor(sys.status)} ring-2 ring-chatBgAlt`} />
              </div>
              <h3 className="text-sm font-medium text-textPrimary mb-1">{sys.name}</h3>
              <p className="text-xs text-textSecondary leading-relaxed mb-2">{sys.description}</p>
              <div className="flex flex-wrap gap-2">
                {sys.stats.map((stat, i) => (
                  <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-chatBg text-textSecondary">
                    {stat.label}: <span className="text-textPrimary font-medium">{stat.value}</span>
                  </span>
                ))}
              </div>
            </button>
          ))}
        </div>
      </section>

      {/* Activity Feed */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-medium text-textSecondary uppercase tracking-wider">
            系统活动
          </h2>
          <div className="flex gap-1.5">
            {['audit', 'memory', 'distill', 'route', 'firewall', 'hyworld'].map(type => (
              <button
                key={type}
                onClick={() => toggleFilter(type)}
                className={`text-[10px] px-2 py-0.5 rounded-full transition-colors ${
                  activeFilters.has(type)
                    ? 'bg-accent/20 text-accent border border-accent/30'
                    : 'bg-chatBgAlt text-textSecondary border border-borderSubtle/20'
                }`}
              >
                {type === 'audit' ? '审计' :
                 type === 'memory' ? '记忆' :
                 type === 'distill' ? '蒸馏' :
                 type === 'route' ? '路由' :
                 type === 'firewall' ? '防火墙' :
                 'HY世界'}
              </button>
            ))}
          </div>
        </div>
        <div className="bg-chatBgAlt rounded-xl border border-borderSubtle/30 overflow-hidden">
          {filteredActivities.length === 0 ? (
            <div className="p-8 text-center text-textSecondary text-sm">无匹配活动记录</div>
          ) : (
            filteredActivities.slice(0, 20).map((item, i) => (
              <div
                key={item.id}
                className={`flex items-start gap-3 px-4 py-2.5 ${
                  i < filteredActivities.slice(0, 20).length - 1 ? 'border-b border-borderSubtle/10' : ''
                }`}
              >
                <div className="mt-0.5">{activityIcon(item.type)}</div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-textPrimary">{item.message}</p>
                  {item.detail && (
                    <p className="text-[11px] text-textSecondary mt-0.5 truncate">{item.detail}</p>
                  )}
                </div>
                <span className="text-[10px] text-textSecondary whitespace-nowrap">
                  {formatTime(item.timestamp)}
                </span>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
}

// ── Mock Data ───────────────────────────────────────────

function buildSubsystemCards(): SubsystemCard[] {
  return [
    {
      id: 'hyworld',
      name: 'HY World 2.0',
      description: '腾讯混元 3D 世界模型 — 全景→轨迹→立体→镜像四阶段管道',
      status: 'active',
      icon: <IconGlobe className="w-5 h-5" />,
      stats: [
        { label: '顶点', value: '128' },
        { label: '场景', value: '3' },
      ],
    },
    {
      id: 'tproc',
      name: 'T-Proc 审计',
      description: 'SAI 后审计层 — 死零检查 / MUS 仲裁 / G_ego 日志',
      status: 'active',
      icon: <IconAuditLog className="w-5 h-5" />,
      stats: [
        { label: '通过', value: '47' },
        { label: '拒绝', value: '3' },
      ],
    },
    {
      id: 'spatial',
      name: '空间死零审计',
      description: '3D 几何物理接地 — 重力验证 / 碰撞检测 / 空间 MUS',
      status: 'active',
      icon: <IconShield className="w-5 h-5" />,
      stats: [
        { label: '接地', value: '92%' },
        { label: '死零', value: '8%' },
      ],
    },
    {
      id: 'deadzero',
      name: '死零/MUS 门控',
      description: '核心 IP — ℐ(e) < θ_dead 拒答 / 悖论双存 / κ-Snap',
      status: 'active',
      icon: <IconFlame className="w-5 h-5" />,
      stats: [
        { label: 'θ', value: '0.15' },
        { label: 'MUS', value: '2' },
      ],
    },
    {
      id: 'memos',
      name: 'MemOS 融合层',
      description: '五点升维记忆 — 死零校验 / MUS 双存 / ψ锚 / κ-Gate / EML',
      status: 'active',
      icon: <IconMemory className="w-5 h-5" />,
      stats: [
        { label: '记忆', value: '156' },
        { label: 'ψ锚', value: '42' },
      ],
    },
    {
      id: 'dikwp',
      name: 'DIKWP 五层桥接',
      description: '数据→信息→知识→智慧→意图 — 层分布映射与语义数学',
      status: 'active',
      icon: <IconLayers className="w-5 h-5" />,
      stats: [
        { label: 'K层', value: '58%' },
        { label: 'W层', value: '12%' },
      ],
    },
    {
      id: 'firewall',
      name: '语义防火墙',
      description: '输入/输出语义审计 — 6 ADC 高风险模式 / 语义漂移检测',
      status: 'active',
      icon: <IconShield className="w-5 h-5" />,
      stats: [
        { label: '拦截', value: '0' },
        { label: '警告', value: '2' },
      ],
    },
    {
      id: 'router',
      name: '多模型路由器',
      description: '12 家开源模型池 — 按任务类型智能路由分发',
      status: 'active',
      icon: <IconRoute className="w-5 h-5" />,
      stats: [
        { label: '在线', value: '12/12' },
        { label: '请求', value: '89' },
      ],
    },
    {
      id: 'tprocessor',
      name: 'T-Processor 仿真器',
      description: 'RRAM Crossbar · DZ Comparator · MUS Arbiter · κ-Snap Scheduler',
      status: 'active',
      icon: <IconCpu className="w-5 h-5" />,
      stats: [
        { label: '周期', value: '1,420' },
        { label: '拒绝', value: '47' },
      ],
    },
    {
      id: 'tshield',
      name: 'T-Shield 认知安全',
      description: 'I-Scene 估计 · Dead-Zero Grafting · MUS 双盒 · κ-Snap · G_ego',
      status: 'active',
      icon: <IconShield className="w-5 h-5" />,
      stats: [
        { label: 'ℐ均值', value: '0.68' },
        { label: '死零', value: '18' },
      ],
    },
    {
      id: 'alignment-triad',
      name: '对齐三范式',
      description: 'ψ-Gate 语义门控 / 语义防火墙 / Grill-Me 需求审问 — 三层对齐保障',
      status: 'active',
      icon: <IconLock className="w-5 h-5" />,
      stats: [
        { label: 'ψ-Gate', value: '通过' },
        { label: '审问', value: '3' },
      ],
    },
    {
      id: 'goal-agent',
      name: 'Goal 导向智能体',
      description: '目标分解 → 执行路径 → 结果验证 — 非阻塞式 Grill 审问集成',
      status: 'active',
      icon: <IconTarget className="w-5 h-5" />,
      stats: [
        { label: '目标', value: '5' },
        { label: '完成', value: '3' },
      ],
    },
    {
      id: 'cognitive-health',
      name: '认知健康监测',
      description: '双引擎成瘾模型 (Must-Do / Feel-Better) · 习惯回路 · MUS 反思',
      status: 'active',
      icon: <IconHeartbeat className="w-5 h-5" />,
      stats: [
        { label: '状态', value: 'NORMAL' },
        { label: '偏误', value: '0' },
      ],
    },
    {
      id: 'grill-me',
      name: 'Grill-Me 需求审问',
      description: 'DIKWP 五层缺口分析 · κ-Snap 链追踪 · SHA-256 防篡改',
      status: 'active',
      icon: <IconSearchGavel className="w-5 h-5" />,
      stats: [
        { label: '缺口', value: '0' },
        { label: '门控', value: 'OPEN' },
      ],
    },
    {
      id: 'luzhao-dna',
      name: '鲁兆 DNA 基因库',
      description: '斐波那契 / 鲁加斯 / 八卦数 — 拓扑不变量与 DNA 复制检测',
      status: 'active',
      icon: <IconDna className="w-5 h-5" />,
      stats: [
        { label: '不变量', value: '35' },
        { label: '八卦', value: '8' },
      ],
    },
    {
      id: 'gat-axioms',
      name: 'GAT 广义代数理论',
      description: 'ARC DSL / 八元数代数 — 公理验证 · 自由模型 · 理论态射',
      status: 'active',
      icon: <IconGat className="w-5 h-5" />,
      stats: [
        { label: '理论', value: '2' },
        { label: '公理', value: '18' },
      ],
    },
    {
      id: 'financial-world',
      name: '金融市场世界模型',
      description: 'LOB 限价订单簿 · 做市商 · 滑点相位 · ENPV · 熔断机制',
      status: 'active',
      icon: <IconFinancial className="w-5 h-5" />,
      stats: [
        { label: '会话', value: '0' },
        { label: '价差', value: '—' },
      ],
    },
    {
      id: 'tokenized-economy',
      name: '代币化经济',
      description: '智能体市场经济 · UBI 全民基本收入 · Gini 系数 · 经济相位',
      status: 'active',
      icon: <IconToken className="w-5 h-5" />,
      stats: [
        { label: '智能体', value: '0' },
        { label: 'Gini', value: '—' },
      ],
    },
  ];
}

function generateMockActivities(): ActivityItem[] {
  const now = Date.now();
  return [
    { id: 'a1', timestamp: new Date(now - 30000), type: 'audit', message: 'T-Proc 死零检查通过 — 查询"量子纠缠机制"', detail: 'ℐ=0.72 > θ_dead=0.15 → ALLOW' },
    { id: 'a2', timestamp: new Date(now - 120000), type: 'memory', message: 'ψ-锚写入 — "用户偏好: 简洁回答"', detail: 'κ=0.63, ego_state: focused' },
    { id: 'a3', timestamp: new Date(now - 300000), type: 'distill', message: 'EML 蒸馏完成 — 物理学语料', detail: '23 概念, 47 关系, ℐ均值=0.61' },
    { id: 'a4', timestamp: new Date(now - 480000), type: 'route', message: '路由决策 — 事实查询 → Qwen2.5-7B', detail: '置信度 0.78, 任务类型: fact' },
    { id: 'a5', timestamp: new Date(now - 600000), type: 'hyworld', message: 'HY World 场景构建 — 起居室', detail: 'Stage A-D 完成, 128 空间顶点, 5 死零过滤' },
    { id: 'a6', timestamp: new Date(now - 900000), type: 'firewall', message: '语义防火墙检查通过 — 用户输入', detail: 'ADC 风险评分: 0.02 (安全), DIKWP层: Data' },
    { id: 'a7', timestamp: new Date(now - 1200000), type: 'audit', message: 'MUS 仲裁激活 — "牛顿是科学家还是炼金术士?"', detail: '悖论对: (科学家, 炼金术士) → 双存' },
    { id: 'a8', timestamp: new Date(now - 1500000), type: 'memory', message: '矛盾记忆双存 — "心主神明" ⊗ "脑主神明"', detail: 'MUS 双存, ψ锚分属不同认知态' },
    { id: 'a9', timestamp: new Date(now - 1800000), type: 'audit', message: '对齐三范式检查通过 — ψ-Gate + 语义防火墙', detail: 'ψ=0.81, ADC风险: 0.03, Grill: 0缺口' },
    { id: 'a10', timestamp: new Date(now - 2100000), type: 'memory', message: '认知健康监测 — 状态: NORMAL', detail: 'Must-Do引擎: 0偏误, Feel-Better引擎: 0成瘾' },
    { id: 'a11', timestamp: new Date(now - 2400000), type: 'firewall', message: '鲁兆DNA检测 — 斐波那契比率匹配', detail: 'Wave 2: 2.618x (φ²), Wave 3: 4.236x (φ³)' },
    { id: 'a12', timestamp: new Date(now - 2700000), type: 'route', message: 'GAT公理验证 — Octonion结合律', detail: '480/512 组合验证通过, 32组符号翻转' },
  ];
}

function formatTime(date: Date): string {
  const diff = Date.now() - date.getTime();
  if (diff < 60000) return '刚刚';
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`;
  return date.toLocaleDateString('zh-CN');
}
