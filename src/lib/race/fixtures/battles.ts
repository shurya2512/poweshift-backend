import { Action, Battle, Feasibility, WorldSide } from '../types';
import { inferred, observed, simulated } from '../valued';

const SCENARIO = 'alt-one-stop';

const feasible = (energyMj: number, tyreLaps: number, constraints: string[] = []): Feasibility => ({
  available: true,
  energyCostMj: inferred(energyMj, [energyMj * 0.8, energyMj * 1.25]),
  tyreCostLaps: inferred(tyreLaps),
  ruleConstraints: constraints,
});

const action = (
  id: string,
  participantId: string,
  kind: Action['kind'],
  label: string,
  feasibility: Feasibility,
): Action => ({ id, kind, label, participantId, feasibility });

/** Race time at a given lap, taken from the entry's own cumulative lap times. */
type LapTime = (id: string, lap: number) => number;

export function buildBattles(at: LapTime, baselineSide: WorldSide = 'baseline'): Battle[] {
  const window = (id: string, lap: number) => ({
    windowStartS: at(id, lap - 1),
    windowEndS: at(id, lap),
  });

  return [
    // ── A clean sequential battle with one pure solution, but a recommendation
    //    that is sensitive to which opponent model is believed.
    {
      id: 'battle-ver-nor-l23',
      baselineSide,
      lap: 23,
      ...window('VER', 23),
      location: 'Turn 1 braking zone, DRS from the back straight',
      attackerId: 'VER',
      defenderId: 'NOR',
      startingGapS: observed(0.62, 'timing feed', at('VER', 22)),
      affectedIds: ['RUS'],
      informationSets: [
        { participantId: 'VER', knows: ['Own energy and tyre state', 'Gap to NOR', 'NOR pit history'] },
        { participantId: 'NOR', knows: ['Own energy and tyre state', 'Gap behind', 'Not VER’s remaining deployment'] },
      ],
      actions: [
        action('ver-attack-inside', 'VER', 'attack', 'Full deployment, inside line into Turn 1', feasible(0.9, 0.4)),
        action('ver-attack-switch', 'VER', 'attack', 'Hold back, switchback out of Turn 2', feasible(0.5, 0.2)),
        action('ver-wait', 'VER', 'wait', 'Stay within a second, attack next lap', feasible(0.15, 0.05)),
        action('nor-defend-inside', 'NOR', 'defend', 'Cover the inside, compromise exit', feasible(0.3, 0.5, ['One change of direction permitted'])),
        action('nor-hold-line', 'NOR', 'defend', 'Hold the racing line, protect exit speed', feasible(0.2, 0.15)),
      ],
      moveStructure: 'sequential',
      objectives: {
        terms: ['Track position', 'Energy cost', 'Tyre cost', 'Contact risk'],
        combinedUtility: 'Position weighted 0.6, energy 0.2, tyre 0.1, risk 0.1',
      },
      solutionStatus: 'pure',
      solutions: [
        {
          id: 'sol-ver-inside',
          label: 'Attack on the inside',
          actionId: 'ver-attack-inside',
          response: {
            kind: 'best',
            actionId: 'nor-defend-inside',
            label: 'NOR covers the inside',
            probability: simulated(0.71, SCENARIO, ['Best-response opponent']),
          },
          outcome: {
            passChance: simulated(0.44, SCENARIO, ['Opportunity window: Turn 1 braking zone only']),
            resultingOrder: ['VER', 'NOR', 'RUS'],
            resultingGapS: simulated(0.35, SCENARIO, []),
            energyCostMj: inferred(0.9, [0.72, 1.13]),
            riskLabel: 'Elevated — late braking with a covered inside',
          },
        },
      ],
      sensitivity: [
        {
          assumption: 'Fitted typical behaviour from this driver’s season',
          moveStructure: 'stochastic',
          recommendedActionId: 'ver-attack-switch',
          recommendedLabel: 'Hold back, switchback out of Turn 2',
          outcomeSummary: 'Pass chance 0.51, lower energy cost, lower contact risk',
          changesRecommendation: true,
        },
        {
          assumption: 'Strategic best-response opponent',
          moveStructure: 'sequential',
          recommendedActionId: 'ver-attack-inside',
          recommendedLabel: 'Full deployment, inside line into Turn 1',
          outcomeSummary: 'Pass chance 0.44, highest energy cost',
          changesRecommendation: false,
        },
        {
          assumption: 'Learned opponent, last eight comparable battles',
          moveStructure: 'learned',
          recommendedActionId: 'ver-attack-switch',
          recommendedLabel: 'Hold back, switchback out of Turn 2',
          outcomeSummary: 'Pass chance 0.48 with a wide interval',
          changesRecommendation: true,
        },
      ],
    },

    // ── Two valid equilibria. Both stay visible; neither is called the answer.
    {
      id: 'battle-lec-rus-l19',
      baselineSide,
      lap: 19,
      ...window('LEC', 19),
      location: 'Turn 8–9 chicane, no DRS',
      attackerId: 'RUS',
      defenderId: 'LEC',
      startingGapS: observed(0.41, 'timing feed', at('LEC', 18)),
      affectedIds: [],
      informationSets: [
        { participantId: 'RUS', knows: ['Own energy', 'Gap to LEC'] },
        { participantId: 'LEC', knows: ['Own energy', 'Gap behind'] },
      ],
      actions: [
        action('rus-commit', 'RUS', 'attack', 'Commit to the inside at Turn 8', feasible(0.7, 0.35)),
        action('rus-hold', 'RUS', 'wait', 'Hold position, save energy', feasible(0.1, 0.05)),
        action('lec-cover', 'LEC', 'defend', 'Cover the inside early', feasible(0.25, 0.4)),
        action('lec-open', 'LEC', 'defend', 'Keep the line, defend on exit', feasible(0.15, 0.1)),
      ],
      moveStructure: 'simultaneous',
      objectives: { terms: ['Track position', 'Energy cost', 'Contact risk'] },
      solutionStatus: 'multiple',
      solutions: [
        {
          id: 'sol-commit-cover',
          label: 'RUS commits · LEC covers',
          actionId: 'rus-commit',
          response: { kind: 'best', actionId: 'lec-cover', label: 'LEC covers the inside' },
          outcome: {
            passChance: simulated(0.22, SCENARIO, ['Simultaneous choice']),
            resultingOrder: ['LEC', 'RUS'],
            resultingGapS: simulated(0.28, SCENARIO, []),
            energyCostMj: inferred(0.7, [0.56, 0.88]),
            riskLabel: 'High — both cars committed to the same line',
          },
        },
        {
          id: 'sol-hold-open',
          label: 'RUS holds · LEC keeps the line',
          actionId: 'rus-hold',
          response: { kind: 'best', actionId: 'lec-open', label: 'LEC keeps the racing line' },
          outcome: {
            passChance: simulated(0.06, SCENARIO, ['Simultaneous choice']),
            resultingOrder: ['LEC', 'RUS'],
            resultingGapS: simulated(0.55, SCENARIO, []),
            energyCostMj: inferred(0.1, [0.08, 0.13]),
            riskLabel: 'Low',
          },
        },
      ],
      sensitivity: [
        {
          assumption: 'Both equilibria are supported; no selection rule is justified',
          moveStructure: 'simultaneous',
          recommendedActionId: '',
          recommendedLabel: 'No unique recommendation',
          outcomeSummary: 'Outcome depends on which equilibrium the drivers coordinate on',
          changesRecommendation: true,
        },
      ],
    },

    // ── The solver could not return a result. Inputs preserved, nothing invented.
    {
      id: 'battle-ham-alo-l27',
      baselineSide,
      lap: 27,
      ...window('HAM', 27),
      location: 'Turn 4 exit, tyre delta unresolved',
      attackerId: 'HAM',
      defenderId: 'ALO',
      startingGapS: observed(0.88, 'timing feed', at('HAM', 26)),
      affectedIds: [],
      informationSets: [
        { participantId: 'HAM', knows: ['Own energy', 'Gap to ALO'] },
        { participantId: 'ALO', knows: ['Own energy'] },
      ],
      actions: [
        action('ham-attack', 'HAM', 'attack', 'Deploy out of Turn 3, attack on the run to 4', feasible(0.8, 0.3)),
        action('ham-wait', 'HAM', 'wait', 'Hold the gap and reassess', feasible(0.1, 0.05)),
        action('alo-defend', 'ALO', 'defend', 'Defensive line through Turn 4', feasible(0.2, 0.35)),
      ],
      moveStructure: 'learned',
      objectives: { terms: ['Track position', 'Energy cost'] },
      solutionStatus: 'solver_failure',
      solutions: [],
      solverNote:
        'The learned opponent model did not converge for this pairing: ALO’s tyre state is unresolved at this lap, and the response distribution is not identifiable from the available comparable battles.',
      sensitivity: [],
    },
  ];
}
