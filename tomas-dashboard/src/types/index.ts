export interface SubsystemStatus {
  name: string;
  label: string;
  status: 'online' | 'offline' | 'degraded' | 'unknown';
  health: number;
  description: string;
  accent: 'blue' | 'cyan' | 'green' | 'yellow' | 'red' | 'purple' | 'orange';
}

export interface TimelineEvent {
  id: string;
  timestamp: string;
  event: string;
  source: string;
  level: 'info' | 'warning' | 'error';
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  route?: 'eml' | 'llm';
  confidence?: number;
  timestamp: string;
}

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  messages: ChatMessage[];
}

export interface CorpusEntry {
  id: number;
  name: string;
  domain: string;
  size: number;
  created_at: string;
}

export interface ConflictRecord {
  id: number;
  concept_a: string;
  concept_b: string;
  similarity: number;
  resolution?: string;
}

export interface KnowledgeTriple {
  id: number;
  subject: string;
  predicate: string;
  object: string;
  i_weight?: number;
}

export interface GraphNode {
  id: string;
  label: string;
  layer: number;
  dikwp: string;
  is_dead_zero: boolean;
  value?: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  weight: number;
}

export interface KnowledgeGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface TShieldStats {
  dead_zone: {
    active: boolean;
    dead_count: number;
    warning_count: number;
    safe_count: number;
    ratio: number;
  };
  mus: {
    ambiguous_pairs: number;
    total_boxes: number;
    ratio: number;
  };
  kappa_snap: {
    current_config: string;
    event_count: number;
    latency_ms: number;
  };
}

export interface TShieldInferRequest {
  image?: string;
  detections: Array<{ box: number[]; label: string; confidence: number }>;
}

export interface TShieldInferResponse {
  scene_assessment: { i_scene: number; level: string };
  dead_zero: { dead_count: number; flagged: number[] };
  mus: { ambiguous_pairs: number; };
  kappa_snap: { config: string; };
}

export interface TProcessorStats {
  crossbar_size: number;
  dead_zero_trigger_count: number;
  mus_arbitration_count: number;
  kappa_snap_latency_ms: number;
  total_ticks: number;
}

export interface AuditEvent {
  id: string;
  timestamp: string;
  source: 'tproc' | 'spatial' | 'g_ego';
  event: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  details?: string;
}

export interface MemoryRecord {
  id: string;
  subject: string;
  predicate: string;
  object: string;
  timestamp: string;
  psi_anchor: string;
  mus_dual: boolean;
}

export interface FirewallRule {
  id: string;
  mode: string;
  description: string;
  enabled: boolean;
  risk: 'high' | 'medium' | 'low';
}

export interface RouterModel {
  id: string;
  name: string;
  provider: string;
  type: 'translator' | 'creative';
  status: 'active' | 'standby' | 'offline';
  load: number;
}

export interface ZynqResources {
  lut: number;
  lut_total: number;
  ff: number;
  ff_total: number;
  bram: number;
  bram_total: number;
  dsp: number;
  dsp_total: number;
}

export interface ZynqTelemetry {
  temperature: number;
  power_w: number;
  latency_ms: number;
}

export interface HealthResponse {
  status: string;
  version: string;
  subsystems: Record<string, string>;
}

export interface ApiResponse<T> {
  data: T | null;
  error?: string;
  status: number;
}
