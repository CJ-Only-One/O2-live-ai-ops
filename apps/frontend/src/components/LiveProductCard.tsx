import { useState } from 'react'

import { productView } from '../presentation'
import type { Product } from '../types'
import './LiveProductCard.css'

interface Props {
  product: Product
  /** 방송 전체 상품 수. 카드에 "외 N개" 로 표시한다. */
  count: number
  onOpen: () => void
}

/**
 * 방송 하단에 고정되는 대표 상품 카드.
 *
 * 누르면 상품 시트가 열린다 — 여기서 바로 주문하지 않는다. 라이브 화면에서
 * 실수로 눌러 주문이 나가는 것을 막는다.
 */
function LiveProductCard({ product, count, onOpen }: Props) {
  const [liked, setLiked] = useState(false)
  const [likeCount, setLikeCount] = useState(702)

  const view = productView(product.sku_id)
  const discount = Math.round((1 - product.sale_price / product.price) * 100)

  function toggleLike() {
    setLiked((v) => !v)
    setLikeCount((c) => (liked ? c - 1 : c + 1))
  }

  return (
    <div className="live-product">
      <button className="live-product__info" onClick={onOpen}>
        <img src={view.image} alt="" className="live-product__thumb" />
        <div className="live-product__text">
          <p className="live-product__brand">{view.brand}</p>
          <p className="live-product__name">{product.name}</p>
          <p className="live-product__price">
            {discount > 0 && <span className="live-product__discount">{discount}%</span>}
            {product.sale_price.toLocaleString()}원
          </p>
          {count > 1 && <p className="live-product__more">외 {count - 1}개 상품 보기 ›</p>}
        </div>
      </button>
      <button
        className={`live-product__like${liked ? ' is-liked' : ''}`}
        onClick={toggleLike}
        aria-label="좋아요"
      >
        <span>{liked ? '❤️' : '🤍'}</span>
        <span className="live-product__like-count">{likeCount.toLocaleString()}</span>
      </button>
    </div>
  )
}

export default LiveProductCard
