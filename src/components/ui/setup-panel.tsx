"use client";

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Check, X, ChevronRight, MapPin, User, Cpu, Flag, Loader2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

// ── Types ────────────────────────────────────────────────────────────────────

interface SelectionOption {
  value: string;
  label: string;
  sublabel?: string;
  badge?: string;
}

interface ConfigItem {
  id: string;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  accentColor: string;
  options: SelectionOption[];
  note?: string;
}

interface SetupPanelProps {
  onStart: (track: string, driver: string, policy: string) => void;
}

// ── Static Data ──────────────────────────────────────────────────────────────

export const CONFIG_ITEMS: ConfigItem[] = [
  {
    id: 'track',
    label: 'Circuit',
    icon: MapPin,
    accentColor: 'text-blue-400',
    note: 'Only held-out circuits are selectable — zero rows in training data.',
    options: [
      { value: 'Monaco Grand Prix',   label: 'Monaco',  sublabel: 'Circuit de Monaco',            badge: 'Held-out' },
      { value: 'Canadian Grand Prix', label: 'Canada',  sublabel: 'Circuit Gilles Villeneuve',     badge: 'Held-out' },
      { value: 'Miami Grand Prix',    label: 'Miami',   sublabel: 'Miami International Autodrome', badge: 'Held-out' },
      { value: 'Belgian Grand Prix',  label: 'Belgium', sublabel: 'Circuit de Spa-Francorchamps',  badge: 'Held-out' },
    ],
  },
  {
    id: 'driver',
    label: 'Reference Driver',
    icon: User,
    accentColor: 'text-blue-300',
    note: 'Driver selection changes which lap is replayed — not the car physics.',
    options: [
      { value: 'VER', label: 'Max Verstappen',  sublabel: 'Red Bull Racing', badge: 'VER' },
      { value: 'HAM', label: 'Lewis Hamilton',  sublabel: 'Ferrari',         badge: 'HAM' },
      { value: 'LEC', label: 'Charles Leclerc', sublabel: 'Ferrari',         badge: 'LEC' },
    ],
  },
  {
    id: 'policy',
    label: 'AI Deployment Policy',
    icon: Cpu,
    accentColor: 'text-red-400',
    note: 'The learned policy is the AI model — others are reference baselines.',
    options: [
      { value: 'learned', label: 'Learned Policy',      sublabel: 'AI Model (HistGBM)',     badge: 'AI' },
      { value: 'ecms',    label: 'ECMS',                sublabel: 'Equivalent Consumption', badge: 'EC' },
      { value: 'greedy',  label: 'Greedy',              sublabel: 'Threshold-based',        badge: 'GR' },
    ],
  },
];

export const CIRCUIT_META: Record<string, { laps: number; length: string; turns: number; lapRecord: string; country: string; mapUrl: string }> = {
  'Monaco Grand Prix':   { laps: 78, length: '3.337 km', turns: 19, lapRecord: '1:12.909', country: 'MC', mapUrl: '/monaco.jpg' },
  'Canadian Grand Prix': { laps: 70, length: '4.361 km', turns: 14, lapRecord: '1:13.078', country: 'CA', mapUrl: '/canada.jpg' },
  'Miami Grand Prix':    { laps: 57, length: '5.412 km', turns: 19, lapRecord: '1:29.708', country: 'US', mapUrl: '/miami.jpg' },
  'Belgian Grand Prix':  { laps: 44, length: '7.004 km', turns: 20, lapRecord: '1:46.286', country: 'BE', mapUrl: '/belgium.jpg' },
};

export const DRIVER_META: Record<string, { number: number; team: string; wdc: number; color: string; nationality: string; bio: string }> = {
  VER: { 
    number: 1,  
    team: 'Red Bull Racing', 
    wdc: 4, 
    color: '#3671C6', 
    nationality: 'NL',
    bio: "Max Verstappen has redefined modern Formula 1 dominance with relentless consistency and aggressive race craft. His reference telemetry is characterised by ultra-late braking and perfect rotation on corner entry, demanding a highly sophisticated AI deployment policy to match his lap times."
  },
  HAM: { 
    number: 44, 
    team: 'Ferrari',          
    wdc: 7, 
    color: '#E8002D', 
    nationality: 'GB',
    bio: "A seven-time World Champion, Lewis Hamilton brings decades of experience and a famously smooth, momentum-carrying driving style to his new chapter at Ferrari. His telemetry provides an excellent benchmark for battery regeneration and tyre management over a full race stint."
  },
  LEC: { 
    number: 16, 
    team: 'Ferrari',          
    wdc: 0, 
    color: '#E8002D', 
    nationality: 'MC',
    bio: "Charles Leclerc is renowned for his blistering one-lap pace and spectacular car control on the limit. His aggressive traction phase and willingness to dance the car on the edge of grip makes his telemetry a punishing benchmark for any AI attempting to optimise energy deployment."
  },
};

export const POLICY_META: Record<string, { type: string; speed: string; compute: string; desc: string }> = {
  greedy:  { type: 'Heuristic', speed: 'Ultra-fast', compute: 'O(1)', desc: 'Rule-based logic: spends available power whenever traction and regulations allow, with zero lookahead. Acts as the cheap baseline floor that every other policy must beat.' },
  dp:      { type: 'Oracle',    speed: 'Offline',    compute: 'O(N²)', desc: 'Dynamic programming over a discretised speed × energy grid, backward-solved for the globally optimal lap. Acts as the oracle generating training labels — far too slow to run at inference.' },
  ecms:    { type: 'Online',    speed: 'Fast',       compute: 'O(K)', desc: 'Equivalent Consumption Minimisation Strategy: prices stored energy with an equivalence factor and picks the locally cheapest deployment via a one-segment lookahead. Near-optimal without requiring a global solve.' },
  learned: { type: 'Model',     speed: 'Real-time',  compute: 'O(1)', desc: "Supervised ML model trained on the DP oracle's labels to imitate optimal deployment at inference speed. Bounded above by DP performance and exposed to distribution shift off the label set." },
};

// ── Sub-components ───────────────────────────────────────────────────────────

// Uniform font system:
//   eyebrow label  → text-[10px] font-medium uppercase tracking-widest text-white/35
//   body value     → text-sm font-semibold text-white
//   sublabel       → text-xs text-white/35
//   heading        → text-xl/2xl/4xl font-bold tracking-tight

const EyebrowLabel = ({ children, className = '' }: { children: React.ReactNode; className?: string }) => (
  <p className={`text-[10px] font-medium uppercase tracking-widest text-white/35 ${className}`}>{children}</p>
);

const GradientBlur = () => (
  <div className="gradient-blur">
    {[...Array(8)].map((_, i) => <div key={i} />)}
  </div>
);

const CircuitMap = ({ circuit }: { circuit: string }) => {
  const url = CIRCUIT_META[circuit].mapUrl;
  return (
    <div className="w-full h-full relative">
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img 
          src={url} 
          alt={circuit} 
          className="w-full h-full object-cover opacity-90"
          onError={(e) => { e.currentTarget.style.opacity = '0'; }}
        />
        <div className="absolute inset-0 flex flex-col items-center justify-center -z-10 bg-neutral-900/40">
          <p className="text-[10px] font-medium uppercase tracking-widest text-white/20">Missing ({url})</p>
        </div>
      </div>
    </div>
  );
};

// No icons — just label/value pairs
const StatChip = ({ label, value }: { label: string; value: string }) => (
  <div className="flex flex-col gap-1.5 bg-white/[0.03] border border-white/[0.06] rounded-2xl px-4 py-3">
    <EyebrowLabel>{label}</EyebrowLabel>
    <span className="text-sm font-semibold text-white">{value}</span>
  </div>
);

// ── Main Component ───────────────────────────────────────────────────────────

export default function SetupPanel({ onStart }: SetupPanelProps) {
  const [selections, setSelections] = useState<Record<string, string>>({
    track: 'Monaco Grand Prix', driver: 'VER', policy: 'learned',
  });
  const [isLoading, setIsLoading] = useState(false);
  const [activeId, setActiveId]   = useState<string | null>(null);
  const [showDriverModal, setShowDriverModal] = useState(false);
  const [showPolicyModal, setShowPolicyModal] = useState(false);

  const timerRef   = useRef<ReturnType<typeof setTimeout> | null>(null);
  const circuit    = CIRCUIT_META[selections.track];
  const driverMeta = DRIVER_META[selections.driver];

  const triggerLoading = useCallback(() => {
    setIsLoading(true);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setIsLoading(false), 750);
  }, []);

  useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current); }, []);

  const closePanel = () => setActiveId(null);

  const select = (id: string, value: string) => {
    if (selections[id] !== value) {
      setSelections(prev => ({ ...prev, [id]: value }));
      triggerLoading();
    }
    closePanel();
  };

  const activeItem = CONFIG_ITEMS.find(c => c.id === activeId) ?? null;

  return (
    <div className="w-full grid grid-cols-1 lg:grid-cols-[420px_1fr] gap-6 lg:gap-8 items-start">

      {/* ── LEFT: Setup Panel ─────────────────────────────────────────────── */}
      <div className="relative">
        <div className={`relative bg-neutral-950/60 backdrop-blur-2xl border border-white/[0.08] rounded-3xl overflow-hidden shadow-[0_20px_60px_rgba(0,0,0,0.8)] transition-all duration-300 ${activeId ? 'scale-[0.97] brightness-75' : ''}`}>

          {/* Header */}
          <div className="px-7 pt-7 pb-6 border-b border-white/[0.06]">
            <EyebrowLabel className="text-blue-400 mb-2">Configure Simulation</EyebrowLabel>
            <h2 className="text-3xl font-black tracking-tight text-white mb-5 drop-shadow-md">Simulation Setup</h2>
            {/* Highlighted Instruction Panel */}
            <div className="bg-blue-900/20 border border-blue-500/30 rounded-xl p-4 shadow-[0_0_20px_rgba(59,130,246,0.1)]">
              <p className="text-xs font-semibold leading-relaxed text-blue-200">
                Configure the circuit, driver reference lap, and AI energy deployment policy before starting your simulation.
              </p>
            </div>
          </div>

          {/* Config Rows */}
          <div className="divide-y divide-white/[0.04]">
            {CONFIG_ITEMS.map((item) => {
              const chosen = item.options.find(o => o.value === selections[item.id]);
              const Icon = item.icon;
              return (
                <div
                  key={item.id}
                  onClick={() => setActiveId(item.id)}
                  className="flex items-center justify-between px-7 py-5 cursor-pointer hover:bg-white/[0.03] transition-colors group"
                >
                  <div className="flex items-center gap-4 min-w-0">
                    <div className="w-9 h-9 rounded-xl bg-white/[0.05] border border-white/[0.07] flex items-center justify-center flex-shrink-0">
                      <Icon size={14} className={item.accentColor} />
                    </div>
                    <div className="min-w-0">
                      <EyebrowLabel className="mb-0.5">{item.label}</EyebrowLabel>
                      <p className="text-sm font-semibold text-white truncate">{chosen?.label ?? '—'}</p>
                      {chosen?.sublabel && <p className="text-xs text-white/25 mt-0.5">{chosen.sublabel}</p>}
                    </div>
                  </div>
                  <ChevronRight size={13} className="text-white/15 group-hover:text-white/40 flex-shrink-0 ml-3 transition-colors" />
                </div>
              );
            })}
          </div>

          {/* Start Button */}
          <div className="px-7 py-6 border-t border-white/[0.06] bg-white/[0.015]">
            <button
              onClick={() => onStart(selections.track, selections.driver, selections.policy)}
              className="w-full bg-white text-black font-semibold text-sm py-4 rounded-full flex items-center justify-center gap-2 shadow-xl transition-all duration-200 hover:scale-[1.02] active:scale-[0.97] hover:bg-neutral-100"
            >
              <Flag size={13} />
              Start Race
            </button>
          </div>
        </div>
      </div>

      {/* ── RIGHT: F1 Context ─────────────────────────────────────────────── */}
      <div className="relative flex flex-col gap-5">

        {/* Loading overlay */}
        <AnimatePresence>
          {isLoading && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="absolute inset-0 z-30 rounded-3xl flex items-center justify-center bg-black/50 backdrop-blur-sm"
            >
              <div className="flex flex-col items-center gap-3">
                <Loader2 size={28} className="text-blue-400 animate-spin" />
                <p className="text-[10px] font-medium uppercase tracking-widest text-white/40">Loading Telemetry</p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Circuit Hero Card */}
        <div className="bg-neutral-950/60 backdrop-blur-2xl border border-white/[0.08] rounded-3xl overflow-hidden shadow-[0_12px_40px_rgba(0,0,0,0.6)]">
          <div className="px-7 pt-7 pb-5 border-b border-white/[0.06]">
            <EyebrowLabel className="text-blue-400 mb-2">Selected Circuit</EyebrowLabel>
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-2xl font-bold tracking-tight text-white">
                  {selections.track.replace(' Grand Prix', '')}
                </h2>
                <p className="text-xs text-white/30 mt-0.5">{selections.track}</p>
              </div>
              <div className="flex items-center gap-2 mt-1 flex-shrink-0">
                <span className="text-[10px] font-medium text-white/25 tracking-widest uppercase">{circuit.country}</span>
                <div className="w-px h-3 bg-white/10" />
                <Flag size={11} className="text-white/25" />
                <span className="text-[10px] font-medium text-white/25">{circuit.laps} laps</span>
              </div>
            </div>
          </div>

          {/* Circuit SVG Map */}
          <div className="relative bg-neutral-950/40 mx-5 mt-4 mb-2 rounded-2xl overflow-hidden border border-white/[0.05]" style={{ height: '360px' }}>
            <AnimatePresence mode="wait">
              <motion.div
                key={selections.track}
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="absolute inset-0 flex items-center justify-center p-4"
              >
                <CircuitMap circuit={selections.track} />
              </motion.div>
            </AnimatePresence>
            <div className="absolute bottom-3 left-1/2 -translate-x-1/2">
              <span className="text-[9px] font-medium uppercase tracking-widest text-blue-400/60">S/F</span>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3 p-5 pt-3">
            <StatChip label="Length"    value={circuit.length} />
            <StatChip label="Turns"     value={`${circuit.turns}`} />
            <StatChip label="Lap Record" value={circuit.lapRecord} />
          </div>
        </div>

        {/* Driver + AI Policy Row */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">

          {/* Driver Card */}
          <div 
            onClick={() => setShowDriverModal(true)}
            className="bg-neutral-950/60 backdrop-blur-2xl border border-white/[0.08] rounded-3xl p-6 shadow-[0_12px_40px_rgba(0,0,0,0.5)] cursor-pointer hover:bg-white/[0.03] transition-colors"
          >
            <div className="flex items-center justify-between mb-4">
              <EyebrowLabel className="text-blue-300">Reference Driver</EyebrowLabel>
              <div className="w-5 h-5 rounded-full bg-white/[0.05] flex items-center justify-center flex-shrink-0">
                <ChevronRight size={10} className="text-white/30" />
              </div>
            </div>
            <div className="flex items-center gap-3.5 mb-5">
              <div
                className="w-14 h-14 rounded-2xl flex items-center justify-center text-xl font-black text-white flex-shrink-0"
                style={{ backgroundColor: `${driverMeta.color}20`, border: `1px solid ${driverMeta.color}50` }}
              >
                #{driverMeta.number}
              </div>
              <div className="min-w-0">
                <p className="font-semibold text-white text-sm leading-tight">
                  {CONFIG_ITEMS[1].options.find(o => o.value === selections.driver)?.label}
                </p>
                <p className="text-xs text-white/35 mt-0.5">{driverMeta.team}</p>
                <p className="text-[10px] font-medium text-white/20 mt-1 tracking-widest uppercase">{driverMeta.nationality}</p>
              </div>
            </div>
            <div className="border-t border-white/[0.05] pt-4 flex items-center justify-between">
              <div>
                <EyebrowLabel className="mb-1">WDC Titles</EyebrowLabel>
                <p className="text-2xl font-bold text-white">{driverMeta.wdc}<span className="text-sm font-normal text-white/30 ml-0.5">×</span></p>
              </div>
              <div className="text-right">
                <EyebrowLabel className="mb-1">Code</EyebrowLabel>
                <p className="text-2xl font-bold" style={{ color: driverMeta.color }}>{selections.driver}</p>
              </div>
            </div>
          </div>

          {/* AI Policy Card */}
          <div 
            onClick={() => setShowPolicyModal(true)}
            className="bg-neutral-950/60 backdrop-blur-2xl border border-white/[0.08] rounded-3xl p-6 shadow-[0_12px_40px_rgba(0,0,0,0.5)] cursor-pointer hover:bg-white/[0.03] transition-colors"
          >
            <div className="flex items-center justify-between mb-4">
              <EyebrowLabel className="text-red-400">AI Policy</EyebrowLabel>
              <div className="w-5 h-5 rounded-full bg-white/[0.05] flex items-center justify-center flex-shrink-0">
                <ChevronRight size={10} className="text-white/30" />
              </div>
            </div>
            <div className="flex items-center gap-3.5 mb-5">
              <div className="w-14 h-14 rounded-2xl bg-red-500/10 border border-red-500/25 flex items-center justify-center flex-shrink-0">
                <Cpu size={22} className="text-red-400" />
              </div>
              <div className="min-w-0">
                <p className="font-semibold text-white text-sm leading-tight">
                  {CONFIG_ITEMS[2].options.find(o => o.value === selections.policy)?.label}
                </p>
                <p className="text-xs text-white/35 mt-0.5">
                  {CONFIG_ITEMS[2].options.find(o => o.value === selections.policy)?.sublabel}
                </p>
              </div>
            </div>
            <div className="border-t border-white/[0.05] pt-4 flex gap-4 justify-between">
              <div>
                <EyebrowLabel className="mb-1">Type</EyebrowLabel>
                <p className="text-sm font-semibold text-white">{POLICY_META[selections.policy].type}</p>
              </div>
              <div className="text-right">
                <EyebrowLabel className="mb-1">Compute</EyebrowLabel>
                <p className="text-sm font-semibold text-white">{POLICY_META[selections.policy].compute}</p>
              </div>
            </div>
          </div>
        </div>

        {/* 2026 Regs Banner */}
        <div className="bg-blue-950/20 border border-blue-500/15 rounded-2xl px-6 py-4">
          <p className="text-xs font-semibold text-blue-300/80 mb-1">2026 F1 Regulations</p>
          <p className="text-xs text-blue-300/40 leading-relaxed">
            Maximum <span className="text-blue-300/70 font-semibold">350 kW</span> electrical output from a{' '}
            <span className="text-blue-300/70 font-semibold">4 MJ</span> battery cap per lap.
            Car mass: <span className="text-blue-300/70 font-semibold">798 kg</span>.
            The AI learns optimal deployment timing to minimise lap time.
          </p>
        </div>
      </div>

      {/* ── CENTERED MODAL: Selection List ──────────────────────────────────── */}
      <AnimatePresence>
        {activeId && activeItem && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
              onClick={closePanel}
            />

            {/* Centered modal */}
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 16 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 16 }}
              transition={{ type: 'spring', stiffness: 400, damping: 32 }}
              className="fixed inset-0 z-50 flex items-center justify-center p-6 pointer-events-none"
            >
              <div
                className="w-full max-w-sm bg-neutral-950/80 backdrop-blur-2xl border border-white/[0.12] rounded-3xl overflow-hidden shadow-[0_24px_60px_rgba(0,0,0,0.9)] pointer-events-auto"
                onClick={e => e.stopPropagation()}
              >
                {/* Modal header */}
                <div className="flex items-center justify-between px-7 py-5 border-b border-white/[0.07]">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-xl bg-white/[0.06] border border-white/[0.08] flex items-center justify-center">
                      <activeItem.icon size={13} className={activeItem.accentColor} />
                    </div>
                    <div>
                      <EyebrowLabel className="mb-0.5">Select</EyebrowLabel>
                      <p className="text-sm font-semibold text-white">{activeItem.label}</p>
                    </div>
                  </div>
                  <button
                    onClick={closePanel}
                    className="p-2 rounded-full bg-white/[0.07] hover:bg-white/[0.14] border border-white/[0.08] transition-colors text-white/40 hover:text-white"
                  >
                    <X size={12} />
                  </button>
                </div>

                {/* Options */}
                <div className="overflow-y-auto max-h-[320px] pb-20">
                  {activeItem.options.map((opt) => {
                    const isSelected = selections[activeId] === opt.value;
                    return (
                      <div
                        key={opt.value}
                        onClick={() => select(activeId, opt.value)}
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

                {/* Footnote */}
                {activeItem.note && (
                  <div className="px-7 py-3.5 border-t border-white/[0.05]">
                    <p className="text-xs text-white/20 leading-relaxed">* {activeItem.note}</p>
                  </div>
                )}

                <GradientBlur />
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* ── DRIVER INFO MODAL ─────────────────────────────────────────────── */}
      <AnimatePresence>
        {showDriverModal && (
          <>
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}
              className="fixed inset-0 z-40 bg-black/60 backdrop-blur-md"
              onClick={() => setShowDriverModal(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 16 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 16 }}
              transition={{ type: 'spring', stiffness: 400, damping: 32 }}
              className="fixed inset-0 z-50 flex items-center justify-center p-6 pointer-events-none"
            >
              <div 
                className="relative w-full max-w-md bg-neutral-950/80 backdrop-blur-2xl border border-white/[0.12] rounded-3xl overflow-hidden shadow-[0_24px_60px_rgba(0,0,0,0.9)] pointer-events-auto"
                onClick={e => e.stopPropagation()}
              >
                {/* Header */}
                <div className="flex items-center justify-between px-7 py-5 border-b border-white/[0.07] z-20 relative">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-xl bg-white/[0.06] border border-white/[0.08] flex items-center justify-center">
                      <User size={13} className="text-blue-300" />
                    </div>
                    <div>
                      <EyebrowLabel className="mb-0.5">Driver Profile</EyebrowLabel>
                      <p className="text-sm font-semibold text-white">{CONFIG_ITEMS[1].options.find(o => o.value === selections.driver)?.label}</p>
                    </div>
                  </div>
                  <button onClick={() => setShowDriverModal(false)} className="p-2 rounded-full bg-white/[0.07] hover:bg-white/[0.14] border border-white/[0.08] transition-colors text-white/40 hover:text-white">
                    <X size={12} />
                  </button>
                </div>

                {/* Photo Area */}
                <div className="relative w-full h-64 bg-neutral-950 border-b border-white/[0.05] z-10">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img 
                    src={`/${selections.driver}.png`} 
                    alt={selections.driver} 
                    className="absolute inset-0 w-full h-full object-contain object-bottom opacity-90 z-10"
                    onError={(e) => { e.currentTarget.style.opacity = '0'; }} 
                  />
                  {/* Fallback if no image */}
                  <div className="absolute inset-0 flex flex-col items-center justify-center z-0 bg-neutral-900/50">
                    <User size={48} className="text-white/10 mb-4" />
                    <p className="text-[10px] font-medium uppercase tracking-widest text-white/20">Photo missing (/{selections.driver}.png)</p>
                  </div>
                  
                  {/* Gradient Overlay at bottom of photo */}
                  <div className="absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-neutral-950 to-transparent z-10" />
                  
                  {/* Floating Number */}
                  <div 
                    className="absolute bottom-4 right-6 text-[80px] leading-none font-black italic tracking-tighter z-20"
                    style={{ color: driverMeta.color, textShadow: '0 4px 24px rgba(0,0,0,0.8)' }}
                  >
                    {driverMeta.number}
                  </div>
                </div>

                {/* Details */}
                <div className="p-7 pt-5 relative z-20 bg-neutral-950/40">
                  <div className="flex gap-6 mb-6">
                    <div>
                      <EyebrowLabel className="mb-1">Team</EyebrowLabel>
                      <p className="text-sm font-semibold text-white">{driverMeta.team}</p>
                    </div>
                    <div>
                      <EyebrowLabel className="mb-1">WDC Titles</EyebrowLabel>
                      <p className="text-sm font-semibold text-white">{driverMeta.wdc}</p>
                    </div>
                    <div>
                      <EyebrowLabel className="mb-1">Nationality</EyebrowLabel>
                      <p className="text-sm font-semibold text-white uppercase">{driverMeta.nationality}</p>
                    </div>
                  </div>
                  
                  <EyebrowLabel className="mb-2">Telemetry Profile</EyebrowLabel>
                  <p className="text-sm text-white/60 leading-relaxed font-medium">
                    {driverMeta.bio}
                  </p>
                </div>
                
                <GradientBlur />
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* ── AI POLICY INFO MODAL ──────────────────────────────────────────── */}
      <AnimatePresence>
        {showPolicyModal && (
          <>
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}
              className="fixed inset-0 z-40 bg-black/60 backdrop-blur-md"
              onClick={() => setShowPolicyModal(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 16 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 16 }}
              transition={{ type: 'spring', stiffness: 400, damping: 32 }}
              className="fixed inset-0 z-50 flex items-center justify-center p-6 pointer-events-none"
            >
              <div 
                className="relative w-full max-w-md bg-neutral-950/80 backdrop-blur-2xl border border-white/[0.12] rounded-3xl overflow-hidden shadow-[0_24px_60px_rgba(0,0,0,0.9)] pointer-events-auto"
                onClick={e => e.stopPropagation()}
              >
                {/* Header */}
                <div className="flex items-center justify-between px-7 py-5 border-b border-white/[0.07] z-20 relative">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-xl bg-white/[0.06] border border-white/[0.08] flex items-center justify-center">
                      <Cpu size={13} className="text-red-400" />
                    </div>
                    <div>
                      <EyebrowLabel className="mb-0.5">Deployment Policy</EyebrowLabel>
                      <p className="text-sm font-semibold text-white">{CONFIG_ITEMS[2].options.find(o => o.value === selections.policy)?.label}</p>
                    </div>
                  </div>
                  <button onClick={() => setShowPolicyModal(false)} className="p-2 rounded-full bg-white/[0.07] hover:bg-white/[0.14] border border-white/[0.08] transition-colors text-white/40 hover:text-white">
                    <X size={12} />
                  </button>
                </div>

                {/* Hero / Graphic Area */}
                <div className="relative w-full h-56 bg-neutral-950 border-b border-white/[0.05] z-10 flex flex-col items-center justify-center">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img 
                    src={`/${selections.policy}.jpg`} 
                    alt={selections.policy} 
                    className="absolute inset-0 w-full h-full object-cover opacity-90 z-10"
                    onError={(e) => { e.currentTarget.style.opacity = '0'; }} 
                  />
                  {/* Fallback graphic if no image provided */}
                  <div className="absolute inset-0 flex flex-col items-center justify-center z-0 bg-neutral-900/40">
                    <div className="w-20 h-20 rounded-2xl bg-red-500/10 border border-red-500/20 flex items-center justify-center mb-4">
                      <Cpu size={40} className="text-red-400/50" />
                    </div>
                    <p className="text-[10px] font-medium uppercase tracking-widest text-white/20">Graphic missing (/{selections.policy}.jpg)</p>
                  </div>
                  
                  {/* Gradient Overlay */}
                  <div className="absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-neutral-950 to-transparent z-10" />
                  
                  {/* Floating Badge */}
                  <div className="absolute bottom-5 right-6 z-20">
                    <span className="text-[10px] font-medium px-3 py-1.5 rounded-full border border-red-500/30 text-red-400 bg-red-500/10 tracking-widest uppercase shadow-[0_0_12px_rgba(248,113,113,0.2)]">
                      {CONFIG_ITEMS[2].options.find(o => o.value === selections.policy)?.badge}
                    </span>
                  </div>
                </div>

                {/* Details */}
                <div className="p-7 pt-5 relative z-20 bg-neutral-950/40">
                  <div className="flex gap-6 mb-6">
                    <div>
                      <EyebrowLabel className="mb-1">Type</EyebrowLabel>
                      <p className="text-sm font-semibold text-white">{POLICY_META[selections.policy].type}</p>
                    </div>
                    <div>
                      <EyebrowLabel className="mb-1">Speed</EyebrowLabel>
                      <p className="text-sm font-semibold text-white">{POLICY_META[selections.policy].speed}</p>
                    </div>
                    <div>
                      <EyebrowLabel className="mb-1">Compute Cost</EyebrowLabel>
                      <p className="text-sm font-semibold text-white">{POLICY_META[selections.policy].compute}</p>
                    </div>
                  </div>
                  
                  <EyebrowLabel className="mb-2">Algorithm Description</EyebrowLabel>
                  <p className="text-sm text-white/60 leading-relaxed font-medium">
                    {POLICY_META[selections.policy].desc}
                  </p>
                </div>
                
                <GradientBlur />
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
