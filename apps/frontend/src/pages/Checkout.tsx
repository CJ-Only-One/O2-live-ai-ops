import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { fetchProductById } from '../services/productService'
import { mockCoupons } from '../mocks/coupons'
import { createOrder } from '../services/checkoutService'
import type { CheckoutResult } from '../services/checkoutService'
import type { Product } from '../types'
import '../styles/common.css'
import './Checkout.css'

type Stage = 'input' | 'processing' | 'success' | 'fail'

const PAYMENT_METHODS = ['신용카드', 'PAYCO', '카카오페이', '네이버페이', '휴대폰결제', '계좌이체']

function Checkout() {
  const { productId } = useParams()
  const navigate = useNavigate()

  const [product, setProduct] = useState<Product | null>(null)
  const [quantity] = useState(1)
  const [couponId, setCouponId] = useState<string>('')
  const [payment, setPayment] = useState(PAYMENT_METHODS[0])
  const [stage, setStage] = useState<Stage>('input')
  const [result, setResult] = useState<CheckoutResult | null>(null)
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(() => {
    if (!productId) return
    fetchProductById(productId).then((p) => p && setProduct(p))
  }, [productId])

  const coupon = mockCoupons.find((c) => c.id === couponId)
  const subtotal = product ? product.price * quantity : 0
  const discount = coupon
    ? coupon.discountAmount < 1
      ? Math.min(Math.round(subtotal * coupon.discountAmount), 10000)
      : coupon.discountAmount
    : 0
  const total = Math.max(subtotal - discount, 0)

  function handlePay() {
    if (!product) return
    setStage('processing')
    createOrder({ productId: product.id, quantity, couponId: couponId || null })
      .then((res) => {
        setResult(res)
        setStage('success')
      })
      .catch((err: Error) => {
        setErrorMessage(err.message)
        setStage('fail')
      })
  }

  if (!product) {
    return (
      <div className="checkout-page">
        <p className="checkout-loading">상품 정보를 불러오는 중...</p>
      </div>
    )
  }

  if (stage === 'processing') {
    return (
      <div className="checkout-result">
        <div className="spinner" />
        <p className="checkout-result__title">결제 처리 중입니다...</p>
        <p className="checkout-result__desc">잠시만 기다려주세요</p>
      </div>
    )
  }

  if (stage === 'success' && result) {
    return (
      <div className="checkout-result">
        <div className="checkout-result__icon checkout-result__icon--ok">✓</div>
        <p className="checkout-result__title">결제가 완료되었습니다</p>
        <p className="checkout-result__desc">주문번호 {result.orderId}</p>
        <p className="checkout-result__amount">{result.totalAmount.toLocaleString()}원 결제</p>
        <div className="checkout-result__actions">
          <button className="btn-primary" onClick={() => navigate('/')}>
            라이브로 돌아가기
          </button>
        </div>
      </div>
    )
  }

  if (stage === 'fail') {
    return (
      <div className="checkout-result">
        <div className="checkout-result__icon checkout-result__icon--fail">✕</div>
        <p className="checkout-result__title">결제에 실패했습니다</p>
        <p className="checkout-result__desc">{errorMessage || '잠시 후 다시 시도해주세요'}</p>
        <div className="checkout-result__actions">
          <button className="btn-primary" onClick={() => setStage('input')}>
            다시 시도
          </button>
          <button className="checkout-result__secondary" onClick={() => navigate('/')}>
            라이브로 돌아가기
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="checkout-page">
      <header className="checkout-topbar">
        <span className="checkout-topbar__logo">OLIVE YOUNG</span>
      </header>

      <div className="checkout-container">
        <div className="checkout-breadcrumb">01 장바구니 &gt; <strong>02 주문/결제</strong></div>
        <h1 className="checkout-heading">주문/결제</h1>

        <div className="checkout-layout">
          <div className="checkout-main">
            <section className="checkout-section">
              <h2 className="checkout-section__title">배송지정보</h2>
              <div className="checkout-form-row">
                <span className="checkout-form-label">받는분</span>
                <span className="checkout-form-value">김올영</span>
              </div>
              <div className="checkout-form-row">
                <span className="checkout-form-label">연락처</span>
                <span className="checkout-form-value">010-1234-5678</span>
              </div>
              <div className="checkout-form-row">
                <span className="checkout-form-label">주소</span>
                <span className="checkout-form-value">서울특별시 강남구 테헤란로 123, 5층</span>
              </div>
            </section>

            <section className="checkout-section">
              <h2 className="checkout-section__title">배송 요청사항</h2>
              <select className="checkout-select" defaultValue="문 앞에 놓아주세요">
                <option>문 앞에 놓아주세요</option>
                <option>경비실에 맡겨주세요</option>
                <option>직접 받을게요</option>
              </select>
            </section>

            <section className="checkout-section">
              <h2 className="checkout-section__title">상품정보</h2>
              <div className="checkout-product">
                <img src={product.thumbnail} alt={product.name} className="checkout-product__img" />
                <div className="checkout-product__info">
                  <p className="checkout-product__name">{product.name}</p>
                  <p className="checkout-product__price">{product.price.toLocaleString()}원</p>
                </div>
                <span className="checkout-product__qty">수량 {quantity}개</span>
              </div>
            </section>

            <section className="checkout-section">
              <h2 className="checkout-section__title">쿠폰할인정보</h2>
              <select
                className="checkout-select"
                value={couponId}
                onChange={(e) => setCouponId(e.target.value)}
              >
                <option value="">쿠폰을 선택하세요</option>
                {mockCoupons.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.title} ({c.discountLabel})
                  </option>
                ))}
              </select>
            </section>

            <section className="checkout-section">
              <h2 className="checkout-section__title">결제수단 선택</h2>
              <div className="checkout-payment-grid">
                {PAYMENT_METHODS.map((m) => (
                  <label
                    key={m}
                    className={`checkout-payment-option${payment === m ? ' is-selected' : ''}`}
                  >
                    <input
                      type="radio"
                      name="payment"
                      checked={payment === m}
                      onChange={() => setPayment(m)}
                    />
                    {m}
                  </label>
                ))}
              </div>
            </section>
          </div>

          <aside className="checkout-summary">
            <h2 className="checkout-summary__title">최종 결제정보</h2>
            <div className="checkout-summary__row">
              <span>총 상품금액</span>
              <span>{subtotal.toLocaleString()}원</span>
            </div>
            <div className="checkout-summary__row">
              <span>쿠폰할인금액</span>
              <span>-{discount.toLocaleString()}원</span>
            </div>
            <div className="checkout-summary__row checkout-summary__row--total">
              <span>최종 결제금액</span>
              <span>{total.toLocaleString()}원</span>
            </div>
            <button className="btn-primary checkout-summary__pay" onClick={handlePay}>
              {total.toLocaleString()}원 결제하기
            </button>
            <p className="checkout-summary__note">
              결제하신 금액은 상품·쿠폰을 서버에서 다시 확인한 뒤 최종 확정됩니다.
            </p>
          </aside>
        </div>
      </div>
    </div>
  )
}

export default Checkout
