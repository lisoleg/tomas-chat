import type { ApiResponse } from '@/types';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:5000';

class ApiClient {
  private baseUrl: string;
  private timeout: number;

  constructor(baseUrl: string, timeout = 12000) {
    this.baseUrl = baseUrl;
    this.timeout = timeout;
  }

  async request<T>(path: string, options?: RequestInit): Promise<ApiResponse<T>> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeout);

    try {
      const url = `${this.baseUrl}${path}`;
      const res = await fetch(url, {
        ...options,
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
      });

      if (!res.ok) {
        const body = await res.text();
        return { data: null, error: `HTTP ${res.status}: ${body}`, status: res.status };
      }

      const data = await res.json();
      return { data, status: res.status };
    } catch (e) {
      const msg = (e as Error).name === 'AbortError' ? '请求超时' : (e as Error).message;
      return { data: null, error: msg, status: 0 };
    } finally {
      clearTimeout(timer);
    }
  }

  async get<T>(path: string): Promise<ApiResponse<T>> {
    return this.request<T>(path);
  }

  async post<T>(path: string, body: unknown): Promise<ApiResponse<T>> {
    return this.request<T>(path, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async del<T>(path: string): Promise<ApiResponse<T>> {
    return this.request<T>(path, { method: 'DELETE' });
  }
}

export const api = new ApiClient(API_BASE);
