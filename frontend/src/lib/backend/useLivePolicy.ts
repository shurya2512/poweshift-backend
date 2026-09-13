'use client';

import { useEffect, useRef, useState } from 'react';
import { LiveObservation, LiveRecommendation, openLivePolicy } from './runtime';
import { ParticipantState } from '@/lib/race/types';
import { isSupported } from '@/lib/race/valued';

// Matches the checkpoint's declared input rate; the backend decides at 5 Hz on its own.
const SEND_INTERVAL_MS = 250;

export type LiveConnectionState = 'connecting' | 'streaming' | 'error';

export interface LivePolicyState {
  recommendation: LiveRecommendation | null;
  connection: LiveConnectionState;
  error: string | null;
}

/**
 * Opens the live policy socket for `runId` and pushes observations built from the
 * currently displayed race frame at 4 Hz. Unsupported values are masked, never guessed.
 */
export function useLivePolicy(
  runId: string | undefined,
  participant: ParticipantState | undefined,
  raceTimeS: number | undefined,
): LivePolicyState {
  const [recommendation, setRecommendation] = useState<LiveRecommendation | null>(null);
  const [connection, setConnection] = useState<LiveConnectionState>('connecting');
  const [error, setError] = useState<string | null>(null);

  // Read inside the send interval so it always uses the latest frame without being recreated.
  const latestRef = useRef<{ participant?: ParticipantState; raceTimeS?: number }>({});
  latestRef.current = { participant, raceTimeS };

  useEffect(() => {
    if (!runId) return;
    let active = true;
    let sequence = 0;

    const socket = openLivePolicy(
      runId,
      (frame) => {
        if (!active) return;
        setRecommendation(frame);
        setConnection('streaming');
      },
      () => {
        if (!active) return;
        setConnection('error');
        setError('Live policy socket disconnected');
      },
    );

    const timer = setInterval(() => {
      const { participant: p, raceTimeS: t } = latestRef.current;
      if (!p || t === undefined) return;

      const speed = p.speedKmh;
      const energy = p.energy.storedMj;
      const speedSupported = isSupported(speed);
      const energySupported = isSupported(energy);

      // Backend requires finite values even when masked, so unsupported fields send a placeholder.
      const observation: LiveObservation = {
        sequence: sequence++,
        observed_at_s: t,
        values: [speedSupported ? speed.value / 3.6 : 0, energySupported ? energy.value * 1e6 : 0],
        feature_mask: [speedSupported, energySupported],
        action_mask: [true, true, true, true],
        deployment_available: true,
        news_prior_ids: [],
      };
      socket.send(observation);
    }, SEND_INTERVAL_MS);

    return () => {
      active = false;
      clearInterval(timer);
      socket.close();
    };
  }, [runId]);

  return { recommendation, connection, error };
}
