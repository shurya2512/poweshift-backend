import React from 'react';
import { RaceReport, WorldReport } from '@/lib/race/report';
import { Participant, ParticipantState } from '@/lib/race/types';
import { Valued } from '@/lib/race/valued';
import { StatusValue } from '../StatusValue';
import { Disclosure, Figure, P, Section, Subhead, Table, Td, Th } from './article';

/** One measured quantity, side by side across the two races. */
function CompareRow<T>({
  label,
  baseline,
  alternative,
  format,
}: {
  label: string;
  baseline: Valued<T> | undefined;
  alternative: Valued<T> | undefined;
  format?: (v: T) => string;
}) {
  return (
    <tr>
      <Td className="text-white/40">{label}</Td>
      <Td className="text-right text-white/75">
        {baseline ? <StatusValue value={baseline} format={format} /> : <span className="text-white/20">—</span>}
      </Td>
      <Td className="text-right text-white/75">
        {alternative ? <StatusValue value={alternative} format={format} /> : <span className="text-white/20">—</span>}
      </Td>
    </tr>
  );
}

/**
 * The field in our plan's order, with where each car finished in the race as it was run.
 * Two columns of positions, not one merged classification — the races are still separate.
 */
function FieldComparison({
  report,
  participants,
}: {
  report: RaceReport;
  participants: Map<string, Participant>;
}) {
  const recordedRank = new Map(report.baseline.classification.map((p) => [p.participantId, p.rank]));

  return (
    <Table minWidth={540}>
      <thead>
        <tr>
          <Th className="w-10">Pos</Th>
          <Th>Driver</Th>
          <Th className="text-right">Gap</Th>
          <Th className="text-right text-sky-300/60">Recorded</Th>
          <Th className="text-right">Change</Th>
        </tr>
      </thead>
      <tbody>
        {report.alternative.classification.map((state) => {
          const entry = participants.get(state.participantId);
          const ours = state.rank;
          const before = recordedRank.get(state.participantId);
          const change = before === undefined ? undefined : before - ours;
          const selected = state.participantId === report.selectedParticipantId;
          const retired = state.participation === 'retired';

          return (
            <tr key={state.participantId} className={retired ? 'opacity-45' : ''}>
              <Td className={`font-bold ${selected ? 'text-white' : 'text-white/50'}`}>{ours}</Td>
              <Td>
                <span className="flex items-center gap-2.5">
                  <span
                    aria-hidden
                    className="h-3 w-[3px] shrink-0 rounded-full"
                    style={{ background: entry?.teamColor ?? '#ffffff30' }}
                  />
                  <span className={selected ? 'font-bold text-white' : 'text-white/80'}>
                    {entry?.name ?? state.participantId}
                  </span>
                </span>
              </Td>
              <Td className="text-right">
                {retired ? (
                  <span className="text-white/30">Retired</span>
                ) : ours === 1 ? (
                  <span className="text-white/35">leader</span>
                ) : (
                  <StatusValue value={state.gapS} format={(v) => `+${v.toFixed(2)}s`} />
                )}
              </Td>
              <Td className="text-right text-white/45">{before ?? '—'}</Td>
              <Td
                className={`text-right font-semibold ${
                  change === undefined || change === 0
                    ? 'text-white/25'
                    : change > 0
                      ? 'text-emerald-300/80'
                      : 'text-rose-300/70'
                }`}
              >
                {change === undefined || change === 0 ? '—' : change > 0 ? `+${change}` : change}
              </Td>
            </tr>
          );
        })}
      </tbody>
    </Table>
  );
}

/** Every quantity our car carried, for a reader who wants the whole state. */
function FullState({
  baseline,
  alternative,
  driver,
}: {
  baseline: ParticipantState | undefined;
  alternative: ParticipantState | undefined;
  driver: Participant | null;
}) {
  if (!baseline && !alternative) return null;

  return (
    <Table minWidth={520}>
      <thead>
        <tr>
          <Th>{driver?.code ?? 'Entry'} at the flag</Th>
          <Th className="text-right text-sky-300/60">Recorded race</Th>
          <Th className="text-right text-emerald-300/60">Our plan</Th>
        </tr>
      </thead>
      <tbody>
        <CompareRow
          label="Interval ahead"
          baseline={baseline?.intervalS}
          alternative={alternative?.intervalS}
          format={(v: number) => `+${v.toFixed(2)}s`}
        />
        <CompareRow
          label="Speed"
          baseline={baseline?.speedKmh}
          alternative={alternative?.speedKmh}
          format={(v: number) => `${v} km/h`}
        />
        <CompareRow
          label="Fuel"
          baseline={baseline?.fuelKg}
          alternative={alternative?.fuelKg}
          format={(v: number) => `${v} kg`}
        />
        <CompareRow
          label="Power requested"
          baseline={baseline?.energy.requestedKw}
          alternative={alternative?.energy.requestedKw}
          format={(v: number) => `${v} kW`}
        />
        <CompareRow
          label="Power delivered"
          baseline={baseline?.energy.deliveredKw}
          alternative={alternative?.energy.deliveredKw}
          format={(v: number) => `${v} kW`}
        />
        <CompareRow
          label="Power recovered"
          baseline={baseline?.energy.recoveredKw}
          alternative={alternative?.energy.recoveredKw}
          format={(v: number) => `${v} kW`}
        />
        <CompareRow
          label="Power curtailed"
          baseline={baseline?.energy.curtailedKw}
          alternative={alternative?.energy.curtailedKw}
          format={(v: number) => `${v} kW`}
        />
        <CompareRow label="Energy target" baseline={baseline?.energyTarget} alternative={alternative?.energyTarget} />
        <CompareRow
          label="Team instruction"
          baseline={baseline?.strategyInstruction}
          alternative={alternative?.strategyInstruction}
        />
      </tbody>
    </Table>
  );
}

export function ClassificationSection({
  report,
  participants,
  driver,
}: {
  report: RaceReport;
  participants: Map<string, Participant>;
  driver: Participant | null;
}) {
  const id = report.selectedParticipantId;
  const find = (world: WorldReport) => world.classification.find((p) => p.participantId === id);
  const ours = find(report.alternative);
  const recorded = find(report.baseline);
  const classified = report.baseline.classification.filter((p) => p.participation !== 'retired').length;

  return (
    <Section
      title="The finish"
      standfirst={`${report.session.participants.length} cars started and ${classified} were classified. The field below is in our plan's order, against where each car finished in the race as it was run.`}
    >
      <Figure title="Final classification" note="Two separate classifications, read side by side.">
        <FieldComparison report={report} participants={participants} />
      </Figure>

      <Subhead>{driver ? `${driver.name} at the flag` : 'Our car at the flag'}</Subhead>
      <P>
        What our car was carrying as each race ended. Anything the source could not support reads as unavailable — it is
        never filled in with a zero or an average.
      </P>

      <Table minWidth={460}>
        <thead>
          <tr>
            <Th>{driver?.code ?? 'Entry'}</Th>
            <Th className="text-right text-sky-300/60">Recorded race</Th>
            <Th className="text-right text-emerald-300/60">Our plan</Th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <Td className="text-white/40">Position</Td>
            <Td className="text-right font-bold text-white">{recorded ? `P${recorded.rank}` : '—'}</Td>
            <Td className="text-right font-bold text-white">{ours ? `P${ours.rank}` : '—'}</Td>
          </tr>
          <CompareRow
            label="Gap to leader"
            baseline={recorded?.gapS}
            alternative={ours?.gapS}
            format={(v: number) => `+${v.toFixed(2)}s`}
          />
          <CompareRow label="Compound" baseline={recorded?.tyre.compound} alternative={ours?.tyre.compound} />
          <CompareRow
            label="Stint age"
            baseline={recorded?.tyre.ageLaps}
            alternative={ours?.tyre.ageLaps}
            format={(v: number) => `${v} laps`}
          />
          <CompareRow
            label="Tyre condition"
            baseline={recorded?.tyre.conditionPct}
            alternative={ours?.tyre.conditionPct}
            format={(v: number) => `${v.toFixed(0)}%`}
          />
          <CompareRow
            label="Stored energy"
            baseline={recorded?.energy.storedMj}
            alternative={ours?.energy.storedMj}
            format={(v: number) => `${v.toFixed(2)} MJ`}
          />
          <CompareRow label="Pace target" baseline={recorded?.paceTarget} alternative={ours?.paceTarget} />
        </tbody>
      </Table>

      <Disclosure summary="Every other quantity our car carried">
        <FullState baseline={recorded} alternative={ours} driver={driver} />
      </Disclosure>
    </Section>
  );
}
