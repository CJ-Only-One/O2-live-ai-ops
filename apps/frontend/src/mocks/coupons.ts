import type { Coupon } from '../types'

export const mockCoupons: Coupon[] = [
  {
    id: 'coupon-1',
    title: '라이브 방송 전용 3천원 할인쿠폰',
    discountLabel: '3,000원 할인',
    discountAmount: 3000,
  },
  {
    id: 'coupon-2',
    title: '올영 라이브 5% 추가할인 쿠폰',
    discountLabel: '5% 할인 (최대 1만원)',
    discountAmount: 0.05,
  },
]
