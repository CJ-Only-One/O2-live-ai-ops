import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { fetchLiveById } from '../services/liveService'
import { fetchProductsByLiveId } from '../services/productService'
import { issueCoupon } from '../services/couponService'
import { mockCoupons } from '../mocks/coupons'
import { useChatStream } from '../services/useChatStream'
import type { LiveItem, Product } from '../types'
import ChatPanel from '../components/ChatPanel'
import LiveProductCard from '../components/LiveProductCard'
import '../styles/common.css'
import './LiveRoom.css'

function LiveRoom() {
  const { liveId } = useParams()
  const navigate = useNavigate()
  const { messages, sendMessage } = useChatStream()

  const [live, setLive] = useState<LiveItem | null>(null)
  const [products, setProducts] = useState<Product[]>([])
  const [muted, setMuted] = useState(true)
  const [couponState, setCouponState] = useState<'idle' | 'loading' | 'issued'>('idle')

  useEffect(() => {
    if (!liveId) return
    fetchLiveById(liveId).then((data) => data && setLive(data))
    fetchProductsByLiveId(liveId).then(setProducts)
  }, [liveId])

  function handleIssueCoupon() {
    if (couponState !== 'idle') return
    setCouponState('loading')
    issueCoupon(mockCoupons[0].id)
      .then(() => setCouponState('issued'))
      .catch(() => setCouponState('idle'))
  }

  if (!live) {
    return (
      <div className="phone-frame">
        <p className="lobby-loading">방송을 불러오는 중...</p>
      </div>
    )
  }

  return (
    <div className="phone-frame room">
      <div className="room__video">
        <img src={live.thumbnail} alt="" className="room__video-img" />
        <div className="room__video-scrim" />

        <div className="room__topbar">
          <span className="room__logo">올영 LIVE.</span>
          <div className="room__topbar-icons">
            <button className="icon-btn" onClick={() => setMuted((m) => !m)} aria-label="음소거">
              {muted ? '🔇' : '🔊'}
            </button>
            <button className="icon-btn" aria-label="공유">
              🔗
            </button>
            <button className="icon-btn" aria-label="설정">
              ⚙️
            </button>
            <button className="icon-btn" onClick={() => navigate('/')} aria-label="닫기">
              ✕
            </button>
          </div>
        </div>

        <div className="room__headline">
          <span className="badge badge-live">LIVE</span>
          <h1 className="room__title">{live.title}</h1>
          <button className="btn-ghost">풀영상 보기</button>
          {live.segment && <p className="room__segment">📍 {live.segment}</p>}
        </div>

        <div className="room__overlay-bottom">
          <ChatPanel messages={messages} onSend={sendMessage} />

          <button
            className="room__coupon"
            onClick={handleIssueCoupon}
            disabled={couponState !== 'idle'}
          >
            {couponState === 'issued'
              ? '✅ 쿠폰 발급 완료'
              : couponState === 'loading'
                ? '발급 중...'
                : `🎟 ${mockCoupons[0].discountLabel} 쿠폰 받기`}
          </button>

          {products[0] && (
            <LiveProductCard
              product={products[0]}
              onBuy={(p) => navigate(`/checkout/${p.id}`)}
            />
          )}
        </div>
      </div>
    </div>
  )
}

export default LiveRoom
