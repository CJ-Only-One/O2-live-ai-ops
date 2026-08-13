import { mockProducts } from '../mocks/products'
import type { Product } from '../types'

// product-api 대신 mock. 응답 형태(가격·재고)는 실제 API와 동일하게 맞춰뒀다.
const DELAY_MS = 200

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), DELAY_MS))
}

export function fetchProductsByLiveId(liveId: string): Promise<Product[]> {
  return delay(mockProducts.filter((product) => product.liveId === liveId))
}

export function fetchProductById(id: string): Promise<Product | undefined> {
  return delay(mockProducts.find((product) => product.id === id))
}
