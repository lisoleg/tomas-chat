/**
 * LuZhaoPanel 组件单元测试
 *
 * 测试鲁兆 DNA 面板：渲染、不变量加载、DNA 复制检测交互
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import React from 'react'
import { LuZhaoPanel } from '../components/LuZhaoPanel'

// Mock icons
vi.mock('../components/icons', () => ({
  IconDna: () => null,
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
})

describe('LuZhaoPanel', () => {
  it('渲染面板标题和副标题', async () => {
    mockFetch.mockResolvedValue(
      mockResponse({ invariants: [1, 1, 2, 3, 5, 8, 13, 21] })
    )
    render(<LuZhaoPanel />)

    expect(screen.getByText('鲁兆 DNA')).toBeInTheDocument()
    expect(screen.getByText(/Lu Zhao DNA/i)).toBeInTheDocument()
  })

  it('挂载时自动请求不变量数据', async () => {
    mockFetch.mockResolvedValue(
      mockResponse({ invariants: [1, 1, 2, 3, 5, 8, 13, 21] })
    )
    render(<LuZhaoPanel />)

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith('/api/v3/luzhao/invariants')
    })
  })

  it('显示不变量参考区域', async () => {
    mockFetch.mockResolvedValue(
      mockResponse({ invariants: [1, 1, 2, 3, 5, 8, 13, 21] })
    )
    render(<LuZhaoPanel />)

    await waitFor(() => {
      expect(screen.getByText('不变量参考')).toBeInTheDocument()
    })
  })

  it('显示 DNA 复制检测区域和输入框', () => {
    mockFetch.mockResolvedValue(
      mockResponse({ invariants: [1, 1, 2, 3, 5, 8, 13, 21] })
    )
    render(<LuZhaoPanel />)

    expect(screen.getByText('DNA 复制检测')).toBeInTheDocument()
    expect(screen.getByText('第一浪持续时间')).toBeInTheDocument()
    expect(screen.getByText('第一浪幅度')).toBeInTheDocument()
  })

  it('显示开始检测按钮', () => {
    mockFetch.mockResolvedValue(
      mockResponse({ invariants: [1, 1, 2, 3, 5, 8, 13, 21] })
    )
    render(<LuZhaoPanel />)

    expect(screen.getByText('开始检测')).toBeInTheDocument()
  })

  it('点击开始检测按钮触发 fetch DNA check', async () => {
    // 第一次 fetch：挂载时的 invariants 请求
    // 第二次 fetch：点击检测按钮时的 dna/check 请求
    mockFetch
      .mockResolvedValueOnce(
        mockResponse({ invariants: [1, 1, 2, 3, 5, 8, 13, 21] })
      )
      .mockResolvedValueOnce(
        mockResponse({
          replication: { 0: { matched: true, ratio: 2.5, generation_type: 'exact_multiple' } },
          timeWindow: [24, 36, [24, 30, 36]],
          baguaTriggers: [],
        })
      )

    render(<LuZhaoPanel />)

    const button = screen.getByText('开始检测')
    fireEvent.click(button)

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v3/luzhao/dna/check',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        })
      )
    })
  })

  it('显示八卦触发点检测区域', () => {
    mockFetch.mockResolvedValue(
      mockResponse({ invariants: [1, 1, 2, 3, 5, 8, 13, 21] })
    )
    render(<LuZhaoPanel />)

    expect(screen.getByText('八卦触发点检测')).toBeInTheDocument()
    expect(screen.getByText('检测触发点')).toBeInTheDocument()
  })

  it('输入框可交互（持续时间）', () => {
    mockFetch.mockResolvedValue(
      mockResponse({ invariants: [1, 1, 2, 3, 5, 8, 13, 21] })
    )
    render(<LuZhaoPanel />)

    const durationInput = screen.getByDisplayValue('12')
    fireEvent.change(durationInput, { target: { value: '24' } })
    expect((durationInput as HTMLInputElement).value).toBe('24')
  })

  it('DNA 检测成功后显示结果', async () => {
    mockFetch
      .mockResolvedValueOnce(
        mockResponse({ invariants: [1, 1, 2, 3, 5, 8, 13, 21] })
      )
      .mockResolvedValueOnce(
        mockResponse({
          replication: { 0: { matched: true, ratio: 2.5, generation_type: 'exact_multiple' } },
          timeWindow: [24, 36, [24, 30, 36]],
          baguaTriggers: [],
        })
      )

    render(<LuZhaoPanel />)

    fireEvent.click(screen.getByText('开始检测'))

    await waitFor(() => {
      expect(screen.getByText('检测结果')).toBeInTheDocument()
    })
  })
})
