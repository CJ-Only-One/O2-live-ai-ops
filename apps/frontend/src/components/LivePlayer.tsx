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
 * **이 파일은 React 와 video 이벤트를 잇는 일만 한다.** 재시도·백오프·
 * 회로 차단은 `services/streamRecovery.ts` 가 하고, 그쪽은 DOM 을 모르므로
 * 가짜 시계로 요청 횟수를 세어 검증한다. 첫 판은 이 로직을 컴포넌트 안에
 * 두었고, 그래서 "폭주하지 않는다" 를 말로만 주장할 수밖에 없었다.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import {
  probeManifest,
  StreamRecoveryController,
  type RecoveryState,
} from '../services/streamRecovery'

/** 이 시간 동안 재생이 안 돌아오면 썸네일로 바꾼다. 그 전에는 마지막
 *  프레임을 유지한다 — 2초짜리 끊김에 화면이 깜빡이면 더 나빠 보인다. */
const THUMBNAIL_AFTER_MS = 3000

interface Props {
  /** contracts.md 2.1 의 hls_url. 없으면 재생할 것이 없다 */
  src: string | null
  /** 재생이 안 될 때 대신 보여줄 이미지 */
  poster: string
  muted: boolean
  /**
   * 방송이 진행 중인가.
   *
   * 진입 시 1회 조회한 스냅샷에서 오므로 낡을 수 있다. 영상 복구 판정에는
   * 쓰지 않는다 — DB 가 LIVE 여도 송출은 끊겨 있을 수 있다. 그 판정은
   * 매니페스트를 직접 확인해서 한다.
   */
  live: boolean
  /** 회로가 열릴 때 부모가 스냅샷을 다시 받아 live 를 갱신하게 한다 */
  onCircuitOpen?: () => void
}

function LivePlayer({ src, poster, muted, live, onCircuitOpen }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const hlsRef = useRef<{ destroy: () => void } | null>(null)
  const generationRef = useRef(0)
  const controllerRef = useRef<StreamRecoveryController | null>(null)
  const srcRef = useRef<string | null>(null)

  const [state, setState] = useState<RecoveryState>('idle')
  const [showPoster, setShowPoster] = useState(true)

  /** 현재 인스턴스를 완전히 해제한다. 이후 요청이 나가면 안 된다 */
  const destroyPlayer = useCallback(() => {
    generationRef.current += 1
    hlsRef.current?.destroy()
    hlsRef.current = null
    const video = videoRef.current
    if (video && video.src) {
      video.removeAttribute('src')
      video.load()
    }
  }, [])

  const attachPlayer = useCallback(() => {
    const video = videoRef.current
    const url = srcRef.current
    if (!video || !url) return

    destroyPlayer()

    // 사파리·iOS. 네이티브가 세그먼트 관리와 재시도까지 한다.
    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = url
      void video.play().catch(() => controllerRef.current?.onFatal())
      return
    }

    generationRef.current += 1
    const generation = generationRef.current

    // 실패를 삼키면 안 된다. 청크가 404 나면 (배포로 해시가 바뀐 뒤 낡은
    // index.html 을 쓰는 브라우저에서 그렇다) 컨트롤러는 붙은 줄 알고 있고,
    // 재부착도 안내 문구도 없이 화면이 그대로 멈춘다. 요청이 0건이라
    // 폭주보다 알아채기 어렵다.
    const fail = () => controllerRef.current?.onFatal()

    import('hls.js').then(({ default: Hls }) => {
      if (generation !== generationRef.current) return
      // 재생할 방법이 아예 없는 브라우저다. 여기서도 알려야 회로가 열려
      // 다시 시도 버튼이라도 뜬다.
      if (!Hls.isSupported()) {
        fail()
        return
      }

      const hls = new Hls({
        // 기본값(3)을 쓴다. 2로 낮추면 지연이 줄지만 버퍼가 세그먼트 2개뿐이라
        // 세그먼트 길이가 들쭉날쭉할 때 금방 마르고, 그 끊김이 재시도를 부른다.
        liveSyncDurationCount: 3,
        // 기본값은 관대하다. 재부착은 컨트롤러가 관리하므로 여기서는 빨리
        // 넘겨 총 요청량을 묶는다.
        manifestLoadingMaxRetry: 2,
        levelLoadingMaxRetry: 2,
        fragLoadingMaxRetry: 3,
      })
      hlsRef.current = hls
      hls.loadSource(url)
      hls.attachMedia(video)

      hls.on(Hls.Events.ERROR, (_e, data) => {
        if (data.fatal) fail()
      })
    }).catch(fail)
  }, [destroyPlayer])

  // 컨트롤러는 한 번만 만든다. 주소·방송 상태는 update 로 알린다.
  useEffect(() => {
    const controller = new StreamRecoveryController({
      clock: {
        now: () => Date.now(),
        setTimeout: (fn, ms) => window.setTimeout(fn, ms),
        clearTimeout: (id) => window.clearTimeout(id),
      },
      attach: attachPlayer,
      destroy: destroyPlayer,
      probe: () => (srcRef.current ? probeManifest(srcRef.current) : Promise.resolve(false)),
      isVisible: () => document.visibilityState === 'visible',
      onState: (next) => {
        setState(next)
        if (next === 'open') onCircuitOpen?.()
      },
    })
    controllerRef.current = controller

    const onVisible = () => controller.onVisibilityChange()
    document.addEventListener('visibilitychange', onVisible)

    return () => {
      document.removeEventListener('visibilitychange', onVisible)
      controller.dispose()
      controllerRef.current = null
    }
  }, [attachPlayer, destroyPlayer, onCircuitOpen])

  useEffect(() => {
    srcRef.current = src
    controllerRef.current?.update(src, live)
  }, [src, live])

  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    const onPlaying = () => {
      controllerRef.current?.onPlaying()
      setShowPoster(false)
    }
    const onStop = () => controllerRef.current?.onStalled()
    // 재생 위치가 흐르면 끊긴 것이 아니다. `stalled` 는 3초간 데이터가 안
    // 들어오면 뜨지만 그동안 재생은 버퍼로 이어지고, 비디오가 멈춘 적이
    // 없으니 `playing` 은 다시 오지 않는다. 이 신호가 없으면 감시 타이머가
    // 안 풀려 멀쩡한 플레이어를 8초마다 재부착한다.
    const onProgress = () => controllerRef.current?.onProgress()

    video.addEventListener('playing', onPlaying)
    video.addEventListener('waiting', onStop)
    video.addEventListener('stalled', onStop)
    video.addEventListener('timeupdate', onProgress)
    return () => {
      video.removeEventListener('playing', onPlaying)
      video.removeEventListener('waiting', onStop)
      video.removeEventListener('stalled', onStop)
      video.removeEventListener('timeupdate', onProgress)
    }
  }, [])

  // 끊긴 상태가 길어질 때만 썸네일로 바꾼다.
  useEffect(() => {
    if (state === 'attached') return
    const id = window.setTimeout(() => setShowPoster(true), THUMBNAIL_AFTER_MS)
    return () => window.clearTimeout(id)
  }, [state])

  const retry = useCallback(() => controllerRef.current?.retryNow(), [])

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
      {/* 썸네일은 실패 화면이 아니라 재연결 중 임시 화면이다.
          video 와 클래스를 나눠 쓰되 흐림 처리는 이쪽에만 건다. 같은 클래스에
          걸면 방송 영상까지 흐려진다. */}
      {showPoster && <img src={poster} alt="" className="room__video-img room__video-poster" />}
      {showPoster && live && src && state === 'recovering' && (
        <p className="room__reconnect">방송을 다시 연결하는 중...</p>
      )}
      {showPoster && live && src && state === 'open' && (
        <button className="room__reconnect room__reconnect--button" onClick={retry}>
          연결이 지연되고 있습니다 · 지금 다시 시도
        </button>
      )}
    </>
  )
}

export default LivePlayer
