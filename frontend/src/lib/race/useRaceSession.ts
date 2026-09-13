'use client';

import { useEffect, useMemo, useReducer, useRef } from 'react';
import { RaceReport } from './report';
import { RaceMessage, RaceSource, SessionRequest } from './source';
import { Battle, ComparisonResult, RaceEvent, RaceFrame, SessionInfo, SupportState } from './types';

export type PlaybackStatus = 'preparing' | 'streaming' | 'paused' | 'complete' | 'disconnected';

export interface RaceSessionState {
  session: SessionInfo | null;
  frame: RaceFrame | null;
  events: RaceEvent[];
  comparison: ComparisonResult | null;
  battles: Battle[];
  /** Only ever what the source delivered. A report is never assembled in this reducer. */
  report: RaceReport | null;
  supportState: SupportState;
  supportReason?: string;
  playback: PlaybackStatus;
  rate: number;
  /** The last confirmed frame is retained on disconnect and marked stale. */
  stale: boolean;
  selectedParticipantId: string | null;
  error?: string;
}

type Action =
  | { type: 'message'; message: RaceMessage }
  | { type: 'pause' }
  | { type: 'resume' }
  | { type: 'rate'; rate: number }
  | { type: 'select'; participantId: string }
  | { type: 'disconnect' };

const initialState: RaceSessionState = {
  session: null,
  frame: null,
  events: [],
  comparison: null,
  battles: [],
  report: null,
  supportState: 'ready',
  playback: 'preparing',
  rate: 20,
  stale: false,
  selectedParticipantId: null,
};

function onMessage(state: RaceSessionState, message: RaceMessage): RaceSessionState {
  switch (message.type) {
    case 'session':
      return {
        ...state,
        session: message.session,
        supportState: message.session.supportState,
        selectedParticipantId: message.session.selectedParticipantId ?? state.selectedParticipantId,
        playback: 'streaming',
        stale: false,
      };
    case 'frame': {
      // Late frames may be skipped, but newer state never appears behind older state.
      if (state.frame && message.frame.sequence < state.frame.sequence) return state;
      const complete = message.frame.baseline.finished && message.frame.alternative.finished;
      return {
        ...state,
        frame: message.frame,
        stale: false,
        playback: complete ? 'complete' : state.playback === 'paused' ? 'paused' : 'streaming',
      };
    }
    case 'events':
      return { ...state, events: message.events };
    case 'comparison':
      return { ...state, comparison: message.comparison };
    case 'battles':
      return { ...state, battles: message.battles };
    case 'report':
      return { ...state, report: message.report, playback: 'complete' };
    case 'support':
      return { ...state, supportState: message.state, supportReason: message.reason };
    case 'error':
      return { ...state, supportState: 'failed', error: message.message };
  }
}

function reducer(state: RaceSessionState, action: Action): RaceSessionState {
  switch (action.type) {
    case 'message':
      return onMessage(state, action.message);
    case 'pause':
      return { ...state, playback: 'paused' };
    case 'resume':
      return { ...state, playback: 'streaming' };
    case 'rate':
      return { ...state, rate: action.rate };
    case 'select':
      return { ...state, selectedParticipantId: action.participantId };
    case 'disconnect':
      // Retain the last confirmed frame and mark it stale until continuity returns.
      return { ...state, playback: 'disconnected', stale: true };
  }
}

export { reducer as raceSessionReducer, initialState as raceSessionInitialState };

export function useRaceSession(source: RaceSource, request: SessionRequest) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const sourceRef = useRef(source);
  const key = `${request.season}:${request.event}:${request.scenarioId}`;

  // A new source replaces the running one, so a late-loading report restarts the race.
  useEffect(() => {
    sourceRef.current = source;
    const unsubscribe = source.subscribe((message) => dispatch({ type: 'message', message }));
    source.start(request);
    return () => {
      unsubscribe();
      source.stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, source]);

  const controls = useMemo(
    () => ({
      pause: () => {
        sourceRef.current.pause();
        dispatch({ type: 'pause' });
      },
      resume: () => {
        sourceRef.current.resume();
        dispatch({ type: 'resume' });
      },
      seek: (raceTimeS: number) => sourceRef.current.seek(raceTimeS),
      setRate: (rate: number) => {
        sourceRef.current.setRate(rate);
        dispatch({ type: 'rate', rate });
      },
      select: (participantId: string) => {
        sourceRef.current.select(participantId);
        dispatch({ type: 'select', participantId });
      },
      /** Drives the degraded layout states from the fixture, so all nine are reachable. */
      injectSupport: (state: SupportState, reason?: string) => {
        if (state === 'ready') sourceRef.current.resume();
        else sourceRef.current.pause();
        dispatch({ type: 'message', message: { type: 'support', state, reason } });
      },
      injectDisconnect: () => {
        sourceRef.current.pause();
        dispatch({ type: 'disconnect' });
      },
    }),
    [],
  );

  return { state, controls };
}
