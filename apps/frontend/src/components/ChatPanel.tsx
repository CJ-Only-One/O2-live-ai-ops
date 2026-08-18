import { useEffect, useRef, useState } from 'react'
import type { ChatItem } from '../types'
import './ChatPanel.css'

interface Props {
  messages: ChatItem[]
  onSend: (text: string) => void
}

function ChatPanel({ messages, onSend }: Props) {
  const [draft, setDraft] = useState('')
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [messages])

  function submit(e: React.FormEvent) {
    e.preventDefault()
    onSend(draft)
    setDraft('')
  }

  return (
    <div className="chat-panel">
      <div className="chat-panel__list" ref={listRef}>
        {messages.map((m, i) => (
          // 서버가 메시지 id 를 주지 않는다. 채팅은 유실을 감수하는 흐름이라
          // 안정적인 키가 필요 없고, 화면에서만 순서를 유지하면 된다.
          <div key={`${m.ts}-${i}`} className="chat-msg chat-msg--chat">
            <span className="chat-msg__author">{m.nick}</span>
            <span className="chat-msg__text">{m.msg}</span>
          </div>
        ))}
      </div>
      <form className="chat-panel__form" onSubmit={submit}>
        <input
          className="chat-panel__input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="댓글을 입력하세요"
        />
        <button className="chat-panel__send" type="submit" aria-label="전송">
          ➤
        </button>
      </form>
    </div>
  )
}

export default ChatPanel
