/**
 * TokenizedEconomyPanel 组件单元测试
 *
 * 测试代币经济面板：渲染、创建经济体、快照显示交互
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import React from 'react'
import { TokenizedEconomyPanel } from '../components/TokenizedEconomyPanel'

// Mock icons
vi.mock('../components/icons', () => ({
  IconToken: () => null,
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

describe('TokenizedEconomyPanel', () => {
  it('渲染面板标题和副标题', () => {
    render(<TokenizedEconomyPanel />)

    expect(screen.getByText('代币经济')).toBeInTheDocument()
    expect(screen.getByText(/智能体市场经济/i)).toBeInTheDocument()
  })

  it('初始状态显示创建经济体按钮和空状态提示', () => {
    render(<TokenizedEconomyPanel />)

    expect(screen.getByText('创建经济体')).toBeInTheDocument()
    expect(screen.getByText('创建经济体开始模拟')).toBeInTheDocument()
  })

  it('点击创建经济体按钮触发 fetch', async () => {
    mockFetch.mockResolvedValue(
      mockResponse({ success: true, economy_id: 'econ1' })
    )

    render(<TokenizedEconomyPanel />)

    fireEvent.click(screen.getByText('创建经济体'))

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v3/tokenized/economy/create',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        })
      )
    })
  })

  it('创建经济体成功后显示经济体 ID', async () => {
    // fetch 1: create economy
    // fetch 2: auto fetch snapshot (useEffect triggered by economyId change)
    mockFetch
      .mockResolvedValueOnce(
        mockResponse({ success: true, economy_id: 'econ1' })
      )
      .mockResolvedValueOnce(
        mockResponse({
          total_agents: 0,
          total_trades: 0,
          executed_trades: 0,
          gini_coefficient: 0.0,
          economic_phase: 'EQUILIBRIUM',
          avg_balance: 0.0,
        })
      )

    render(<TokenizedEconomyPanel />)

    fireEvent.click(screen.getByText('创建经济体'))

    await waitFor(() => {
      expect(screen.getByText('经济体: econ1')).toBeInTheDocument()
    })
  })

  it('创建经济体后显示经济快照', async () => {
    mockFetch
      .mockResolvedValueOnce(
        mockResponse({ success: true, economy_id: 'econ1' })
      )
      .mockResolvedValueOnce(
        mockResponse({
          total_agents: 5,
          total_trades: 10,
          executed_trades: 8,
          gini_coefficient: 0.35,
          economic_phase: 'EXPANSION',
          avg_balance: 200000.0,
        })
      )

    render(<TokenizedEconomyPanel />)

    fireEvent.click(screen.getByText('创建经济体'))

    await waitFor(() => {
      expect(screen.getByText('经济快照')).toBeInTheDocument()
      expect(screen.getByText('智能体数')).toBeInTheDocument()
      expect(screen.getByText('已执行交易')).toBeInTheDocument()
      expect(screen.getByText('Gini 系数')).toBeInTheDocument()
    })
  })

  it('快照显示正确的智能体数量', async () => {
    mockFetch
      .mockResolvedValueOnce(
        mockResponse({ success: true, economy_id: 'econ1' })
      )
      .mockResolvedValueOnce(
        mockResponse({
          total_agents: 5,
          total_trades: 10,
          executed_trades: 8,
          gini_coefficient: 0.35,
          economic_phase: 'EXPANSION',
          avg_balance: 200000.0,
        })
      )

    render(<TokenizedEconomyPanel />)

    fireEvent.click(screen.getByText('创建经济体'))

    await waitFor(() => {
      expect(screen.getByText('5')).toBeInTheDocument()
    })
  })

  it('快照显示已执行交易数', async () => {
    mockFetch
      .mockResolvedValueOnce(
        mockResponse({ success: true, economy_id: 'econ1' })
      )
      .mockResolvedValueOnce(
        mockResponse({
          total_agents: 5,
          total_trades: 10,
          executed_trades: 8,
          gini_coefficient: 0.35,
          economic_phase: 'EXPANSION',
          avg_balance: 200000.0,
        })
      )

    render(<TokenizedEconomyPanel />)

    fireEvent.click(screen.getByText('创建经济体'))

    await waitFor(() => {
      expect(screen.getByText('8')).toBeInTheDocument()
    })
  })

  it('创建经济体后显示智能体管理区域', async () => {
    mockFetch
      .mockResolvedValueOnce(
        mockResponse({ success: true, economy_id: 'econ1' })
      )
      .mockResolvedValueOnce(
        mockResponse({
          total_agents: 0,
          total_trades: 0,
          executed_trades: 0,
          gini_coefficient: 0.0,
          economic_phase: 'EQUILIBRIUM',
          avg_balance: 0.0,
        })
      )

    render(<TokenizedEconomyPanel />)

    fireEvent.click(screen.getByText('创建经济体'))

    await waitFor(() => {
      expect(screen.getByText('智能体管理')).toBeInTheDocument()
      expect(screen.getByPlaceholderText('智能体 ID')).toBeInTheDocument()
    })
  })

  it('创建经济体后显示刷新快照按钮', async () => {
    mockFetch
      .mockResolvedValueOnce(
        mockResponse({ success: true, economy_id: 'econ1' })
      )
      .mockResolvedValueOnce(
        mockResponse({
          total_agents: 0,
          total_trades: 0,
          executed_trades: 0,
          gini_coefficient: 0.0,
          economic_phase: 'EQUILIBRIUM',
          avg_balance: 0.0,
        })
      )

    render(<TokenizedEconomyPanel />)

    fireEvent.click(screen.getByText('创建经济体'))

    await waitFor(() => {
      expect(screen.getByText('刷新快照')).toBeInTheDocument()
    })
  })
})
