import { mockProducts } from '../mocks/products'
import { mockCoupons } from '../mocks/coupons'

export interface CheckoutRequest {
  productId: string
  quantity: number
  couponId: string | null
}

export interface CheckoutResult {
  orderId: string
  totalAmount: number
}

const PROCESSING_MS = 1600

// checkout-api를 흉내낸다. 프론트가 들고 있던 가격은 쓰지 않고,
// productId·couponId로 서버 쪽(mock) 데이터를 다시 조회해서 최종 금액을 만든다 —
// 실제 checkout-api도 이 원칙(프론트 가격 불신)을 그대로 따라야 한다.
export function createOrder(req: CheckoutRequest): Promise<CheckoutResult> {
  return new Promise((resolve, reject) => {
    setTimeout(() => {
      const product = mockProducts.find((p) => p.id === req.productId)
      if (!product) {
        reject(new Error('상품을 찾을 수 없습니다'))
        return
      }
      if (product.stock < req.quantity) {
        reject(new Error('재고가 부족합니다'))
        return
      }

      let total = product.price * req.quantity
      const coupon = req.couponId ? mockCoupons.find((c) => c.id === req.couponId) : null
      if (coupon) {
        total -=
          coupon.discountAmount < 1
            ? Math.min(Math.round(total * coupon.discountAmount), 10000)
            : coupon.discountAmount
      }
      total = Math.max(total, 0)

      // 데모용으로 결제 실패 케이스도 가끔 재현한다 (Result 상태 전환 확인용).
      if (Math.random() < 0.15) {
        reject(new Error('PG 승인에 실패했습니다'))
        return
      }

      resolve({
        orderId: `OY${Date.now().toString().slice(-9)}`,
        totalAmount: total,
      })
    }, PROCESSING_MS)
  })
}
