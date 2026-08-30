'use client';

import React, { useState } from 'react';
import { useSimulation } from '../lib/useSimulation';
import { TrackMap } from './TrackMap';
import { BatteryMeter } from './BatteryMeter';
import { Play, Pause, Square, FastForward, Rewind } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';

import { ArrowLeft } from 'lucide-react';
import Link from 'next/link';

interface DashboardProps {
  year?: string;
  track?: string;
  driver?: string;
  policy?: string;
}

export function Dashboard({ 
  year = '2026', 
  track = 'Monaco Grand Prix', 
  driver = 'VER', 
  policy = 'learned' 
}: DashboardProps) {
  const { state, connectAndStart, pause, resume, stop, setSpeed, seek } = useSimulation();

  const isPlaying = state.status === 'playing';
  const isPaused = state.status === 'paused';
  const isFinished = state.status === 'finished';

  const handlePlayPause = () => {
    if (state.status === 'idle' || state.status === 'error' || isFinished) {
      connectAndStart(Number(year), track, driver, policy);
    } else if (isPlaying) {
      pause();
    } else if (isPaused) {
      resume();
    }
  };

  const handleStop = () => stop();

  const currentRef = state.currentFrame?.reference;
  const currentPol = state.currentFrame?.policy;

  return (
    <div className="flex-1 w-full bg-transparent text-white p-4 font-sans relative z-10">
      {/* Computing Overlay */}
      {state.status === 'computing' && (
        <div className="absolute inset-0 z-50 flex flex-col items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-white mb-4"></div>
          <h2 className="text-xl font-bold tracking-widest uppercase">Computing Optimal Strategy...</h2>
          <p className="text-neutral-400 mt-2 font-mono text-sm">Running simulation, please wait (this takes a few seconds)</p>
        </div>
      )}

      <div className="max-w-7xl mx-auto space-y-4">
        
        {/* Header / Controls */}
        <div className="flex flex-col md:flex-row flex-wrap items-start md:items-center justify-between bg-neutral-900 p-4 rounded border border-neutral-800 gap-4">
          <div className="flex flex-col md:flex-row md:items-center gap-4 w-full md:w-auto">
            <h1 className="text-xl font-bold italic tracking-wider md:pr-4 md:border-r border-neutral-700">TRACK-SHIFT</h1>
            <div className="flex flex-wrap items-center gap-4">
              <Link href="/setup" className="flex items-center gap-2 text-sm text-neutral-400 hover:text-white transition-colors bg-neutral-800 px-3 py-1.5 rounded">
                <ArrowLeft size={16} /> Setup
              </Link>
              <div className="flex gap-3 text-sm font-mono text-neutral-300 bg-neutral-950 px-3 py-1.5 rounded border border-neutral-800">
                <span>{track}</span>
                <span className="text-neutral-600">|</span>
                <span className="text-blue-400">{driver}</span>
                <span className="text-neutral-600">|</span>
                <span className="text-green-400 uppercase">{policy}</span>
              </div>
            </div>
          </div>
          
          <div className="flex items-center gap-4 w-full md:w-auto mt-4 md:mt-0">
            {/* Speed Selector */}
            <select 
              className="bg-neutral-800 border border-neutral-700 rounded p-1 text-xs" 
              value={state.speed} 
              onChange={e => setSpeed(Number(e.target.value))}
              disabled={state.status === 'idle' || state.status === 'computing'}
            >
              <option value="0.25">0.25x</option>
              <option value="0.5">0.5x</option>
              <option value="1">1.0x</option>
              <option value="2">2.0x</option>
              <option value="4">4.0x</option>
            </select>

            {/* Playback Controls */}
            <button onClick={handlePlayPause} className="p-2 bg-neutral-100 text-black rounded hover:bg-neutral-300 font-bold px-4 flex items-center gap-2">
              {isPlaying ? <Pause size={16} fill="currentColor"/> : <Play size={16} fill="currentColor"/>}
              {isPlaying ? 'PAUSE' : (isFinished || isPaused) ? 'RESUME' : 'PLAY'}
            </button>
            <button onClick={handleStop} className="p-2 bg-neutral-800 rounded hover:bg-neutral-700">
              <Square size={16} fill="currentColor"/>
            </button>
          </div>
        </div>

        {/* Scrub Bar */}
        {(state.initData && state.status !== 'idle' && state.status !== 'computing') && (
          <div className="flex items-center gap-4 bg-neutral-900 border border-neutral-800 p-2 rounded px-4">
            <span className="text-xs font-mono text-neutral-400 w-12 text-right">
              {state.currentFrame?.t.toFixed(1) || "0.0"}s
            </span>
            <input 
              type="range" 
              min="0" 
              max={state.initData.duration_s} 
              step="0.25"
              value={state.currentFrame?.t || 0}
              onChange={(e) => {
                const t = Number(e.target.value);
                seek(t);
              }}
              className="w-full accent-blue-500"
            />
            <span className="text-xs font-mono text-neutral-400 w-12">
              {state.initData.duration_s.toFixed(1)}s
            </span>
          </div>
        )}

        <div className="text-[10px] text-neutral-500 font-mono flex flex-col md:flex-row items-start md:items-center justify-between px-2 gap-2">
          <span>* Only the four held-out circuits are selectable because they contributed zero rows to the AI&apos;s training data. This proves the AI can generalize to tracks it has never seen.</span>
          <span>* Driver selection changes the <i>lap</i> being replayed, not the <i>car model</i> (all cars use the same aerodynamics/mass formula).</span>
        </div>

        {/* Status bar */}
        {state.status === 'error' && (
          <div className="bg-red-950 border border-red-800 rounded p-4 text-center">
            <span className="text-red-400 font-bold uppercase tracking-wider">Connection Error: </span>
            <span className="text-red-300">{state.error || "Could not connect to WebSocket at ws://localhost:8000/api/stream/simulation"}</span>
            <div className="text-xs text-red-500 mt-2">Make sure your backend is running and has the WebSocket endpoint.</div>
          </div>
        )}

        {state.initData && state.status !== 'error' && (
          <div className="bg-neutral-900 border border-neutral-800 rounded p-4 flex flex-col md:flex-row justify-between items-center gap-4">
            <div className="flex flex-col items-center md:items-start">
              <span className="text-neutral-500 text-xs uppercase tracking-widest font-bold mb-1">Headline Result</span>
              {(() => {
                const margin = state.initData.headline.time_gained_vs_reference_s;
                const tolerance = state.initData.headline.reference_frame_width * state.initData.duration_s;
                if (Math.abs(margin) < tolerance) {
                  return <span className="text-xl font-mono font-bold text-yellow-400">Within modelling error</span>;
                }
                return (
                  <div className="flex items-baseline gap-2">
                    <span className={`text-2xl font-mono font-bold ${margin > 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {margin > 0 ? '-' : '+'}{Math.abs(margin).toFixed(3)}s
                    </span>
                    <span className="text-neutral-400 text-sm uppercase tracking-widest">vs Team Strategy</span>
                  </div>
                );
              })()}
            </div>
            
            <div className="flex gap-6 text-right">
              <div className="flex flex-col">
                <span className="text-neutral-500 text-[10px] uppercase tracking-widest font-bold">Model Error (Grip Gap)</span>
                <span className="text-neutral-300 font-mono text-sm">{state.initData.headline.grip_gap_s > 0 ? '+' : ''}{state.initData.headline.grip_gap_s.toFixed(3)}s</span>
              </div>
              <div className="flex flex-col">
                <span className="text-neutral-500 text-[10px] uppercase tracking-widest font-bold">vs Real Stopwatch</span>
                <span className="text-neutral-300 font-mono text-sm">{state.initData.headline.time_gained_s > 0 ? '-' : '+'}{Math.abs(state.initData.headline.time_gained_s).toFixed(3)}s</span>
              </div>
            </div>
          </div>
        )}

        {/* Top Section: Maps & Meters */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Reference (Team) */}
          <div className="bg-neutral-950 border border-neutral-800 rounded p-4">
            <h2 className="text-sm font-bold uppercase tracking-wider text-neutral-400 mb-2">Team (Reference Strategy)</h2>
            <TrackMap geometry={state.initData?.track || null} carState={currentRef || null} color="#3b82f6" />
            <BatteryMeter 
              label="Battery (Team)" 
              socMj={currentRef?.soc ?? 4.0} 
              p_kw={currentRef?.p_kw ?? 0} 
              color="#3b82f6" 
              ghostSocMj={currentPol?.soc}
              isFinished={currentRef?.finished}
            />
          </div>

          {/* Policy (Learned) */}
          <div className="bg-neutral-950 border border-neutral-800 rounded p-4">
            <h2 className="text-sm font-bold uppercase tracking-wider text-neutral-400 mb-2">Policy (Learned)</h2>
            <TrackMap geometry={state.initData?.track || null} carState={currentPol || null} color="#10b981" />
            <BatteryMeter 
              label="Battery (Policy)" 
              socMj={currentPol?.soc ?? 4.0} 
              p_kw={currentPol?.p_kw ?? 0} 
              color="#10b981" 
              ghostSocMj={currentRef?.soc}
              isFinished={currentPol?.finished}
            />
          </div>
        </div>

        {/* Gap Strip */}
        <div className="bg-neutral-900 border border-neutral-800 rounded p-3 flex justify-between items-center font-mono text-sm">
          <span className="text-neutral-500 uppercase tracking-widest text-xs">Live Gap</span>
          <span className={`font-bold ${state.currentFrame?.gap_s && state.currentFrame.gap_s < 0 ? 'text-green-400' : 'text-red-400'}`}>
            {state.currentFrame ? (state.currentFrame.gap_s > 0 ? '+' : '') + state.currentFrame.gap_s.toFixed(2) + 's' : '--'}
          </span>
        </div>

        {/* Bottom Section: Charts */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-neutral-900 border border-neutral-800 rounded p-4 h-[300px] flex flex-col">
            <h3 className="text-xs font-bold uppercase tracking-widest text-neutral-500 mb-4">Speed vs Distance</h3>
            <div className="flex-1 min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart>
                  <XAxis type="number" dataKey="d" domain={[0, state.initData?.track.lap_length_m || 'auto']} hide />
                  <YAxis domain={['auto', 'auto']} stroke="#555" tick={{fill: '#888', fontSize: 10}} />
                  <Tooltip contentStyle={{backgroundColor: '#111', borderColor: '#333'}} itemStyle={{color: '#fff'}} />
                  <Line data={state.history.map(h => ({ d: h.reference.d, v: h.reference.v }))} type="monotone" dataKey="v" stroke="#3b82f6" dot={false} isAnimationActive={false} strokeWidth={2} name="Team Speed" />
                  <Line data={state.history.map(h => ({ d: h.policy.d, v: h.policy.v }))} type="monotone" dataKey="v" stroke="#10b981" dot={false} isAnimationActive={false} strokeWidth={2} name="Policy Speed" />
                  {currentRef && <ReferenceLine x={currentRef.d} stroke="#3b82f6" strokeDasharray="3 3" />}
                  {currentPol && <ReferenceLine x={currentPol.d} stroke="#10b981" strokeDasharray="3 3" />}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="bg-neutral-900 border border-neutral-800 rounded p-4 h-[300px] flex flex-col">
            <h3 className="text-xs font-bold uppercase tracking-widest text-neutral-500 mb-4">Battery SoC vs Distance</h3>
            <div className="flex-1 min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart>
                  <XAxis type="number" dataKey="d" domain={[0, state.initData?.track.lap_length_m || 'auto']} hide />
                  <YAxis domain={[0, 4]} stroke="#555" tick={{fill: '#888', fontSize: 10}} />
                  <Tooltip contentStyle={{backgroundColor: '#111', borderColor: '#333'}} itemStyle={{color: '#fff'}} />
                  <Line data={state.history.map(h => ({ d: h.reference.d, soc: h.reference.soc }))} type="stepAfter" dataKey="soc" stroke="#3b82f6" dot={false} isAnimationActive={false} strokeWidth={2} name="Team SoC" />
                  <Line data={state.history.map(h => ({ d: h.policy.d, soc: h.policy.soc }))} type="stepAfter" dataKey="soc" stroke="#10b981" dot={false} isAnimationActive={false} strokeWidth={2} name="Policy SoC" />
                  {currentRef && <ReferenceLine x={currentRef.d} stroke="#3b82f6" strokeDasharray="3 3" />}
                  {currentPol && <ReferenceLine x={currentPol.d} stroke="#10b981" strokeDasharray="3 3" />}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
