import { useState, useEffect } from 'react';
import { useAppStore } from '@/store/appStore';
import { useApi } from '@/hooks/useApi';
import { fetchApiKey, postApiKey } from '@/api/endpoints';

export default function Settings() {
  const { theme, toggleTheme } = useAppStore();
  const [apiKey, setApiKey] = useState('');
  const [saved, setSaved] = useState(false);

  const { data: keyData, loading: keyLoading } = useApi<{ key: string }>(() => fetchApiKey() as ReturnType<typeof fetchApiKey>);

  useEffect(() => {
    if (keyData?.key) setApiKey(keyData.key);
  }, [keyData]);

  const handleSaveKey = async () => {
    const res = await postApiKey(apiKey);
    if (res.data) {
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* API Key */}
      <div className="status-card" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
        <h2 className="text-lg font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
          🔑 API Key
        </h2>
        {keyLoading ? (
          <div className="animate-pulse h-10 rounded-lg" style={{ background: 'var(--bg-hover)' }} />
        ) : (
          <div className="flex gap-3">
            <input
              type="password" value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-..."
              className="flex-1 px-4 py-2.5 rounded-lg border outline-none text-sm font-mono"
              style={{ background: 'var(--bg-input)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
            />
            <button onClick={handleSaveKey} className="btn-primary">
              {saved ? '✅ 已保存' : '保存'}
            </button>
          </div>
        )}
        <p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
          DeepSeek API Key，用于 LLM 蒸馏和路由后端
        </p>
      </div>

      {/* Theme */}
      <div className="status-card" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
        <h2 className="text-lg font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
          🎨 主题
        </h2>
        <div className="flex items-center gap-4">
          <button
            onClick={toggleTheme}
            className="btn-secondary flex items-center gap-2"
          >
            {theme === 'dark' ? '🌙 暗色模式' : '☀️ 亮色模式'}
          </button>
          <span className="text-sm" style={{ color: 'var(--text-muted)' }}>
            当前: {theme === 'dark' ? '暗色' : '亮色'}
          </span>
        </div>
      </div>

      {/* Model Pool */}
      <div className="status-card" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
        <h2 className="text-lg font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
          🤖 模型池配置
        </h2>
        <textarea
          readOnly
          rows={6}
          className="w-full px-4 py-3 rounded-lg border outline-none text-sm font-mono"
          style={{ background: 'var(--bg-input)', borderColor: 'var(--border)', color: 'var(--text-muted)' }}
          value={JSON.stringify([
            { id: 'deepseek-v3', type: 'translator', active: true },
            { id: 'deepseek-r1', type: 'creative', active: true },
            { id: 'qwen-2.5-72b', type: 'translator', active: false },
            { id: 'llama-3-70b', type: 'creative', active: false },
          ], null, 2)}
        />
        <p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
          模型池配置文件: tomas_agi/sim/model_pool.json · 12 个开源模型
        </p>
      </div>

      {/* About */}
      <div className="status-card" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
        <h2 className="text-lg font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
          📋 系统信息
        </h2>
        <div className="grid grid-cols-2 gap-3 text-sm">
          {[
            ['版本', 'TOMAS AGI v2.0'],
            ['后端', 'Flask (server.py)'],
            ['API 基地址', import.meta.env.VITE_API_BASE || 'http://localhost:5000'],
            ['构建', 'Vite 5 + React 18 + TypeScript'],
            ['样式', 'Tailwind CSS 3.4 (暗色/亮色)'],
            ['状态管理', 'Zustand'],
            ['3D 渲染', 'Three.js'],
            ['测试', 'Vitest + React Testing Library'],
          ].map(([k, v]) => (
            <div key={k} className="p-2 rounded-lg" style={{ background: 'var(--bg-hover)' }}>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{k}</p>
              <p className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>{v}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
