import { useRef, useState } from 'react'
import { initialChat } from '../mocks/chat'
import type { ChatMessage } from '../types'

// live-api + Redis의 SSE 채팅 스트림을 흉내낸다.
// 실제 연결로 바꿀 땐 sendMessage 대신 new EventSource(...)로 메시지를 받으면 된다.
export function useChatStream() {
  const [messages, setMessages] = useState<ChatMessage[]>(initialChat)
  const idRef = useRef(0)

  function sendMessage(text: string) {
    if (!text.trim()) return
    idRef.current += 1
    setMessages((prev) => [
      ...prev,
      { id: `me-${idRef.current}`, author: '나', text, kind: 'chat' },
    ])
  }

  return { messages, sendMessage }
}
