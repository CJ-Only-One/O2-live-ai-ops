import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchLives } from '../services/liveService'
import type { LiveItem } from '../types'
import LiveCard from '../components/LiveCard'
import LiveDetailSheet from '../components/LiveDetailSheet'
import '../styles/common.css'
import './LiveLobby.css'

const TABS = ['샵티끄', '매거진', '라이브'] as const

function LiveLobby() {
  const [lives, setLives] = useState<LiveItem[]>([])
  const [loading, setLoading] = useState(true)
  const [detailLive, setDetailLive] = useState<LiveItem | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    fetchLives().then((data) => {
      setLives(data)
      setLoading(false)
    })
  }, [])

  function handleOpen(live: LiveItem) {
    if (live.status === 'LIVE') {
      navigate(`/live/${live.id}`)
    } else if (live.status === 'UPCOMING') {
      setDetailLive(live)
    }
  }

  const liveNow = lives.filter((l) => l.status === 'LIVE')
  const upcoming = lives.filter((l) => l.status === 'UPCOMING')
  const ended = lives.filter((l) => l.status === 'ENDED')

  return (
    <div className="phone-frame">
      <header className="lobby-header">
        <span className="lobby-header__logo">OLIVE YOUNG</span>
        <nav className="lobby-tabs">
          {TABS.map((tab) => (
            <span key={tab} className={`lobby-tabs__item${tab === '라이브' ? ' is-active' : ''}`}>
              {tab}
            </span>
          ))}
        </nav>
      </header>

      <main className="lobby-main">
        {loading && <p className="lobby-loading">불러오는 중...</p>}

        {!loading && liveNow.length > 0 && (
          <section className="lobby-section">
            <h2 className="lobby-section__title">지금 LIVE</h2>
            <div className="lobby-carousel">
              {liveNow.map((live) => (
                <LiveCard key={live.id} live={live} onOpen={handleOpen} />
              ))}
            </div>
          </section>
        )}

        {!loading && upcoming.length > 0 && (
          <section className="lobby-section">
            <h2 className="lobby-section__title">방송 예정</h2>
            <div className="lobby-carousel">
              {upcoming.map((live) => (
                <LiveCard key={live.id} live={live} onOpen={handleOpen} />
              ))}
            </div>
          </section>
        )}

        {!loading && ended.length > 0 && (
          <section className="lobby-section">
            <h2 className="lobby-section__title">다시보기</h2>
            <div className="lobby-carousel">
              {ended.map((live) => (
                <LiveCard key={live.id} live={live} onOpen={handleOpen} />
              ))}
            </div>
          </section>
        )}
      </main>

      {detailLive && <LiveDetailSheet live={detailLive} onClose={() => setDetailLive(null)} />}
    </div>
  )
}

export default LiveLobby
