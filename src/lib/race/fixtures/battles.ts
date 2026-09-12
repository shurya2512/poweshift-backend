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
    // ── The out-lap fight. Our car rejoins behind a car that stopped earlier and is
    //    already on worn tyres, so the tyre delta does most of the work.
    {
      id: 'battle-ver-lec-l13',
      baselineSide,
      lap: 13,
      ...window('VER', 13),
      location: 'Back straight into Turn 12, DRS available',
      attackerId: 'VER',
      defenderId: 'LEC',
      startingGapS: observed(0.94, 'timing feed', at('VER', 12)),
      affectedIds: [],
      informationSets: [
        { participantId: 'VER', knows: ['Own tyre age — three laps', 'LEC tyre age', 'Gap to LEC'] },
        { participantId: 'LEC', knows: ['Own tyre state', 'Gap behind', 'Not VER’s deployment plan'] },
      ],
      actions: [
        action('ver-l13-drs', 'VER', 'attack', 'Take DRS and commit on the straight', feasible(0.55, 0.1)),
        action('ver-l13-settle', 'VER', 'wait', 'Settle in, build the tyre delta for a lap', feasible(0.1, 0.04)),
        action('lec-l13-cover', 'LEC', 'defend', 'Move to the inside before the braking board', feasible(0.18, 0.22, ['One change of direction permitted'])),
      ],
      moveStructure: 'sequential',
      objectives: {
        terms: ['Track position', 'Tyre cost'],
        combinedUtility: 'Position weighted 0.8, tyre 0.2',
      },
      solutionStatus: 'pure',
      solutions: [
        {
          id: 'sol-ver-l13-drs',
          label: 'Take DRS and commit on the straight',
          actionId: 'ver-l13-drs',
          response: {
            kind: 'best',
            actionId: 'lec-l13-cover',
            label: 'LEC moves to the inside',
            probability: simulated(0.83, SCENARIO, ['Best-response opponent']),
          },
          outcome: {
            passChance: simulated(0.79, SCENARIO, ['Opportunity window: back straight and Turn 12 only']),
            resultingOrder: ['VER', 'LEC'],
            resultingGapS: simulated(0.71, SCENARIO, []),
            energyCostMj: inferred(0.55, [0.44, 0.69]),
            riskLabel: 'Low — twelve laps of tyre advantage into a braking zone',
          },
        },
      ],
      sensitivity: [
        {
          assumption: 'Fitted typical behaviour from this driver’s season',
          moveStructure: 'stochastic',
          recommendedActionId: 'ver-l13-drs',
          recommendedLabel: 'Take DRS and commit on the straight',
          outcomeSummary: 'Pass chance 0.74, same line recommended',
          changesRecommendation: false,
        },
        {
          assumption: 'Strategic best-response opponent',
          moveStructure: 'sequential',
          recommendedActionId: 'ver-l13-drs',
          recommendedLabel: 'Take DRS and commit on the straight',
          outcomeSummary: 'Pass chance 0.79, lowest energy cost of the attacking lines',
          changesRecommendation: false,
        },
      ],
    },

    // ── A mixed equilibrium: neither car has a pure best line, and the recommendation
    //    is a distribution over two of them rather than one choice.
    {
      id: 'battle-ver-pia-l19',
      baselineSide: 'alternative',
      lap: 19,
      ...window('VER', 19),
      location: 'Turn 6 hairpin, two laps after the restart',
      attackerId: 'VER',
      defenderId: 'PIA',
      startingGapS: simulated(0.48, SCENARIO, ['Restart order under the safety car']),
      affectedIds: ['ANT'],
      informationSets: [
        { participantId: 'VER', knows: ['Own energy after the restart', 'Gap to PIA', 'PIA stint age'] },
        { participantId: 'PIA', knows: ['Own energy', 'Gap behind', 'Not whether VER is on a one-stop'] },
      ],
      actions: [
        action('ver-l19-lunge', 'VER', 'attack', 'Lunge down the inside at the hairpin', feasible(0.72, 0.45)),
        action('ver-l19-exit', 'VER', 'attack', 'Sacrifice entry, take the exit and the run to Turn 7', feasible(0.44, 0.18)),
        action('ver-l19-hold', 'VER', 'wait', 'Hold the gap, save energy for the next lap', feasible(0.08, 0.03)),
        action('pia-l19-shut', 'PIA', 'defend', 'Shut the door at the apex', feasible(0.22, 0.38)),
        action('pia-l19-exit', 'PIA', 'defend', 'Give up the apex, protect the exit', feasible(0.14, 0.12)),
      ],
      moveStructure: 'simultaneous',
      objectives: {
        terms: ['Track position', 'Energy cost', 'Contact risk'],
        combinedUtility: 'Position weighted 0.55, energy 0.2, risk 0.25',
      },
      solutionStatus: 'mixed',
      solutions: [
        {
          id: 'sol-ver-l19-exit',
          label: 'Sacrifice entry, take the exit',
          actionId: 'ver-l19-exit',
          response: {
            kind: 'distribution',
            actionId: 'pia-l19-shut',
            label: 'PIA shuts the door at the apex',
            probability: simulated(0.62, SCENARIO, ['Mixed equilibrium over two defensive lines']),
          },
          outcome: {
            passChance: simulated(0.57, SCENARIO, ['Opportunity window: hairpin exit to Turn 7 only']),
            resultingOrder: ['VER', 'PIA', 'ANT'],
            resultingGapS: simulated(0.22, SCENARIO, []),
            energyCostMj: inferred(0.44, [0.35, 0.55]),
            riskLabel: 'Moderate — no contact exposure at the apex, but the exit is tight',
          },
        },
      ],
      sensitivity: [
        {
          assumption: 'Mixed equilibrium as solved',
          moveStructure: 'simultaneous',
          recommendedActionId: 'ver-l19-exit',
          recommendedLabel: 'Sacrifice entry, take the exit',
          outcomeSummary: 'Pass chance 0.57 against a defence that shuts the apex 62% of the time',
          changesRecommendation: false,
        },
        {
          assumption: 'Defender always shuts the apex',
          moveStructure: 'sequential',
          recommendedActionId: 'ver-l19-exit',
          recommendedLabel: 'Sacrifice entry, take the exit',
          outcomeSummary: 'Pass chance 0.66 — the exit line is the answer to a covered apex',
          changesRecommendation: false,
        },
        {
          assumption: 'Defender protects the exit instead',
          moveStructure: 'sequential',
          recommendedActionId: 'ver-l19-lunge',
          recommendedLabel: 'Lunge down the inside at the hairpin',
          outcomeSummary: 'Pass chance 0.61, at a much higher tyre and contact cost',
          changesRecommendation: true,
        },
      ],
    },

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

    // ── The other side of the same problem: our car defending, and losing the place.
    //    Nothing about this window is different in kind — the model is asked what the
    //    attacker should do, and our car is the one it is done to.
    {
      id: 'battle-rus-ver-l21',
      baselineSide,
      lap: 21,
      ...window('RUS', 21),
      location: 'Turn 3, on the exit of the long left',
      attackerId: 'RUS',
      defenderId: 'VER',
      startingGapS: observed(0.55, 'timing feed', at('RUS', 20)),
      affectedIds: ['NOR'],
      informationSets: [
        { participantId: 'RUS', knows: ['Own tyre age — seven laps', 'Gap to VER', 'VER stint age'] },
        { participantId: 'VER', knows: ['Own tyre state', 'Gap behind', 'Own remaining energy'] },
      ],
      actions: [
        action('rus-l21-outside', 'RUS', 'attack', 'Go around the outside on the exit', feasible(0.65, 0.3)),
        action('rus-l21-wait', 'RUS', 'wait', 'Sit in the gap and wait for the second stop', feasible(0.09, 0.03)),
        action('ver-l21-defend', 'VER', 'defend', 'Take the defensive line, give up exit speed', feasible(0.24, 0.42, ['One change of direction permitted'])),
        action('ver-l21-hold', 'VER', 'defend', 'Hold the racing line and keep the tyre alive', feasible(0.12, 0.09)),
      ],
      moveStructure: 'sequential',
      objectives: {
        terms: ['Track position', 'Tyre cost', 'Remaining stint length'],
        combinedUtility: 'Position weighted 0.5, tyre 0.35, stint 0.15',
      },
      solutionStatus: 'pure',
      solutions: [
        {
          id: 'sol-rus-l21-outside',
          label: 'RUS goes around the outside',
          actionId: 'rus-l21-outside',
          response: {
            kind: 'best',
            actionId: 'ver-l21-hold',
            label: 'VER holds the racing line',
            probability: simulated(0.68, SCENARIO, ['Best-response opponent']),
          },
          outcome: {
            passChance: simulated(0.63, SCENARIO, ['Opportunity window: Turn 3 exit to Turn 4 only']),
            resultingOrder: ['RUS', 'VER', 'NOR'],
            resultingGapS: simulated(0.41, SCENARIO, []),
            energyCostMj: inferred(0.65, [0.52, 0.81]),
            riskLabel: 'Low for the attacker — the defence gives up the place rather than the tyre',
          },
        },
      ],
      sensitivity: [
        {
          assumption: 'Strategic best-response opponent',
          moveStructure: 'sequential',
          recommendedActionId: 'rus-l21-outside',
          recommendedLabel: 'Go around the outside on the exit',
          outcomeSummary: 'Pass chance 0.63 against a defence that protects its tyre',
          changesRecommendation: false,
        },
        {
          assumption: 'Defender spends the tyre to keep the place',
          moveStructure: 'sequential',
          recommendedActionId: 'rus-l21-wait',
          recommendedLabel: 'Sit in the gap and wait for the second stop',
          outcomeSummary: 'Pass chance falls to 0.24 — waiting for the stop is worth more than the move',
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
