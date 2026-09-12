"use client";

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Check, X, ChevronRight, MapPin, User, Cpu, Flag, Loader2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { SpinningBorderButton } from '@/components/ui/spinning-border-button';
import { DropdownMenu } from '@/components/ui/dropdown-menu';

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

// Shown in the setup bar — the AI deployment policy is no longer user-selectable here,
// but stays in CONFIG_ITEMS because the in-race Dashboard still exposes it.
const SETUP_ITEMS: ConfigItem[] = CONFIG_ITEMS.filter(c => c.id !== 'policy');

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
          className="w-full h-full object-contain opacity-90"
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

// Site's brand gradient: blue on the left, red on the right.
const SPOT_BLUE: [number, number, number] = [59, 130, 246];
const SPOT_RED: [number, number, number] = [239, 68, 68];
const lerp = (a: number, b: number, t: number) => Math.round(a + (b - a) * t);

// Cursor-tracked glow: follows the pointer and blends blue→red across the card's width.
function useSpotlight() {
  const ref = useRef<HTMLDivElement>(null);
  const onMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const el = ref.current;
    const rect = el?.getBoundingClientRect();
    if (!el || !rect) return;
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const t = Math.min(1, Math.max(0, rect.width ? x / rect.width : 0));
    const [r, g, b] = [
      lerp(SPOT_BLUE[0], SPOT_RED[0], t),
      lerp(SPOT_BLUE[1], SPOT_RED[1], t),
      lerp(SPOT_BLUE[2], SPOT_RED[2], t),
    ];
    el.style.setProperty('--spot-x', `${x}px`);
    el.style.setProperty('--spot-y', `${y}px`);
    el.style.setProperty('--spot-color', `rgba(${r}, ${g}, ${b}, 0.2)`);
  };
  return { ref, onMouseMove };
}

const Spotlight = () => (
  <div
    aria-hidden
    className="pointer-events-none absolute inset-0 -z-10 rounded-[inherit] opacity-0 transition-opacity duration-300 group-hover:opacity-100"
    style={{ background: `radial-gradient(320px circle at var(--spot-x, 50%) var(--spot-y, 50%), var(--spot-color, rgba(150,99,157,0.2)), transparent 60%)` }}
  />
);

// ── Main Component ───────────────────────────────────────────────────────────

export default function SetupPanel({ onStart }: SetupPanelProps) {
  const [selections, setSelections] = useState<Record<string, string>>({
    track: 'Monaco Grand Prix', driver: 'VER', policy: 'learned',
  });
  const [isLoading, setIsLoading] = useState(false);
  const [showDriverModal, setShowDriverModal] = useState(false);

  const timerRef   = useRef<ReturnType<typeof setTimeout> | null>(null);
  const circuit    = CIRCUIT_META[selections.track];
  const driverMeta = DRIVER_META[selections.driver];

  const setupSpot   = useSpotlight();
  const egoSpot     = useSpotlight();
  const circuitSpot = useSpotlight();
  const driverSpot  = useSpotlight();
  const startSpot   = useSpotlight();
  const regsSpot    = useSpotlight();

  const triggerLoading = useCallback(() => {
    setIsLoading(true);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setIsLoading(false), 750);
  }, []);

  useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current); }, []);

  const select = (id: string, value: string) => {
    if (selections[id] !== value) {
      setSelections(prev => ({ ...prev, [id]: value }));
      triggerLoading();
    }
  };

  return (
    <div className="w-full flex flex-col gap-6">

      {/* ── TOP: Simulation Setup — title left, selectors right ───────────── */}
      <div
        ref={setupSpot.ref}
        onMouseMove={setupSpot.onMouseMove}
        className="relative isolate group z-30 bg-neutral-950/90 backdrop-blur-2xl border border-white/[0.08] rounded-3xl shadow-[0_20px_60px_rgba(0,0,0,0.8)] transition-colors duration-300 group-hover:border-blue-400/25"
      >
        <Spotlight />
        <div className="grid grid-cols-1 md:grid-cols-[2fr_3fr_3fr]">

          {/* Title block */}
          <div className="px-6 py-6 border-b md:border-b-0 md:border-r border-white/[0.06] flex flex-col justify-center">
            <h2 className="text-2xl font-black tracking-tight text-white mb-2 drop-shadow-md">Simulation Setup</h2>
            <p className="text-xs font-medium leading-relaxed text-white/35">
              Pick the circuit and the reference driver lap, then start the simulation.
            </p>
          </div>

          {/* Selectors — animated DropdownMenu per setting */}
          {SETUP_ITEMS.map((item, i) => {
            const chosen = item.options.find(o => o.value === selections[item.id]);
            const Icon = item.icon;
            return (
              <div
                key={item.id}
                className={`relative flex flex-col justify-center p-2 ${i > 0 ? 'border-t md:border-t-0 md:border-l border-white/[0.06]' : ''}`}
              >
                {/* The whole section is the dropdown trigger */}
                <DropdownMenu
                  triggerClassName="w-full h-auto justify-between px-4 py-4 rounded-2xl bg-transparent hover:bg-white/[0.05] shadow-none backdrop-blur-none text-left whitespace-normal"
                  menuClassName="w-full"
                  options={item.options.map(opt => ({
                    label: opt.label,
                    onClick: () => select(item.id, opt.value),
                    Icon: opt.value === selections[item.id]
                      ? <Check className="h-4 w-4 text-blue-400" />
                      : <span className="h-4 w-4" />,
                  }))}
                >
                  <span className="flex items-center gap-4 min-w-0">
                    <span className="w-9 h-9 rounded-xl bg-white/[0.05] border border-white/[0.07] flex items-center justify-center flex-shrink-0">
                      <Icon size={14} className={item.accentColor} />
                    </span>
                    <span className="min-w-0 block">
                      <span className="block text-[10px] font-medium uppercase tracking-widest text-white/35 mb-0.5">{item.label}</span>
                      <span className="block text-sm font-semibold text-white truncate">{chosen?.label ?? '—'}</span>
                      {chosen?.sublabel && <span className="block text-xs text-white/25 mt-0.5 truncate">{chosen.sublabel}</span>}
                    </span>
                  </span>
                </DropdownMenu>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Ego Car — the simulated vehicle the AI controls ───────────────── */}
      <div
        ref={egoSpot.ref}
        onMouseMove={egoSpot.onMouseMove}
        className="relative isolate group bg-neutral-950/90 backdrop-blur-2xl border border-white/[0.08] rounded-3xl shadow-[0_12px_40px_rgba(0,0,0,0.6)] overflow-hidden transition-colors duration-300 group-hover:border-red-400/25"
      >
        <Spotlight />
        <div className="grid grid-cols-1 md:grid-cols-3">

          <div className="px-6 py-6 border-b md:border-b-0 md:border-r border-white/[0.06] flex flex-col justify-center">
            <EyebrowLabel className="text-red-400 mb-2">Simulated Vehicle</EyebrowLabel>
            <h2 className="text-2xl font-black tracking-tight text-white mb-2 drop-shadow-md">Ego Car</h2>
            <p className="text-xs font-medium leading-relaxed text-white/35">
              The car the AI drives. Only energy deployment is controlled — the physics follow the 2026 spec.
            </p>
          </div>

          <div className="relative min-h-[140px] flex items-center justify-center px-6 py-6 border-b md:border-b-0 md:border-r border-white/[0.06]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/haas_car2.png" alt="Ego car" className="w-full max-w-[320px] object-contain drop-shadow-[0_10px_30px_rgba(0,0,0,0.8)]" />
          </div>

          <div className="grid grid-cols-2 gap-3 p-5">
            <StatChip label="Mass"    value="798 kg" />
            <StatChip label="Max ERS" value="350 kW" />
            <StatChip label="Battery" value="4 MJ / lap" />
            <StatChip label="Policy"  value="Learned (AI)" />
          </div>
        </div>
      </div>

      {/* ── BELOW: Circuit Map + Driver Info ──────────────────────────────── */}
      <div className="relative grid grid-cols-1 md:grid-cols-[3fr_2fr] gap-6 items-stretch">

        {/* Loading overlay */}
        <AnimatePresence>
          {isLoading && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="absolute inset-0 z-20 rounded-3xl flex items-center justify-center bg-black/50 backdrop-blur-sm"
            >
              <div className="flex flex-col items-center gap-3">
                <Loader2 size={28} className="text-blue-400 animate-spin" />
                <p className="text-[10px] font-medium uppercase tracking-widest text-white/40">Loading Telemetry</p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Circuit Hero Card */}
        <div
          ref={circuitSpot.ref}
          onMouseMove={circuitSpot.onMouseMove}
          className="relative isolate group h-full flex flex-col bg-neutral-950/90 backdrop-blur-2xl border border-white/[0.08] rounded-3xl overflow-hidden shadow-[0_12px_40px_rgba(0,0,0,0.6)] transition-colors duration-300 group-hover:border-blue-400/25"
        >
          <Spotlight />
          <div className="px-6 pt-6 pb-5 border-b border-white/[0.06]">
            <EyebrowLabel className="text-blue-400 mb-2">Selected Circuit</EyebrowLabel>
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h2 className="text-2xl font-bold tracking-tight text-white truncate">
                  {selections.track.replace(' Grand Prix', '')}
                </h2>
                <p className="text-xs text-white/30 mt-0.5 truncate">{selections.track}</p>
              </div>
              <div className="flex items-center gap-2 mt-1 flex-shrink-0">
                <span className="text-[10px] font-medium text-white/25 tracking-widest uppercase">{circuit.country}</span>
                <div className="w-px h-3 bg-white/10" />
                <Flag size={11} className="text-white/25" />
                <span className="text-[10px] font-medium text-white/25">{circuit.laps} laps</span>
              </div>
            </div>
          </div>

          {/* Circuit map — panel is black to match the source images' own background, so the
              letterboxing from object-contain is invisible rather than a grey band. */}
          <div className="relative w-full flex-1 min-h-[260px] bg-black overflow-hidden border-b border-white/[0.05]">
            <AnimatePresence mode="wait">
              <motion.div
                key={selections.track}
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="absolute inset-0"
              >
                <CircuitMap circuit={selections.track} />
              </motion.div>
            </AnimatePresence>
            <div className="absolute bottom-2 left-1/2 -translate-x-1/2">
              <span className="text-[9px] font-medium uppercase tracking-widest text-blue-400/60">S/F</span>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3 p-5">
            <StatChip label="Length"    value={circuit.length} />
            <StatChip label="Turns"     value={`${circuit.turns}`} />
            <StatChip label="Lap Record" value={circuit.lapRecord} />
          </div>
        </div>

        {/* Driver Info Card — full profile */}
        <div
          ref={driverSpot.ref}
          onMouseMove={driverSpot.onMouseMove}
          className="relative isolate group h-full flex flex-col bg-neutral-950/90 backdrop-blur-2xl border border-white/[0.08] rounded-3xl overflow-hidden shadow-[0_12px_40px_rgba(0,0,0,0.5)] transition-colors duration-300 group-hover:border-blue-300/25"
        >
          <Spotlight />

          {/* Header */}
          <div className="px-6 pt-6 pb-5 border-b border-white/[0.06] flex items-start justify-between gap-4">
            <div className="min-w-0">
              <EyebrowLabel className="text-blue-300 mb-2">Reference Driver</EyebrowLabel>
              <h2 className="text-2xl font-bold tracking-tight text-white truncate">
                {CONFIG_ITEMS[1].options.find(o => o.value === selections.driver)?.label}
              </h2>
              <p className="text-xs text-white/30 mt-0.5 truncate">{driverMeta.team}</p>
            </div>
            <button
              type="button"
              onClick={() => setShowDriverModal(true)}
              className="w-8 h-8 rounded-full bg-white/[0.05] border border-white/[0.08] flex items-center justify-center flex-shrink-0 text-white/30 hover:text-white hover:bg-white/[0.12] transition-colors"
            >
              <ChevronRight size={12} />
            </button>
          </div>

          {/* Driver photo */}
          <div className="relative w-full aspect-[4/3] bg-neutral-950/40 overflow-hidden border-b border-white/[0.05]">
            <AnimatePresence mode="wait">
              <motion.div
                key={selections.driver}
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="absolute inset-0"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`/${selections.driver}.png`}
                  alt={selections.driver}
                  className="absolute inset-0 w-full h-full object-contain object-bottom opacity-90 z-10"
                  onError={(e) => { e.currentTarget.style.opacity = '0'; }}
                />
                <div className="absolute inset-0 flex flex-col items-center justify-center z-0 bg-neutral-900/40">
                  <User size={40} className="text-white/10 mb-3" />
                  <p className="text-[10px] font-medium uppercase tracking-widest text-white/20">Photo missing (/{selections.driver}.png)</p>
                </div>
              </motion.div>
            </AnimatePresence>
            <div className="absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-neutral-950 to-transparent z-10 pointer-events-none" />
            <div
              className="absolute bottom-2 right-5 text-[56px] leading-none font-black italic tracking-tighter z-20 pointer-events-none"
              style={{ color: driverMeta.color, textShadow: '0 4px 24px rgba(0,0,0,0.8)' }}
            >
              {driverMeta.number}
            </div>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-3 gap-3 p-5 pb-3">
            <StatChip label="WDC Titles"  value={`${driverMeta.wdc}`} />
            <StatChip label="Code"        value={selections.driver} />
            <StatChip label="Nationality" value={driverMeta.nationality} />
          </div>

          {/* Telemetry profile */}
          <div className="px-6 pb-6 pt-2 mt-auto">
            <EyebrowLabel className="mb-2">Telemetry Profile</EyebrowLabel>
            <p className="text-xs text-white/45 leading-relaxed font-medium line-clamp-4">
              {driverMeta.bio}
            </p>
          </div>
        </div>
      </div>

      {/* ── Start Race ────────────────────────────────────────────────────── */}
      <div
        ref={startSpot.ref}
        onMouseMove={startSpot.onMouseMove}
        className="relative isolate group bg-neutral-950/90 backdrop-blur-2xl border border-white/[0.08] rounded-3xl px-6 py-5 shadow-[0_12px_40px_rgba(0,0,0,0.6)] flex flex-col sm:flex-row sm:items-center gap-4 transition-colors duration-300 group-hover:border-red-400/25"
      >
        <Spotlight />
        <div className="min-w-0 flex-1">
          <EyebrowLabel className="mb-1">Ready to launch</EyebrowLabel>
          <p className="text-sm font-semibold text-white truncate">
            {selections.track.replace(' Grand Prix', '')}
            <span className="text-white/25 font-normal"> · </span>
            {CONFIG_ITEMS[1].options.find(o => o.value === selections.driver)?.label}
          </p>
        </div>
        <SpinningBorderButton
          text="Start Race"
          onClick={() => onStart(selections.track, selections.driver, selections.policy)}
        />
      </div>

      {/* ── BOTTOM: 2026 Regs Banner ──────────────────────────────────────── */}
      <div
        ref={regsSpot.ref}
        onMouseMove={regsSpot.onMouseMove}
        className="relative isolate group bg-blue-950/35 border border-blue-500/15 rounded-2xl px-6 py-4 transition-colors duration-300 group-hover:border-blue-400/40"
      >
        <Spotlight />
        <p className="text-xs font-semibold text-blue-300/80 mb-1">2026 F1 Regulations</p>
        <p className="text-xs text-blue-300/40 leading-relaxed">
          Maximum <span className="text-blue-300/70 font-semibold">350 kW</span> electrical output from a{' '}
          <span className="text-blue-300/70 font-semibold">4 MJ</span> battery cap per lap.
          Car mass: <span className="text-blue-300/70 font-semibold">798 kg</span>.
          The AI learns optimal deployment timing to minimise lap time.
        </p>
      </div>

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
                className="relative w-full max-w-md bg-neutral-950/95 backdrop-blur-2xl border border-white/[0.12] rounded-3xl overflow-hidden shadow-[0_24px_60px_rgba(0,0,0,0.9)] pointer-events-auto"
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
    </div>
  );
}
