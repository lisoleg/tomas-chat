/**
 * TaiyiDuelPanel 组件单元测试
 *
 * 测试太一互搏 Agent 面板：渲染、博弈历史、L3/L2/L4 状态、RHAE 评分
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import React from 'react'
import { TaiyiDuelPanel } from '../components/TaiyiDuelPanel'

// Mock icons
vi.mock('../components/icons', () => ({
  IconTaiyi: () => null,
}))

// Mock fetch
const mockFetch = vi.fn()
globalThis.fetch = mockFetch as any

function mockResponse(data: any, ok = true) {
  return Promise.resolve({
    ok,
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(JSON.stringify(data)),
  } as any)
}

beforeEach(() => {
  mockFetch.mockReset()
  mockFetch.mockImplementation(() => mockResponse({}))
})

describe('TaiyiDuelPanel', () => {
  it('渲染面板标题和副标题', () => {
    render(<TaiyiDuelPanel />)
    expect(screen.getByText('太一互搏 Agent')).toBeInTheDocument()
    // "Physical AI" appears in both subtitle and section title
    expect(screen.getAllByText(/Physical AI/i).length).toBeGreaterThan(0)
  })

  it('显示博弈语义引擎区域', () => {
    render(<TaiyiDuelPanel />)
    expect(screen.getByText('博弈语义引擎')).toBeInTheDocument()
  })

  it('显示证实者和证伪者策略列表', () => {
    render(<TaiyiDuelPanel />)
    expect(screen.getByText('证实者策略')).toBeInTheDocument()
    expect(screen.getByText('证伪者反驳')).toBeInTheDocument()
  })

  it('显示 L3 差分感知', () => {
    render(<TaiyiDuelPanel />)
    expect(screen.getByText('L3 差分感知')).toBeInTheDocument()
    expect(screen.getByText('Row')).toBeInTheDocument()
    expect(screen.getByText('Col')).toBeInTheDocument()
    expect(screen.getByText('置信度')).toBeInTheDocument()
  })

  it('显示 L2 DFS 回溯', () => {
    render(<TaiyiDuelPanel />)
    expect(screen.getByText('L2 DFS 回溯')).toBeInTheDocument()
    expect(screen.getByText('搜索深度')).toBeInTheDocument()
    expect(screen.getByText('回溯次数')).toBeInTheDocument()
    expect(screen.getByText('路径长度')).toBeInTheDocument()
  })

  it('显示 L4 贝叶斯熔断状态', () => {
    render(<TaiyiDuelPanel />)
    expect(screen.getByText('L4 贝叶斯熔断')).toBeInTheDocument()
    expect(screen.getByText('EXECUTE')).toBeInTheDocument()
  })

  it('显示 RHAE 评分', () => {
    render(<TaiyiDuelPanel />)
    expect(screen.getByText('RHAE 评分')).toBeInTheDocument()
    expect(screen.getByText('72')).toBeInTheDocument()
  })

  it('显示 Physical AI 定理', () => {
    render(<TaiyiDuelPanel />)
    expect(screen.getByText('Physical AI 定理')).toBeInTheDocument()
    expect(screen.getByText('内思即外作')).toBeInTheDocument()
  })

  it('挂载时请求互搏状态', async () => {
    mockFetch.mockImplementation(() => mockResponse({
      history: [{ strategy: 'test', counter: 'open', result: 'success' }],
      l3: { detectedRow: 1, detectedCol: 2, confidence: 0.9 },
    }))
    render(<TaiyiDuelPanel />)

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith('/api/v3/taiyi-duel/status')
    })
  })
})
