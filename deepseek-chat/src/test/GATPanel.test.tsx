/**
 * GATPanel 组件单元测试
 *
 * 测试 GAT 公理面板：渲染、理论列表加载、态射计算交互
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import React from 'react'
import { GATPanel } from '../components/GATPanel'

// Mock icons
vi.mock('../components/icons', () => ({
  IconGat: () => null,
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
  // Set a default implementation so fetch never returns undefined
  mockFetch.mockImplementation(() => mockResponse([]))
})

describe('GATPanel', () => {
  it('渲染面板标题和副标题', async () => {
    mockFetch.mockImplementation(() => mockResponse([{ name: 'ARC_DSL_GAT', sorts: 5, operations: 10, axioms: 3 }]))
    render(<GATPanel />)

    expect(screen.getByText('GAT 公理')).toBeInTheDocument()
    expect(screen.getByText(/广义代数理论/i)).toBeInTheDocument()
  })

  it('挂载时自动请求理论列表', async () => {
    mockFetch.mockImplementation(() => mockResponse([{ name: 'ARC_DSL_GAT', sorts: 5, operations: 10, axioms: 3 }]))
    render(<GATPanel />)

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith('/api/v3/gat/theories')
    })
  })

  it('显示理论列表', async () => {
    mockFetch.mockImplementation(() => mockResponse([{ name: 'ARC_DSL_GAT', sorts: 5, operations: 10, axioms: 3 }]))
    render(<GATPanel />)

    // Use findByText which waits for the element to appear
    expect(await screen.findByText('ARC_DSL_GAT')).toBeInTheDocument()
  })

  it('显示预定义理论和理论态射区域', async () => {
    mockFetch.mockImplementation(() => mockResponse([{ name: 'ARC_DSL_GAT', sorts: 5, operations: 10, axioms: 3 }]))
    render(<GATPanel />)

    expect(screen.getByText('预定义理论')).toBeInTheDocument()
    expect(screen.getByText('理论态射 (Theory Map)')).toBeInTheDocument()
  })

  it('显示构造自由模型按钮（初始禁用）', async () => {
    mockFetch.mockImplementation(() => mockResponse([{ name: 'ARC_DSL_GAT', sorts: 5, operations: 10, axioms: 3 }]))
    render(<GATPanel />)

    const button = screen.getByText('构造自由模型')
    expect(button).toBeInTheDocument()
    expect(button).toBeDisabled()
  })

  it('显示计算态射按钮', async () => {
    mockFetch.mockImplementation(() => mockResponse([{ name: 'ARC_DSL_GAT', sorts: 5, operations: 10, axioms: 3 }]))
    render(<GATPanel />)

    expect(screen.getByText('计算态射')).toBeInTheDocument()
  })

  it('选择理论后可点击构造自由模型按钮', async () => {
    mockFetch.mockImplementation(() => mockResponse([
      { name: 'ARC_DSL_GAT', sorts: 5, operations: 10, axioms: 3 },
      { name: 'Octonion_GAT', sorts: 3, operations: 11, axioms: 15 },
    ]))
    const { container } = render(<GATPanel />)

    // Wait for theories to load
    await screen.findByText('ARC_DSL_GAT')

    // Click the clickable theory container (parent div with cursor-pointer)
    const clickableItems = container.querySelectorAll('[class*="cursor-pointer"]')
    expect(clickableItems.length).toBeGreaterThan(0)
    fireEvent.click(clickableItems[0])

    // Wait for state update to propagate (React 18 batching)
    await waitFor(() => {
      const button = screen.getByText('构造自由模型')
      expect(button).not.toBeDisabled()
    })
  })

  it('点击计算态射按钮触发 fetch', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/v3/gat/theories') {
        return mockResponse([{ name: 'ARC_DSL_GAT', sorts: 5, operations: 10, axioms: 3 }])
      }
      if (url === '/api/v3/gat/theory/map') {
        return mockResponse({
          is_valid: true,
          mapping: { grid: 'octonion' },
          preserves_axioms: true,
        })
      }
      return mockResponse({})
    })

    render(<GATPanel />)

    await screen.findByText('计算态射')
    fireEvent.click(screen.getByText('计算态射'))

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v3/gat/theory/map',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        })
      )
    })
  })

  it('态射计算成功后显示结果', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/v3/gat/theories') {
        return mockResponse([{ name: 'ARC_DSL_GAT', sorts: 5, operations: 10, axioms: 3 }])
      }
      if (url === '/api/v3/gat/theory/map') {
        return mockResponse({
          is_valid: true,
          mapping: { grid: 'octonion' },
          preserves_axioms: true,
        })
      }
      return mockResponse({})
    })

    render(<GATPanel />)

    await screen.findByText('计算态射')
    fireEvent.click(screen.getByText('计算态射'))

    // Use regex to match partial text (text is split across elements)
    expect(await screen.findByText(/态射有效/)).toBeInTheDocument()
  })
})
