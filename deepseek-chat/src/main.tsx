import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ToastProvider } from './components/Toast'
import App from './App'
import './index.css'
import 'highlight.js/styles/github-dark.css'

// Service Worker 已禁用（避免缓存旧 API 数据导致显示脏数据）
// 如果之前注册过，自动卸载 + 清空 Cache Storage
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations().then(regs => {
    for (const reg of regs) {
      reg.unregister()
      console.log('[SW] 已卸载旧 Service Worker')
    }
  })
}
// 清空所有缓存（防止旧 API 响应被缓存导致显示脏数据）
if ('caches' in window) {
  caches.keys().then(names => {
    for (const name of names) {
      caches.delete(name)
      console.log('[Cache] 已删除缓存:', name)
    }
  })
}

// 挂载 React 应用
const rootEl = document.getElementById('root')
if (rootEl) {
  createRoot(rootEl).render(
    <StrictMode>
      <ToastProvider>
        <App />
      </ToastProvider>
    </StrictMode>
  )
}
