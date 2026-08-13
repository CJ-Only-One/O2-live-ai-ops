import type { ChatMessage } from '../types'

export const initialChat: ChatMessage[] = [
  { id: 'c1', author: 'ou****', text: '부모님 운동 안 하셔도 먹어도 되나요?', kind: 'question' },
  {
    id: 'c2',
    author: '올영LIVE',
    text: '성인 기준, 몸무게 1kg당 단백질을 최소 1g 이상 드시는 걸 권장해요!',
    kind: 'answer',
  },
  { id: 'c3', author: 'ki****', text: '지금 주문하면 오늘 도착하나요?', kind: 'question' },
]
