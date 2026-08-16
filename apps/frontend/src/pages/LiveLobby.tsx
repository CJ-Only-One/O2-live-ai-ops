import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { fetchBroadcast, KNOWN_BROADCAST_IDS } from '../services/broadcastService'
import type { Broadcast } from '../types'
import '../styles/common.css'

/**
 * 방송 목록.
 *
 * 계약에 목록 API 가 없어 알려진 방송을 하나씩 조회한다. mock 서비스를 두면
 * 없는 API 가 있는 것처럼 보이므로 상수를 그대로 쓴다. 목록이 필요해지면
 * 계약에 GET /api/broadcasts 를 추가하는 것이 먼저다.
 */
function LiveLobby() {
  const navigate = useNavigate()
  const [items, setItems] = useState<Broadcast[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.allSettled(KNOWN_BROADCAST_IDS.map(fetchBroadcast)).then((results) => {
      const ok = results
        .filter((r): r is PromiseFulfilledResult<Broadcast> => r.status === 'fulfilled')
        .map((r) => r.value)
      setItems(ok)
      if (ok.length === 0) setError('방송을 불러오지 못했습니다')
    })
  }, [])

  if (error) {
    return (
      <div className="phone-frame">
        <p className="lobby-loading">{error}</p>
      </div>
    )
  }

  return (
    <div className="phone-frame">
      <h1 style={{ padding: '20px 16px 8px', fontSize: 20 }}>올영 LIVE</h1>
      {items.length === 0 && <p className="lobby-loading">불러오는 중...</p>}
      {items.map((b) => (
        <button
          key={b.broadcast_id}
          onClick={() => navigate(`/live/${b.broadcast_id}`)}
          style={{
            display: 'block',
            width: '100%',
            padding: '16px',
            textAlign: 'left',
            background: 'none',
            border: 'none',
            borderBottom: '1px solid rgba(0,0,0,.08)',
            cursor: 'pointer',
          }}
        >
          <span className="badge badge-live">{b.state}</span>
          <p style={{ margin: '8px 0 4px', fontWeight: 600 }}>{b.broadcast_id}</p>
          <p style={{ margin: 0, fontSize: 13, opacity: 0.7 }}>
            상품 {b.products.length}개
          </p>
        </button>
      ))}
    </div>
  )
}

export default LiveLobby
