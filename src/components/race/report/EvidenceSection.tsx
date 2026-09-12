import React from 'react';
import { RaceReport } from '@/lib/race/report';
import { ParticipantState } from '@/lib/race/types';
import { Valued } from '@/lib/race/valued';
import { StatusLegend, StatusValue } from '../StatusValue';
import { Aside, DataList, Datum, Disclosure, P, PullQuote, Section, Subhead } from './article';

/** Every unsupported value in the finished fields, grouped by the reason given for it. */
function unsupportedReasons(report: RaceReport): { reason: string; count: number }[] {
  const counts = new Map<string, number>();
  const scan = (state: ParticipantState) => {
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
  };

  report.baseline.classification.forEach(scan);
  report.alternative.classification.forEach(scan);

  return [...counts.entries()]
    .map(([reason, count]) => ({ reason, count }))
    .sort((a, b) => b.count - a.count);
}

const List = ({ items, empty }: { items: string[]; empty: string }) =>
  items.length === 0 ? (
    <span className="italic text-white/25">{empty}</span>
  ) : (
    <span className="text-[13px] font-normal text-white/60">{items.join(' · ')}</span>
  );

/** Whether the answer survives the other assumptions the backend supports. */
export function RobustnessSection({ index, report }: { index: string; report: RaceReport }) {
  const stability = report.comparison.stability;
  if (!stability) return null;

  const flips = stability.cases.filter(
    (c) => c.preferredScenarioId !== stability.preferredScenarioId && c.preferredScenarioId !== 'unresolved',
  );

  return (
    <Section
      index={index}
      title="Does it hold?"
      standfirst="The same comparison, re-run under every other assumption the backend supports."
    >
      <P>
        A preferred plan means nothing without the assumptions that make it preferred, so each supported assumption is
        re-tested below.{' '}
        {stability.changesUnderSupportedAssumption
          ? `Under ${flips.length === 1 ? 'one of them' : `${flips.length} of them`} the preference reverses. That reversal is part of the result, not a footnote to it.`
          : 'The preference holds under all of them.'}
      </P>

      <DataList>
        {stability.cases.map((c) => {
          const unresolved = c.preferredScenarioId === 'unresolved';
          const flipped = !unresolved && c.preferredScenarioId !== stability.preferredScenarioId;
          return (
            <Datum key={c.assumption} label={c.assumption}>
              <span className={flipped ? 'text-amber-300' : unresolved ? 'italic text-white/25' : 'text-white/70'}>
                {unresolved ? 'unavailable' : c.preferredScenarioId}
              </span>
              <span className="ml-3 text-[12px] font-normal text-white/35">{c.outcomeSummary}</span>
            </Datum>
          );
        })}
      </DataList>

      <PullQuote>{stability.note}</PullQuote>
    </Section>
  );
}

/** The closing section: what the answer rests on, and what it could not see. */
export function EvidenceSection({ index, report }: { index: string; report: RaceReport }) {
  const { assumptions, validity, coverage } = report.session;
  const unsupported = unsupportedReasons(report);

  return (
    <Section
      index={index}
      title="Notes on the evidence"
      standfirst="What this report was allowed to use, what it could not resolve, and how to read every figure in it."
    >
      <P>
        Each value carries where it came from. The recorded race is observed or inferred from the timing feed; our plan
        never happened, so every one of its values is simulated under the assumptions below. The two races are compared
        on one clock and one evidence cutoff, and are never merged into a single classification.
      </P>

      <DataList>
        <Datum label="Interruptions">
          <span className="text-[13px] font-normal text-white/60">{assumptions.interruptions}</span>
        </Datum>
        <Datum label="Opponent beliefs">
          <span className="text-[13px] font-normal text-white/60">{assumptions.opponentBeliefs}</span>
        </Datum>
        <Datum label="Pit loss">
          <StatusValue value={assumptions.pitLossS} format={(v) => `${v.toFixed(1)}s`} />
        </Datum>
      </DataList>

      {validity.warnings.length > 0 && (
        <ul className="flex flex-col gap-2">
          {validity.warnings.map((w) => (
            <li key={w} className="border-l-2 border-amber-400/30 pl-5 text-[14px] leading-relaxed text-white/55">
              {w}
            </li>
          ))}
        </ul>
      )}
      {validity.abstentionReason && <Aside>Abstained: {validity.abstentionReason}</Aside>}

      <div className="border-t border-white/10 pt-5">
        <StatusLegend />
      </div>

      <Disclosure summary="Coverage, weather and every value the source could not supply">
        <DataList>
          <Datum label="Weather">
            <span className="text-[13px] font-normal text-white/60">{assumptions.weather}</span>
          </Datum>
          <Datum label="Tyre sets">
            <span className="text-[13px] font-normal text-white/60">{assumptions.tyreSets}</span>
          </Datum>
          <Datum label="Starting states">
            <span className="text-[13px] font-normal text-white/60">{assumptions.startingStates}</span>
          </Datum>
          <Datum label="Sessions available">
            <List items={coverage.availableSessions} empty="None declared" />
          </Datum>
          <Datum label="Permitted evidence">
            <List items={coverage.permittedEvidence} empty="Not declared" />
          </Datum>
          <Datum label="Missing inputs">
            <List items={coverage.missingInputs} empty="None declared" />
          </Datum>
          <Datum label="Supported horizon">{validity.supportedHorizonS.toFixed(0)}s</Datum>
          {validity.fallbacks.length > 0 && (
            <Datum label="Fallbacks applied">
              <List items={validity.fallbacks} empty="None" />
            </Datum>
          )}
        </DataList>

        <Subhead>Values this report could not supply</Subhead>
        {unsupported.length === 0 ? (
          <Aside>Every value in this report is supported.</Aside>
        ) : (
          <DataList>
            {unsupported.map(({ reason, count }) => (
              <Datum key={reason} label={reason}>
                <span className="text-[13px] font-normal text-white/45">{count} values</span>
              </Datum>
            ))}
          </DataList>
        )}
      </Disclosure>
    </Section>
  );
}
