import assert from 'node:assert/strict';
import test from 'node:test';

import { decayedComplaintRatio } from './recovery-decay.mjs';

test('복구 뒤 불만 확률이 선형으로 0까지 감소한다', () => {
  assert.equal(decayedComplaintRatio(0.3, 0, 60), 0.3);
  assert.equal(decayedComplaintRatio(0.3, 30, 60), 0.15);
  assert.equal(decayedComplaintRatio(0.3, 60, 60), 0);
  assert.equal(decayedComplaintRatio(0.3, 90, 60), 0);
  assert.equal(decayedComplaintRatio(0.3, 0, 0), 0);
});
