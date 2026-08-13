import { useEffect, useRef, useState } from 'react'
import type { ChatMessage } from '../types'
import './ChatPanel.css'

interface Props {
  messages: ChatMessage[]
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
        {messages.map((m) => (
          <div key={m.id} className={`chat-msg chat-msg--${m.kind}`}>
            <span className="chat-msg__author">{m.author}</span>
            <span className="chat-msg__text">{m.text}</span>
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
