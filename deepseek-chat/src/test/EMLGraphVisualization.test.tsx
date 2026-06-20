/**
 * EMLGraphVisualization 组件单元测试
 * 
 * 测试 D3.js 力导向知识图谱可视化组件的核心行为
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import React from 'react'
import { EMLGraphVisualization, type EMLGraphData } from '../components/EMLGraphVisualization'

// Mock D3 — 避免 JSDOM 中 D3 SVG 操作的复杂性
// 注意: import * as d3 from 'd3' 使用命名导出 (顶层), 不是 default
vi.mock('d3', () => {
  const mockSelection = {
    attr: vi.fn().mockReturnThis(),
    style: vi.fn().mockReturnThis(),
    text: vi.fn().mockReturnThis(),
    append: vi.fn().mockReturnThis(),
    selectAll: vi.fn().mockReturnThis(),
    data: vi.fn().mockReturnThis(),
    join: vi.fn().mockReturnThis(),
    enter: vi.fn().mockReturnThis(),
    merge: vi.fn().mockReturnThis(),
    call: vi.fn().mockReturnThis(),
    on: vi.fn().mockReturnThis(),
    remove: vi.fn().mockReturnThis(),
    node: vi.fn(() => null),
  }

  const mockForceSimulation = vi.fn(() => ({
    force: vi.fn().mockReturnThis(),
    alphaTarget: vi.fn().mockReturnThis(),
    restart: vi.fn().mockReturnThis(),
    stop: vi.fn().mockReturnThis(),
    on: vi.fn().mockReturnThis(),
    nodes: vi.fn().mockReturnThis(),
    tick: vi.fn(),
  }))

  const mockZoom = vi.fn(() => ({
    scaleExtent: vi.fn().mockReturnThis(),
    on: vi.fn().mockReturnThis(),
    transform: vi.fn(),
  }))

  const mockDrag = vi.fn(() => ({
    on: vi.fn().mockReturnThis(),
  }))

  const selectFn = vi.fn(() => mockSelection)

  return {
    __esModule: true,
    select: selectFn,
    forceSimulation: mockForceSimulation,
    forceLink: vi.fn(() => ({ id: vi.fn(), distance: vi.fn().mockReturnThis() })),
    forceManyBody: vi.fn(() => ({ strength: vi.fn().mockReturnThis() })),
    forceCollide: vi.fn(() => ({ radius: vi.fn().mockReturnThis() })),
    forceCenter: vi.fn(() => ({})),
    zoom: mockZoom,
    drag: mockDrag,
    zoomIdentity: { k: 1, x: 0, y: 0, scale: vi.fn(() => ({ k: 1, x: 0, y: 0 })), translate: vi.fn().mockReturnThis() },
  }
})

// Mock ResizeObserver (not in JSDOM)
// Must use class (not arrow) — Vitest requires constructor mock to be callable with new
class MockResizeObserver {
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
}
(globalThis as any).ResizeObserver = MockResizeObserver as unknown as typeof ResizeObserver

// 构造测试数据
function makeGraphData(vertexCount: number, edgeCount: number): EMLGraphData {
  const vertices = Array.from({ length: vertexCount }, (_, i) => ({
    id: i,
    label: `概念_${i}`,
    delta: 0.5 + Math.random() * 0.5,
    info_existence: 0.5 + Math.random() * 0.5,
    corpusName: i < vertexCount / 2 ? '物理' : '化学',
  }))

  const edges = Array.from({ length: edgeCount }, (_, i) => ({
    src: i % vertexCount,
    dst: (i + 1) % vertexCount,
    weight: 0.3 + Math.random() * 0.7,
    associator_flag: i % 4,
  }))

  return { vertices, edges }
}


describe('EMLGraphVisualization', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('graphData=null 时不崩溃且渲染空容器', () => {
    const { container } = render(
      <EMLGraphVisualization
        graphData={null}
        height={400}
      />
    )

    // 组件应渲染容器 div（不崩溃）
    expect(container.querySelector('.relative')).toBeTruthy()
  })

  it('渲染空数据状态（vertices=[]）且 showAllByDefault', () => {
    const { container } = render(
      <EMLGraphVisualization
        graphData={{ vertices: [], edges: [] }}
        height={400}
        showAllByDefault={true}
      />
    )

    // 空数据图应优雅渲染（无 D3 崩溃）
    expect(container.querySelector('.relative')).toBeTruthy()
  })

  it('渲染性能模式标签（节点数 > 500）', () => {
    const bigData = makeGraphData(600, 1000)

    render(
      <EMLGraphVisualization
        graphData={bigData}
        height={400}
        showAllByDefault={true}
      />
    )

    expect(screen.getByText(/性能模式/i)).toBeInTheDocument()
  })

  it('超过1000节点时显示性能模式', () => {
    const hugeData = makeGraphData(1500, 3000)

    render(
      <EMLGraphVisualization
        graphData={hugeData}
        height={400}
        showAllByDefault={true}
      />
    )

    expect(screen.getByText(/性能模式/i)).toBeInTheDocument()
  })

  it('小图 showAllByDefault 显示全部概念标题', () => {
    const data = makeGraphData(10, 15)

    render(
      <EMLGraphVisualization
        graphData={data}
        height={400}
        showAllByDefault={true}
      />
    )

    // 小图（10 节点 < 500）不显示性能模式，但显示全部概念标题
    expect(screen.getByText(/全部概念/i)).toBeInTheDocument()
  })

  it('搜索框占位符为搜索节点', () => {
    const data = makeGraphData(50, 100)

    render(
      <EMLGraphVisualization
        graphData={data}
        height={400}
        showAllByDefault={true}
      />
    )

    const input = screen.getByPlaceholderText(/搜索节点/i)
    expect(input).toBeInTheDocument()

    fireEvent.change(input, { target: { value: '物理' } })
    expect(input).toHaveValue('物理')
  })

  it('边权重阈值滑块存在', () => {
    const data = makeGraphData(50, 100)
    const onThresholdChange = vi.fn()

    render(
      <EMLGraphVisualization
        graphData={data}
        height={400}
        showAllByDefault={true}
        edgeWeightThreshold={0.3}
        onEdgeWeightThresholdChange={onThresholdChange}
      />
    )

    const slider = screen.getByRole('slider')
    expect(slider).toBeInTheDocument()
  })
})
