import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ToastProvider } from './components/Toast'
import App from './App'
import './index.css'
import 'highlight.js/styles/github-dark.css'

// 注册 Service Worker（支持离线访问）
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js')
      .then((registration) => {
        console.log('SW registered: ', registration)
      })
      .catch((error) => {
        console.log('SW registration failed: ', error)
      })
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
