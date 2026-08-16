import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'

import ChatPanel from '../components/ChatPanel'
import LiveProductCard from '../components/LiveProductCard'
import { ApiError } from '../services/api'
import { fetchBroadcast } from '../services/broadcastService'
import { createOrder } from '../services/orderService'
import { useChat } from '../services/useChat'
import type { Broadcast, Product } from '../types'
import '../styles/common.css'
import './LiveRoom.css'

type OrderPhase =
  | { kind: 'idle' }
  | { kind: 'sending' }
  | { kind: 'accepted'; orderId: string }
  | { kind: 'failed'; message: string }

function LiveRoom() {
  const { broadcastId } = useParams()
  const [broadcast, setBroadcast] = useState<Broadcast | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [muted, setMuted] = useState(true)
  const [order, setOrder] = useState<OrderPhase>({ kind: 'idle' })

  const { messages, connected, send } = useChat(broadcastId)

  /**
   * 재시도는 같은 멱등키를 다시 보내야 한다. 서버가 만들어주지 않으므로
   * 여기서 상품별로 하나씩 들고 있는다 (contracts.md 1.2).
   */
  const idemKeys = useRef(new Map<string, string>())

  const load = useCallback(() => {
    if (!broadcastId) return
    setLoadError(null)
    fetchBroadcast(broadcastId)
      .then(setBroadcast)
      .catch((e: ApiError) => setLoadError(e.message))
  }, [broadcastId])

  // 진입 시 1회 조회. 이후 변화는 WebSocket 으로 온다 — 폴링하지 않는다.
  useEffect(load, [load])

  // 끊겼다 다시 붙으면 스냅샷을 다시 받는다. 끊긴 동안의 변경은 푸시로
  // 오지 않았기 때문이다 (contracts.md 3.6).
  const wasConnected = useRef(false)
  useEffect(() => {
    if (connected && wasConnected.current) load()
    wasConnected.current = connected
  }, [connected, load])

  function buy(product: Product) {
    if (!broadcastId || order.kind === 'sending') return

    let key = idemKeys.current.get(product.sku_id)
    if (!key) {
      key = crypto.randomUUID()
      idemKeys.current.set(product.sku_id, key)
    }

    setOrder({ kind: 'sending' })
    createOrder(broadcastId, product.sku_id, 1, key)
      .then((res) => setOrder({ kind: 'accepted', orderId: res.order_id }))
      .catch((e: ApiError) => {
        // code 로 분기한다. message 는 예고 없이 바뀐다 (contracts.md 1.3).
        const text =
          e.code === 'SOLD_OUT'
            ? '주문 처리 중 품절되었습니다'
            : e.code === 'RATE_LIMITED'
              ? '잠시 후 다시 시도해 주세요'
              : '주문을 접수하지 못했습니다'
        setOrder({ kind: 'failed', message: text })
      })
  }

  if (loadError) {
    return (
      <div className="phone-frame">
        <p className="lobby-loading">{loadError}</p>
      </div>
    )
  }
  if (!broadcast) {
    return (
      <div className="phone-frame">
        <p className="lobby-loading">방송을 불러오는 중...</p>
      </div>
    )
  }

  const featured = broadcast.products[0]

  return (
    <div className="phone-frame room">
      <div className="room__video">
        {/*
          hls_url 은 05-media(MediaMTX·CloudFront)가 생기면 실제 값이 온다.
          그때 이 자리를 HLS 플레이어로 바꾼다 — 오버레이는 손대지 않는다.
        */}
        <div className="room__video-img" />
        <div className="room__video-scrim" />

        <div className="room__topbar">
          <span className="room__logo">올영 LIVE.</span>
          <div className="room__topbar-icons">
            <button className="icon-btn" onClick={() => setMuted((m) => !m)} aria-label="음소거">
              {muted ? '🔇' : '🔊'}
            </button>
            <button className="icon-btn" aria-label="공유">🔗</button>
          </div>
        </div>

        <div className="room__headline">
          <span className="badge badge-live">{broadcast.state}</span>
          <h1 className="room__title">{broadcast.broadcast_id}</h1>
          {!connected && <p className="room__segment">채팅 다시 연결 중...</p>}
        </div>

        <div className="room__overlay-bottom">
          <ChatPanel messages={messages} onSend={send} />

          {order.kind === 'accepted' && (
            <p className="room__order-note">
              주문이 접수되었습니다 ({order.orderId.slice(0, 12)}…)
            </p>
          )}
          {order.kind === 'failed' && <p className="room__order-note">{order.message}</p>}

          {featured && (
            <LiveProductCard
              product={featured}
              onBuy={buy}
            />
          )}
        </div>
      </div>
    </div>
  )
}

export default LiveRoom
