import { create } from 'zustand';

interface AppState {
  theme: 'dark' | 'light';
  sidebarCollapsed: boolean;
  currentPage: string;
  toggleTheme: () => void;
  toggleSidebar: () => void;
  setPage: (page: string) => void;
}

export const useAppStore = create<AppState>((set) => ({
  theme: 'dark',
  sidebarCollapsed: false,
  currentPage: 'dashboard',
  toggleTheme: () =>
    set((s) => {
      const next = s.theme === 'dark' ? 'light' : 'dark';
      document.documentElement.className = next;
      return { theme: next };
    }),
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setPage: (page) => set({ currentPage: page }),
}));
