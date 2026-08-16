import { approximateViewers, broadcastView } from '../presentation'
import type { Broadcast } from '../types'
import './LiveCard.css'

interface Props {
  broadcast: Broadcast
  onOpen: (broadcast: Broadcast) => void
}

function formatTime(iso: string | null) {
  if (!iso) return ''
  const d = new Date(iso)
  const days = ['일', '월', '화', '수', '목', '금', '토']
  const hh = d.getHours().toString().padStart(2, '0')
  const mm = d.getMinutes().toString().padStart(2, '0')
  return `${d.getMonth() + 1}.${d.getDate().toString().padStart(2, '0')} (${days[d.getDay()]}) ${hh}:${mm}`
}

function LiveCard({ broadcast, onOpen }: Props) {
  // 상태·시각은 서버 값, 제목·썸네일·뱃지는 화면 장식이다 (presentation.ts).
  const view = broadcastView(broadcast.broadcast_id)
  const isLive = broadcast.state === 'LIVE'
  const isEnded = broadcast.state === 'ENDED'

  return (
    <button
      className={`live-card${isEnded ? ' live-card--ended' : ''}`}
      onClick={() => onOpen(broadcast)}
    >
      <img src={view.thumbnail} alt={view.title} className="live-card__img" />

      <div className="live-card__top">
        {view.badges.map((badge) => (
          <span key={badge} className="badge">
            {badge}
          </span>
        ))}
      </div>

      {isLive && <span className="badge badge-live live-card__live-tag">LIVE</span>}

      <div className="live-card__bottom">
        <p className="live-card__brand">{view.brand}</p>
        <p className="live-card__title">{view.title}</p>
        <div className="live-card__meta">
          <span className="live-card__time">{formatTime(broadcast.started_at)}</span>
          {!isLive && !isEnded && (
            <span className="live-card__bell" aria-hidden>
              🔔 알림받기
            </span>
          )}
          {isLive && (
            <span className="live-card__viewers">
              👁 {approximateViewers(broadcast.broadcast_id).toLocaleString()}
            </span>
          )}
        </div>
      </div>
    </button>
  )
}

export default LiveCard
