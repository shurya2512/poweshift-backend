import { DecisionEpisode, RaceProfileReport, RouteGeometry } from '@/lib/backend/report';
import { codeForEntry } from './roster';

/** The parts of a race the diagnostic report actually measures. */
export interface RaceSpec {
  totalLaps: number;
  baseLapS: number;
  selectedId: string;
  eventName: string;
  finalPosition: number;
  startingPosition: number;
  gapToLeaderS: number;
  deploymentJ: number;
  harvestJ: number;
  finalStoredJ: number;
  evidenceStatus: string;
  /** End-of-lap position the ego actually held, indexed from lap one. */
  lapPositions: number[];
  lapEnergy: { deploymentJ: number; harvestJ: number; storedEndJ: number; peakKw: number }[];
  events: { timeS: number; lap: number; label: string; detail: string | null }[];
  attacksTaken: number;
  attackOpportunities: number;
  geometry: RouteGeometry | null;
  pitLaps: number[];
  compounds: string[];
  stints: { compound: string; fromLap: number; toLap: number; tyreLifeLaps: number | null }[];
  attacks: {
    lap: number;
    startTimeS: number;
    endTimeS: number;
    ticks: number;
    taken: boolean;
    probability: number;
    peakKw: number;
    deploymentJ: number;
    storedStartJ: number;
    storedEndJ: number;
  }[];
}

const median = (values: number[]): number => {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)];
};

/** Reads one profile report into the numbers the race view renders. */
export function raceSpecFromReport(report: RaceProfileReport, geometry: RouteGeometry | null = null): RaceSpec {
  const race = report.p23;
  const laps = race.laps ?? [];
  const lapTimes = laps.map((lap) => lap.end_time_s - lap.start_time_s).filter((value) => value > 0);
  const startTime = laps[0]?.start_time_s ?? 0;
  const strategy = (report.source_strategy?.stints ?? []).map((stint) => ({
    compound: stint.compound,
    fromLap: stint.from_lap,
    toLap: stint.to_lap,
    tyreLifeLaps: stint.end_tyre_life_laps,
  }));
  return {
    totalLaps: Math.max(1, laps.length),
    baseLapS: median(lapTimes) || 88.0,
    selectedId: codeForEntry(report.profile_entry),
    eventName: report.event_name,
    finalPosition: race.final_proxy_position,
    startingPosition: race.starting_grid_position,
    gapToLeaderS: race.signed_gap_to_leader_s,
    deploymentJ: race.gross_deployment_j,
    harvestJ: race.gross_harvest_j,
    finalStoredJ: race.final_stored_energy_j,
    evidenceStatus: race.evidence_status ?? 'full_span',
    lapPositions: laps.map((lap) => lap.end_position),
    lapEnergy: laps.map((lap) => ({
      deploymentJ: lap.deployment_j,
      harvestJ: lap.harvest_j,
      storedEndJ: lap.stored_energy_end_j,
      peakKw: lap.maximum_motor_wheel_power_kw,
    })),
    events: (race.major_event_decisions ?? []).map((row) => ({
      timeS: Math.max(0, row.event.time_s - startTime),
      lap: row.nearest_policy_decision.lap,
      label: row.event.label,
      detail: row.event.detail ?? null,
    })),
    attacksTaken: race.opportunity_totals?.attack_taken ?? 0,
    attackOpportunities: race.opportunity_totals?.attack_episodes ?? 0,
    geometry,
    pitLaps: strategy.map((stint) => stint.toLap).slice(0, -1),
    compounds: strategy.map((stint) => stint.compound),
    stints: strategy,
    attacks: topAttacks(race.policy_action_episodes ?? [], laps.length),
  };
}

/** The passes the policy actually committed energy to, biggest deployment first. */
function topAttacks(episodes: DecisionEpisode[], totalLaps: number) {
  return episodes
    .filter((row) => row.kind === 'attack' && row.taken && row.lap <= totalLaps)
    .sort((a, b) => b.deployment_j - a.deployment_j)
    .slice(0, 3)
    .sort((a, b) => a.lap - b.lap)
    .map((row) => ({
      lap: row.lap,
      startTimeS: row.start_time_s,
      endTimeS: row.end_time_s,
      ticks: row.ticks,
      taken: row.taken ?? true,
      probability: row.maximum_uncalibrated_action_probability,
      peakKw: row.peak_motor_wheel_power_kw,
      deploymentJ: row.deployment_j,
      storedStartJ: row.stored_energy_start_j ?? 0,
      storedEndJ: row.stored_energy_end_j ?? 0,
    }));
}


let activeLapEnergy: RaceSpec['lapEnergy'] | null = null;

/** Holds the measured per-lap energy the current race renders. */
export function setMeasuredEnergy(spec: RaceSpec | null): void {
  activeLapEnergy = spec ? spec.lapEnergy : null;
}

/** Measured energy for one lap, or null when no report is loaded. */
export function measuredLapEnergy(lap: number): RaceSpec['lapEnergy'][number] | null {
  return activeLapEnergy?.[lap - 1] ?? null;
}
