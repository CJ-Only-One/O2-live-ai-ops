import assert from 'node:assert/strict';
import test from 'node:test';

import {
  assertSuccess,
  historyLocation,
  loadConfig,
  unmarshallItem,
} from './chat-to-dify-e2e.mjs';

test('live execution requires explicit opt-in and a synthetic broadcast id', () => {
  assert.throws(() => loadConfig({}), /ALLOW_LIVE_CHAT_TO_DIFY_E2E/);
  assert.throws(
    () =>
      loadConfig({
        ALLOW_LIVE_CHAT_TO_DIFY_E2E: '1',
        CHAT_TEST_WS_BASE: 'wss://example.test',
        CHAT_E2E_BROADCAST_ID: 'production',
      }),
    /bc_<digits>/,
  );
});

test('configuration derives isolated resource names without storing endpoints', () => {
  const config = loadConfig({
    ALLOW_LIVE_CHAT_TO_DIFY_E2E: '1',
    CHAT_TEST_WS_BASE: 'wss://example.test',
    CHAT_E2E_BROADCAST_ID: 'bc_2026082401',
    O2_PROJECT: 'sample',
    O2_ENVIRONMENT: 'dev',
  });
  assert.equal(config.prefix, 'sample-dev');
  assert.equal(config.agentWorker, 'sample-dev-dify-agent-entry-worker');
});

test('live execution is restricted to the dev namespace', () => {
  assert.throws(
    () =>
      loadConfig({
        ALLOW_LIVE_CHAT_TO_DIFY_E2E: '1',
        CHAT_TEST_WS_BASE: 'wss://example.test',
        CHAT_E2E_BROADCAST_ID: 'bc_2026082402',
        O2_ENVIRONMENT: 'prod',
        O2_NAMESPACE: 'o2-prod',
      }),
    /restricted to environment=dev/,
  );
});

test('DynamoDB values are unmarshalled for Candidate and ledger assertions', () => {
  assert.deepEqual(
    unmarshallItem({
      status: { S: 'SUCCEEDED' },
      attempt_count: { N: '1' },
      raw_chat_included: { BOOL: false },
      nested: { M: { revision: { N: '1' } } },
    }),
    {
      status: 'SUCCEEDED',
      attempt_count: 1,
      raw_chat_included: false,
      nested: { revision: 1 },
    },
  );
});

test('history object and vector keys are derived only from the Incident snapshot', () => {
  assert.deepEqual(
    historyLocation({
      incident_id: 'inc_test123',
      opened_at: '2026-08-25T12:34:56Z',
    }),
    {
      key: 'incidents/dt=2026-08-25/inc_test123.json',
      vectorKey: 'inc_test123',
    },
  );
  assert.throws(() => historyLocation({ incident_id: 'inc_test123' }), /cannot resolve/);
});

test('success requires privacy, incident contract, and exactly-once Dify completion', () => {
  assert.doesNotThrow(() =>
    assertSuccess({
      candidate: { raw_chat_included: false, agent_handoff_status: 'NOT_CONFIGURED' },
      claim: {
        status: 'EMITTED',
        snapshot: { event_type: 'agent.incident.v1', revision: 1 },
      },
      ledger: { status: 'SUCCEEDED', attempt_count: 1, workflow_run_id: 'run-test' },
    }),
  );
  assert.throws(
    () =>
      assertSuccess({
        candidate: { raw_chat_included: true, agent_handoff_status: 'NOT_CONFIGURED' },
        claim: {
          status: 'EMITTED',
          snapshot: { event_type: 'agent.incident.v1', revision: 1 },
        },
        ledger: { status: 'SUCCEEDED', attempt_count: 1, workflow_run_id: 'run-test' },
      }),
    /privacy/,
  );
});
