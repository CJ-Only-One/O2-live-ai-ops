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
  /** 방송 전 화면의 한 줄 멘트. 실제 라이브의 예고 카피와 같은 자리다. */
  teaser: string
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
  thumbnail: '/live/bc_1042.jpg',
  teaser: '라이브 특가로 만나보세요',
  badges: [],
  segment: '',
}

const BROADCASTS: Record<string, BroadcastPresentation> = {
  bc_1042: {
    title: '문이는 못말려: 집안 살림 다 팝니다.',
    brand: '올리브영 단독',
    thumbnail: '/live/bc_1042.jpg',
    teaser: '1등 수분세럼 리필 기획 1시간 라이브 특가!',
    badges: ['라이브 특가', '리필 증정'],
    segment: '토리든 다이브인 세럼 리필 기획 소개 중',
  },
  bc_1043: {
    title: '이니스프리 비타민C 세럼 · 에스네이처 수분크림 기획전',
    brand: '올영 PICK',
    thumbnail: '/live/bc_1043.jpg',
    teaser: '1+1 더블 기획 · 라이브 단독 구성!',
    badges: ['1+1', '호텔스파권 증정'],
    segment: '비타민C 캡슐 세럼 사용법 시연 중',
  },
  bc_1050: {
    title: '딜라이트 프로젝트 단백질쉐이크 8월 올영픽',
    brand: '딜라이트 프로젝트',
    thumbnail: '/live/bc_1050.jpg',
    teaser: '단백질쉐이크 45g 택1 · 올영픽 라이브!',
    badges: ['8월 올영픽'],
    segment: '',
  },
  bc_1051: {
    title: '덴프스 덴마크 유산균이야기 1+1 기획전',
    brand: '덴프스',
    thumbnail: '/live/bc_1051.jpg',
    teaser: '60일분 1+1 · 카카오프렌즈 키링 증정!',
    badges: ['1+1', '키링 증정'],
    segment: '',
  },
  bc_1030: {
    title: '메디힐 에센셜 마스크팩 10+1 골라담기',
    brand: '메디힐',
    thumbnail: '/live/bc_1030.jpg',
    teaser: '15년 연속 1위 마스크팩 7종 골라담기!',
    badges: [],
    segment: '',
  },
}

const DEFAULT_PRODUCT: ProductPresentation = {
  image: '/products/88213.jpg',
  brand: '올리브영',
}

// 제품 사진이다. 원본은 1000×1000 에 합계 5.5MB 였는데 화면에서는 52px·68px
// 썸네일로만 쓴다. 240px 로 줄여 넣었다 (합계 340KB) — 고해상도 화면에서도
// 3배수라 충분하다. 알파가 있는 둘만 PNG 로 두고 나머지는 JPG 다.
const PRODUCTS: Record<string, ProductPresentation> = {
  '88213': { image: '/products/88213.jpg', brand: '토리든' },
  '88214': { image: '/products/88214.jpg', brand: '제로이드' },
  '88215': { image: '/products/88215.jpg', brand: '미쟝센' },
  '88216': { image: '/products/88216.png', brand: '아누아' },
  '88220': { image: '/products/88220.png', brand: '이니스프리' },
  '88221': { image: '/products/88221.jpg', brand: '에스네이처' },
  '88230': { image: '/products/88230.jpg', brand: '딜라이트 프로젝트' },
  '88240': { image: '/products/88240.jpg', brand: '덴프스' },
  '88250': { image: '/products/88250.jpg', brand: '메디힐' },
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
 *
 * 배경은 **그 배너가 말하는 상품의 사진**이다. 방송 썸네일을 그대로 재사용하므로
 * 파일이 늘지 않는다. 히어로에서는 흐리지 않는다 — 상품이 무엇인지 보이는 것이
 * 목적이고, 글자 대비는 `tint` 가 맡는다.
 *
 * 카피는 **실제로 편성된 상품과 맞춘다.** 없는 기획전을 말하면 배너를 눌러볼
 * 이유가 없고, 시연 중 "저건 뭐냐" 는 질문만 남는다.
 */
export const HOME_BANNERS = [
  {
    id: 'ev-summer',
    eyebrow: 'OLIVE YOUNG LIVE',
    // 메디힐 마스크팩이 실제로 20,000 → 10,000 이다.
    title: '메디힐 마스크팩\n10+1 골라담기 50%',
    sub: '15년 연속 1위 · 7종 골라담기',
    image: '/live/bc_1030.jpg',
    tint: 'linear-gradient(180deg, rgba(0,0,0,.05) 30%, rgba(0,0,0,.62) 100%)',
  },
  {
    id: 'ev-skin',
    eyebrow: 'SKINCARE WEEK',
    title: '스킨케어 위크\n토리든 리필기획 · 비타민C 1+1',
    sub: '1등 수분세럼 리필 증정 · 라이브 단독',
    image: '/live/bc_1042.jpg',
    tint: 'linear-gradient(180deg, rgba(0,0,0,.05) 30%, rgba(0,0,0,.6) 100%)',
  },
  {
    id: 'ev-inner',
    eyebrow: 'INNER BEAUTY',
    title: '이너뷰티 기획전\n덴프스 유산균 1+1',
    sub: '60일분 · 카카오프렌즈 키링 증정',
    image: '/live/bc_1051.jpg',
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
