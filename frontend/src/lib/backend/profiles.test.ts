import assert from 'node:assert/strict';
import test from 'node:test';
import { EGO_PROFILES, sessionTracks } from './profiles.ts';

test('offers every promoted ego profile exactly once', () => {
  assert.equal(EGO_PROFILES.length, 22);
  assert.equal(new Set(EGO_PROFILES.map((profile) => profile.entry)).size, 22);
  assert.deepEqual(
    EGO_PROFILES.map((profile) => profile.entry).sort((a, b) => Number(a) - Number(b)),
    ['1', '3', '5', '6', '10', '11', '12', '14', '16', '18', '23', '27', '30', '31', '41', '43', '44', '55', '63', '77', '81', '87'],
  );
});

test('keeps qualifying and race circuits on their diagnostic report sets', () => {
  assert.equal(sessionTracks('qualifying').length, 10);
  assert.deepEqual(
    sessionTracks('full-race').map((track) => track.event),
    ['Miami Grand Prix', 'Barcelona Grand Prix', 'Austrian Grand Prix', 'British Grand Prix'],
  );
});
