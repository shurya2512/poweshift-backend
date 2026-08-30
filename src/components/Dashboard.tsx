'use client';

import React, { useState } from 'react';
import { useSimulation } from '../lib/useSimulation';
import { TrackMap } from './TrackMap';
import { BatteryMeter } from './BatteryMeter';
import { Play, Pause, Square, FastForward, Rewind, ArrowLeft, X, RotateCcw, Maximize2 } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { motion, AnimatePresence } from 'framer-motion';
import Link from 'next/link';

interface DashboardProps {
  year?: string;
  track?: string;
  driver?: string;
  policy?: string;
}

const EyebrowLabel = ({ children, className = '' }: { children: React.ReactNode; className?: string }) => (
  <p className={`text-[10px] font-medium uppercase tracking-widest text-white/35 ${className}`}>{children}</p>
);

import { useRouter } from 'next/navigation';
import { MapPin, User, Cpu, Check } from 'lucide-react';
import { LimelightNav } from './ui/limelight-nav';
import { CONFIG_ITEMS } from './ui/setup-panel';
import { SubtleGridBackground } from './ui/the-infinite-grid';

export function Dashboard({ 
  year = '2026', 
  track = 'Monaco Grand Prix', 
  driver = 'VER', 
  policy = 'learned' 
}: DashboardProps) {
  const router = useRouter();
  const { state, connectAndStart, pause, resume, stop, setSpeed, seek } = useSimulation();

  const [expandedChart, setExpandedChart] = useState<'speed' | 'soc' | null>(null);
  const [expandedTrack, setExpandedTrack] = useState<'reference' | 'policy' | null>(null);
  const [activeConfigId, setActiveConfigId] = useState<string | null>(null);

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

  const handleConfigSelect = (id: string, value: string) => {
    setActiveConfigId(null);
    const newConfig = { track, driver, policy, [id]: value };
    const params = new URLSearchParams({
      track: newConfig.track,
      driver: newConfig.driver,
      policy: newConfig.policy,
      year: year
    });
    router.push(`/race?${params.toString()}`);
  };

  React.useEffect(() => {
    // Automatically start or restart the simulation whenever the configuration changes
    connectAndStart(Number(year), track, driver, policy);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year, track, driver, policy]);

  const currentRef = state.currentFrame?.reference;
  const currentPol = state.currentFrame?.policy;

  // Theme colors
  const teamColor = "#3b82f6"; // Blue-500
  const policyColor = "#ef4444"; // Red-500

  const activeConfigItem = CONFIG_ITEMS.find(c => c.id === activeConfigId) ?? null;

  return (
    <div className="flex-1 w-full bg-transparent text-white p-6 lg:p-10 font-sans relative z-10">
      {/* Computing Overlay */}
      {state.status === 'computing' && (
        <div className="absolute inset-0 z-50 flex flex-col items-center justify-center bg-black/60 backdrop-blur-md">
          <div className="animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-blue-500 mb-6 shadow-[0_0_20px_rgba(59,130,246,0.5)]"></div>
          <h2 className="text-xl font-bold tracking-widest uppercase">Computing Optimal Strategy</h2>
          <p className="text-white/40 mt-3 text-sm">Running simulation, please wait (this takes a few seconds)</p>
        </div>
      )}

      {/* ── MODAL: Config Selection ────────────────────────────────────────── */}
      <AnimatePresence>
        {activeConfigId && activeConfigItem && (
          <>
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="fixed inset-0 z-[110] bg-black/50 backdrop-blur-sm"
              onClick={() => setActiveConfigId(null)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 16 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 16 }}
              transition={{ type: 'spring', stiffness: 400, damping: 32 }}
              className="fixed inset-0 z-[120] flex items-center justify-center p-6 pointer-events-none"
            >
              <div
                className="w-full max-w-sm bg-neutral-950/80 backdrop-blur-2xl border border-white/[0.12] rounded-3xl overflow-hidden shadow-[0_24px_60px_rgba(0,0,0,0.9)] pointer-events-auto relative"
                onClick={e => e.stopPropagation()}
              >
                <div className="flex items-center justify-between px-7 py-5 border-b border-white/[0.07]">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-xl bg-white/[0.06] border border-white/[0.08] flex items-center justify-center">
                      <activeConfigItem.icon size={13} className={activeConfigItem.accentColor} />
                    </div>
                    <div>
                      <EyebrowLabel className="mb-0.5">Select</EyebrowLabel>
                      <p className="text-sm font-semibold text-white">{activeConfigItem.label}</p>
                    </div>
                  </div>
                  <button
                    onClick={() => setActiveConfigId(null)}
                    className="p-2 rounded-full bg-white/[0.07] hover:bg-white/[0.14] border border-white/[0.08] transition-colors text-white/40 hover:text-white"
                  >
                    <X size={12} />
                  </button>
                </div>
                <div className="overflow-y-auto max-h-[320px] pb-10">
                  {activeConfigItem.options.map((opt) => {
                    const currentVal = activeConfigId === 'track' ? track : activeConfigId === 'driver' ? driver : policy;
                    const isSelected = currentVal === opt.value;
                    return (
                      <div
                        key={opt.value}
                        onClick={() => handleConfigSelect(activeConfigId, opt.value)}
                        className={`flex items-center justify-between px-7 py-4 cursor-pointer transition-colors ${isSelected ? 'bg-white/[0.07]' : 'hover:bg-white/[0.03]'}`}
                      >
                        <div>
                          <p className={`text-sm font-semibold ${isSelected ? 'text-white' : 'text-white/55'}`}>
                            {opt.label}
                          </p>
                          {opt.sublabel && <p className="text-xs text-white/25 mt-0.5">{opt.sublabel}</p>}
                        </div>
                        <div className="flex items-center gap-2.5 flex-shrink-0 ml-3">
                          {opt.badge && (
                            <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full border tracking-wider ${isSelected ? 'border-white/25 text-white/60 bg-white/[0.08]' : 'border-white/8 text-white/20'}`}>
                              {opt.badge}
                            </span>
                          )}
                          {isSelected && (
                            <div className="w-5 h-5 rounded-full bg-white flex items-center justify-center">
                              <Check size={10} className="text-black" strokeWidth={3} />
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      <div className="max-w-7xl mx-auto space-y-6">
        
        {/* Floating Top Nav */}
        <div className="relative flex items-center justify-center w-full">
          <Link href="/setup" className="absolute left-0 flex items-center gap-2 text-sm text-white/50 hover:text-white transition-colors bg-white/[0.03] hover:bg-white/[0.08] border border-white/[0.05] h-10 px-4 rounded-[14px] font-medium shadow-lg backdrop-blur-md">
            <ArrowLeft size={16} /> Setup
          </Link>
          
          <LimelightNav 
            className="shadow-lg backdrop-blur-md"
            items={[
              { id: 'track', icon: <MapPin />, label: 'Track', onClick: () => setActiveConfigId('track') },
              { id: 'driver', icon: <User />, label: 'Driver', onClick: () => setActiveConfigId('driver') },
              { id: 'policy', icon: <Cpu />, label: 'Policy', onClick: () => setActiveConfigId('policy') },
            ]}
          />
        </div>

        {/* Scrub Bar was here */}
        
        {/* Status bar */}
        {state.status === 'error' && (
          <div className="bg-red-950/50 backdrop-blur-xl border border-red-500/30 rounded-3xl p-6 text-center shadow-[0_12px_40px_rgba(239,68,68,0.2)]">
            <span className="text-red-400 font-bold uppercase tracking-wider text-sm">Connection Error: </span>
            <span className="text-red-300 text-sm ml-2">{state.error || "Could not connect to WebSocket at ws://localhost:8000/api/stream/simulation"}</span>
            <div className="text-xs text-red-400/70 mt-3 font-medium">Make sure your backend is running on port 8000.</div>
          </div>
        )}

        {state.initData && state.status !== 'error' && (
          <div className="bg-neutral-950/60 backdrop-blur-2xl border border-white/[0.08] rounded-3xl p-6 px-8 flex flex-col md:flex-row justify-between items-center gap-6 shadow-[0_12px_40px_rgba(0,0,0,0.5)]">
            <div className="flex flex-col items-center md:items-start w-full">
              <EyebrowLabel className="mb-2">Headline Result</EyebrowLabel>
              {!isFinished ? (
                <div className="flex items-center gap-4 py-2">
                  <div className="animate-pulse w-3 h-3 bg-blue-500 rounded-full"></div>
                  <span className="text-xl font-bold text-white/60 tracking-tight">Calculating final lap margin...</span>
                </div>
              ) : (() => {
                const margin = state.initData.headline.time_gained_vs_reference_s;
                const tolerance = state.initData.headline.reference_frame_width * state.initData.duration_s;
                if (Math.abs(margin) < tolerance) {
                  return <span className="text-xl font-bold text-yellow-400">Within modelling error</span>;
                }
                return (
                  <div className="flex items-baseline gap-3 w-full justify-between md:justify-start">
                    <span className={`text-4xl font-black tracking-tighter ${margin > 0 ? 'text-green-400 drop-shadow-[0_0_12px_rgba(74,222,128,0.4)]' : 'text-red-400 drop-shadow-[0_0_12px_rgba(248,113,113,0.4)]'}`}>
                      {margin > 0 ? '-' : '+'}{Math.abs(margin).toFixed(3)}s
                    </span>
                    <span className="text-white/40 text-sm font-semibold uppercase tracking-widest">vs Team Strategy</span>
                  </div>
                );
              })()}
            </div>
            
            {isFinished && (
              <div className="flex gap-8 text-right bg-white/[0.03] border border-white/[0.05] p-4 rounded-2xl shrink-0">
                <div className="flex flex-col">
                  <EyebrowLabel className="mb-1">Model Error</EyebrowLabel>
                  <span className="text-white font-semibold text-sm">{state.initData.headline.grip_gap_s > 0 ? '+' : ''}{state.initData.headline.grip_gap_s.toFixed(3)}s</span>
                </div>
                <div className="w-px bg-white/10" />
                <div className="flex flex-col">
                  <EyebrowLabel className="mb-1">vs Stopwatch</EyebrowLabel>
                  <span className="text-white font-semibold text-sm">{state.initData.headline.time_gained_s > 0 ? '-' : '+'}{Math.abs(state.initData.headline.time_gained_s).toFixed(3)}s</span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Top Section: Maps & Meters */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Reference (Team) */}
          <div className="bg-neutral-950/60 backdrop-blur-2xl border border-white/[0.08] rounded-3xl p-6 shadow-[0_12px_40px_rgba(0,0,0,0.5)]">
            <div className="flex items-center justify-between mb-4">
              <EyebrowLabel className="text-blue-400">Team Strategy (Reference)</EyebrowLabel>
              <button
                onClick={() => setExpandedTrack('reference')}
                aria-label="Expand team strategy"
                className="p-2 rounded-full bg-white/[0.05] hover:bg-white/[0.14] border border-white/[0.08] text-white/40 hover:text-white transition-colors"
              >
                <Maximize2 size={13} />
              </button>
            </div>
            <TrackMap geometry={state.initData?.track || null} carState={currentRef || null} color={teamColor} />
            <div className="mt-4">
              <BatteryMeter 
                label="Team Battery" 
                socMj={currentRef?.soc ?? 4.0} 
                p_kw={currentRef?.p_kw ?? 0} 
                color={teamColor} 
                ghostSocMj={currentPol?.soc}
                isFinished={currentRef?.finished}
              />
            </div>
          </div>

          {/* Policy (Learned) */}
          <div className="bg-neutral-950/60 backdrop-blur-2xl border border-white/[0.08] rounded-3xl p-6 shadow-[0_12px_40px_rgba(0,0,0,0.5)]">
            <div className="flex items-center justify-between mb-4">
              <EyebrowLabel className="text-red-400">AI Strategy ({policy})</EyebrowLabel>
              <button
                onClick={() => setExpandedTrack('policy')}
                aria-label="Expand AI strategy"
                className="p-2 rounded-full bg-white/[0.05] hover:bg-white/[0.14] border border-white/[0.08] text-white/40 hover:text-white transition-colors"
              >
                <Maximize2 size={13} />
              </button>
            </div>
            <TrackMap geometry={state.initData?.track || null} carState={currentPol || null} color={policyColor} />
            <div className="mt-4">
              <BatteryMeter 
                label="AI Battery" 
                socMj={currentPol?.soc ?? 4.0} 
                p_kw={currentPol?.p_kw ?? 0} 
                color={policyColor} 
                ghostSocMj={currentRef?.soc}
                isFinished={currentPol?.finished}
              />
            </div>
          </div>
        </div>

        {/* Playback Controls & Timeline (Moved Below Maps) */}
        <div className="bg-neutral-950/60 backdrop-blur-2xl border border-white/[0.08] rounded-3xl p-5 px-6 flex flex-col md:flex-row items-center gap-6 shadow-[0_12px_40px_rgba(0,0,0,0.5)]">
          
          {/* Play/Pause Buttons */}
          <div className="flex items-center gap-3 shrink-0">
            <button 
              onClick={handlePlayPause} 
              className="bg-white text-black rounded-xl hover:bg-neutral-200 font-bold px-6 py-3 flex items-center gap-2 shadow-lg hover:scale-105 active:scale-95 transition-all text-sm"
            >
              {isPlaying ? <Pause size={18} fill="currentColor"/> : <Play size={18} fill="currentColor"/>}
              {isPlaying ? 'PAUSE' : (isFinished || isPaused) ? 'RESUME' : 'START SIMULATION'}
            </button>
            <button 
              onClick={handleStop} 
              className="p-3 bg-white/[0.05] border border-white/[0.08] rounded-xl hover:bg-red-500/20 hover:text-red-400 hover:border-red-500/30 transition-colors"
            >
              <RotateCcw size={18} />
            </button>
          </div>

          {/* Scrub Bar */}
          <div className={`flex items-center gap-5 flex-1 w-full bg-white/[0.03] border border-white/[0.05] p-3 rounded-2xl px-6 ${(!state.initData || state.status === 'idle' || state.status === 'computing') ? 'opacity-50 pointer-events-none' : ''}`}>
            <span className="text-xs font-semibold text-white/50 w-12 text-right">
              {state.currentFrame?.t.toFixed(1) || "0.0"}s
            </span>
            <input 
              type="range" 
              min="0" 
              max={state.initData?.duration_s || 100} 
              step="0.25"
              value={state.currentFrame?.t || 0}
              onChange={(e) => seek(Number(e.target.value))}
              className="w-full h-1.5 bg-white/10 rounded-full appearance-none cursor-pointer accent-white hover:accent-blue-400 transition-colors"
            />
            <span className="text-xs font-semibold text-white/50 w-12">
              {state.initData?.duration_s.toFixed(1) || "0.0"}s
            </span>
          </div>

            {/* Speed Selector */}
            <div className="relative shrink-0">
              <select 
                className="bg-white/[0.05] border border-white/[0.08] rounded-xl px-4 py-3 text-sm font-medium text-white cursor-pointer hover:bg-white/[0.08] transition-colors focus:outline-none" 
                value={state.speed} 
                onChange={e => setSpeed(Number(e.target.value))}
              >
                <option value="0.25" className="bg-neutral-900 text-white">0.25x Speed</option>
                <option value="0.5" className="bg-neutral-900 text-white">0.5x Speed</option>
                <option value="1" className="bg-neutral-900 text-white">1.0x Speed</option>
                <option value="2" className="bg-neutral-900 text-white">2.0x Speed</option>
                <option value="4" className="bg-neutral-900 text-white">4.0x Speed</option>
              </select>
            </div>
          </div>
        {/* Gap Strip */}
        <div className="bg-neutral-950/60 backdrop-blur-2xl border border-white/[0.08] rounded-3xl p-5 px-8 flex justify-between items-center shadow-[0_12px_40px_rgba(0,0,0,0.5)]">
          <EyebrowLabel>Live Track Gap</EyebrowLabel>
          <span className={`text-xl font-bold tracking-tight ${state.currentFrame?.gap_s && state.currentFrame.gap_s < 0 ? 'text-green-400' : 'text-red-400'}`}>
            {state.currentFrame ? (state.currentFrame.gap_s > 0 ? '+' : '') + state.currentFrame.gap_s.toFixed(2) + 's' : '--'}
          </span>
        </div>

        {/* Bottom Section: Charts */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div 
            onClick={() => setExpandedChart('speed')}
            className="bg-neutral-950/60 backdrop-blur-2xl border border-white/[0.08] rounded-3xl p-6 h-[320px] flex flex-col shadow-[0_12px_40px_rgba(0,0,0,0.5)] cursor-pointer hover:bg-neutral-900/80 transition-colors group relative overflow-hidden"
          >
            <div className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity z-20 backdrop-blur-sm">
              <span className="text-white font-bold tracking-widest uppercase text-sm border border-white/20 bg-black/60 px-6 py-2 rounded-full">Expand Chart</span>
            </div>
            <EyebrowLabel className="mb-6">Speed vs Distance</EyebrowLabel>
            <div className="flex-1 min-h-0 pointer-events-none">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart>
                  <XAxis type="number" dataKey="d" domain={[0, state.initData?.track.lap_length_m || 'auto']} hide />
                  <YAxis domain={['auto', 'auto']} stroke="#ffffff20" tick={{fill: '#ffffff60', fontSize: 10}} />
                  <Line data={state.history.map(h => ({ d: h.reference.d, v: h.reference.v }))} type="monotone" dataKey="v" stroke={teamColor} dot={false} isAnimationActive={false} strokeWidth={2} />
                  <Line data={state.history.map(h => ({ d: h.policy.d, v: h.policy.v }))} type="monotone" dataKey="v" stroke={policyColor} dot={false} isAnimationActive={false} strokeWidth={2} />
                  {currentRef && <ReferenceLine x={currentRef.d} stroke={teamColor} strokeDasharray="3 3" />}
                  {currentPol && <ReferenceLine x={currentPol.d} stroke={policyColor} strokeDasharray="3 3" />}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div 
            onClick={() => setExpandedChart('soc')}
            className="bg-neutral-950/60 backdrop-blur-2xl border border-white/[0.08] rounded-3xl p-6 h-[320px] flex flex-col shadow-[0_12px_40px_rgba(0,0,0,0.5)] cursor-pointer hover:bg-neutral-900/80 transition-colors group relative overflow-hidden"
          >
            <div className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity z-20 backdrop-blur-sm">
              <span className="text-white font-bold tracking-widest uppercase text-sm border border-white/20 bg-black/60 px-6 py-2 rounded-full">Expand Chart</span>
            </div>
            <EyebrowLabel className="mb-6">Battery SoC vs Distance</EyebrowLabel>
            <div className="flex-1 min-h-0 pointer-events-none">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart>
                  <XAxis type="number" dataKey="d" domain={[0, state.initData?.track.lap_length_m || 'auto']} hide />
                  <YAxis domain={[0, 4]} stroke="#ffffff20" tick={{fill: '#ffffff60', fontSize: 10}} />
                  <Line data={state.history.map(h => ({ d: h.reference.d, soc: h.reference.soc }))} type="stepAfter" dataKey="soc" stroke={teamColor} dot={false} isAnimationActive={false} strokeWidth={2} />
                  <Line data={state.history.map(h => ({ d: h.policy.d, soc: h.policy.soc }))} type="stepAfter" dataKey="soc" stroke={policyColor} dot={false} isAnimationActive={false} strokeWidth={2} />
                  {currentRef && <ReferenceLine x={currentRef.d} stroke={teamColor} strokeDasharray="3 3" />}
                  {currentPol && <ReferenceLine x={currentPol.d} stroke={policyColor} strokeDasharray="3 3" />}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Full-Screen Chart Modals */}
        <AnimatePresence>
          {expandedChart && (
            <motion.div 
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ type: "spring", damping: 25, stiffness: 300 }}
              className="fixed inset-0 z-[100] flex items-center justify-center p-8 bg-black/80 backdrop-blur-3xl"
            >
              <SubtleGridBackground id="chart-grid" />
              <div className="relative z-10 w-full h-full max-w-6xl max-h-[800px] bg-neutral-950/80 border border-white/10 rounded-3xl p-10 flex flex-col shadow-[0_40px_100px_rgba(0,0,0,0.8)]">
                <button 
                  onClick={() => setExpandedChart(null)}
                  className="absolute top-8 right-8 p-3 bg-white/10 hover:bg-white/20 text-white rounded-full transition-colors"
                >
                  <X size={24} />
                </button>
                <h2 className="text-3xl font-black tracking-tight mb-8">
                  {expandedChart === 'speed' ? 'Speed vs Distance' : 'Battery SoC vs Distance'}
                </h2>
                
                <div className="flex-1 w-full min-h-0">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart>
                      <XAxis type="number" dataKey="d" domain={[0, state.initData?.track.lap_length_m || 'auto']} stroke="#ffffff40" tick={{fill: '#ffffff60', fontSize: 14}} />
                      <YAxis domain={expandedChart === 'speed' ? ['auto', 'auto'] : [0, 4]} stroke="#ffffff40" tick={{fill: '#ffffff60', fontSize: 14}} />
                      <Tooltip contentStyle={{backgroundColor: '#0a0a0a', borderColor: '#ffffff20', borderRadius: '12px'}} itemStyle={{color: '#fff', fontSize: '14px'}} />
                      <Line data={state.history.map(h => ({ d: h.reference.d, val: expandedChart === 'speed' ? h.reference.v : h.reference.soc }))} type={expandedChart === 'speed' ? "monotone" : "stepAfter"} dataKey="val" stroke={teamColor} dot={false} isAnimationActive={false} strokeWidth={4} name={expandedChart === 'speed' ? "Team Speed" : "Team SoC"} />
                      <Line data={state.history.map(h => ({ d: h.policy.d, val: expandedChart === 'speed' ? h.policy.v : h.policy.soc }))} type={expandedChart === 'speed' ? "monotone" : "stepAfter"} dataKey="val" stroke={policyColor} dot={false} isAnimationActive={false} strokeWidth={4} name={expandedChart === 'speed' ? "AI Speed" : "AI SoC"} />
                      {currentRef && <ReferenceLine x={currentRef.d} stroke={teamColor} strokeDasharray="6 6" strokeWidth={2} />}
                      {currentPol && <ReferenceLine x={currentPol.d} stroke={policyColor} strokeDasharray="6 6" strokeWidth={2} />}
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Full-Screen Strategy Modal */}
        <AnimatePresence>
          {expandedTrack && (() => {
            const isRef = expandedTrack === 'reference';
            const car = isRef ? currentRef : currentPol;
            const ghost = isRef ? currentPol : currentRef;
            const color = isRef ? teamColor : policyColor;
            return (
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={{ type: "spring", damping: 25, stiffness: 300 }}
                className="fixed inset-0 z-[100] flex items-center justify-center p-8 bg-black/80 backdrop-blur-3xl"
              >
                <SubtleGridBackground id="strategy-grid" />
                <div className="relative z-10 w-full h-full max-w-6xl max-h-[800px] bg-neutral-950/80 border border-white/10 rounded-3xl p-10 flex flex-col shadow-[0_40px_100px_rgba(0,0,0,0.8)]">
                  <button
                    onClick={() => setExpandedTrack(null)}
                    className="absolute top-8 right-8 p-3 bg-white/10 hover:bg-white/20 text-white rounded-full transition-colors"
                  >
                    <X size={24} />
                  </button>
                  <h2 className={`text-3xl font-black tracking-tight mb-8 ${isRef ? 'text-blue-400' : 'text-red-400'}`}>
                    {isRef ? 'Team Strategy (Reference)' : `AI Strategy (${policy})`}
                  </h2>

                  <div className="flex-1 w-full min-h-0 overflow-y-auto flex items-center justify-center">
                    <div className="w-full max-w-3xl">
                      <TrackMap geometry={state.initData?.track || null} carState={car || null} color={color} />
                      <BatteryMeter
                        label={isRef ? 'Team Battery' : 'AI Battery'}
                        socMj={car?.soc ?? 4.0}
                        p_kw={car?.p_kw ?? 0}
                        color={color}
                        ghostSocMj={ghost?.soc}
                        isFinished={car?.finished}
                      />
                    </div>
                  </div>
                </div>
              </motion.div>
            );
          })()}
        </AnimatePresence>

        {/* Disclaimer Footer */}
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between px-4 gap-4 mt-8 pb-8">
          <p className="text-[10px] text-white/30 font-medium tracking-wide uppercase leading-relaxed max-w-lg">
            * Only the four held-out circuits are selectable because they contributed zero rows to the AI&apos;s training data. This proves the AI can generalize to tracks it has never seen.
          </p>
          <p className="text-[10px] text-white/30 font-medium tracking-wide uppercase leading-relaxed max-w-lg text-left md:text-right">
            * Driver selection changes the lap being replayed, not the car model (all cars use the same aerodynamics/mass formula).
          </p>
        </div>

      </div>
    </div>
  );
}
