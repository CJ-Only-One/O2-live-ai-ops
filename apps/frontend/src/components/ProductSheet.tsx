import { useState } from 'react'

import { productView } from '../presentation'
import type { Product } from '../types'
import './ProductSheet.css'

interface Props {
  products: Product[]
  onClose: () => void
  onBuy: (product: Product, qty: number) => void
  pending: boolean
}

/**
 * 상품 목록과 구매 시트.
 *
 * 카드를 누르면 바로 주문이 나가지 않는다. 수량을 고르고 "구매하기" 를
 * 눌러야 나간다 — 라이브 화면에서 실수로 눌러 주문이 되는 것을 막는다.
 *
 * 버튼을 재고로 막지 않는다. 화면의 재고는 최대 30초 지난 값일 수 있고,
 * 판정은 서버의 차감 결과가 한다. 눌러보고 품절이면 그때 안내한다.
 */
function ProductSheet({ products, onClose, onBuy, pending }: Props) {
  const [selected, setSelected] = useState<Product | null>(null)
  const [qty, setQty] = useState(1)

  const pick = (p: Product) => {
    setSelected(p)
    setQty(1)
  }

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet" onClick={(e) => e.stopPropagation()}>
        <div className="sheet__handle" />

        {!selected && (
          <>
            <h2 className="sheet__title">방송 상품 {products.length}</h2>
            <ul className="sheet__list">
              {products.map((p) => {
                const view = productView(p.sku_id)
                const discount = Math.round((1 - p.sale_price / p.price) * 100)
                return (
                  <li key={p.sku_id}>
                    <button className="sheet__item" onClick={() => pick(p)}>
                      <img src={view.image} alt="" className="sheet__thumb" />
                      <div className="sheet__info">
                        <p className="sheet__brand">{view.brand}</p>
                        <p className="sheet__name">{p.name}</p>
                        <p className="sheet__price">
                          {discount > 0 && <span className="sheet__discount">{discount}%</span>}
                          <strong>{p.sale_price.toLocaleString()}</strong>원
                          <span className="sheet__origin">{p.price.toLocaleString()}원</span>
                        </p>
                        <p className="sheet__stock">
                          {p.state === 'SOLD_OUT'
                            ? '품절'
                            : p.state === 'PENDING'
                              ? '특가 오픈 예정'
                              : `${p.stock_display}개 남음`}
                        </p>
                      </div>
                    </button>
                  </li>
                )
              })}
            </ul>
          </>
        )}

        {selected && (
          <>
            <button className="sheet__back" onClick={() => setSelected(null)}>
              ← 상품 목록
            </button>
            <div className="sheet__buy">
              <img src={productView(selected.sku_id).image} alt="" className="sheet__thumb" />
              <div className="sheet__info">
                <p className="sheet__name">{selected.name}</p>
                <p className="sheet__price">
                  <strong>{selected.sale_price.toLocaleString()}</strong>원
                </p>
              </div>
            </div>

            <div className="sheet__qty">
              <span>수량</span>
              <div className="sheet__stepper">
                <button onClick={() => setQty((q) => Math.max(1, q - 1))} aria-label="수량 감소">
                  −
                </button>
                <span>{qty}</span>
                <button onClick={() => setQty((q) => q + 1)} aria-label="수량 증가">
                  +
                </button>
              </div>
            </div>

            <p className="sheet__total">
              총 결제금액 <strong>{(selected.sale_price * qty).toLocaleString()}원</strong>
            </p>

            <button
              className="sheet__cta"
              disabled={pending}
              onClick={() => onBuy(selected, qty)}
            >
              {pending ? '주문 처리 중...' : '구매하기'}
            </button>
          </>
        )}
      </div>
    </div>
  )
}

export default ProductSheet
