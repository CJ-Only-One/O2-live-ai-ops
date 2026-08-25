#!/usr/bin/env node

import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';

import { WebSocket } from 'ws';

const WINDOW_SECONDS = 15;
const DEFAULT_TIMEOUT_SECONDS = 180;
const DISABLED_CUTOFF_EPOCH = 4102444800;
const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(SCRIPT_DIR, '../../..');

export function loadConfig(env = process.env) {
  const enabled = env.ALLOW_LIVE_CHAT_TO_DIFY_E2E === '1';
  const wsBase = env.CHAT_TEST_WS_BASE;
  const broadcastId = env.CHAT_E2E_BROADCAST_ID;
  const timeoutSeconds = Number.parseInt(
    env.CHAT_E2E_TIMEOUT_SECONDS ?? String(DEFAULT_TIMEOUT_SECONDS),
    10,
  );

  if (!enabled) throw new Error('ALLOW_LIVE_CHAT_TO_DIFY_E2E=1 is required');
  if (!wsBase || !/^wss?:\/\//.test(wsBase)) {
    throw new Error('CHAT_TEST_WS_BASE must be an explicit ws:// or wss:// URL');
  }
  if (!broadcastId || !/^bc_[0-9]+$/.test(broadcastId)) {
    throw new Error('CHAT_E2E_BROADCAST_ID must match bc_<digits>');
  }
  if (!Number.isSafeInteger(timeoutSeconds) || timeoutSeconds < 60 || timeoutSeconds > 600) {
    throw new Error('CHAT_E2E_TIMEOUT_SECONDS must be an integer from 60 through 600');
  }

  const project = env.O2_PROJECT ?? 'o2';
  const environment = env.O2_ENVIRONMENT ?? 'dev';
  const namespace = env.O2_NAMESPACE ?? 'o2-dev';
  if (environment !== 'dev' || namespace !== 'o2-dev') {
    throw new Error('This live E2E runner is restricted to environment=dev and namespace=o2-dev');
  }
  const prefix = `${project}-${environment}`;
  return {
    wsBase,
    broadcastId,
    timeoutSeconds,
    region: env.AWS_REGION ?? 'ap-northeast-2',
    namespace,
    project,
    environment,
    prefix,
    chatTable: env.CHAT_INCIDENT_TABLE ?? `${prefix}-chat-incident-state`,
    incidentTable: env.AGENT_INCIDENT_TABLE ?? `${prefix}-dify-incident-state`,
    ledgerTable: env.AGENT_LEDGER_TABLE ?? `${prefix}-dify-agent-entry-idempotency`,
    chatWorker: env.CHAT_SIGNAL_WORKER ?? `${prefix}-chat-signal-worker`,
    chatAdapter: env.CHAT_SOURCE_ADAPTER ?? `${prefix}-chat-candidate-source-adapter`,
    correlator: env.INCIDENT_CORRELATOR ?? `${prefix}-dify-incident-correlator`,
    agentWorker: env.AGENT_ENTRY_WORKER ?? `${prefix}-dify-agent-entry-worker`,
  };
}

function run(command, args, { json = false, quiet = false, cwd = REPO_ROOT } = {}) {
  const result = spawnSync(command, args, {
    cwd,
    encoding: 'utf8',
    stdio: quiet ? ['ignore', 'pipe', 'pipe'] : ['ignore', 'pipe', 'inherit'],
  });
  if (result.status !== 0) {
    const detail = quiet ? result.stderr.trim() : '';
    throw new Error(`${command} failed with exit ${result.status}${detail ? `: ${detail}` : ''}`);
  }
  return json ? JSON.parse(result.stdout || '{}') : result.stdout;
}

function aws(config, args) {
  return run('aws', [...args, '--region', config.region, '--output', 'json'], {
    json: true,
    quiet: true,
  });
}

function awsMaybe(config, args) {
  try {
    return aws(config, args);
  } catch {
    return null;
  }
}

function terraformApply(stack, variables, targets) {
  const args = [`-chdir=${path.join(REPO_ROOT, 'infra', stack)}`, 'apply', '-auto-approve'];
  for (const [name, value] of Object.entries(variables)) args.push(`-var=${name}=${value}`);
  for (const target of targets) args.push(`-target=${target}`);
  run('terraform', args);
}

function tfSet(value) {
  return JSON.stringify([value]);
}

function sha256(value) {
  return createHash('sha256').update(value).digest('hex');
}

export function unmarshall(attribute) {
  if (attribute.S !== undefined) return attribute.S;
  if (attribute.N !== undefined) return Number(attribute.N);
  if (attribute.BOOL !== undefined) return attribute.BOOL;
  if (attribute.NULL === true) return null;
  if (attribute.SS !== undefined) return [...attribute.SS];
  if (attribute.L !== undefined) return attribute.L.map(unmarshall);
  if (attribute.M !== undefined) {
    return Object.fromEntries(Object.entries(attribute.M).map(([key, value]) => [key, unmarshall(value)]));
  }
  throw new Error('Unsupported DynamoDB attribute type');
}

export function unmarshallItem(item) {
  return Object.fromEntries(Object.entries(item).map(([key, value]) => [key, unmarshall(value)]));
}

async function poll(label, timeoutSeconds, fn) {
  const deadline = Date.now() + timeoutSeconds * 1000;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const value = await fn();
      if (value) return value;
    } catch (error) {
      lastError = error;
    }
    await sleep(2000);
  }
  throw new Error(`${label} timed out${lastError ? `: ${lastError.message}` : ''}`);
}

function queueUrl(region, account, name) {
  return `https://sqs.${region}.amazonaws.com/${account}/${name}`;
}

function queueAttributes(config, url) {
  const response = aws(config, [
    'sqs',
    'get-queue-attributes',
    '--queue-url',
    url,
    '--attribute-names',
    'ApproximateNumberOfMessages',
    'ApproximateNumberOfMessagesNotVisible',
    'ApproximateNumberOfMessagesDelayed',
  ]);
  const attrs = response.Attributes ?? {};
  return {
    visible: Number(attrs.ApproximateNumberOfMessages ?? 0),
    inFlight: Number(attrs.ApproximateNumberOfMessagesNotVisible ?? 0),
    delayed: Number(attrs.ApproximateNumberOfMessagesDelayed ?? 0),
  };
}

function isEmptyQueue(value) {
  return value.visible === 0 && value.inFlight === 0 && value.delayed === 0;
}

function adapterDlqContainsBroadcast(config, url) {
  const response = aws(config, [
    'sqs',
    'receive-message',
    '--queue-url',
    url,
    '--max-number-of-messages',
    '10',
    '--wait-time-seconds',
    '10',
    '--visibility-timeout',
    '30',
    '--attribute-names',
    'SentTimestamp',
  ]);
  let found = false;
  for (const message of response.Messages ?? []) {
    if (typeof message.Body === 'string' && message.Body.includes(config.broadcastId)) found = true;
    if (message.ReceiptHandle) {
      aws(config, [
        'sqs',
        'change-message-visibility',
        '--queue-url',
        url,
        '--receipt-handle',
        message.ReceiptHandle,
        '--visibility-timeout',
        '0',
      ]);
    }
  }
  return found;
}

function eventSourceState(config, functionName, sourceFragment) {
  const response = aws(config, [
    'lambda',
    'list-event-source-mappings',
    '--function-name',
    functionName,
  ]);
  const mapping = (response.EventSourceMappings ?? []).find((item) =>
    item.EventSourceArn?.includes(sourceFragment),
  );
  return mapping?.State ?? 'MISSING';
}

function lambdaEnvironment(config, functionName) {
  return (
    aws(config, [
      'lambda',
      'get-function-configuration',
      '--function-name',
      functionName,
    ]).Environment?.Variables ?? {}
  );
}

function preflight(config) {
  const identity = aws(config, ['sts', 'get-caller-identity']);
  const account = identity.Account;
  if (!account) throw new Error('AWS account could not be resolved');

  const deployment = run(
    'kubectl',
    ['get', 'deployment', 'chat-gateway', '-n', config.namespace, '-o', 'json'],
    { json: true, quiet: true },
  );
  if (deployment.status?.readyReplicas !== deployment.spec?.replicas) {
    throw new Error('chat-gateway is not fully Ready');
  }
  const dataConfig = run(
    'kubectl',
    ['get', 'configmap', 'o2-data', '-n', config.namespace, '-o', 'json'],
    { json: true, quiet: true },
  );
  if (dataConfig.data?.CHAT_SIGNAL_MODE !== 'shadow') {
    throw new Error('o2-data CHAT_SIGNAL_MODE must be shadow');
  }
  if (!dataConfig.data?.SQS_CHAT_SIGNAL_QUEUE_URL) {
    throw new Error('o2-data SQS_CHAT_SIGNAL_QUEUE_URL is missing');
  }
  if (eventSourceState(config, config.chatWorker, `:${config.prefix}-chat-signal`) !== 'Enabled') {
    throw new Error('Chat Signal Worker event source must already be Enabled');
  }

  const agentEnvironment = lambdaEnvironment(config, config.agentWorker);
  const history = {
    bucket: agentEnvironment.HISTORY_BUCKET,
    vectorBucket: agentEnvironment.VECTOR_BUCKET,
    vectorIndex: agentEnvironment.VECTOR_INDEX,
  };
  if (!history.bucket || !history.vectorBucket || !history.vectorIndex) {
    throw new Error('Agent Entry Worker history storage configuration is incomplete');
  }

  const disabledGates = [
    [
      config.chatAdapter,
      'CHAT_SOURCE_ADAPTER_ENABLED',
      `:table/${config.chatTable}/stream/`,
    ],
    [
      config.correlator,
      'INCIDENT_CORRELATOR_EXECUTION_ENABLED',
      `:${config.prefix}-dify-agent-trigger`,
    ],
    [
      config.agentWorker,
      'AGENT_ENTRY_EXECUTION_ENABLED',
      `:${config.prefix}-dify-agent-invocation`,
    ],
  ];
  for (const [functionName, flag, sourceSuffix] of disabledGates) {
    if (lambdaEnvironment(config, functionName)[flag] !== 'false') {
      throw new Error(`${functionName} must start with ${flag}=false`);
    }
    const state = eventSourceState(config, functionName, sourceSuffix);
    if (state !== 'Disabled') throw new Error(`${functionName} event source must start Disabled`);
  }

  const queues = {
    chatSignal: dataConfig.data.SQS_CHAT_SIGNAL_QUEUE_URL,
    signal: queueUrl(config.region, account, `${config.prefix}-dify-agent-trigger`),
    signalDlq: queueUrl(config.region, account, `${config.prefix}-dify-agent-trigger-dlq`),
    invocation: queueUrl(config.region, account, `${config.prefix}-dify-agent-invocation`),
    invocationDlq: queueUrl(config.region, account, `${config.prefix}-dify-agent-invocation-dlq`),
    adapterDlq: queueUrl(
      config.region,
      account,
      `${config.prefix}-chat-candidate-source-adapter-dlq`,
    ),
  };
  const queueBaselines = Object.fromEntries(
    Object.entries(queues).map(([name, url]) => [name, queueAttributes(config, url)]),
  );
  for (const name of ['chatSignal', 'signal', 'invocation']) {
    if (!isEmptyQueue(queueBaselines[name])) throw new Error(`${name} work queue is not empty`);
  }

  if (findChatState(config).length > 0) {
    throw new Error('CHAT_E2E_BROADCAST_ID already has synthetic state');
  }
  return { account, queues, queueBaselines, history };
}

function openSocket(config, userNumber) {
  const url = new URL('/ws', config.wsBase);
  url.searchParams.set('broadcast_id', config.broadcastId);
  const socket = new WebSocket(url, `e2e-${config.broadcastId}-${userNumber}`);
  let receivedItems = 0;
  socket.on('message', (raw) => {
    try {
      const frame = JSON.parse(raw.toString());
      if (frame.t === 'chat' && Array.isArray(frame.items)) receivedItems += frame.items.length;
    } catch {
      // Payload 내용은 출력하지 않고 최종 수신 개수로만 실패를 판정한다.
    }
  });
  return {
    socket,
    opened: new Promise((resolve, reject) => {
      socket.once('open', resolve);
      socket.once('error', reject);
    }),
    count: () => receivedItems,
  };
}

async function waitForWindowOffset(targetSeconds) {
  const current = (Date.now() / 1000) % WINDOW_SECONDS;
  let waitSeconds = (targetSeconds - current + WINDOW_SECONDS) % WINDOW_SECONDS;
  if (waitSeconds < 0.2) waitSeconds += WINDOW_SECONDS;
  await sleep(waitSeconds * 1000);
}

async function sendSyntheticChat(config) {
  const clients = Array.from({ length: 4 }, (_unused, index) => openSocket(config, index + 1));
  try {
    await Promise.all(clients.map((client) => client.opened));
    await waitForWindowOffset(2);
    const messages = [
      '상품 정보가 늦게 떠요',
      '새로고침해도 계속 로딩돼요',
      '결제 버튼 반응이 없어요',
      '상품 페이지가 너무 느려요',
    ];
    for (let index = 0; index < messages.length; index += 1) {
      clients[index].socket.send(JSON.stringify({ t: 'chat', msg: messages[index] }));
      await sleep(50);
    }
    await sleep(1000);
    const receivedItems = clients.reduce((total, client) => total + client.count(), 0);
    if (!clients.every((client) => client.count() >= messages.length)) {
      throw new Error('WebSocket fanout did not return all synthetic chats to every client');
    }
    return { sentMessages: messages.length, receivedItems };
  } finally {
    for (const client of clients) client.socket.close();
    await sleep(100);
  }
}

function findCandidate(config) {
  const response = aws(config, [
    'dynamodb',
    'scan',
    '--table-name',
    config.chatTable,
    '--filter-expression',
    '#pk = :active OR begins_with(#pk, :candidate)',
    '--expression-attribute-names',
    JSON.stringify({ '#pk': 'pk' }),
    '--expression-attribute-values',
    JSON.stringify({
      ':active': { S: `ACTIVE#${config.broadcastId}#USER_PERCEIVED_LATENCY` },
      ':candidate': { S: 'CANDIDATE#' },
    }),
    '--consistent-read',
  ]);
  for (const raw of response.Items ?? []) {
    const item = unmarshallItem(raw);
    if (item.payload?.broadcast_id === config.broadcastId) return item.payload;
  }
  return null;
}

function findChatState(config) {
  const response = aws(config, [
    'dynamodb',
    'scan',
    '--table-name',
    config.chatTable,
    '--projection-expression',
    '#pk,#sk',
    '--filter-expression',
    'contains(#pk, :broadcast)',
    '--expression-attribute-names',
    JSON.stringify({ '#pk': 'pk', '#sk': 'sk' }),
    '--expression-attribute-values',
    JSON.stringify({ ':broadcast': { S: config.broadcastId } }),
    '--consistent-read',
  ]);
  return response.Items ?? [];
}

function getItem(config, table, key) {
  const response = aws(config, [
    'dynamodb',
    'get-item',
    '--table-name',
    table,
    '--key',
    JSON.stringify(key),
    '--consistent-read',
  ]);
  return response.Item ? unmarshallItem(response.Item) : null;
}

function getIncidentClaim(config, sourceKey) {
  return getItem(config, config.incidentTable, {
    pk: { S: `SIGNAL#${sha256(sourceKey)}` },
  });
}

function getLedger(config, incidentId, revision) {
  return getItem(config, config.ledgerTable, {
    idempotency_key: { S: `incident:${incidentId}:revision:${revision}` },
  });
}

export function historyLocation(snapshot) {
  if (!snapshot?.incident_id || !/^\d{4}-\d{2}-\d{2}/.test(snapshot.opened_at ?? '')) {
    throw new Error('Incident snapshot cannot resolve a history location');
  }
  return {
    key: `incidents/dt=${snapshot.opened_at.slice(0, 10)}/${snapshot.incident_id}.json`,
    vectorKey: snapshot.incident_id,
  };
}

function findHistory(config, history, snapshot) {
  const location = historyLocation(snapshot);
  const object = awsMaybe(config, [
    's3api',
    'head-object',
    '--bucket',
    history.bucket,
    '--key',
    location.key,
  ]);
  if (!object) return null;

  const response = aws(config, [
    's3vectors',
    'get-vectors',
    '--vector-bucket-name',
    history.vectorBucket,
    '--index-name',
    history.vectorIndex,
    '--keys',
    location.vectorKey,
    '--return-metadata',
  ]);
  const vector = (response.vectors ?? []).find((item) => item.key === location.vectorKey);
  if (!vector) return null;
  if (vector.metadata?.s3_key !== location.key || vector.metadata?.source !== 'agent_entry') {
    throw new Error('Stored history vector metadata does not match the Agent Entry record');
  }
  if (Number(vector.metadata?.revision) !== snapshot.revision) {
    throw new Error('Stored history revision does not match the Incident snapshot');
  }
  return {
    s3_key: location.key,
    vector_key: location.vectorKey,
    vector_source: vector.metadata.source,
    revision: Number(vector.metadata.revision),
  };
}

function cleanupHistory(config, history, snapshot) {
  if (!history || !snapshot?.incident_id) return { deleted: false };
  const location = historyLocation(snapshot);
  aws(config, [
    's3vectors',
    'delete-vectors',
    '--vector-bucket-name',
    history.vectorBucket,
    '--index-name',
    history.vectorIndex,
    '--keys',
    location.vectorKey,
  ]);

  const listed = aws(config, [
    's3api',
    'list-object-versions',
    '--bucket',
    history.bucket,
    '--prefix',
    location.key,
  ]);
  const objects = [...(listed.Versions ?? []), ...(listed.DeleteMarkers ?? [])]
    .filter((item) => item.Key === location.key)
    .map((item) => ({ Key: item.Key, VersionId: item.VersionId }));
  if (objects.length > 0) {
    aws(config, [
      's3api',
      'delete-objects',
      '--bucket',
      history.bucket,
      '--delete',
      JSON.stringify({ Objects: objects, Quiet: true }),
    ]);
  }

  const objectStillPresent = awsMaybe(config, [
    's3api',
    'head-object',
    '--bucket',
    history.bucket,
    '--key',
    location.key,
  ]);
  const vectors = aws(config, [
    's3vectors',
    'get-vectors',
    '--vector-bucket-name',
    history.vectorBucket,
    '--index-name',
    history.vectorIndex,
    '--keys',
    location.vectorKey,
  ]).vectors ?? [];
  if (objectStillPresent || vectors.some((item) => item.key === location.vectorKey)) {
    throw new Error('Synthetic history cleanup did not finish');
  }
  return {
    deleted: true,
    s3_versions_deleted: objects.length,
    vector_deleted: true,
  };
}

function enableChatAdapter(config, cutoffEpoch) {
  terraformApply(
    '08-chat-signal',
    {
      chat_source_adapter_execution_enabled: 'true',
      chat_source_adapter_event_source_enabled: 'true',
      chat_source_adapter_allowed_broadcast_ids: tfSet(config.broadcastId),
      chat_source_adapter_not_before_epoch: String(cutoffEpoch),
    },
    [
      'aws_lambda_function.chat_source_adapter',
      'aws_lambda_event_source_mapping.chat_source_adapter',
    ],
  );
}

function disableChatAdapter() {
  terraformApply(
    '08-chat-signal',
    {
      chat_source_adapter_execution_enabled: 'false',
      chat_source_adapter_event_source_enabled: 'false',
      chat_source_adapter_allowed_broadcast_ids: '[]',
      chat_source_adapter_not_before_epoch: String(DISABLED_CUTOFF_EPOCH),
    },
    [
      'aws_lambda_function.chat_source_adapter',
      'aws_lambda_event_source_mapping.chat_source_adapter',
    ],
  );
}

function enableCorrelator(sourceKey) {
  terraformApply(
    '06-agent',
    {
      incident_correlator_execution_enabled: 'true',
      incident_correlator_event_source_enabled: 'true',
      incident_correlator_allowed_idempotency_keys: tfSet(sourceKey),
    },
    [
      'aws_lambda_function.incident_correlator',
      'aws_lambda_event_source_mapping.incident_correlator',
    ],
  );
}

function disableCorrelator() {
  terraformApply(
    '06-agent',
    {
      incident_correlator_execution_enabled: 'false',
      incident_correlator_event_source_enabled: 'false',
      incident_correlator_allowed_idempotency_keys: '[]',
    },
    [
      'aws_lambda_function.incident_correlator',
      'aws_lambda_event_source_mapping.incident_correlator',
    ],
  );
}

function enableAgentWorker(incidentId) {
  terraformApply(
    '06-agent',
    {
      agent_entry_execution_enabled: 'true',
      agent_entry_event_source_enabled: 'true',
      agent_entry_allowed_incident_ids: tfSet(incidentId),
    },
    [
      'aws_lambda_function.agent_entry_worker',
      'aws_lambda_event_source_mapping.agent_invocation_worker',
    ],
  );
}

function disableAgentWorker() {
  terraformApply(
    '06-agent',
    {
      agent_entry_execution_enabled: 'false',
      agent_entry_event_source_enabled: 'false',
      agent_entry_allowed_incident_ids: '[]',
    },
    [
      'aws_lambda_function.agent_entry_worker',
      'aws_lambda_event_source_mapping.agent_invocation_worker',
    ],
  );
}

function deleteItem(config, table, key) {
  aws(config, [
    'dynamodb',
    'delete-item',
    '--table-name',
    table,
    '--key',
    JSON.stringify(key),
  ]);
}

function cleanupState(config, candidate, claim) {
  if (claim?.snapshot?.incident_id) {
    const incidentId = claim.snapshot.incident_id;
    const revision = claim.snapshot.revision;
    const incidentItem = getItem(config, config.incidentTable, {
      pk: { S: `INCIDENT#${incidentId}` },
    });
    deleteItem(config, config.ledgerTable, {
      idempotency_key: { S: `incident:${incidentId}:revision:${revision}` },
    });
    deleteItem(config, config.ledgerTable, {
      idempotency_key: { S: `incident:${incidentId}:lock` },
    });
    deleteItem(config, config.incidentTable, { pk: { S: `INCIDENT#${incidentId}` } });
    deleteItem(config, config.incidentTable, {
      pk: { S: `SIGNAL#${sha256(`chat:${candidate.candidate_id}`)}` },
    });
    if (incidentItem?.correlation_key) {
      deleteItem(config, config.incidentTable, {
        pk: { S: `CORRELATION#${sha256(incidentItem.correlation_key)}` },
      });
    }
  }

  if (!candidate) return;
  const response = aws(config, [
    'dynamodb',
    'scan',
    '--table-name',
    config.chatTable,
    '--projection-expression',
    '#pk,#sk',
    '--filter-expression',
    'contains(#pk, :broadcast) OR #pk = :candidate',
    '--expression-attribute-names',
    JSON.stringify({ '#pk': 'pk', '#sk': 'sk' }),
    '--expression-attribute-values',
    JSON.stringify({
      ':broadcast': { S: config.broadcastId },
      ':candidate': { S: `CANDIDATE#${candidate.candidate_id}` },
    }),
    '--consistent-read',
  ]);
  for (const item of response.Items ?? []) {
    deleteItem(config, config.chatTable, { pk: item.pk, sk: item.sk });
  }
}

async function verifyRestored(config, queues, queueBaselines, candidate, claim) {
  const expected = [
    [
      config.chatAdapter,
      'CHAT_SOURCE_ADAPTER_ENABLED',
      `:table/${config.chatTable}/stream/`,
    ],
    [
      config.correlator,
      'INCIDENT_CORRELATOR_EXECUTION_ENABLED',
      `:${config.prefix}-dify-agent-trigger`,
    ],
    [
      config.agentWorker,
      'AGENT_ENTRY_EXECUTION_ENABLED',
      `:${config.prefix}-dify-agent-invocation`,
    ],
  ];
  for (const [functionName, flag, sourceSuffix] of expected) {
    if (lambdaEnvironment(config, functionName)[flag] !== 'false') {
      throw new Error(`${functionName} execution gate was not restored`);
    }
    if (eventSourceState(config, functionName, sourceSuffix) !== 'Disabled') {
      throw new Error(`${functionName} event source was not restored`);
    }
  }
  await poll('Queue drain after cleanup', 60, () => {
    const values = Object.fromEntries(
      Object.entries(queues).map(([name, url]) => [name, queueAttributes(config, url)]),
    );
    const workQueuesEmpty = ['chatSignal', 'signal', 'invocation'].every((name) =>
      isEmptyQueue(values[name]),
    );
    const dlqBaselinePreserved = ['signalDlq', 'invocationDlq'].every(
      (name) => JSON.stringify(values[name]) === JSON.stringify(queueBaselines[name]),
    );
    return workQueuesEmpty && dlqBaselinePreserved;
  });
  if (candidate && findChatState(config).length > 0) {
    throw new Error('Candidate cleanup did not finish');
  }
  if (candidate && getIncidentClaim(config, `chat:${candidate.candidate_id}`)) {
    throw new Error('Incident claim cleanup did not finish');
  }
  if (claim?.snapshot?.incident_id) {
    const incidentId = claim.snapshot.incident_id;
    if (
      getLedger(config, incidentId, claim.snapshot.revision) ||
      getItem(config, config.incidentTable, { pk: { S: `INCIDENT#${incidentId}` } })
    ) {
      throw new Error('Incident or ledger cleanup did not finish');
    }
  }
  if (adapterDlqContainsBroadcast(config, queues.adapterDlq)) {
    throw new Error('The current synthetic broadcast was found in the Adapter DLQ');
  }
  return {
    work_queues_empty: true,
    signal_and_invocation_dlq_baseline_preserved: true,
    adapter_dlq_test_broadcast_absent: true,
    adapter_dlq_visible_after: queueAttributes(config, queues.adapterDlq).visible,
  };
}

export function assertSuccess({ candidate, claim, ledger }) {
  if (candidate.raw_chat_included !== false) throw new Error('Candidate privacy contract failed');
  if (candidate.agent_handoff_status !== 'NOT_CONFIGURED') {
    throw new Error('Candidate handoff boundary changed unexpectedly');
  }
  if (claim.status !== 'EMITTED') throw new Error('Incident claim was not emitted');
  if (claim.snapshot?.event_type !== 'agent.incident.v1') {
    throw new Error('Incident contract was not produced');
  }
  if (claim.snapshot?.revision !== 1) throw new Error('Chat-only Incident must be revision 1');
  if (ledger.status !== 'SUCCEEDED') throw new Error('Dify workflow did not succeed');
  if (ledger.attempt_count !== 1) throw new Error('Dify workflow was not exactly-once');
  if (!ledger.workflow_run_id) throw new Error('Dify workflow run id is missing');
}

async function main() {
  if (process.argv.includes('--help')) {
    console.log(
      'Set ALLOW_LIVE_CHAT_TO_DIFY_E2E=1, CHAT_TEST_WS_BASE and CHAT_E2E_BROADCAST_ID, then run this script.',
    );
    return;
  }

  const config = loadConfig();
  let chatAdapterEnabled = false;
  let correlatorEnabled = false;
  let agentWorkerEnabled = false;
  let candidate = null;
  let claim = null;
  let queues = null;
  let queueBaselines = null;
  let history = null;
  let historyVerification = null;
  let historyCleanup = null;
  let result;
  let cleanupVerification;
  let failure;

  try {
    const preflightResult = preflight(config);
    queues = preflightResult.queues;
    queueBaselines = preflightResult.queueBaselines;
    history = preflightResult.history;
    const cutoffEpoch = Math.floor(Date.now() / 1000) - 2;

    console.error('[1/6] enabling the synthetic Chat Candidate adapter');
    chatAdapterEnabled = true;
    enableChatAdapter(config, cutoffEpoch);

    console.error('[2/6] sending four synthetic WebSocket chats in one 15-second window');
    const fanout = await sendSyntheticChat(config);
    candidate = await poll('Candidate creation', config.timeoutSeconds, () => findCandidate(config));
    const sourceKey = `chat:${candidate.candidate_id}`;

    console.error('[3/6] enabling the Correlator for the single Candidate');
    correlatorEnabled = true;
    enableCorrelator(sourceKey);
    claim = await poll('Incident creation', config.timeoutSeconds, () => {
      const value = getIncidentClaim(config, sourceKey);
      return value?.status === 'EMITTED' ? value : null;
    });
    const incidentId = claim.snapshot.incident_id;
    const revision = claim.snapshot.revision;

    console.error('[4/6] enabling the Generic Worker for the single Incident');
    agentWorkerEnabled = true;
    enableAgentWorker(incidentId);
    const ledger = await poll('Dify workflow completion', config.timeoutSeconds, () => {
      const value = getLedger(config, incidentId, revision);
      if (value?.status === 'FAILED') throw new Error(`Dify Worker failed: ${value.error_code ?? 'UNKNOWN'}`);
      return value?.status === 'SUCCEEDED' ? value : null;
    });

    assertSuccess({ candidate, claim, ledger });
    historyVerification = await poll('History object and vector storage', config.timeoutSeconds, () =>
      findHistory(config, history, claim.snapshot),
    );
    result = {
      schema_version: '1.0',
      suite: 'chat-input-to-dify-contract-workflow',
      status: 'PASS',
      broadcast_id: config.broadcastId,
      candidate_id: candidate.candidate_id,
      incident_id: incidentId,
      revision,
      candidate: {
        suspected_surface: candidate.suspected_surface,
        matched_messages: candidate.matched_messages,
        unique_users: candidate.unique_users,
        raw_chat_included: candidate.raw_chat_included,
      },
      websocket: fanout,
      dify: {
        ledger_status: ledger.status,
        attempt_count: ledger.attempt_count,
        workflow_run_id: ledger.workflow_run_id,
      },
      history: historyVerification,
      preflight: {
        work_queues_empty: true,
        existing_dlq_messages_preserved: Object.fromEntries(
          ['signalDlq', 'invocationDlq', 'adapterDlq'].map((name) => [
            name,
            preflightResult.queueBaselines[name].visible,
          ]),
        ),
      },
    };
  } catch (error) {
    failure = error;
  } finally {
    console.error('[5/6] restoring all execution gates to disabled');
    const cleanupErrors = [];
    for (const [enabled, disable] of [
      [chatAdapterEnabled, disableChatAdapter],
      [correlatorEnabled, disableCorrelator],
      [agentWorkerEnabled, disableAgentWorker],
    ]) {
      if (!enabled) continue;
      try {
        disable();
      } catch (error) {
        cleanupErrors.push(error);
      }
    }

    console.error('[6/6] removing only the discovered synthetic state');
    try {
      if (history && claim?.snapshot?.incident_id) {
        historyCleanup = cleanupHistory(config, history, claim.snapshot);
      }
      cleanupState(config, candidate, claim);
      if (queues) {
        cleanupVerification = await verifyRestored(
          config,
          queues,
          queueBaselines,
          candidate,
          claim,
        );
      }
    } catch (error) {
      cleanupErrors.push(error);
    }
    if (cleanupErrors.length > 0) {
      const message = cleanupErrors.map((error) => error.message).join('; ');
      failure = new Error(`${failure?.message ?? 'E2E cleanup failed'}; cleanup: ${message}`);
    }
  }

  if (failure) throw failure;
  result.cleanup = { ...cleanupVerification, history: historyCleanup };
  console.log(JSON.stringify(result, null, 2));
}

const invokedDirectly = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (invokedDirectly) {
  main().catch((error) => {
    console.error(`E2E_FAILED: ${error.message}`);
    process.exitCode = 1;
  });
}
