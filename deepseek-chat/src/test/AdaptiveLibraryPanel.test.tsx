/**
 * AdaptiveLibraryPanel 组件单元测试
 *
 * 测试自适应库学习面板：渲染、参数控制、预算计算、Rice定理上界
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import React from 'react'
import { AdaptiveLibraryPanel } from '../components/AdaptiveLibraryPanel'

// Mock icons
vi.mock('../components/icons', () => ({
  IconAdaptiveLib: () => null,
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

describe('AdaptiveLibraryPanel', () => {
  it('渲染面板标题和副标题', () => {
    render(<AdaptiveLibraryPanel />)
    expect(screen.getByText('自适应库学习')).toBeInTheDocument()
    expect(screen.getByText(/α\/β在线学习/i)).toBeInTheDocument()
  })

  it('显示参数控制区域', () => {
    render(<AdaptiveLibraryPanel />)
    expect(screen.getByText('参数控制')).toBeInTheDocument()
    expect(screen.getByText('α (MDL权重)')).toBeInTheDocument()
    expect(screen.getByText('β (频率权重)')).toBeInTheDocument()
  })

  it('显示计算预算 B', () => {
    render(<AdaptiveLibraryPanel />)
    expect(screen.getByText('计算预算 B')).toBeInTheDocument()
    // B = 1.0 + 1.0*3.5 + 1.0*log2(11) ≈ 1.0 + 3.5 + 3.459 = 7.959
    expect(screen.getByText('7.9594')).toBeInTheDocument()
  })

  it('显示 Sleep-Step 结果区域', async () => {
    render(<AdaptiveLibraryPanel />)
    expect(screen.getByText('Sleep-Step 结果')).toBeInTheDocument()
  })

  it('挂载时请求库状态', async () => {
    mockFetch.mockImplementation(() => mockResponse({
      closure_size: 8,
      primitives: [{ name: 'test_op', gain: 0.9, mdl: 2.0 }],
    }))
    render(<AdaptiveLibraryPanel />)

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith('/api/v3/adaptive-library/status')
    })
  })

  it('显示 Rice 定理上界对比', () => {
    render(<AdaptiveLibraryPanel />)
    expect(screen.getByText('Rice 定理上界')).toBeInTheDocument()
    expect(screen.getByText('LLM 天花板')).toBeInTheDocument()
    expect(screen.getByText('TOMAS 理论上限')).toBeInTheDocument()
  })

  it('显示阴龙积说明', () => {
    render(<AdaptiveLibraryPanel />)
    expect(screen.getByText('阴龙积')).toBeInTheDocument()
    expect(screen.getByText('八元数乘法')).toBeInTheDocument()
  })
})
