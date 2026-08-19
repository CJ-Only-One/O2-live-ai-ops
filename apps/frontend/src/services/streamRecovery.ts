/**
 * HLS 재생 복구 상태 기계.
 *
 * **React 와 DOM 을 모르는 순수 로직이다.** 시계·탐색·부착·해제를 주입받아
 * 가짜 구현으로 테스트할 수 있다. 이렇게 나눈 이유는 하나다 — 첫 판이
 * 요청 폭주를 만들었고, "이제 안 그런다" 를 말이 아니라 숫자로 증명해야
 * 한다. `.tsx` 안에 두면 Node 에 DOM 이 없어 검증이 막힌다.
 *
 * ## 상태
 *
 *   idle       붙지 않음 (방송 전, src 없음)
 *   attached   부착함. 재생을 기다리거나 재생 중
 *   recovering 끊김. 최소 간격으로 재부착 (상한 있음)
 *   open       상한 도달. 인스턴스를 죽이고 저속 탐색만
 *
 * ## 나가는 요청량
 *
 *   attached    재생에 필요한 만큼 (플레이어가 냄)
 *   recovering  MIN_ATTACH_MS 당 재부착 1회, 최대 MAX_ATTACHES 회
 *   open        PROBE_MS ± 지터 당 탐색 1건
 *   숨김        재부착·탐색 예약 0건. 재생 중이면 플레이어 요청은 계속된다
 *
 * `MAX_ATTACHES` 는 **재부착 횟수**다. HTTP 요청 수가 아니다 — 재부착
 * 하나가 매니페스트·플레이리스트·세그먼트 요청 여러 건을 낸다.
 *
 * ## 숨겨진 탭에서는 복구하지 않는다
 *
 * 정상 재생은 그대로 두고 (탭을 내려놓고 소리만 듣는 사용을 깨지 않는다)
 * **복구는 탭이 돌아온 뒤에 한다.** 절충이 아니라 제약이다 — 브라우저가
 * 백그라운드 탭의 타이머를 분 단위로 클램프하므로 숨김 중에 8초든 30초든
 * 약속할 수 없다. 게다가 숨김 중 방송이 끊기면 지킬 오디오도 이미 없다.
 */

/** 재부착 최소 간격. 어떤 경로로 불려도 이보다 자주 붙지 않는다. */
export const MIN_ATTACH_MS = 5000

/** 재부착 상한. 넘으면 회로를 열고 저속 탐색으로 내려간다. */
export const MAX_ATTACHES = 12

/** 회로가 열린 뒤 생존 확인 주기. */
export const PROBE_MS = 30000

/** 탐색 지터. 여러 클라이언트가 정각에 몰리는 것을 막는다. */
export const PROBE_JITTER_MS = 5000

/** 이만큼 연속 재생돼야 회복으로 인정한다. 재생 이벤트 하나로 인정하면
 *  붙었다 끊기는 상태에서 카운터가 매번 초기화되어 폭주한다 — 첫 판의
 *  실제 원인이다. */
export const STABLE_MS = 15000

/**
 * 정지가 이만큼 이어지면 재부착한다.
 *
 * `waiting` 은 **버퍼가 이미 마른 뒤에** 뜬다. 그러니 이 값은 "버퍼가 다시
 * 찰 시간" 이 아니라 "일시적 딸꾹질이 스스로 회복할 시간" 이다 — 세그먼트
 * 2초(키프레임 때문에 최대 3.7초) × 2회면 충분하다.
 *
 * 이 감시가 없으면 **조용히 영영 멈춘다.** m3u8 이 200 을 반환하면서 내용만
 * 갱신을 멈추면 (송출이 끊겨도 muxer 가 마지막 플레이리스트를 붙들고 있는
 * 동안) hls.js 는 오류로 보지 않아 fatal 을 내지 않는다. 그러면 재부착도
 * 탐색도 예약되지 않고 화면에는 "다시 연결하는 중" 만 남는다 — 실제로는
 * 아무것도 하지 않으면서.
 */
export const STALL_TIMEOUT_MS = 8000

export type RecoveryState = 'idle' | 'attached' | 'recovering' | 'open'

export interface Clock {
  now(): number
  setTimeout(fn: () => void, ms: number): number
  clearTimeout(id: number): void
}

export interface RecoveryDeps {
  clock: Clock
  /** 플레이어를 붙인다. 실제 요청은 이 안에서 난다 */
  attach(): void
  /** 붙어 있는 플레이어를 완전히 해제한다. 이후 요청이 나가면 안 된다 */
  destroy(): void
  /** 매니페스트가 살아 있는지 확인한다. 성공하면 true */
  probe(): Promise<boolean>
  /** 탭이 보이는가 */
  isVisible(): boolean
  /** 상태가 바뀔 때 알린다 (화면 표시용) */
  onState?(state: RecoveryState): void
  /** 0 이상 1 미만. 테스트에서 고정하기 위해 주입한다 */
  random?(): number
}

export class StreamRecoveryController {
  private state: RecoveryState = 'idle'
  private attaches = 0
  private lastAttachAt = 0
  private timer: number | null = null
  private stableTimer: number | null = null
  // 재부착·탐색용 timer 와 섞지 않는다. 한쪽을 지울 때 다른 쪽이 함께
  // 지워지면 감시가 조용히 사라진다.
  private stallTimer: number | null = null
  private live = false
  private src: string | null = null
  private disposed = false

  private readonly deps: RecoveryDeps

  // 파라미터 프로퍼티를 쓰지 않는다. tsconfig 의 erasableSyntaxOnly 가
  // 타입만 지워서 실행 가능한 문법만 허용한다.
  constructor(deps: RecoveryDeps) {
    this.deps = deps
  }

  getState(): RecoveryState {
    return this.state
  }

  /** 테스트와 화면이 함께 보는 값. 재부착 횟수다 */
  getAttachCount(): number {
    return this.attaches
  }

  private setState(next: RecoveryState) {
    if (this.state === next) return
    this.state = next
    this.deps.onState?.(next)
  }

  private clearTimer() {
    if (this.timer !== null) {
      this.deps.clock.clearTimeout(this.timer)
      this.timer = null
    }
  }

  private clearStable() {
    if (this.stableTimer !== null) {
      this.deps.clock.clearTimeout(this.stableTimer)
      this.stableTimer = null
    }
  }

  private clearStall() {
    if (this.stallTimer !== null) {
      this.deps.clock.clearTimeout(this.stallTimer)
      this.stallTimer = null
    }
  }

  /**
   * 방송과 주소를 알린다. src 가 바뀌면 회로를 초기화한다 — 이전 방송에서
   * 상한에 걸린 상태가 새 방송까지 따라가면 영영 못 붙는다.
   */
  update(src: string | null, live: boolean) {
    const srcChanged = src !== this.src
    this.src = src
    this.live = live

    if (srcChanged) {
      this.attaches = 0
      this.lastAttachAt = 0
      this.clearTimer()
      this.clearStable()
      this.clearStall()
      this.deps.destroy()
      this.setState('idle')
    }

    if (!src || !live) {
      this.clearTimer()
      this.clearStable()
      this.clearStall()
      this.deps.destroy()
      this.setState('idle')
      return
    }

    if (this.state === 'idle') this.tryAttach()
  }

  /** 실제로 재생이 시작됐다. 유지되면 그때 카운터를 푼다 */
  onPlaying() {
    this.clearTimer()
    this.clearStall()
    this.setState('attached')
    this.clearStable()
    this.stableTimer = this.deps.clock.setTimeout(() => {
      this.stableTimer = null
      this.attaches = 0
    }, STABLE_MS)
  }

  /**
   * 재생이 멈췄다 (버퍼링·오류). 아직 회복 시도 단계다.
   *
   * `waiting` 은 짧은 버퍼링에도 뜨므로 이벤트마다 재부착하면 안 된다.
   * 감시 타이머만 걸고, 그 안에 `onPlaying` 이 오면 취소한다.
   */
  onStalled() {
    this.clearStable()
    if (this.state === 'open' || this.state === 'idle') return
    this.setState('recovering')
    this.scheduleStallWatch()
  }

  /** 플레이어가 회복 불가로 판정했다 */
  onFatal() {
    this.clearStable()
    this.clearStall()
    if (this.state === 'open') return
    this.setState('recovering')
    this.scheduleAttach()
  }

  /** 탭 가시성이 바뀌었다 */
  onVisibilityChange() {
    if (this.disposed) return

    if (!this.deps.isVisible()) {
      // 보이지 않으면 복구를 예약하지 않는다. 재생 중인 플레이어는 그대로
      // 두므로 세그먼트 요청은 계속 나간다 — 그것까지 0 은 아니다.
      this.clearTimer()
      this.clearStall()
      return
    }

    if (this.state === 'open') {
      this.scheduleProbe(0)
      return
    }
    if (this.state === 'recovering') this.scheduleAttach()
  }

  /** 사용자가 직접 눌렀다. 대기 없이 지금 확인한다 */
  retryNow() {
    this.attaches = 0
    this.lastAttachAt = 0
    this.clearTimer()
    this.clearStall()
    if (this.state === 'open') {
      this.scheduleProbe(0)
      return
    }
    this.tryAttach()
  }

  dispose() {
    this.disposed = true
    this.clearTimer()
    this.clearStable()
    this.clearStall()
    this.deps.destroy()
    this.setState('idle')
  }

  // ── 내부 ──────────────────────────────────────────────────

  /**
   * 정지가 이어지는지 지켜본다.
   *
   * 이미 걸려 있으면 건드리지 않는다. `waiting`/`stalled` 는 연달아 뜨는데
   * 그때마다 다시 잡으면 감시 시각이 계속 뒤로 밀려 영영 발동하지 않는다 —
   * `scheduleAttach` 의 기아 문제와 같은 모양이다.
   */
  private scheduleStallWatch() {
    if (this.stallTimer !== null) return
    if (!this.deps.isVisible()) return

    this.stallTimer = this.deps.clock.setTimeout(() => {
      this.stallTimer = null
      // 그 사이 재생이 돌아왔거나 회로가 열렸으면 할 일이 없다.
      if (this.disposed || this.state !== 'recovering') return
      this.scheduleAttach()
    }, STALL_TIMEOUT_MS)
  }

  private scheduleAttach() {
    // 타이머가 이미 있으면 건드리지 않는다. 반복 오류가 타이머를 계속
    // 다시 잡으면 재부착이 영원히 미뤄진다 (기아 상태).
    if (this.timer !== null) return
    if (!this.deps.isVisible()) return

    const wait = Math.max(0, MIN_ATTACH_MS - (this.deps.clock.now() - this.lastAttachAt))
    this.timer = this.deps.clock.setTimeout(() => {
      this.timer = null
      this.tryAttach()
    }, wait)
  }

  private tryAttach() {
    if (this.disposed || !this.src || !this.live) return
    if (!this.deps.isVisible()) return

    if (this.attaches >= MAX_ATTACHES) {
      this.openCircuit()
      return
    }

    const since = this.deps.clock.now() - this.lastAttachAt
    if (this.lastAttachAt !== 0 && since < MIN_ATTACH_MS) {
      this.scheduleAttach()
      return
    }

    this.attaches += 1
    this.lastAttachAt = this.deps.clock.now()
    this.setState('attached')
    this.deps.attach()
  }

  /**
   * 회로를 연다. **인스턴스를 반드시 죽인다** — 상태 표시만 바꾸고 살려두면
   * 플레이어가 계속 요청을 낸다. 첫 판이 그렇게 폭주했다.
   */
  private openCircuit() {
    this.clearTimer()
    this.clearStable()
    // 여기서 안 지우면 회로를 열어놓고도 감시가 나중에 터져 tryAttach 로
    // 들어간다. 저속 탐색만 남기려는 상태 자체가 무너진다.
    this.clearStall()
    this.deps.destroy()
    this.setState('open')
    this.scheduleProbe()
  }

  private scheduleProbe(delay?: number) {
    if (this.timer !== null) return
    if (!this.deps.isVisible()) return

    const rnd = this.deps.random?.() ?? Math.random()
    const wait = delay ?? PROBE_MS + Math.floor(rnd * PROBE_JITTER_MS)

    this.timer = this.deps.clock.setTimeout(() => {
      this.timer = null
      void this.runProbe()
    }, wait)
  }

  private async runProbe() {
    if (this.disposed || this.state !== 'open') return

    let alive = false
    try {
      alive = await this.deps.probe()
    } catch {
      alive = false
    }

    if (this.disposed || this.state !== 'open') return

    if (alive) {
      // 살아 있으면 카운터를 풀고 다시 붙는다. 재생이 실제로 유지되는지는
      // onPlaying 이 판정한다 — 응답 200 을 회복으로 치면 안 된다.
      this.attaches = 0
      this.lastAttachAt = 0
      this.tryAttach()
      return
    }

    this.scheduleProbe()
  }
}

/** 매니페스트가 살아 있는지 본다. 200 이면서 본문이 HLS 여야 한다. */
export async function probeManifest(url: string): Promise<boolean> {
  const res = await fetch(url, { cache: 'no-store' })
  if (!res.ok) return false
  const text = await res.text()
  return text.trimStart().startsWith('#EXTM3U')
}
