/**
 * HLS 플레이어.
 *
 * 사파리는 `<video src="...m3u8">` 를 그대로 재생하지만 크롬·파이어폭스는
 * 못 한다. hls.js 가 플레이리스트를 받아 세그먼트를 MediaSource 로 밀어
 * 넣는다. 그래서 네이티브를 먼저 보고, 없을 때만 hls.js 를 붙인다 —
 * 사파리에서 굳이 자바스크립트로 다시 구현할 이유가 없다.
 *
 * hls.js 는 동적 임포트로 받는다. 정적으로 임포트하면 번들이 254KB 에서
 * 764KB 로 늘고, 사파리와 방송 전 화면처럼 쓰지 않는 경우에도 내려간다.
 *
 * **재생 실패는 화면을 깨뜨리지 않는다.** 송출이 없으면 플레이리스트가 아예
 * 없고(404), 그때는 썸네일로 떨어진다. 방송 중인데 OBS 를 안 켠 상태가
 * 흔하므로 이 경로가 예외가 아니라 정상 분기다.
 */

import { useEffect, useRef, useState } from 'react'

interface Props {
  /** contracts.md 2.1 의 hls_url. 없으면 재생할 것이 없다 */
  src: string | null
  /** 재생이 안 될 때 대신 보여줄 이미지 */
  poster: string
  muted: boolean
}

function LivePlayer({ src, poster, muted }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const video = videoRef.current
    if (!video || !src) return

    setFailed(false)

    // 사파리·iOS. 네이티브가 세그먼트 관리까지 다 한다.
    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = src
      return
    }

    // 언마운트가 임포트보다 빠를 수 있다. 그때 만들어진 인스턴스를 정리한다.
    let disposed = false
    let hls: { destroy: () => void } | null = null

    import('hls.js').then(({ default: Hls }) => {
      if (disposed) return
      if (!Hls.isSupported()) {
        setFailed(true)
        return
      }

      const instance = new Hls({
        // 라이브는 끝에 붙어야 한다. 기본값은 세그먼트 3개 뒤에서 시작해
        // 지연이 그만큼 늘어난다.
        liveSyncDurationCount: 2,
      })
      hls = instance
      instance.loadSource(src)
      instance.attachMedia(video)

      instance.on(Hls.Events.ERROR, (_e, data) => {
        // 네트워크 오류는 재시도로 회복되는 경우가 많다. 치명적인 것만 접는다.
        if (data.fatal) setFailed(true)
      })
    })

    return () => {
      disposed = true
      hls?.destroy()
    }
  }, [src])

  if (!src || failed) {
    return <img src={poster} alt="" className="room__video-img" />
  }

  return (
    <video
      ref={videoRef}
      className="room__video-img"
      poster={poster}
      autoPlay
      muted={muted}
      playsInline
    />
  )
}

export default LivePlayer
