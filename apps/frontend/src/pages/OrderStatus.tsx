import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

import { ApiError } from '../services/api'
import { fetchOrder } from '../services/orderService'
import type { OrderStatus as Order } from '../types'
import '../styles/common.css'

/**
 * 주문 상태.
 *
 * 접수 직후에는 ACCEPTED 이고, 워커가 MySQL 에 기록하면 CONFIRMED 가 된다.
 * 그 전이를 보려면 폴링이 필요하다 — 이 값은 WebSocket 으로 푸시되지 않는다.
 *
 * 결제 화면은 없다. 결제 게이트웨이 연동이 프로젝트 범위 밖이다
 * (contracts.md 0).
 */
const POLL_MS = 2000
const MAX_POLLS = 15

function OrderStatusPage() {
  const { orderId } = useParams()
  const [order, setOrder] = useState<Order | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!orderId) return
    let polls = 0
    let timer: number | undefined

    const tick = () => {
      fetchOrder(orderId)
        .then((o) => {
          setOrder(o)
          // 확정되면 멈춘다. 계속 부르면 서버만 때린다.
          if (o.state === 'ACCEPTED' && polls++ < MAX_POLLS) {
            timer = window.setTimeout(tick, POLL_MS)
          }
        })
        .catch((e: ApiError) => setError(e.message))
    }

    tick()
    return () => clearTimeout(timer)
  }, [orderId])

  const label =
    order?.state === 'CONFIRMED'
      ? '주문이 확정되었습니다'
      : order?.state === 'CANCELLED'
        ? '주문이 취소되었습니다'
        : '주문을 처리하고 있습니다'

  return (
    <div className="phone-frame" style={{ padding: 24 }}>
      <h1 style={{ fontSize: 20 }}>주문 상태</h1>
      {error && <p>{error}</p>}
      {!order && !error && <p className="lobby-loading">조회 중...</p>}
      {order && (
        <>
          <p style={{ fontSize: 18, fontWeight: 600 }}>{label}</p>
          <dl style={{ fontSize: 14, lineHeight: 1.8 }}>
            <div>주문번호 {order.order_id}</div>
            <div>상품 {order.sku_id}</div>
            <div>수량 {order.qty}</div>
            <div>상태 {order.state}</div>
          </dl>
        </>
      )}
    </div>
  )
}

export default OrderStatusPage
