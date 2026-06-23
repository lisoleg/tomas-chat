// 消息列表：自动滚动到底部
import React, { useEffect, useRef } from 'react'
import type { ChatMessage } from '../types'
import { MessageBubble } from './MessageBubble'

interface MessageListProps {
  messages: ChatMessage[]
  onRetryDirect?: (messageId: string) => void
  onFeedback?: (messageId: string, feedback: 'like' | 'dislike' | null) => void
}

function MessageListInner({ messages, onRetryDirect, onFeedback }: MessageListProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  // 消息变化或内容更新（流式）时，自动滚动到底部
  useEffect(() => {
    const el = bottomRef.current
    if (el) {
      // 平滑滚动
      try {
        el.scrollIntoView({ behavior: 'smooth', block: 'end' })
      } catch {
        el.scrollIntoView()
      }
    }
  }, [messages])

  return (
    <div
      ref={containerRef}
      className="flex-1 min-h-0 overflow-y-auto chat-scroll"
    >
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} onRetryDirect={onRetryDirect} onFeedback={onFeedback} />
      ))}
      <div ref={bottomRef} className="h-2" />
    </div>
  )
}

export const MessageList = React.memo(MessageListInner, (prev, next) => {
  return prev.messages === next.messages
    && prev.onRetryDirect === next.onRetryDirect
    && prev.onFeedback === next.onFeedback
})
