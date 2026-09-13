'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft } from 'lucide-react';
import { EGO_PROFILES, admittedProfiles, egoProfile } from '@/lib/backend/profiles';
import {
  DiagnosticSummary,
  QualifyingProfileReport,
  RaceProfileReport,
  diagnosticReportPath,
  formatEnergy,
  summarizeRaceProfile,
} from '@/lib/backend/report';
import {
  DiagnosticCatalog,
  DiagnosticTrack,
  fetchDiagnosticCatalog,
  fetchDiagnosticReport,
} from '@/lib/backend/runtime';
import { Aside, Column, Figure, P, Section, Table, Td, Th } from '@/components/race/report/article';

type ReportMode = 'qualifying' | 'race';

const clock = (seconds: number): string => {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${(seconds - minutes * 60).toFixed(1).padStart(4, '0')}`;
};

const percent = (value: number): string => `${Math.round(value * 100)}%`;

function Select({ label, value, onChange, children }: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
}) {
  return (
    <label className="flex min-w-0 flex-1 flex-col gap-2">
      <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-white/35">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-xl border border-white/10 bg-neutral-950 px-4 py-3 text-sm text-white outline-none focus:border-sky-400/60"
      >
        {children}
      </select>
    </label>
  );
}

function RaceReport({ report }: { report: RaceProfileReport }) {
  const profile = egoProfile(report.profile_entry);
  const view = summarizeRaceProfile(report);
  const race = report.p23;
  const total = race.opportunity_totals;
  const opportunities = [...race.opportunity_episodes].sort((a, b) => a.start_time_s - b.start_time_s);
  const policyActions = [...race.policy_action_episodes].sort((a, b) => a.start_time_s - b.start_time_s);
  const eventDecisions = [...race.major_event_decisions].sort((a, b) => a.event.time_s - b.event.time_s);

  return (
    <>
      <div className="mt-14">
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-300">P23 race diagnostic</p>
        <h1 className="mt-3 text-4xl font-black uppercase leading-none tracking-tighter md:text-7xl">{report.event_name}</h1>
        <P className="mt-6">
          {profile.name}&apos;s promoted profile starts independently at P23. The other {race.reference_entries} cars
          replay source controls without electric deployment or overtake intelligence.
        </P>
      </div>

      <div className="mt-12 grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-white/10 bg-white/10 md:grid-cols-4">
        {[
          ['Ego journey', `${view.ego.start} → ${view.ego.finish}`],
          ['Positions gained', `${view.ego.positionsGained >= 0 ? '+' : ''}${view.ego.positionsGained}`],
          ['Energy deployed', view.ego.deployment],
          ['Energy harvested', view.ego.harvest],
        ].map(([label, value]) => (
          <div key={label} className="bg-black px-5 py-5">
            <p className="text-[10px] uppercase tracking-widest text-white/35">{label}</p>
            <p className="mt-2 text-xl font-black text-white">{value}</p>
          </div>
        ))}
      </div>

      <div className="mt-24 flex flex-col">
        <Section title="Ego against the original field" standfirst="The control field and independently controlled ego are separate populations, not two labels for the same car.">
          <Figure title="Treatment boundary" note="The reference field is replayed; only the added P23 ego receives policy actions and electric energy.">
            <Table minWidth={620}>
              <thead><tr><Th>Measure</Th><Th className="text-right text-sky-300/60">Original 22-car field</Th><Th className="text-right text-emerald-300/60">Selected ego</Th></tr></thead>
              <tbody>
                <tr><Td>Identity</Td><Td className="text-right">{view.reference.field}</Td><Td className="text-right">{profile.name} · profile #{profile.entry}</Td></tr>
                <tr><Td>Starting state</Td><Td className="text-right">{view.reference.start}</Td><Td className="text-right font-bold text-white">{view.ego.start}</Td></tr>
                <tr><Td>Finish</Td><Td className="text-right">Held source field</Td><Td className="text-right font-bold text-white">{view.ego.finish}</Td></tr>
                <tr><Td>Overtake intelligence</Td><Td className="text-right">{view.reference.intelligence}</Td><Td className="text-right">Attack / defend / hold</Td></tr>
                <tr><Td>Electric deployment</Td><Td className="text-right">{view.reference.electricEnergy}</Td><Td className="text-right">{view.ego.deployment}</Td></tr>
                <tr><Td>Input / decision clocks</Td><Td className="text-right">{race.field_input_hz} Hz source</Td><Td className="text-right">{race.decision_hz} Hz policy</Td></tr>
              </tbody>
            </Table>
          </Figure>
          <Aside>
            The report does not claim a counterfactual finish for the original profile. It compares one added policy ego
            with the fixed policy-free field that defines its traffic and final proxy position. Times use source timestamps;
            the report begins at the first complete 22-car tick, which may be later than 0:00.
          </Aside>
        </Section>

        <Section title="Overtake decisions" standfirst="Every detected attack or defence window is shown, including windows where the policy held instead of acting.">
          <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
            {[
              ['Attack windows', total.attack_episodes], ['Attacks taken', total.attack_taken], ['Attacks missed', total.attack_missed],
              ['Defence threats', total.defence_episodes], ['Defences taken', total.defence_taken], ['Defences missed', total.defence_missed],
            ].map(([label, value]) => <div key={label} className="border-b border-white/10 pb-3"><p className="text-white/35">{label}</p><p className="mt-1 text-xl font-black">{value}</p></div>)}
          </div>

          <Figure title="Opportunity timeline" note="Probability is the uncalibrated selection probability reported by the policy.">
            <Table minWidth={900}>
              <thead><tr><Th>Lap / time</Th><Th>Window</Th><Th>Decision</Th><Th className="text-right">Probability</Th><Th className="text-right">Power</Th><Th className="text-right">Deploy / harvest</Th><Th className="text-right">Store</Th></tr></thead>
              <tbody>
                {opportunities.map((episode, index) => (
                  <tr key={`${episode.kind}-${episode.start_time_s}-${index}`}>
                    <Td>L{episode.lap} · {clock(episode.start_time_s)}–{clock(episode.end_time_s)}</Td>
                    <Td className={episode.kind === 'attack' ? 'text-emerald-300/80' : 'text-amber-300/80'}>{episode.kind}</Td>
                    <Td>{episode.taken ? 'Taken' : 'Held'} · {(episode.selected_paths ?? []).join(', ') || 'none'}</Td>
                    <Td className="text-right">{percent(episode.maximum_uncalibrated_action_probability)}</Td>
                    <Td className="text-right">{episode.peak_motor_wheel_power_kw.toFixed(1)} kW</Td>
                    <Td className="text-right">{formatEnergy(episode.deployment_j)} / {formatEnergy(episode.harvest_j)}</Td>
                    <Td className="text-right">{formatEnergy(episode.stored_energy_start_j ?? 0)} → {formatEnergy(episode.stored_energy_end_j ?? 0)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Figure>

          <Figure title="Policy action episodes" note="Actions outside a detected opportunity remain visible instead of being counted as overtakes.">
            <Table minWidth={760}>
              <thead><tr><Th>Lap / time</Th><Th>Path</Th><Th>Traffic context</Th><Th className="text-right">Probability</Th><Th className="text-right">Peak power</Th><Th className="text-right">Energy</Th></tr></thead>
              <tbody>
                {policyActions.map((episode, index) => (
                  <tr key={`${episode.path}-${episode.start_time_s}-${index}`}>
                    <Td>L{episode.lap} · {clock(episode.start_time_s)}–{clock(episode.end_time_s)}</Td>
                    <Td>{episode.path}</Td>
                    <Td>{episode.attack_opportunity_present ? 'Attack window' : episode.defence_threat_present ? 'Defence threat' : 'No detected window'}</Td>
                    <Td className="text-right">{percent(episode.maximum_uncalibrated_action_probability)}</Td>
                    <Td className="text-right">{episode.peak_motor_wheel_power_kw.toFixed(1)} kW</Td>
                    <Td className="text-right">{formatEnergy(episode.deployment_j)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Figure>
        </Section>

        <Section title="Lap-by-lap performance" standfirst="Position, tactical activity and energy accounting on the same source-relative clock.">
          <Figure title={`${race.laps.length} reported laps`} note="Start and end positions are the ego's proxy rank among the 22 references plus itself.">
            <Table minWidth={980}>
              <thead><tr><Th>Lap / time</Th><Th className="text-right">Position</Th><Th className="text-right">Attack opp / act</Th><Th className="text-right">Defence threat / act</Th><Th className="text-right">Request</Th><Th className="text-right">Peak</Th><Th className="text-right">Deploy / harvest</Th><Th className="text-right">Store</Th></tr></thead>
              <tbody>
                {race.laps.map((lap) => (
                  <tr key={lap.lap}>
                    <Td>L{lap.lap} · {clock(lap.start_time_s)}–{clock(lap.end_time_s)}</Td>
                    <Td className="text-right">P{lap.start_position} → P{lap.end_position}</Td>
                    <Td className="text-right">{lap.attack_opportunity_ticks} / {lap.attack_ticks}</Td>
                    <Td className="text-right">{lap.defence_threat_ticks} / {lap.defend_ticks}</Td>
                    <Td className="text-right">{percent(lap.mean_requested_deployment_fraction)}</Td>
                    <Td className="text-right">{lap.maximum_motor_wheel_power_kw.toFixed(1)} kW</Td>
                    <Td className="text-right">{formatEnergy(lap.deployment_j)} / {formatEnergy(lap.harvest_j)}</Td>
                    <Td className="text-right">{formatEnergy(lap.stored_energy_start_j)} → {formatEnergy(lap.stored_energy_end_j)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Figure>
        </Section>

        <Section title="Race-control decisions" standfirst="Source events are paired with the nearest 5 Hz policy row; the time delta is printed explicitly.">
          {eventDecisions.length === 0 ? <P>No yellow-flag, safety-car or virtual-safety-car event was bound in this source.</P> : (
            <Figure title="Major event timeline">
              <Table minWidth={760}>
                <thead><tr><Th>Event</Th><Th>Nearest decision</Th><Th className="text-right">Probability</Th><Th className="text-right">Requested</Th><Th className="text-right">Power</Th><Th className="text-right">Alignment</Th></tr></thead>
                <tbody>{eventDecisions.map((row, index) => <tr key={`${row.event.label}-${row.event.time_s}-${index}`}><Td>{row.event.label} · {clock(row.event.time_s)}</Td><Td>L{row.nearest_policy_decision.lap} · {row.nearest_policy_decision.path}</Td><Td className="text-right">{percent(row.nearest_policy_decision.uncalibrated_action_probability)}</Td><Td className="text-right">{percent(row.nearest_policy_decision.requested_deployment_fraction)}</Td><Td className="text-right">{row.nearest_policy_decision.motor_wheel_power_kw.toFixed(1)} kW</Td><Td className="text-right">{row.decision_time_delta_s.toFixed(3)}s</Td></tr>)}</tbody>
              </Table>
            </Figure>
          )}
        </Section>

        <Section title="Limits" standfirst="These boundaries apply to every number above.">
          {race.limitations.map((limit) => <Aside key={limit}>{limit}</Aside>)}
        </Section>
      </div>
    </>
  );
}

function QualifyingReport({ report }: { report: QualifyingProfileReport }) {
  const profile = egoProfile(report.profile_entry);
  const available = report.best_observed_lap_time_s !== null && report.best_diagnostic_attainable_lap_time_s !== null;

  return (
    <>
      <div className="mt-14">
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-sky-300">
          {report.event_name === 'Spanish Grand Prix' ? 'Madring qualifying test' : 'Qualifying diagnostic'}
        </p>
        <h1 className="mt-3 text-4xl font-black uppercase leading-none tracking-tighter md:text-7xl">{report.event_name}</h1>
        <P className="mt-6">{profile.name} · promoted profile #{profile.entry}. Overtake intelligence is masked in qualifying; this report isolates energy deployment against each observed lap.</P>
      </div>

      {!available ? <div className="mt-12"><Aside>This profile has no qualifying laps in the selected source. No time or energy value has been substituted.</Aside></div> : (
        <div className="mt-12 grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-white/10 bg-white/10 md:grid-cols-4">
          {[
            ['Best observed', `${report.best_observed_lap_time_s!.toFixed(3)}s`],
            ['Best diagnostic proxy', `${report.best_diagnostic_attainable_lap_time_s!.toFixed(3)}s`],
            ['Energy deployed', formatEnergy(report.gross_deployment_j)],
            ['Energy harvested', formatEnergy(report.gross_harvest_j)],
          ].map(([label, value]) => <div key={label} className="bg-black px-5 py-5"><p className="text-[10px] uppercase tracking-widest text-white/35">{label}</p><p className="mt-2 text-xl font-black">{value}</p></div>)}
        </div>
      )}

      <div className="mt-24 flex flex-col">
        <Section title="Lap-by-lap energy" standfirst="Observed and idealized diagnostic lap times share the same source lap and energy account.">
          <Figure title={`${report.laps.length} qualifying laps`} note="The attainable time is an additive-power-ratio proxy, not a physical prediction.">
            <Table minWidth={980}>
              <thead><tr><Th>Source lap</Th><Th>Path</Th><Th className="text-right">Observed</Th><Th className="text-right">Diagnostic</Th><Th className="text-right">Proxy gain</Th><Th className="text-right">Probability</Th><Th className="text-right">Request / delivered</Th><Th className="text-right">Peak</Th><Th className="text-right">Deploy / harvest</Th><Th className="text-right">Store</Th></tr></thead>
              <tbody>{report.laps.map((lap) => <tr key={lap.source_lap}><Td>L{lap.source_lap}</Td><Td>{lap.path}</Td><Td className="text-right">{lap.observed_lap_time_s.toFixed(3)}s</Td><Td className="text-right">{lap.diagnostic_attainable_lap_time_s.toFixed(3)}s</Td><Td className="text-right">{lap.diagnostic_time_gain_proxy_s.toFixed(3)}s</Td><Td className="text-right">{percent(lap.mean_uncalibrated_action_probability)}</Td><Td className="text-right">{percent(lap.mean_requested_deployment_fraction)} / {percent(lap.mean_delivered_deployment_fraction)}</Td><Td className="text-right">{lap.peak_motor_wheel_power_kw.toFixed(1)} kW</Td><Td className="text-right">{formatEnergy(lap.gross_deployment_j)} / {formatEnergy(lap.gross_harvest_j)}</Td><Td className="text-right">{formatEnergy(lap.stored_energy_start_j)} → {formatEnergy(lap.stored_energy_end_j)}</Td></tr>)}</tbody>
            </Table>
          </Figure>
          <Aside>{report.lap_time_semantics.replaceAll('_', ' ')}. Probability means {report.probability_semantics.replaceAll('_', ' ')}.</Aside>
        </Section>
      </div>
    </>
  );
}

export function ReportView() {
  const search = useSearchParams();
  const router = useRouter();
  const mode: ReportMode = search.get('mode') === 'qualifying' ? 'qualifying' : 'race';
  const [catalog, setCatalog] = useState<DiagnosticCatalog | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<{
    key: string;
    summary: DiagnosticSummary | null;
    report: RaceProfileReport | QualifyingProfileReport | null;
    error: string | null;
  }>({ key: '', summary: null, report: null, error: null });
  const tracks = useMemo(() => catalog?.[mode] ?? [], [catalog, mode]);
  const requestedTrack = search.get('track');
  const selectedTrack = useMemo(
    () => tracks.find((item) => item.event_name === requestedTrack && item.status !== 'unavailable')
      ?? tracks.find((item) => item.status !== 'unavailable')
      ?? tracks[0],
    [requestedTrack, tracks],
  );
  const track = selectedTrack?.event_name ?? '';
  const trackProfiles = useMemo(() => admittedProfiles(selectedTrack?.profiles), [selectedTrack]);
  const requestedProfile = search.get('profile') ?? '1';
  const profile = trackProfiles.some((item) => item.entry === requestedProfile)
    ? requestedProfile
    : trackProfiles[0]?.entry ?? requestedProfile;
  const loadKey = `${mode}:${track}:${profile}`;

  useEffect(() => {
    fetchDiagnosticCatalog().then(setCatalog).catch(() => setCatalogError('The diagnostic backend is unavailable.'));
  }, []);

  useEffect(() => {
    if (!selectedTrack) return;
    let active = true;
    fetchDiagnosticReport<DiagnosticSummary>(`${mode}/${selectedTrack.summary}`)
      .then((nextSummary) => {
        if (nextSummary.status === 'unavailable') throw new Error(nextSummary.reason ?? 'This report is unavailable.');
        const relative = nextSummary.reports?.[profile];
        if (!relative) throw new Error('The selected profile has no registered report for this event.');
        return fetchDiagnosticReport<RaceProfileReport | QualifyingProfileReport>(diagnosticReportPath(mode, selectedTrack.summary, relative))
          .then((nextReport) => ({ summary: nextSummary, report: nextReport }));
      })
      .then((value) => active && setLoaded({ key: loadKey, ...value, error: null }))
      .catch((reason: Error) => active && setLoaded({ key: loadKey, summary: null, report: null, error: reason.message }));
    return () => { active = false; };
  }, [loadKey, mode, profile, selectedTrack]);

  const replaceSelection = (nextTrack: string, nextProfile: string) => {
    const params = new URLSearchParams(search.toString());
    params.set('mode', mode);
    params.set('track', nextTrack);
    params.set('profile', nextProfile);
    router.replace(`/report?${params.toString()}`);
  };

  return (
    <div className="px-4 py-8 sm:px-8 md:px-10">
      <Column className="mb-12 flex flex-col items-start justify-between gap-3 border-b border-white/[0.07] pb-5 sm:flex-row sm:items-center">
        <Link href={mode === 'race' ? '/full-race' : '/setup-qualifying'} className="flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] text-white/40 hover:text-white"><ArrowLeft size={14} /> {mode === 'race' ? 'Race' : 'Setup'}</Link>
        <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/30">Backend diagnostic · not physics-admitted</span>
      </Column>

      <Column>
        <div className="flex flex-col gap-4 rounded-2xl border border-white/10 bg-white/[0.03] p-5 sm:flex-row">
          <Select label="Report set" value={mode} onChange={(value) => router.replace(`/report?mode=${value}&profile=${profile}`)}><option value="race">Race P23</option><option value="qualifying">Qualifying</option></Select>
          <Select label="Circuit" value={track} onChange={(value) => replaceSelection(value, profile)}>{tracks.map((item: DiagnosticTrack) => <option key={item.event_name} value={item.event_name} disabled={item.status === 'unavailable'}>{item.event_name}{item.status === 'unavailable' ? ' · unavailable' : ''}</option>)}</Select>
          <Select label="Ego driver / profile" value={profile} onChange={(value) => replaceSelection(track, value)}>{trackProfiles.map((item) => <option key={item.entry} value={item.entry}>{item.code} · #{item.entry} · {item.name}</option>)}</Select>
        </div>

        {loaded.key === loadKey && loaded.summary?.profiles_without_laps?.includes(profile) && <div className="mt-8"><Aside>The selected source contains no qualifying laps for profile #{profile}; the empty report is shown without substitution.</Aside></div>}
        {loaded.key === loadKey && loaded.summary?.profiles_relieved && loaded.summary.profiles_relieved.length > 0 && (
          <div className="mt-8"><Aside>
            {loaded.summary.profiles_relieved.length} of {EGO_PROFILES.length} profiles are relieved at this event because their own source telemetry cannot carry a full race: {loaded.summary.profiles_relieved.map((item) => `#${item.profile_entry} (${item.reason.includes('sparse') ? `${Math.round((item.sample_density ?? 0) * 100)}% sampled` : `ends at ${Math.round(item.covered_span_fraction * 100)}% of the race`})`).join(', ')}. They stay in the reference field and carry no report.
          </Aside></div>
        )}
        {catalogError ? <div className="mt-12"><Aside>{catalogError}</Aside></div> : loaded.key !== loadKey ? <P className="mt-12">Loading the selected diagnostic report…</P> : loaded.error ? <div className="mt-12"><Aside>{loaded.error}</Aside></div> : mode === 'race' ? <RaceReport report={loaded.report as RaceProfileReport} /> : <QualifyingReport report={loaded.report as QualifyingProfileReport} />}
      </Column>
    </div>
  );
}
