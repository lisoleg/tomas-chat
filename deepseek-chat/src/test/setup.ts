import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'
import '@testing-library/jest-dom'

// 每个测试后清理 DOM
afterEach(() => {
  cleanup()
})

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => {},
  }),
})

// 简单的 IntersectionObserver mock
class MockIO {
  constructor(public callback: any) {}
  disconnect() {}
  observe() {}
  takeRecords() { return [] }
  unobserve() {}
}
globalThis.IntersectionObserver = MockIO as any

// 简单的 ResizeObserver mock
class MockRO {
  constructor(public callback: any) {}
  disconnect() {}
  observe() {}
  unobserve() {}
}
globalThis.ResizeObserver = MockRO as any

console.log('[Vitest Setup] @testing-library/jest-dom loaded')
