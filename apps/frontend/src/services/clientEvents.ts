/**
 * 클라이언트 행동 수집 (contracts.md 2.5).
 *
 * 브라우저가 Kinesis 에 직접 쓰지 않는다 — 자격증명이 번들에 들어가기 때문이다.
 * api 의 수집 엔드포인트로 보내고, 거기서 `client.action` 이 되어 stream-client
 * 로 간다.
 *
 * **화면 동작에 끼어들지 않는다.** 실패를 삼키고 응답도 읽지 않는다.
 * 계측이 구매를 막는 것은 언제나 손해다.
 */

import { BASE, sessionKey } from './api'

/** SDK schemas.py 의 CLIENT_ACTION. 여기 없는 값을 보내면 서버가 400 이다. */
export type ClientAction =
  | 'LIVE_ENTER'
  | 'LIVE_LEAVE'
  | 'COUPON_BUTTON_CLICK'
  | 'CHECKOUT_CLICK'

export interface ClientEvent {
  action: ClientAction
  /** sku_id 처럼 이 행동이 가리키는 대상. 자유 문자열이 아니다. */
  target_id?: string
}

/**
 * `keepalive` 는 이탈 이벤트에만 쓴다. 페이지가 사라지는 중에도 요청이 살아남는
 * 유일한 방법이다.
 *
 * `navigator.sendBeacon` 을 쓰지 않는 이유는 헤더를 붙일 수 없어서다 —
 * `x-session-key` 가 빠지면 그 이벤트만 `user_key` 없이 들어가, 진입은 있는데
 * 이탈은 누구 것인지 모르는 상태가 된다.
 */
export function track(
  broadcastId: string | undefined,
  events: ClientEvent[],
  keepalive = false,
): void {
  if (!broadcastId || events.length === 0) return

  void fetch(`${BASE}/broadcasts/${broadcastId}/events`, {
    method: 'POST',
    keepalive,
    headers: { 'Content-Type': 'application/json', 'x-session-key': sessionKey() },
    body: JSON.stringify({ events }),
  }).catch(() => {
    // 수집 실패는 화면에 알리지 않는다. 사용자가 할 수 있는 일이 없다.
  })
}
