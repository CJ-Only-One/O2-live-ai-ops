import assert from 'node:assert/strict';
import test from 'node:test';

import { nicknameFor } from './nickname.js';

test('nicknameFor: 같은 사용자 키는 항상 같은 닉네임', () => {
  const key = 'u_0123456789abcdef';
  assert.equal(nicknameFor(key), nicknameFor(key));
  assert.match(nicknameFor(key), /^[가-힣]+[1-9][0-9]$/);
});

test('nicknameFor: 다른 사용자 키는 대체로 다른 닉네임', () => {
  const nicks = new Set<string>();
  for (let i = 0; i < 200; i += 1) {
    nicks.add(nicknameFor(`u_${i.toString(16).padStart(16, '0')}`));
  }
  // 낱말 32개 × 번호 90개라 200명이면 겹침이 몇 건 나올 수 있다. 화면에서
  // "다들 다른 사람" 으로 읽히면 되므로 9할 이상 고유하면 통과로 본다.
  assert.ok(nicks.size >= 180, `고유 닉네임 ${nicks.size}개`);
});

test('nicknameFor: 원본 세션 키를 노출하지 않는다', () => {
  assert.equal(nicknameFor('u_00000000000000ff').includes('00000000'), false);
});

test('nicknameFor: 형식이 다르면 예전처럼 앞 8자', () => {
  assert.equal(nicknameFor('anon-abcdefgh'), 'anon-abc');
});
