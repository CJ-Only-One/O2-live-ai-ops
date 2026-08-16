import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import EventBanner from '../components/EventBanner'
import LiveCard from '../components/LiveCard'
import TabBar from '../components/TabBar'
import { CATEGORIES, HOME_BANNERS, QUICK_MENU, productView } from '../presentation'
import { KNOWN_BROADCAST_IDS, fetchBroadcast } from '../services/broadcastService'
import type { Broadcast, Product } from '../types'
import '../styles/common.css'
import './Home.css'

/**
 * 메인 홈.
 *
 * 배너·카테고리·퀵메뉴는 화면 장식이다 (presentation.ts). 라이브 섹션과
 * 상품 목록은 실제 API 응답에서 나온다 — 가격과 재고는 서버 값이어야 한다.
 */
function Home() {
  const navigate = useNavigate()
  const [broadcasts, setBroadcasts] = useState<Broadcast[]>([])

  useEffect(() => {
    Promise.allSettled(KNOWN_BROADCAST_IDS.map(fetchBroadcast)).then((results) => {
      setBroadcasts(
        results
          .filter((r): r is PromiseFulfilledResult<Broadcast> => r.status === 'fulfilled')
          .map((r) => r.value),
      )
    })
  }, [])

  const liveNow = broadcasts.filter((b) => b.state === 'LIVE')

  // 방송에 편성된 상품을 모아 추천 목록으로 쓴다. 서버가 준 값 그대로다.
  const products: { product: Product; broadcastId: string }[] = broadcasts.flatMap((b) =>
    b.products.map((p) => ({ product: p, broadcastId: b.broadcast_id })),
  )

  return (
    <div className="phone-frame home">
      <header className="home-top">
        <div className="home-top__bar">
          <span className="home-top__logo">
            <span className="home-top__leaf" />
            OLIVE YOUNG
          </span>
          <div className="home-top__icons">
            <button className="icon-btn" aria-label="검색">🔍</button>
            <button className="icon-btn" aria-label="장바구니">🛒</button>
          </div>
        </div>
        <nav className="home-top__cats">
          {CATEGORIES.map((c, i) => (
            <span key={c} className={`home-top__cat${i === 0 ? ' is-active' : ''}`}>
              {c}
            </span>
          ))}
        </nav>
      </header>

      <main className="home-main">
        <EventBanner banners={HOME_BANNERS} />

        <nav className="quick">
          {QUICK_MENU.map((q) => (
            <button
              key={q.label}
              className="quick__item"
              onClick={() => q.label === '올영LIVE' && navigate('/live')}
            >
              <span className="quick__icon">{q.icon}</span>
              <span className="quick__label">{q.label}</span>
            </button>
          ))}
        </nav>

        {liveNow.length > 0 && (
          <section className="home-section">
            <div className="home-section__head">
              <h2 className="home-section__title">
                올영LIVE <span className="home-section__dot" />
              </h2>
              <button className="home-section__more" onClick={() => navigate('/live')}>
                전체보기 ›
              </button>
            </div>
            <div className="lobby-carousel">
              {liveNow.map((b) => (
                <LiveCard
                  key={b.broadcast_id}
                  broadcast={b}
                  onOpen={(x) => navigate(`/live/${x.broadcast_id}`)}
                />
              ))}
            </div>
          </section>
        )}

        {products.length > 0 && (
          <section className="home-section">
            <div className="home-section__head">
              <h2 className="home-section__title">지금 인기 상품</h2>
            </div>
            <div className="pgrid">
              {products.map(({ product, broadcastId }) => {
                const view = productView(product.sku_id)
                const discount = Math.round((1 - product.sale_price / product.price) * 100)
                return (
                  <button
                    key={product.sku_id}
                    className="pgrid__item"
                    onClick={() => navigate(`/live/${broadcastId}`)}
                  >
                    <div className="pgrid__thumb-wrap">
                      <img src={view.image} alt="" className="pgrid__thumb" />
                      {product.state === 'SOLD_OUT' && (
                        <span className="pgrid__soldout">품절</span>
                      )}
                    </div>
                    <p className="pgrid__brand">{view.brand}</p>
                    <p className="pgrid__name">{product.name}</p>
                    <p className="pgrid__price">
                      {discount > 0 && <span className="pgrid__discount">{discount}%</span>}
                      <strong>{product.sale_price.toLocaleString()}</strong>원
                    </p>
                  </button>
                )
              })}
            </div>
          </section>
        )}
      </main>

      <TabBar />
    </div>
  )
}

export default Home
