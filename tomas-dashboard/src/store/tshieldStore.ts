import { create } from 'zustand';
import type { TShieldStats } from '@/types';
import { fetchTShieldDemo } from '@/api/endpoints';

interface TShieldState {
  stats: TShieldStats | null;
  loading: boolean;
  error: string | null;
  fetchStats: () => Promise<void>;
}

export const useTShieldStore = create<TShieldState>((set) => ({
  stats: null,
  loading: true,
  error: null,
  fetchStats: async () => {
    set({ loading: true, error: null });
    const res = await fetchTShieldDemo();
    if (res.data) {
      set({ stats: res.data, loading: false });
    } else {
      set({ error: res.error || '加载失败', loading: false });
    }
  },
}));
