// LLM 蒸馏器核心逻辑：移植 Python 版 llm_distiller.py 到 TypeScript
// 包含：概念提取、关系提取、EML 图构建、信息存在度计算、八元数映射、二进制序列化

import { streamChatCompletion } from './deepseek'
import type { DistillConcept, DistillRelation, EMLGraphData, EMLVertex, EMLEdge } from '../types'

// ===================== 常量 =====================

/** EML 文件魔数 */
const EML_MAGIC = 0x454d4c47
/** EML 版本号 */
const EML_VERSION = 0x00020000
/** 默认 Laplacian α */
const DEFAULT_LAPLACIAN_ALPHA = 0.15
/** 默认图 δ */
const DEFAULT_GRAPH_DELTA = 0.05

// ===================== 对话意图检测 =====================

/**
 * 检测查询是否为对话/闲聊型（应强制走 LLM 作家路径，不走 EML 翻译官）
 *
 * 覆盖场景：
 * - 身份/自我介绍：你是谁, 你叫什么,介绍一下自己, 你是什么
 * - 问候/寒暄：你好, 嗨, hi, hello, 早上好, 晚上好
 * - 社交/礼貌：谢谢, 不客气, 再见, 拜拜, 对不起
 * - 观点/评价：你觉得, 你认为, 怎么看, 你喜欢
 * - 能力/帮助：你能做什么, 帮帮我, 怎么用
 */
const CONVERSATIONAL_PATTERNS = [
  // 身份/自我
  /^(你是谁|你是谁呀|你叫什么|你叫什么名字|介绍一下[你自]己|你是什[么么]|what are you|who are you)/i,
  // 问候
  /^(你好|您好|嗨|hi|hello|嘿|哈喽|早[上午安]|晚[上午安]|good (morning|afternoon|evening))/i,
  // 礼貌/社交
  /^(谢谢|感谢|不客气|没关系|再见|拜拜|bye|goodbye|对不起|抱歉|好的?|嗯|哦|好吧)/i,
  // 观点/态度
  /(你觉[得认为]|你怎[么样么]看|你(的)?看法|你喜[欢不喜欢])/i,
  // 能力/帮助
  /^(你能做什|你会什|帮帮我|怎么用|如何使用|help|can you)/i,
]

export function isConversationalQuery(text: string): boolean {
  const trimmed = text.trim()
  if (trimmed.length <= 4) return true // 极短输入（如"你好"、"谢谢"）一律走作家
  return CONVERSATIONAL_PATTERNS.some(p => p.test(trimmed))
}
/** 信息存在度默认参数 */
const DEFAULT_ALPHA = 0.4
const DEFAULT_BETA = 0.4

// ===================== 辅助函数 =====================

/**
 * 从 API 返回的文本中解析 JSON 数组。
 * 先尝试去掉 ```json...``` 包裹，然后找第一个 [ 开始解析。
 */
function parseJSONArray(text: string): unknown[] {
  // 去掉 markdown 代码块包裹
  let cleaned = text.trim()
  const codeBlockMatch = cleaned.match(/```(?:json)?\s*([\s\S]*?)```/)
  if (codeBlockMatch) {
    cleaned = codeBlockMatch[1].trim()
  }

  // 找到第一个 [ 开始解析
  const startIdx = cleaned.indexOf('[')
  if (startIdx === -1) {
    throw new Error('无法在 API 响应中找到 JSON 数组')
  }
  const endIdx = cleaned.lastIndexOf(']')
  if (endIdx === -1) {
    throw new Error('无法在 API 响应中找到 JSON 数组结束标记')
  }
  const jsonStr = cleaned.slice(startIdx, endIdx + 1)
  const parsed = JSON.parse(jsonStr)
  if (!Array.isArray(parsed)) {
    throw new Error('API 返回的不是 JSON 数组')
  }
  return parsed
}

// ===================== 核心函数 =====================

/**
 * 非流式调用 DeepSeek API：复用 streamChatCompletion 但收集全部内容后一次性返回。
 */
export async function callDeepSeekAPI(
  apiKey: string,
  messages: Array<{ role: 'user' | 'assistant' | 'system'; content: string }>,
  temperature: number = 0.3,
  maxTokens: number = 4096,
  model?: string
): Promise<string> {
  let fullContent = ''

  return new Promise<string>((resolve, reject) => {
    streamChatCompletion({
      apiKey,
      messages,
      model,
      temperature,
      maxTokens,
      onDelta: (delta) => {
        fullContent += delta
      },
      onComplete: () => {
        resolve(fullContent)
      },
      onError: (err) => {
        reject(err)
      }
    })
  })
}

/**
 * 从文本中提取概念（重要性 + 描述）。
 * 调用 DeepSeek API 执行概念提取。
 */
export async function extractConcepts(
  apiKey: string,
  text: string,
  maxConcepts: number = 50
): Promise<DistillConcept[]> {
  const prompt = `你是一个知识图谱实体提取专家。参考 OwnThink 知识图谱模型
（实体 → 属性 → 值），请从以下文本中提取最多 ${maxConcepts} 个**知识实体**。

## 什么是知识实体？
知识实体是你可以为之写出有意义定义的事物。如果你只能用"一个日期"、"一个数字"、
"一个度量值"来描述它——那它就不是知识实体，不要返回。

## ✅ 正确示例
{"entity": "哥白尼", "description": "文艺复兴时期波兰天文学家，提出日心说理论，颠覆了地心说宇宙观", "tags": ["人物", "天文学"], "importance": 0.95}
{"entity": "日心说", "description": "认为太阳是宇宙中心、行星绕太阳运行的天文学理论", "tags": ["天文学", "科学理论"], "importance": 0.90}
{"entity": "文艺复兴", "description": "14-17世纪欧洲的思想文化运动，推动了科学和艺术的蓬勃发展", "tags": ["历史", "文化运动"], "importance": 0.85}

## ❌ 错误示例：绝对不能返回
{"entity": "1473年2月19日", "description": "哥白尼的出生日期"}  — entity 本身是日期值，不是实体！
{"entity": "1543年5月24日", "description": "哥白尼去世日期"}    — entity 本身是日期值，不是实体！
{"entity": "1473—1543", "description": "哥白尼的生卒年份"}    — 日期范围，不是实体！
{"entity": "1543", "description": "一个年份"}                  — 纯数字，不是实体！
{"entity": "100公里", "description": "一个距离"}               — 度量值，不是实体！
{"entity": "v2.0", "description": "版本号"}                   — 编号，不是实体！

## 要求
1. entity: 知识实体名称（2-20字，名词性，不能是日期/数字/度量）
2. description: 一句话定义（至少8个汉字，不能是"一个XX"的空洞描述）
3. tags: 1-3个分类标签（如"人物""科学""历史"等）
4. importance: 0.0~1.0 重要性评分
5. ⚠️ **核心原则：写不出有意义的定义 → 就不要返回**

以纯 JSON 数组返回：
[{"entity": "...", "description": "...", "tags": ["标签1"], "importance": 0.8}, ...]

待分析文本：
${text.slice(0, 4000)}`

  const response = await callDeepSeekAPI(
    apiKey,
    [{ role: 'user', content: prompt }],
    0.3,
    4096
  )

  const rawArray = parseJSONArray(response)

  // 后置校验：过滤描述空洞的伪实体
  const TRIVIAL_DESC_PATTERNS = [
    /^一个(日期|时间|数字|数量|年份|世纪|度量|单位|版本|编号|季度|月份|距离|重量|长度|温度|速度|数值)$/,
    /^(同上|见上|类似)$/,
    /^.{1,4}$/,  // 不足5字符
    /^(a|an|the|is|was|it)\b/i,
  ]

  // 统计每个概念在原文中出现的频率
  const conceptCounts = new Map<string, number>()
  for (const item of rawArray) {
    const raw = item as Record<string, unknown>
    const entity = String(raw.entity ?? raw.concept ?? '').trim()
    if (!entity) continue
    const regex = new RegExp(entity.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi')
    const matches = text.match(regex)
    conceptCounts.set(entity, matches ? matches.length : 0)
  }

  const concepts: DistillConcept[] = []
  for (const item of rawArray) {
    const raw = item as Record<string, unknown>
    // 兼容新旧两种 LLM 输出格式
    const concept = String(raw.entity ?? raw.concept ?? '').trim()
    if (!concept || concept.length < 2) continue

    const description = String(raw.description ?? raw.context ?? '').trim()

    // 🔍 "describe or discard" — 描述空洞的直接丢弃
    const isTrivial = TRIVIAL_DESC_PATTERNS.some(p => p.test(description))
    if (isTrivial) {
      console.log(`[distiller] 🗑 丢弃伪实体 "${concept}"：描述空洞 — "${description}"`)
      continue
    }
    // 描述不能只是 entity 本身
    if (description === concept || description.replace(/\s/g, '') === concept) {
      console.log(`[distiller] 🗑 丢弃伪实体 "${concept}"：描述等于实体名`)
      continue
    }

    const importance = typeof raw.importance === 'number' ? raw.importance : 0.5
    const tags = Array.isArray(raw.tags) ? (raw.tags as string[]).join('、') : ''

    // context = description + tags，向后兼容
    const context = tags ? `${description} [${tags}]` : description
    const frequency = conceptCounts.get(concept) ?? 0
    concepts.push({ concept, importance, context, frequency })
  }

  console.log(
    `[distiller] 提取 ${concepts.length} 个有效实体（丢弃 ${rawArray.length - concepts.length} 个伪实体）`
  )

  return concepts.slice(0, maxConcepts)
}

/**
 * 提取概念间的关系。
 * 调用 DeepSeek API 执行关系提取。
 */
export async function extractRelations(
  apiKey: string,
  concepts: DistillConcept[],
  text: string,
  maxRelations: number = 100
): Promise<DistillRelation[]> {
  const conceptNames = concepts.map((c) => c.concept)
  const conceptList = conceptNames.join('、')

  const prompt = `你是一个知识图谱构建专家。给定以下概念列表和原文，请提取这些概念之间的关系。

概念列表：${conceptList}

关系类型包括：is_a（是...的一种）、part_of（是...的一部分）、causes（导致）、related_to（相关）、used_in（用于）、inspired_by（启发）

对每个关系，请提供：
1. src: 源概念名称
2. dst: 目标概念名称
3. type: 关系类型（is_a, part_of, causes, related_to, used_in, inspired_by）
4. strength: 关系强度（0到1之间的浮点数，1最强）

请以 JSON 数组格式返回，最多 ${maxRelations} 个关系。
示例：
[
  {"src": "机器学习", "dst": "人工智能", "type": "is_a", "strength": 0.95},
  {"src": "深度学习", "dst": "机器学习", "type": "is_a", "strength": 0.9}
]

原文：
${text}`

  const response = await callDeepSeekAPI(
    apiKey,
    [{ role: 'user', content: prompt }],
    0.3,
    4096
  )

  const rawArray = parseJSONArray(response)

  const relations: DistillRelation[] = rawArray.map((item) => {
    const raw = item as Record<string, unknown>
    const src = String(raw.src ?? '').trim()
    const dst = String(raw.dst ?? '').trim()
    const type = String(raw.type ?? 'related_to').trim()
    const strength = typeof raw.strength === 'number' ? raw.strength : 0.5
    return { src, dst, type, strength }
  }).filter((r) => r.src.length > 0 && r.dst.length > 0)

  return relations.slice(0, maxRelations)
}

/**
 * 计算信息存在度 𝕀(X)
 * 𝕀(X) = α·norm_freq + β·importance + (1-α-β)·consistency
 * norm_freq = log(1 + frequency) / log(1 + max(frequency, 1))
 */
export function computeInfoExistence(
  frequency: number,
  importance: number,
  consistency: number,
  alpha: number = DEFAULT_ALPHA,
  beta: number = DEFAULT_BETA
): number {
  const maxFreq = Math.max(frequency, 1)
  const normFreq = Math.log1p(frequency) / Math.log1p(maxFreq)
  const gamma = 1 - alpha - beta
  return alpha * normFreq + beta * importance + gamma * consistency
}

/**
 * 将文本映射到八元数空间（8 维向量）。
 * 使用 SubtleCrypto SHA-256 生成 8 个 float64 值。
 * phi[0] = text.length / 100.0
 * phi[1] = (空格数) / max(text.length, 1)
 * phi[2..7] 从 SHA-256 哈希派生
 */
export async function textToOctonion(
  text: string,
  dimension: number = 8
): Promise<number[]> {
  const phi: number[] = new Array(dimension).fill(0)

  // 前两个维度基于文本统计特征
  phi[0] = text.length / 100.0
  phi[1] = (text.split(' ').length - 1) / Math.max(text.length, 1)

  // 使用 SHA-256 哈希派生剩余维度
  const encoder = new TextEncoder()
  const data = encoder.encode(text)
  const hashBuffer = await crypto.subtle.digest('SHA-256', data)
  const hashArray = new Uint8Array(hashBuffer)

  // 从 32 字节哈希中提取 6 个 float64 值（每个用 4 字节构建 float）
  for (let i = 2; i < dimension; i++) {
    const offset = (i - 2) * 4
    // 用 4 字节构造一个浮点数，映射到 [0, 1)
    let value = 0
    for (let j = 0; j < 4; j++) {
      const byteIdx = (offset + j) % hashArray.length
      value = value * 256 + hashArray[byteIdx]
    }
    // 归一化到 [-1, 1] 范围
    phi[i] = (value / (256 ** 4 - 1)) * 2 - 1
  }

  return phi
}

/**
 * 构建内存中的 EML 图（顶点 + 八元数场 + δ加权边）
 */
export async function buildEMLGraph(
  concepts: DistillConcept[],
  relations: DistillRelation[],
  laplacianAlpha: number = DEFAULT_LAPLACIAN_ALPHA,
  graphDelta: number = DEFAULT_GRAPH_DELTA
): Promise<EMLGraphData> {
  // 构建概念名称 → ID 映射
  const conceptToId = new Map<string, number>()
  concepts.forEach((c, idx) => {
    conceptToId.set(c.concept, idx)
  })

  // 计算最大频率用于归一化
  const maxFrequency = Math.max(...concepts.map((c) => c.frequency ?? 0), 1)

  // 构建顶点：计算信息存在度 + 八元数映射
  const vertices: EMLVertex[] = []
  for (let i = 0; i < concepts.length; i++) {
    const c = concepts[i]
    const freq = c.frequency ?? 0
    const consistency = freq > 0 ? Math.min(freq / maxFrequency, 1) : 0.1
    const infoExistence = computeInfoExistence(freq, c.importance, consistency)

    // 更新概念的信息存在度
    c.info_existence = infoExistence

    // 八元数映射
    const octonion = await textToOctonion(c.concept + ' ' + c.context)

    vertices.push({
      id: i,
      label: c.concept,
      octonion,
      delta: infoExistence
    })
  }

  // 构建边
  const edges: EMLEdge[] = []
  for (const rel of relations) {
    const srcId = conceptToId.get(rel.src)
    const dstId = conceptToId.get(rel.dst)
    if (srcId === undefined || dstId === undefined) continue

    // δ加权 = strength × (srcDelta + dstDelta) / 2
    const srcDelta = vertices[srcId].delta
    const dstDelta = vertices[dstId].delta
    const deltaWeight = rel.strength * (srcDelta + dstDelta) / 2

    // 结合子标志：causes 和 inspired_by 关系标记为结合子
    const associatorFlag = (rel.type === 'causes' || rel.type === 'inspired_by') ? 1 : 0

    edges.push({
      src: srcId,
      dst: dstId,
      weight: rel.strength,
      deltaWeight,
      associatorFlag
    })
  }

  return {
    vertices,
    edges,
    laplacianAlpha,
    graphDelta
  }
}

/**
 * 序列化 EML 图为与 Python 版兼容的二进制格式。
 *
 * Header: magic(uint32) + version(uint32) + numVertices(uint32) + numEdges(uint32)
 *         + laplacianAlpha(float64) + graphDelta(float64) + timestamp(uint64) + padding(4×uint64)
 * Vertex: id(int32) + padding(int32) + 8×octonion(float64) + delta(float64)
 * Edge:   src(int32) + dst(int32) + weight(float64) + deltaWeight(float64)
 *         + associatorFlag(int32) + padding(int32)
 */
export function serializeEML(graphData: EMLGraphData): ArrayBuffer {
  const { vertices, edges, laplacianAlpha, graphDelta } = graphData

  // 计算各部分字节大小
  // Header: 4+4+4+4 + 8+8 + 8 + 8*4 = 16 + 16 + 8 + 32 = 72 字节
  const headerSize = 72
  // Vertex: 4+4 + 8*8 + 8 = 8 + 64 + 8 = 80 字节
  const vertexSize = 80
  // Edge: 4+4 + 8+8 + 4+4 = 8 + 16 + 8 = 32 字节
  const edgeSize = 32

  const totalSize = headerSize + vertices.length * vertexSize + edges.length * edgeSize
  const buffer = new ArrayBuffer(totalSize)
  const view = new DataView(buffer)

  let offset = 0

  // ---- Header ----
  view.setUint32(offset, EML_MAGIC, true); offset += 4        // magic
  view.setUint32(offset, EML_VERSION, true); offset += 4      // version
  view.setUint32(offset, vertices.length, true); offset += 4  // numVertices
  view.setUint32(offset, edges.length, true); offset += 4     // numEdges
  view.setFloat64(offset, laplacianAlpha, true); offset += 8  // laplacianAlpha
  view.setFloat64(offset, graphDelta, true); offset += 8      // graphDelta
  // timestamp (uint64, 用两个 uint32 模拟)
  const timestamp = BigInt(Date.now())
  view.setUint32(offset, Number(timestamp & BigInt(0xFFFFFFFF)), true); offset += 4
  view.setUint32(offset, Number((timestamp >> BigInt(32)) & BigInt(0xFFFFFFFF)), true); offset += 4
  // padding: 4 × uint64 (每个用两个 uint32 填零)
  for (let i = 0; i < 8; i++) {
    view.setUint32(offset, 0, true); offset += 4
  }

  // ---- Vertices ----
  for (const vertex of vertices) {
    view.setInt32(offset, vertex.id, true); offset += 4    // id
    view.setInt32(offset, 0, true); offset += 4             // padding
    // 8 个八元数分量
    for (let i = 0; i < 8; i++) {
      view.setFloat64(offset, vertex.octonion[i] ?? 0, true); offset += 8
    }
    view.setFloat64(offset, vertex.delta, true); offset += 8 // delta (信息存在度)
  }

  // ---- Edges ----
  for (const edge of edges) {
    view.setInt32(offset, edge.src, true); offset += 4       // src
    view.setInt32(offset, edge.dst, true); offset += 4       // dst
    view.setFloat64(offset, edge.weight, true); offset += 8  // weight
    view.setFloat64(offset, edge.deltaWeight, true); offset += 8  // deltaWeight
    view.setInt32(offset, edge.associatorFlag, true); offset += 4  // associatorFlag
    view.setInt32(offset, 0, true); offset += 4              // padding
  }

  return buffer
}

/**
 * 在浏览器端触发 EML 文件下载。
 */
export function downloadEMLFile(buffer: ArrayBuffer, filename: string = 'knowledge_graph.eml'): void {
  const blob = new Blob([buffer], { type: 'application/octet-stream' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  // 清理
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/**
 * 格式化文件大小为人类可读字符串。
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// ===================== Token Bridge: EML 加载 + 本地推理 =====================

/**
 * 从 ArrayBuffer 解析 EML 二进制文件为内存中的图数据。
 * 格式与 Python 版 llm_distiller.py 完全兼容。
 */
export function loadEMLFromBuffer(buffer: ArrayBuffer): EMLGraphData {
  const view = new DataView(buffer)
  const HEADER_SIZE = 72
  const VERTEX_SIZE = 80
  const EDGE_SIZE = 32

  // ---- Header ----
  const magic = view.getUint32(0, true)
  if (magic !== EML_MAGIC) {
    throw new Error(`无效 EML 魔数：0x${magic.toString(16).toUpperCase()}`)
  }
  const numVertices = view.getUint32(8, true)
  const numEdges = view.getUint32(12, true)
  const laplacianAlpha = view.getFloat64(16, true)
  const graphDelta = view.getFloat64(24, true)

  // ---- Vertices ----
  const vertices: EMLVertex[] = []
  for (let i = 0; i < numVertices; i++) {
    const off = HEADER_SIZE + i * VERTEX_SIZE
    const id = view.getInt32(off, true)
    // padding at off+4
    const octonion: number[] = []
    for (let d = 0; d < 8; d++) {
      octonion.push(view.getFloat64(off + 8 + d * 8, true))
    }
    const delta = view.getFloat64(off + 72, true)
    vertices.push({ id, label: '', octonion, delta }) // 标签留空，由 loadConceptNames / 外部映射补充真实概念名
  }

  // ---- Edges ----
  const edges: EMLEdge[] = []
  const edgeOffset = HEADER_SIZE + numVertices * VERTEX_SIZE
  for (let i = 0; i < numEdges; i++) {
    const off = edgeOffset + i * EDGE_SIZE
    const src = view.getInt32(off, true)
    const dst = view.getInt32(off + 4, true)
    const weight = view.getFloat64(off + 8, true)
    const deltaWeight = view.getFloat64(off + 16, true)
    const associatorFlag = view.getInt32(off + 24, true)
    edges.push({ src, dst, weight, deltaWeight, associatorFlag })
  }

  return { vertices, edges, laplacianAlpha, graphDelta }
}

/**
 * Token Bridge 客户端（浏览器端本地推理，不需要后端/LLM）
 */
export class TokenBridgeClient {
  private graph: EMLGraphData | null = null
  private phiMatrix: number[][] = []     // 每个顶点的 φ 向量
  private phiNorms: number[] = []        // 每个顶点的 φ L2 范数
  private adjacency: Map<number, number[]> = new Map() // 邻接表

  /** 从 JSON 对象加载概念名称（概念 ID → 概念文本） */
  loadConceptNames(conceptNames: Map<number, string>): void {
    if (!this.graph) return
    for (const v of this.graph.vertices) {
      const name = conceptNames.get(v.id)
      if (name) v.label = name
    }
  }

  /** 从 JSON 对象加载概念名称（支持新格式，含 domain/corpusName） */
  loadConceptNamesFromJson(jsonData: { domain?: string; concepts: Array<{ id: number; concept: string; domain?: string }> }): void {
    if (!this.graph) return
    const domain = jsonData.domain ?? ''
    for (const c of jsonData.concepts) {
      const v = this.graph.vertices[c.id]
      if (v) {
        v.label = c.concept
        // 如果有 domain 字段，写入 corpusName（用于前端语料过滤）
        if (c.domain ?? domain) {
          v.corpusName = (c.domain ?? domain) as string
        }
      }
    }
  }

  /** 获取当前图数据（只读） */
  getGraph(): EMLGraphData | null {
    return this.graph
  }

  /** 加载 EML 图（从 ArrayBuffer 或已解析的 EMLGraphData） */
  loadEML(source: ArrayBuffer | EMLGraphData, conceptNames?: Map<number, string>): void {
    this.graph = source instanceof ArrayBuffer ? loadEMLFromBuffer(source) : source

    // 可选：从外部加载概念名称
    if (conceptNames) {
      for (const v of this.graph.vertices) {
        const name = conceptNames.get(v.id)
        if (name) v.label = name
      }
    }

    // 构建 φ 矩阵和范数
    this.phiMatrix = this.graph.vertices.map(v => v.octonion)
    this.phiNorms = this.phiMatrix.map(phi => {
      const norm = Math.sqrt(phi.reduce((s, x) => s + x * x, 0))
      return Math.max(norm, 1e-10)
    })

    // 构建邻接表
    this.adjacency = new Map()
    for (let i = 0; i < this.graph.vertices.length; i++) {
      this.adjacency.set(i, [])
    }
    for (let i = 0; i < this.graph.edges.length; i++) {
      const e = this.graph.edges[i]
      if (this.adjacency.has(e.src)) this.adjacency.get(e.src)!.push(i)
      if (this.adjacency.has(e.dst)) this.adjacency.get(e.dst)!.push(i)
    }
  }

  /** 文本 → 八元数 φ（与 Python text_to_octonion 一致） */
  async textToPhi(text: string): Promise<number[]> {
    return await textToOctonion(text)
  }

  /** 在 φ 空间中查找最近概念（余弦相似度） */
  findNearestConcepts(phi: number[], topK: number = 5): Array<{
    vertexId: number; concept: string; similarity: number; delta: number
  }> {
    if (!this.graph) return []

    // 归一化查询向量
    const queryNorm = Math.sqrt(phi.reduce((s, x) => s + x * x, 0))
    if (queryNorm < 1e-10) return []
    const queryNorm2 = phi.map(x => x / queryNorm)

    // 计算余弦相似度
    const sims = this.phiMatrix.map((vphi, i) => {
      const vNorm = this.phiNorms[i]
      let dot = 0
      for (let d = 0; d < vphi.length; d++) {
        dot += queryNorm2[d] * (vphi[d] / vNorm)
      }
      return { idx: i, sim: dot }
    })

    // 排序取 topK
    sims.sort((a, b) => b.sim - a.sim)
    return sims.slice(0, topK).map(s => ({
      vertexId: this.graph!.vertices[s.idx].id,
      concept: this.graph!.vertices[s.idx].label,
      similarity: s.sim,
      delta: this.graph!.vertices[s.idx].delta
    }))
  }

  /** BFS 子图扩展 */
  extractSubgraph(vertexIds: number[], radius: number = 2): {
    vertexCount: number; edgeCount: number
  } {
    if (!this.graph) return { vertexCount: 0, edgeCount: 0 }

    const visited = new Set(vertexIds)
    const queue: Array<[number, number]> = vertexIds.map(id => [id, 0])
    const edgeSet = new Set<number>()

    while (queue.length > 0) {
      const [vid, dist] = queue.shift()!
      if (dist >= radius) continue

      for (const eidx of this.adjacency.get(vid) ?? []) {
        edgeSet.add(eidx)
        const edge = this.graph.edges[eidx]
        const neighbor = edge.src === vid ? edge.dst : edge.src
        if (!visited.has(neighbor) && neighbor < this.graph.vertices.length) {
          visited.add(neighbor)
          queue.push([neighbor, dist + 1])
        }
      }
    }

    return { vertexCount: visited.size, edgeCount: edgeSet.size }
  }

  /** 完整搜索：文本 → φ → 最近邻 → 子图 */
  async search(query: string, topK: number = 5): Promise<{
    query: string
    matchedConcepts: Array<{ vertexId: number; concept: string; similarity: number; delta: number }>
    subgraphSize: number
    confidence: number
  }> {
    const phi = await this.textToPhi(query)
    const matched = this.findNearestConcepts(phi, topK)
    const matchedIds = matched.filter(m => m.similarity > 0.3).map(m => m.vertexId)
    const sg = matchedIds.length > 0 ? this.extractSubgraph(matchedIds) : { vertexCount: 0, edgeCount: 0 }
    const confidence = matched.length > 0 ? matched[0].similarity : 0

    return {
      query,
      matchedConcepts: matched,
      subgraphSize: sg.vertexCount + sg.edgeCount,
      confidence
    }
  }

  /**
   * 智能对话生成：翻译官（模板）+ 作家（DeepSeek LLM）混合架构
   *
   * 路由逻辑：
   *   - 高置信度(≥0.5)：翻译官模板生成（事实复述）
   *   - 低置信度(<0.5)：作家 DeepSeek LLM（创造性生成）+ EML 上下文
   *
   * @param query - 用户查询
   * @param maxLen - 最大生成长度
   * @param options.llmApiKey - DeepSeek API Key（启用作家模式时必填）
   * @param options.llmModel - LLM 模型名（默认 deepseek-chat）
   * @param options.forceCreative - 强制使用作家
   * @param options.forceTranslator - 强制使用翻译官
   * @returns 生成结果 { text, mode, confidence }
   */
  async generateResponse(query: string, maxLen: number = 500, options?: {
    llmApiKey?: string
    llmModel?: string
    forceCreative?: boolean
    forceTranslator?: boolean
  }): Promise<{ text: string; mode: string; confidence: number }> {
    if (!this.graph) return { text: '❌ 请先加载 EML 图文件。', mode: 'error', confidence: 0 }

    const text = query.trim()
    if (!text) return { text: '请输入查询内容。', mode: 'error', confidence: 0 }

    // Step 1: EML 概念搜索
    const phi = this.textToPhiSync(text)
    let matched = phi ? this.findNearestConcepts(phi, 5) : []
    if (matched.length === 0) {
      matched = this.fuzzyMatch(text, 5)
    }

    const confidence = matched.length > 0 ? matched[0].similarity : 0

    if (matched.length === 0) {
      return {
        text: `抱歉，我在当前知识库中没有找到与「${text}」相关的概念。请先通过蒸馏功能添加相关知识。`,
        mode: 'translator',
        confidence: 0
      }
    }

    // Step 2: 路由判断
    // 对话型查询（问候/身份/闲聊）→ 强制走作家路径，不管 EML 置信度多高
    const isChat = isConversationalQuery(query)
    const useCreative = isChat || options?.forceCreative
      || (!options?.forceTranslator
          && confidence < 0.5
          && !!options?.llmApiKey)

    if (useCreative) {
      return this._generateCreative(query, matched, confidence, options!)
    }

    // Step 3: 翻译官模式（模板生成）
    const conceptNames = new Map<number, string>()
    for (const v of this.graph.vertices) {
      conceptNames.set(v.id, v.label)
    }

    const matchedIds = matched.filter(m => m.similarity > 0.3).map(m => m.vertexId)
    const subgraph = matchedIds.length > 0
      ? this.extractSubgraphDetailed(matchedIds, 2)
      : { vertices: [], edges: [] }

    const translatorText = this._templateGenerate(
      query, matched, subgraph.vertices, subgraph.edges, conceptNames, maxLen
    )

    return { text: translatorText, mode: 'translator', confidence }
  }

  /**
   * 作家模式：DeepSeek LLM 创造性生成（带入 EML 上下文）
   */
  private async _generateCreative(
    query: string,
    matched: Array<{ vertexId: number; concept: string; similarity: number; delta: number }>,
    confidence: number,
    options: { llmApiKey?: string; llmModel?: string }
  ): Promise<{ text: string; mode: string; confidence: number }> {
    if (!options.llmApiKey) {
      // 无 API Key，回退到翻译官
      const conceptNames = new Map<number, string>()
      if (this.graph) {
        for (const v of this.graph.vertices) {
          conceptNames.set(v.id, v.label)
        }
      }
      const subgraph = this.extractSubgraphDetailed(
        matched.filter(m => m.similarity > 0.3).map(m => m.vertexId), 2
      )
      return {
        text: `⚠️ 未设置 DeepSeek API Key，作家模式不可用。\n\n` +
          this._templateGenerate(query, matched, subgraph.vertices, subgraph.edges, conceptNames, 500),
        mode: 'fallback',
        confidence
      }
    }

    // 构建 EML 知识图谱上下文
    const emlContext = this._buildEMLContext(matched)

    // 构建 DeepSeek 消息
    const messages: Array<{ role: 'user' | 'assistant' | 'system'; content: string }> = [
      {
        role: 'system',
        content: `你是 TOMAS/太极OS 的创造性引擎。你的回答应基于提供的 EML 知识图谱上下文。

规则：
1. 如果上下文提供了明确信息，优先基于上下文回答
2. 如果上下文不足，可以基于你的知识进行创造性扩展，但需注明来源
3. 保持回答专业、准确、简洁
4. 用中文回答
5. 不要编造不存在的概念或事实`
      },
    ]

    if (emlContext) {
      messages.push({
        role: 'system',
        content: `以下是 EML 知识图谱中的相关概念和关系，请优先参考：\n\n${emlContext}`
      })
    }

    messages.push({ role: 'user', content: query })

    try {
      const llmOutput = await callDeepSeekAPI(
        options.llmApiKey,
        messages,
        0.7,  // temperature for creative
        4096, // maxTokens
        options.llmModel || 'deepseek-chat'
      )
      return { text: llmOutput, mode: 'creative', confidence }
    } catch (e: any) {
      console.error('DeepSeek API 调用失败:', e)
      const conceptNames = new Map<number, string>()
      if (this.graph) {
        for (const v of this.graph.vertices) {
          conceptNames.set(v.id, v.label)
        }
      }
      const subgraph = this.extractSubgraphDetailed(
        matched.filter(m => m.similarity > 0.3).map(m => m.vertexId), 2
      )
      return {
        text: `⚠️ LLM 调用失败：${e?.message || '未知错误'}\n\n回退到翻译官：\n\n` +
          this._templateGenerate(query, matched, subgraph.vertices, subgraph.edges, conceptNames, 500),
        mode: 'fallback',
        confidence
      }
    }
  }

  /**
   * 公共方法：查询 + 构建 EML 上下文（供 useChat 流式路由使用）
   * 返回匹配概念、置信度、EML 上下文文本
   */
  async searchAndGetContext(query: string): Promise<{
    matched: Array<{ vertexId: number; concept: string; similarity: number; delta: number }>
    confidence: number
    emlContext: string
    phi: number[] | null
  }> {
    if (!this.graph) return { matched: [], confidence: 0, emlContext: '', phi: null }

    const phi = this.textToPhiSync(query)
    let matched = phi ? this.findNearestConcepts(phi, 5) : []
    if (matched.length === 0) {
      matched = this.fuzzyMatch(query, 5)
    }
    const confidence = matched.length > 0 ? matched[0].similarity : 0
    const emlContext = this._buildEMLContext(matched)

    return { matched, confidence, emlContext, phi }
  }

  /**
   * 公共方法：翻译官模板回复（供 useChat 路由使用）
   * @param query 用户查询
   * @param matched 已匹配概念列表
   * @param maxLen 最大长度
   */
  translatorResponse(
    query: string,
    matched: Array<{ vertexId: number; concept: string; similarity: number; delta: number }>,
    maxLen: number = 500
  ): { text: string; mode: string; confidence: number } {
    if (!this.graph) return { text: '', mode: 'error', confidence: 0 }

    const conceptNames = new Map<number, string>()
    for (const v of this.graph.vertices) {
      conceptNames.set(v.id, v.label)
    }

    const matchedIds = matched.filter(m => m.similarity > 0.3).map(m => m.vertexId)
    const subgraph = matchedIds.length > 0
      ? this.extractSubgraphDetailed(matchedIds, 2)
      : { vertices: [], edges: [] }

    const text = this._templateGenerate(
      query, matched, subgraph.vertices, subgraph.edges, conceptNames, maxLen
    )

    const confidence = matched.length > 0 ? matched[0].similarity : 0
    return { text, mode: 'translator', confidence }
  }

  /**
   * 生成太乙互博推理链路（φ 编码 → 概念匹配 → 子图 BFS → 路由裁决）
   * 以 LEAN 风格的证明格式展示 AI 内部推理过程
   */
  buildLeanTrace(
    query: string,
    matched: Array<{ vertexId: number; concept: string; similarity: number; delta: number }>,
    confidence: number,
    mode: string,
    phi?: number[]
  ): string {
    if (!this.graph) return ''

    const lines: string[] = []
    lines.push(';; ─── 太乙互博 · φ-空间推理链路 ───')
    lines.push('')

    // Step 1: φ 编码
    lines.push('-- 阶段1：文本 → φ 八元数编码')
    lines.push(`  query ∷= "${query.length > 40 ? query.slice(0, 40) + '…' : query}"`)
    if (phi && phi.length === 8) {
      lines.push(`  φ(query) ∷= [${phi.map(v => v.toFixed(4)).join(', ')}]`)
      const components = ['|ψ|', '空格率', 'c3', 'c4', 'c5', 'c6', 'c7', 'c8']
      lines.push(`  -- ${components.map((c, i) => `${c}=${phi[i].toFixed(4)}`).join('  ')}`)
    } else {
      lines.push('  φ ∷= SHA256 ⟶ ℝ⁸ (未缓存)')
    }
    lines.push('')

    // Step 2: 概念匹配
    lines.push('-- 阶段2：φ 空间最近邻搜索（余弦相似度）')
    lines.push(`  top_k ∷= ${matched.length}`)
    if (matched.length === 0) {
      lines.push('  matched_concepts ∷= []  -- 无匹配')
    } else {
      lines.push('  matched_concepts ∷= [')
      for (let i = 0; i < matched.length; i++) {
        const m = matched[i]
        const bar = '█'.repeat(Math.min(10, Math.floor(m.similarity * 10)))
        const spc = '·'.repeat(Math.max(0, 10 - Math.floor(m.similarity * 10)))
        const deltaFlag = m.delta > 0.7 ? '⟐' : m.delta > 0.4 ? '◈' : '◇'
        lines.push(`    (${i + 1}) { concept := "${m.concept}"`)
        lines.push(`        , cos_sim := ${(m.similarity * 100).toFixed(1)}%  -- ${bar}${spc}`)
        lines.push(`        , 𝕀(δ)   := ${m.delta.toFixed(4)}  ${deltaFlag}`)
        lines.push(`        }${i < matched.length - 1 ? ',' : ''}`)
      }
      lines.push('  ]')
    }
    lines.push('')

    // Step 3: 子图扩展
    const matchedIds = matched.filter(m => m.similarity > 0.3).map(m => m.vertexId)
    if (matchedIds.length > 0) {
      const sg = this.extractSubgraph(matchedIds, 2)
      lines.push('-- 阶段3：BFS 子图扩展 (radius=2)')
      lines.push(`  种子 ∷= {${matchedIds.join(', ')}} -- ${matchedIds.length} 个高置信概念`)
      lines.push(`  子图 ∷= V=${sg.vertexCount} (+${sg.vertexCount - matchedIds.length} 扩展)  E=${sg.edgeCount}`)
      lines.push('')
    }

    // Step 4: 路由裁决 — 太乙判决
    lines.push('-- 阶段4：太乙路由裁决')
    const threshold = 0.5
    const verdict = confidence >= threshold ? 'TRANSLATOR' : 'CREATIVE'
    lines.push(`  confidence ∷= ${(confidence * 100).toFixed(1)}%`)
    lines.push(`  threshold  ∷= ${(threshold * 100).toFixed(0)}%`)
    lines.push(`  rule       ∷= conf ≥ thresh → TRANSLATOR | conf < thresh → CREATIVE`)
    lines.push(`  verdict    ∷= ${verdict}  -- ${confidence >= threshold ? '∵ 高置信 → 事实性查询' : '∵ 低置信 → 创造性查询'}`)
    lines.push('')

    // Step 5: 执行模式
    const modeEmoji = mode === 'translator' ? '📖 翻译官' 
      : mode === 'creative' ? '✍️ 作家'
      : mode === 'fallback' ? '🔄 回退'
      : `❓ ${mode}`
    lines.push(`-- 最终执行 ∷= ${modeEmoji}`)
    if (mode === 'translator') {
      lines.push('  策略：模板 LSTM → 从 EML 图检索事实 → 结构化组装')
    } else if (mode === 'creative') {
      lines.push('  策略：DeepSeek LLM + EML 上下文 → 创造性生成 → φ-Gate 监管')
    }

    return lines.join('\n')
  }

  /** 构建 EML 上下文文本（格式化后发给 LLM） */
  private _buildEMLContext(matched: Array<{
    vertexId: number; concept: string; similarity: number; delta: number
  }>): string {
    if (!this.graph) return ''

    const lines: string[] = []

    // 匹配概念
    lines.push('【EML 知识图谱相关概念】')
    for (let i = 0; i < Math.min(matched.length, 5); i++) {
      const m = matched[i]
      const simBar = '█'.repeat(Math.floor(m.similarity * 10))
      lines.push(`  ${i + 1}. ${simBar} ${m.concept} (相似度 ${(m.similarity * 100).toFixed(0)}%, δ=${m.delta.toFixed(3)})`)
    }

    // 扩展子图
    const matchedIds = matched.filter(m => m.similarity > 0.3).map(m => m.vertexId)
    const subgraph = this.extractSubgraphDetailed(matchedIds, 2)

    // 构建名称映射
    const nameMap = new Map<number, string>()
    for (const v of subgraph.vertices) {
      nameMap.set(v.id, v.concept)
    }

    if (subgraph.vertices.length > 0) {
      lines.push(`\n【关联子图：${subgraph.vertices.length} 概念 + ${subgraph.edges.length} 关系】`)

      const matchedNames = new Set(matched.map(m => m.concept))
      const extended = subgraph.vertices.filter(v => !matchedNames.has(v.concept))
      if (extended.length > 0) {
        lines.push('  扩展概念：')
        for (const v of extended.slice(0, 10)) {
          lines.push(`    • ${v.concept}`)
        }
      }

      if (subgraph.edges.length > 0) {
        lines.push('  关键关系：')
        for (const e of subgraph.edges.slice(0, 8)) {
          const srcName = nameMap.get(e.src) || `v${e.src}`
          const dstName = nameMap.get(e.dst) || `v${e.dst}`
          lines.push(`    ${srcName} → ${dstName} (权重 ${e.weight.toFixed(3)})`)
        }
      }
    }

    return lines.join('\n')
  }

  /** 文本模糊匹配（不依赖 φ 空间） */
  fuzzyMatch(query: string, topK: number = 5): Array<{ vertexId: number; concept: string; similarity: number; delta: number }> {
    if (!this.graph) return []

    const queryLower = query.toLowerCase()
    const results: Array<{ vertexId: number; concept: string; similarity: number; delta: number }> = []

    for (const v of this.graph.vertices) {
      const label = v.label.toLowerCase()

      // 精确匹配
      let sim = 0
      if (label === queryLower) {
        sim = 1.0
      } else if (label.includes(queryLower)) {
        sim = 0.8
      } else if (queryLower.includes(label)) {
        sim = 0.6
      } else {
        // 部分匹配（Jaccard 风格）
        const chars = new Set(queryLower)
        let matchCount = 0
        for (const ch of label) {
          if (chars.has(ch)) matchCount++
        }
        sim = matchCount / Math.max(label.length, queryLower.length) * 0.5
      }

      if (sim > 0.2) {
        results.push({ vertexId: v.id, concept: v.label, similarity: sim, delta: v.delta })
      }
    }

    results.sort((a, b) => b.similarity - a.similarity)
    return results.slice(0, topK)
  }

  /** 获取详细的子图顶点和边 */
  private extractSubgraphDetailed(vertexIds: number[], radius: number = 2): {
    vertices: Array<{ id: number; concept: string; delta: number }>
    edges: Array<{ src: number; dst: number; weight: number; associatorFlag: number }>
  } {
    if (!this.graph) return { vertices: [], edges: [] }

    const visited = new Set(vertexIds)
    const queue: Array<[number, number]> = vertexIds.map(id => [id, 0])
    const edgeSet = new Set<number>()

    while (queue.length > 0) {
      const [vid, dist] = queue.shift()!
      if (dist >= radius) continue

      for (const eidx of this.adjacency.get(vid) ?? []) {
        edgeSet.add(eidx)
        const edge = this.graph.edges[eidx]
        const neighbor = edge.src === vid ? edge.dst : edge.src
        if (!visited.has(neighbor) && neighbor < this.graph.vertices.length) {
          visited.add(neighbor)
          queue.push([neighbor, dist + 1])
        }
      }
    }

    const vertices = Array.from(visited)
      .filter(vid => vid < this.graph!.vertices.length)
      .map(vid => ({
        id: this.graph!.vertices[vid].id,
        concept: this.graph!.vertices[vid].label,
        delta: this.graph!.vertices[vid].delta
      }))

    const edges = Array.from(edgeSet).map(eidx => this.graph!.edges[eidx])

    return { vertices, edges }
  }

  /** 模板驱动的文本生成 */
  private _templateGenerate(
    query: string,
    matched: Array<{ vertexId: number; concept: string; similarity: number; delta: number }>,
    subVertices: Array<{ id: number; concept: string; delta: number }>,
    subEdges: Array<{ src: number; dst: number; weight: number; associatorFlag: number }>,
    conceptNames: Map<number, string>,
    maxLen: number = 500
  ): string {
    const lines: string[] = []

    // 1. 开头
    const topConcept = matched[0]?.concept || '该主题'
    lines.push(`关于「${topConcept}」，我找到了以下相关知识：\n`)

    // 2. 核心概念介绍
    lines.push('【核心概念】')
    for (let i = 0; i < Math.min(matched.length, 5); i++) {
      const m = matched[i]
      const delta = m.delta.toFixed(3)
      // 查找相关概念
      const related = this._findRelatedConcepts(m.vertexId, subEdges, conceptNames)
      let desc = `信息存在度 δ=${delta}`
      if (related.length > 0) {
        desc += `，与「${related[0]}」等相关`
      }
      lines.push(`  ${i + 1}. ${m.concept} — ${desc}`)
    }
    lines.push('')

    // 3. 关系网络
    if (subEdges.length > 0) {
      lines.push('【关系网络】')
      const matchedIds = new Set(matched.map(m => m.vertexId))
      const shown = new Set<string>()
      let count = 0
      for (const e of subEdges) {
        if (count >= 5) break
        const key = `${e.src}-${e.dst}`
        if (shown.has(key)) continue
        if (matchedIds.has(e.src) || matchedIds.has(e.dst)) {
          const srcName = conceptNames.get(e.src) || `v${e.src}`
          const dstName = conceptNames.get(e.dst) || `v${e.dst}`
          lines.push(`  • ${srcName} 相关于 ${dstName}`)
          shown.add(key)
          count++
        }
      }
      if (count === 0) {
        lines.push('  （无显式关系，概念通过语义相似度关联）')
      }
      lines.push('')
    }

    // 4. 扩展知识
    const seen = new Set(matched.map(m => m.concept))
    const extra = subVertices.filter(v => !seen.has(v.concept)).slice(0, 5)
    if (extra.length > 0) {
      lines.push('【扩展知识】')
      for (const v of extra) {
        lines.push(`  • ${v.concept}（δ=${v.delta.toFixed(3)}）`)
        seen.add(v.concept)
      }
      lines.push('')
    }

    // 5. 结尾
    lines.push(`以上是基于已蒸馏知识库对「${query}」的回答。`)
    lines.push('如需更深入的分析，请继续提问或蒸馏更多相关文本。')

    let response = lines.join('\n')
    if (response.length > maxLen) {
      response = response.slice(0, maxLen) + '\n...(内容过长，已截断)'
    }

    return response
  }

  /** 查找与给定顶点相关的概念名称 */
  private _findRelatedConcepts(
    vertexId: number,
    edges: Array<{ src: number; dst: number; [key: string]: unknown }>,
    conceptNames: Map<number, string>
  ): string[] {
    const related: string[] = []
    for (const e of edges) {
      if (related.length >= 3) break
      if (e.src === vertexId) {
        related.push(conceptNames.get(e.dst) || `v${e.dst}`)
      } else if (e.dst === vertexId) {
        related.push(conceptNames.get(e.src) || `v${e.src}`)
      }
    }
    return related
  }

  /** 同步文本→φ（用于 generateResponse） */
  private textToPhiSync(text: string, dimension: number = 8): number[] | null {
    // 简单的同步 TextEncoder + 手动哈希近似（SHA-256 需要异步 crypto.subtle）
    const encoder = new TextEncoder()
    const data = encoder.encode(text)

    // 用一个简单的非密码哈希替代（DJB2 变体）
    let hash = 5381
    for (let i = 0; i < data.length; i++) {
      hash = ((hash << 5) + hash) + data[i]
      hash = hash & 0xFFFFFFFF  // 32-bit
    }

    const phi: number[] = new Array(dimension).fill(0)
    phi[0] = Math.min(text.length / 100.0, 1.0)
    phi[1] = Math.min((text.split(' ').length - 1) / Math.max(text.length, 1), 1.0)

    // 从 hash 派生其余维度
    for (let i = 2; i < dimension; i++) {
      const val = ((hash * (i + 1)) & 0xFFFFFFFF) / 0xFFFFFFFF
      phi[i] = (val - 0.5) * 2
    }

    return phi
  }
}

/**
 * 合并多个 EML 图为一个。顶点 ID 重新索引，边 src/dst 偏移。
 * laplacianAlpha 和 graphDelta 取平均值。
 */
export function mergeEMLGraphs(graphs: EMLGraphData[]): EMLGraphData {
  if (graphs.length === 0) {
    return { vertices: [], edges: [], laplacianAlpha: DEFAULT_LAPLACIAN_ALPHA, graphDelta: DEFAULT_GRAPH_DELTA }
  }
  if (graphs.length === 1) return graphs[0]

  const vertices: EMLVertex[] = []
  const edges: EMLEdge[] = []
  let totalLA = 0
  let totalGD = 0

  for (const g of graphs) {
    const idOffset = vertices.length
    for (const v of g.vertices) {
      vertices.push({ ...v, id: v.id + idOffset })
    }
    for (const e of g.edges) {
      edges.push({ ...e, src: e.src + idOffset, dst: e.dst + idOffset })
    }
    totalLA += g.laplacianAlpha
    totalGD += g.graphDelta
  }

  return {
    vertices,
    edges,
    laplacianAlpha: totalLA / graphs.length,
    graphDelta: totalGD / graphs.length
  }
}

/**
 * 重叠/冲突检测结果
 */
export interface ConceptOverlap {
  name: string
  existingId: number
  existingDelta: number
  newImportance: number
  newFrequency: number
}

export interface RelationConflict {
  src: string
  dst: string
  existingWeight: number
  newType: string
  newStrength: number
}

export interface MergeSummary {
  conceptOverlaps: ConceptOverlap[]
  conceptNewCount: number
  relationConflicts: RelationConflict[]
  relationNewCount: number
  relationDuplicateCount: number
}

/**
 * 检测新蒸馏结果与已加载 EML 图谱的重叠概念和冲突关系。
 *
 * - 重叠概念：新概念名（忽略大小写）在已加载图谱中存在
 * - 冲突关系：相同 src→dst 对存在于双方，类型或强度差异显著
 * - 新增概念/关系：仅在蒸馏结果中存在
 * - 冗余关系：相同 src→dst、相同类型且强度接近（差异<0.2）
 */
export function detectMergeSummary(
  newConcepts: DistillConcept[],
  newRelations: DistillRelation[],
  loadedGraph: EMLGraphData
): MergeSummary {
  // 构建已有概念名→顶点映射（大小写不敏感）
  const existingNameMap = new Map<string, EMLVertex>()
  for (const v of loadedGraph.vertices) {
    existingNameMap.set(v.label.toLowerCase(), v)
  }

  // 1) 检测概念重叠
  const conceptOverlaps: ConceptOverlap[] = []
  let conceptNewCount = 0
  for (const c of newConcepts) {
    const existing = existingNameMap.get(c.concept.toLowerCase())
    if (existing) {
      conceptOverlaps.push({
        name: c.concept,
        existingId: existing.id,
        existingDelta: existing.delta,
        newImportance: c.importance,
        newFrequency: c.frequency ?? 0
      })
    } else {
      conceptNewCount++
    }
  }

  // 构建已有关系键→边信息映射
  const existingEdgeMap = new Map<string, { type?: string; weight: number }>()
  for (const e of loadedGraph.edges) {
    const srcLabel = loadedGraph.vertices[e.src]?.label ?? `v${e.src}`
    const dstLabel = loadedGraph.vertices[e.dst]?.label ?? `v${e.dst}`
    // 关系类型从 associatorFlag 推断
    const etype = e.associatorFlag === 1 ? 'causes' : 'related_to'
    existingEdgeMap.set(`${srcLabel}→${dstLabel}`, { type: etype, weight: e.weight })
  }

  // 2) 检测关系冲突
  const relationConflicts: RelationConflict[] = []
  let relationNewCount = 0
  let relationDuplicateCount = 0
  for (const rel of newRelations) {
    const key = `${rel.src}→${rel.dst}`
    const existing = existingEdgeMap.get(key)
    if (existing) {
      // 类型不同 → 冲突；类型相同且强度差异大 → 也标记为冲突
      const typeMatch = (existing.type ?? 'related_to') === rel.type
      const strengthDiff = Math.abs(existing.weight - rel.strength)
      if (!typeMatch || strengthDiff >= 0.2) {
        relationConflicts.push({
          src: rel.src,
          dst: rel.dst,
          existingWeight: existing.weight,
          newType: rel.type,
          newStrength: rel.strength
        })
      } else {
        relationDuplicateCount++
      }
    } else {
      relationNewCount++
    }
  }

  return { conceptOverlaps, conceptNewCount, relationConflicts, relationNewCount, relationDuplicateCount }
}

/**
 * 将新蒸馏结果合并到已加载图谱中。
 *
 * 合并策略（全自动）：
 *   - 重叠概念 → 取 infoExistence(delta) 更高的一方
 *   - 冲突关系 → 取强度更高的一方，类型以新蒸馏为准
 *   - 新增概念/关系 → 直接追加
 *   - 已加载图谱中无冲突的概念/关系 → 保留
 *
 * 内部调用 buildEMLGraph 构建完整图。
 */
export async function buildMergedEML(
  newConcepts: DistillConcept[],
  newRelations: DistillRelation[],
  loadedGraph: EMLGraphData
): Promise<EMLGraphData> {
  // 已有概念名→顶点映射
  const existingVertexMap = new Map<string, EMLVertex>()
  for (const v of loadedGraph.vertices) {
    existingVertexMap.set(v.label.toLowerCase(), v)
  }

  // 记录被新概念覆盖的旧概念 ID
  const replacedVertices = new Set<number>()

  // 1) 合并概念
  const allConcepts: DistillConcept[] = []

  for (const c of newConcepts) {
    const existing = existingVertexMap.get(c.concept.toLowerCase())
    if (existing && existing.delta >= (c.info_existence ?? c.importance)) {
      // 旧概念 delta 更高 → 保留旧概念
      allConcepts.push({
        concept: c.concept,
        importance: Math.max(c.importance, existing.delta),
        context: '',
        frequency: c.frequency ?? 0,
        info_existence: existing.delta
      })
      replacedVertices.add(existing.id)
    } else if (existing) {
      // 新概念 infoExistence 更高 → 用新的
      allConcepts.push({ ...c })
      replacedVertices.add(existing.id)
    } else {
      // 全新概念
      allConcepts.push({ ...c })
    }
  }

  // 保留未被覆盖的已有概念
  for (const v of loadedGraph.vertices) {
    if (!replacedVertices.has(v.id)) {
      allConcepts.push({
        concept: v.label,
        importance: v.delta,
        context: '',
        frequency: 0,
        info_existence: v.delta
      })
    }
  }

  // 2) 合并关系
  const allRelations: DistillRelation[] = []
  const newEdgeKeys = new Set<string>()

  for (const rel of newRelations) {
    const key = `${rel.src}→${rel.dst}`
    newEdgeKeys.add(key)
    allRelations.push(rel)
  }

  // 保留未冲突的已有关系
  for (const e of loadedGraph.edges) {
    const srcLabel = loadedGraph.vertices[e.src]?.label ?? `v${e.src}`
    const dstLabel = loadedGraph.vertices[e.dst]?.label ?? `v${e.dst}`
    const key = `${srcLabel}→${dstLabel}`
    if (!newEdgeKeys.has(key)) {
      allRelations.push({
        src: srcLabel,
        dst: dstLabel,
        type: e.associatorFlag === 1 ? 'causes' : 'related_to',
        strength: e.weight
      })
    }
  }

  // 3) 构建合并后的完整 EML
  return await buildEMLGraph(allConcepts, allRelations, loadedGraph.laplacianAlpha, loadedGraph.graphDelta)
}

/**
 * 从 EML 文件缓冲区提取图可视化数据
 * 用于 D3.js 力导向图渲染
 *
 * @param buffer - EML 文件的 ArrayBuffer
 * @returns 包含 vertices 和 edges 的图数据
 */
export function extractGraphForVisualization(buffer: ArrayBuffer): {
  vertices: Array<{ id: number; label: string; delta: number; info_existence: number; corpusName?: string }>
  edges: Array<{ src: number; dst: number; weight: number; associator_flag: number }>
} | null {
  const data = loadEMLFromBuffer(buffer)
  if (!data) return null

  const vertices = data.vertices.map(v => ({
    id: v.id,
    label: v.label,
    delta: v.delta,
    info_existence: v.info_existence ?? 0
  }))

  const edges = data.edges.map(e => ({
    src: e.src,
    dst: e.dst,
    weight: e.weight,
    associator_flag: e.associatorFlag
  }))

  return { vertices, edges }
}

/**
 * 从已加载图谱中删除指定的顶点和边，重建 EML 图。
 *
 * - 删除顶点时，所有关联该顶点的边也一并删除
 * - 重建调用 buildEMLGraph，保留原有 laplacianAlpha/graphDelta
 *
 * @param graph - 当前已加载的 EML 图谱
 * @param removeVertexIds - 要删除的顶点 ID 集合
 * @param removeEdgeKeys - 要删除的边键集合（格式 `"srcLabel→dstLabel"`）
 * @returns 重建后的 EML 图谱
 */
export async function rebuildGraphAfterDelete(
  graph: EMLGraphData,
  removeVertexIds: Set<number>,
  removeEdgeKeys: Set<string>
): Promise<EMLGraphData> {
  // 1) 过滤概念：排除被删除的顶点
  const keptConcepts: DistillConcept[] = []
  const oldToNew = new Map<number, number>() // 旧 ID → 新 ID

  for (let i = 0; i < graph.vertices.length; i++) {
    const v = graph.vertices[i]
    if (removeVertexIds.has(v.id)) continue
    const newIdx = keptConcepts.length
    oldToNew.set(v.id, newIdx)
    keptConcepts.push({
      concept: v.label,
      importance: v.delta,
      context: '',
      frequency: 0,
      info_existence: v.delta
    })
  }

  // 2) 过滤关系：排除被删除的边 + 源/目标顶点被删除的边
  const keptRelations: DistillRelation[] = []

  for (const e of graph.edges) {
    const srcLabel = graph.vertices[e.src]?.label ?? ''
    const dstLabel = graph.vertices[e.dst]?.label ?? ''

    // 顶点被删则边也删
    if (removeVertexIds.has(e.src) || removeVertexIds.has(e.dst)) continue

    const edgeKey = `${srcLabel}→${dstLabel}`
    if (removeEdgeKeys.has(edgeKey)) continue

    keptRelations.push({
      src: srcLabel,
      dst: dstLabel,
      type: e.associatorFlag === 1 ? 'causes' : 'related_to',
      strength: e.weight
    })
  }

  // 3) 重建 EML 图
  return await buildEMLGraph(keptConcepts, keptRelations, graph.laplacianAlpha, graph.graphDelta)
}
