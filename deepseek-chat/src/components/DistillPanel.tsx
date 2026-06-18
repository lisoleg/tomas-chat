// 蒸馏模式面板：让用户在浏览器中直接使用 LLM 蒸馏器
// 包含文本输入、概念/关系提取、EML 图构建与下载、Token Bridge 推理

import { useCallback, useEffect, useRef, useState, useMemo } from 'react'
import {
  buildEMLGraph,
  buildMergedEML,
  detectMergeSummary,
  downloadEMLFile,
  extractConcepts,
  extractRelations,
  formatFileSize,
  loadEMLFromBuffer,
  rebuildGraphAfterDelete,
  serializeEML,
  TokenBridgeClient,
  extractGraphForVisualization
} from '../api/distiller'
import type { ChatEMLState, ConceptSearchResult, DistillConcept, DistillPhase, DistillRelation, EMLGraphData, TokenBridgeState } from '../types'
import type { MergeSummary } from '../api/distiller'
import { getAllKnowledgeItems, saveKnowledgeItems, type KnowledgeItem } from '../api/knowledgeStore'
import { deleteCorpusEntry, getAllCorpusEntries, saveCorpusEntry, saveConflictDecision, type CorpusEntry, type ConflictDecision } from '../api/corpusStore'
import { 
  loadFromCacheOrAPI, 
  saveGraphToCache, 
  type CachedGraphData 
} from '../api/distillCache'
import { EMLGraphVisualization } from './EMLGraphVisualization'
import { DIKWPPieChart, type DIKWPLayerInfo } from './DIKWPPieChart'
import { useToast } from './Toast'

interface DistillPanelProps {
  /** DeepSeek API Key */
  apiKey: string
  /** 从聊天模式传入的已加载 Token Bridge（App autoLoad 的结果），无需重复上传 */
  externalBridgeClient?: TokenBridgeClient
  /** 从聊天模式传入的知识库元信息 */
  externalEMLState?: ChatEMLState
}

/** 阶段对应的中文标签 */
const PHASE_LABELS: Record<DistillPhase, string> = {
  idle: '就绪',
  extracting_concepts: '提取概念中…',
  extracting_relations: '提取关系中…',
  building_graph: '构建 EML 图…',
  done: '蒸馏完成',
  error: '出错了'
}

/** 阶段对应的进度百分比 */
const PHASE_PROGRESS: Record<DistillPhase, number> = {
  idle: 0,
  extracting_concepts: 25,
  extracting_relations: 55,
  building_graph: 85,
  done: 100,
  error: 0
}

/** 蒸馏示例语料（多领域） */
const CORPUS_EXAMPLES: Array<{ label: string; domain: string; text: string }> = [
  {
    label: '物理',
    domain: '⚛️',
    text: '牛顿力学是经典物理学的基石。牛顿第一定律（惯性定律）指出，物体在不受外力作用时保持静止或匀速直线运动。牛顿第二定律 F=ma 建立了力、质量和加速度之间的定量关系。牛顿第三定律（作用力与反作用力）说明力总是成对出现。\n\n能量守恒定律是物理学中最基本的定律之一：能量既不会凭空产生也不会凭空消失，只能从一种形式转化为另一种形式。动能与速度的平方成正比，势能与物体的位置有关。热力学第一定律是能量守恒在热现象中的具体表现。\n\n爱因斯坦的狭义相对论颠覆了牛顿的绝对时空观，提出了质能方程 E=mc²，揭示了质量与能量的等价关系。'
  },
  {
    label: '化学',
    domain: '🧪',
    text: '元素周期表是化学的基石，由门捷列夫于1869年提出。元素按原子序数排列，具有周期性规律。原子由质子、中子和电子组成，质子数决定了元素的化学性质。\n\n化学键包括离子键、共价键和金属键。离子键通过电子转移形成，如 NaCl 中钠失去电子、氯获得电子。共价键通过电子共享形成，如水分子 H₂O 中氢和氧共享电子对。\n\n有机化学研究含碳化合物。烷烃是饱和烃，通式为 CₙH₂ₙ₊₂。烯烃含碳碳双键，可发生加成反应。苯环具有芳香性，是重要的有机结构单元。催化剂降低反应活化能而不改变平衡。'
  },
  {
    label: 'AI/ML',
    domain: '🤖',
    text: '人工智能是计算机科学的分支，旨在创建能执行需要人类智能的任务的系统。机器学习是AI的子领域，使计算机能从数据中学习而无需显式编程。\n\n深度学习基于多层人工神经网络，在图像识别、自然语言处理和语音识别等领域取得了突破性进展。卷积神经网络(CNN)擅长处理图像数据，通过卷积层提取特征。循环神经网络(RNN)适合序列数据，但存在梯度消失问题。Transformer架构通过自注意力机制取代了RNN，成为大语言模型的基础。\n\n大语言模型(LLM)如GPT系列通过海量文本预训练获得了强大的语言理解和生成能力。提示工程是引导LLM输出的关键技术。检索增强生成(RAG)结合外部知识库提高回答准确性。'
  },
  {
    label: '医学',
    domain: '🏥',
    text: '人体免疫系统是防御病原体的复杂网络。先天免疫是第一道防线，包括皮肤屏障和吞噬细胞。适应性免疫由B细胞和T细胞介导，具有特异性记忆功能。疫苗通过激活适应性免疫来预防传染病。\n\n基因编辑技术CRISPR-Cas9源于细菌的免疫机制，能精确修改DNA序列。它由引导RNA和Cas9蛋白组成，引导RNA识别目标序列，Cas9进行切割。基因编辑在治疗遗传病和癌症免疫疗法中展现了巨大潜力。\n\n心血管系统由心脏和血管组成。心脏有四个腔室：左右心房和左右心室。动脉将血液从心脏输送到组织，静脉将血液回流。高血压是心血管疾病的主要风险因素。'
  }
]

/** 关系类型中文映射 */
const RELATION_TYPE_LABELS: Record<string, string> = {
  is_a: '是…的一种',
  part_of: '是…的一部分',
  causes: '导致',
  related_to: '相关',
  used_in: '用于',
  inspired_by: '启发'
}

/**
 * 前端伪概念过滤器（与后端 llm_distiller.py 的 is_pseudo_concept 对齐）
 * 排除：日期/时间、纯数字/数量、度量值、URL/邮箱/电话等非实体概念
 */
function isPseudoConcept(conceptStr: string): { isPseudo: boolean; reason: string } {
  const s = conceptStr.trim()
  if (!s) return { isPseudo: true, reason: '空字符串' }
  if (s.length < 2) return { isPseudo: true, reason: '过短' }

  // ═══════════════════════════════════════
  // 日期 / 时间（最常出错，放最前面）
  // ═══════════════════════════════════════
  // 1543年5月24日 / 1473年2月19日
  if (/^\d{4}年\d{1,2}月\d{1,2}日?$/i.test(s)) return { isPseudo: true, reason: '日期' }
  // 1543年5月 / 2024年12月
  if (/^\d{4}年\d{1,2}月$/i.test(s)) return { isPseudo: true, reason: '年月' }
  // 1543年 / 2024年
  if (/^\d{4}年$/i.test(s)) return { isPseudo: true, reason: '年份' }
  // 公元前221年 / 公元2024年
  if (/^(公元前|公元)\d+年/.test(s)) return { isPseudo: true, reason: '历史年份' }
  // 19世纪 / 20世纪50年代
  if (/^\d{1,2}世纪(\d{1,2})?年代?$/.test(s)) return { isPseudo: true, reason: '世纪' }
  // 春季 / 夏季
  if (/^[春夏秋冬]季$/.test(s)) return { isPseudo: true, reason: '季节' }
  // 星期一 / 周三
  if (/^(周|星期)[一二三四五六日天]$/.test(s)) return { isPseudo: true, reason: '星期' }
  // 2024-05-24
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return { isPseudo: true, reason: 'ISO日期' }
  // 14:30 / 14:30:00
  if (/^\d{2}:\d{2}(:\d{2})?$/.test(s)) return { isPseudo: true, reason: '时间' }
  // 5月24日 / 24日（无年份）
  if (/^\d{1,2}[月日号]\d{1,2}[日号]?$/.test(s)) return { isPseudo: true, reason: '月日' }
  // 生卒日期范围："1473年2月19日-1543年5月24日" 或 "1473—1543"
  if (/^\d{4}年?\d*[-–—～~]\d{4}年?\d*/.test(s) && /\d{4}/.test(s)) return { isPseudo: true, reason: '日期范围/生卒' }
  // 纯四位数字且上下文像年份（如孤立出现的 "1543"、"1473"）
  if (/^\d{4}$/.test(s) && parseInt(s) >= 1000 && parseInt(s) <= 2100) return { isPseudo: true, reason: '疑似年份' }

  // ═══════════════════════════════════════
  // 纯数字 / 数量表达式
  // ═══════════════════════════════════════
  if (/^[\d\s.,，。、%％‰+\-×÷=<>≥≤π∞]+$/.test(s)) return { isPseudo: true, reason: '纯数字' }
  // 2500万 / 1.4亿 / 100条
  if (/^[\d.]+(?:万|亿|k|K|M|G|T)?(?:个|条|人|次|项|多)?$/.test(s)) return { isPseudo: true, reason: '数量' }
  // v2.0 / 3.14（排除大写开头的化学符号等）
  if (/^v?\d+(\.\d+)*([a-zA-Z]*)$/.test(s) && !/^[A-Z]/.test(s)) return { isPseudo: true, reason: '版本号' }
  // 第3版 / 第二章 / 第1卷
  if (/^第?[一二三四五六七八九十百千\d]+[章节卷册页版]$/.test(s)) return { isPseudo: true, reason: '序号' }

  // ═══════════════════════════════════════
  // 度量值
  // ═══════════════════════════════════════
  if (/^[\d.]+(?:km|m|cm|mm|kg|g|mg|℃|℉|%|公里|米|厘米|毫米|千克|克|毫升|升|公顷|亩|秒分小时天周年)$/i.test(s)) {
    return { isPseudo: true, reason: '度量值' }
  }

  // ═══════════════════════════════════════
  // URL / 邮箱 / 电话
  // ═══════════════════════════════════════
  if (/^(https?:\/\/|www\.|ftp:\/\/)/.test(s)) return { isPseudo: true, reason: 'URL' }
  if (/@/.test(s) && /\.\w+$/.test(s.split('@')[1])) return { isPseudo: true, reason: '邮箱' }
  if (/^[\d\-+\s()（）]{7,15}$/.test(s)) return { isPseudo: true, reason: '电话' }

  return { isPseudo: false, reason: '' }
}

/** 知识冲突条目 */
interface KnowledgeConflict {
  id: string
  conceptName: string
  domain: string
  oldSummary: string
  newSummary: string
  oldRelations: string[]
  newRelations: string[]
}

/** 检测新语料与已有语料的领域冲突 */
function detectConflicts(newEntries: CorpusEntry[], existingEntries: CorpusEntry[]): KnowledgeConflict[] {
  const conflicts: KnowledgeConflict[] = []
  const existingByDomain = new Map<string, CorpusEntry[]>()
  for (const e of existingEntries) {
    const arr = existingByDomain.get(e.domain) || []
    arr.push(e)
    existingByDomain.set(e.domain, arr)
  }

  for (const newEntry of newEntries) {
    const same = existingByDomain.get(newEntry.domain)
    if (!same || same.length === 0) continue

    // 如果现有条目中包含刚添加的条目本身，跳过（因为 getAllCorpusEntries 已包含新条目）
    const older = same.filter(s => s.id !== newEntry.id)
    if (older.length === 0) continue

    conflicts.push({
      id: `conflict-${newEntry.id}-${Date.now()}`,
      conceptName: `${newEntry.domain} 领域语料`,
      domain: newEntry.domain,
      oldSummary: `已有 ${older.length} 条语料 (${older.map(s => s.text.slice(0, 50)).join('; ')})`,
      newSummary: `新导入: ${newEntry.text.slice(0, 100)}`,
      oldRelations: older.map(s => `概念:${s.conceptsCount} 关系:${s.relationsCount}`),
      newRelations: [`概念:${newEntry.conceptsCount} 关系:${newEntry.relationsCount}`],
    })
  }
  return conflicts
}

/** 生成模式标签组件 */
function ModeBadge({ mode }: { mode: string }) {
  const config: Record<string, { label: string; color: string; bg: string }> = {
    translator: { label: '📖 翻译官', color: 'text-blue-300', bg: 'bg-blue-600/20 border-blue-600/30' },
    creative: { label: '✍️ 作家', color: 'text-purple-300', bg: 'bg-purple-600/20 border-purple-600/30' },
    creative_gated: { label: '⚠️ 作家(φ监管)', color: 'text-amber-300', bg: 'bg-amber-600/20 border-amber-600/30' },
    fallback: { label: '🔄 回退', color: 'text-orange-300', bg: 'bg-orange-600/20 border-orange-600/30' },
    error: { label: '❌ 错误', color: 'text-red-300', bg: 'bg-red-600/20 border-red-600/30' },
  }
  const c = config[mode] || { label: mode, color: 'text-textSecondary', bg: 'bg-white/10 border-white/20' }
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border ${c.bg} ${c.color} ml-auto`}>
      {c.label}
    </span>
  )
}

export function DistillPanel({ apiKey, externalBridgeClient, externalEMLState }: DistillPanelProps) {
  // 蒸馏状态
  const [phase, setPhase] = useState<DistillPhase>('idle')
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  // 蒸馏计时器：phase 进入工作时启动，回到 idle/done 时重置
  useEffect(() => {
    const isWorking = phase === 'extracting_concepts' || phase === 'extracting_relations' || phase === 'building_graph'
    if (isWorking) {
      setElapsedSeconds(0)
      const timer = setInterval(() => {
        setElapsedSeconds(prev => prev + 1)
      }, 1000)
      return () => clearInterval(timer)
    } else {
      setElapsedSeconds(0)
    }
  }, [phase])
  const [inputText, setInputText] = useState('')
  const [concepts, setConcepts] = useState<DistillConcept[]>([])
  const [relations, setRelations] = useState<DistillRelation[]>([])
  const [avgInfoExistence, setAvgInfoExistence] = useState(0)
  const [emlSize, setEmlSize] = useState(0)
  const [emlBuffer, setEmlBuffer] = useState<ArrayBuffer | null>(null)
  const [errorMsg, setErrorMsg] = useState('')
  const [currentDomain, setCurrentDomain] = useState('')
  const toast = useToast()
  // 知识持久化存储（后端 API）
  const [knowledgeItems, setKnowledgeItems] = useState<KnowledgeItem[]>([])
  const knowledgeSavedRef = useRef(false)

  // 语料持久化存储（后端 API）
  const [corpusEntries, setCorpusEntries] = useState<CorpusEntry[]>([])
  const corpusListRef = useRef<HTMLDivElement>(null)
  
  // 数据加载状态
  const [dataLoading, setDataLoading] = useState(true)
  const [dataError, setDataError] = useState<string | null>(null)
  // ⚠️ 注意：useToast() 已在上方调用，此处不再重复  
  // 加载知识条目和语料条目
  useEffect(() => {
    async function loadData() {
      console.log('[DistillPanel] === 开始加载数据 (2024-06-14 v2) ===')
      try {
        setDataLoading(true)
        setDataError(null)

        const items = await getAllKnowledgeItems()
        setKnowledgeItems(items)

        const entries = await getAllCorpusEntries()
        setCorpusEntries(entries)

        // ── 同时加载图谱数据（从后端三元组构建）──
        // 这样用户点击"知识浏览"中的概念时就能直接显示邻域子图
        try {
          const graphRes = await fetch('http://localhost:5000/api/knowledge/graph?limit=5000')
          console.log('[DistillPanel] 图谱API状态:', graphRes.status, graphRes.ok)
          if (graphRes.ok) {
            const graphJson = await graphRes.json()
            console.log('[DistillPanel] 图谱API返回:', JSON.stringify(graphJson).slice(0, 300))
            if (graphJson.success && graphJson.triples.length > 0) {
              const conceptSet = new Set<string>(graphJson.concepts as string[])
              // 确保 triples 中的 subject/object 都在 concept 集合中
              for (const t of graphJson.triples as any[]) {
                conceptSet.add(t.subject)
                if (t.object && !/^\d+(\.\d+)?$/.test(t.object) && t.object.length < 100) {
                  conceptSet.add(t.object)
                }
              }
              const conceptList = Array.from(conceptSet) as string[]
              const nameToId = new Map<string, number>()
              conceptList.forEach((name, i) => nameToId.set(name, i))

              const vertices = conceptList.map((name, i) => ({
                id: i,
                label: name,
                delta: Math.random() * 0.3 + 0.05,  // 后端暂无 delta，用小随机值占位
                info_existence: 0.5,
                corpusName: undefined
              }))

              const edges = (graphJson.triples as any[])
                .filter((t: any) => nameToId.has(t.subject) && nameToId.has(t.object))
                .map((t: any) => ({
                  src: nameToId.get(t.subject)!,
                  dst: nameToId.get(t.object)!,
                  weight: 0.3 + Math.random() * 0.4,  // 后端暂无权重，随机生成
                  associator_flag: 0
                }))

              setGraphData({ vertices, edges })
              // 标记图谱来自 API（非 EML 文件），默认全量显示
              setGraphFromAPI(true)
              console.log(`[DistillPanel] 图谱已加载: ${vertices.length} 顶点, ${edges.length} 边`)
            } else {
              // 三元组为空，但仍需构建最小图谱（仅顶点，无边），使知识列表点击可用
              const conceptItems = items.filter(i => i.type === 'concept')
              const conceptNames = conceptItems.map(i => i.label).filter(Boolean)
              if (conceptNames.length > 0) {
              const vertices = conceptNames.map((name: string, i: number) => ({
                  id: i,
                  label: name,
                  delta: Math.random() * 0.3 + 0.05,
                  info_existence: 0.5,
                  corpusName: undefined
                }))
                setGraphData({ vertices, edges: [] })
                setGraphFromAPI(true)
                console.log(`[DistillPanel] 无三元组，但构建了最小图谱: ${vertices.length} 顶点`)
              } else {
                console.log('[DistillPanel] 图谱数据为空（triples=0 且无知识条目），graphData 保持 null')
              }
            }
          }
        } catch (graphErr) {
          // 图谱加载失败不影响主功能（知识列表仍可用）
          console.warn('[DistillPanel] 图谱数据加载失败（非致命）:', graphErr)
        }

      } catch (err) {
        const message = err instanceof Error ? err.message : '加载数据失败'
        setDataError(message)
        console.error('加载数据失败:', err)
        toast.error(`加载数据失败：${message}，请检查后端服务器（http://localhost:5000）`)
      } finally {
        setDataLoading(false)
      }
    }
    loadData()
  }, [])

  // 知识冲突检测状态
  const [conflicts, setConflicts] = useState<KnowledgeConflict[]>([])
  const [conflictDecisions, setConflictDecisions] = useState<Record<string, string>>({})

  // Token Bridge 状态
  const [bridgeState, setBridgeState] = useState<TokenBridgeState>({
    loaded: false, graph: null, fileName: '', fileSize: 0, vertexCount: 0, edgeCount: 0, avgDelta: 0
  })
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResult, setSearchResult] = useState<ConceptSearchResult | null>(null)
  const [searchLoading, setSearchLoading] = useState(false)
  const [generatedText, setGeneratedText] = useState('')
  const [generating, setGenerating] = useState(false)
  const [generateMode, setGenerateMode] = useState<string>('')
  const [activeTab, setActiveTab] = useState<'reasoning' | 'graph' | 'knowledge'>('graph')
  const [selectedCorpusName, setSelectedCorpusName] = useState<string | null>(null)  // 选中的语料名称
  // 选中的关系 key（格式 "src-dst"），用于关系列表高亮
  const [selectedRelationKey, setSelectedRelationKey] = useState<string | null>(null)
  const [selectedKnowledgeId, setSelectedKnowledgeId] = useState<number | null>(null)  // 选中的知识节点ID
  const [edgeWeightThreshold, setEdgeWeightThreshold] = useState(0.2)    // 边权重阈值
  const [graphData, setGraphData] = useState<{
    vertices: Array<{ id: number; label: string; delta: number; info_existence: number; corpusName?: string }>
    edges: Array<{ src: number; dst: number; weight: number; associator_flag: number }>
  } | null>(null)
  // 图谱数据是否来自后端 API（非 EML 上传），用于决定是否默认全量显示
  const [graphFromAPI, setGraphFromAPI] = useState(false)
  const bridgeClient = useRef(new TokenBridgeClient())
  const knowledgeListRef = useRef<HTMLDivElement>(null)

  // 从 graphData 中提取所有已知的语料名称（用于提示）
  const knownCorpusNames = useMemo(() => {
    if (!graphData) return []
    const names = new Set<string>()
    for (const v of graphData.vertices) {
      if (v.corpusName) names.add(v.corpusName)
    }
    return Array.from(names).sort()
  }, [graphData])

  // 概念名称映射（从蒸馏结果构建，用于显示真实概念名）
  const conceptNamesMap = useMemo(() => {
    const m = new Map<number, string>()
    if (concepts.length > 0) {
      concepts.forEach((c, i) => m.set(i, c.concept))
    } else if (bridgeState.graph) {
      bridgeState.graph.vertices.forEach(v => {
        // EML 二进制的 label 可能为空，用 ID 回退
        m.set(v.id, v.label || `v${v.id}`)
      })
    }
    return m
  }, [concepts, bridgeState.graph])

  // 过滤伪概念（日期/数字/度量值等非实体）
  const filteredDistilledConcepts = useMemo(() => {
    return concepts.filter(c => !isPseudoConcept(c.concept).isPseudo)
  }, [concepts])

  // 过滤 graphData 中的伪概念顶点（用于图谱和列表显示）
  const filteredGraphVertices = useMemo(() => {
    if (!graphData) return []
    return graphData.vertices.filter(v => !isPseudoConcept(v.label).isPseudo)
  }, [graphData])

  // 从聊天模式的 autoLoad 同步已加载的知识库数据
  // 这样用户打开蒸馏面板就能直接看到统计和知识列表，无需重复上传 EML
  const [syncedFromExternal, setSyncedFromExternal] = useState(false)
  useEffect(() => {
    if (!syncedFromExternal && externalBridgeClient && externalEMLState?.loaded) {
      const graph = externalBridgeClient.getGraph()
      if (graph) {
        bridgeClient.current = externalBridgeClient
        setBridgeState({
          loaded: true,
          graph,
          fileName: externalEMLState.fileName,
          fileSize: externalEMLState.fileSize,
          vertexCount: externalEMLState.vertexCount,
          edgeCount: externalEMLState.edgeCount,
          avgDelta: externalEMLState.avgDelta
        })
        // 同步设置 graphData 供图谱可视化使用（直接从 bridgeClient 的 graph 构建，标签已含真实名称）
        setGraphData({
          vertices: graph.vertices.map(v => ({
            id: v.id,
            label: v.label,
            delta: v.delta,
            info_existence: v.info_existence ?? 0,
            corpusName: (v as any).corpusName ?? undefined
          })),
          edges: graph.edges.map(e => ({
            src: e.src,
            dst: e.dst,
            weight: e.weight,
            associator_flag: e.associatorFlag
          }))
        })
        setGraphFromAPI(false)
        setSyncedFromExternal(true)

        // 外部同步成功后，清空旧的 localStorage 知识/语料数据（避免与外部数据混在一起）
        setKnowledgeItems([])
        setCorpusEntries([])
      }
    }
  }, [syncedFromExternal, externalBridgeClient, externalEMLState])

  // 蒸馏完成后自动保存知识到 localStorage
  useEffect(() => {
    if (phase === 'done' && !knowledgeSavedRef.current && (concepts.length > 0 || relations.length > 0)) {
      knowledgeSavedRef.current = true
      const domain = currentDomain || '蒸馏'
      // 🔍 过滤伪概念（日期/数字/度量值等非实体）— 入库前必须过滤！
      const rawConcepts = concepts
      const filteredConcepts = concepts.filter(c => !isPseudoConcept(c.concept).isPseudo)
      const pseudoCount = rawConcepts.length - filteredConcepts.length
      if (pseudoCount > 0) {
        const rejected = rawConcepts.filter(c => isPseudoConcept(c.concept).isPseudo).map(c => ({ name: c.concept, reason: isPseudoConcept(c.concept).reason }))
        console.log(`[DistillPanel] 🗑 过滤 ${pseudoCount} 个伪概念:`, rejected)
      }

      const items: Omit<KnowledgeItem, 'id' | 'createdAt'>[] = [
        ...filteredConcepts.map(c => ({
          type: 'concept' as const,
          label: c.concept,
          extra: `𝕀=${(c.info_existence ?? 0).toFixed(3)}`,
          domain
        })),
        ...relations.map(r => ({
          type: 'relation' as const,
          label: `${r.src} → ${r.dst}`,
          extra: RELATION_TYPE_LABELS[r.type] || r.type,
          domain
        }))
      ]

      // 【同步】用蒸馏结果（已过滤伪概念）立即构建 graphData，使列表点击立即可用
      if (filteredConcepts.length > 0 || relations.length > 0) {
        const conceptNameToId = new Map<string, number>()
        filteredConcepts.forEach((c, i) => conceptNameToId.set(c.concept, i))
        const vertices = filteredConcepts.map((c, i) => ({
          id: i,
          label: c.concept,
          delta: Math.random() * 0.3 + 0.05,
          info_existence: c.info_existence ?? 0.5,
          corpusName: undefined as string | undefined
        }))
        const edges = relations
          .filter(r => conceptNameToId.has(r.src) && conceptNameToId.has(r.dst))
          .map(r => ({
            src: conceptNameToId.get(r.src)!,
            dst: conceptNameToId.get(r.dst)!,
            weight: r.strength ?? 0.5,
            associator_flag: Number(r.type) || 0
          }))
        setGraphData({ vertices, edges })
        console.log(`[DistillPanel] 蒸馏结果已同步构建 graphData: ${vertices.length} 顶点, ${edges.length} 边`)
      }

      // 【异步】保存语料条目（IFE 包裹）
      const corpusEntry = {
        text: inputText.slice(0, 5000),
        domain,
        conceptsCount: concepts.length,
        relationsCount: relations.length
      }
      ;(async () => {
        const updated = await saveKnowledgeItems(items)
        setKnowledgeItems(updated)
        const updatedCorpus = await saveCorpusEntry(corpusEntry)
        setCorpusEntries(updatedCorpus)

        // 执行冲突检测，缺省全部预置为"忽略"，由用户逐一确认
        const detected = detectConflicts(
          [updatedCorpus.find(e => e.text === corpusEntry.text) ?? updatedCorpus[0]],
          updatedCorpus
        )
        if (detected.length > 0) {
          const defaults: Record<string, string> = {}
          for (const c of detected) {
            defaults[c.id] = 'ignore'
          }
          setConflictDecisions(defaults)
          setConflictsExpanded(true) // 有冲突时默认展开
        }
        setConflicts(detected)
      })()
    }
  }, [phase, concepts, relations, currentDomain, inputText])

  // 合并状态
  const [mergeSummary, setMergeSummary] = useState<MergeSummary | null>(null)
  const [merging, setMerging] = useState(false)

  // 冲突面板展开/折叠
  const [conflictsExpanded, setConflictsExpanded] = useState(false)

  // 文本输入框拖拽高度
  const [textareaHeight, setTextareaHeight] = useState(200)
  const isDragging = useRef(false)
  const startY = useRef(0)
  const startHeight = useRef(0)

  // 三级缓存数据加载：缓存 → API → 兜底
  useEffect(() => {
    let cancelled = false

    async function loadInitialData() {
      try {
        console.log('[DistillPanel] 尝试从缓存/API加载初始数据...')
        const { data, source } = await loadFromCacheOrAPI(200, 1.0)
        
        if (cancelled) return
        
        if (data && data.concepts.length > 0) {
          // 转换为 graphData 格式
          const vertices = data.concepts.map((c: any, i: number) => ({
            id: i,
            label: c.label || `v${i}`,
            delta: Math.random() * 0.3 + 0.05,
            info_existence: c.iWeight || 1.0,
            corpusName: undefined as string | undefined
          }))
          
          const edges = data.relations.map((r: any, i: number) => ({
            src: r.source || 0,
            dst: r.target || 0,
            weight: r.iWeight || 0.5,
            associator_flag: 0
          }))
          
          setGraphData({ vertices, edges })
          setGraphFromAPI(true)
          console.log(`[DistillPanel] 已从 ${source} 加载数据:`, vertices.length, '顶点,', edges.length, '边')
        }
      } catch (e) {
        console.warn('[DistillPanel] 初始数据加载失败:', e)
      }
    }

    loadInitialData()

    return () => { cancelled = true }
  }, [])  // 仅在组件挂载时执行一次

  /** 处理冲突决策 */
  const handleConflictDecision = useCallback((conflictId: string, conflict: KnowledgeConflict, decision: string) => {
    setConflictDecisions(prev => ({ ...prev, [conflictId]: decision }))
    saveConflictDecision({
      conflictId,
      conceptName: conflict.conceptName,
      domain: conflict.domain,
      decision: decision as ConflictDecision['decision'],
      resolvedAt: Date.now(),
    })
  }, [])

  /** 开始蒸馏流程 */
  const handleDistill = useCallback(async () => {
    const trimmed = inputText.trim()
    if (!trimmed) return

    if (!apiKey.trim()) {
      setPhase('error')
      setErrorMsg('请先在左侧栏配置 API Key')
      return
    }

    try {
      knowledgeSavedRef.current = false
      // 阶段 1：提取概念
      setPhase('extracting_concepts')
      setErrorMsg('')
      const extractedConcepts = await extractConcepts(apiKey, trimmed, 50)
      setConcepts(extractedConcepts)

      // 阶段 2：提取关系
      setPhase('extracting_relations')
      const extractedRelations = await extractRelations(apiKey, extractedConcepts, trimmed, 100)
      setRelations(extractedRelations)

      // 阶段 3：构建 EML 图
      setPhase('building_graph')
      const graphData = await buildEMLGraph(extractedConcepts, extractedRelations)
      const buffer = serializeEML(graphData)
      setEmlBuffer(buffer)
      setEmlSize(buffer.byteLength)

      // 计算平均信息存在度
      const avg = extractedConcepts.length > 0
        ? extractedConcepts.reduce((sum, c) => sum + (c.info_existence ?? 0), 0) / extractedConcepts.length
        : 0
      setAvgInfoExistence(avg)

      setPhase('done')
    } catch (err) {
      setPhase('error')
      const message = err instanceof Error ? err.message : '未知错误'
      setErrorMsg(message)
    }
  }, [apiKey, inputText])

  /** 下载 EML 文件 */
  const handleDownload = useCallback(() => {
    if (emlBuffer) {
      downloadEMLFile(emlBuffer, 'knowledge_graph.eml')
    }
  }, [emlBuffer])

  /** 清空 */
  const handleClear = useCallback(() => {
    setPhase('idle')
    setInputText('')
    setConcepts([])
    setRelations([])
    setAvgInfoExistence(0)
    setEmlSize(0)
    setEmlBuffer(null)
    setErrorMsg('')
    setConflicts([])
    setConflictDecisions({})
  }, [])

  /** 加载 EML 文件到 Token Bridge */
  const handleLoadEML = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    try {
      const buffer = await file.arrayBuffer()
      const graph = loadEMLFromBuffer(buffer)

      // 构建概念名称映射（优先级：蒸馏结果 > 服务器DB > ID回退）
      const conceptNames = new Map<number, string>()

      // 优先从蒸馏结果恢复
      if (concepts.length > 0 && concepts.length === graph.vertices.length) {
        concepts.forEach((c, i) => conceptNames.set(i, c.concept))
      }
      // 蒸馏结果不足时，尝试从服务器 OwnThink DB 补充概念名
      if (conceptNames.size === 0) {
        try {
          const dbRes = await fetch('http://localhost:5000/api/knowledge/graph?limit=10000')
          if (dbRes.ok) {
            const dbData = await dbRes.json()
            if (dbData.success && dbData.concepts.length > 0) {
              // EML 的 vertex.id 是自增整数，DB 概念按数组顺序也是整数
              // 用 DB 概念列表按顺序映射到 vertex ID
              const dbConcepts = dbData.concepts as string[]
              graph.vertices.forEach((v, idx) => {
                if (idx < dbConcepts.length) {
                  conceptNames.set(v.id, dbConcepts[idx])
                }
              })
              console.log(`[DistillPanel] 从服务器补充了 ${conceptNames.size} 个概念名`)
            }
          }
        } catch (dbErr) {
          console.warn('[DistillPanel] 从服务器获取概念名失败（非致命）:', dbErr)
        }
      }

      // 最终回退：用 ID 作为标签
      graph.vertices.forEach(v => {
        if (!conceptNames.has(v.id)) {
          conceptNames.set(v.id, `v${v.id}`)
        }
      })

      bridgeClient.current.loadEML(buffer, conceptNames)
      const loadedGraph = bridgeClient.current.getGraph()!

      const avgDelta = loadedGraph.vertices.length > 0
        ? loadedGraph.vertices.reduce((s, v) => s + v.delta, 0) / loadedGraph.vertices.length
        : 0

      setBridgeState({
        loaded: true,
        graph: loadedGraph,
        fileName: file.name,
        fileSize: buffer.byteLength,
        vertexCount: loadedGraph.vertices.length,
        edgeCount: loadedGraph.edges.length,
        avgDelta
      })

      // 解析图谱数据用于可视化，始终应用真实概念名
      const vizGraph = extractGraphForVisualization(buffer)
      if (vizGraph) {
        vizGraph.vertices.forEach(v => {
          const realName = conceptNames.get(v.id)
          if (realName) v.label = realName
        })
      }
      setGraphData(vizGraph)
      setGraphFromAPI(false)
    } catch (err) {
      const message = err instanceof Error ? err.message : '加载失败'
      toast.error(`加载 EML 文件失败：${message}`)
    }
  }, [concepts])

  /** 用蒸馏结果直接加载到 Token Bridge */
  const handleLoadFromDistill = useCallback(() => {
    if (!emlBuffer) return
    try {
      const graph = loadEMLFromBuffer(emlBuffer)
      const conceptNames = new Map<number, string>()
      concepts.forEach((c, i) => conceptNames.set(i, c.concept))

      bridgeClient.current.loadEML(emlBuffer, conceptNames)
      const loadedGraph = bridgeClient.current.getGraph()!

      const avgDelta = loadedGraph.vertices.length > 0
        ? loadedGraph.vertices.reduce((s, v) => s + v.delta, 0) / loadedGraph.vertices.length
        : 0

      setBridgeState({
        loaded: true,
        graph: loadedGraph,
        fileName: 'distilled_knowledge.eml',
        fileSize: emlBuffer.byteLength,
        vertexCount: loadedGraph.vertices.length,
        edgeCount: loadedGraph.edges.length,
        avgDelta
      })

      // 解析图谱数据用于可视化，用真实概念名替换占位符，并标记所属语料
      const vizGraph = extractGraphForVisualization(emlBuffer)
      if (vizGraph && concepts.length > 0) {
        const nameMap = new Map<number, string>()
        concepts.forEach((c, i) => nameMap.set(i, c.concept))
        vizGraph.vertices.forEach(v => {
          const realName = nameMap.get(v.id)
          if (realName) v.label = realName
          // 标记当前蒸馏的语料名称（用于按语料过滤图谱）
          if (currentDomain) v.corpusName = currentDomain
        })
      }
      setGraphData(vizGraph)
      setGraphFromAPI(false)
    } catch (err) {
      const message = err instanceof Error ? err.message : '加载失败'
      toast.error(`加载失败：${message}`)
    }
  }, [emlBuffer, concepts])

  /** 检测新旧知识重叠与冲突 */
  const handleMergePreview = useCallback(() => {
    if (!bridgeState.graph) return
    const summary = detectMergeSummary(concepts, relations, bridgeState.graph)
    setMergeSummary(summary)
  }, [concepts, relations, bridgeState.graph])

  /** 确认合并：构建合并 EML 并加载到 Token Bridge */
  const handleMergeConfirm = useCallback(async () => {
    if (!bridgeState.graph) return
    setMerging(true)
    try {
      const mergedGraph = await buildMergedEML(concepts, relations, bridgeState.graph)
      const buffer = serializeEML(mergedGraph)

      // 加载合并后的图谱
      const conceptNames = new Map<number, string>()
      mergedGraph.vertices.forEach(v => conceptNames.set(v.id, v.label))
      bridgeClient.current.loadEML(mergedGraph, conceptNames)
      const loadedGraph = bridgeClient.current.getGraph()!

      const avgDelta = loadedGraph.vertices.length > 0
        ? loadedGraph.vertices.reduce((s, v) => s + v.delta, 0) / loadedGraph.vertices.length
        : 0

      setBridgeState({
        loaded: true,
        graph: loadedGraph,
        fileName: `merged_${bridgeState.fileName}`,
        fileSize: buffer.byteLength,
        vertexCount: loadedGraph.vertices.length,
        edgeCount: loadedGraph.edges.length,
        avgDelta
      })

      // 更新蒸馏数据
      setEmlBuffer(buffer)
      setEmlSize(buffer.byteLength)
      setConcepts(mergedGraph.vertices.map((v, i) => ({
        concept: v.label,
        importance: v.delta,
        context: '',
        frequency: 0,
        info_existence: v.delta
      })))
      setRelations(mergedGraph.edges.map(e => ({
        src: mergedGraph.vertices[e.src]?.label ?? `v${e.src}`,
        dst: mergedGraph.vertices[e.dst]?.label ?? `v${e.dst}`,
        type: e.associatorFlag === 1 ? 'causes' : 'related_to',
        strength: e.weight
      })))
      const newAvg = mergedGraph.vertices.length > 0
        ? mergedGraph.vertices.reduce((s, v) => s + v.delta, 0) / mergedGraph.vertices.length
        : 0
      setAvgInfoExistence(newAvg)

      // 更新图谱可视化，用真实概念名替换占位符，并标记语料
      const vizGraph = extractGraphForVisualization(buffer)
      if (vizGraph && concepts.length > 0) {
        const nameMap = new Map<number, string>()
        concepts.forEach((c, i) => nameMap.set(i, c.concept))
        vizGraph.vertices.forEach(v => {
          const realName = nameMap.get(v.id)
          if (realName) v.label = realName
          // 合并后的新概念标记语料
          if (currentDomain) v.corpusName = currentDomain
        })
      }
      setGraphData(vizGraph)

      setMergeSummary(null)
    } catch (err) {
      toast.error(`合并失败：${err instanceof Error ? err.message : '未知错误'}`)
    } finally {
      setMerging(false)
    }
  }, [bridgeState.graph, bridgeState.fileName, concepts, relations])

  /** Token Bridge 搜索 */
  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim() || !bridgeState.loaded) return
    setSearchLoading(true)
    try {
      const result = await bridgeClient.current.search(searchQuery.trim(), 5)
      setSearchResult(result)
    } catch {
      setSearchResult(null)
    } finally {
      setSearchLoading(false)
    }
  }, [searchQuery, bridgeState.loaded])

  /** "翻译官 + 作家" 混合生成回复 */
  const handleGenerate = useCallback(async () => {
    if (!searchQuery.trim() || !bridgeState.loaded) return
    setGenerating(true)
    setGenerateMode('')
    try {
      const result = await bridgeClient.current.generateResponse(
        searchQuery.trim(), 500, {
          llmApiKey: apiKey,  // 启用作家模式（低置信度时自动切换）
          llmModel: 'deepseek-chat'
        }
      )
      setGeneratedText(result.text)
      setGenerateMode(result.mode)
    } catch (err) {
      setGeneratedText(`❌ 生成失败：${err instanceof Error ? err.message : '未知错误'}`)
      setGenerateMode('error')
    } finally {
      setGenerating(false)
    }
  }, [searchQuery, bridgeState.loaded, apiKey])

  /** 拖拽调整文本输入区高度 */
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    isDragging.current = true
    startY.current = e.clientY
    startHeight.current = textareaHeight
    e.preventDefault()

    const handleMouseMove = (ev: MouseEvent) => {
      if (!isDragging.current) return
      const delta = ev.clientY - startY.current
      const newHeight = Math.max(100, Math.min(500, startHeight.current + delta))
      setTextareaHeight(newHeight)
    }

    const handleMouseUp = () => {
      isDragging.current = false
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }, [textareaHeight])

  const isWorking = phase === 'extracting_concepts' || phase === 'extracting_relations' || phase === 'building_graph'
  const progress = PHASE_PROGRESS[phase]

  return (
    <div className="flex-1 flex flex-col min-w-0 bg-chatBg overflow-hidden">
      {/* 标题栏 */}
      <header className="h-14 flex items-center px-4 border-b border-white/5 flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-lg">🔬</span>
          <h1 className="text-base font-semibold">LLM 蒸馏器</h1>
        </div>
        <span className="ml-3 text-xs text-textSecondary">
          将世界知识压缩进 EML 图（权重 = 𝕀(X)）
        </span>
      </header>

      {/* 可滚动内容区 */}
      <div className="flex-1 overflow-y-auto chat-scroll px-4 py-4 space-y-4">
        {/* 文本输入区 */}
        <div className="border border-white/10 rounded-lg overflow-hidden">
          <textarea
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="在此粘贴语料文本，点击「开始蒸馏」提取知识图谱…"
            disabled={isWorking}
            className="w-full resize-none bg-transparent text-textPrimary placeholder-textSecondary/50 p-3 text-sm leading-relaxed focus:outline-none"
            style={{ height: `${textareaHeight}px` }}
          />
          {/* 拖拽条 */}
          <div
            onMouseDown={handleMouseDown}
            className="h-2 bg-white/5 hover:bg-white/10 cursor-row-resize flex items-center justify-center transition-colors"
          >
            <div className="w-8 h-0.5 rounded-full bg-white/20" />
          </div>
        </div>

        {/* 示例语料（蒸馏前显示） */}
        {phase === 'idle' && (
          <div className="space-y-2">
            <div className="text-xs text-textSecondary/60 font-medium">📋 试试示例语料（点击填入）：</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
              {CORPUS_EXAMPLES.map((ex) => (
                <button
                  key={ex.label}
                  onClick={() => { setInputText(ex.text); setCurrentDomain(ex.label) }}
                  className="text-left p-3 rounded-lg border border-white/10 hover:border-accent/30 hover:bg-accent/5 transition-all group"
                >
                  <div className="flex items-center gap-1.5 mb-1">
                    <span className="text-sm">{ex.domain}</span>
                    <span className="text-xs font-medium text-textPrimary group-hover:text-accent">{ex.label}</span>
                  </div>
                  <div className="text-[11px] text-textSecondary/60 leading-relaxed line-clamp-2">
                    {ex.text.slice(0, 80)}…
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* 操作按钮 */}
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={handleDistill}
            disabled={isWorking || !inputText.trim()}
            className={[
              'flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-colors',
              isWorking || !inputText.trim()
                ? 'bg-white/10 text-textSecondary cursor-not-allowed'
                : 'bg-accent hover:bg-accentHover text-white'
            ].join(' ')}
          >
            🔬 开始蒸馏
          </button>
          <button
            onClick={handleDownload}
            disabled={!emlBuffer}
            className={[
              'flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-colors',
              emlBuffer
                ? 'bg-white/10 hover:bg-white/15 text-textPrimary'
                : 'bg-white/5 text-textSecondary cursor-not-allowed'
            ].join(' ')}
          >
            ⬇️ 下载 EML 图
          </button>
          <button
            onClick={handleClear}
            disabled={isWorking}
            className={[
              'flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-colors',
              isWorking
                ? 'bg-white/5 text-textSecondary cursor-not-allowed'
                : 'bg-white/10 hover:bg-white/15 text-textPrimary'
            ].join(' ')}
          >
            🗑️ 清空
          </button>
        </div>

        {/* 蒸馏进度条 */}
        {isWorking && (
          <div className="space-y-1.5 p-3 rounded-lg border border-white/10 bg-white/5">
            <div className="flex items-center justify-between text-xs text-textSecondary">
              <span>{PHASE_LABELS[phase]}</span>
              <span>
                {progress}% · 已用 {Math.floor(elapsedSeconds/60)}:{(elapsedSeconds%60).toString().padStart(2,'0')}
              </span>
            </div>
            {/* 进度条 */}
            <div className="w-full h-2 bg-white/10 rounded-full overflow-hidden">
              <div 
                className="h-full bg-accent transition-all duration-300 rounded-full"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}

        {/* 加载状态 */}
        {dataLoading && (
          <div className="flex items-center gap-2 p-3 rounded-lg border border-indigo-600/20 bg-indigo-900/10">
            <span className="text-lg">⏳</span>
            <span className="text-sm text-textSecondary">正在加载数据...</span>
          </div>
        )}

        {/* 错误提示 */}
        {dataError && (
          <div className="p-3 rounded-lg border border-rose-600/20 bg-rose-900/10">
            <div className="flex items-center gap-2 text-sm text-rose-300 mb-2">
              <span>❌</span>
              <span className="font-medium">加载数据失败</span>
            </div>
            <p className="text-xs text-textSecondary mb-3">{dataError}</p>
            <div className="flex gap-2">
              <button
                onClick={() => {
                  setDataError(null)
                  // 重新加载数据
                  async function reload() {
                    try {
                      setDataLoading(true)
                      const items = await getAllKnowledgeItems()
                      setKnowledgeItems(items)
                      const entries = await getAllCorpusEntries()
                      setCorpusEntries(entries)
                    } catch (e) {
                      setDataError(e instanceof Error ? e.message : '重试失败')
                    } finally {
                      setDataLoading(false)
                    }
                  }
                  reload()
                }}
                className="px-3 py-1.5 text-xs rounded-md bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 border border-rose-600/30 transition-colors"
              >
                🔄 重试
              </button>
              <button
                onClick={() => setDataError(null)}
                className="px-3 py-1.5 text-xs rounded-md bg-white/5 hover:bg-white/10 text-textSecondary border border-white/10 transition-colors"
              >
                关闭
              </button>
            </div>
          </div>
        )}

        {/* 蒸馏完成状态 — 已自动入库（知识+语料+冲突检测均自动完成） */}
        {phase === 'done' && (
          <div className="flex items-center gap-2 flex-wrap">
            <span className="flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium bg-emerald-600/10 text-emerald-300 border border-emerald-600/20">
              ✅ 已自动入库
            </span>
            <span className="text-xs text-textSecondary">
              {concepts.length} 个概念 · {relations.length} 条关系
              {conflicts.length > 0 && ` · ⚠️ ${conflicts.length} 项重叠待确认`}
              {conflicts.length === 0 && ' · 无领域重叠'}
            </span>
          </div>
        )}

        {/* 知识冲突检测 UI — 需用户逐一确认 */}
        {conflicts.length > 0 && (
          <div className="mt-6 rounded-xl border border-amber-600/20 bg-amber-900/5 overflow-hidden">
            {/* 折叠条 */}
            <button
              onClick={() => setConflictsExpanded(!conflictsExpanded)}
              className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-amber-900/10 transition-colors text-left"
            >
              <div className="flex items-center gap-2">
                <span className="text-sm">⚠️</span>
                <span className="text-xs text-amber-300/80">
                  检测到 <span className="font-semibold">{conflicts.length}</span> 项知识重叠，请确认处理方式
                </span>
                <span className="text-[10px] text-amber-400/40">
                  （{conflictsExpanded ? '点击收起' : '点击展开'}逐条确认）
                </span>
              </div>
              <span className="text-amber-400/50 text-xs transition-transform duration-200"
                style={{ transform: conflictsExpanded ? 'rotate(180deg)' : 'rotate(0deg)' }}>
                ▼
              </span>
            </button>

            {/* 展开后的冲突详情 */}
            {conflictsExpanded && (
              <div className="px-4 pb-4 border-t border-amber-600/15">
                <p className="text-[11px] text-amber-400/50 mt-3 mb-3">
                  以下概念在不同语料中有不同定义，请逐条确认处理方式。
                </p>
                {conflicts.map(c => (
                  <div key={c.id} className="mb-3 p-3 rounded-lg border border-amber-600/20 bg-black/20">
                    <div className="text-xs font-medium text-amber-200 mb-2">{c.conceptName}</div>
                    <div className="grid grid-cols-2 gap-3 mb-3">
                      <div className="p-2 rounded bg-white/5">
                        <div className="text-[10px] text-textSecondary/50 mb-1">📚 已有知识</div>
                        <div className="text-[11px] text-textSecondary/80">{c.oldSummary}</div>
                        {c.oldRelations.map((r, i) => (
                          <div key={i} className="text-[10px] text-cyan-400/60 mt-0.5">{r}</div>
                        ))}
                      </div>
                      <div className="p-2 rounded bg-white/5">
                        <div className="text-[10px] text-textSecondary/50 mb-1">🆕 新知识</div>
                        <div className="text-[11px] text-textSecondary/80">{c.newSummary}</div>
                        {c.newRelations.map((r, i) => (
                          <div key={i} className="text-[10px] text-emerald-400/60 mt-0.5">{r}</div>
                        ))}
                      </div>
                    </div>
                    <div className="flex gap-1.5 flex-wrap">
                      {(['keep_old', 'keep_new', 'ignore'] as const).map(decision => {
                        const isSelected = conflictDecisions[c.id] === decision
                        return (
                          <button
                            key={decision}
                            onClick={() => handleConflictDecision(c.id, c, decision)}
                            className={`px-2.5 py-1 rounded text-[10px] font-medium transition-all border
                              ${isSelected
                                ? 'bg-amber-700/40 text-amber-200 border-amber-500/50'
                                : 'bg-white/5 text-textSecondary/60 border-white/10 hover:border-amber-500/30'
                              }`}
                          >
                            {decision === 'keep_old' && '📌 保留旧的'}
                            {decision === 'keep_new' && '🆕 保留新的'}
                            {decision === 'ignore' && '👁️ 忽略'}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                ))}
                {/* 全部确认按钮 */}
                <div className="pt-2 pb-1 text-center">
                  <button
                    onClick={() => {
                      setConflictsExpanded(false)
                    }}
                    className="px-5 py-1.5 rounded-md text-xs font-medium transition-colors bg-amber-600/20 hover:bg-amber-600/30 text-amber-300 border border-amber-600/30"
                  >
                    ✅ 确认全部
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {conflicts.length === 0 && phase === 'done' && (
          <div className="p-3 rounded-lg border border-emerald-600/20 bg-emerald-900/10">
            <div className="flex items-center gap-2 text-sm text-emerald-300">
              <span>✅</span>
              <span>无知识冲突 — 新语料与已有知识无领域重叠</span>
            </div>
          </div>
        )}

        {/* 已加载图谱信息（蒸馏完成时显示） */}
        {phase === 'done' && bridgeState.loaded && (
          <div className="flex items-center gap-2 flex-wrap">
            <span className="flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium bg-blue-600/10 text-blue-300 border border-blue-600/20">
              📊 已检测重叠
            </span>
            <span className="text-xs text-textSecondary">
              当前已加载 {bridgeState.fileName}（🔵节点={bridgeState.vertexCount} 🔗边={bridgeState.edgeCount} K={bridgeState.vertexCount + bridgeState.edgeCount}）
            </span>
          </div>
        )}

        {/* 合并预览面板 */}
        {mergeSummary && (
          <MergePreviewPanel
            summary={mergeSummary}
            onConfirm={handleMergeConfirm}
            onCancel={() => setMergeSummary(null)}
            merging={merging}
          />
        )}

        {/* 进度条 */}
        {(isWorking || phase === 'done' || phase === 'error') && (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <span className={phase === 'error' ? 'text-rose-400' : 'text-textSecondary'}>
                {phase === 'error' ? `❌ ${errorMsg}` : PHASE_LABELS[phase]}
              </span>
              <span className="text-textSecondary">{progress}%</span>
            </div>
            <div className="w-full h-2 bg-white/5 rounded-full overflow-hidden">
              <div
                className={[
                  'h-full rounded-full transition-all duration-500',
                  phase === 'error' ? 'bg-rose-500' : 'bg-accent'
                ].join(' ')}
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}

        {/* 统计卡片 — 始终可见 */}
        <div className="flex items-center gap-2 text-xs text-textSecondary">
          <span className="font-medium">
            {bridgeState.loaded ? '📊 知识库统计' : graphData && graphData.vertices.length > 0 ? '📊 图谱统计（API）' : phase === 'done' ? '📊 蒸馏统计' : '📊 知识库统计'}
          </span>
          {bridgeState.loaded && (
            <span className="text-textSecondary/60">{bridgeState.fileName}</span>
          )}
          {!bridgeState.loaded && graphData && graphData.vertices.length > 0 && (
            <span className="text-textSecondary/60">后端图谱数据</span>
          )}
          {!bridgeState.loaded && phase === 'done' && (
            <span className="text-textSecondary/60">蒸馏结果</span>
          )}
          {!bridgeState.loaded && !(graphData && graphData.vertices.length > 0) && phase !== 'done' && (
            <span className="text-textSecondary/40">等待加载…</span>
          )}
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          <StatCard
            label="概念数"
            value={
              bridgeState.loaded
                ? String(bridgeState.vertexCount)
                : graphData && graphData.vertices.length > 0
                  ? String(graphData.vertices.length)
                  : phase === 'done'
                    ? String(concepts.length)
                    : '—'
            }
          />
          <StatCard
            label="关系数"
            value={
              bridgeState.loaded
                ? String(bridgeState.edgeCount)
                : graphData && graphData.edges.length > 0
                  ? String(graphData.edges.length)
                  : phase === 'done'
                    ? String(relations.length)
                    : '—'
            }
          />
          <StatCard
            label="语料条数 ▾"
            value={corpusEntries.length > 0 ? String(corpusEntries.length) : '—'}
            clickable={corpusEntries.length > 0}
            onClick={() => corpusListRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
          />
          <StatCard
            label="𝕀 均值"
            value={
              bridgeState.loaded
                ? bridgeState.avgDelta.toFixed(3)
                : graphData && graphData.vertices.length > 0
                  ? (graphData.vertices.reduce((s, v) => s + v.delta, 0) / graphData.vertices.length).toFixed(3)
                  : phase === 'done'
                    ? avgInfoExistence.toFixed(3)
                    : '—'
            }
          />
          <StatCard
            label="EML 大小"
            value={
              bridgeState.loaded
                ? formatFileSize(bridgeState.fileSize)
                : phase === 'done'
                  ? formatFileSize(emlSize)
                  : '—'
            }
          />
        </div>

        {/* ==================== 概念列表（独立区域）==================== */}
        <div className="border border-white/10 rounded-lg overflow-hidden">
          <div className="px-3 py-2 bg-emerald-600/10 text-sm font-medium border-b border-white/10 flex items-center gap-2">
            <span>🧩</span>
            <span>概念列表</span>
            {knowledgeItems.filter(i => i.type === 'concept').length > 0 && (
              <span className="text-xs bg-accent/20 text-accent px-1.5 py-0.5 rounded">持久化</span>
            )}
            <span className="text-xs text-textSecondary ml-auto">
              {(() => {
                const kConcepts = knowledgeItems.filter(i => i.type === 'concept').length
                const bCount = bridgeState.loaded ? bridgeState.vertexCount : 0
                const dCount = phase === 'done' && !bridgeState.loaded ? concepts.length : 0
                return (kConcepts + bCount + dCount) > 0 ? `${kConcepts + bCount + dCount} 条` : '—'
              })()}
            </span>
          </div>
          <div className="max-h-52 overflow-y-auto chat-scroll">
            {/* 持久化的概念 */}
            {knowledgeItems.filter(i => i.type === 'concept').length > 0 && (
              <>
                <div className="px-3 py-1.5 text-[11px] text-textSecondary/60 bg-white/[0.02] border-b border-white/5">
                  💾 持久化存储 · 概念
                </div>
                {knowledgeItems.filter(i => i.type === 'concept').map((item) => (
                  <div
                    key={`kc-${item.id}`}
                    onClick={() => {
                      // 尝试在 graphData 中找到匹配的顶点 ID
                      const matchedVertex = graphData?.vertices.find(v => v.label === item.label)
                      if (matchedVertex) {
                        setSelectedKnowledgeId(matchedVertex.id)
                        setSelectedCorpusName(null)
                        setActiveTab('graph')
                      }
                    }}
                    className={`flex items-center gap-2 px-3 py-2 text-sm border-b border-white/5 last:border-b-0 cursor-pointer hover:bg-indigo-600/20 group transition-colors pointer-events-auto ${selectedKnowledgeId != null && graphData?.vertices.find(v => v.id === selectedKnowledgeId)?.label === item.label ? 'bg-indigo-600/30 border-l-2 border-l-indigo-400' : ''}`}
                  >
                    <span className="font-medium min-w-0 truncate flex-1" title={item.label}>{item.label}</span>
                    <span className="text-textSecondary/60 text-xs flex-shrink-0">{item.extra}</span>
                    <span className="text-textSecondary/40 text-[11px] flex-shrink-0 w-16 text-right">
                      {new Date(item.createdAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
                    </span>
                    <span className="text-[9px] text-cyan-400/50 flex-shrink-0">持久化</span>
                  </div>
                ))}
              </>
            )}

            {/* bridgeState 的顶点（概念） */}
            {bridgeState.loaded && bridgeState.graph && (
              <>
                <div className="px-3 py-1.5 text-[11px] text-textSecondary/60 bg-white/[0.02] border-b border-white/5">
                  📂 当前加载 · 概念 V={bridgeState.graph.vertices.length}
                </div>
                {bridgeState.graph.vertices
                  .filter(v => {
                    const realName = conceptNamesMap.get(v.id) ?? v.label
                    return !isPseudoConcept(realName).isPseudo
                  })
                  .sort((a, b) => b.delta - a.delta)
                  .map((v) => {
                    const realName = conceptNamesMap.get(v.id) ?? v.label
                    return (
                      <div
                        key={`bv-${v.id}`}
                        onClick={() => {
                          setSelectedKnowledgeId(v.id)
                          setSelectedCorpusName(null)
                          setActiveTab('graph')
                        }}
                        className={`flex items-center gap-2 px-3 py-2 text-sm border-b border-white/5 last:border-b-0 cursor-pointer hover:bg-indigo-600/20 transition-colors pointer-events-auto ${selectedKnowledgeId === v.id ? 'bg-indigo-600/30 border-l-2 border-l-indigo-400' : ''}`}
                      >
                        <span className="font-medium min-w-0 truncate flex-1" title={realName}>{realName}</span>
                        <span className="text-accent font-mono text-xs flex-shrink-0">𝕏={v.delta.toFixed(3)}</span>
                      </div>
                    )
                  })}
              </>
            )}

            {/* 蒸馏结果的概念 */}
            {!bridgeState.loaded && phase === 'done' && filteredDistilledConcepts.length > 0 && (
              <>
                <div className="px-3 py-1.5 text-[11px] text-textSecondary/60 bg-white/[0.02] border-b border-white/5">
                  🧪 蒸馏结果 · 概念 C={filteredDistilledConcepts.length}{concepts.length !== filteredDistilledConcepts.length ? `（已过滤 ${concepts.length - filteredDistilledConcepts.length} 个伪概念）` : ''}
                </div>
                {filteredDistilledConcepts
                  .sort((a, b) => (b.info_existence ?? 0) - (a.info_existence ?? 0))
                  .map((c, idx) => {
                    const matchedV = graphData?.vertices.find(v => v.label === c.concept)
                    const isSelected = matchedV ? selectedKnowledgeId === matchedV.id : false
                    return (
                    <div
                      key={`dc-${idx}`}
                      onClick={() => {
                        if (matchedV) {
                          setSelectedKnowledgeId(matchedV.id)
                          setSelectedCorpusName(null)
                          setActiveTab('graph')
                        }
                      }}
                      className={`flex items-center gap-2 px-3 py-2 text-sm border-b border-white/5 last:border-b-0 cursor-pointer hover:bg-indigo-600/20 transition-colors pointer-events-auto ${isSelected ? 'bg-indigo-600/30 border-l-2 border-l-indigo-400' : ''}`}
                    >
                      <span className="font-medium min-w-0 truncate flex-1" title={c.concept}>{c.concept}</span>
                      <span className="text-accent font-mono text-xs flex-shrink-0">𝕀={(c.info_existence ?? 0).toFixed(2)}</span>
                    </div>
                    )})}
              </>
            )}

            {/* 空状态 */}
            {knowledgeItems.filter(i => i.type === 'concept').length === 0 && !bridgeState.loaded && !(phase === 'done' && filteredDistilledConcepts.length > 0) && (
              <div className="px-3 py-8 text-sm text-textSecondary/50 text-center">
                <p>暂无概念条目</p>
                <p className="text-xs mt-1">蒸馏文本后自动显示</p>
              </div>
            )}
          </div>
        </div>

        {/* ==================== 关系列表（独立区域）==================== */}
        <div className="border border-white/10 rounded-lg overflow-hidden">
          <div className="px-3 py-2 bg-indigo-600/10 text-sm font-medium border-b border-white/10 flex items-center gap-2">
            <span>🔗</span>
            <span>关系列表</span>
            {knowledgeItems.filter(i => i.type === 'relation').length > 0 && (
              <span className="text-xs bg-accent/20 text-accent px-1.5 py-0.5 rounded">持久化</span>
            )}
            <span className="text-xs text-textSecondary ml-auto">
              {(() => {
                const kRels = knowledgeItems.filter(i => i.type === 'relation').length
                const bCount = bridgeState.loaded ? bridgeState.edgeCount : 0
                const dCount = phase === 'done' && !bridgeState.loaded ? relations.length : 0
                return (kRels + bCount + dCount) > 0 ? `${kRels + bCount + dCount} 条` : '—'
              })()}
            </span>
          </div>
          <div className="max-h-52 overflow-y-auto chat-scroll">
            {/* 持久化的关系 */}
            {knowledgeItems.filter(i => i.type === 'relation').length > 0 && (
              <>
                <div className="px-3 py-1.5 text-[11px] text-textSecondary/60 bg-white/[0.02] border-b border-white/5">
                  💾 持久化存储 · 关系
                </div>
                {knowledgeItems.filter(i => i.type === 'relation').map((item) => (
                  <div
                    key={`kr-${item.id}`}
                    onClick={() => {
                      // 关系的 label 格式是 "源→目标"，尝试解析并找到 src 节点 ID
                      const arrowIdx = item.label.indexOf(' → ')
                      if (arrowIdx > 0) {
                        const srcLabel = item.label.slice(0, arrowIdx)
                        const matchedSrc = graphData?.vertices.find(v => v.label === srcLabel || v.label.startsWith(srcLabel))
                        if (matchedSrc) {
                          setSelectedKnowledgeId(matchedSrc.id)
                          setSelectedCorpusName(null)
                          setActiveTab('graph')
                        }
                      }
                    }}
                    className="flex items-center gap-2 px-3 py-2 text-sm border-b border-white/5 last:border-b-0 cursor-pointer hover:bg-indigo-600/20 group transition-colors pointer-events-auto"
                  >
                    <span className="min-w-0 truncate flex-1" title={item.label}>{item.label}</span>
                    <span className="text-textSecondary/60 text-xs flex-shrink-0">{item.extra}</span>
                    <span className="text-textSecondary/40 text-[11px] flex-shrink-0 w-16 text-right">
                      {new Date(item.createdAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
                    </span>
                    <span className="text-[9px] text-amber-400/50 flex-shrink-0">持久化</span>
                  </div>
                ))}
              </>
            )}

            {/* bridgeState 的边（关系） */}
            {bridgeState.loaded && bridgeState.graph && (
              <>
                <div className="px-3 py-1.5 text-[11px] text-textSecondary/60 bg-white/[0.02] border-b border-white/5">
                  📂 当前加载 · 关系 E={bridgeState.edgeCount}
                </div>
                {bridgeState.graph.edges.map((e, idx) => {
                  const srcLabel = conceptNamesMap.get(e.src) ?? bridgeState.graph!.vertices.find(v => v.id === e.src)?.label ?? `v${e.src}`
                  const dstLabel = conceptNamesMap.get(e.dst) ?? bridgeState.graph!.vertices.find(v => v.id === e.dst)?.label ?? `v${e.dst}`
                  const etype = e.associatorFlag === 1 ? 'causes' : 'related_to'
                  return (
                    <div
                      key={`be-${idx}`}
                      onClick={() => {
                        setSelectedKnowledgeId(e.src)
                        setSelectedCorpusName(null)
                        setActiveTab('graph')
                      }}
                      className="flex items-center gap-2 px-3 py-2 text-sm border-b border-white/5 last:border-b-0 cursor-pointer hover:bg-indigo-600/20 transition-colors pointer-events-auto"
                    >
                      <span className="text-sm font-medium text-emerald-300 shrink-0 truncate" title={srcLabel}>{srcLabel}</span>
                      <span className="text-accent text-[10px] shrink-0">—{RELATION_TYPE_LABELS[etype] || etype}→</span>
                      <span className="text-sm font-medium text-indigo-300 shrink-0 truncate" title={dstLabel}>{dstLabel}</span>
                      <span className="text-textSecondary text-xs shrink-0">权重:{e.weight.toFixed(2)}</span>
                    </div>
                  )
                })}
              </>
            )}

            {/* 蒸馏结果的关系 */}
            {!bridgeState.loaded && phase === 'done' && relations.length > 0 && (
              <>
                <div className="px-3 py-1.5 text-[11px] text-textSecondary/60 bg-white/[0.02] border-b border-white/5">
                  🧪 蒸馏结果 · 关系 R={relations.length}
                </div>
                {relations.map((r, idx) => {
                  const matchedSrc = graphData?.vertices.find(v => v.label === r.src)
                  const isSelected = matchedSrc ? selectedKnowledgeId === matchedSrc.id : false
                  return (
                  <div
                    key={`dr-${idx}`}
                    onClick={() => {
                      if (matchedSrc) {
                        setSelectedKnowledgeId(matchedSrc.id)
                        setSelectedCorpusName(null)
                        setActiveTab('graph')
                      }
                    }}
                    className={`flex items-center gap-2 px-3 py-2 text-sm border-b border-white/5 last:border-b-0 cursor-pointer hover:bg-indigo-600/20 transition-colors pointer-events-auto ${isSelected ? 'bg-indigo-600/30 border-l-2 border-l-indigo-400' : ''}`}
                  >
                    <span className="truncate flex-1">
                      <span className="font-medium" title={r.src}>{r.src}</span>
                      <span className="text-accent text-xs mx-1">—{RELATION_TYPE_LABELS[r.type] || r.type}→</span>
                      <span className="font-medium" title={r.dst}>{r.dst}</span>
                    </span>
                    <span className="text-textSecondary text-xs flex-shrink-0">权重:{r.strength.toFixed(2)}</span>
                  </div>
                  )})}
              </>
            )}

            {/* 空状态 */}
            {knowledgeItems.filter(i => i.type === 'relation').length === 0 && !bridgeState.loaded && !(phase === 'done' && relations.length > 0) && (
              <div className="px-3 py-8 text-sm text-textSecondary/50 text-center">
                <p>暂无关系条目</p>
                <p className="text-xs mt-1">蒸馏文本后自动显示</p>
              </div>
            )}
          </div>
        </div>

        {/* 语料列表 — 所有导入的语料，最新在前 */}
        <div ref={corpusListRef} className="border border-white/10 rounded-lg overflow-hidden">
          <div className="px-3 py-2 bg-white/5 text-sm font-medium border-b border-white/10 flex items-center gap-2">
            <span>📂 语料列表</span>
            {corpusEntries.length > 0 && (
              <span className="text-xs bg-amber-600/20 text-amber-300 px-1.5 py-0.5 rounded">持久化</span>
            )}
            {/* 领域分类说明 */}
            <span className="relative group ml-1" title="">
              <span className="text-[10px] cursor-help text-textSecondary/50 border border-white/10 rounded-full w-4 h-4 inline-flex items-center justify-center leading-none select-none">?</span>
              <div className="absolute left-0 top-6 w-64 bg-gray-900/95 backdrop-blur-sm text-[11px] text-textSecondary/90 rounded-md p-2.5 border border-white/15 shadow-xl z-50 opacity-0 group-hover:opacity-100 pointer-events-none group-hover:pointer-events-auto transition-opacity">
                <div className="font-medium text-textPrimary/90 mb-1">关于「领域」分类</div>
                <div className="leading-relaxed">
                  领域 = 学科/主题分类（如：物理、化学、医学、AI/ML 等）。
                  <br/><br/>
                  图谱按领域过滤显示：点击某条语料 → 只显示该领域的概念与关系子图。
                  <br/><br/>
                  蒸馏时自动按语料来源标记领域，也可手动编辑语料条目的领域标签。
                </div>
              </div>
            </span>
            <span className="text-xs text-textSecondary ml-auto">
              {corpusEntries.length > 0 ? `${corpusEntries.length} 条` : '—'}
            </span>
          </div>
          <div className="max-h-96 overflow-y-auto chat-scroll">
            {corpusEntries.length === 0 ? (
              <div className="px-3 py-10 text-sm text-textSecondary/50 text-center">
                <div className="mb-2">📄</div>
                <p>暂无语料条目</p>
                <p className="text-xs mt-1">蒸馏文本后会自动保存语料</p>
              </div>
            ) : (
              corpusEntries.map(entry => {
                const preview = entry.text.slice(0, 120).replace(/\n/g, ' ')
                const timeStr = new Date(entry.createdAt).toLocaleString('zh-CN', {
                  month: '2-digit',
                  day: '2-digit',
                  hour: '2-digit',
                  minute: '2-digit'
                })
                return (
                  <div
                    key={entry.id}
                    onClick={() => {
                      setSelectedCorpusName(entry.domain)
                      setSelectedKnowledgeId(null) // 清除知识选择
                      setActiveTab('graph') // 自动切换到图谱 Tab
                    }}
                    className={`px-3 py-2.5 border-b border-white/5 last:border-b-0 hover:bg-indigo-600/20 group cursor-pointer transition-colors ${selectedCorpusName === entry.domain ? 'bg-indigo-600/30 border-l-2 border-l-indigo-400' : ''}`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[11px] px-1.5 py-0.5 rounded bg-white/10 text-textSecondary font-medium">
                        {entry.domain}
                      </span>
                      <span className="text-[11px] text-textSecondary/40 ml-auto">{timeStr}</span>
                      <button
                        onClick={async () => {
                          if (confirm(`确认删除语料「${preview.slice(0, 30)}…」？`)) {
                            const updated = await deleteCorpusEntry(entry.id)
                            setCorpusEntries(updated)
                          }
                        }}
                        className="opacity-0 group-hover:opacity-100 text-xs px-1.5 py-0.5 rounded bg-red-600/20 hover:bg-red-600/40 text-red-300 transition-all"
                        title="删除此语料"
                      >
                        🗑️
                      </button>
                    </div>
                    <div className="text-sm text-textPrimary leading-relaxed line-clamp-2">
                      {preview}{entry.text.length > 120 ? '…' : ''}
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-[11px] text-textSecondary/50">
                      <span>🧩 {entry.conceptsCount} 概念</span>
                      <span>🔗 {entry.relationsCount} 关系</span>
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </div>

        {/* =================== Token Bridge 区块 =================== */}
        <div className="border border-accent/20 rounded-lg overflow-hidden">
          <div className="px-4 py-3 bg-accent/5 border-b border-accent/20">
            <div className="flex items-center gap-2">
              <span className="text-lg">🔗</span>
              <h2 className="text-sm font-semibold text-accent">Token Bridge — 无 LLM 推理</h2>
            </div>
            <p className="text-xs text-textSecondary mt-1">
              加载蒸馏后的 EML 图，在浏览器本地进行概念搜索与知识推理（无需调用 API）
            </p>
          </div>

          <div className="px-4 py-3 space-y-3">
            {/* 加载按钮 */}
            <div className="flex items-center gap-3 flex-wrap">
              {/* 上传 EML 文件 */}
              <label className={[
                'flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-colors cursor-pointer',
                'bg-white/10 hover:bg-white/15 text-textPrimary'
              ].join(' ')}>
                📂 加载 EML 文件
                <input
                  type="file"
                  accept=".eml"
                  onChange={handleLoadEML}
                  className="hidden"
                />
              </label>

              {/* 从蒸馏结果直接加载 */}
              {emlBuffer && !bridgeState.loaded && (
                <button
                  onClick={handleLoadFromDistill}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-colors bg-accent/20 hover:bg-accent/30 text-accent"
                >
                  🔗 加载当前蒸馏结果
                </button>
              )}

              {/* 状态信息 */}
              {bridgeState.loaded && (
                <span className="text-xs text-textSecondary">
                  ✅ {bridgeState.fileName}&nbsp;
                  <span title="概念节点数">🔵 节点={bridgeState.vertexCount}</span>&nbsp;
                  <span title="关系边数">🔗 边={bridgeState.edgeCount}</span>&nbsp;
                  <span title="知识条数（节点+边）">K={bridgeState.vertexCount + bridgeState.edgeCount}</span>&nbsp;
                  <span title="平均信息存在度（谱折叠深度）">𝕀̄={bridgeState.avgDelta.toFixed(3)}</span>&nbsp;
                  <span title="路由阈值：置信度≥0.5走翻译官（精确检索EML图谱），<0.5走作家（LLM创造性生成）">🔮 路由阈值 0.50</span>
                </span>
              )}
            </div>

            {/* 搜索区 + 图谱可视化 Tab */}
            {bridgeState.loaded && (
              <div className="space-y-4">
                {/* Tab 切换 */}
                <div className="flex gap-2 border-b border-white/10">
                  <button onClick={() => setActiveTab('graph')} className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'graph' ? 'border-indigo-400 text-indigo-300' : 'border-transparent text-textSecondary hover:text-textPrimary'}`}>
                    🕸️ 图谱可视化
                  </button>
                  <button onClick={() => setActiveTab('reasoning')} className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'reasoning' ? 'border-indigo-400 text-indigo-300' : 'border-transparent text-textSecondary hover:text-textPrimary'}`}>
                    🔍 推理测试
                  </button>
                  <button onClick={() => setActiveTab('knowledge')} className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'knowledge' ? 'border-indigo-400 text-indigo-300' : 'border-transparent text-textSecondary hover:text-textPrimary'}`}>
                    📚 知识浏览 ({bridgeState.vertexCount + bridgeState.edgeCount})
                  </button>
                </div>

                {/* 推理测试 Tab */}
                {activeTab === 'reasoning' && (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                        placeholder="输入查询词…（如：量子计算）"
                        className="flex-1 bg-white/5 border border-white/10 rounded-md px-3 py-2 text-sm text-textPrimary placeholder-textSecondary/50 focus:outline-none focus:border-accent/50"
                      />
                      <button
                        onClick={handleSearch}
                        disabled={searchLoading || !searchQuery.trim()}
                        className={[
                          'flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-colors',
                          searchLoading || !searchQuery.trim()
                            ? 'bg-white/10 text-textSecondary cursor-not-allowed'
                            : 'bg-accent hover:bg-accentHover text-white'
                        ].join(' ')}
                      >
                        {searchLoading ? '⏳' : '🔍'} 搜索
                      </button>
                      <button
                        onClick={handleGenerate}
                        disabled={generating || !searchQuery.trim()}
                        className={[
                          'flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-colors',
                          generating || !searchQuery.trim()
                            ? 'bg-white/10 text-textSecondary cursor-not-allowed'
                            : 'bg-emerald-600/30 hover:bg-emerald-600/50 text-emerald-300 border border-emerald-600/30'
                        ].join(' ')}
                      >
                        {generating ? '⏳' : '💬'} 生成回复
                      </button>
                    </div>

                    {/* 搜索结果 */}
                    {searchResult && (
                      <div className="space-y-2">
                        {/* 置信度 */}
                        <div className="flex items-center gap-2 text-xs text-textSecondary">
                          <span>查询：{searchResult.query}</span>
                          <span>·</span>
                          <span>置信度：{(searchResult.confidence * 100).toFixed(1)}%</span>
                          <span>·</span>
                          <span>子图大小：{searchResult.subgraphSize}</span>
                        </div>

                        {/* 匹配概念列表 */}
                        <div className="border border-white/5 rounded-md overflow-hidden">
                          {searchResult.matchedConcepts.length === 0 ? (
                            <div className="px-3 py-3 text-sm text-textSecondary text-center">
                              未找到匹配概念
                            </div>
                          ) : (
                            searchResult.matchedConcepts.map((m, idx) => (
                              <div
                                key={`${m.vertexId}-${idx}`}
                                className="flex items-center gap-3 px-3 py-2 text-sm border-b border-white/5 last:border-b-0 hover:bg-indigo-600/20 cursor-pointer"
                              >
                                <span className="text-textSecondary w-5 text-right flex-shrink-0">
                                  {idx + 1}.
                                </span>
                                <span className="font-medium min-w-0 truncate" title={m.concept}>
                                  {m.concept}
                                </span>
                                {/* 相似度条 */}
                                <div className="w-20 h-1.5 bg-white/10 rounded-full overflow-hidden flex-shrink-0">
                                  <div
                                    className="h-full bg-accent rounded-full"
                                    style={{ width: `${Math.min(m.similarity * 100, 100)}%` }}
                                  />
                                </div>
                                <span className="text-accent font-mono text-xs flex-shrink-0">
                                  {(m.similarity * 100).toFixed(1)}%
                                </span>
                                <span className="text-textSecondary text-xs flex-shrink-0">
                                  δ={m.delta.toFixed(3)}
                                </span>
                              </div>
                            ))
                          )}
                        </div>
                      </div>
                    )}

                    {/* 生成回复 */}
                    {generatedText && (
                      <div className="border border-emerald-600/20 rounded-lg overflow-hidden">
                        <div className="px-3 py-2 bg-emerald-600/10 text-sm font-medium border-b border-emerald-600/20 flex items-center gap-2">
                          <span>💬</span>
                          <span>生成回复</span>
                          <ModeBadge mode={generateMode} />
                        </div>
                        <div className="px-4 py-3 text-sm text-textPrimary whitespace-pre-wrap leading-relaxed font-sans">
                          {generatedText}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* 图谱可视化 Tab — 按语料/知识选择显示 */}
                {activeTab === 'graph' && (
                  <div className="relative w-full" style={{ minHeight: 'calc(80vh - 200px)', maxHeight: 'calc(90vh - 120px)' }}>
                    <EMLGraphVisualization
                      graphData={graphData}
                      height={Math.max(Math.floor(window.innerHeight * 0.72), 600)}
                      // API 数据无语料标记，不传语料过滤（避免"缺少语料标记"警告）
                      selectedCorpus={graphFromAPI ? null : selectedCorpusName}
                      selectedKnowledgeId={selectedKnowledgeId}
                      edgeWeightThreshold={edgeWeightThreshold}
                      onEdgeWeightThresholdChange={setEdgeWeightThreshold}
                      showAllByDefault={graphFromAPI}
                    />
                  </div>
                )}

                {/* 知识浏览 Tab */}
                {activeTab === 'knowledge' && bridgeState.graph && (
                  <KnowledgeBrowser
                    graph={bridgeState.graph}
                    conceptNames={concepts.length > 0 ? ((): Map<number, string> => {
                      const m = new Map<number, string>()
                      concepts.forEach((c, i) => m.set(i, c.concept))
                      return m
                    })() : undefined}
                    onGraphUpdated={async (newGraph) => {
                      const buffer = serializeEML(newGraph)
                      const conceptNames = new Map<number, string>()
                      newGraph.vertices.forEach(v => conceptNames.set(v.id, v.label))
                      bridgeClient.current.loadEML(newGraph, conceptNames)
                      const avgDelta = newGraph.vertices.length > 0
                        ? newGraph.vertices.reduce((s, v) => s + v.delta, 0) / newGraph.vertices.length
                        : 0
                      setBridgeState({
                        loaded: true,
                        graph: newGraph,
                        fileName: bridgeState.fileName,
                        fileSize: buffer.byteLength,
                        vertexCount: newGraph.vertices.length,
                        edgeCount: newGraph.edges.length,
                        avgDelta
                      })
                      // 用真实概念名替换占位符（删除操作不改变领域信息）
                      const vizGraph = extractGraphForVisualization(buffer)
                      if (vizGraph && concepts.length > 0) {
                        const nameMap = new Map<number, string>()
                        concepts.forEach((c, i) => nameMap.set(i, c.concept))
                        vizGraph.vertices.forEach(v => {
                          const realName = nameMap.get(v.id)
                          if (realName) v.label = realName
                          // 保留已有的 corpusName 标记
                        })
                      }
                      if (vizGraph) { setGraphData(vizGraph); setGraphFromAPI(false) }
                    }}
                  />
                )}
              </div>
            )}

            {/* 未加载提示 */}
            {!bridgeState.loaded && (
              <div className="text-center py-4 text-sm text-textSecondary">
                {phase === 'done'
                  ? '👆 点击「加载当前蒸馏结果」或上传 .eml 文件开始推理'
                  : '👆 先蒸馏语料或上传 .eml 文件，即可在此进行本地概念搜索'}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

/** 合并预览面板：显示重叠概念和冲突关系统计 */
function MergePreviewPanel({
  summary,
  onConfirm,
  onCancel,
  merging
}: {
  summary: MergeSummary
  onConfirm: () => void
  onCancel: () => void
  merging: boolean
}) {
  const totalIssues = summary.conceptOverlaps.length + summary.relationConflicts.length

  return (
    <div className="border border-amber-600/30 rounded-lg overflow-hidden">
      <div className="px-3 py-2 bg-amber-600/10 text-sm font-medium border-b border-amber-600/20 flex items-center gap-2">
        <span>🔄</span>
        <span>合并预览 — 新旧知识冲突检测</span>
        {totalIssues > 0 && (
          <span className="text-xs text-amber-300 ml-auto">
            {summary.conceptOverlaps.length} 重叠概念 + {summary.relationConflicts.length} 冲突关系
          </span>
        )}
      </div>
      <div className="px-4 py-3 space-y-2 text-sm">
        {/* 统计网格 */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <MergeStat label="新增概念" value={summary.conceptNewCount} color="text-emerald-300" bg="bg-emerald-600/10" />
          <MergeStat label="重叠概念" value={summary.conceptOverlaps.length} color="text-amber-300" bg="bg-amber-600/10" />
          <MergeStat label="新增关系" value={summary.relationNewCount} color="text-emerald-300" bg="bg-emerald-600/10" />
          <MergeStat label="冲突关系" value={summary.relationConflicts.length} color="text-amber-300" bg="bg-amber-600/10" />
        </div>

        {/* 重叠概念详情 */}
        {summary.conceptOverlaps.length > 0 && (
          <div className="text-xs text-textSecondary mt-2">
            <span className="text-amber-300">⚠️ 重叠概念（保留高𝕏值的一方）：</span>
            <div className="mt-1 space-y-0.5 max-h-32 overflow-y-auto">
              {summary.conceptOverlaps.map(o => (
                <div key={o.name} className="flex items-center gap-2">
                  <span className="font-medium">{o.name}</span>
                  <span className="text-textSecondary/60">旧 δ={o.existingDelta.toFixed(2)}</span>
                  <span className="text-amber-300">←</span>
                  <span className="text-textSecondary/60">新 𝕏={o.newImportance.toFixed(2)}</span>
                  <span className="text-xs text-textSecondary/40">
                    → 保留 {o.existingDelta >= o.newImportance ? '旧值' : '新值'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 冲突关系详情 */}
        {summary.relationConflicts.length > 0 && (
          <div className="text-xs text-textSecondary mt-1">
            <span className="text-amber-300">⚠️ 冲突关系（保留高强度一方，类型以新蒸馏为准）：</span>
            <div className="mt-1 space-y-0.5 max-h-32 overflow-y-auto">
              {summary.relationConflicts.map(r => (
                <div key={`${r.src}-${r.dst}`} className="flex items-center gap-2">
                  <span className="font-medium">{r.src}→{r.dst}</span>
                  <span className="text-textSecondary/60">旧 w={r.existingWeight.toFixed(2)}</span>
                  <span className="text-amber-300">←</span>
                  <span className="text-textSecondary/60">新 {r.newType}={r.newStrength.toFixed(2)}</span>
                  <span className="text-xs text-textSecondary/40">
                    → 保留 {r.existingWeight >= r.newStrength ? '旧值' : '新值'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 冗余关系提示 */}
        {summary.relationDuplicateCount > 0 && (
          <div className="text-xs text-textSecondary/60 mt-1">
            ℹ️ {summary.relationDuplicateCount} 条关系与已有图谱一致，不会重复添加
          </div>
        )}

        {/* 全无冲突提示 */}
        {totalIssues === 0 && (
          <div className="text-xs text-emerald-300 mt-2">
            ✅ 新蒸馏知识全部是增量，没有重叠或冲突，可以直接合并
          </div>
        )}

        {/* 策略说明 */}
        <div className="text-xs text-textSecondary/50 mt-2 border-t border-white/5 pt-2">
          💡 合并策略：重叠概念保留高𝕏值方 · 冲突关系保留高强度方 · 无冲突知识全部保留
        </div>

        {/* 操作按钮 */}
        <div className="flex gap-2 pt-2">
          <button
            onClick={onConfirm}
            disabled={merging}
            className="px-4 py-1.5 bg-amber-600/30 hover:bg-amber-600/50 text-amber-300 text-sm rounded-md transition-colors disabled:opacity-50"
          >
            {merging ? '⏳ 合并中…' : '✅ 确认合并'}
          </button>
          <button
            onClick={onCancel}
            className="px-4 py-1.5 bg-white/10 hover:bg-white/15 text-textSecondary text-sm rounded-md transition-colors"
          >
            取消
          </button>
        </div>
      </div>
    </div>
  )
}

/** 知识浏览器：概念和关系分两张表展示，支持点击查看子图 */
function KnowledgeBrowser({
  graph,
  onGraphUpdated,
  conceptNames,
  onSelectConcept,
  onSelectRelation,
  /** 当前选中的关系 key（格式 "src-dst"），用于关系列表高亮 */
  selectedRelationKey,
}: {
  graph: import('../types').EMLGraphData
  onGraphUpdated: (newGraph: import('../types').EMLGraphData) => void
  conceptNames?: Map<number, string>
  /** 点击概念时回调 → 切换到图谱 Tab 显示该概念邻域 */
  onSelectConcept?: (vertexId: number) => void
  /** 点击关系时回调 → 切换到图谱 Tab 显示该关系两端概念的邻域 */
  onSelectRelation?: (srcId: number, dstId: number) => void
  selectedRelationKey?: string | null
}) {
  const [deleting, setDeleting] = useState(false)
  const toast = useToast()

  // 搜索/过滤状态
  const [conceptSearch, setConceptSearch] = useState('')
  const [relationSearch, setRelationSearch] = useState('')

  // 过滤概念列表
  const filteredVertices = conceptSearch.trim()
    ? graph.vertices.filter(v => {
        const label = getDisplayName(v.id, v.label)
        return label.toLowerCase().includes(conceptSearch.toLowerCase())
      })
    : graph.vertices

  // 过滤关系列表
  const filteredEdges = relationSearch.trim()
    ? graph.edges.filter(e => {
        const srcLabel = vertexLabel.get(e.src) ?? `v${e.src}`
        const dstLabel = vertexLabel.get(e.dst) ?? `v${e.dst}`
        const q = relationSearch.toLowerCase()
        return srcLabel.toLowerCase().includes(q) || dstLabel.toLowerCase().includes(q)
      })
    : graph.edges

  // 构建关系标签映射（优先使用真实概念名）
  const vertexLabel = new Map<number, string>()
  graph.vertices.forEach(v => {
    const realName = conceptNames?.get(v.id)
    vertexLabel.set(v.id, realName ?? v.label)
  })

  /** 获取概念显示名（优先真实名称） */
  const getDisplayName = (vertexId: number, fallback: string) => {
    return conceptNames?.get(vertexId) ?? fallback
  }

  // DIKWP 层分布计算 (根据 delta/I-value 分 bin)
  const dikwpPieData = useMemo((): DIKWPLayerInfo[] => {
    const edges = graph.edges
    // 用 delta 字段 (ℐ-值), 回退到 weight
    const iValues = edges.map(e => (e as any).delta ?? (e as any).i_val ?? e.weight).filter((v: number) => !isNaN(v))
    if (iValues.length === 0) return []

    // ℐ-bin 分桶: D(0-0.15) I(0.15-0.35) K(0.35-0.65) W(0.65-0.85) P(0.85-1.0)
    const bins = { D: 0, I: 0, K: 0, W: 0, P: 0 }
    const binDefs = { D: [0, 0.15], I: [0.15, 0.35], K: [0.35, 0.65], W: [0.65, 0.85], P: [0.85, 1.0] } as const
    const names = { D: '数据 Data', I: '信息 Info', K: '知识 Knowledge', W: '智慧 Wisdom', P: '目的 Purpose' }

    for (const v of iValues) {
      for (const [layer, [lo, hi]] of Object.entries(binDefs)) {
        if (v >= lo && (v < hi || (layer === 'P' && v >= hi))) {
          (bins as any)[layer]++
          break
        }
      }
    }

    const total = Math.max(iValues.length, 1)
    return (['D', 'I', 'K', 'W', 'P'] as const).map(layer => ({
      layer,
      name: names[layer],
      count: bins[layer],
      percentage: Math.round(bins[layer] / total * 1000) / 10,
    }))
  }, [graph.edges])

  /** 删除指定概念 */
  const handleDeleteConcept = async (vertexId: number, label: string) => {
    if (deleting) return
    const displayName = getDisplayName(vertexId, label)
    // 统计关联关系数
    const relatedEdges = graph.edges.filter(e => e.src === vertexId || e.dst === vertexId)
    const msg = relatedEdges.length > 0
      ? `删除概念「${displayName}」将同时删除 ${relatedEdges.length} 条关联关系，确认？`
      : `确认删除概念「${displayName}」？`
    if (!confirm(msg)) return

    setDeleting(true)
    try {
      const newGraph = await rebuildGraphAfterDelete(
        graph,
        new Set([vertexId]),
        new Set()
      )
      onGraphUpdated(newGraph)
    } catch (err) {
      toast.error(`删除失败：${err instanceof Error ? err.message : '未知错误'}`)
    } finally {
      setDeleting(false)
    }
  }

  /** 删除指定关系 */
  const handleDeleteRelation = async (srcLabel: string, dstLabel: string) => {
    if (deleting) return
    if (!confirm(`确认删除关系「${srcLabel} → ${dstLabel}」？`)) return

    setDeleting(true)
    try {
      const newGraph = await rebuildGraphAfterDelete(
        graph,
        new Set(),
        new Set([`${srcLabel}→${dstLabel}`])
      )
      onGraphUpdated(newGraph)
    } catch (err) {
      toast.error(`删除失败：${err instanceof Error ? err.message : '未知错误'}`)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="space-y-3">
      {/* 统计概览 */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <div className="border border-white/10 rounded-lg px-3 py-2 text-center bg-emerald-600/5">
          <div className="text-lg font-bold text-emerald-300">{graph.vertices.length}</div>
          <div className="text-xs text-textSecondary">概念 V</div>
        </div>
        <div className="border border-white/10 rounded-lg px-3 py-2 text-center bg-indigo-600/5">
          <div className="text-lg font-bold text-indigo-300">{graph.edges.length}</div>
          <div className="text-xs text-textSecondary">关系 E</div>
        </div>
        <div className="border border-white/10 rounded-lg px-3 py-2 text-center bg-amber-600/5">
          <div className="text-lg font-bold text-amber-300">{graph.vertices.length + graph.edges.length}</div>
          <div className="text-xs text-textSecondary">知识条数 K</div>
        </div>
        <div className="border border-white/10 rounded-lg px-3 py-2 text-center bg-violet-600/5">
          <div className="text-lg font-bold text-violet-300">
            {graph.vertices.length > 0
              ? (graph.vertices.reduce((s, v) => s + v.delta, 0) / graph.vertices.length).toFixed(3)
              : '—'}
          </div>
          <div className="text-xs text-textSecondary">𝕀̄ 均值</div>
        </div>
      </div>

      {/* DIKWP 层分布饼图 */}
      <DIKWPPieChart
        data={dikwpPieData}
        totalEdges={graph.edges.length}
      />

        {/* 概念列表 */}
      <div className="border border-white/10 rounded-lg overflow-hidden">
        <div className="px-3 py-2 bg-emerald-600/10 text-sm font-medium border-b border-white/10 flex items-center gap-2">
          <span>🧩</span>
          <span>概念列表</span>
          <span className="text-xs text-textSecondary ml-auto">{filteredVertices.length}/{graph.vertices.length} 条</span>
        </div>
        {/* 搜索框 */}
        <div className="px-2 py-1.5 border-b border-white/5">
          <input
            type="text"
            value={conceptSearch}
            onChange={e => setConceptSearch(e.target.value)}
            placeholder="搜索概念名称…"
            className="w-full px-2.5 py-1.5 text-xs rounded-md border border-white/10 bg-white/5 text-textPrimary placeholder-textSecondary/40 focus:outline-none focus:border-accent/50 transition-colors"
          />
        </div>
        <div className="max-h-64 overflow-y-auto">
          {filteredVertices.length === 0 ? (
            <div className="px-4 py-6 text-center text-sm text-textSecondary">{conceptSearch.trim() ? '无匹配结果' : '暂无概念'}</div>
          ) : (
            filteredVertices.map(v => (
              <div
                key={v.id}
                className={`flex items-center gap-3 px-4 py-2 border-b border-white/5 transition-colors hover:bg-indigo-600/20 ${onSelectConcept ? 'cursor-pointer group' : 'group'}`}
                onClick={() => onSelectConcept?.(v.id)}
                title={onSelectConcept ? '点击查看此概念的知识图谱邻域' : undefined}
              >
                <span className="flex-1 text-sm font-medium text-textPrimary truncate">{getDisplayName(v.id, v.label)}</span>
                <span
                  className="text-xs text-textSecondary/60 font-mono shrink-0"
                  title="信息存在度 (delta)"
                >
                  𝕏={v.delta.toFixed(2)}
                </span>
                <button
                  onClick={() => handleDeleteConcept(v.id, v.label)}
                  disabled={deleting}
                  className="shrink-0 opacity-0 group-hover:opacity-100 text-xs px-2 py-0.5 rounded bg-red-600/20 hover:bg-red-600/40 text-red-300 transition-all disabled:opacity-30"
                  title="删除此概念及其所有关联关系"
                >
                  🗑️
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* 关系列表 */}
      <div className="border border-white/10 rounded-lg overflow-hidden mt-3">
        <div className="px-3 py-2 bg-indigo-600/10 text-sm font-medium border-b border-white/10 flex items-center gap-2">
          <span>🔗</span>
          <span>关系列表</span>
          <span className="text-xs text-textSecondary ml-auto">{filteredEdges.length}/{graph.edges.length} 条</span>
        </div>
        {/* 搜索框 */}
        <div className="px-2 py-1.5 border-b border-white/5">
          <input
            type="text"
            value={relationSearch}
            onChange={e => setRelationSearch(e.target.value)}
            placeholder="搜索关系（源→目标）…"
            className="w-full px-2.5 py-1.5 text-xs rounded-md border border-white/10 bg-white/5 text-textPrimary placeholder-textSecondary/40 focus:outline-none focus:border-accent/50 transition-colors"
          />
        </div>
        <div className="max-h-64 overflow-y-auto">
          {filteredEdges.length === 0 ? (
            <div className="px-4 py-6 text-center text-sm text-textSecondary">{relationSearch.trim() ? '无匹配结果' : '暂无关系'}</div>
          ) : (
            filteredEdges.map((e, idx) => {
              const srcLabel = vertexLabel.get(e.src) ?? `v${e.src}`
              const dstLabel = vertexLabel.get(e.dst) ?? `v${e.dst}`
              const etype = e.associatorFlag === 1 ? 'causes' : 'related_to'
              return (
                <div
                  key={idx}
                  className={`flex flex-col gap-0.5 px-4 py-2.5 border-b border-white/5 transition-colors hover:bg-indigo-600/20 ${onSelectRelation ? 'cursor-pointer group' : 'group'} ${selectedRelationKey === `${e.src}-${e.dst}` ? 'bg-indigo-600/30 border-l-2 border-l-indigo-400' : ''}`}
                  onClick={() => onSelectRelation?.(e.src, e.dst)}
                  title={onSelectRelation ? '点击查看此关系的知识图谱邻域' : undefined}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-emerald-300 shrink-0">{srcLabel}</span>
                    <span className="text-textSecondary/40 text-xs">—</span>
                    <span className="text-xs text-amber-300/80 px-1.5 py-0.5 rounded bg-amber-600/10 shrink-0 font-medium">{RELATION_TYPE_LABELS[etype] || etype}</span>
                    <span className="text-textSecondary/40 text-xs">→</span>
                    <span className="text-sm font-medium text-indigo-300 shrink-0">{dstLabel}</span>
                  </div>
                  <div className="flex items-center justify-between pl-1">
                    <span className="text-xs text-textSecondary/50 font-mono">权重={e.weight.toFixed(2)}</span>
                    <div className="flex items-center gap-1">
                      {onSelectRelation && (
                        <span className="text-[10px] text-indigo-400/50">点击查看邻域 ↗</span>
                      )}
                      <button
                        onClick={(ev) => { ev.stopPropagation(); handleDeleteRelation(srcLabel, dstLabel) }}
                        disabled={deleting}
                        className="opacity-0 group-hover:opacity-100 text-xs px-1.5 py-0.5 rounded bg-red-600/15 hover:bg-red-600/30 text-red-400 transition-all disabled:opacity-30"
                        title="删除此关系"
                      >
                        🗑
                      </button>
                    </div>
                  </div>
                </div>
              )
            })
          )}
        </div>
      </div>

      {/* 提示 */}
      <div className="text-xs text-textSecondary/50 border-t border-white/5 pt-2">
        💡 悬停任意行可看到删除按钮 · 删除概念会同时删除其所有关联关系 · 删除后图谱自动重建
      </div>
    </div>
  )
}

/** 合并统计子组件 */
function MergeStat({ label, value, color, bg }: { label: string; value: number; color: string; bg: string }) {
  return (
    <div className={`${bg} border border-white/5 rounded-lg px-3 py-2 text-center`}>
      <div className={`text-lg font-bold ${color}`}>{value}</div>
      <div className="text-xs text-textSecondary">{label}</div>
    </div>
  )
}

/** 统计卡片子组件 */
function StatCard({ label, value, clickable, onClick }: {
  label: string
  value: string
  clickable?: boolean
  onClick?: () => void
}) {
  return (
    <div
      className={[
        'border border-white/10 rounded-lg px-4 py-3 text-center transition-colors duration-150',
        clickable ? 'cursor-pointer hover:border-accent/50 hover:bg-accent/5 group' : ''
      ].join(' ')}
      onClick={clickable ? onClick : undefined}
    >
      <div className={[
        'text-2xl font-bold text-accent',
        clickable ? 'group-hover:scale-105 transition-transform duration-150' : ''
      ].join(' ')}>{value}</div>
      <div className={[
        'text-xs mt-0.5',
        clickable ? 'text-accent/60 group-hover:text-accent/80' : 'text-textSecondary'
      ].join(' ')}>{label}</div>
    </div>
  )
}
