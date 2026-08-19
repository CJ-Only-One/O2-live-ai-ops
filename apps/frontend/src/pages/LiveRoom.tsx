import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import ChatPanel from '../components/ChatPanel'
import LiveProductCard from '../components/LiveProductCard'
import PreBroadcast from '../components/PreBroadcast'
import ProductSheet from '../components/ProductSheet'
import { approximateViewers, broadcastView } from '../presentation'
import { ApiError } from '../services/api'
import { fetchBroadcast } from '../services/broadcastService'
import { track } from '../services/clientEvents'
import { createOrder } from '../services/orderService'
import { useChat } from '../services/useChat'
import type { Broadcast, Product } from '../types'
import { uuid } from '../utils/uuid'
import '../styles/common.css'
import './LiveRoom.css'

type OrderPhase =
  | { kind: 'idle' }
  | { kind: 'sending' }
  | { kind: 'accepted'; orderId: string }
  | { kind: 'failed'; message: string }

function LiveRoom() {
  const { broadcastId } = useParams()
  const navigate = useNavigate()

  const [broadcast, setBroadcast] = useState<Broadcast | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [muted, setMuted] = useState(true)
  const [sheetOpen, setSheetOpen] = useState(false)
  const [couponIssued, setCouponIssued] = useState(false)
  const [order, setOrder] = useState<OrderPhase>({ kind: 'idle' })

  const { messages, connected, send } = useChat(broadcastId)

  /**
   * 재시도는 같은 멱등키를 다시 보내야 한다. 서버가 만들어주지 않으므로
   * 상품별로 하나씩 들고 있는다 (contracts.md 1.2).
   *
   * 주문이 성사되면 버린다. 남겨두면 같은 상품을 또 살 때 서버가 첫 주문을
   * 그대로 돌려준다.
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

  /**
   * 진입·이탈 (contracts.md 2.5).
   *
   * 이탈은 언마운트(다른 화면으로 이동)와 pagehide(탭을 닫음) 양쪽에서 온다.
   * 둘 다 일어날 수 있어 한 번만 보내도록 잠근다 — 이탈이 두 번 세어지면
   * 동시 시청자 추정이 음수 쪽으로 흐른다.
   *
   * 개발 모드에서는 StrictMode 가 effect 를 두 번 돌려 진입이 두 번 나간다.
   * 빌드에서는 일어나지 않는다.
   */
  const leftRef = useRef(false)
  useEffect(() => {
    if (!broadcastId) return

    leftRef.current = false
    track(broadcastId, [{ action: 'LIVE_ENTER' }])

    const leave = () => {
      if (leftRef.current) return
      leftRef.current = true
      track(broadcastId, [{ action: 'LIVE_LEAVE' }], true)
    }

    window.addEventListener('pagehide', leave)
    return () => {
      window.removeEventListener('pagehide', leave)
      leave()
    }
  }, [broadcastId])

  // 끊겼다 다시 붙으면 스냅샷을 다시 받는다. 끊긴 동안의 변경은 푸시로
  // 오지 않았기 때문이다 (contracts.md 3.6).
  const wasConnected = useRef(false)
  useEffect(() => {
    if (connected && wasConnected.current) load()
    wasConnected.current = connected
  }, [connected, load])

  function buy(product: Product, qty: number) {
    if (!broadcastId || order.kind === 'sending') return

    /*
      이 한 번의 누름이 서버에서 이벤트 둘(coupon.issue · order.create)이 되므로
      클릭도 둘로 낸다 (contracts.md 5.2). 짝이 1:1 이어야 click_ratio 가
      "버튼 없이 API 를 부르는 트래픽"을 가려낸다.

      요청 **직전에** 낸다. 클릭과 서버 이벤트가 같은 10초 윈도우에서 만나야
      집계에서 짝이 지어진다 (infra/06-datastream/warm).
    */
    track(broadcastId, [
      { action: 'COUPON_BUTTON_CLICK', target_id: product.sku_id },
      { action: 'CHECKOUT_CLICK', target_id: product.sku_id },
    ])

    let key = idemKeys.current.get(product.sku_id)
    if (!key) {
      key = uuid()
      idemKeys.current.set(product.sku_id, key)
    }

    setOrder({ kind: 'sending' })
    createOrder(broadcastId, product.sku_id, qty, key)
      .then((res) => {
        idemKeys.current.delete(product.sku_id)
        setSheetOpen(false)
        setOrder({ kind: 'accepted', orderId: res.order_id })
        // 재고가 줄었으므로 스냅샷을 다시 받는다. stock.update 푸시가
        // 붙으면 이 호출은 필요 없어진다 (contracts.md 3.3).
        load()
      })
      .catch((e: ApiError) => {
        // code 로 분기한다. message 는 예고 없이 바뀐다 (contracts.md 1.3).
        const text =
          e.code === 'SOLD_OUT'
            ? '주문 처리 중 품절되었습니다'
            : e.code === 'NOT_STARTED'
              ? '아직 특가가 시작되지 않았습니다'
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

  // 방송 전에는 재생할 것이 없다. 상품 시트도 채팅도 열지 않고 예고 화면만
  // 보여준다 — 시작 시각 전에 주문이 들어가면 서버가 NOT_STARTED 로 막는다.
  if (broadcast.state === 'SCHEDULED') {
    return (
      <PreBroadcast
        broadcastId={broadcast.broadcast_id}
        startedAt={broadcast.started_at}
        onClose={() => navigate('/')}
      />
    )
  }

  const view = broadcastView(broadcast.broadcast_id)
  const featured = broadcast.products.find((p) => p.state === 'ON_SALE') ?? broadcast.products[0]

  return (
    <div className="phone-frame room">
      <div className="room__video">
        {/*
          영상 자리. 07-media(MediaMTX·CloudFront)가 생기면 hls_url 로
          플레이어를 붙인다 — 오버레이 구조는 그대로라 교체가 이 한 줄이다.
        */}
        <img src={view.thumbnail} alt="" className="room__video-img" />
        <div className="room__video-scrim" />

        <div className="room__topbar">
          <span className="room__logo">올영LIVE</span>
          <div className="room__topbar-icons">
            <span className="room__viewers">
              👁 {approximateViewers(broadcast.broadcast_id).toLocaleString()}
            </span>
            <button className="icon-btn" onClick={() => setMuted((m) => !m)} aria-label="음소거">
              {muted ? '🔇' : '🔊'}
            </button>
            <button className="icon-btn" onClick={() => navigate('/')} aria-label="닫기">
              ✕
            </button>
          </div>
        </div>

        <div className="room__headline">
          {broadcast.state === 'LIVE' && <span className="badge badge-live">LIVE</span>}
          <p className="room__brand">{view.brand}</p>
          <h1 className="room__title">{view.title}</h1>
          {view.segment && <p className="room__segment">📍 {view.segment}</p>}
          {!connected && <p className="room__segment">채팅 다시 연결 중...</p>}
        </div>

        <div className="room__overlay-bottom">
          <ChatPanel messages={messages} onSend={send} />

          {order.kind === 'accepted' && (
            <button className="room__toast" onClick={() => navigate(`/orders/${order.orderId}`)}>
              주문이 접수되었습니다 · 상태 보기 →
            </button>
          )}
          {order.kind === 'failed' && <p className="room__toast is-error">{order.message}</p>}

          {/*
            쿠폰 API 는 계약에 없다. 화면 장식이고 실제 발급이 일어나지 않는다 —
            특가 자체가 쿠폰을 대신한다 (contracts.md 5.2).
          */}
          <button
            className={`room__coupon${couponIssued ? ' is-issued' : ''}`}
            onClick={() => setCouponIssued(true)}
            disabled={couponIssued}
          >
            {couponIssued ? '✓ 쿠폰이 발급되었습니다' : '🎟 라이브 전용 쿠폰 받기'}
          </button>

          {featured && (
            <LiveProductCard
              product={featured}
              count={broadcast.products.length}
              onOpen={() => setSheetOpen(true)}
            />
          )}
        </div>
      </div>

      {sheetOpen && (
        <ProductSheet
          products={broadcast.products}
          onClose={() => setSheetOpen(false)}
          onBuy={buy}
          pending={order.kind === 'sending'}
        />
      )}
    </div>
  )
}

export default LiveRoom
