import React from 'react';
import { Participant, RaceFrame, SessionInfo } from '@/lib/race/types';
import { Eyebrow, Panel } from './primitives';
import { StatusValue } from './StatusValue';

interface DeltaColumnProps {
  frame: RaceFrame;
  session: SessionInfo;
  selected: Participant | null;
}

/**
 * Differences only. This region never becomes a third race world — it reports how
 * the two supplied worlds differ, and nothing about a race of its own.
 */
export function DeltaColumn({ frame, session, selected }: DeltaColumnProps) {
  const beforeBranch = frame.raceTimeS < session.branchPoint.raceTimeS;
  const baselineRank = frame.baseline.field.find((p) => p.participantId === selected?.id)?.rank;
  const altRank = frame.alternative.field.find((p) => p.participantId === selected?.id)?.rank;

  return (
    <Panel className="flex flex-col gap-5 p-5">
      <div>
        <Eyebrow>Live differences</Eyebrow>
        <p className="mt-1 text-sm font-semibold text-white">{selected ? selected.code : 'No driver selected'}</p>
      </div>

      {beforeBranch ? (
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4">
          <p className="text-xs font-semibold text-white/70">Shared history</p>
          <p className="mt-1 text-[11px] leading-relaxed text-white/40">
            Both worlds are identical until lap {session.branchPoint.lap}. There is nothing to compare yet.
          </p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4">
              <Eyebrow>Position</Eyebrow>
              <p className="mt-2 text-lg font-bold tabular-nums text-white">
                {baselineRank ?? '–'} <span className="text-white/30">→</span> {altRank ?? '–'}
              </p>
              <div className="mt-1 text-[11px] text-white/45">
                <StatusValue
                  value={frame.delta.positionDelta}
                  format={(v) => (v === 0 ? 'no change' : v < 0 ? `${-v} place gain` : `${v} place loss`)}
                />
              </div>
            </div>
            <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4">
              <Eyebrow>Track time</Eyebrow>
              <div className="mt-2 text-lg font-bold tabular-nums text-white">
                <StatusValue value={frame.delta.timeDeltaS} format={(v) => `${v > 0 ? '+' : ''}${v.toFixed(2)}s`} />
              </div>
            </div>
          </div>

          <div>
            <Eyebrow className="mb-2">Strategy divergence</Eyebrow>
            <ul className="space-y-1.5">
              {frame.delta.strategyDivergence.map((line) => (
                <li key={line} className="flex gap-2 text-[11px] leading-relaxed text-white/50">
                  <span className="text-white/25">·</span>
                  {line}
                </li>
              ))}
            </ul>
          </div>
        </>
      )}

      <div className="mt-auto border-t border-white/[0.06] pt-3">
        <Eyebrow>Confidence</Eyebrow>
        <p className="mt-1 text-[11px] leading-relaxed text-white/40">
          {frame.forecastHorizonS === undefined
            ? 'Replay of a supplied scenario — no forecast horizon applies.'
            : `Supported for ${frame.forecastHorizonS.toFixed(0)} s beyond the cutoff.`}
        </p>
      </div>
    </Panel>
  );
}
