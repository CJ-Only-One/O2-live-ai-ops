/**
 * 화면 장식용 값.
 *
 * **서버가 만들지 않는 것들이다.** 계약(contracts.md 2.1)이 주는 것은 재고와
 * 가격처럼 틀리면 안 되는 값이고, 제목·썸네일·브랜드는 AIOps 시연과 무관해
 * 백엔드가 관리할 이유가 없다. 그렇다고 화면에서 빼면 데모가 볼품없어지므로
 * 여기서 채운다.
 *
 * 규칙 하나만 지킨다 — **여기 있는 값으로 주문 가부나 금액을 판단하지 않는다.**
 * 그것은 항상 서버 응답을 따른다. 여기 값이 틀려도 사고가 나지 않아야 한다.
 *
 * 서버가 모르는 방송·상품이 와도 화면이 깨지지 않게 기본값을 둔다.
 */

export interface BroadcastPresentation {
  title: string
  brand: string
  thumbnail: string
  badges: string[]
  /** 진행 중인 코너. 나중에 WebSocket 의 broadcast.state 로 대체될 수 있다. */
  segment: string
}

export interface ProductPresentation {
  image: string
  brand: string
}

const DEFAULT_BROADCAST: BroadcastPresentation = {
  title: '올영라이브',
  brand: '올리브영',
  thumbnail: 'https://picsum.photos/seed/oliveyoung-live/600/900',
  badges: [],
  segment: '',
}

const BROADCASTS: Record<string, BroadcastPresentation> = {
  bc_1042: {
    title: '수분 앰플 · 선크림 최대 50% 단독 특가',
    brand: '올리브영 단독',
    thumbnail: 'https://picsum.photos/seed/oliveyoung-ampoule/600/900',
    badges: ['라이브 특가', '선착순 증정'],
    segment: '수분 앰플 특가 소개 중',
  },
}

const DEFAULT_PRODUCT: ProductPresentation = {
  image: 'https://picsum.photos/seed/oliveyoung-item/200/200',
  brand: '올리브영',
}

const PRODUCTS: Record<string, ProductPresentation> = {
  '88213': { image: 'https://picsum.photos/seed/oy-ampoule/200/200', brand: '올리브영 단독' },
  '88214': { image: 'https://picsum.photos/seed/oy-suncream/200/200', brand: '데일리' },
  '88215': { image: 'https://picsum.photos/seed/oy-hair/200/200', brand: '리페어' },
}

export function broadcastView(broadcastId: string): BroadcastPresentation {
  return BROADCASTS[broadcastId] ?? DEFAULT_BROADCAST
}

export function productView(skuId: string): ProductPresentation {
  return PRODUCTS[skuId] ?? DEFAULT_PRODUCT
}

/**
 * 시청자 수. 계약 3.3 에 WebSocket viewers 프레임이 정의돼 있지만 아직
 * 발행하는 쪽이 없다. 그때까지 화면이 비지 않게 근사값을 만든다 —
 * "정확할 필요가 없다" 는 것이 계약의 판단이기도 하다.
 */
export function approximateViewers(broadcastId: string): number {
  let seed = 0
  for (const ch of broadcastId) seed = (seed * 31 + ch.charCodeAt(0)) % 100000
  return 1200 + (seed % 2800)
}
