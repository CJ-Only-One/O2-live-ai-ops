import type { Product } from '../types'

export const mockProducts: Product[] = [
  {
    id: 'prod-1',
    liveId: 'live-1',
    name: '마이프로틴 임팩트 웨이 프로틴 WPC 1kg 6종 택1',
    thumbnail: 'https://picsum.photos/seed/product-protein/200/200',
    price: 54900,
    originalPrice: 79900,
    stock: 128,
  },
  {
    id: 'prod-2',
    liveId: 'live-2',
    name: '지노마스터 여성 유산균 30포 (5일분 추가증정)',
    thumbnail: 'https://picsum.photos/seed/product-probiotics/200/200',
    price: 32900,
    originalPrice: 45000,
    stock: 46,
  },
  {
    id: 'prod-3',
    liveId: 'live-3',
    name: '프리메라 비타톤 바운시 밸런스 세럼 45ml',
    thumbnail: 'https://picsum.photos/seed/product-serum/200/200',
    price: 41300,
    originalPrice: 70000,
    stock: 210,
  },
  {
    id: 'prod-4',
    liveId: 'live-4',
    name: '메디힐 마데카소사이드 더마 세럼 50+50mL 기획',
    thumbnail: 'https://picsum.photos/seed/product-mask/200/200',
    price: 43000,
    originalPrice: 58000,
    stock: 12,
  },
]
