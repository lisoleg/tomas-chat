import { useState, useEffect, useRef } from 'react';
import { useChatStore } from '@/store/chatStore';

export default function Chat() {
  const { messages, sending, loadSessions, sendMessage } = useChatStore();
  const [input, setInput] = useState('');
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => { loadSessions(); }, [loadSessions]);
  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [messages]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput('');
    await sendMessage(text);
  };

  return (
    <div className="flex flex-col h-[calc(100vh-var(--header-h)-160px)]">
      {/* Messages */}
      <div ref={listRef} className="flex-1 overflow-y-auto space-y-4 mb-4">
        {messages.length === 0 && (
          <div className="text-center py-20" style={{ color: 'var(--text-muted)' }}>
            <p className="text-4xl mb-3">💬</p>
            <p>开始对话 — 输入问题，系统将自动选择翻译官或作家引擎</p>
          </div>
        )}
        {messages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className="max-w-[75%] rounded-xl px-4 py-3"
              style={{
                background: msg.role === 'user' ? 'var(--accent-blue)' : 'var(--bg-card)',
                border: msg.role === 'user' ? 'none' : '1px solid var(--border)',
                color: msg.role === 'user' ? '#fff' : 'var(--text-primary)',
              }}
            >
              <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
              {msg.role === 'assistant' && msg.route && (
                <div className="flex items-center gap-2 mt-2 pt-2 border-t" style={{ borderColor: 'var(--border)' }}>
                  <span className="badge badge-info text-xs">
                    {msg.route === 'eml' ? '📡 EML 路由' : '✨ LLM 创作'}
                  </span>
                  {msg.confidence !== undefined && (
                    <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                      {Math.round(msg.confidence * 100)}%
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}

        {sending && (
          <div className="flex justify-start">
            <div className="px-4 py-3 rounded-xl animate-pulse"
              style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
              <span style={{ color: 'var(--text-muted)' }}>思考中...</span>
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="flex gap-3">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          placeholder="输入消息..."
          className="flex-1 px-4 py-3 rounded-xl border outline-none transition-colors text-sm"
          style={{
            background: 'var(--bg-input)',
            borderColor: 'var(--border)',
            color: 'var(--text-primary)',
          }}
          disabled={sending}
        />
        <button onClick={handleSend} disabled={sending || !input.trim()} className="btn-primary px-6">
          发送
        </button>
      </div>
    </div>
  );
}
