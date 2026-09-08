import { Valued } from './valued';

// ── Race identity and freshness ──────────────────────────────────────────────

export interface RaceIdentity {
  season: number;
  event: string;
  circuit: string;
  session: string;
  rulesVersion: string;
}

/** How the displayed race worlds were produced. Never inferred by the frontend. */
export type ExperienceMode =
  | 'recorded_replay'
  | 'conditional_replay'
  | 'forward_forecast'
  | 'counterfactual';

export interface TimeBoundary {
  /** Race seconds up to which observations were accepted. */
  observationCutoffS: number;
  /** Wall-clock ms when this session was produced. */
  generatedAtMs: number;
  latestAcceptedUpdateMs: number;
}

export type SupportState =
  | 'ready'
  | 'partial'
  | 'stale'
  | 'unsupported'
  | 'abstained'
  | 'failed';

export type FlagState =
  | 'green'
  | 'yellow'
  | 'safety_car'
  | 'virtual_safety_car'
  | 'red'
  | 'chequered';

export type RacePhase = 'formation' | 'racing' | 'suspended' | 'finished';

// ── Scenario identity ────────────────────────────────────────────────────────

/** Where the two worlds separate. Everything before this is shared history. */
export interface BranchPoint {
  raceTimeS: number;
  lap: number;
  description: string;
  eventId?: string;
}

export type OpponentFormulation =
  | 'recorded'
  | 'fitted_stochastic'
  | 'sequential'
  | 'simultaneous'
  | 'learned';

export interface ScenarioIdentity {
  id: string;
  name: string;
  purpose: string;
  parentBranch?: string;
  opponentFormulation: OpponentFormulation;
}

export interface Assumptions {
  weather: string;
  interruptions: string;
  pitLossS: Valued<number>;
  tyreSets: string;
  startingStates: string;
  opponentBeliefs: string;
}

export interface Validity {
  supportedHorizonS: number;
  warnings: string[];
  fallbacks: string[];
  abstentionReason?: string;
}

export interface DataCoverage {
  availableSessions: string[];
  missingInputs: string[];
  permittedEvidence: string[];
}

// ── Participants ─────────────────────────────────────────────────────────────

export type ParticipationState =
  | 'running'
  | 'in_pit'
  | 'retired'
  | 'finished'
  | 'disqualified';

export interface Participant {
  id: string;
  code: string;
  name: string;
  team: string;
  raceNumber: number;
  teamColor: string;
}

/**
 * Energy accounting kept as separate quantities. A single net battery number
 * must not replace this when the richer values are available.
 */
export interface EnergyState {
  storedMj: Valued<number>;
  requestedKw: Valued<number>;
  deliveredKw: Valued<number>;
  recoveredKw: Valued<number>;
  curtailedKw: Valued<number>;
}

export interface TyreState {
  compound: Valued<string>;
  ageLaps: Valued<number>;
  conditionPct: Valued<number>;
}

export interface TrafficState {
  aheadId?: string;
  behindId?: string;
  gapAheadS: Valued<number>;
  gapBehindS: Valued<number>;
}

/** One participant's state inside one race world at one frame. */
export interface ParticipantState {
  participantId: string;
  participation: ParticipationState;
  rank: number;
  lap: number;
  /** Distance along the lap in metres. */
  distanceM: number;
  x: number;
  y: number;
  speedKmh: Valued<number>;
  /** Gap to the leader. */
  gapS: Valued<number>;
  /** Gap to the car ahead on the road. */
  intervalS: Valued<number>;
  /** Track sector, 1-3. */
  sector: Valued<number>;
  lapsDown: number;
  tyre: TyreState;
  energy: EnergyState;
  fuelKg: Valued<number>;
  paceTarget: Valued<string>;
  energyTarget: Valued<string>;
  strategyInstruction: Valued<string>;
  traffic: TrafficState;
}

// ── Race worlds and frames ───────────────────────────────────────────────────

export type WorldSide = 'baseline' | 'alternative';

export interface TrackGeometry {
  name: string;
  x: number[];
  y: number[];
  lapLengthM: number;
}

/**
 * One coherent race. Baseline and alternative keep separate lap counts, order,
 * events and finish states — they are never merged into one classification.
 */
export interface RaceWorld {
  side: WorldSide;
  scenario: ScenarioIdentity;
  leaderLap: number;
  totalLaps: number;
  phase: RacePhase;
  flag: FlagState;
  weather: string;
  trackCondition: string;
  /** Ordered by rank. Retired and finished entries keep their classification. */
  field: ParticipantState[];
  finished: boolean;
}

export interface ComparisonDelta {
  positionDelta: Valued<number>;
  timeDeltaS: Valued<number>;
  /** Short lines naming where the two plans currently differ. */
  strategyDivergence: string[];
}

export interface RaceFrame {
  /** Shared comparison clock, in race seconds. */
  raceTimeS: number;
  /** Monotonic. A frame with an older sequence is dropped. */
  sequence: number;
  baseline: RaceWorld;
  alternative: RaceWorld;
  /** Deltas for the selected driver. Computed by the source, never by a view. */
  delta: ComparisonDelta;
  freshnessMs: number;
  forecastHorizonS?: number;
}

// ── Events ───────────────────────────────────────────────────────────────────

export type EventGroup =
  | 'session_control'
  | 'strategy'
  | 'competition'
  | 'environment'
  | 'outcome'
  | 'model';

export interface RaceEvent {
  id: string;
  /** `shared` only when the event stays identical after the branch point. */
  world: WorldSide | 'shared';
  group: EventGroup;
  raceTimeS: number;
  lap: number;
  participantId?: string;
  label: string;
}

// ── Comparison results ───────────────────────────────────────────────────────

export interface RaceOutcome {
  finishPosition: Valued<number>;
  classifiedStatus: string;
  totalTimeS: Valued<number>;
  points: Valued<number>;
  pitCount: number;
  tyreUse: string;
}

export interface ComparisonResult {
  branchPoint: BranchPoint;
  /** Both outcomes must share this cutoff to be compared directly. */
  evidenceCutoffS: number;
  baseline: RaceOutcome;
  alternative: RaceOutcome;
  relativeTimeS: Valued<number>;
  relativePositions: Valued<number>;
  relativePoints: Valued<number>;
  /** Robustness across credible assumptions, and whether the preference flips. */
  stability?: DecisionStability;
}

// ── Session ──────────────────────────────────────────────────────────────────

export interface SessionInfo {
  identity: RaceIdentity;
  mode: ExperienceMode;
  timeBoundary: TimeBoundary;
  supportState: SupportState;
  branchPoint: BranchPoint;
  assumptions: Assumptions;
  validity: Validity;
  coverage: DataCoverage;
  participants: Participant[];
  track: TrackGeometry;
  durationS: number;
  rateHz: number;
  selectedParticipantId: string;
}

// ── Battle and game theory ───────────────────────────────────────────────────

/**
 * `multiple` and `none` are outcomes to render, not failures to hide. The frontend
 * shows the model the backend used and its sensitivity; it never decides which is true.
 */
export type SolutionStatus = 'pure' | 'mixed' | 'multiple' | 'none' | 'solver_failure';

export type MoveStructure = 'sequential' | 'simultaneous' | 'stochastic' | 'learned';

export type ActionKind = 'attack' | 'defend' | 'wait' | 'line' | 'pace' | 'energy';

export interface Feasibility {
  /** Physically available at all, before any cost is weighed. */
  available: boolean;
  energyCostMj: Valued<number>;
  tyreCostLaps: Valued<number>;
  ruleConstraints: string[];
}

export interface Action {
  id: string;
  kind: ActionKind;
  label: string;
  /** Which participant this action belongs to. */
  participantId: string;
  feasibility: Feasibility;
}

export interface InformationSet {
  participantId: string;
  /** What this participant is assumed to know when choosing. */
  knows: string[];
}

export interface Objectives {
  /** Named objective terms and their weights in the supplied utility, if any. */
  terms: string[];
  combinedUtility?: string;
}

export interface Response {
  /** `typical` is fitted behaviour; `best` is the strategic best response. */
  kind: 'typical' | 'best' | 'distribution';
  actionId: string;
  label: string;
  probability?: Valued<number>;
}

export interface BattleOutcome {
  /** Behaviour within the declared opportunity window — not physical feasibility. */
  passChance: Valued<number>;
  resultingOrder: string[];
  resultingGapS: Valued<number>;
  energyCostMj: Valued<number>;
  riskLabel: string;
}

/** One candidate solution. Several may be valid at once. */
export interface BattleSolution {
  id: string;
  label: string;
  actionId: string;
  response: Response;
  outcome: BattleOutcome;
}

export interface SensitivityCase {
  /** The opponent belief or game formulation this row assumes. */
  assumption: string;
  moveStructure: MoveStructure;
  recommendedActionId: string;
  recommendedLabel: string;
  outcomeSummary: string;
  /** True when this assumption changes the recommendation. */
  changesRecommendation: boolean;
}

export interface Battle {
  id: string;
  /** The world whose recorded run this battle is measured against. */
  baselineSide: WorldSide;
  lap: number;
  windowStartS: number;
  windowEndS: number;
  location: string;
  attackerId: string;
  defenderId: string;
  startingGapS: Valued<number>;
  /** Other entries whose state changes materially inside the window. */
  affectedIds: string[];
  informationSets: InformationSet[];
  actions: Action[];
  moveStructure: MoveStructure;
  objectives: Objectives;
  solutionStatus: SolutionStatus;
  /** Empty when the status is `none` or `solver_failure`. */
  solutions: BattleSolution[];
  /** Present when the solver could not return a result. */
  solverNote?: string;
  sensitivity: SensitivityCase[];
}

// ── Robustness and decision stability ────────────────────────────────────────

export interface RobustnessCase {
  assumption: string;
  preferredScenarioId: string;
  outcomeSummary: string;
}

export interface DecisionStability {
  /** The choice preferred under the declared assumptions. */
  preferredScenarioId: string;
  cases: RobustnessCase[];
  /** True when at least one supported assumption flips the preference. */
  changesUnderSupportedAssumption: boolean;
  note: string;
}
