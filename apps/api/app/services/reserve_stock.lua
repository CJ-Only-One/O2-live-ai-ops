-- 멱등 확인과 재고 차감을 한 왕복으로 처리한다.
--
-- 둘을 나눠 부르면 그 사이에 같은 멱등키의 두 번째 요청이 들어와 재고가
-- 두 번 깎인다. MySQL 로 직접 차감하지 않는 이유는 동일 행 X 락이 직렬화되고
-- REPEATABLE READ 에서 갭 락까지 잡혀 특가 오픈 부하를 못 견디기 때문이다
-- (architecture.md 4.5).
--
-- KEYS[1] = idem:{key}      ARGV[1] = order_id
-- KEYS[2] = stock:{sku}     ARGV[2] = 수량
--                           ARGV[3] = 멱등키 TTL(초)
--
-- 반환 {코드, 값}
--   { 1, order_id }  이미 처리된 멱등키. 재고를 건드리지 않았다
--   { 0, 남은수량 }  차감 성공
--   {-1, ""       }  재고 부족
--   {-2, ""       }  재고 키 미초기화 — 시드가 안 돌았다는 뜻이다

local seen = redis.call('GET', KEYS[1])
if seen then
  return { 1, seen }
end

local cur = redis.call('GET', KEYS[2])
if cur == false then
  return { -2, "" }
end

local qty = tonumber(ARGV[2])
if tonumber(cur) < qty then
  return { -1, "" }
end

local remaining = redis.call('DECRBY', KEYS[2], qty)

-- 차감과 같은 원자 구간에서 멱등키를 남긴다. 뒤에서 SQS 발행이 실패하면
-- 애플리케이션이 이 키를 지우고 재고를 되돌린다.
redis.call('SET', KEYS[1], ARGV[1], 'EX', tonumber(ARGV[3]))

return { 0, tostring(remaining) }
