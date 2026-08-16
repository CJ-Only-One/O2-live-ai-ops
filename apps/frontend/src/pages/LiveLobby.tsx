import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import LiveCard from '../components/LiveCard'
import TabBar from '../components/TabBar'
import { fetchBroadcast, KNOWN_BROADCAST_IDS } from '../services/broadcastService'
import type { Broadcast } from '../types'
import '../styles/common.css'
import './LiveLobby.css'

/**
 * 방송 목록.
 *
 * 계약에 목록 API 가 없어 알려진 방송을 하나씩 조회한다. 상태·시각은 서버
 * 값이고 제목·썸네일은 화면 장식이다 (presentation.ts).
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

  const open = (b: Broadcast) => navigate(`/live/${b.broadcast_id}`)
  const groups: [string, Broadcast[]][] = [
    ['지금 라이브', items.filter((b) => b.state === 'LIVE')],
    ['방송 예정', items.filter((b) => b.state === 'SCHEDULED')],
    ['다시보기', items.filter((b) => b.state === 'ENDED')],
  ]

  return (
    <div className="phone-frame">
      <header className="lobby-header">
        <p className="lobby-header__logo">올영LIVE</p>
        {/*
          탭은 표시만 한다. 방송이 하나뿐이라 거를 것이 없고, 필터를 붙이려면
          목록 API 가 먼저 있어야 한다.
        */}
        <nav className="lobby-tabs">
          <span className="lobby-tabs__item is-active">라이브</span>
          <span className="lobby-tabs__item">예정</span>
          <span className="lobby-tabs__item">다시보기</span>
        </nav>
      </header>

      <main className="lobby-main">
        {error && <p className="lobby-loading">{error}</p>}
        {!error && items.length === 0 && <p className="lobby-loading">불러오는 중...</p>}

        {groups.map(([title, list]) =>
          list.length === 0 ? null : (
            <section className="lobby-section" key={title}>
              <h2 className="lobby-section__title">{title}</h2>
              <div className="lobby-carousel">
                {list.map((b) => (
                  <LiveCard key={b.broadcast_id} broadcast={b} onOpen={open} />
                ))}
              </div>
            </section>
          ),
        )}
      </main>

      <TabBar />
    </div>
  )
}

export default LiveLobby
