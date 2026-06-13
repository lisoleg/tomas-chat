import { createContext, useContext, useState, useCallback, ReactNode } from 'react'

interface Toast {
  id: number
  type: 'success' | 'error' | 'warning' | 'info'
  title: string
  message?: string
  duration?: number // 毫秒，0 表示不自动关闭
}

interface ToastContextType {
  toasts: Toast[]
  addToast: (toast: Omit<Toast, 'id'>) => void
  removeToast: (id: number) => void
  success: (title: string, message?: string) => void
  error: (title: string, message?: string) => void
  warning: (title: string, message?: string) => void
  info: (title: string, message?: string) => void
}

const ToastContext = createContext<ToastContextType | null>(null)

let toastIdCounter = 0

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const removeToast = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const addToast = useCallback((toast: Omit<Toast, 'id'>) => {
    const id = ++toastIdCounter
    const newToast: Toast = {
      ...toast,
      id,
      duration: toast.duration ?? 4000,
    }

    setToasts(prev => [...prev, newToast])

    // 自动关闭
    if (newToast.duration > 0) {
      setTimeout(() => removeToast(id), newToast.duration)
    }
  }, [removeToast])

  const value: ToastContextType = {
    toasts,
    addToast,
    removeToast,
    success: (title, message) => addToast({ type: 'success', title, message }),
    error: (title, message) => addToast({ type: 'error', title, message }),
    warning: (title, message) => addToast({ type: 'warning', title, message }),
    info: (title, message) => addToast({ type: 'info', title, message }),
  }

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastContainer toasts={toasts} onRemove={removeToast} />
    </ToastContext.Provider>
  )
}

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('useToast must be used within ToastProvider')
  }
  return context
}

// ==================== Toast UI 组件 ====================

function ToastContainer({ toasts, onRemove }: { toasts: Toast[]; onRemove: (id: number) => void }) {
  if (toasts.length === 0) return null

  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 max-w-md">
      {toasts.map(toast => (
        <ToastItem key={toast.id} toast={toast} onRemove={onRemove} />
      ))}
    </div>
  )
}

function ToastItem({ toast, onRemove }: { toast: Toast; onRemove: (id: number) => void }) {
  const iconMap = {
    success: '✅',
    error: '❌',
    warning: '⚠️',
    info: 'ℹ️',
  }

  const bgMap = {
    success: 'bg-emerald-900/90 border-emerald-600/30',
    error: 'bg-rose-900/90 border-rose-600/30',
    warning: 'bg-amber-900/90 border-amber-600/30',
    info: 'bg-blue-900/90 border-blue-600/30',
  }

  return (
    <div
      className={`
        ${bgMap[toast.type]}
        backdrop-blur-sm border rounded-lg p-4 shadow-lg
        animate-slide-in-right
        transition-all duration-300 ease-in-out
      `}
    >
      <div className="flex items-start gap-3">
        <span className="text-xl flex-shrink-0">{iconMap[toast.type]}</span>
        
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-textPrimary">{toast.title}</p>
          {toast.message && (
            <p className="text-xs text-textSecondary mt-1">{toast.message}</p>
          )}
        </div>

        <button
          onClick={() => onRemove(toast.id)}
          className="flex-shrink-0 text-textSecondary hover:text-textPrimary transition-colors"
        >
          ✕
        </button>
      </div>
    </div>
  )
}
