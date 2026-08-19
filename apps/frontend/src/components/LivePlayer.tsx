/**
 * HLS 플레이어.
 *
 * 사파리는 `<video src="...m3u8">` 를 그대로 재생하지만 크롬·파이어폭스는
 * 못 한다. hls.js 가 플레이리스트를 받아 세그먼트를 MediaSource 로 밀어
 * 넣는다. 그래서 네이티브를 먼저 보고, 없을 때만 hls.js 를 붙인다.
 *
 * hls.js 는 동적 임포트로 받는다. 정적으로 임포트하면 번들이 254KB 에서
 * 764KB 로 늘고, 사파리와 방송 전 화면처럼 쓰지 않는 경우에도 내려간다.
 *
 * **끊김은 예외가 아니라 일상이다.** 송출자가 잠깐 끊기고, 설정이 리로드되고,
 * 파드가 옮겨간다. 한 번 실패했다고 영구히 썸네일로 두면 사용자는 새로고침
 * 말고 방법이 없다. 그래서 이 컴포넌트는 계속 재시도한다.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

/** 이 시간 동안 재생이 안 돌아오면 그때 썸네일로 바꾼다. 그 전에는 마지막
 *  프레임을 유지한다 — 2초짜리 끊김에 화면이 깜빡이면 더 나빠 보인다. */
const THUMBNAIL_AFTER_MS = 3000

/** 재시도 간격. 활성 탭 기준이다. 플레이리스트 자체를 몇 초마다 받아가므로
 *  4초 재시도가 과하지 않다. 더 늘리면 보고 있는 사람이 오래 기다린다. */
const BACKOFF_MS = [1000, 2000, 4000]

/** hls.js 자체 복구를 이 횟수까지 믿는다. 넘으면 인스턴스를 다시 만든다.
 *  시간으로 재면 hls.js 가 백오프 중인 것과 구분이 안 된다. */
const RECOVER_ATTEMPTS = 3

/** 부모에게 방송 상태를 다시 확인해 달라고 조르는 최소 간격.
 *  없으면 끊긴 동안 API 를 계속 두드린다. */
const RECHECK_MIN_MS = 30000

interface Props {
  /** contracts.md 2.1 의 hls_url. 없으면 재생할 것이 없다 */
  src: string | null
  /** 재생이 안 될 때 대신 보여줄 이미지 */
  poster: string
  muted: boolean
  /**
   * 방송이 진행 중인가. 끝난 방송에 영원히 재시도하지 않기 위한 조건이다.
   *
   * 이 값은 진입 시 1회 조회한 스냅샷에서 온다. 그래서 **낡을 수 있다** —
   * 그것만 믿고 재시도를 끊으면 살아난 방송을 놓친다. 대신 재생이 오래
   * 안 돌아올 때 onStalled 로 부모에게 다시 확인해 달라고 한다.
   */
  live: boolean
  /** 재생이 계속 실패할 때 호출된다. 부모가 스냅샷을 다시 받아 live 를 갱신한다 */
  onStalled?: () => void
}

function LivePlayer({ src, poster, muted, live, onStalled }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const hlsRef = useRef<{ destroy: () => void } | null>(null)
  const attachRef = useRef<(() => void) | null>(null)
  const timerRef = useRef<number | null>(null)
  const failuresRef = useRef(0)
  const lastRecheckRef = useRef(0)
  const generationRef = useRef(0)

  // 재생 중이 아니면 '재연결 중', 그 상태가 길어지면 썸네일까지 간다.
  const [playing, setPlaying] = useState(false)
  const [showPoster, setShowPoster] = useState(true)

  const clearTimer = () => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }

  /** 다음 재시도를 예약한다. 숨겨진 탭에서는 예약하지 않는다. */
  const scheduleRetry = useCallback(() => {
    clearTimer()
    if (document.visibilityState !== 'visible') return

    const delay = BACKOFF_MS[Math.min(failuresRef.current, BACKOFF_MS.length - 1)]
    timerRef.current = window.setTimeout(() => attachRef.current?.(), delay)

    // 끊김이 길어지면 방송이 끝난 것일 수 있다. 부모에게 확인을 부탁한다.
    const now = Date.now()
    if (failuresRef.current >= RECOVER_ATTEMPTS && now - lastRecheckRef.current > RECHECK_MIN_MS) {
      lastRecheckRef.current = now
      onStalled?.()
    }
  }, [onStalled])

  const attach = useCallback(() => {
    const video = videoRef.current
    if (!video || !src || !live) return

    hlsRef.current?.destroy()
    hlsRef.current = null

    // 사파리·iOS. 네이티브가 세그먼트 관리와 재시도까지 한다.
    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = src
      void video.play().catch(() => scheduleRetry())
      return
    }

    // 임포트가 끝나기 전에 다시 attach 되면 그 사이 인스턴스가 두 개가 된다.
    // 세대 번호로 늦게 도착한 것을 버린다.
    generationRef.current += 1
    const generation = generationRef.current

    import('hls.js').then(({ default: Hls }) => {
      if (generation !== generationRef.current || !Hls.isSupported()) return

      const hls = new Hls({
        // 라이브는 끝에 붙어야 한다. 기본값은 세그먼트 3개 뒤에서 시작해
        // 지연이 그만큼 늘어난다.
        liveSyncDurationCount: 2,
      })
      hlsRef.current = hls
      hls.loadSource(src)
      hls.attachMedia(video)

      hls.on(Hls.Events.ERROR, (_e, data) => {
        if (!data.fatal) return

        failuresRef.current += 1

        // hls.js 의 복구 사다리를 먼저 쓴다. 우리 타이머로 먼저 부수면
        // 회복될 연결을 우리가 끊는다.
        if (failuresRef.current <= RECOVER_ATTEMPTS) {
          if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
            hls.startLoad()
            return
          }
          if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
            hls.recoverMediaError()
            return
          }
        }

        // 그래도 안 되면 인스턴스째 다시 만든다.
        scheduleRetry()
      })
    })
  }, [src, live, scheduleRetry])

  // scheduleRetry 가 attach 를 부르고 attach 가 scheduleRetry 를 부른다.
  // 서로를 직접 참조하면 순환이라 ref 를 한 겹 둔다.
  useEffect(() => {
    attachRef.current = attach
  }, [attach])

  // 재생이 실제로 시작되면 모든 카운터를 되돌린다. 상태 전환의 근거를
  // 추측이 아니라 playing 이벤트에 둔다.
  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    const onPlaying = () => {
      failuresRef.current = 0
      clearTimer()
      setPlaying(true)
      setShowPoster(false)
    }
    const onStop = () => setPlaying(false)

    video.addEventListener('playing', onPlaying)
    video.addEventListener('waiting', onStop)
    video.addEventListener('stalled', onStop)
    video.addEventListener('error', onStop)
    return () => {
      video.removeEventListener('playing', onPlaying)
      video.removeEventListener('waiting', onStop)
      video.removeEventListener('stalled', onStop)
      video.removeEventListener('error', onStop)
    }
  }, [])

  // 끊긴 상태가 길어질 때만 썸네일로 바꾼다. 그 전에는 마지막 프레임이
  // 남아 있어 잠깐의 끊김이 화면에 드러나지 않는다.
  useEffect(() => {
    if (playing) return
    const id = window.setTimeout(() => setShowPoster(true), THUMBNAIL_AFTER_MS)
    return () => window.clearTimeout(id)
  }, [playing])

  useEffect(() => {
    attach()
    return () => {
      clearTimer()
      hlsRef.current?.destroy()
      hlsRef.current = null
    }
  }, [attach])

  // 숨겨진 탭은 재시도하지 않는다. 보이지 않는 화면 때문에 요청이 나가면
  // CloudFront 를 붙인 뒤에는 그것이 그대로 요금이 된다.
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        if (!playing) attach()
      } else {
        clearTimer()
      }
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [attach, playing])

  return (
    <>
      <video
        ref={videoRef}
        className="room__video-img"
        poster={poster}
        autoPlay
        muted={muted}
        playsInline
      />
      {/* 썸네일은 실패 화면이 아니라 재연결 중 임시 화면이다. */}
      {showPoster && <img src={poster} alt="" className="room__video-img" />}
      {showPoster && live && src && <p className="room__reconnect">방송을 다시 연결하는 중...</p>}
    </>
  )
}

export default LivePlayer
