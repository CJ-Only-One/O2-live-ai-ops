/**
 * 방송 시작 전 화면.
 *
 * 실제 올리브영 라이브가 SCHEDULED 방송에서 보여주는 것과 같은 구성이다 —
 * 상품 이미지, 멘트, 시작까지 남은 시간, 편성 시각.
 *
 * 남은 시간은 서버가 내려주지 않는다. 스냅샷 응답이 캐시를 타므로 "남은
 * 초"를 담으면 캐시에 굳은 값이 박힌다. started_at 만 받고 뺄셈은 여기서 한다.
 */

import { useEffect, useState } from 'react'

import { broadcastView } from '../presentation'
import './PreBroadcast.css'

interface Props {
  broadcastId: string
  /** ISO 8601. 계약상 null 일 수 있다 (contracts.md 2.1) */
  startedAt: string | null
  onClose: () => void
}

/** 남은 밀리초를 HH:MM:SS 로. 이미 지났으면 null 이다. */
function formatCountdown(remainMs: number): string | null {
  if (remainMs <= 0) return null
  const total = Math.floor(remainMs / 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(Math.floor(total / 3600))}:${pad(Math.floor(total / 60) % 60)}:${pad(total % 60)}`
}

/** "8.18(화) PM 8:00 방송" — 편성표 표기라 한국 시간으로 고정한다. */
function formatSchedule(iso: string): string {
  const d = new Date(iso)
  const parts = new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    month: 'numeric',
    day: 'numeric',
    weekday: 'short',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).formatToParts(d)
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? ''
  const ampm = get('dayPeriod') === '오전' ? 'AM' : 'PM'
  return `${get('month')}.${get('day')}(${get('weekday')}) ${ampm} ${get('hour')}:${get('minute')} 방송`
}

function PreBroadcast({ broadcastId, startedAt, onClose }: Props) {
  const view = broadcastView(broadcastId)
  const [now, setNow] = useState(() => Date.now())

  // 1초마다 다시 그린다. 방송 전 화면에만 있는 타이머라 방송이 시작되면
  // 이 컴포넌트째로 사라진다.
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])

  const startMs = startedAt ? new Date(startedAt).getTime() : null
  const countdown = startMs === null ? null : formatCountdown(startMs - now)

  return (
    <div className="phone-frame prelive">
      <div className="prelive__stage">
        <img src={view.thumbnail} alt="" className="prelive__img" />
        <div className="prelive__scrim" />

        <button className="icon-btn prelive__close" onClick={onClose} aria-label="닫기">
          ✕
        </button>

        <div className="prelive__copy">
          <h1 className="prelive__title">{view.title}</h1>
          <p className="prelive__teaser">{view.teaser}</p>

          {/* 시작 시각을 모르면 남은 시간을 만들 수 없다. 문구로 흡수한다. */}
          <p className="prelive__countdown">
            {countdown ? (
              <>
                <b>{countdown}</b> 후 방송 시작
              </>
            ) : (
              '곧 방송이 시작됩니다'
            )}
          </p>
        </div>
      </div>

      <div className="prelive__bar">
        <span>{startedAt ? formatSchedule(startedAt) : '편성 시각 미정'}</span>
      </div>
    </div>
  )
}

export default PreBroadcast
