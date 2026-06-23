/**
 * MathUnificationPanel 组件单元测试
 *
 * 测试数学大统一面板：渲染、热带半环计算器、太一几何定位表
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import React from 'react'
import { MathUnificationPanel } from '../components/MathUnificationPanel'

// Mock icons
vi.mock('../components/icons', () => ({
  IconMathUnify: () => null,
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

describe('MathUnificationPanel', () => {
  it('渲染面板标题和副标题', () => {
    render(<MathUnificationPanel />)
    expect(screen.getByText('数学大统一')).toBeInTheDocument()
    // "热带几何" appears in subtitle and geometry table
    expect(screen.getAllByText(/热带几何/i).length).toBeGreaterThan(0)
  })

  it('显示热带半环计算器', () => {
    render(<MathUnificationPanel />)
    expect(screen.getByText('热带半环计算器')).toBeInTheDocument()
  })

  it('计算热带加法 max(a, b)', () => {
    render(<MathUnificationPanel />)
    // a=3, b=5 → max = 5 (result span contains exactly "5")
    expect(screen.getByText('5', { exact: true })).toBeInTheDocument()
  })

  it('显示太一几何全景定位表', () => {
    render(<MathUnificationPanel />)
    expect(screen.getByText('太一几何全景定位表')).toBeInTheDocument()
    expect(screen.getByText('八元数/Clifford代数')).toBeInTheDocument()
    expect(screen.getByText('热带几何')).toBeInTheDocument()
  })

  it('显示 UV/IR 对偶自对偶不动点', () => {
    render(<MathUnificationPanel />)
    expect(screen.getByText('UV/IR 对偶')).toBeInTheDocument()
    expect(screen.getByText('s = 0.5')).toBeInTheDocument()
  })

  it('显示柏拉图收敛信息', () => {
    render(<MathUnificationPanel />)
    expect(screen.getByText('柏拉图收敛')).toBeInTheDocument()
    expect(screen.getByText(/Gromov-Wasserstein/)).toBeInTheDocument()
  })

  it('修改输入值更新热带计算结果', () => {
    render(<MathUnificationPanel />)
    const inputs = screen.getAllByRole('spinbutton')
    fireEvent.change(inputs[0], { target: { value: '8' } })
    fireEvent.change(inputs[1], { target: { value: '3' } })
    // tropical_add(8, 3) = max(8, 3) = 8
    expect(screen.getByText(/= 8/)).toBeInTheDocument()
  })
})
