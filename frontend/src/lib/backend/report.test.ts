import assert from 'node:assert/strict';
import test from 'node:test';
import { profileReportPath, summarizeRaceProfile } from './report.ts';

test('builds the profile report path relative to its race summary', () => {
  assert.equal(
    profileReportPath('barcelona/summary.json', 'reports/entry-11.json'),
    'race/barcelona/reports/entry-11.json',
  );
});

test('keeps the P23 ego separate from the policy-free reference field', () => {
  const summary = summarizeRaceProfile({
    event_name: 'Barcelona Grand Prix',
    profile_entry: '11',
    p23: {
      ego_identity: 'policy-profile-11-p23',
      profile_entry: '11',
      starting_grid_position: 23,
      reference_entries: 22,
      reference_mode: 'source_native_reference_field_replay',
      reference_policy_actions: 0,
      reference_electric_deployment_j: 0,
      field_input_hz: 4,
      decision_hz: 5,
      final_proxy_position: 18,
      signed_gap_to_leader_s: -12.5,
      signed_gap_to_leader_m: -420,
      evidence_status: 'full_span',
      ego_covered_span_fraction: 1,
      retired_reference_entries: 3,
      maximum_additive_speed_ms: 5,
      gross_deployment_j: 4_500_000,
      gross_harvest_j: 900_000,
      final_stored_energy_j: 1_000_000,
      probability_semantics: 'uncalibrated_action_selection_probability',
      opportunity_totals: {
        attack_episodes: 2,
        attack_taken: 1,
        attack_missed: 1,
        defence_episodes: 1,
        defence_taken: 0,
        defence_missed: 1,
      },
      laps: [],
      opportunity_episodes: [],
      policy_action_episodes: [],
      major_event_decisions: [],
      limitations: [],
    },
  });

  assert.deepEqual(summary.reference, {
    field: '22 source cars',
    start: 'Source-native grid',
    intelligence: 'None',
    electricEnergy: '0.00 MJ',
  });
  assert.deepEqual(summary.ego, {
    identity: 'Profile 11 ego',
    start: 'P23',
    finish: 'P18',
    positionsGained: 5,
    deployment: '4.50 MJ',
    harvest: '0.90 MJ',
  });
});
