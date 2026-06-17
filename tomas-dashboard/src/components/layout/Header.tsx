import { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { useAppStore } from '@/store/appStore';

const pageTitles: Record<string, string> = {
  '/': '仪表盘',
  '/chat': 'AI 对话',
  '/distill': '知识蒸馏',
  '/world': '世界模型',
  '/tshield': 'T-Shield 监控',
  '/audit': '审计中心',
  '/memory': '记忆管理',
  '/firewall': '防火墙 · 路由器',
  '/zynq': 'Zynq-7000 板卡',
  '/settings': '系统设置',
};

export default function Header() {
  const location = useLocation();
  const { theme, toggleTheme } = useAppStore();
  const [time, setTime] = useState('');

  useEffect(() => {
    const update = () => {
      const now = new Date();
      setTime(
        `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
      );
    };
    update();
    const id = setInterval(update, 30000);
    return () => clearInterval(id);
  }, []);

  const title = pageTitles[location.pathname] || 'TOMAS Dashboard';

  return (
    <header
      className="flex items-center justify-between px-6 border-b z-10"
      style={{
        height: 'var(--header-h)',
        background: 'var(--bg-secondary)',
        borderColor: 'var(--border)',
      }}
    >
      <h1 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
        {title}
      </h1>

      <div className="flex items-center gap-4">
        <span className="text-sm" style={{ color: 'var(--text-muted)' }}>
          {time}
        </span>
        <button
          onClick={toggleTheme}
          className="p-2 rounded-lg transition-colors hover:bg-opacity-20"
          style={{ background: 'var(--bg-hover)' }}
          title={`切换到${theme === 'dark' ? '亮色' : '暗色'}主题`}
        >
          {theme === 'dark' ? '☀️' : '🌙'}
        </button>
      </div>
    </header>
  );
}
