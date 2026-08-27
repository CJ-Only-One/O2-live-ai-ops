/**
 * 복구 상태 기계 검증.
 *
 * 첫 판이 초당 50건을 냈다. "이제 안 그런다" 를 말로 주장하지 않고 가짜
 * 시계로 시간을 돌려 **호출 횟수를 센다.**
 *
 *   npm test
 */

import assert from 'node:assert/strict'
import { beforeEach, describe, it } from 'node:test'

import {
  MAX_ATTACHES,
  MIN_ATTACH_MS,
  PROBE_JITTER_MS,
  PROBE_MS,
  STABLE_MS,
  STALL_TIMEOUT_MS,
  StreamRecoveryController,
  type Clock,
  type RecoveryDeps,
} from './streamRecovery.ts'

/** 가짜 시계. tick 으로 시간을 밀어 예약된 콜백을 실행한다. */
function fakeClock() {
  let now = 0
  let seq = 1
  const jobs = new Map<number, { at: number; fn: () => void }>()

  const clock: Clock = {
    now: () => now,
    setTimeout(fn, ms) {
      const id = seq++
      jobs.set(id, { at: now + ms, fn })
      return id
    },
    clearTimeout(id) {
      jobs.delete(id)
    },
  }

  /** ms 만큼 시간을 민다. 도중에 예약된 것도 실행한다 */
  async function tick(ms: number) {
    const target = now + ms
    for (;;) {
      const due = [...jobs.entries()]
        .filter(([, j]) => j.at <= target)
        .sort((a, b) => a[1].at - b[1].at)[0]
      if (!due) break
      const [id, job] = due
      jobs.delete(id)
      now = job.at
      job.fn()
      // probe 가 Promise 라 마이크로태스크를 흘려보낸다
      await Promise.resolve()
      await Promise.resolve()
    }
    now = target
  }

  return { clock, tick, pending: () => jobs.size }
}

function harness(opts: { alive?: boolean; visible?: boolean } = {}) {
  const { clock, tick, pending } = fakeClock()
  const counts = { attach: 0, destroy: 0, probe: 0 }
  let alive = opts.alive ?? false
  let visible = opts.visible ?? true

  const deps: RecoveryDeps = {
    clock,
    attach: () => {
      counts.attach += 1
    },
    destroy: () => {
      counts.destroy += 1
    },
    probe: async () => {
      counts.probe += 1
      return alive
    },
    isVisible: () => visible,
    random: () => 0.5,
  }

  const c = new StreamRecoveryController(deps)
  return {
    c,
    counts,
    tick,
    pending,
    setAlive: (v: boolean) => {
      alive = v
    },
    setVisible: (v: boolean) => {
      visible = v
    },
  }
}

describe('재부착', () => {
  let h: ReturnType<typeof harness>
  beforeEach(() => {
    h = harness()
  })

  it('첫 부착은 즉시 한 번', () => {
    h.c.update('/hls/x/index.m3u8', true)
    assert.equal(h.counts.attach, 1)
  })

  it('최소 간격보다 자주 붙지 않는다', async () => {
    h.c.update('/hls/x/index.m3u8', true)
    // 오류를 촘촘히 쏟아붓는다 — 첫 판이 여기서 폭주했다
    for (let i = 0; i < 50; i += 1) {
      h.c.onFatal()
      await h.tick(100)
    }
    // 5초 동안 5,000ms/100ms = 50회 오류가 났지만 재부착은 1회를 넘지 않는다
    assert.ok(h.counts.attach <= 2, `재부착 ${h.counts.attach}회`)
  })

  it('상한을 넘지 않고, 넘으면 인스턴스를 죽인다', async () => {
    h.c.update('/hls/x/index.m3u8', true)
    for (let i = 0; i < 40; i += 1) {
      h.c.onFatal()
      await h.tick(MIN_ATTACH_MS)
    }
    assert.equal(h.counts.attach, MAX_ATTACHES)
    assert.equal(h.c.getState(), 'open')
    assert.ok(h.counts.destroy >= 1, '회로를 열 때 destroy 가 불려야 한다')
  })
})

describe('1분간 요청량', () => {
  it('계속 실패해도 재부착이 상한 안에 묶인다', async () => {
    const h = harness()
    h.c.update('/hls/x/index.m3u8', true)
    for (let i = 0; i < 600; i += 1) {
      h.c.onFatal()
      await h.tick(100)
    }
    // 60초. 최소 간격 5초면 이론상 최대 12회이고 그것이 상한과 같다
    assert.ok(h.counts.attach <= MAX_ATTACHES, `재부착 ${h.counts.attach}회`)
  })

  it('회로가 열린 뒤에는 30초당 탐색 1건뿐', async () => {
    const h = harness()
    h.c.update('/hls/x/index.m3u8', true)
    for (let i = 0; i < 40; i += 1) {
      h.c.onFatal()
      await h.tick(MIN_ATTACH_MS)
    }
    assert.equal(h.c.getState(), 'open')

    const before = h.counts.probe
    await h.tick(5 * (PROBE_MS + PROBE_JITTER_MS))
    const probes = h.counts.probe - before
    assert.ok(probes >= 4 && probes <= 6, `탐색 ${probes}건`)
  })
})

describe('숨겨진 탭', () => {
  it('숨겨지면 아무 요청도 예약하지 않는다', async () => {
    const h = harness()
    h.c.update('/hls/x/index.m3u8', true)
    h.setVisible(false)
    h.c.onVisibilityChange()

    const before = h.counts.attach
    h.c.onFatal()
    await h.tick(60000)
    assert.equal(h.counts.attach, before, '숨긴 뒤 재부착이 없어야 한다')
  })

  it('다시 보이면 붙는다', async () => {
    const h = harness()
    h.c.update('/hls/x/index.m3u8', true)
    h.setVisible(false)
    h.c.onVisibilityChange()
    h.c.onFatal()
    await h.tick(60000)

    h.setVisible(true)
    h.c.onVisibilityChange()
    await h.tick(MIN_ATTACH_MS)
    assert.ok(h.counts.attach >= 2)
  })
})

describe('회복', () => {
  it('탐색이 성공하면 다시 붙는다', async () => {
    const h = harness()
    h.c.update('/hls/x/index.m3u8', true)
    for (let i = 0; i < 40; i += 1) {
      h.c.onFatal()
      await h.tick(MIN_ATTACH_MS)
    }
    assert.equal(h.c.getState(), 'open')

    h.setAlive(true)
    const before = h.counts.attach
    await h.tick(PROBE_MS + PROBE_JITTER_MS)
    assert.ok(h.counts.attach > before, '살아나면 재부착해야 한다')
  })

  it('재생이 유지돼야 카운터가 풀린다', async () => {
    const h = harness()
    h.c.update('/hls/x/index.m3u8', true)
    h.c.onFatal()
    await h.tick(MIN_ATTACH_MS)

    h.c.onPlaying()
    await h.tick(STABLE_MS - 1000)
    assert.ok(h.c.getAttachCount() > 0, '아직 유지 시간 전이라 안 풀린다')

    await h.tick(2000)
    assert.equal(h.c.getAttachCount(), 0)
  })

  it('붙었다 끊기기를 반복해도 폭주하지 않는다', async () => {
    const h = harness()
    h.c.update('/hls/x/index.m3u8', true)

    // 첫 판의 폭주 시나리오: playing 이 나오면 카운터가 초기화되고
    // 곧바로 끊긴다. 이것이 무한 즉시 재시도를 만들었다.
    for (let i = 0; i < 30; i += 1) {
      h.c.onPlaying()
      await h.tick(500)
      h.c.onFatal()
      await h.tick(500)
    }
    // 30초 동안. 최소 간격 5초면 6회가 상한이다
    assert.ok(h.counts.attach <= 7, `재부착 ${h.counts.attach}회`)
  })
})

/**
 * 폭주의 반대편이다. fatal 이 오지 않는 정지 — m3u8 이 200 을 주면서 내용만
 * 멈춘 경우 — 에서 재부착이 0회가 되어 조용히 영영 멈추는 것을 막는다.
 */
describe('조용한 정지', () => {
  const SRC = '/hls/x/index.m3u8'

  it('짧은 버퍼링에는 재부착하지 않는다', async () => {
    const h = harness()
    h.c.update(SRC, true)
    h.c.onStalled()
    await h.tick(STALL_TIMEOUT_MS - 1000)
    assert.equal(h.counts.attach, 1, '유예 안에서는 그대로 둔다')
  })

  it('정지가 이어지면 재부착한다 — fatal 이 없어도', async () => {
    const h = harness()
    h.c.update(SRC, true)
    h.c.onStalled()
    await h.tick(STALL_TIMEOUT_MS)
    assert.equal(h.counts.attach, 2)
  })

  it('재생 위치가 흐르면 재부착하지 않는다 — playing 이 다시 안 와도', async () => {
    // 라이브 엣지에서 세그먼트가 늦으면 stalled 가 뜨지만 재생은 버퍼로
    // 이어진다. 비디오가 멈춘 적이 없어 playing 은 다시 오지 않으므로,
    // 진행 신호가 없으면 멀쩡한 재생을 8초마다 끊게 된다.
    const h = harness()
    h.c.update(SRC, true)
    h.c.onPlaying()
    h.c.onStalled()
    await h.tick(STALL_TIMEOUT_MS - 2000)
    h.c.onProgress()
    await h.tick(60000)
    assert.equal(h.counts.attach, 1, '재생이 흐르면 재부착이 없어야 한다')
  })

  it('정지 중 재생이 돌아오면 예약이 취소된다', async () => {
    const h = harness()
    h.c.update(SRC, true)
    h.c.onStalled()
    await h.tick(STALL_TIMEOUT_MS - 2000)
    h.c.onPlaying()
    await h.tick(60000)
    assert.equal(h.counts.attach, 1, '회복했으면 재부착이 없어야 한다')
  })

  it('stalled 가 반복돼도 감시가 뒤로 밀리지 않는다', async () => {
    const h = harness()
    h.c.update(SRC, true)
    // 이벤트마다 타이머를 다시 잡으면 발동 시각이 계속 미뤄져 영영 안 붙는다
    for (let i = 0; i < 10; i += 1) {
      h.c.onStalled()
      await h.tick(1000)
    }
    assert.ok(h.counts.attach >= 2, `10초 정지에도 재부착 ${h.counts.attach}회`)
  })

  it('fatal 이 먼저 오면 정지 타이머가 남지 않는다', async () => {
    const h = harness()
    h.c.update(SRC, true)
    h.c.onStalled()
    await h.tick(2000)
    h.c.onFatal()
    // 재부착 타이머 하나뿐이어야 한다. 정지 타이머가 살아 있으면 둘이다
    assert.equal(h.pending(), 1)
  })

  it('정지가 계속되면 회로까지 도달하고 감시는 남지 않는다', async () => {
    const h = harness()
    h.c.update(SRC, true)
    for (let i = 0; i < 200 && h.c.getState() !== 'open'; i += 1) {
      h.c.onStalled()
      await h.tick(1000)
    }
    assert.equal(h.c.getState(), 'open')
    assert.equal(h.counts.attach, MAX_ATTACHES)
    assert.equal(h.pending(), 1, '회로가 열리면 저속 탐색 하나만 남는다')
  })

  it('숨김 중에는 정지해도 붙지 않고, 돌아오면 붙는다', async () => {
    const h = harness()
    h.c.update(SRC, true)
    h.setVisible(false)
    h.c.onVisibilityChange()

    h.c.onStalled()
    await h.tick(60000)
    assert.equal(h.counts.attach, 1, '숨김 중에는 복구하지 않는다')

    h.setVisible(true)
    h.c.onVisibilityChange()
    await h.tick(MIN_ATTACH_MS)
    assert.equal(h.counts.attach, 2, '돌아오면 복구한다')
  })
})

describe('방송 전환', () => {
  it('src 가 바뀌면 회로가 초기화된다', async () => {
    const h = harness()
    h.c.update('/hls/a/index.m3u8', true)
    for (let i = 0; i < 40; i += 1) {
      h.c.onFatal()
      await h.tick(MIN_ATTACH_MS)
    }
    assert.equal(h.c.getState(), 'open')

    h.c.update('/hls/b/index.m3u8', true)
    assert.notEqual(h.c.getState(), 'open')
    assert.equal(h.c.getAttachCount(), 1)
  })

  it('방송이 아니면 붙지 않고 죽인다', () => {
    const h = harness()
    h.c.update('/hls/x/index.m3u8', false)
    assert.equal(h.counts.attach, 0)
    assert.equal(h.c.getState(), 'idle')
    assert.ok(h.counts.destroy >= 1)
  })
})
