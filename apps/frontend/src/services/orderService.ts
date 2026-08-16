import { api, sessionKey } from './api'
import type { OrderAccepted, OrderStatus } from '../types'

/**
 * 주문 접수 (contracts.md 2.2).
 *
 * Idempotency-Key 를 클라이언트가 만든다. 서버가 만들면 재시도할 때 같은
 * 키를 다시 보낼 수 없어 멱등성이 성립하지 않는다. 그래서 재시도 시에는
 * **같은 키를 다시 써야 한다** — 호출부가 키를 들고 있어야 하는 이유다.
 *
 * 응답은 202 다. 이 시점에 확정된 것은 재고 차감까지이고 저장은 워커가 한다.
 */
export function createOrder(
  broadcastId: string,
  skuId: string,
  qty: number,
  idempotencyKey: string,
): Promise<OrderAccepted> {
  return api.post<OrderAccepted>(
    '/orders',
    { broadcast_id: broadcastId, sku_id: skuId, qty },
    { 'Idempotency-Key': idempotencyKey, 'x-session-key': sessionKey() },
  )
}

/** 주문 상태 조회 (contracts.md 2.3). */
export function fetchOrder(orderId: string): Promise<OrderStatus> {
  return api.get<OrderStatus>(`/orders/${orderId}`)
}
