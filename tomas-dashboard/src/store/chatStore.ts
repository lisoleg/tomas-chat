import { create } from 'zustand';
import type { ChatMessage, ChatSession } from '@/types';
import { fetchSessions, postSession } from '@/api/endpoints';

interface ChatState {
  messages: ChatMessage[];
  sessions: ChatSession[];
  currentSessionId: string | null;
  loading: boolean;
  sending: boolean;
  error: string | null;
  loadSessions: () => Promise<void>;
  sendMessage: (content: string) => Promise<void>;
  clearMessages: () => void;
}

let localId = 0;

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  sessions: [],
  currentSessionId: null,
  loading: true,
  sending: false,
  error: null,

  loadSessions: async () => {
    set({ loading: true, error: null });
    const res = await fetchSessions();
    if (res.data && res.data.length > 0) {
      set({
        sessions: res.data,
        currentSessionId: res.data[0].id,
        messages: res.data[0].messages || [],
        loading: false,
      });
    } else {
      set({ loading: false });
    }
  },

  sendMessage: async (content: string) => {
    const userMsg: ChatMessage = {
      id: `u${++localId}`,
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    };
    set((s) => ({ messages: [...s.messages, userMsg], sending: true }));

    try {
      const res = await postSession({ message: content, session_id: get().currentSessionId ?? undefined });
      if (res.data) {
        set((s) => ({ messages: [...s.messages, res.data as ChatMessage], sending: false }));
      } else {
        // fallback mock response
        const mockReply: ChatMessage = {
          id: `a${++localId}`,
          role: 'assistant',
          content: content.toLowerCase().includes('eml') || content.length < 10
            ? `[翻译官] 收到问题"${content}"，已从 EML 图谱检索相关概念。`
            : `[作家] 基于 ${content.length} 字符的查询，进行深度推理。`,
          route: content.length < 10 ? 'eml' : 'llm',
          confidence: content.length < 10 ? 0.89 : 0.72,
          timestamp: new Date().toISOString(),
        };
        set((s) => ({ messages: [...s.messages, mockReply], sending: false }));
      }
    } catch {
      set((s) => ({ messages: [...s.messages], sending: false, error: '发送失败' }));
    }
  },

  clearMessages: () => set({ messages: [] }),
}));
