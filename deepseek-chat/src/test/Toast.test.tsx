import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ToastProvider, useToast } from '../components/Toast'

// 测试组件：使用 Toast 的示例组件
function TestComponent() {
  const { success, error, warning, info } = useToast()

  return (
    <div>
      <button onClick={() => success('成功', '消息内容', 1000)}>显示成功</button>
      <button onClick={() => error('错误', '错误消息')}>显示错误</button>
      <button onClick={() => warning('警告', '警告消息')}>显示警告</button>
      <button onClick={() => info('信息', '信息消息')}>显示信息</button>
    </div>
  )
}

describe('Toast 组件', () => {
  it('渲染 ToastProvider', () => {
    render(
      <ToastProvider>
        <TestComponent />
      </ToastProvider>
    )
    
    expect(screen.getByText('显示成功')).toBeInTheDocument()
    expect(screen.getByText('显示错误')).toBeInTheDocument()
  })

  it('点击成功按钮显示 Toast', async () => {
    render(
      <ToastProvider>
        <TestComponent />
      </ToastProvider>
    )

    const successButton = screen.getByText('显示成功')
    fireEvent.click(successButton)

    // 等待 Toast 出现（title 是 '成功'）
    const toast = await screen.findByText('成功')
    expect(toast).toBeInTheDocument()
  })

  it('Toast 自动消失（duration=1000）', async () => {
    render(
      <ToastProvider>
        <TestComponent />
      </ToastProvider>
    )

    const successButton = screen.getByText('显示成功')
    fireEvent.click(successButton)

    // 确认 Toast 出现
    expect(await screen.findByText('成功')).toBeInTheDocument()

    // 等待 Toast 消失（duration=1000ms，给一点缓冲时间）
    await new Promise(resolve => setTimeout(resolve, 1100))

    // Toast 应该消失
    const toast = screen.queryByText('成功')
    expect(toast).not.toBeInTheDocument()
  }, 5000) // 增加测试超时到 5 秒
})

describe('useToast Hook', () => {
  it('抛出错误当在 Provider 外使用', () => {
    // 抑制 console.error
    const consoleError = console.error
    console.error = vi.fn()

    expect(() => render(<TestComponent />)).toThrow()

    console.error = consoleError
  })
})
