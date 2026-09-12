import React from 'react';
import { RaceReport } from '@/lib/race/report';
import { EventGroup, Participant, RaceEvent } from '@/lib/race/types';
import { formatClock } from '../primitives';
import { Aside, Disclosure, Section, Side } from './article';

const GROUP_LABEL: Record<EventGroup, string> = {
  session_control: 'Session control',
  strategy: 'Strategy',
  competition: 'Competition',
  environment: 'Environment',
  outcome: 'Outcome',
  model: 'Model',
};

const WORLD_LABEL = {
  shared: 'Both races',
  baseline: 'Recorded race',
  alternative: 'Our plan',
} as const;

function Entry({ event, participants }: { event: RaceEvent; participants: Map<string, Participant> }) {
  const driver = event.participantId ? participants.get(event.participantId) : undefined;

  return (
    <li className="grid grid-cols-[auto_1fr] gap-x-5 border-b border-white/[0.06] py-3.5 sm:grid-cols-[92px_1fr]">
      <div className="pt-0.5">
        <p className="font-mono text-[12px] tabular-nums text-white/50">{formatClock(event.raceTimeS)}</p>
        <p className="mt-0.5 font-mono text-[10px] uppercase tracking-widest text-white/25">Lap {event.lap}</p>
      </div>
      <div>
        <p className="text-[15px] leading-snug text-white/75">{event.label}</p>
        <p className="mt-1 text-[11px] uppercase tracking-[0.12em]">
          <Side side={event.world}>{WORLD_LABEL[event.world]}</Side>
          <span className="text-white/20"> · </span>
          <span className="text-white/30">{GROUP_LABEL[event.group]}</span>
          {driver && (
            <>
              <span className="text-white/20"> · </span>
              <span className="text-white/40">{driver.name}</span>
            </>
          )}
        </p>
      </div>
    </li>
  );
}

/** Marks where shared history ends. Everything below it belongs to one race or the other. */
function Divider({ lap, description }: { lap: number; description: string }) {
  return (
    <li className="py-6">
      <div className="border-t border-dashed border-white/25 pt-3">
        <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-white/60">
          Lap {lap} — the two races separate
        </p>
        <p className="mt-1 text-[13px] leading-relaxed text-white/35">{description}</p>
      </div>
    </li>
  );
}

/** Events that moved our race: our own car, and anything that stopped or neutralised the race. */
const isMainLine = (event: RaceEvent, ourId: string): boolean =>
  event.participantId === ourId || event.group === 'session_control' || event.group === 'outcome';

function Chronicle({
  events,
  participants,
  branch,
}: {
  events: RaceEvent[];
  participants: Map<string, Participant>;
  branch: { lap: number; description: string };
}) {
  // Shared history ends at the first line that belongs to only one race — the two races
  // reach the branch on their own clocks, so the branch time alone would misplace this.
  const dividerAt = events.findIndex((e) => e.world !== 'shared');

  return (
    <ul className="border-t border-white/15">
      {events.map((event, i) => (
        <React.Fragment key={event.id}>
          {i === dividerAt && <Divider lap={branch.lap} description={branch.description} />}
          <Entry event={event} participants={participants} />
        </React.Fragment>
      ))}
    </ul>
  );
}

/** The race as it unfolded: our own laps first, the rest of the field's kept behind. */
export function ChronicleSection({
  report,
  participants,
}: {
  report: RaceReport;
  participants: Map<string, Participant>;
}) {
  const events = [...report.events].sort((a, b) => a.raceTimeS - b.raceTimeS);
  const branch = report.comparison.branchPoint;
  const ourId = report.selectedParticipantId;
  const main = events.filter((e) => isMainLine(e, ourId));
  const rest = events.filter((e) => !isMainLine(e, ourId));

  if (events.length === 0) {
    return (
      <Section title="What happened" standfirst="The race in order.">
        <Aside>No events were supplied for this race.</Aside>
      </Section>
    );
  }

  return (
    <Section
      title="What happened"
      standfirst="Our car's race, in order. Lines before the branch belong to both races; after it, each names the one it belongs to."
    >
      <Chronicle events={main} participants={participants} branch={branch} />

      {rest.length > 0 && (
        <Disclosure summary={`The rest of the field — ${rest.length} more events`}>
          <Chronicle events={rest} participants={participants} branch={branch} />
        </Disclosure>
      )}
    </Section>
  );
}
