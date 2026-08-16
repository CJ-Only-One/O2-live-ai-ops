import { useState } from 'react'
import type { Product } from '../types'
import './LiveProductCard.css'

interface Props {
  product: Product
  onBuy: (product: Product) => void
}

function LiveProductCard({ product, onBuy }: Props) {
  const [liked, setLiked] = useState(false)
  const [likeCount, setLikeCount] = useState(702)
  const discount = Math.round((1 - product.sale_price / product.price) * 100)

  function toggleLike() {
    setLiked((v) => !v)
    setLikeCount((c) => (liked ? c - 1 : c + 1))
  }

  return (
    <div className="live-product">
      <button className="live-product__info" onClick={() => onBuy(product)}>
        <div className="live-product__text">
          <p className="live-product__name">{product.name}</p>
          <p className="live-product__stock">
            {/* 표시용이다. 주문 가부는 서버의 재고 차감 결과가 정한다. */}
            {product.state === 'SOLD_OUT' ? '품절' : `${product.stock_display}개 남음`}
          </p>
          <p className="live-product__price">
            {discount > 0 && <span className="live-product__discount">{discount}%</span>}
            {product.sale_price.toLocaleString()}원
          </p>
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
