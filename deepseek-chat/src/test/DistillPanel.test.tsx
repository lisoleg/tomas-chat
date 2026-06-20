/**
 * DistillPanel 组件单元测试
 *
 * 测试蒸馏面板的核心逻辑：阶段常量、语料示例、基础渲染
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import React from 'react'
import { DistillPanel } from '../components/DistillPanel'

// Mock heavy dependencies
vi.mock('../api/distiller', () => ({
  buildEMLGraph: vi.fn(),
  buildMergedEML: vi.fn(),
  detectMergeSummary: vi.fn(),
  downloadEMLFile: vi.fn(),
  extractConcepts: vi.fn(),
  extractRelations: vi.fn(),
  formatFileSize: vi.fn((size: number) => `${(size / 1024).toFixed(1)} KB`),
  loadEMLFromBuffer: vi.fn(),
  rebuildGraphAfterDelete: vi.fn(),
  serializeEML: vi.fn(),
  TokenBridgeClient: vi.fn(),
  extractGraphForVisualization: vi.fn(),
}))

vi.mock('../api/knowledgeStore', () => ({
  getAllKnowledgeItems: vi.fn(() => Promise.resolve([])),
  saveKnowledgeItems: vi.fn(),
}))

vi.mock('../api/corpusStore', () => ({
  getAllCorpusEntries: vi.fn(() => Promise.resolve([])),
  saveCorpusEntry: vi.fn(),
  deleteCorpusEntry: vi.fn(),
  saveConflictDecision: vi.fn(),
}))

// Mock Toast
vi.mock('../components/Toast', () => ({
  useToast: () => ({
    toasts: [],
    addToast: vi.fn(),
    removeToast: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  }),
  ToastProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))


// Mock ResizeObserver (not in JSDOM — needed by EMLGraphVisualization child)
class MockResizeObserver {
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
}
(globalThis as any).ResizeObserver = MockResizeObserver as unknown as typeof ResizeObserver


describe('DistillPanel', () => {
  const defaultProps = { apiKey: 'test-key' }

  it('渲染 LLM 蒸馏器标题', () => {
    render(<DistillPanel {...defaultProps} />)

    // 标题栏应显示 LLM 蒸馏器
    expect(screen.getByText('LLM 蒸馏器')).toBeInTheDocument()
  })

  it('显示文本输入区和占位符', async () => {
    render(<DistillPanel {...defaultProps} />)

    // 文本输入区存在，占位符包含"开始蒸馏"
    const textarea = screen.getByPlaceholderText(/开始蒸馏/i)
    expect(textarea).toBeInTheDocument()
  })

  it('显示开始蒸馏按钮（含 emoji）', async () => {
    render(<DistillPanel {...defaultProps} />)

    // 按钮文本含 🔬 和"开始蒸馏"
    expect(screen.getByText(/开始蒸馏/)).toBeInTheDocument()
  })

  it('显示示例语料按钮（物理/化学/AI/医学）', async () => {
    render(<DistillPanel {...defaultProps} />)

    expect(screen.getByText('物理')).toBeInTheDocument()
    expect(screen.getByText('化学')).toBeInTheDocument()
    expect(screen.getByText('AI/ML')).toBeInTheDocument()
    expect(screen.getByText('医学')).toBeInTheDocument()
  })

  it('默认显示文本输入区', async () => {
    render(<DistillPanel {...defaultProps} />)

    // 应显示示例语料标题
    expect(screen.getByText(/示例语料/i)).toBeInTheDocument()
  })

  it('标题栏包含副标题', () => {
    render(<DistillPanel {...defaultProps} />)

    // 副标题描述
    expect(screen.getByText(/将世界知识压缩进 EML 图/i)).toBeInTheDocument()
  })
})
