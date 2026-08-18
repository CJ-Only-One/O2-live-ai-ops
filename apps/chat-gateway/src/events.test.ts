/**
 * ulid() 가 SDK core.py 와 같은 값을 내는지 본다.
 *
 * 여기서 검사하는 것은 형식이 아니라 정렬성이다. 시간순 정렬이 깨져도
 * 아무 에러가 안 나고, 수집단이 중복 제거를 하는 시점에야 드러난다.
 *
 *   npm test
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { digest, hashUserKey, ulid } from './events.js';

const CROCKFORD = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';

test('ulid: 26자 Crockford base32', () => {
  const v = ulid();
  assert.equal(v.length, 26);
  for (const c of v) assert.ok(CROCKFORD.includes(c), `허용되지 않는 문자: ${c}`);
});

test('ulid: 문자열 정렬이 시간순 정렬이다', async () => {
  const first = ulid();
  await new Promise((r) => setTimeout(r, 5));
  const second = ulid();
  assert.ok(first < second, `${first} < ${second} 여야 한다`);
});

test('ulid: 같은 밀리초 안에서도 충돌하지 않는다', () => {
  const seen = new Set(Array.from({ length: 1000 }, () => ulid()));
  assert.equal(seen.size, 1000);
});

test('ulid: 앞 10자가 밀리초 타임스탬프다', () => {
  const before = Date.now();
  const prefix = ulid().slice(0, 10);
  const decoded = [...prefix].reduce((acc, c) => acc * 32n + BigInt(CROCKFORD.indexOf(c)), 0n);
  assert.ok(Number(decoded) >= before && Number(decoded) <= Date.now());
});

test('hashUserKey: SDK hash_key("u", raw) 형식', () => {
  const v = hashUserKey('session-abc');
  assert.match(v, /^u_[0-9a-f]{16}$/);
  assert.equal(v, hashUserKey('session-abc'));
  assert.notEqual(v, hashUserKey('session-abd'));
});

test('digest: 같은 문구는 같은 해시', () => {
  assert.equal(digest('사랑해요'), digest('사랑해요'));
  assert.equal(digest('사랑해요').length, 16);
});
