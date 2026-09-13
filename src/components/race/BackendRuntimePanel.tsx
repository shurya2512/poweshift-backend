'use client';

import { useEffect, useState } from 'react';
import {
  DiagnosticCatalog,
  RuntimeRecommendation,
  fetchDiagnosticCatalog,
  startRegisteredRun,
  streamRegisteredRun,
} from '@/lib/backend/runtime';
import { Panel } from './primitives';
import { egoProfile } from '@/lib/backend/profiles';

const RUN_ID = process.env.NEXT_PUBLIC_POWESHIFT_RUN_ID;

export function BackendRuntimePanel({ track, profileEntry }: { track?: string; profileEntry?: string }) {
  const [catalog, setCatalog] = useState<DiagnosticCatalog | null>(null);
  const [available, setAvailable] = useState(true);
  const [recommendation, setRecommendation] = useState<RuntimeRecommendation | null>(null);

  useEffect(() => {
    let active = true;
    fetchDiagnosticCatalog()
      .then((value) => active && setCatalog(value))
      .catch(() => active && setAvailable(false));
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!RUN_ID) return;
    let close = () => {};
    let active = true;
    startRegisteredRun(RUN_ID)
      .then(() => {
        if (active) close = streamRegisteredRun(RUN_ID, setRecommendation, () => setAvailable(false));
      })
      .catch(() => active && setAvailable(false));
    return () => {
      active = false;
      close();
    };
  }, []);

  const raceReady = catalog?.race.filter((track) => track.status === 'diagnostic_only').length ?? 0;
  const raceUnavailable = catalog?.race.filter((track) => track.status === 'unavailable').length ?? 0;

  return (
    <Panel className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
      <div>
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-sky-400">Policy backend</p>
        <p className="mt-1 text-sm text-white">
          {!available ? 'Backend unavailable' : catalog
            ? `${catalog.qualifying.length} qualifying reports · ${raceReady} race reports · ${raceUnavailable} unavailable`
            : 'Connecting to diagnostic reports'}
        </p>
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
    </Panel>
  );
}
