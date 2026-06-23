// 全局类型定义：会话、消息、API、蒸馏相关

/** 消息发送者角色 */
export type MessageRole = 'user' | 'assistant' | 'system'

/** 单条聊天消息 */
export interface ChatMessage {
  /** 消息唯一 ID（本地生成） */
  id: string
  /** 角色：用户 / 助手 / 系统 */
  role: MessageRole
  /** 消息文本内容（Markdown 格式） */
  content: string
  /** 创建时间戳（毫秒） */
  createdAt: number
  /** 是否正在流式接收中（仅 assistant 消息使用） */
  streaming?: boolean
  /** 错误标记：流式过程中失败时为 true */
  error?: boolean
  /** 生成模式：translator / creative / creative_gated / fallback / error */
  mode?: string
  /** EML 路由置信度 (0-1) */
  confidence?: number
  /** 太乙互博推理链路（φ 编码 → 概念匹配 → 路由裁决） */
  leanTrace?: string
  /** 子图顶点数 (Token Bridge 推理时) */
  subgraphVertexCount?: number
  /** 子图边数 (Token Bridge 推理时) */
  subgraphEdgeCount?: number
  /** 用户反馈 */
  feedback?: 'like' | 'dislike' | null
  /** 发给 LLM 的原始 prompt（system + user 消息原文） */
  promptTrace?: string
}

/** EML 加载状态（聊天模式用） */
export interface ChatEMLState {
  /** 是否已加载 */
  loaded: boolean
  /** 文件名 */
  fileName: string
  /** 文件大小（字节） */
  fileSize: number
  /** 顶点数 */
  vertexCount: number
  /** 边数 */
  edgeCount: number
  /** 平均 δ */
  avgDelta: number
}

/** 一个会话 */
export interface ChatSession {
  /** 会话唯一 ID */
  id: string
  /** 会话标题（默认取首条用户消息前 20 字） */
  title: string
  /** 该会话下的全部消息 */
  messages: ChatMessage[]
  /** 会话创建时间戳（毫秒） */
  createdAt: number
  /** 最后更新时间戳（毫秒），用于排序 */
  updatedAt: number
}

/** DeepSeek API 请求体 */
export interface DeepSeekRequestMessage {
  role: MessageRole
  content: string
}

/** DeepSeek API 响应（流式 chunk） */
export interface DeepSeekStreamChunk {
  id: string
  object: string
  created: number
  model: string
  choices: Array<{
    index: number
    delta: {
      role?: MessageRole
      content?: string
    }
    finish_reason: string | null
  }>
}

/** useChat Hook 的状态 */
export interface ChatState {
  /** 全部会话列表 */
  sessions: ChatSession[]
  /** 当前激活会话 ID */
  currentSessionId: string | null
  /** 是否正在请求 API */
  isLoading: boolean
}

// ===================== AEGIS + AFS 类型 =====================

/** AEGIS 引擎统计 */
export interface AEGISStats {
  /** 流水线是否运行中 */
  pipelineRunning: boolean;
  /** 当前阶段 */
  currentStage: string;
  /** 四阶段状态 */
  stageStatus: Record<'digester' | 'planner' | 'evolver' | 'critic_gate', string>;
  /** 总演进次数 */
  totalEvolutions: number;
  /** 成功演进次数 */
  successfulEvolutions: number;
  /** 因果日志条目数 */
  causalityLogLen: number;
  /** ψ-Alignment 对齐率 (0-1) */
  psiAlignmentRate: number;
  /** 四阶段平均延迟（ms） */
  avgStageLatencyMs: Record<string, number>;
  /** AFS KB 统计（后端 v3.5+） */
  afs?: AFSStats;
}

/** AFS (EML-Lite KB) 统计 */
export interface AFSStats {
  /** KB 中总边数 */
  totalEdges: number;
  /** 被 superseded 的边数（Append-Only，不删除） */
  superseded: number;
  /** USCS bucket 数量 */
  buckets: number;
  /** κ-Snap 因果日志长度 */
  kappaLogLen: number;
  /** USCS PageTable bucket 数量 */
  nBuckets: number;
  /** MUS 争端数量 */
  musDisputes: number;
  /** φ-Gate 是否启用 */
  phiGateEnabled?: boolean;
  /** ψ-对齐率 */
  psiAlignmentRate?: number;
}

/** AEGIS MUS 变体簇 */
export interface AEGISVariant {
  id: string;
  name: string;
  harnessId: string;
  crr: number;       // Capability Retention Rate
  status: 'active' | 'standby' | 'retired';
}

/** κ-Snap 因果日志条目 */
export interface CausalLogEntry {
  snapId: string;
  sessionId: string;
  subject: string;
  refId: string;
  meta: Record<string, any>;
  timestamp: Date;
}

// ===================== 蒸馏相关类型 =====================

/** 蒸馏概念 */
export interface DistillConcept {
  /** 概念名称 */
  concept: string
  /** 重要性评分 (0-1) */
  importance: number
  /** 上下文描述 */
  context: string
  /** 出现频率（从文本中统计） */
  frequency?: number
  /** 信息存在度 𝕀(X) */
  info_existence?: number
}

/** 蒸馏关系 */
export interface DistillRelation {
  /** 源概念 */
  src: string
  /** 目标概念 */
  dst: string
  /** 关系类型：is_a, part_of, causes, related_to, used_in, inspired_by */
  type: string
  /** 关系强度 (0-1) */
  strength: number
}

/** 蒸馏阶段状态 */
export type DistillPhase =
  | 'idle'
  | 'extracting_concepts'
  | 'extracting_relations'
  | 'building_graph'
  | 'done'
  | 'error'

/** 蒸馏结果 */
export interface DistillResult {
  /** 提取的概念列表 */
  concepts: DistillConcept[]
  /** 提取的关系列表 */
  relations: DistillRelation[]
  /** 平均信息存在度 */
  avgInfoExistence: number
  /** EML 文件大小（字节） */
  emlSize: number
  /** EML 二进制数据 */
  emlBuffer: ArrayBuffer | null
}

/** 应用模式：仪表盘 / 聊天 / 蒸馏 / 世界模型 / 审计 / 记忆 / 防火墙&路由 / 文档 / IDO / FDE / 双时间 / IT-OT / T-Processor / T-Shield / AEGIS / 超图数据库 / 对齐三范式 / Goal导向 */
export type AppMode = 'dashboard' | 'chat' | 'distill' | 'world-model' | 'audit' | 'memory' | 'firewall-router' | 'docs' | 'ido' | 'fde' | 'dual' | 'itot' | 'tprocessor' | 'tshield' | 'aegis' | 'hypergraph' | 'v2' | 'alignment-triad' | 'goal-agent' | 'cognitive-health' | 'grill-me' | 'luzhao-dna' | 'gat-axioms' | 'financial-world' | 'tokenized-economy' | 'superposition-geometry' | 'math-unification' | 'adaptive-library' | 'chl-isomorphism' | 'taiyi-duel'

// ===================== Token Bridge 相关类型 =====================

/** Token Bridge 加载状态 */
export interface TokenBridgeState {
  /** 是否已加载 EML 图 */
  loaded: boolean
  /** EML 图数据 */
  graph: EMLGraphData | null
  /** 加载的文件名 */
  fileName: string
  /** 文件大小（字节） */
  fileSize: number
  /** 顶点数 */
  vertexCount: number
  /** 边数 */
  edgeCount: number
  /** 平均 δ 值 */
  avgDelta: number
}

/** 概念搜索结果 */
export interface ConceptSearchResult {
  /** 查询文本 */
  query: string
  /** 匹配的概念列表 */
  matchedConcepts: Array<{
    /** 顶点 ID */
    vertexId: number
    /** 概念名称 */
    concept: string
    /** 余弦相似度 */
    similarity: number
    /** δ 值（信息存在度） */
    delta: number
  }>
  /** 子图大小 */
  subgraphSize: number
  /** 置信度 */
  confidence: number
}

/** EML 图顶点数据 */
export interface EMLVertex {
  /** 顶点 ID */
  id: number
  /** 概念名称 */
  label: string
  /** 八元数场向量（8 个 float64） */
  octonion: number[]
  /** 信息存在度 */
  delta: number
  /** 信息存在度 𝕀(X) — 冗余字段，与 delta 同义 */
  info_existence?: number
  /** 所属语料名称（如 "⚛️物理"、"🧪化学"）— 用于按语料过滤 */
  corpusName?: string
}

/** EML 图边数据 */
export interface EMLEdge {
  /** 源顶点 ID */
  src: number
  /** 目标顶点 ID */
  dst: number
  /** 边权重 */
  weight: number
  /** δ加权 */
  deltaWeight: number
  /** 结合子标志（0=普通, 1=结合子） */
  associatorFlag: number
}

/** EML 图数据（内存表示） */
export interface EMLGraphData {
  /** 顶点列表 */
  vertices: EMLVertex[]
  /** 边列表 */
  edges: EMLEdge[]
  /** Laplacian α 参数 */
  laplacianAlpha: number
  /** 图 δ 参数 */
  graphDelta: number
}
