/**
 * FinancialWorldPanel 组件单元测试
 *
 * 测试金融市场面板：渲染、创建 LOB 会话、ENPV 计算交互
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import React from 'react'
import { FinancialWorldPanel } from '../components/FinancialWorldPanel'

// Mock icons
vi.mock('../components/icons', () => ({
  IconFinancial: () => null,
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

describe('FinancialWorldPanel', () => {
  it('渲染面板标题和副标题', () => {
    render(<FinancialWorldPanel />)

    expect(screen.getByText('金融市场')).toBeInTheDocument()
    expect(screen.getByText(/LOB 限价订单簿/i)).toBeInTheDocument()
  })

  it('初始状态显示创建会话按钮和空状态提示', () => {
    render(<FinancialWorldPanel />)

    expect(screen.getByText('创建 LOB 会话')).toBeInTheDocument()
    expect(screen.getByText('创建 LOB 会话开始模拟')).toBeInTheDocument()
  })

  it('点击创建会话按钮触发 fetch', async () => {
    mockFetch.mockResolvedValue(
      mockResponse({ success: true, session_id: 'test1234' })
    )

    render(<FinancialWorldPanel />)

    fireEvent.click(screen.getByText('创建 LOB 会话'))

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v3/financial/lob/create',
        expect.objectContaining({ method: 'POST' })
      )
    })
  })

  it('创建会话成功后显示会话 ID 和刷新状态按钮', async () => {
    // 第一个 fetch：创建会话
    // 第二个 fetch：自动获取 LOB 状态 (useEffect triggered by sessionId change)
    mockFetch
      .mockResolvedValueOnce(
        mockResponse({ success: true, session_id: 'test1234' })
      )
      .mockResolvedValueOnce(
        mockResponse({
          session_id: 'test1234',
          best_bid: 100.5,
          best_ask: 100.8,
          mid_price: 100.65,
          spread: 0.3,
          spread_bps: 29.85,
          depth_entropy: 1.2,
          bid_orders: 3,
          ask_orders: 2,
        })
      )

    render(<FinancialWorldPanel />)

    fireEvent.click(screen.getByText('创建 LOB 会话'))

    await waitFor(() => {
      expect(screen.getByText(/会话: test1234/)).toBeInTheDocument()
    })
  })

  it('创建会话后显示订单簿状态', async () => {
    mockFetch
      .mockResolvedValueOnce(
        mockResponse({ success: true, session_id: 'test1234' })
      )
      .mockResolvedValueOnce(
        mockResponse({
          session_id: 'test1234',
          best_bid: 100.5,
          best_ask: 100.8,
          mid_price: 100.65,
          spread: 0.3,
          spread_bps: 29.85,
          depth_entropy: 1.2,
          bid_orders: 3,
          ask_orders: 2,
        })
      )

    render(<FinancialWorldPanel />)

    fireEvent.click(screen.getByText('创建 LOB 会话'))

    await waitFor(() => {
      expect(screen.getByText('订单簿状态')).toBeInTheDocument()
    })
  })

  it('LOB 状态显示后可计算 ENPV', async () => {
    // fetch 1: create session
    // fetch 2: auto fetch status (useEffect)
    // fetch 3: calc ENPV (user click)
    mockFetch
      .mockResolvedValueOnce(
        mockResponse({ success: true, session_id: 'test1234' })
      )
      .mockResolvedValueOnce(
        mockResponse({
          session_id: 'test1234',
          best_bid: 100.5,
          best_ask: 100.8,
          mid_price: 100.65,
          spread: 0.3,
          spread_bps: 29.85,
          depth_entropy: 1.2,
          bid_orders: 3,
          ask_orders: 2,
        })
      )
      .mockResolvedValueOnce(
        mockResponse({ enpv: 0.65, should_chase: true, should_trade: true, explanation: 'test' })
      )

    render(<FinancialWorldPanel />)

    // 创建会话
    fireEvent.click(screen.getByText('创建 LOB 会话'))

    await waitFor(() => {
      expect(screen.getByText('ENPV 决策')).toBeInTheDocument()
    })

    // 计算 ENPV
    fireEvent.click(screen.getByText('计算 ENPV (示例参数)'))

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v3/financial/enpv',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        })
      )
    })
  })

  it('ENPV 计算后显示结果', async () => {
    mockFetch
      .mockResolvedValueOnce(
        mockResponse({ success: true, session_id: 'test1234' })
      )
      .mockResolvedValueOnce(
        mockResponse({
          session_id: 'test1234',
          best_bid: 100.5,
          best_ask: 100.8,
          mid_price: 100.65,
          spread: 0.3,
          spread_bps: 29.85,
          depth_entropy: 1.2,
          bid_orders: 3,
          ask_orders: 2,
        })
      )
      .mockResolvedValueOnce(
        mockResponse({ enpv: 0.65, should_chase: true, should_trade: true, explanation: 'test ENPV explanation' })
      )

    render(<FinancialWorldPanel />)

    fireEvent.click(screen.getByText('创建 LOB 会话'))

    await waitFor(() => {
      expect(screen.getByText('ENPV 决策')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('计算 ENPV (示例参数)'))

    await waitFor(() => {
      expect(screen.getByText('test ENPV explanation')).toBeInTheDocument()
    })
  })

  it('显示熔断检测按钮（创建会话后）', async () => {
    mockFetch
      .mockResolvedValueOnce(
        mockResponse({ success: true, session_id: 'test1234' })
      )
      .mockResolvedValueOnce(
        mockResponse({
          session_id: 'test1234',
          best_bid: 100.5,
          best_ask: 100.8,
          mid_price: 100.65,
          spread: 0.3,
          spread_bps: 29.85,
          depth_entropy: 1.2,
          bid_orders: 3,
          ask_orders: 2,
        })
      )

    render(<FinancialWorldPanel />)

    fireEvent.click(screen.getByText('创建 LOB 会话'))

    await waitFor(() => {
      expect(screen.getByText('熔断检测')).toBeInTheDocument()
      expect(screen.getByText('检测熔断状态')).toBeInTheDocument()
    })
  })
})
