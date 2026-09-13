import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeDiagnosticTracks } from './runtime.ts';

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
    }],
  );
});
