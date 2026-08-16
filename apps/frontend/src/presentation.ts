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
    title: '수분 앰플·선크림 최대 50% 단독 특가',
    brand: '올리브영 단독',
    thumbnail: 'https://picsum.photos/seed/oy-ampoule-live/600/800',
    badges: ['라이브 특가', '선착순 증정'],
    segment: '수분 앰플 특가 소개 중',
  },
  bc_1043: {
    title: '비타민 세럼 · 수분 크림 리뉴얼 기념전',
    brand: '올영 PICK',
    thumbnail: 'https://picsum.photos/seed/oy-vitamin-live/600/800',
    badges: ['1+1', '무료배송'],
    segment: '비타민 세럼 사용법 시연 중',
  },
  bc_1050: {
    title: '프로틴 쉐이크 최대 40% + 쉐이커 증정',
    brand: '올리브베러',
    thumbnail: 'https://picsum.photos/seed/oy-protein/600/800',
    badges: ['쉐이커 증정'],
    segment: '',
  },
  bc_1051: {
    title: '유산균 30포 · 이너뷰티 기획전',
    brand: '올리브영 단독',
    thumbnail: 'https://picsum.photos/seed/oy-probiotics/600/800',
    badges: ['앵콜 특가'],
    segment: '',
  },
  bc_1030: {
    title: '마스크팩 30매 파격가 라이브',
    brand: '올영 PICK',
    thumbnail: 'https://picsum.photos/seed/oy-maskpack/600/800',
    badges: [],
    segment: '',
  },
}

const DEFAULT_PRODUCT: ProductPresentation = {
  image: 'https://picsum.photos/seed/oliveyoung-item/200/200',
  brand: '올리브영',
}

const PRODUCTS: Record<string, ProductPresentation> = {
  '88213': { image: 'https://picsum.photos/seed/oy-p-ampoule/240/240', brand: '올리브영 단독' },
  '88214': { image: 'https://picsum.photos/seed/oy-p-sun/240/240', brand: '데일리' },
  '88215': { image: 'https://picsum.photos/seed/oy-p-hair/240/240', brand: '리페어' },
  '88216': { image: 'https://picsum.photos/seed/oy-p-cleansing/240/240', brand: '딥클렌' },
  '88220': { image: 'https://picsum.photos/seed/oy-p-vitamin/240/240', brand: '비타랩' },
  '88221': { image: 'https://picsum.photos/seed/oy-p-cream/240/240', brand: '모이스트' },
  '88230': { image: 'https://picsum.photos/seed/oy-p-protein/240/240', brand: '올리브베러' },
  '88240': { image: 'https://picsum.photos/seed/oy-p-probio/240/240', brand: '이너뷰티' },
  '88250': { image: 'https://picsum.photos/seed/oy-p-mask/240/240', brand: '올영 PICK' },
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


/**
 * 메인 이벤트 배너. 서버가 주지 않는 장식이다 — 기획전은 이 프로젝트의
 * 범위 밖이고, 화면이 앱처럼 보이려면 필요하다.
 */
export const HOME_BANNERS = [
  {
    id: 'ev-summer',
    eyebrow: 'OLIVE YOUNG LIVE',
    title: '여름 마무리 세일\n최대 50% 단독 특가',
    sub: '라이브 방송 중 · 선착순 쿠폰 증정',
    image: 'https://picsum.photos/seed/oy-ev-summer/750/840',
    tint: 'linear-gradient(180deg, rgba(0,0,0,.05) 30%, rgba(0,0,0,.62) 100%)',
  },
  {
    id: 'ev-skin',
    eyebrow: 'SKINCARE WEEK',
    title: '스킨케어 위크\n앰플·세럼 1+1',
    sub: '오늘드림 주문 시 무료배송',
    image: 'https://picsum.photos/seed/oy-ev-skin/750/840',
    tint: 'linear-gradient(180deg, rgba(0,0,0,.05) 30%, rgba(0,0,0,.6) 100%)',
  },
  {
    id: 'ev-inner',
    eyebrow: 'INNER BEAUTY',
    title: '이너뷰티 기획전\n유산균·프로틴 모음',
    sub: '구매 시 쉐이커 증정',
    image: 'https://picsum.photos/seed/oy-ev-inner/750/840',
    tint: 'linear-gradient(180deg, rgba(0,0,0,.05) 30%, rgba(0,0,0,.6) 100%)',
  },
]

/** 상단 카테고리 칩. 표시만 하고 이동하지 않는다. */
export const CATEGORIES = ['추천', '랭킹', '세일', '오늘드림', '기획전', '브랜드관']

/** 퀵메뉴. 실제 앱의 아이콘 줄을 흉내낸다. */
export const QUICK_MENU = [
  { icon: '🔥', label: '세일' },
  { icon: '🏆', label: '랭킹' },
  { icon: '🚚', label: '오늘드림' },
  { icon: '🎁', label: '기획전' },
  { icon: '📺', label: '올영LIVE' },
]
