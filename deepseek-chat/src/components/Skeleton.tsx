interface SkeletonProps {
  className?: string
  lines?: number
  active?: boolean
}

export function SkeletonBox({ className = '' }: { className?: string }) {
  return (
    <div className={`animate-pulse bg-white/5 rounded ${className}`} />
  )
}

export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className={`animate-pulse bg-white/5 rounded h-4 ${
            i === lines - 1 ? 'w-3/4' : 'w-full'
          }`}
        />
      ))}
    </div>
  )
}

export function SkeletonCard() {
  return (
    <div className="p-4 border border-white/5 rounded-lg space-y-3">
      <SkeletonBox className="h-6 w-1/3" />
      <SkeletonText lines={2} />
      <div className="flex gap-2">
        <SkeletonBox className="h-8 w-20" />
        <SkeletonBox className="h-8 w-20" />
      </div>
    </div>
  )
}

export function SkeletonGraph() {
  return (
    <div className="w-full h-full min-h-[400px] flex items-center justify-center">
      <div className="text-center space-y-4">
        <div className="animate-spin w-12 h-12 border-4 border-indigo-500/30 border-t-indigo-500 rounded-full mx-auto" />
        <SkeletonText lines={2} />
      </div>
    </div>
  )
}

// 加载覆盖层（全屏）
export function LoadingOverlay({ message = '加载中...' }: { message?: string }) {
  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center">
      <div className="bg-chatBg border border-white/10 rounded-xl p-8 max-w-sm text-center space-y-4">
        <div className="animate-spin w-12 h-12 border-4 border-indigo-500/30 border-t-indigo-500 rounded-full mx-auto" />
        <p className="text-textPrimary font-medium">{message}</p>
      </div>
    </div>
  )
}
