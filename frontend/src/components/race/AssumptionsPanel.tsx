import React from 'react';
import { RaceFrame, SessionInfo } from '@/lib/race/types';
import { Valued } from '@/lib/race/valued';
import { Eyebrow, Panel } from './primitives';
import { StatusValue } from './StatusValue';

/** Every unsupported value currently on screen, grouped by the reason given. */
function unsupportedReasons(frame: RaceFrame): { reason: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const world of [frame.baseline, frame.alternative]) {
    for (const state of world.field) {
      const values: Valued<unknown>[] = [
        state.gapS,
        state.intervalS,
        state.sector,
        state.speedKmh,
        state.fuelKg,
        state.paceTarget,
        state.energyTarget,
        state.strategyInstruction,
        state.tyre.compound,
        state.tyre.ageLaps,
        state.tyre.conditionPct,
        state.energy.storedMj,
        state.energy.requestedKw,
        state.energy.deliveredKw,
        state.energy.recoveredKw,
        state.energy.curtailedKw,
        state.traffic.gapAheadS,
        state.traffic.gapBehindS,
      ];
      for (const v of values) {
        if (v.status === 'unsupported') counts.set(v.reason, (counts.get(v.reason) ?? 0) + 1);
      }
    }
  }
  return [...counts.entries()]
    .map(([reason, count]) => ({ reason, count }))
    .sort((a, b) => b.count - a.count);
}

const Row = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div className="flex flex-col gap-1 py-2">
    <Eyebrow>{label}</Eyebrow>
    <span className="text-[11px] leading-relaxed text-white/65">{children}</span>
  </div>
);

const List = ({ items, empty }: { items: string[]; empty: string }) =>
  items.length === 0 ? (
    <span className="italic text-white/25">{empty}</span>
  ) : (
    <ul className="space-y-1">
      {items.map((i) => (
        <li key={i} className="flex gap-2">
          <span className="text-white/25">·</span>
          {i}
        </li>
      ))}
    </ul>
  );

/**
 * A preferred strategy is only ever shown with the assumptions that make it preferred.
 * This region carries those assumptions, what the evidence covers, and every value the
 * backend could not support.
 */
export function AssumptionsPanel({ session, frame }: { session: SessionInfo; frame: RaceFrame | null }) {
  const { assumptions, validity, coverage } = session;
  const unsupported = frame ? unsupportedReasons(frame) : [];

  return (
    <Panel className="p-6 px-8">
      <div className="mb-4 flex items-center justify-between">
        <Eyebrow>Assumptions · source status · uncertainty · warnings</Eyebrow>
        <span className="text-[10px] uppercase tracking-widest text-white/30">
          Supported horizon {validity.supportedHorizonS.toFixed(0)} s
        </span>
      </div>

      <div className="grid grid-cols-1 gap-x-10 divide-y divide-white/[0.05] md:grid-cols-3 md:divide-y-0">
        <div className="md:border-r md:border-white/[0.05] md:pr-8">
          <Row label="Weather">{assumptions.weather}</Row>
          <Row label="Interruptions">{assumptions.interruptions}</Row>
          <Row label="Pit loss">
            <StatusValue value={assumptions.pitLossS} format={(v) => `${v.toFixed(1)} s`} />
          </Row>
          <Row label="Tyre sets">{assumptions.tyreSets}</Row>
        </div>

        <div className="md:border-r md:border-white/[0.05] md:pr-8">
          <Row label="Starting states">{assumptions.startingStates}</Row>
          <Row label="Opponent beliefs">{assumptions.opponentBeliefs}</Row>
          <Row label="Permitted evidence">
            <List items={coverage.permittedEvidence} empty="Not declared" />
          </Row>
          <Row label="Missing inputs">
            <List items={coverage.missingInputs} empty="None declared" />
          </Row>
        </div>

        <div>
          <Row label="Warnings">
            <List items={validity.warnings} empty="None" />
          </Row>
          <Row label="Fallbacks">
            <List items={validity.fallbacks} empty="None applied" />
          </Row>
          <Row label="Unsupported values on screen">
            {unsupported.length === 0 ? (
              <span className="italic text-white/25">None</span>
            ) : (
              <ul className="space-y-1">
                {unsupported.map(({ reason, count }) => (
                  <li key={reason} className="flex gap-2">
                    <span className="text-white/25">·</span>
                    <span>
                      {reason} <span className="text-white/30">({count} values)</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Row>
        </div>
      </div>

      {validity.abstentionReason && (
        <p className="mt-4 rounded-2xl border border-violet-400/20 bg-violet-400/10 p-4 text-[11px] text-violet-200">
          Abstained: {validity.abstentionReason}
        </p>
      )}
    </Panel>
  );
}
