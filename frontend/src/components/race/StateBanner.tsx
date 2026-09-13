import React from 'react';
import { SessionInfo, SupportState } from '@/lib/race/types';
import { PlaybackStatus } from '@/lib/race/useRaceSession';
import { Eyebrow, Panel } from './primitives';

interface StateBannerProps {
  session: SessionInfo;
  support: SupportState;
  playback: PlaybackStatus;
  reason?: string;
  error?: string;
}

const TONE: Record<string, string> = {
  amber: 'border-amber-400/25 bg-amber-400/10 text-amber-200',
  violet: 'border-violet-400/25 bg-violet-400/10 text-violet-200',
  red: 'border-red-400/25 bg-red-400/10 text-red-200',
  neutral: 'border-white/10 bg-white/[0.04] text-white/70',
};

/**
 * The requested question stays visible in every degraded state. A missing answer is
 * reported as missing, with what is absent — never quietly replaced by a partial one.
 */
export function StateBanner({ session, support, playback, reason, error }: StateBannerProps) {
  const question = `${session.identity.season} ${session.identity.event} — baseline against "${session.branchPoint.description}"`;

  const spec = (() => {
    if (playback === 'disconnected')
      return {
        tone: 'amber',
        title: 'Disconnected — showing the last confirmed frame',
        body: 'This state is stale. Nothing newer has been accepted; the frame below has not been updated since the connection dropped.',
      };
    switch (support) {
      case 'partial':
        return {
          tone: 'amber',
          title: 'Partial result',
          body: reason ?? 'Some values or one race world are incomplete. Available regions are preserved below.',
        };
      case 'stale':
        return {
          tone: 'amber',
          title: 'Stale',
          body: reason ?? 'No newer state has been accepted.',
        };
      case 'unsupported':
        return {
          tone: 'neutral',
          title: 'Not supported by the available evidence',
          body: reason ?? 'The backend cannot answer this comparison with the inputs it has.',
        };
      case 'abstained':
        return {
          tone: 'violet',
          title: 'Abstained',
          body: reason ?? 'The backend declined to answer beyond its supported horizon.',
        };
      case 'failed':
        return {
          tone: 'red',
          title: 'Comparison failed',
          body: error ?? reason ?? 'The scenario inputs are preserved below.',
        };
      default:
        return null;
    }
  })();

  if (!spec) return null;

  return (
    <Panel className={`border p-6 px-8 ${TONE[spec.tone]}`}>
      <Eyebrow className="!text-current opacity-60">Requested comparison</Eyebrow>
      <p className="mt-1 text-sm font-semibold">{question}</p>
      <div className="mt-4 border-t border-current/20 pt-3 opacity-90">
        <p className="text-sm font-bold">{spec.title}</p>
        <p className="mt-1 text-[11px] leading-relaxed">{spec.body}</p>
        {support === 'abstained' && (
          <p className="mt-2 text-[11px] opacity-70">
            Supported horizon: {session.validity.supportedHorizonS.toFixed(0)} s.
            {session.validity.fallbacks.length > 0
              ? ` Fallback: ${session.validity.fallbacks.join('; ')}.`
              : ' No safe fallback result is available.'}
          </p>
        )}
      </div>
    </Panel>
  );
}
