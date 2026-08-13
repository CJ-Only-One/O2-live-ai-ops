import type { LiveItem } from '../types'
import './LiveCard.css'

interface Props {
  live: LiveItem
  onOpen: (live: LiveItem) => void
}

function formatTime(iso: string) {
  const d = new Date(iso)
  const days = ['일', '월', '화', '수', '목', '금', '토']
  const hh = d.getHours().toString().padStart(2, '0')
  const mm = d.getMinutes().toString().padStart(2, '0')
  return `${d.getMonth() + 1}.${d.getDate().toString().padStart(2, '0')} (${days[d.getDay()]}) ${hh}:${mm}`
}

function LiveCard({ live, onOpen }: Props) {
  const isLive = live.status === 'LIVE'
  const isEnded = live.status === 'ENDED'

  return (
    <button
      className={`live-card${isEnded ? ' live-card--ended' : ''}`}
      onClick={() => onOpen(live)}
    >
      <img src={live.thumbnail} alt={live.title} className="live-card__img" />

      <div className="live-card__top">
        {live.badges.map((badge) => (
          <span key={badge} className="badge">
            {badge}
          </span>
        ))}
      </div>

      {isLive && <span className="badge badge-live live-card__live-tag">LIVE</span>}

      <div className="live-card__bottom">
        <p className="live-card__title">{live.title}</p>
        <div className="live-card__meta">
          <span className="live-card__time">{formatTime(live.startAt)}</span>
          {!isLive && !isEnded && (
            <span className="live-card__bell" aria-hidden>
              🔔 알림받기
            </span>
          )}
          {isLive && <span className="live-card__viewers">👁 {live.viewerCount.toLocaleString()}</span>}
        </div>
      </div>
    </button>
  )
}

export default LiveCard
