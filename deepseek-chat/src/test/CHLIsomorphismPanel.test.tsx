/**
 * CHLIsomorphismPanel 组件单元测试
 *
 * 测试 Curry-Howard-Lambek 同构面板：渲染、证明搜索、公理扩展、定理展示
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import React from 'react'
import { CHLIsomorphismPanel } from '../components/CHLIsomorphismPanel'

// Mock icons
vi.mock('../components/icons', () => ({
  IconCHL: () => null,
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

describe('CHLIsomorphismPanel', () => {
  it('渲染面板标题和副标题', () => {
    render(<CHLIsomorphismPanel />)
    expect(screen.getByText('CHL 同构')).toBeInTheDocument()
    expect(screen.getByText(/构造即证明/i)).toBeInTheDocument()
  })

  it('显示 CHL 三角同构图', () => {
    render(<CHLIsomorphismPanel />)
    expect(screen.getByText('Curry-Howard-Lambek 三角同构')).toBeInTheDocument()
    expect(screen.getByText('逻辑命题')).toBeInTheDocument()
    expect(screen.getByText('证明项')).toBeInTheDocument()
    expect(screen.getByText('范畴态射')).toBeInTheDocument()
  })

  it('显示 κ-Snap 证明搜索区域', () => {
    render(<CHLIsomorphismPanel />)
    expect(screen.getByText('κ-Snap 证明搜索')).toBeInTheDocument()
    expect(screen.getByText('搜索')).toBeInTheDocument()
  })

  it('点击搜索按钮触发 fetch 请求', async () => {
    mockFetch.mockImplementation(() =>
      mockResponse({
        proposition: 'test_prop',
        proof_term: '(lambda (x) x)',
        mdl_score: 1.5,
      })
    )
    render(<CHLIsomorphismPanel />)

    const input = screen.getByPlaceholderText('如: color_swap')
    fireEvent.change(input, { target: { value: 'test' } })
    fireEvent.click(screen.getByText('搜索'))

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v3/chl/proof-search',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        })
      )
    })
  })

  it('显示公理扩展列表', () => {
    render(<CHLIsomorphismPanel />)
    expect(screen.getByText('公理扩展 (Sleep-Step 发现)')).toBeInTheDocument()
    expect(screen.getByText('κ-compose')).toBeInTheDocument()
  })

  it('显示 CHL 定理', () => {
    render(<CHLIsomorphismPanel />)
    expect(screen.getByText('CHL 定理')).toBeInTheDocument()
    expect(screen.getByText(/求解即证明/i)).toBeInTheDocument()
    expect(screen.getByText(/程序即证明项/i)).toBeInTheDocument()
    expect(screen.getByText(/执行即态射/i)).toBeInTheDocument()
  })

  it('搜索成功后显示证明结果', async () => {
    mockFetch.mockImplementation(() =>
      mockResponse({
        proposition: 'color_swap',
        proof_term: '(swap (map grid color_map))',
        mdl_score: 3.8,
      })
    )
    render(<CHLIsomorphismPanel />)

    const input = screen.getByPlaceholderText('如: color_swap')
    fireEvent.change(input, { target: { value: 'color' } })
    fireEvent.click(screen.getByText('搜索'))

    expect(await screen.findByText('(swap (map grid color_map))')).toBeInTheDocument()
  })
})
