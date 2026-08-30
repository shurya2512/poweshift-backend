import { useEffect, useReducer, useRef } from 'react';
import { FrameMessage, InitMessage, WebSocketMessage } from './types';

interface SimulationState {
  status: 'idle' | 'computing' | 'playing' | 'paused' | 'finished' | 'error';
  error?: string;
  initData: InitMessage | null;
  currentFrame: FrameMessage | null;
  history: FrameMessage[]; // Store history for charts and trails
  speed: number;
}

type Action =
  | { type: 'START' }
  | { type: 'COMPUTING' }
  | { type: 'INIT'; payload: InitMessage }
  | { type: 'FRAME'; payload: FrameMessage }
  | { type: 'PAUSE' }
  | { type: 'RESUME' }
  | { type: 'END'; final_gap_s: number }
  | { type: 'ERROR'; message: string }
  | { type: 'SET_SPEED'; speed: number };

const initialState: SimulationState = {
  status: 'idle',
  initData: null,
  currentFrame: null,
  history: [],
  speed: 1.0,
};

function simulationReducer(state: SimulationState, action: Action): SimulationState {
  switch (action.type) {
    case 'START':
      return { ...initialState, status: 'computing' };
    case 'COMPUTING':
      return { ...state, status: 'computing' };
    case 'INIT':
      return { ...state, status: 'playing', initData: action.payload, history: [] };
    case 'FRAME':
      return {
        ...state,
        currentFrame: action.payload,
        history: [...state.history, action.payload],
      };
    case 'PAUSE':
      return { ...state, status: 'paused' };
    case 'RESUME':
      return { ...state, status: 'playing' };
    case 'END':
      return { ...state, status: 'finished' };
    case 'ERROR':
      return { ...state, status: 'error', error: action.message };
    case 'SET_SPEED':
      return { ...state, speed: action.speed };
    default:
      return state;
  }
}

export function useSimulation() {
  const [state, dispatch] = useReducer(simulationReducer, initialState);
  const wsRef = useRef<WebSocket | null>(null);

  const connectAndStart = (year: number, track: string, driver: string, policy: string) => {
    dispatch({ type: 'START' });

    if (wsRef.current) {
      wsRef.current.close();
    }

    const ws = new WebSocket('ws://localhost:8000/api/stream/simulation');
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(
        JSON.stringify({
          type: 'start',
          year,
          track,
          driver,
          policy,
          rate_hz: 4,
          speed: state.speed,
        })
      );
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data) as WebSocketMessage;

      switch (data.type) {
        case 'status':
          if (data.phase === 'solving') {
            dispatch({ type: 'COMPUTING' });
          }
          break;
        case 'init':
          dispatch({ type: 'INIT', payload: data });
          break;
        case 'frame':
          dispatch({ type: 'FRAME', payload: data });
          break;
        case 'end':
          dispatch({ type: 'END', final_gap_s: data.final_gap_s });
          break;
        case 'error':
          dispatch({ type: 'ERROR', message: data.message });
          break;
      }
    };

    ws.onerror = (err) => {
      console.error('WebSocket error:', err);
      dispatch({ type: 'ERROR', message: 'WebSocket connection failed' });
    };

    ws.onclose = () => {
      console.log('WebSocket closed');
    };
  };

  const pause = () => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'pause' }));
      dispatch({ type: 'PAUSE' });
    }
  };

  const resume = () => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'resume' }));
      dispatch({ type: 'RESUME' });
    }
  };

  const setSpeed = (speed: number) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'speed', value: speed }));
    }
    dispatch({ type: 'SET_SPEED', speed });
  };

  const seek = (t: number) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'seek', t }));
      // We might want to clear history after seek, or backend will just send frames from t
    }
  };

  const stop = () => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'stop' }));
      wsRef.current.close();
      dispatch({ type: 'END', final_gap_s: 0 });
    }
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  return {
    state,
    connectAndStart,
    pause,
    resume,
    setSpeed,
    seek,
    stop,
  };
}
