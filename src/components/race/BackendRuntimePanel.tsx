'use client';

import { useEffect, useState } from 'react';
import {
  DiagnosticCatalog,
  RunReport,
  RunStatus,
  RuntimeRecommendation,
  controlRun,
  fetchDiagnosticCatalog,
  fetchLatestRecommendation,
  fetchRunReport,
  fetchRunStatus,
  startRegisteredRun,
  streamRegisteredRun,
} from '@/lib/backend/runtime';
import { useLivePolicy } from '@/lib/backend/useLivePolicy';
import { Panel } from './primitives';
import { egoProfile } from '@/lib/backend/profiles';
import { ParticipantState } from '@/lib/race/types';

const RUN_ID = process.env.NEXT_PUBLIC_POWESHIFT_RUN_ID;

// States where pause/resume/stop still change anything.
const PAUSABLE: RunStatus['status'][] = ['running'];
const RESUMABLE: RunStatus['status'][] = ['pending'];
const STOPPABLE: RunStatus['status'][] = ['pending', 'running'];

export function BackendRuntimePanel({
  track,
  profileEntry,
  participant,
  raceTimeS,
}: {
  track?: string;
  profileEntry?: string;
  participant?: ParticipantState;
  raceTimeS?: number;
}) {
  const [catalog, setCatalog] = useState<DiagnosticCatalog | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [controlError, setControlError] = useState<string | null>(null);
  const [recommendation, setRecommendation] = useState<RuntimeRecommendation | null>(null);
  const [runStatus, setRunStatus] = useState<RunStatus | null>(null);
  const [runReport, setRunReport] = useState<RunReport | null>(null);

  useEffect(() => {
    let active = true;
    fetchDiagnosticCatalog()
      .then((value) => active && setCatalog(value))
      .catch((err) => active && setCatalogError(err instanceof Error ? err.message : 'Backend unavailable'));
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!RUN_ID) return;
    let close = () => {};
    let active = true;
    startRegisteredRun(RUN_ID)
      .then(async () => {
        if (!active) return;
        close = streamRegisteredRun(RUN_ID, setRecommendation, () =>
          active && setRunError('Recommendation stream disconnected'),
        );
        // Seed with the latest result so a completed run isn't blank until a new frame streams in.
        const [latest, status, report] = await Promise.all([
          fetchLatestRecommendation(RUN_ID),
          fetchRunStatus(RUN_ID),
          fetchRunReport(RUN_ID),
        ]);
        if (!active) return;
        if (latest) setRecommendation(latest);
        setRunStatus(status);
        setRunReport(report);
      })
      .catch((err) => active && setRunError(err instanceof Error ? err.message : 'Backend unavailable'));
    return () => {
      active = false;
      close();
    };
  }, []);

  const live = useLivePolicy(RUN_ID, participant, raceTimeS);

  const runControl = (command: 'pause' | 'resume' | 'stop') => {
    if (!RUN_ID) return;
    controlRun(RUN_ID, command)
      .then(() => fetchRunStatus(RUN_ID))
      .then(setRunStatus)
      .catch((err) => setControlError(err instanceof Error ? err.message : 'Run control failed'));
  };

  const raceReady = catalog?.race.filter((entry) => entry.status === 'diagnostic_only').length ?? 0;
  const raceUnavailable = catalog?.race.filter((entry) => entry.status === 'unavailable').length ?? 0;

  return (
    <Panel className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
      <div>
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-sky-400">Policy backend</p>
        <p className="mt-1 text-sm text-white">
          {catalogError ?? (catalog
            ? `${catalog.qualifying.length} qualifying reports · ${raceReady} race reports · ${raceUnavailable} unavailable`
            : 'Connecting to diagnostic reports')}
        </p>
        {runStatus && (
          <p className="mt-1 text-[11px] uppercase tracking-wide text-white/45">
            Run {runStatus.status} · {runStatus.recommendation_count} recommendations
            {runStatus.error && <span className="text-red-300"> · {runStatus.error}</span>}
          </p>
        )}
        {runError && <p className="mt-1 text-[11px] text-red-300">{runError}</p>}
        {controlError && <p className="mt-1 text-[11px] text-red-300">{controlError}</p>}
        {runReport && runReport.limitations.length > 0 && (
          <p className="mt-1 max-w-md text-[10px] italic leading-snug text-white/35">
            {runReport.limitations.join(' · ')}
          </p>
        )}
        {RUN_ID && runStatus && (
          <div className="mt-2 flex gap-2 text-[10px] uppercase tracking-widest">
            {PAUSABLE.includes(runStatus.status) && (
              <button onClick={() => runControl('pause')} className="text-white/45 hover:text-white">
                Pause
              </button>
            )}
            {RESUMABLE.includes(runStatus.status) && (
              <button onClick={() => runControl('resume')} className="text-white/45 hover:text-white">
                Resume
              </button>
            )}
            {STOPPABLE.includes(runStatus.status) && (
              <button onClick={() => runControl('stop')} className="text-white/45 hover:text-white">
                Stop
              </button>
            )}
          </div>
        )}
      </div>
      <div className="text-right text-xs text-white/55">
        {recommendation ? (
          <>
            <p className="font-semibold uppercase text-white">{recommendation.intent}</p>
            <p>{Math.round(recommendation.deployment_fraction * 100)}% requested deployment</p>
          </>
        ) : (
          <>
            {track && profileEntry && <p className="font-semibold text-white">{track} · {egoProfile(profileEntry).code} #{profileEntry}</p>}
            <p>{RUN_ID ? 'Waiting for registered run' : 'Open report for stored decisions'}</p>
          </>
        )}
      </div>
      {RUN_ID && (
        <div className="rounded border border-emerald-400/25 bg-emerald-400/5 px-3 py-2 text-right text-xs">
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-300">Live policy inference</p>
          {live.recommendation ? (
            <>
              <p className="mt-1 font-semibold uppercase text-white">
                {live.recommendation.recommendation.intent}
                {live.recommendation.held_source_frame && (
                  <span className="ml-1.5 text-amber-300">· held frame</span>
                )}
              </p>
              <p className="text-white/45">{live.recommendation.decision_hz} Hz decisions</p>
            </>
          ) : (
            <p className="text-white/45">{live.error ?? 'Connecting to live policy'}</p>
          )}
          {/* Inference is real; the input feeding it is the fixture race stream, not measured telemetry. */}
          <p className="mt-1 text-[10px] italic text-white/35">Live policy inference on fixture-derived input</p>
        </div>
      )}
    </Panel>
  );
}
