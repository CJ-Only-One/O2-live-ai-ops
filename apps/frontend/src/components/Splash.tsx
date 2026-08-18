import { useEffect, useState } from 'react'

import './Splash.css'

/**
 * 앱 진입 스플래시.
 *
 * 실제 앱처럼 로고를 잠깐 띄운다. 화면 전환일 뿐 데이터를 기다리지 않는다 —
 * 여기서 API 를 기다리면 서버가 느릴 때 진입이 통째로 막힌다.
 *
 * 세션당 한 번만 보여준다. 방송 화면에서 새로고침할 때마다 로고가 뜨면
 * 데모 중에 거슬린다.
 */
const SHOWN_KEY = 'o2-splash-shown'
const DURATION_MS = 1400

function Splash() {
  const [visible, setVisible] = useState(() => !sessionStorage.getItem(SHOWN_KEY))
  const [leaving, setLeaving] = useState(false)

  useEffect(() => {
    if (!visible) return
    sessionStorage.setItem(SHOWN_KEY, '1')

    const fade = window.setTimeout(() => setLeaving(true), DURATION_MS - 400)
    const done = window.setTimeout(() => setVisible(false), DURATION_MS)
    return () => {
      clearTimeout(fade)
      clearTimeout(done)
    }
  }, [visible])

  if (!visible) return null

  return (
    <div className={`splash${leaving ? ' is-leaving' : ''}`} aria-hidden>
      <div className="splash__mark">
        <span className="splash__leaf" />
        <span className="splash__word">OLIVE YOUNG</span>
      </div>
      <span className="splash__sub">LIVE</span>
    </div>
  )
}

export default Splash
