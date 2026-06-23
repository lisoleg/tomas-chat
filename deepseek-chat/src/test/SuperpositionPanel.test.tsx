/**
 * SuperpositionPanel 组件单元测试
 *
 * 测试叠加态几何面板：渲染、Thomson 求解器交互、E8 堆积密度、相变检测
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import React from 'react'
import { SuperpositionPanel } from '../components/SuperpositionPanel'

// Mock icons
vi.mock('../components/icons', () => ({
  IconSuperposition: () => null,
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

describe('SuperpositionPanel', () => {
  it('渲染面板标题和副标题', () => {
    render(<SuperpositionPanel />)
    expect(screen.getByText('叠加态几何')).toBeInTheDocument()
    // "Thomson 问题" appears in both subtitle and section title
    expect(screen.getAllByText(/Thomson 问题/i).length).toBeGreaterThan(0)
  })

  it('显示 Thomson 问题求解器区域', () => {
    render(<SuperpositionPanel />)
    expect(screen.getByText('Thomson 问题求解器')).toBeInTheDocument()
  })

  it('显示求解按钮', () => {
    render(<SuperpositionPanel />)
    expect(screen.getByText('求解')).toBeInTheDocument()
  })

  it('点击求解按钮触发 fetch 请求', async () => {
    mockFetch.mockImplementation(() =>
      mockResponse({ type: '八面体 (Octahedron)', energy: 0.167 })
    )
    render(<SuperpositionPanel />)

    fireEvent.click(screen.getByText('求解'))

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v3/superposition/thomson',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        })
      )
    })
  })

  it('求解成功后显示结果', async () => {
    mockFetch.mockImplementation(() =>
      mockResponse({ type: '四面体 (Tetrahedron)', energy: 0.25 })
    )
    render(<SuperpositionPanel />)

    fireEvent.click(screen.getByText('求解'))

    expect(await screen.findByText('四面体 (Tetrahedron)')).toBeInTheDocument()
    expect(screen.getByText('0.2500')).toBeInTheDocument()
  })

  it('API 失败时使用 fallback 数据', async () => {
    mockFetch.mockImplementation(() => Promise.reject(new Error('Network error')))
    render(<SuperpositionPanel />)

    fireEvent.click(screen.getByText('求解'))

    // n=6 default → Octahedron
    expect(await screen.findByText('八面体 (Octahedron)')).toBeInTheDocument()
  })

  it('显示 E8 格堆积密度', () => {
    render(<SuperpositionPanel />)
    // "E8 格堆积密度" appears in section title and predictions list
    expect(screen.getAllByText('E8 格堆积密度').length).toBeGreaterThan(0)
    expect(screen.getByText('0.25367')).toBeInTheDocument()
  })

  it('显示相变检测和可证伪预言', () => {
    render(<SuperpositionPanel />)
    expect(screen.getByText('相变检测')).toBeInTheDocument()
    expect(screen.getByText('可证伪预言')).toBeInTheDocument()
  })
})
