import {
  Battle,
  ComparisonResult,
  EventKind,
  PlannedStint,
  RaceEvent,
  RaceFrame,
  RaceOutcome,
  ScenarioIdentity,
  SessionInfo,
  StrategyBrief,
  WorldSide,
} from '../types';
import { inferred, observed, predicted, simulated } from '../valued';
import { battlesFromReport, buildBattles } from './battles';
import { positionChangeEvents } from './positions';
import { RaceSpec } from './report';
import { ROSTER, byId } from './roster';
import { buildTrack } from './track';
import { buildWorld } from './world';
import {
  ALTERNATIVE_PLAN,
  BASELINE_PLAN,
  BRANCH_LAP,
  applyRaceSpec,
  Neutralisation,
  RETIREMENT_ID,
  RETIREMENT_LAP,
  SELECTED_ID,
  TOTAL_LAPS,
  WorldPlan,
  WorldTiming,
  buildTiming,
  pitLapsFor,
  worldDuration,
} from './model';

const BASELINE_SCENARIO: ScenarioIdentity = {
  id: 'baseline-recorded',
  name: 'Recorded race',
  purpose: 'The race as it was run, used as the reference for every comparison',
  opponentFormulation: 'recorded',
};

const ALTERNATIVE_SCENARIO: ScenarioIdentity = {
  id: 'alt-one-stop',
  name: 'One-stop, stay out at lap 12',
  purpose: 'Extend the opening stint and take a single stop on lap 20',
  parentBranch: 'baseline-recorded',
  opponentFormulation: 'recorded',
};

/** Cumulative race time at the end of a given lap, for one entry. */
const lapEnd = (timing: WorldTiming, id: string, lap: number): number =>
  timing.get(id)?.[lap - 1] ?? 0;

const NEUTRALISATION_LABEL: Record<Neutralisation['kind'], string> = {
  safety_car: 'Safety car',
  virtual_safety_car: 'Virtual safety car',
};

const sameNeutralisation = (a: Neutralisation, b: Neutralisation): boolean =>
  a.kind === b.kind && a.fromLap === b.fromLap && a.toLap === b.toLap;

/**
 * One event per neutralisation rather than a deployed/withdrawn pair, so the stretch of
 * race time it covers is carried on the event itself and can be drawn as a period.
 * A neutralisation both races carry is shared history, emitted once from the baseline.
 */
function neutralisationEvents(
  side: WorldSide,
  plan: WorldPlan,
  other: WorldPlan,
  timing: WorldTiming,
): RaceEvent[] {
  const at = (lap: number) => lapEnd(timing, SELECTED_ID, lap);

  return plan.neutralisations.flatMap((n) => {
    const shared = other.neutralisations.some((o) => sameNeutralisation(n, o));
    if (shared && side === 'alternative') return [];
    return [
      {
        id: `${shared ? 'shared' : side}-${n.kind}-${n.fromLap}`,
        world: shared ? ('shared' as const) : side,
        group: 'session_control' as const,
        kind: n.kind,
        raceTimeS: at(n.fromLap - 1),
        periodEndS: at(n.toLap),
        lap: n.fromLap,
        label: `${NEUTRALISATION_LABEL[n.kind]}, laps ${n.fromLap}–${n.toLap}`,
      },
    ];
  });
}

function eventsFor(
  side: WorldSide,
  plan: WorldPlan,
  timing: WorldTiming,
): RaceEvent[] {
  const out: RaceEvent[] = [];
  const at = (lap: number, id = SELECTED_ID) => lapEnd(timing, id, lap);

  for (const lap of pitLapsFor(plan, SELECTED_ID)) {
    out.push({
      id: `${side}-ver-pit-${lap}`,
      world: side,
      group: 'strategy',
      kind: 'pit_stop',
      raceTimeS: at(lap),
      lap,
      participantId: SELECTED_ID,
      label: `VER pit stop, lap ${lap}`,
    });
  }

  out.push({
    id: `${side}-field-stop-2`,
    world: side,
    group: 'strategy',
    raceTimeS: at(22, 'NOR'),
    lap: 22,
    label: 'Field second stop window',
  });

  if (side === 'alternative') {
    out.push({
      id: 'alt-branch',
      world: 'alternative',
      group: 'strategy',
      raceTimeS: at(BRANCH_LAP),
      lap: BRANCH_LAP,
      participantId: SELECTED_ID,
      label: 'VER stays out — worlds separate here',
    });
  }

  out.push({
    id: `${side}-ver-finish`,
    world: side,
    group: 'outcome',
    kind: 'chequered',
    raceTimeS: at(TOTAL_LAPS),
    lap: TOTAL_LAPS,
    participantId: SELECTED_ID,
    label: 'VER takes the chequered flag',
  });

  return out;
}

/** Events before the branch point, identical in both worlds. */
function sharedEvents(timing: WorldTiming): RaceEvent[] {
  return [
    {
      id: 'shared-start',
      world: 'shared',
      group: 'session_control',
      kind: 'start',
      raceTimeS: 0,
      lap: 1,
      label: 'Race start',
    },
    {
      id: 'shared-str-retire',
      world: 'shared',
      group: 'outcome',
      kind: 'retirement',
      raceTimeS: lapEnd(timing, RETIREMENT_ID, RETIREMENT_LAP),
      lap: RETIREMENT_LAP,
      participantId: RETIREMENT_ID,
      label: 'STR retires — power unit',
    },
    {
      id: 'shared-field-stop-1',
      world: 'shared',
      group: 'strategy',
      raceTimeS: lapEnd(timing, 'NOR', 10),
      lap: 10,
      label: 'Field first stop window',
    },
  ];
}

function outcomeFor(plan: WorldPlan, timing: WorldTiming, rank: number, spec: RaceSpec | null): RaceOutcome {
  const total = lapEnd(timing, SELECTED_ID, TOTAL_LAPS);
  const finish = spec ? spec.finalPosition : rank;
  const mark = <T,>(v: T) =>
    plan.side === 'baseline' ? observed(v, 'official classification', total) : simulated(v, ALTERNATIVE_SCENARIO.id, ['fixed-opponent replay']);
  return {
    finishPosition: mark(finish),
    classifiedStatus: 'Classified',
    totalTimeS: mark(Number(total.toFixed(2))),
    points: mark(rank === 1 ? 25 : rank === 2 ? 18 : 15),
    pitCount: plan.selectedPitLaps.length,
    tyreUse: plan.selectedCompounds.join(' → '),
  };
}

/** The stints a set of pit laps and compounds describes, as inclusive lap ranges. */
function stintsOf(pitLaps: number[], compounds: string[]): PlannedStint[] {
  const starts = [1, ...pitLaps.map((l) => l + 1)];
  return compounds.map((compound, i) => ({
    compound,
    fromLap: starts[i],
    toLap: i === compounds.length - 1 ? TOTAL_LAPS : pitLaps[i],
  }));
}

const SOURCE_EVENT: Record<string, { label: string; kind?: EventKind }> = {
  yellow: { label: 'Yellow flag' },
  safety_car_deployed: { label: 'Safety car', kind: 'safety_car' },
  vsc_deployed: { label: 'Virtual safety car', kind: 'virtual_safety_car' },
  vsc_ending: { label: 'Virtual safety car ending', kind: 'virtual_safety_car' },
  red: { label: 'Red flag', kind: 'red_flag' },
};

/** Track-status events the source race actually recorded. */
function sourceEvents(spec: RaceSpec): RaceEvent[] {
  return spec.events.map((event, index) => {
    const known = SOURCE_EVENT[event.label];
    return {
      id: `source-event-${index}`,
      world: 'shared' as const,
      group: 'session_control' as const,
      kind: known?.kind,
      raceTimeS: event.timeS,
      lap: event.lap,
      label: event.detail ?? known?.label ?? event.label,
    };
  });
}

export interface FixtureRace {
  session: SessionInfo;
  events: RaceEvent[];
  comparison: ComparisonResult;
  battles: Battle[];
  frameAt(raceTimeS: number): RaceFrame;
  durationS: number;
}

export function buildFixtureRace(spec: RaceSpec | null = null): FixtureRace {
  applyRaceSpec(spec);
  const track = buildTrack(spec ? spec.eventName : 'Autodromo Fixture', spec?.geometry ?? null);
  const baselineTiming = buildTiming(BASELINE_PLAN);
  const alternativeTiming = buildTiming(ALTERNATIVE_PLAN);
  const durationS = Math.max(worldDuration(baselineTiming), worldDuration(alternativeTiming));

  const rankOf = (timing: WorldTiming): number => {
    const total = lapEnd(timing, SELECTED_ID, TOTAL_LAPS);
    return (
      ROSTER.filter((e) => e.id !== RETIREMENT_ID)
        .map((e) => lapEnd(timing, e.id, TOTAL_LAPS))
        .filter((v) => v > 0 && v < total).length + 1
    );
  };

  const baselineOutcome = outcomeFor(BASELINE_PLAN, baselineTiming, rankOf(baselineTiming), null);
  const alternativeOutcome = outcomeFor(ALTERNATIVE_PLAN, alternativeTiming, rankOf(alternativeTiming), spec);
  const relativeTime =
    lapEnd(alternativeTiming, SELECTED_ID, TOTAL_LAPS) - lapEnd(baselineTiming, SELECTED_ID, TOTAL_LAPS);

  const branchTimeS = lapEnd(baselineTiming, SELECTED_ID, BRANCH_LAP);

  /**
   * The call we were handed before the race: run the recorded car's two-stop, and be
   * inside the top two at the flag. The expectation is `predicted` because it was made
   * before anything was observed — cutoff 0, horizon the whole race.
   */
  const brief: StrategyBrief = {
    author: 'Team principal',
    car: byId(SELECTED_ID).team,
    stints: spec && spec.stints.length > 0
      ? spec.stints.map((stint) => ({ compound: stint.compound, fromLap: stint.fromLap, toLap: stint.toLap }))
      : stintsOf(BASELINE_PLAN.selectedPitLaps, BASELINE_PLAN.selectedCompounds),
    pitLaps: spec ? spec.pitLaps : BASELINE_PLAN.selectedPitLaps,
    expectedFinishPosition: predicted(spec ? spec.finalPosition : 2, 0, durationS, [1, 4]),
    note: spec
      ? `Recorded strategy for car #${byId(SELECTED_ID).raceNumber}: ${spec.stints.length} ${spec.stints.length === 1 ? 'stint' : 'stints'} on ${spec.compounds.join(' → ').toLowerCase()}, stopping on ${spec.pitLaps.length > 0 ? `lap ${spec.pitLaps.join(' and ')}` : 'no lap'}.`
      : 'Two stops, both inside the primary window. Stay out past lap 12 only if the race is neutralised.',
  };

  const session: SessionInfo = {
    identity: {
      season: 2026,
      event: spec ? spec.eventName : 'Fixture Grand Prix',
      circuit: spec ? spec.eventName : 'Autodromo Fixture',
      session: 'Race',
      rulesVersion: '2026',
    },
    mode: 'counterfactual',
    timeBoundary: {
      observationCutoffS: durationS,
      generatedAtMs: Date.UTC(2026, 8, 9, 14, 0, 0),
      latestAcceptedUpdateMs: Date.UTC(2026, 8, 9, 14, 0, 0),
    },
    supportState: 'ready',
    branchPoint: {
      raceTimeS: branchTimeS,
      lap: BRANCH_LAP,
      description: 'VER pit call on lap 12',
      eventId: 'alt-branch',
    },
    brief,
    assumptions: {
      weather: 'Dry throughout, no forecast change',
      interruptions: spec
        ? `${spec.events.length} recorded track-status events, taken from the source race`
        : 'Virtual safety car on laps 5–6 in both races; safety car on laps 15–17 in the alternative world only',
      pitLossS: inferred(22.0, [20.4, 23.8]),
      tyreSets: spec ? `Recorded stints: ${spec.compounds.join(' → ').toLowerCase()}` : 'Two new mediums and one new hard available at the branch',
      startingStates: spec ? `Our car is added at P${spec.startingPosition} behind the recorded field` : 'Both worlds identical up to lap 12',
      opponentBeliefs: 'Recorded opponents — they do not react to the changed call',
    },
    validity: {
      supportedHorizonS: durationS,
      warnings: spec
        ? [
            `Measured from the ${spec.eventName} diagnostic report for car ${spec.selectedId}`,
            'Only our car is measured; the rest of the field is an illustrative running order',
          ]
        : [
            'Opponents are recorded and do not respond to the alternative pit call',
            'One entry has no energy telemetry coverage',
          ],
      fallbacks: [],
    },
    coverage: {
      availableSessions: ['Race'],
      missingInputs: ['Per-entry battery truth', 'Defensive racing lines'],
      permittedEvidence: ['Timing feed', 'Official classification', 'Fitted car profile'],
    },
    participants: ROSTER.map(({ id, code, name, team, raceNumber, teamColor }) => ({
      id,
      code,
      name,
      team,
      raceNumber,
      teamColor,
    })),
    track: track.geometry,
    durationS,
    rateHz: 4,
    selectedParticipantId: SELECTED_ID,
  };

  // Battles are declared against the recorded baseline, and surface on the timeline
  // as competition events so they can be opened from it.
  const battles = spec && spec.attacks.length > 0
    ? battlesFromReport(spec)
    : buildBattles((id, lap) => lapEnd(baselineTiming, id, lap));
  const battleEvents: RaceEvent[] = battles.map((b) => ({
    id: `battle-event-${b.id}`,
    world: b.lap <= BRANCH_LAP ? 'shared' : b.baselineSide,
    group: 'competition',
    kind:
      b.attackerId === SELECTED_ID
        ? ('overtake' as const)
        : b.defenderId === SELECTED_ID
          ? ('overtaken' as const)
          : undefined,
    raceTimeS: b.windowStartS,
    lap: b.lap,
    participantId: b.attackerId,
    label: `${b.attackerId} v ${b.defenderId} — ${b.location.split(',')[0]}`,
  }));

  // A lap our car fought over is already on the timeline as that battle, so the
  // position change derived for the same pair on the same lap is not repeated.
  const covered = new Set(
    battles
      .filter((b) => b.attackerId === SELECTED_ID || b.defenderId === SELECTED_ID)
      .map((b) => {
        const other = b.attackerId === SELECTED_ID ? b.defenderId : b.attackerId;
        const world = b.lap <= BRANCH_LAP ? 'shared' : b.baselineSide;
        return `${world}|${b.lap}|${other}`;
      }),
  );

  const positionEvents = [
    ...positionChangeEvents('baseline', BASELINE_PLAN, baselineTiming),
    ...positionChangeEvents('alternative', ALTERNATIVE_PLAN, alternativeTiming),
  ]
    .filter(({ event, otherId }) => !covered.has(`${event.world}|${event.lap}|${otherId}`))
    .map(({ event }) => event);

  const events = [
    ...battleEvents,
    ...positionEvents,
    ...sharedEvents(baselineTiming),
    ...(spec
      ? sourceEvents(spec)
      : [
          ...neutralisationEvents('baseline', BASELINE_PLAN, ALTERNATIVE_PLAN, baselineTiming),
          ...neutralisationEvents('alternative', ALTERNATIVE_PLAN, BASELINE_PLAN, alternativeTiming),
        ]),
    ...eventsFor('baseline', BASELINE_PLAN, baselineTiming),
    ...eventsFor('alternative', ALTERNATIVE_PLAN, alternativeTiming),
  ].sort((a, b) => a.raceTimeS - b.raceTimeS);

  const comparison: ComparisonResult = {
    branchPoint: session.branchPoint,
    evidenceCutoffS: durationS,
    baseline: baselineOutcome,
    alternative: alternativeOutcome,
    relativeTimeS: simulated(Number(relativeTime.toFixed(2)), ALTERNATIVE_SCENARIO.id, [
      'Recorded opponents',
      'Safety car on laps 15–17',
    ]),
    relativePositions: simulated(
      rankOf(alternativeTiming) - rankOf(baselineTiming),
      ALTERNATIVE_SCENARIO.id,
      ['Recorded opponents'],
    ),
    relativePoints: simulated(0, ALTERNATIVE_SCENARIO.id, ['Points model not supplied']),
    stability: {
      preferredScenarioId: ALTERNATIVE_SCENARIO.id,
      cases: [
        {
          assumption: 'Declared assumptions — safety car on laps 15–17',
          preferredScenarioId: ALTERNATIVE_SCENARIO.id,
          outcomeSummary: 'One stop taken under neutralisation; P1 against P3 in the baseline',
        },
        {
          assumption: 'No safety car',
          preferredScenarioId: BASELINE_SCENARIO.id,
          outcomeSummary: 'The stop costs full pit loss and the stint is 4 laps too long — the two-stop wins',
        },
        {
          assumption: 'Safety car two laps later, on laps 17–19',
          preferredScenarioId: ALTERNATIVE_SCENARIO.id,
          outcomeSummary: 'Still favours staying out, with a narrower margin',
        },
        {
          assumption: 'Opponents respond to the changed call instead of being recorded',
          preferredScenarioId: 'unresolved',
          outcomeSummary: 'Not supported — no responsive opponent model is supplied for this race',
        },
      ],
      changesUnderSupportedAssumption: true,
      note:
        'The alternative is preferred only because a safety car falls inside its stint. Remove that interruption and the preference reverses, so the interruption is part of the result, not background.',
    },
  };

  let sequence = 0;

  const frameAt = (raceTimeS: number): RaceFrame => {
    const baseline = buildWorld('baseline', BASELINE_SCENARIO, BASELINE_PLAN, baselineTiming, track, raceTimeS);
    const alternative = buildWorld(
      'alternative',
      ALTERNATIVE_SCENARIO,
      ALTERNATIVE_PLAN,
      alternativeTiming,
      track,
      raceTimeS,
    );
    const selectedBaseline = baseline.field.find((p) => p.participantId === SELECTED_ID);
    const selectedAlternative = alternative.field.find((p) => p.participantId === SELECTED_ID);
    const entry = byId(SELECTED_ID);

    const positionDelta = (selectedAlternative?.rank ?? 0) - (selectedBaseline?.rank ?? 0);
    const beforeBranch = raceTimeS < branchTimeS;

    return {
      raceTimeS,
      sequence: sequence++,
      baseline,
      alternative,
      delta: {
        positionDelta: simulated(positionDelta, ALTERNATIVE_SCENARIO.id, ['Recorded opponents']),
        timeDeltaS: simulated(
          Number(
            (
              ((selectedBaseline?.lap ?? 0) - (selectedAlternative?.lap ?? 0)) *
              (88 + entry.paceOffsetS)
            ).toFixed(2),
          ),
          ALTERNATIVE_SCENARIO.id,
          ['Recorded opponents'],
        ),
        strategyDivergence: beforeBranch
          ? ['Shared history — worlds are identical']
          : [
              `Baseline on ${pitLapsFor(BASELINE_PLAN, SELECTED_ID).length} stops, alternative on ${pitLapsFor(ALTERNATIVE_PLAN, SELECTED_ID).length}`,
              'Safety car in the alternative world only',
            ],
      },
      freshnessMs: 0,
      forecastHorizonS: undefined,
    };
  };

  return { session, events, comparison, battles, frameAt, durationS };
}
