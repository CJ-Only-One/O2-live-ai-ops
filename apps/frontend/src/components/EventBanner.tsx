import { useEffect, useState } from 'react'

import './EventBanner.css'

export interface Banner {
  id: string
  eyebrow: string
  title: string
  sub: string
  image: string
  tint: string
}

interface Props {
  banners: Banner[]
}

/**
 * 메인 이벤트 배너.
 *
 * 자동으로 넘어가고 손으로도 넘길 수 있다. 실제 앱처럼 현재 위치를
 * "2 / 5" 로 보여준다 — 점보다 개수를 세기 쉽다.
 *
 * 움직임을 줄이도록 설정한 사용자에게는 자동 전환을 하지 않는다.
 */
const INTERVAL_MS = 4000

function EventBanner({ banners }: Props) {
  const [index, setIndex] = useState(0)

  useEffect(() => {
    if (banners.length <= 1) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

    const timer = window.setInterval(
      () => setIndex((i) => (i + 1) % banners.length),
      INTERVAL_MS,
    )
    return () => clearInterval(timer)
  }, [banners.length])

  if (banners.length === 0) return null

  return (
    <section className="banner">
      <div className="banner__stage">
        {banners.map((b, i) => (
          <article
            key={b.id}
            className={`banner__slide${i === index ? ' is-active' : ''}`}
            aria-hidden={i !== index}
          >
            <img src={b.image} alt="" className="banner__img" />
            <div className="banner__scrim" style={{ background: b.tint }} />
            <div className="banner__text">
              <p className="banner__eyebrow">{b.eyebrow}</p>
              <h2 className="banner__title">{b.title}</h2>
              <p className="banner__sub">{b.sub}</p>
            </div>
          </article>
        ))}
      </div>

      <div className="banner__controls">
        <button
          className="banner__nav"
          onClick={() => setIndex((i) => (i - 1 + banners.length) % banners.length)}
          aria-label="이전 배너"
        >
          ‹
        </button>
        <span className="banner__count">
          <strong>{index + 1}</strong> / {banners.length}
        </span>
        <button
          className="banner__nav"
          onClick={() => setIndex((i) => (i + 1) % banners.length)}
          aria-label="다음 배너"
        >
          ›
        </button>
      </div>

      <div className="banner__progress" aria-hidden>
        <span style={{ width: `${((index + 1) / banners.length) * 100}%` }} />
      </div>
    </section>
  )
}

export default EventBanner
