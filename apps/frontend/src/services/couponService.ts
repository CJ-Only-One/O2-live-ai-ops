import { mockCoupons } from '../mocks/coupons'
import type { Coupon } from '../types'

// coupon-api 대신 mock.
const DELAY_MS = 300

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), DELAY_MS))
}

export function fetchCoupons(): Promise<Coupon[]> {
  return delay(mockCoupons)
}

export function issueCoupon(couponId: string): Promise<Coupon> {
  const coupon = mockCoupons.find((c) => c.id === couponId)
  if (!coupon) return Promise.reject(new Error('존재하지 않는 쿠폰입니다'))
  return delay(coupon)
}
