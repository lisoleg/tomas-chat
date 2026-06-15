import React, { useRef, useEffect, useState, useMemo, useCallback } from 'react'
import * as d3 from 'd3'

export interface EMLGraphData {
  vertices: Array<{
    id: number
    label: string
    delta: number
    info_existence: number
    /** 所属语料名称（如 "⚛️物理"、"🧪化学"）— 用于按语料过滤 */
    corpusName?: string
  }>
  edges: Array<{
    src: number
    dst: number
    weight: number
    associator_flag: number
  }>
}

interface EMLGraphVisualizationProps {
  /** 完整图谱数据（所有语料合并后的全集） */
  graphData: EMLGraphData | null
  /** 当前选中的语料名称 → 只显示该语料的子图 */
  selectedCorpus?: string | null
  /** 当前选中的知识节点 ID → 只显示该节点及其邻居的子图 */
  selectedKnowledgeId?: number | null
  height?: number
  onNodeClick?: (nodeId: number) => void
  selectedNodeId?: number | null
  /** 边权重阈值（低于此值的边不显示，默认 0.2） */
  edgeWeightThreshold?: number
  /** 边权重阈值变更回调 */
  onEdgeWeightThresholdChange?: (threshold: number) => void
  /** 当前选中的关系 key（格式 "src-dst"），显示该关系两端节点的联合邻域并高亮此边 */
  selectedRelationKey?: string | null
  /** 当没有选中任何项目时是否默认全量显示（用于从 API 加载的数据） */
  showAllByDefault?: boolean
}

/**
 * EML 概念关系图谱可视化（D3.js 力导向图）
 *
 * 核心交互：
 * - 选中某个语料 → 显示该语料的子图
 * - 选中某个知识项 → 显示该知识的邻域子图
 * - 缺省不显示（提示用户选择）
 */
export const EMLGraphVisualization: React.FC<EMLGraphVisualizationProps> = ({
  graphData,
  selectedCorpus = null,
  selectedKnowledgeId = null,
  selectedRelationKey = null,
  height = 620,
  onNodeClick,
  selectedNodeId = null,
  edgeWeightThreshold = 0.2,
  onEdgeWeightThresholdChange,
  showAllByDefault = false,
}) => {
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const simulationRef = useRef<d3.Simulation<d3.SimulationNodeDatum, undefined> | null>(null)
  const [containerSize, setContainerSize] = useState({ w: 800, h: height })
  const [tooltip, setTooltip] = useState<{ x: number; y: number; content: string } | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const searchRef = useRef<HTMLInputElement>(null)
  const [renderError, setRenderError] = useState<string | null>(null)

  // ── 边颜色映射（提升至组件顶层，供高亮 useEffect 使用）──
  const EDGE_COLOR_MAP: Record<number, string> = {
    0: '#6366f1',   // indigo  - 一般关联
    1: '#f59e0b',   // amber   - 因果
    2: '#10b981',   // emerald - 组成/部分
    3: '#ec4899',   // pink    - 对比/对立
    4: '#8b5cf6',   // violet  - 层级
  }
  const getEdgeColor = (flag: number): string => {
    return EDGE_COLOR_MAP[flag] ?? '#6366f1'
  }

  // ── 响应式尺寸：监听容器实际大小 ──
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const ro = new ResizeObserver(entries => {
      for (const e of entries) {
        const rect = e.target.getBoundingClientRect()
        if (rect.width > 50 && rect.height > 50) {
          setContainerSize({ w: Math.floor(rect.width), h: Math.max(Math.floor(rect.height), 300) })
        }
      }
    })
    ro.observe(container)
    return () => ro.disconnect()
  }, [height])

  // ── 根据 selectedCorpus / selectedKnowledgeId 过滤子图 ──
  const [filterWarning, setFilterWarning] = useState<string | null>(null)

  const filteredData = useMemo(() => {
    if (!graphData) return null

    // 优先：选中了知识项 → 提取该节点的 1-hop 邻居子图
    if (selectedKnowledgeId != null) {
      const neighborIds = new Set<number>([selectedKnowledgeId])
      for (const e of graphData.edges) {
        if (e.src === selectedKnowledgeId) neighborIds.add(e.dst)
        if (e.dst === selectedKnowledgeId) neighborIds.add(e.src)
      }
      return {
        vertices: graphData.vertices.filter(v => neighborIds.has(v.id)),
        edges: graphData.edges.filter(e => neighborIds.has(e.src) && neighborIds.has(e.dst))
      }
    }

    // 其次：选中了关系 → 显示该关系两端节点的联合邻域子图
    if (selectedRelationKey && graphData) {
      const parts = selectedRelationKey.split('-')
      if (parts.length >= 2) {
        const srcId = parseInt(parts[0], 10)
        const dstId = parseInt(parts[parts.length - 1], 10)
        if (!isNaN(srcId) && !isNaN(dstId)) {
          const neighborIds = new Set<number>([srcId, dstId])
          for (const e of graphData.edges) {
            if (e.src === srcId || e.dst === srcId) {
              const other = e.src === srcId ? e.dst : e.src
              if (!neighborIds.has(other)) neighborIds.add(other)
            }
            if (e.src === dstId || e.dst === dstId) {
              const other = e.src === dstId ? e.dst : e.src
              if (!neighborIds.has(other)) neighborIds.add(other)
            }
          }
          return {
            vertices: graphData.vertices.filter(v => neighborIds.has(v.id)),
            edges: graphData.edges.filter(e => neighborIds.has(e.src) && neighborIds.has(e.dst))
          }
        }
      }
    }

    // 第三：选中了语料 → 只显示该语料的节点+边
    if (selectedCorpus) {
      // 检查是否有任何顶点带有 corpusName（API 数据可能全部为 null）
      const hasAnyCorpusName = graphData.vertices.some(v => v.corpusName)
      if (!hasAnyCorpusName) {
        // API 数据无语料标记 → 忽略语料过滤，直接全量显示（不报错）
        setFilterWarning(null)
        return { vertices: graphData.vertices, edges: graphData.edges }
      }
      const corpusVertexIds = new Set(
        graphData.vertices.filter(v => v.corpusName === selectedCorpus).map(v => v.id)
      )
      if (corpusVertexIds.size === 0) {
        // 有语料标记但当前选中的不匹配 → 返回 null
        setFilterWarning(null)
        return null
      }
      setFilterWarning(null)
      return {
        vertices: graphData.vertices.filter(v => corpusVertexIds.has(v.id)),
        edges: graphData.edges.filter(e => corpusVertexIds.has(e.src) && corpusVertexIds.has(e.dst))
      }
    }

    // 都没选中 → 通常返回 null（显示空状态提示）
    // 但如果 showAllByDefault=true（数据来自 API），则全量显示
    setFilterWarning(null)
    if (showAllByDefault) {
      return { vertices: graphData.vertices, edges: graphData.edges }
    }
    return null
  }, [graphData, selectedCorpus, selectedKnowledgeId, selectedRelationKey, showAllByDefault])

  // ── 导出当前图谱为 JSON 文件（必须在 filteredData 声明之后）──
  const handleExport = useCallback(() => {
    const dataToExport = filteredData ?? graphData
    if (!dataToExport) return
    const now = new Date().toISOString()
    const domain = selectedCorpus ?? 'all'
    const json = {
      version: '1.0',
      exported_at: now,
      domain,
      vertices: dataToExport.vertices.map(v => ({
        id: v.id,
        label: v.label,
        delta: v.delta,
        info_existence: v.info_existence,
        corpusName: v.corpusName ?? null,
      })),
      edges: dataToExport.edges
        .filter(e => e.weight >= edgeWeightThreshold)
        .map(e => ({
          src: e.src,
          dst: e.dst,
          weight: e.weight,
          associator_flag: e.associator_flag,
        })),
    }
    const blob = new Blob([JSON.stringify(json, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `eml-graph-export-${Date.now()}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }, [filteredData, graphData, selectedCorpus, edgeWeightThreshold])

  // 可见边数统计（用于滑块旁的计数）
  const visibleEdgeCount = useMemo(() => {
    if (!filteredData) return 0
    return filteredData.edges.filter(e => e.weight >= edgeWeightThreshold).length
  }, [filteredData, edgeWeightThreshold])

  // ── 搜索高亮：根据 searchQuery 高亮匹配节点 ──
  useEffect(() => {
    if (!svgRef.current || !filteredData) return
    const svg = d3.select(svgRef.current)
    const q = searchQuery.toLowerCase().trim()
    const filteredDataEdges = filteredData.edges.filter(e => e.weight >= edgeWeightThreshold)

    // 构建匹配节点 ID 集合
    const matchingIds = new Set<number>()
    if (q) {
      filteredData.vertices.forEach(v => {
        if (v.label.toLowerCase().includes(q)) matchingIds.add(v.id)
      })
    }

    // 节点高亮
    svg.selectAll<SVGCircleElement, any>('.nodes circle')
      .attr('opacity', d => !q ? 1 : (matchingIds.has(d.id) ? 1 : 0.12))
      .attr('stroke', (d: any) => {
        if (!q) return d.id === selectedNodeId ? '#fbbf24' : '#1e1b4b'
        return matchingIds.has(d.id) ? '#fbbf24' : (d.id === selectedNodeId ? '#fbbf24' : '#1e1b4b')
      })
      .attr('stroke-width', (d: any) => {
        if (!q) return d.id === selectedNodeId ? 3 : 1.5
        return matchingIds.has(d.id) ? 2.5 : (d.id === selectedNodeId ? 3 : 1.5)
      })

    // 边高亮：通过 index 查找对应 edge
    svg.selectAll<SVGLineElement, any>('.links line')
      .attr('stroke-opacity', (_e: any, i: number) => {
        if (!q) return 0.4
        const edge = filteredDataEdges[i]
        if (!edge) return 0.05
        return (matchingIds.has(edge.src) || matchingIds.has(edge.dst)) ? 0.7 : 0.05
      })
      .attr('stroke-width', (_e: any, i: number) => {
        if (!q) return 0.5 + (filteredDataEdges[i]?.weight ?? 0) * 2.5
        const edge = filteredDataEdges[i]
        if (!edge) return 0.3
        return (matchingIds.has(edge.src) || matchingIds.has(edge.dst)) ? (1 + edge.weight * 3) : 0.3
      })

    // 标签高亮
    svg.selectAll<SVGTextElement, any>('.labels text')
      .style('opacity', (d: any) => {
        if (!q) return filteredData.vertices.length <= 60 ? 1 : 0
        return matchingIds.has(d.id) ? 1 : 0
      })

    // hover 标签也同步
    svg.selectAll<SVGTextElement, any>('.hover-labels text')
      .style('opacity', (d: any) => {
        if (!q) return 0
        return matchingIds.has(d.id) ? 1 : 0
      })
  }, [searchQuery, filteredData, edgeWeightThreshold, selectedNodeId])

  // ── D3 渲染核心 ──
  useEffect(() => {
    if (!filteredData || !svgRef.current) return
    setRenderError(null)

    try {
    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const { vertices, edges } = filteredData
    const cw = containerSize.w
    const ch = containerSize.h

    // 边权重过滤
    const filteredEdges = edges.filter(e => e.weight >= edgeWeightThreshold)

    // 节点/边计数（提前声明，后续多处引用）
    const nodeCount = vertices.length
    const linkCount = filteredEdges.length
    // 大图分级优化
    const isLargeGraph = nodeCount > 80
    const isMediumGraph = nodeCount > 40
    const isHugeGraph = nodeCount > 500  // 性能模式阈值
    // 大幅提高节点基础半径，确保文字可读
    const baseRadius = isLargeGraph ? 14 : (isMediumGraph ? 16 : 18)
    const deltaScale = isLargeGraph ? 20 : (isMediumGraph ? 30 : 38)

    // 找到主概念（delta 最大）—— 固定在画布中心
    let mainConceptId = -1
    let maxDelta = -Infinity
    for (const v of vertices) {
      if (v.delta > maxDelta) { maxDelta = v.delta; mainConceptId = v.id }
    }

    // Archimedean spiral 初始布局 —— 所有节点从中心螺旋展开，保证起点都在可视区
    const angleStep = (2 * Math.PI) / Math.max(nodeCount, 1)
    const spiralMaxR = Math.min(cw, ch) * 0.38
    const nodes = vertices.map((v, i) => {
      const isMain = v.id === mainConceptId && nodeCount > 1
      const angle = (i + (isMain ? 0 : 1)) * angleStep  // 主概念跳过螺旋,非主概念从索引1开始排
      const r = isMain ? 0 : (i / Math.max(nodeCount - 1, 1)) * spiralMaxR
      return {
        id: v.id,
        label: v.label,
        delta: v.delta,
        info_existence: v.info_existence,
        radius: Math.max(baseRadius, baseRadius + v.delta * deltaScale),
        x: cw / 2 + r * Math.cos(angle),
        y: ch / 2 + r * Math.sin(angle),
        fx: isMain ? cw / 2 : undefined,
        fy: isMain ? ch / 2 : undefined,
      }
    })

    const links = filteredEdges.map(e => ({
      source: e.src,
      target: e.dst,
      weight: e.weight,
      associator_flag: e.associator_flag,
    }))

    // SVG 容器 + 背景点击清除高亮
    const g = svg.append('g')

    // 透明背景矩形：捕获背景点击，清除节点高亮/搜索
    g.append('rect')
      .attr('width', cw)
      .attr('height', ch)
      .attr('fill', 'transparent')
      .style('pointer-events', 'all')
      .on('click', () => {
        // 清除点击高亮
        svg.selectAll<SVGCircleElement, any>('.nodes circle').attr('opacity', 1)
          .attr('stroke', (d: any) => d.id === selectedNodeId ? '#fbbf24' : '#1e1b4b')
          .attr('stroke-width', (d: any) => d.id === selectedNodeId ? 3 : 1.5)
        svg.selectAll<SVGLineElement, any>('.links line')
          .attr('stroke-opacity', edgeOpacity)
          .attr('stroke-width', (e: any) => 0.5 + e.weight * (isLargeGraph ? 2.2 : 3.0))
        svg.selectAll<SVGTextElement, any>('.labels text')
          .style('opacity', vertices.length <= 60 ? 1 : 0)
        svg.selectAll<SVGTextElement, any>('.hover-labels text').style('opacity', 0)
        setSearchQuery('')
      })

    // 缩放 —— 根据节点数动态计算最佳缩放，小图尽量放大填满画布
    const defaultScale = nodeCount <= 5 ? 2.0
      : nodeCount <= 10 ? 1.6
      : nodeCount <= 20 ? 1.2
      : nodeCount <= 40 ? 0.9
      : nodeCount <= 80 ? 0.65
      : 0.45
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.15, 10])
      .on('zoom', (event) => g.attr('transform', event.transform.toString()))

    svg.call(zoom)
    svg.call(zoom.transform, d3.zoomIdentity
      .scale(defaultScale)
      .translate(cw * (1 - defaultScale) / 2, ch * (1 - defaultScale) / 2))

    // 力模拟 —— 根据节点数量动态调整参数（四级优化）
    // 四级优化：小图(<40)、中图(40-80)、大图(80-500)、超大图(>500)
    let linkDist: number, chargeStrength: number, collidePadding: number
    let forceStrength: number, centerStrength: number
    if (isHugeGraph) {
      // 超大图（>500）：性能模式，极度紧凑 + 快速冷却
      linkDist = Math.max(40, 20 + nodeCount * 0.3)
      chargeStrength = Math.max(-15000, -1000 - nodeCount * 100)
      collidePadding = 2
      forceStrength = 0.3
      centerStrength = 0.05
    } else if (nodeCount > 80) {
      // 大图：极度紧凑
      linkDist = Math.max(60, 30 + nodeCount * 0.6)
      chargeStrength = Math.max(-8000, -800 - nodeCount * 50)
      collidePadding = 4
      forceStrength = 0.7
      centerStrength = 0.12
    } else if (nodeCount > 40) {
      // 中图：较紧凑
      linkDist = Math.max(100, 60 + nodeCount)
      chargeStrength = Math.max(-5000, -600 - nodeCount * 40)
      collidePadding = 8
      forceStrength = 0.5
      centerStrength = 0.18
    } else {
      // 小图：宽松可读
      linkDist = Math.max(160, Math.min(350, 80 + nodeCount * 3))
      chargeStrength = Math.max(-2000, Math.min(-400, -300 - nodeCount * 12))
      collidePadding = 14
      forceStrength = 0.3
      centerStrength = 0.25
    }

    const simulation = d3.forceSimulation(nodes as d3.SimulationNodeDatum[])
      .force('link', d3.forceLink(links).id((d: any) => d.id).distance(linkDist).strength(forceStrength))
      .force('charge', d3.forceManyBody().strength(chargeStrength).distanceMax(Math.max(cw, ch) * (nodeCount > 80 ? 0.5 : 0.8)))
      .force('collision', d3.forceCollide().radius((d: any) => d.radius + collidePadding).strength(0.9))
      .force('x', d3.forceX(cw / 2).strength(centerStrength))
      .force('y', d3.forceY(ch / 2).strength(centerStrength))
      .alphaDecay(isHugeGraph ? 0.05 : (nodeCount > 40 ? 0.015 : 0.02))
      .velocityDecay(isHugeGraph ? 0.5 : (nodeCount > 40 ? 0.3 : 0.4))

    simulationRef.current = simulation

    // 绘制边 —— 大幅提升可见性：提高透明度底线 + 加宽线
    const edgeOpacity = linkCount > 300 ? 0.12 : (linkCount > 150 ? 0.18 : (linkCount > 80 ? 0.28 : (linkCount > 40 ? 0.38 : 0.5)))
    const edgeWidthScale = isLargeGraph ? 2.2 : 3.0
    const link = g.append('g').attr('class', 'links')
      .selectAll('line')
      .data(links)
      .enter()
      .append('line')
      .attr('stroke', (d: any) => getEdgeColor(d.associator_flag ?? 0))
      .attr('stroke-opacity', edgeOpacity)
      .attr('stroke-width', (d: any) => 0.5 + d.weight * edgeWidthScale)

    // 绘制节点
    const node = g.append('g').attr('class', 'nodes')
      .selectAll('circle')
      .data(nodes)
      .enter()
      .append('circle')
      .attr('r', (d: any) => d.radius)
      .attr('fill', (d: any) => {
        const t = d.delta
        return `rgb(${Math.round(99 + t * 156)}, ${Math.round(102 + t * 100)}, ${Math.round(241 - t * 100)})`
      })
      .attr('stroke', (d: any) => {
        if (d.id === selectedNodeId) return '#fbbf24'
        if (d.fx !== undefined) return '#f59e0b' // 主概念：金色描边
        return '#1e1b4b'
      })
      .attr('stroke-width', (d: any) => {
        if (d.id === selectedNodeId) return 3
        if (d.fx !== undefined) return 2.5 // 主概念：较粗描边
        return 1.5
      })
      // 主概念光晕效果
      .style('filter', (d: any) => d.fx !== undefined ? 'drop-shadow(0 0 8px rgba(245,158,11,0.5))' : 'none')
      .style('cursor', 'pointer')
      .call(drag(simulation) as any)

    // 节点内标签 —— 根据节点数调整显示策略
    const showStaticLabels = isHugeGraph ? false : (nodes.length <= 60)  // 超大图不显示标签，小图全量显示
    const labelText = g.append('g').attr('class', 'labels')
      .selectAll('text')
      .data(nodes)
      .enter()
      .append('text')
      .text((d: any) => {
        const maxChars = Math.max(3, Math.floor(d.radius / 3.5))  // 允许更多字符
        return d.label.length > maxChars ? d.label.slice(0, maxChars) + '\u2026' : d.label
      })
      .attr('font-size', (d: any) => {
        const base = Math.max(9, Math.min(d.radius * 0.5, 16))
        return d.fx !== undefined ? base * 1.3 : base // 主概念标签放大 30%
      })
      .attr('fill', (d: any) => d.fx !== undefined ? '#fef08a' : '#fde047') // 主概念更亮
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'central')
      .style('pointer-events', 'none')
      .style('font-weight', (d: any) => d.fx !== undefined ? '800' : '600') // 主概念更粗
      .style('user-select', 'none')
      .style('opacity', showStaticLabels ? 1 : 0)

    // 悬停放大标签
    const hoverLabel = g.append('g').attr('class', 'hover-labels')
      .selectAll('text')
      .data(nodes)
      .enter()
      .append('text')
      .text((d: any) => d.label)
      .attr('font-size', (d: any) => Math.min(d.radius * 0.65, 20))  // 悬停标签也稍大
      .attr('fill', '#fbbf24')
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'central')
      .style('opacity', 0)
      .style('pointer-events', 'none')
      .style('font-weight', '700')

    // 语料标签：小图时在每个节点下方显示所属语料
    if (nodes.length <= 50) {
      const corpusLabelData = nodes.filter((d: any) => {
        const v = vertices.find((vv: any) => vv.id === d.id)
        return v?.corpusName
      })
      g.append('g').attr('class', 'corpus-labels')
        .selectAll('text')
        .data(corpusLabelData)
        .enter()
        .append('text')
        .text((d: any) => {
          const v = vertices.find((vv: any) => vv.id === d.id)
          return v?.corpusName ?? ''
        })
        .attr('font-size', 9)
        .attr('fill', '#a78bfa')
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'hanging')
        .style('pointer-events', 'none')
        .style('opacity', 0.7)
    }

    // 悬停交互 + 点击高亮邻居
    // (highlightLinksRef / highlightNodesRef 已在组件顶层声明)

    node
      .on('mouseover', function (event: MouseEvent, d: any) {
        hoverLabel.style('opacity', (hd: any) => hd.id === d.id ? 1 : 0)
        node.attr('stroke', (nd: any) => nd.id === d.id ? '#fbbf24' : '#1e1b4b')
          .attr('stroke-width', (nd: any) => nd.id === d.id ? 3 : 1.5)
        setTooltip({
          x: event.pageX,
          y: event.pageY,
          content: `${d.label}\nδ=${d.delta.toFixed(3)}  𝔇(X)=${(d.info_existence ?? d.delta).toFixed(3)}`,
        })
      })
      .on('mouseout', () => {
        hoverLabel.style('opacity', 0)
        node.attr('stroke', (nd: any) => nd.id === selectedNodeId ? '#fbbf24' : '#1e1b4b')
          .attr('stroke-width', (nd: any) => nd.id === selectedNodeId ? 3 : 1.5)
        setTooltip(null)
      })
      .on('click', (event: MouseEvent, d: any) => {
        event.stopPropagation()
        onNodeClick?.(d.id)
        // 高亮当前节点的邻居
        const neighborIds = new Set<number>([d.id])
        filteredData?.edges.forEach(e => {
          if (e.src === d.id) neighborIds.add(e.dst)
          if (e.dst === d.id) neighborIds.add(e.src)
        })
        // 用 neighborIds 直接高亮，不依赖 D3 变异后的 source/target
        link
          .attr('stroke-opacity', (_e: any, i: number) => {
            const edge = filteredData!.edges.filter(e => e.weight >= edgeWeightThreshold)[i]
            if (!edge) return 0.05
            return (neighborIds.has(edge.src) && neighborIds.has(edge.dst)) ? 0.8 : 0.05
          })
          .attr('stroke-width', (_e: any, i: number) => {
            const edge = filteredData!.edges.filter(e => e.weight >= edgeWeightThreshold)[i]
            if (!edge) return 0.3
            return (neighborIds.has(edge.src) && neighborIds.has(edge.dst)) ? (1 + edge.weight * 3) : 0.3
          })
        node
          .attr('opacity', (nd: any) => neighborIds.has(nd.id) || nd.id === d.id ? 1 : 0.15)
        labelText.style('opacity', (nd: any) => (neighborIds.has(nd.id) || nd.id === d.id) && !showStaticLabels ? 1 : (showStaticLabels ? 1 : 0))
        hoverLabel.style('opacity', (nd: any) => nd.id === d.id ? 1 : 0)
      })

    // Tick —— 用全画布边界
    const pad = 25
    simulation.on('tick', () => {
      link
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y)

      node
        .attr('cx', (d: any) => d.x = Math.max(d.radius + pad, Math.min(cw - d.radius - pad, d.x)))
        .attr('cy', (d: any) => d.y = Math.max(d.radius + pad, Math.min(ch - d.radius - pad, d.y)))

      labelText.attr('x', (d: any) => d.x).attr('y', (d: any) => d.y)
      hoverLabel.attr('x', (d: any) => d.x).attr('y', (d: any) => d.y - d.radius - 10)
      // 语料标签位置
      g.selectAll<SVGTextElement, any>('.corpus-labels text')
        .attr('x', (d: any) => d.x)
        .attr('y', (d: any) => d.y + d.radius + 4)
    })

    // 仿真结束后自动适配缩放 —— 确保所有节点/关系都在可视区域内
    simulation.on('end', () => {
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
      nodes.forEach((d: any) => {
        minX = Math.min(minX, d.x - d.radius - pad)
        minY = Math.min(minY, d.y - d.radius - pad)
        maxX = Math.max(maxX, d.x + d.radius + pad)
        maxY = Math.max(maxY, d.y + d.radius + pad)
      })
      const bbW = Math.max(maxX - minX, 50)
      const bbH = Math.max(maxY - minY, 50)
      const margin = 0.92  // 留 8% 边距
      const scale = Math.min(cw / bbW, ch / bbH, nodeCount <= 5 ? 2.5 : nodeCount <= 10 ? 2.0 : 1.8) * margin
      const tx = (cw - bbW * scale) / 2 - minX * scale
      const ty = (ch - bbH * scale) / 2 - minY * scale
      svg.transition().duration(600).call(
        zoom.transform as any,
        d3.zoomIdentity.translate(tx, ty).scale(scale)
      )
    })

    } catch (err) {
      console.error('[EMLGraphVisualization] D3 render error:', err)
      setRenderError(String(err))
    }

    return () => { simulationRef.current?.stop() }
  }, [filteredData, containerSize, selectedNodeId, edgeWeightThreshold])

  // ── 高亮选中关系 ──
  useEffect(() => {
    if (!svgRef.current || !filteredData || !selectedRelationKey) return
    const svg = d3.select(svgRef.current)
    const parts = selectedRelationKey.split('-')
    if (parts.length < 2) return
    const srcId = parseInt(parts[0], 10)
    const dstId = parseInt(parts[parts.length - 1], 10)
    if (isNaN(srcId) || isNaN(dstId)) return

    const filteredDataEdges = filteredData.edges.filter(e => e.weight >= edgeWeightThreshold)
    const linkCount = filteredDataEdges.length
    const edgeOpacity = linkCount > 300 ? 0.12 : (linkCount > 150 ? 0.18 : (linkCount > 80 ? 0.28 : (linkCount > 40 ? 0.38 : 0.5)))
    const isLargeGraph = filteredData.vertices.length > 80

    // 重置所有边
    svg.selectAll<SVGLineElement, any>('.links line')
      .attr('stroke-opacity', edgeOpacity)
      .attr('stroke-width', (e: any) => 0.3 + e.weight * (isLargeGraph ? 1.5 : 2.5))
      .attr('stroke', (e: any) => getEdgeColor(e.associator_flag ?? 0))

    // 高亮选中的边
    svg.selectAll<SVGLineElement, any>('.links line')
      .filter((_e: any, i: number) => {
        const edge = filteredDataEdges[i]
        if (!edge) return false
        return (edge.src === srcId && edge.dst === dstId) || (edge.src === dstId && edge.dst === srcId)
      })
      .attr('stroke-opacity', 1)
      .attr('stroke-width', (e: any) => 2 + e.weight * 3)
      .attr('stroke', '#fbbf24')
  }, [selectedRelationKey, filteredData, edgeWeightThreshold])

  // ── D3 拖拽行为 ──
  function drag(simulation: d3.Simulation<d3.SimulationNodeDatum, undefined>) {
    return d3.drag<SVGCircleElement, d3.SimulationNodeDatum>()
      .on('start', function (event: any, d: any) {
        if (!event.active) simulation.alphaTarget(0.3).restart()
        d.fx = d.x; d.fy = d.y
      })
      .on('drag', function (event: any, d: any) {
        d.fx = event.x; d.fy = event.y
      })
      .on('end', function (_event: any, d: any) {
        d.fx = null; d.fy = null
      })
  }

  // ── 全局 Escape 清除高亮/搜索 ──
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setSearchQuery('')
        // 清除 D3 高亮
      if (svgRef.current) {
        const svg = d3.select(svgRef.current)
        const feCount = filteredData ? filteredData.edges.filter(e => e.weight >= edgeWeightThreshold).length : 0
        svg.selectAll<SVGCircleElement, any>('.nodes circle')
          .attr('opacity', 1)
          .attr('stroke', (d: any) => d.id === selectedNodeId ? '#fbbf24' : '#1e1b4b')
          .attr('stroke-width', (d: any) => d.id === selectedNodeId ? 3 : 1.5)
        svg.selectAll<SVGLineElement, any>('.links line')
          .attr('stroke-opacity', feCount > 150 ? 0.18 : (feCount > 80 ? 0.28 : (feCount > 40 ? 0.38 : 0.5)))
          .attr('stroke-width', (e: any) => 0.5 + e.weight * 2.5)
        svg.selectAll<SVGTextElement, any>('.labels text')
          .style('opacity', filteredData ? (filteredData.vertices.length <= 60 ? 1 : 0) : 0)
        svg.selectAll<SVGTextElement, any>('.hover-labels text').style('opacity', 0)
      }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [selectedNodeId, filteredData, edgeWeightThreshold])

  // ── 空状态：没有选择任何语料/知识 ──
  const showEmptyState = !filteredData && graphData && graphData.vertices.length > 0

  // 标题文本
  const titleText = useMemo(() => {
    if (selectedCorpus) return `📂 语料：${selectedCorpus}`
    if (selectedKnowledgeId != null && graphData) {
      const v = graphData.vertices.find(v => v.id === selectedKnowledgeId)
      return v ? `🔍 知识：${v.label}` : '🔍 知识邻域'
    }
    // API 全量数据时显示概要
    if (showAllByDefault && filteredData) {
      return `🌐 全部概念（${filteredData.vertices.length} 顶点 · ${filteredData.edges.length} 边）`
    }
    return ''
  }, [selectedCorpus, selectedKnowledgeId, graphData, showAllByDefault, filteredData])

  return (
    <div
      ref={containerRef}
      className="relative border border-white/10 rounded-lg overflow-hidden bg-[#0f0a1a] w-full flex-1"
      style={{ minHeight: `${height}px`, height: `${height}px` }}
    >
      {/* 渲染错误提示 */}
      {renderError && (
        <div className="flex items-center justify-center h-full text-center px-6" style={{ minHeight: `${height}px` }}>
          <div>
            <div className="text-2xl mb-3">⚠️</div>
            <div className="text-sm text-red-300 font-medium mb-2">图谱渲染出错</div>
            <div className="text-xs text-textSecondary/60 max-w-xs leading-relaxed font-mono bg-white/5 rounded-md p-2">
              {renderError}
            </div>
            <button
              onClick={() => { setRenderError(null); window.location.reload() }}
              className="mt-3 px-3 py-1 bg-white/10 hover:bg-white/20 text-xs rounded-md transition-colors"
            >
              刷新页面
            </button>
          </div>
        </div>
      )}

      {/* 顶部控制栏：搜索 + 边权重阈值 */}
      {!showEmptyState && filteredData && (
        <div className="absolute top-2 right-2 z-10 flex items-center gap-2 bg-black/70 backdrop-blur-sm rounded-md px-2.5 py-1 border border-white/10">
          {/* 搜索框 */}
          <div className="flex items-center gap-1">
            <svg className="w-3 h-3 text-textSecondary/50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              ref={searchRef}
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onKeyDown={e => { if (e.key === 'Escape') setSearchQuery('') }}
              placeholder="搜索节点…"
              className="w-20 text-[10px] bg-white/5 border border-white/10 rounded px-1.5 py-0.5 text-textPrimary placeholder-textSecondary/40 focus:outline-none focus:border-indigo-400/50"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="text-textSecondary/50 hover:text-textPrimary text-xs leading-none px-0.5"
                title="清除搜索"
              >×</button>
            )}
          </div>
          <div className="w-px h-4 bg-white/10" />
          <span className="text-[10px] text-textSecondary/60 whitespace-nowrap">边权重 ≥</span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={edgeWeightThreshold}
            onChange={(e) => onEdgeWeightThresholdChange?.(parseFloat(e.target.value))}
            className="w-16 h-1 accent-indigo-400 cursor-pointer"
          />
          <span className="text-[10px] text-indigo-300 font-mono w-7 text-right tabular-nums">
            {edgeWeightThreshold.toFixed(2)}
          </span>
          <span className="text-[9px] text-textSecondary/40 whitespace-nowrap">
            ({visibleEdgeCount}/{filteredData.edges.length})
          </span>
          {/* 导出按钮 */}
          <button
            onClick={handleExport}
            title="导出当前图谱为 JSON 文件"
            className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-white/5 hover:bg-white/10 text-textSecondary/60 hover:text-textPrimary transition-colors border border-white/10 hover:border-white/20"
          >
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3M3 17l3.75-1.5a4 4 0 010 2.5 0l7.5 0a4 4 0 010 2.5 0L21 17" />
            </svg>
            导出
          </button>
        </div>
      )}

      {/* 当前显示标题 */}
      {titleText && (
        <div className="absolute top-2 left-16 z-10 bg-black/70 backdrop-blur-sm rounded-md px-2.5 py-1 border border-white/10 flex items-center gap-2">
          <span className="text-[11px] text-amber-300/90 font-medium">
            {titleText}
          </span>
          {/* 性能模式提示：节点数 > 500 时显示 */}
          {filteredData && filteredData.vertices.length > 500 && (
            <span className="text-[9px] bg-amber-500/20 text-amber-300 px-1.5 py-0.5 rounded font-medium">
              性能模式
            </span>
          )}
        </div>
      )}

      {/* 图例：关系颜色 */}
      {!showEmptyState && filteredData && (
        <div className="absolute bottom-2 left-2 z-10 bg-black/70 backdrop-blur-sm rounded-md px-2.5 py-1.5 border border-white/10">
          <div className="text-[9px] text-textSecondary/50 mb-1.5">关系类型</div>
          {[
            [0, '#6366f1', '一般关联'],
            [1, '#f59e0b', '因果'],
            [2, '#10b981', '组成/部分'],
            [3, '#ec4899', '对比/对立'],
            [4, '#8b5cf6', '层级'],
          ].map(([flag, color, label]) => (
            <div key={String(flag)} className="flex items-center gap-1.5 leading-none mb-0.5 last:mb-0">
              <span
                className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0"
                style={{ backgroundColor: color as string }}
              />
              <span className="text-[10px] text-textSecondary/70 whitespace-nowrap">{label as string}</span>
            </div>
          ))}
        </div>
      )}

      {/* SVG 图谱 */}
      {!showEmptyState && filteredData && (
        <svg
          ref={svgRef}
          width={containerSize.w}
          height={containerSize.h}
          className="block"
          style={{ cursor: 'grab' }}
          onMouseDown={() => {
            const svg = svgRef.current
            if (svg) svg.style.cursor = 'grabbing'
          }}
          onMouseUp={() => {
            const svg = svgRef.current
            if (svg) svg.style.cursor = 'grab'
          }}
        />
      )}

      {/* 空状态提示 */}
      {showEmptyState && (
        <div className="flex flex-col items-center justify-center h-full text-center px-6" style={{ minHeight: `${height}px` }}>
          <div className="text-4xl mb-3">🕸️</div>
          <div className="text-base text-textSecondary/70 font-medium mb-1">
            请选择语料或知识项以查看图谱
          </div>
          <div className="text-xs text-textSecondary/40 max-w-xs leading-relaxed">
            在左侧「语料列表」点击某个语料，或「知识浏览」点击某个概念，即可在此处显示对应的知识图谱子图
          </div>
        </div>
      )}

      {/* 过滤降级提示 */}
      {filterWarning && filteredData && (
        <div className="absolute top-12 left-2 right-2 z-10 bg-amber-600/20 backdrop-blur-sm rounded-md px-3 py-1.5 border border-amber-500/30 flex items-center gap-2">
          <span className="text-amber-300 text-[11px]">⚠️</span>
          <span className="text-[11px] text-amber-200/80">{filterWarning}</span>
        </div>
      )}

      {/* Tooltip */}
      {tooltip && (
        <div
          className="fixed z-50 bg-gray-900/95 backdrop-blur-sm text-xs text-textPrimary rounded-md px-2.5 py-1.5 border border-white/20 pointer-events-none whitespace-pre-line font-mono"
          style={{
            left: tooltip.x + 12,
            top: tooltip.y - 30,
            maxWidth: '220px',
          }}
        >
          {tooltip.content}
        </div>
      )}
    </div>
  )
}
