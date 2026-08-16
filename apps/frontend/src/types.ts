/**
 * 서버 응답 형태. docs/contracts.md 를 따른다.
 *
 * 이 파일이 계약과 어긋나면 화면이 조용히 빈 값을 그린다. 필드 이름을
 * 바꾸고 싶으면 코드가 아니라 계약 문서를 먼저 고친다.
 */

/** contracts.md 2.1 */
export type BroadcastState = 'SCHEDULED' | 'LIVE' | 'ENDED'
export type ProductState = 'PENDING' | 'ON_SALE' | 'SOLD_OUT'

export interface Product {
  // 계약상 문자열이다. 숫자로 다루면 앞자리 0 이 사라진다.
  sku_id: string
  name: string
  price: number
  sale_price: number

  /**
   * 표시용이며 주문 가부의 근거가 아니다. 판정은 항상 서버의 재고 차감
   * 결과를 따른다 — "1개 남음" 이 몇 초 더 보이는 것은 정상 동작이고,
   * 이 불일치는 없애려 하지 말고 문구로 흡수한다 (contracts.md 2.1).
   */
  stock_display: number
  state: ProductState
}

export interface Broadcast {
  broadcast_id: string
  state: BroadcastState
  started_at: string | null
  hls_url: string | null
  products: Product[]
}

/** contracts.md 2.2 · 2.3 */
export type OrderState = 'ACCEPTED' | 'CONFIRMED' | 'CANCELLED'

export interface OrderAccepted {
  order_id: string
  state: OrderState
}

export interface OrderStatus {
  order_id: string
  state: OrderState
  sku_id: string
  qty: number
}

/** contracts.md 1.3 — code 로 분기하고 message 로 분기하지 않는다. */
export type ErrorCode =
  | 'SOLD_OUT'
  | 'NOT_STARTED'
  | 'RATE_LIMITED'
  | 'INVALID_REQUEST'
  | 'INTERNAL_ERROR'

export interface ApiErrorBody {
  error: { code: ErrorCode; message: string }
}

/** contracts.md 3.3 — 서버가 보내는 프레임의 items 원소 */
export interface ChatItem {
  user: string
  nick: string
  msg: string
  ts: number
}
