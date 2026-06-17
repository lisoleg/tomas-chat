import { api } from './client';
import type {
  HealthResponse,
  TProcessorStats,
  TShieldStats,
  TShieldInferRequest,
  TShieldInferResponse,
  ChatSession,
  ChatMessage,
  CorpusEntry,
  ConflictRecord,
  KnowledgeTriple,
  KnowledgeGraph,
  ApiResponse,
} from '@/types';

// ===== 健康检查 =====
export async function fetchHealth(): Promise<ApiResponse<HealthResponse>> {
  return api.get<HealthResponse>('/api/health');
}

// ===== T-Processor =====
export async function fetchTProcessorStats(): Promise<ApiResponse<TProcessorStats>> {
  return api.get<TProcessorStats>('/api/tprocessor/stats');
}

export async function postTProcessorTick(vIn: number[]): Promise<ApiResponse<unknown>> {
  return api.post('/api/tprocessor/tick', { v_in: vIn });
}

// ===== T-Shield =====
export async function fetchTShieldDemo(): Promise<ApiResponse<TShieldStats>> {
  return api.get<TShieldStats>('/api/tshield/demo');
}

export async function postTShieldInfer(req: TShieldInferRequest): Promise<ApiResponse<TShieldInferResponse>> {
  return api.post<TShieldInferResponse>('/api/tshield/infer', req);
}

// ===== 聊天 =====
export async function fetchSessions(): Promise<ApiResponse<ChatSession[]>> {
  return api.get<ChatSession[]>('/api/sessions');
}

export async function postSession(payload: { message: string; session_id?: string }): Promise<ApiResponse<ChatMessage>> {
  return api.post<ChatMessage>('/api/sessions', payload);
}

// ===== 语料/蒸馏 =====
export async function fetchCorpus(): Promise<ApiResponse<CorpusEntry[]>> {
  return api.get<CorpusEntry[]>('/api/corpus');
}

export async function postCorpus(payload: { name: string; content: string }): Promise<ApiResponse<CorpusEntry>> {
  return api.post<CorpusEntry>('/api/corpus', payload);
}

export async function fetchConflicts(): Promise<ApiResponse<ConflictRecord[]>> {
  return api.get<ConflictRecord[]>('/api/conflicts');
}

// ===== 知识图谱 =====
export async function fetchKnowledgeTriples(): Promise<ApiResponse<KnowledgeTriple[]>> {
  return api.get<KnowledgeTriple[]>('/api/knowledge/triples');
}

export async function fetchKnowledgeSubjects(q?: string): Promise<ApiResponse<string[]>> {
  const path = q ? `/api/knowledge/subjects?q=${encodeURIComponent(q)}` : '/api/knowledge/subjects';
  return api.get<string[]>(path);
}

export async function fetchKnowledgeGraph(): Promise<ApiResponse<KnowledgeGraph>> {
  return api.get<KnowledgeGraph>('/api/knowledge/graph');
}

// ===== API Key =====
export async function fetchApiKey(): Promise<ApiResponse<{ key: string }>> {
  return api.get<{ key: string }>('/api/apikey');
}

export async function postApiKey(key: string): Promise<ApiResponse<{ success: boolean }>> {
  return api.post<{ success: boolean }>('/api/apikey', { key });
}

// ===== Settings =====
export async function fetchSetting(key: string): Promise<ApiResponse<{ key: string; value: unknown }>> {
  return api.get<{ key: string; value: unknown }>(`/api/settings/${key}`);
}

export async function postSetting(key: string, value: unknown): Promise<ApiResponse<{ success: boolean }>> {
  return api.post<{ success: boolean }>('/api/settings', { key, value });
}

// ===== IDO / FDE / Dual Timeline / IT-OT =====
export async function fetchIdoStats(): Promise<ApiResponse<unknown>> {
  return api.get('/api/ido/stats');
}

export async function fetchFdeStatus(): Promise<ApiResponse<unknown>> {
  return api.get('/api/fde/status');
}

export async function fetchDualTimelineStatus(): Promise<ApiResponse<unknown>> {
  return api.get('/api/dual-timeline/status');
}

export async function fetchItotKpi(): Promise<ApiResponse<unknown>> {
  return api.get('/api/itot/kpi');
}
