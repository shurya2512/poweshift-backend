export interface OpportunityTotals {
  attack_episodes: number;
  attack_taken: number;
  attack_missed: number;
  defence_episodes: number;
  defence_taken: number;
  defence_missed: number;
}

export interface DecisionEpisode {
  kind?: 'attack' | 'defence';
  path?: string;
  lap: number;
  start_time_s: number;
  end_time_s: number;
  ticks: number;
  taken?: boolean;
  selected_paths?: string[];
  maximum_uncalibrated_action_probability: number;
  mean_requested_deployment_fraction?: number;
  mean_delivered_deployment_fraction?: number;
  peak_motor_wheel_power_kw: number;
  deployment_j: number;
  harvest_j: number;
  stored_energy_start_j?: number;
  stored_energy_end_j?: number;
  attack_opportunity_present?: boolean;
  defence_threat_present?: boolean;
}

export interface RaceLapDiagnostic {
  lap: number;
  start_time_s: number;
  end_time_s: number;
  start_position: number;
  end_position: number;
  deployment_j: number;
  harvest_j: number;
  stored_energy_start_j: number;
  stored_energy_end_j: number;
  mean_requested_deployment_fraction: number;
  maximum_motor_wheel_power_kw: number;
  attack_opportunity_ticks: number;
  attack_ticks: number;
  defence_threat_ticks: number;
  defend_ticks: number;
}

export interface PolicyDecision {
  time_s: number;
  lap: number;
  path: string;
  uncalibrated_action_probability: number;
  requested_deployment_fraction: number;
  motor_wheel_power_kw: number;
  deployment_j: number;
  harvest_j: number;
  stored_energy_after_j: number;
}

export interface MajorEventDecision {
  event: { time_s: number; label: string; detail?: string | null };
  nearest_policy_decision: PolicyDecision;
  decision_time_delta_s: number;
}

export interface SourceStint {
  stint: number;
  compound: string;
  from_lap: number;
  to_lap: number;
  end_tyre_life_laps: number | null;
}

export interface SourceStrategy {
  entry: string;
  status: 'source_bound' | 'unavailable';
  stints: SourceStint[];
  pit_laps: { lap: number; pit_in_time_s: number | null }[];
  total_source_laps?: number;
}

export interface RaceProfileReport {
  event_name: string;
  profile_entry: string;
  source_strategy?: SourceStrategy;
  p23: {
    ego_identity: string;
    profile_entry: string;
    starting_grid_position: number;
    reference_entries: number;
    reference_mode: string;
    reference_policy_actions: number;
    reference_electric_deployment_j: number;
    field_input_hz: number;
    decision_hz: number;
    final_proxy_position: number;
    signed_gap_to_leader_s: number;
    signed_gap_to_leader_m: number;
    evidence_status: string;
    ego_covered_span_fraction: number;
    retired_reference_entries: number;
    maximum_additive_speed_ms: number;
    gross_deployment_j: number;
    gross_harvest_j: number;
    final_stored_energy_j: number;
    probability_semantics: string;
    opportunity_totals: OpportunityTotals;
    laps: RaceLapDiagnostic[];
    opportunity_episodes: DecisionEpisode[];
    policy_action_episodes: DecisionEpisode[];
    major_event_decisions: MajorEventDecision[];
    limitations: string[];
  };
}

export interface QualifyingLapDiagnostic {
  source_lap: number;
  observed_lap_time_s: number;
  diagnostic_attainable_lap_time_s: number;
  diagnostic_time_gain_proxy_s: number;
  path: string;
  mean_uncalibrated_action_probability: number;
  mean_requested_deployment_fraction: number;
  mean_delivered_deployment_fraction: number;
  peak_motor_wheel_power_kw: number;
  gross_deployment_j: number;
  gross_harvest_j: number;
  stored_energy_start_j: number;
  stored_energy_end_j: number;
}

export interface QualifyingProfileReport {
  event_name: string;
  profile_entry: string;
  best_observed_lap_time_s: number | null;
  best_diagnostic_attainable_lap_time_s: number | null;
  gross_deployment_j: number;
  gross_harvest_j: number;
  final_stored_energy_j: number | null;
  lap_time_semantics: string;
  probability_semantics: string;
  laps: QualifyingLapDiagnostic[];
}

export interface RelievedProfile {
  profile_entry: string;
  last_sample_s: number;
  covered_span_fraction: number;
  sample_density?: number;
  reason: string;
}

export interface RouteGeometry {
  status: 'source_bound';
  closed: boolean;
  loop_closure_m: number;
  lap_length_m: number;
  point_count: number;
  x_m: number[];
  y_m: number[];
  progress_m: number[];
}

export interface DiagnosticSummary {
  event_name: string;
  status: 'diagnostic_only' | 'unavailable';
  reports?: Record<string, string>;
  reason?: string;
  profiles_without_laps?: string[];
  profiles_with_full_span?: string[];
  profiles_relieved?: RelievedProfile[];
  route_geometry?: RouteGeometry;
}

const mj = (joules: number): string => `${(joules / 1_000_000).toFixed(2)} MJ`;

export function diagnosticReportPath(
  mode: 'qualifying' | 'race',
  summaryPath: string,
  relativeReportPath: string,
): string {
  const directory = summaryPath.slice(0, summaryPath.lastIndexOf('/') + 1);
  return `${mode}/${directory}${relativeReportPath}`;
}

export function profileReportPath(summaryPath: string, relativeReportPath: string): string {
  return diagnosticReportPath('race', summaryPath, relativeReportPath);
}

export function summarizeRaceProfile(report: RaceProfileReport) {
  const race = report.p23;
  return {
    reference: {
      field: `${race.reference_entries} source cars`,
      start: 'Source-native grid',
      intelligence: race.reference_policy_actions === 0 ? 'None' : `${race.reference_policy_actions} actions`,
      electricEnergy: mj(race.reference_electric_deployment_j),
    },
    ego: {
      identity: `Profile ${report.profile_entry} ego`,
      start: `P${race.starting_grid_position}`,
      finish: `P${race.final_proxy_position}`,
      positionsGained: race.starting_grid_position - race.final_proxy_position,
      deployment: mj(race.gross_deployment_j),
      harvest: mj(race.gross_harvest_j),
    },
  };
}

export const formatEnergy = mj;
