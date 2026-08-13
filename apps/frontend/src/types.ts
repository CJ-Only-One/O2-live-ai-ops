export type LiveStatus = 'LIVE' | 'UPCOMING' | 'ENDED'

export interface LiveItem {
  id: string
  title: string
  brand: string
  thumbnail: string
  status: LiveStatus
  startAt: string
  viewerCount: number
  badges: string[]
  segment: string
}

export interface Product {
  id: string
  liveId: string
  name: string
  thumbnail: string
  price: number
  originalPrice: number
  stock: number
}

export interface Coupon {
  id: string
  title: string
  discountLabel: string
  discountAmount: number
}

export interface ChatMessage {
  id: string
  author: string
  text: string
  kind: 'chat' | 'question' | 'answer'
}
