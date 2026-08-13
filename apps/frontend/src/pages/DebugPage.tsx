import { useEffect, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

interface Item {
  id: number
  name: string
}

// 백엔드(FastAPI + MySQL) 연결 확인용 페이지. 실제 라이브커머스 데모와는 별개.
function DebugPage() {
  const [status, setStatus] = useState('확인 중...')
  const [items, setItems] = useState<Item[]>([])
  const [name, setName] = useState('')
  const [itemsError, setItemsError] = useState('')

  useEffect(() => {
    fetch(`${API_BASE_URL}/health`)
      .then((res) => res.json())
      .then((data) => setStatus(data.status))
      .catch(() => setStatus('백엔드에 연결하지 못했습니다'))

    loadItems()
  }, [])

  function loadItems() {
    fetch(`${API_BASE_URL}/items`)
      .then((res) => {
        if (!res.ok) throw new Error()
        return res.json()
      })
      .then((data) => {
        setItems(data)
        setItemsError('')
      })
      .catch(() => setItemsError('목록을 불러오지 못했습니다 (DB 연결을 확인하세요)'))
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return

    fetch(`${API_BASE_URL}/items`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
      .then((res) => {
        if (!res.ok) throw new Error()
        setName('')
        loadItems()
      })
      .catch(() => setItemsError('저장하지 못했습니다 (DB 연결을 확인하세용)'))
  }

  return (
    <div style={{ padding: 24, fontFamily: 'sans-serif' }}>
      <h1>O2 Debug</h1>
      <p>백엔드 상태: {status}</p>

      <h2>아이템 테스트</h2>
      <form onSubmit={handleSubmit}>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="이름 입력" />
        <button type="submit">추가</button>
      </form>

      {itemsError && <p>{itemsError}</p>}

      <ul>
        {items.map((item) => (
          <li key={item.id}>{item.name}</li>
        ))}
      </ul>
    </div>
  )
}

export default DebugPage
