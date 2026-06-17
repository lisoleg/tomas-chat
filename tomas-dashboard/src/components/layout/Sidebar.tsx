import { useNavigate, useLocation } from 'react-router-dom';
import { useAppStore } from '@/store/appStore';

const coreNav = [
  { path: '/', label: '仪表盘', icon: '◉' },
  { path: '/chat', label: 'AI 对话', icon: '💬' },
  { path: '/distill', label: '知识蒸馏', icon: '⚗' },
  { path: '/world', label: '世界模型', icon: '🌐' },
];

const engineNav = [
  { path: '/tshield', label: 'T-Shield', icon: '🛡' },
  { path: '/audit', label: '审计监控', icon: '📋' },
  { path: '/memory', label: '记忆管理', icon: '🧠' },
  { path: '/firewall', label: '防火墙·路由', icon: '🔥' },
  { path: '/zynq', label: 'Zynq 板卡', icon: '⚡' },
];

const systemNav = [
  { path: '/settings', label: '系统设置', icon: '⚙' },
];

export default function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const { sidebarCollapsed, toggleSidebar } = useAppStore();

  const isActive = (path: string) => {
    if (path === '/') return location.pathname === '/';
    return location.pathname.startsWith(path);
  };

  const sideW = sidebarCollapsed ? 'var(--sidebar-w-collapsed)' : 'var(--sidebar-w)';

  return (
    <aside
      className="fixed top-0 left-0 h-full flex flex-col border-r transition-all duration-300 z-20 overflow-hidden"
      style={{
        width: sideW,
        background: 'var(--bg-secondary)',
        borderColor: 'var(--border)',
      }}
    >
      {/* Logo */}
      <div
        className="flex items-center gap-3 px-4 border-b cursor-pointer select-none"
        style={{ height: 'var(--header-h)', borderColor: 'var(--border)' }}
        onClick={toggleSidebar}
      >
        <span className="text-2xl flex-shrink-0">☯</span>
        {!sidebarCollapsed && (
          <span className="font-bold text-lg whitespace-nowrap" style={{ color: 'var(--accent-cyan)' }}>
            TOMAS
          </span>
        )}
      </div>

      {/* Nav Sections */}
      <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-6">
        <NavSection title={sidebarCollapsed ? '' : '核心功能'} items={coreNav} />
        <NavSection title={sidebarCollapsed ? '' : 'TOMAS 引擎'} items={engineNav} />
        <NavSection title={sidebarCollapsed ? '' : '系统'} items={systemNav} />
      </nav>

      {/* Footer */}
      {!sidebarCollapsed && (
        <div className="p-4 border-t text-xs" style={{ borderColor: 'var(--border)', color: 'var(--text-muted)' }}>
          <p>TOMAS AGI v2.0</p>
          <p>太极 OS 控制台</p>
        </div>
      )}
    </aside>
  );

  function NavSection({ title, items }: { title: string; items: typeof coreNav }) {
    return (
      <div>
        {title && (
          <p className="px-3 mb-2 text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
            {title}
          </p>
        )}
        <ul className="space-y-1">
          {items.map((item) => (
            <li key={item.path}>
              <button
                onClick={() => {
                  navigate(item.path);
                }}
                className={`sidebar-link w-full text-left ${isActive(item.path) ? 'active' : ''} ${sidebarCollapsed ? 'collapsed justify-center' : ''}`}
                title={sidebarCollapsed ? item.label : undefined}
              >
                <span className="text-lg flex-shrink-0">{item.icon}</span>
                {!sidebarCollapsed && <span className="text-sm whitespace-nowrap">{item.label}</span>}
              </button>
            </li>
          ))}
        </ul>
      </div>
    );
  }
}
