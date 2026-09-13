export interface TrackGeometry {
  name: string;
  x: number[];
  y: number[];
  lap_length_m: number;
}

export interface LapTimeInfo {
  reference: number;
  policy: number;
  baseline: number;
}

export interface HeadlineStats {
  time_gained_vs_reference_s: number;
  grip_gap_s: number;
  reference_frame_width: number;
  time_gained_s: number;
}

export interface InitMessage {
  type: 'init';
  track: TrackGeometry;
  driver: string;
  team: string;
  policy: string;
  held_out: boolean;
  lap_time_s: LapTimeInfo;
  headline: HeadlineStats;
  duration_s: number;
  rate_hz: number;
}

export interface CarState {
  d: number;
  x: number;
  y: number;
  v: number;
  p_kw: number;
  soc: number;
  finished: boolean;
}

export interface FrameMessage {
  type: 'frame';
  t: number;
  progress: number;
  reference: CarState;
  policy: CarState;
  gap_s: number;
  live_decision_kw: number;
}

export interface StatusMessage {
  type: 'status';
  phase: string;
}

export interface EndMessage {
  type: 'end';
  final_gap_s: number;
}

export interface ErrorMessage {
  type: 'error';
  code: string;
  message: string;
}

export type WebSocketMessage =
  | InitMessage
  | FrameMessage
  | StatusMessage
  | EndMessage
  | ErrorMessage;
