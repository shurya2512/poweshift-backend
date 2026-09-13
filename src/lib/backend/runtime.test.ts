import assert from 'node:assert/strict';
import test from 'node:test';
import {
  controlRun,
  fetchLatestRecommendation,
  fetchRunReport,
  normalizeDiagnosticTracks,
  startRegisteredRun,
  streamRegisteredRun,
} from './runtime.ts';

test('accepts qualifying rows that omit race-only status', () => {
  assert.deepEqual(
    normalizeDiagnosticTracks([
      { event_name: 'Spanish Grand Prix', summary: 'spanish/summary.json', partition: 'final_evaluation' },
    ], 'qualifying'),
    [{
      event_name: 'Spanish Grand Prix',
      summary: 'spanish/summary.json',
      status: 'diagnostic_only',
      mode: 'qualifying',
      profiles: [],
    }],
  );
});

test('carries the admitted profile roster on a race row', () => {
  assert.deepEqual(
    normalizeDiagnosticTracks([
      { event_name: 'Barcelona Grand Prix', summary: 'barcelona/summary.json', status: 'diagnostic_only', profiles: ['1', 23] },
    ], 'race'),
    [{
      event_name: 'Barcelona Grand Prix',
      summary: 'barcelona/summary.json',
      status: 'diagnostic_only',
      mode: 'race',
      profiles: ['1', '23'],
    }],
  );
});

// Stubs global fetch with a queue of canned responses for the duration of one test.
function stubFetch(responses: Response[]): () => void {
  const original = globalThis.fetch;
  const queue = [...responses];
  globalThis.fetch = (async () => {
    const next = queue.shift();
    if (!next) throw new Error('stubFetch: no more responses queued');
    return next;
  }) as typeof fetch;
  return () => {
    globalThis.fetch = original;
  };
}

test('425 from the recommendation endpoint resolves to null, not an error', async () => {
  const restore = stubFetch([new Response(null, { status: 425 })]);
  try {
    assert.equal(await fetchLatestRecommendation('selection-run'), null);
  } finally {
    restore();
  }
});

test('425 from the report endpoint resolves to null, not an error', async () => {
  const restore = stubFetch([new Response(null, { status: 425 })]);
  try {
    assert.equal(await fetchRunReport('selection-run'), null);
  } finally {
    restore();
  }
});

test('404 from a run endpoint throws, unlike a 425', async () => {
  const restore = stubFetch([
    new Response(JSON.stringify({ detail: "'run is not known: ghost-run'" }), { status: 404 }),
  ]);
  try {
    await assert.rejects(() => fetchLatestRecommendation('ghost-run'));
  } finally {
    restore();
  }
});

test('an already-known run resolves without issuing a POST', async () => {
  let calls = 0;
  const original = globalThis.fetch;
  globalThis.fetch = (async () => {
    calls += 1;
    return new Response(
      JSON.stringify({ run_id: 'selection-run', status: 'running', recommendation_count: 0, error: null }),
      { status: 200 },
    );
  }) as typeof fetch;
  try {
    await assert.doesNotReject(() => startRegisteredRun('selection-run'));
    assert.equal(calls, 1);
  } finally {
    globalThis.fetch = original;
  }
});

test('a benign 409 (run already known) lets the run start proceed', async () => {
  // Status check misses first (unknown run), forcing the POST, which then races
  // and hits a benign 409; the follow-up status check resolves.
  const restore = stubFetch([
    new Response(JSON.stringify({ detail: "'run is not known: selection-run'" }), { status: 404 }),
    new Response(JSON.stringify({ detail: 'run is already known to this supervisor' }), { status: 409 }),
    new Response(
      JSON.stringify({ run_id: 'selection-run', status: 'running', recommendation_count: 0, error: null }),
      { status: 200 },
    ),
  ]);
  try {
    await assert.doesNotReject(() => startRegisteredRun('selection-run'));
  } finally {
    restore();
  }
});

test('a fatal 409 (stale run output) throws a distinguishable error', async () => {
  const restore = stubFetch([
    new Response(JSON.stringify({ detail: "'run is not known: selection-run'" }), { status: 404 }),
    new Response(
      JSON.stringify({ detail: 'run output already exists: /data/runs/selection-run' }),
      { status: 409 },
    ),
    new Response(JSON.stringify({ detail: "'run is not known: selection-run'" }), { status: 404 }),
  ]);
  try {
    await assert.rejects(
      () => startRegisteredRun('selection-run'),
      /output already exists|cannot be started|cannot be restarted/,
    );
  } finally {
    restore();
  }
});

test('control sends the command and rejects on a non-ok response', async () => {
  const restore = stubFetch([new Response(null, { status: 200 })]);
  try {
    await assert.doesNotReject(() => controlRun('selection-run', 'pause'));
  } finally {
    restore();
  }
});

test('afterSequence is appended to the stream websocket URL as a query parameter', () => {
  const original = globalThis.WebSocket;
  let capturedUrl = '';
  class FakeWebSocket {
    onmessage: ((event: MessageEvent) => void) | null = null;
    onerror: (() => void) | null = null;
    constructor(url: string) {
      capturedUrl = url;
    }
    close() {}
  }
  globalThis.WebSocket = FakeWebSocket as unknown as typeof WebSocket;
  try {
    const close = streamRegisteredRun('selection-run', () => {}, () => {}, 42);
    close();
    assert.match(capturedUrl, /after_sequence=42/);
  } finally {
    globalThis.WebSocket = original;
  }
});

test('omitting afterSequence leaves the stream websocket URL unchanged', () => {
  const original = globalThis.WebSocket;
  let capturedUrl = '';
  class FakeWebSocket {
    onmessage: ((event: MessageEvent) => void) | null = null;
    onerror: (() => void) | null = null;
    constructor(url: string) {
      capturedUrl = url;
    }
    close() {}
  }
  globalThis.WebSocket = FakeWebSocket as unknown as typeof WebSocket;
  try {
    const close = streamRegisteredRun('selection-run', () => {}, () => {});
    close();
    assert.doesNotMatch(capturedUrl, /after_sequence/);
    assert.match(capturedUrl, /\/runs\/selection-run\/stream$/);
  } finally {
    globalThis.WebSocket = original;
  }
});
