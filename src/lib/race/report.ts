import {
  Action,
  Battle,
  BattleSolution,
  ComparisonDelta,
  ComparisonResult,
  FlagState,
  ParticipantState,
  RaceEvent,
  RaceFrame,
  RaceOutcome,
  RacePhase,
  RaceWorld,
  ScenarioIdentity,
  SessionInfo,
  WorldSide,
} from './types';

/** One world's race as it stood when the flag fell. */
export interface WorldReport {
  side: WorldSide;
  scenario: ScenarioIdentity;
  /** The selected entry's classified result in this world. */
  outcome: RaceOutcome;
  /** The whole field in finishing order. Retired entries keep their classification. */
  classification: ParticipantState[];
  leaderLap: number;
  totalLaps: number;
  phase: RacePhase;
  flag: FlagState;
  weather: string;
  trackCondition: string;
  finished: boolean;
}

/**
 * Everything the race leaves behind, cut once both worlds have taken the flag.
 *
 * The backend sends one of these whole at the end of a session. `buildReport`
 * assembles the same shape from a finished session so the page works before that
 * message exists — neither path invents a value the session did not carry.
 */
export interface RaceReport {
  session: SessionInfo;
  /** The one clock both worlds are read at. Worlds are never cut at different times. */
  finalRaceTimeS: number;
  baseline: WorldReport;
  alternative: WorldReport;
  comparison: ComparisonResult;
  /** The selected entry's standing delta at the flag. */
  delta: ComparisonDelta;
  events: RaceEvent[];
  battles: Battle[];
  selectedParticipantId: string;
}

/**
 * A decision window our car came out of ahead of the car it was behind.
 *
 * `chosen` is the line the model returned; `rejected` are the others that were open to
 * us in the same window. Both come from the battle as supplied — nothing here decides
 * which line was right.
 */
export interface OvertakeMove {
  battle: Battle;
  chosen: BattleSolution;
  chosenAction?: Action;
  rejected: Action[];
  /** The defender's expected answer to the chosen line, when the solution names one. */
  response?: Action;
}

/**
 * Passes by one entry: it attacked, and the solution's order puts it ahead.
 *
 * Takes the battles rather than a report, so the live race page can read the same
 * moves off the session before a report exists to cut.
 */
export function findOvertakeMoves(battles: Battle[], id: string): OvertakeMove[] {
  return battles
    .filter((battle) => battle.attackerId === id)
    .flatMap((battle) =>
      battle.solutions
        .filter((solution) => {
          const order = solution.outcome.resultingOrder;
          const ours = order.indexOf(id);
          const theirs = order.indexOf(battle.defenderId);
          return ours !== -1 && theirs !== -1 && ours < theirs;
        })
        .map((chosen) => ({
          battle,
          chosen,
          chosenAction: battle.actions.find((a) => a.id === chosen.actionId),
          rejected: battle.actions.filter((a) => a.participantId === id && a.id !== chosen.actionId),
          response: battle.actions.find((a) => a.id === chosen.response.actionId),
        })),
    );
}

/** The selected entry's passes, read off a finished report. */
export function findOvertakes(report: RaceReport): OvertakeMove[] {
  return findOvertakeMoves(report.battles, report.selectedParticipantId);
}

/** A running race has no result yet, so a report is only cut once both worlds finish. */
export function isReportReady(frame: RaceFrame | null): frame is RaceFrame {
  return !!frame && frame.baseline.finished && frame.alternative.finished;
}

const worldReport = (world: RaceWorld, outcome: RaceOutcome): WorldReport => ({
  side: world.side,
  scenario: world.scenario,
  outcome,
  classification: world.field,
  leaderLap: world.leaderLap,
  totalLaps: world.totalLaps,
  phase: world.phase,
  flag: world.flag,
  weather: world.weather,
  trackCondition: world.trackCondition,
  finished: world.finished,
});

export interface ReportInput {
  session: SessionInfo | null;
  frame: RaceFrame | null;
  comparison: ComparisonResult | null;
  events: RaceEvent[];
  battles: Battle[];
  selectedParticipantId: string | null;
}

/**
 * Null until the session carries a finished frame and a comparison — a report with
 * a missing half is not a smaller report, it is not a report.
 */
export function buildReport(input: ReportInput): RaceReport | null {
  const { session, frame, comparison } = input;
  if (!session || !comparison || !isReportReady(frame)) return null;

  return {
    session,
    finalRaceTimeS: frame.raceTimeS,
    baseline: worldReport(frame.baseline, comparison.baseline),
    alternative: worldReport(frame.alternative, comparison.alternative),
    comparison,
    delta: frame.delta,
    events: input.events,
    battles: input.battles,
    selectedParticipantId: input.selectedParticipantId ?? session.selectedParticipantId,
  };
}
