import React from 'react';
import { RaceReport, findOvertakes } from '@/lib/race/report';
import { Participant } from '@/lib/race/types';
import { formatClock } from '../primitives';
import { StatusValue } from '../StatusValue';
import { Aside, Column, DataList, Datum, Lede, P, Section, Subhead, Table, Td, Th } from './article';
import { ChronicleSection } from './ChronicleSection';
import { ClassificationSection } from './ClassificationSection';
import { EvidenceSection, RobustnessSection } from './EvidenceSection';
import { OvertakeSection } from './OvertakeSection';

const MODE_LABEL: Record<RaceReport['session']['mode'], string> = {
  recorded_replay: 'Recorded replay',
  conditional_replay: 'Conditional replay',
  forward_forecast: 'Forward forecast',
  counterfactual: 'Counterfactual',
};

/** UTC and fixed — a locale-formatted time would differ between server and client render. */
const stamp = (ms: number): string => `${new Date(ms).toISOString().slice(0, 16).replace('T', ' ')} UTC`;

const places = (v: number): string =>
  v === 0 ? 'no change in position' : v < 0 ? `${-v} place${v === -1 ? '' : 's'} gained` : `${v} place${v === 1 ? '' : 's'} lost`;

function Masthead({ report, driver }: { report: RaceReport; driver: Participant | null }) {
  const { identity, timeBoundary } = report.session;

  return (
    <header>
      <p className="font-mono text-[11px] uppercase tracking-[0.4em] text-sky-400/70">Race report</p>
      <h1 className="mt-5 text-[44px] font-black uppercase leading-[0.9] tracking-tighter text-white md:text-[76px]">
        {identity.event}
      </h1>
      <p className="mt-6 max-w-[58ch] text-[17px] leading-relaxed text-white/45">
        The race as it was run, set against one plan we asked for instead — {report.alternative.scenario.name} — read at
        the chequered flag{driver ? ` through ${driver.name}'s car` : ''}.
      </p>

      <div className="mt-8 flex flex-wrap gap-x-8 gap-y-3 border-y border-white/10 py-4 font-mono text-[11px] uppercase tracking-[0.15em] text-white/35">
        <span>
          {identity.season} · {identity.circuit}
        </span>
        <span>{identity.session}</span>
        <span>{report.baseline.totalLaps} laps</span>
        <span>{formatClock(report.finalRaceTimeS)}</span>
        <span>{MODE_LABEL[report.session.mode]}</span>
        <span className="text-white/25">Generated {stamp(timeBoundary.generatedAtMs)}</span>
      </div>
    </header>
  );
}

/** The numbers behind the lede: what each race paid for the finish it got. */
function TheResult({ report, driver }: { report: RaceReport; driver: Participant | null }) {
  const { comparison, delta } = report;

  return (
    <Section
      index="01"
      title="The result"
      standfirst="What our car finished with in each race, and what separates them."
    >
      <Table minWidth={440}>
        <thead>
          <tr>
            <Th>{driver?.code ?? 'Our car'}</Th>
            <Th className="text-right text-sky-300/60">Recorded race</Th>
            <Th className="text-right text-emerald-300/60">Our plan</Th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <Td className="text-white/40">Finishing position</Td>
            <Td className="text-right text-lg font-black text-white">
              <StatusValue value={comparison.baseline.finishPosition} format={(v) => `P${v}`} />
            </Td>
            <Td className="text-right text-lg font-black text-white">
              <StatusValue value={comparison.alternative.finishPosition} format={(v) => `P${v}`} />
            </Td>
          </tr>
          <tr>
            <Td className="text-white/40">Total race time</Td>
            <Td className="text-right text-white/75">
              <StatusValue value={comparison.baseline.totalTimeS} format={(v) => `${v.toFixed(2)}s`} />
            </Td>
            <Td className="text-right text-white/75">
              <StatusValue value={comparison.alternative.totalTimeS} format={(v) => `${v.toFixed(2)}s`} />
            </Td>
          </tr>
          <tr>
            <Td className="text-white/40">Points</Td>
            <Td className="text-right text-white/75">
              <StatusValue value={comparison.baseline.points} format={(v) => `${v}`} />
            </Td>
            <Td className="text-right text-white/75">
              <StatusValue value={comparison.alternative.points} format={(v) => `${v}`} />
            </Td>
          </tr>
          <tr>
            <Td className="text-white/40">Pit stops</Td>
            <Td className="text-right text-white/75">{comparison.baseline.pitCount}</Td>
            <Td className="text-right text-white/75">{comparison.alternative.pitCount}</Td>
          </tr>
          <tr>
            <Td className="text-white/40">Tyres used</Td>
            <Td className="text-right text-white/75">{comparison.baseline.tyreUse}</Td>
            <Td className="text-right text-white/75">{comparison.alternative.tyreUse}</Td>
          </tr>
        </tbody>
      </Table>

      <P>
        Against the race as it was run, our plan is{' '}
        <StatusValue value={comparison.relativePositions} format={places} hideMark /> and{' '}
        <StatusValue
          value={comparison.relativeTimeS}
          format={(v) => `${v > 0 ? '+' : ''}${v.toFixed(2)}s`}
          hideMark
        />{' '}
        on raw race time, with a points difference of{' '}
        <StatusValue value={comparison.relativePoints} format={(v) => `${v > 0 ? '+' : ''}${v}`} hideMark />. All three
        are simulated under the plan, not measured.
      </P>

      {delta.strategyDivergence.length > 0 && (
        <Aside>
          Where the two stood apart at the flag: {delta.strategyDivergence.join('; ')}. Raw race time spans different
          interruptions in each race, so it is read with those rather than on its own.
        </Aside>
      )}
    </Section>
  );
}

function ThePlan({ report, driver }: { report: RaceReport; driver: Participant | null }) {
  const { comparison, session } = report;
  const ours = report.alternative;
  const recorded = report.baseline;
  const code = driver?.code ?? report.selectedParticipantId;

  return (
    <Section
      index="02"
      title="Our plan"
      standfirst="Where we asked the race to go differently, and everything that call was allowed to assume."
    >
      <P>
        Two races are on one clock. The first is the recorded race — {recorded.scenario.purpose}. The second is ours,{' '}
        <span className="font-semibold text-emerald-300">{ours.scenario.name}</span> — {ours.scenario.purpose}.
      </P>

      <P>
        They are the same race until lap {comparison.branchPoint.lap}, {formatClock(comparison.branchPoint.raceTimeS)} in,
        at the call the session names: {comparison.branchPoint.description}. Everything before that point is shared
        history and is not re-simulated. After it, {code} runs {ours.outcome.pitCount}{' '}
        {ours.outcome.pitCount === 1 ? 'stop' : 'stops'} on {ours.outcome.tyreUse} instead of the{' '}
        {recorded.outcome.pitCount} it took on {recorded.outcome.tyreUse}.
      </P>

      <Subhead>What the call was allowed to assume</Subhead>
      <DataList>
        <Datum label="Weather">
          <span className="text-[13px] font-normal text-white/60">{session.assumptions.weather}</span>
        </Datum>
        <Datum label="Interruptions">
          <span className="text-[13px] font-normal text-white/60">{session.assumptions.interruptions}</span>
        </Datum>
        <Datum label="Tyre sets">
          <span className="text-[13px] font-normal text-white/60">{session.assumptions.tyreSets}</span>
        </Datum>
        <Datum label="Pit loss">
          <StatusValue value={session.assumptions.pitLossS} format={(v) => `${v.toFixed(1)}s`} />
        </Datum>
        <Datum label="Starting states">
          <span className="text-[13px] font-normal text-white/60">{session.assumptions.startingStates}</span>
        </Datum>
      </DataList>

      <Aside>
        The other cars in our plan are {ours.scenario.opponentFormulation}: {session.assumptions.opponentBeliefs}.
        Nothing here claims they would have driven the same race against a different call — that is an assumption the
        result rests on, not something the evidence shows.
      </Aside>
    </Section>
  );
}

export function ReportArticle({
  report,
  participants,
}: {
  report: RaceReport;
  participants: Map<string, Participant>;
}) {
  const driver = participants.get(report.selectedParticipantId) ?? null;
  const { comparison } = report;
  const overtakes = findOvertakes(report);

  // The move section only exists when our car actually passed someone, so the numbering
  // after it shifts rather than leaving a gap in the document.
  const n = (position: number) => String(position - (overtakes.length === 0 ? 1 : 0)).padStart(2, '0');

  return (
    <Column className="pb-32">
      <Masthead report={report} driver={driver} />

      <div className="mt-14">
        <Lede>
          Over {report.baseline.totalLaps} laps at {report.session.identity.circuit},{' '}
          {driver?.name ?? report.selectedParticipantId} finished{' '}
          <StatusValue value={comparison.baseline.finishPosition} format={(v) => `P${v}`} hideMark /> in the race as it
          was run. Under our plan the same car finished{' '}
          <StatusValue value={comparison.alternative.finishPosition} format={(v) => `P${v}`} hideMark /> —{' '}
          <StatusValue value={comparison.relativePositions} format={places} hideMark />.
        </Lede>

        <P className="mt-6">
          It rests on one pit call, on lap {comparison.branchPoint.lap}, and on a field that does not react to it
          {comparison.stability?.changesUnderSupportedAssumption
            ? ' — and there is at least one supported assumption under which the preference reverses'
            : ''}
          .
        </P>
      </div>

      <div className="mt-24 flex flex-col">
        <TheResult report={report} driver={driver} />
        <ThePlan report={report} driver={driver} />
        <ChronicleSection index="03" report={report} participants={participants} />
        <OvertakeSection index="04" moves={overtakes} participants={participants} />
        <ClassificationSection index={n(5)} report={report} participants={participants} driver={driver} />
        <RobustnessSection index={n(6)} report={report} />
        <EvidenceSection index={n(7)} report={report} />
      </div>
    </Column>
  );
}
