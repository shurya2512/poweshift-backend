import { RaceEvent, WorldSide } from '../types';
import { ROSTER } from './roster';
import { BRANCH_LAP, SELECTED_ID, TOTAL_LAPS, WorldPlan, WorldTiming, pitLapsFor } from './model';

/**
 * On-track position changes for the selected entry, derived from the same cumulative
 * lap times every other part of this world is built from.
 *
 * Two things are deliberately not reported as passes. A car takes its pit loss during
 * the lap it stops on, so a swap measured across that lap is a pit cycle and is
 * skipped — laps either side of it are ordinary racing and are not. And a car that
 * disappears from the order because it retired was not overtaken, so a change is only
 * reported when both entries are running at both ends of it.
 */

/** Entries ahead of the selected one at the end of `lap`, by cumulative race time. */
function aheadAt(timing: WorldTiming, lap: number): Set<string> {
  const ours = timing.get(SELECTED_ID)?.[lap - 1];
  const ahead = new Set<string>();
  if (ours === undefined) return ahead;
  for (const entry of ROSTER) {
    if (entry.id === SELECTED_ID) continue;
    const theirs = timing.get(entry.id)?.[lap - 1];
    if (theirs !== undefined && theirs < ours) ahead.add(entry.id);
  }
  return ahead;
}

/** The event, plus the entry it was against — which the event itself does not carry. */
export interface PositionChange {
  event: RaceEvent;
  otherId: string;
}

export function positionChangeEvents(
  side: WorldSide,
  plan: WorldPlan,
  timing: WorldTiming,
): PositionChange[] {
  const out: PositionChange[] = [];
  const ours = timing.get(SELECTED_ID) ?? [];
  const running = (id: string, lap: number) => timing.get(id)?.[lap - 1] !== undefined;
  const pitted = (id: string, lap: number) => pitLapsFor(plan, id).includes(lap);

  for (let lap = 2; lap <= TOTAL_LAPS; lap++) {
    // Before the branch the two worlds are the same race, so only the baseline pass
    // emits those changes — as shared history, once.
    if (side === 'alternative' && lap <= BRANCH_LAP) continue;
    if (ours[lap - 1] === undefined || pitted(SELECTED_ID, lap)) continue;

    const before = aheadAt(timing, lap - 1);
    const now = aheadAt(timing, lap);
    const world: RaceEvent['world'] = lap <= BRANCH_LAP ? 'shared' : side;
    const at = ours[lap - 1];

    const change = (otherId: string, gained: boolean) => {
      if (pitted(otherId, lap) || !running(otherId, lap) || !running(otherId, lap - 1)) return;
      out.push({
        otherId,
        event: {
          id: `${world}-pos-${lap}-${SELECTED_ID}-${otherId}`,
          world,
          group: 'competition',
          kind: gained ? 'overtake' : 'overtaken',
          raceTimeS: at,
          lap,
          participantId: SELECTED_ID,
          label: gained
            ? `${SELECTED_ID} passes ${otherId} on lap ${lap}`
            : `${otherId} passes ${SELECTED_ID} on lap ${lap}`,
        },
      });
    };

    for (const id of before) if (!now.has(id)) change(id, true);
    for (const id of now) if (!before.has(id)) change(id, false);
  }

  return out;
}
