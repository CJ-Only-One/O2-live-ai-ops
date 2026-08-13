import { useState } from 'react'
import type { LiveItem } from '../types'
import './LiveDetailSheet.css'

interface Props {
  live: LiveItem
  onClose: () => void
}

function LiveDetailSheet({ live, onClose }: Props) {
  const [notified, setNotified] = useState(false)
  const d = new Date(live.startAt)

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet" onClick={(e) => e.stopPropagation()}>
        <img src={live.thumbnail} alt={live.title} className="sheet__img" />
        <div className="sheet__body">
          <span className="sheet__brand">{live.brand}</span>
          <h3 className="sheet__title">{live.title}</h3>
          <p className="sheet__time">
            {d.getMonth() + 1}월 {d.getDate()}일 {d.getHours()}:
            {d.getMinutes().toString().padStart(2, '0')} 방송 예정
          </p>
          <div className="sheet__badges">
            {live.badges.map((b) => (
              <span key={b} className="badge">
                {b}
              </span>
            ))}
          </div>
          <button
            className="btn-primary sheet__notify"
            disabled={notified}
            onClick={() => setNotified(true)}
          >
            {notified ? '알림 설정 완료' : '🔔 알림받기'}
          </button>
          <button className="sheet__close" onClick={onClose}>
            닫기
          </button>
        </div>
      </div>
    </div>
  )
}

export default LiveDetailSheet
