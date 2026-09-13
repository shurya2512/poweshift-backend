"use client";

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Check, X, MapPin, User, Cpu, Flag, Loader2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { SpinningBorderButton } from '@/components/ui/spinning-border-button';
import { DropdownMenu } from '@/components/ui/dropdown-menu';
import { BentoSection, BentoCard } from '@/components/MagicBento';
import { TrailCard } from '@/components/ui/trail-card';
import { EGO_PROFILES, egoProfile, sessionTracks } from '@/lib/backend/profiles';

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

/** Which session is being set up. The two are laid out identically and read differently. */
export type SetupMode = 'qualifying' | 'full-race';

interface SetupPanelProps {
  mode: SetupMode;
  onStart: (track: string, driver: string, policy: string) => void;
}

// ── Static Data ──────────────────────────────────────────────────────────────

export const CONFIG_ITEMS: ConfigItem[] = [
  {
    id: 'track',
    label: 'Circuit',
    icon: MapPin,
    accentColor: 'text-blue-400',
    note: 'Only events present in the selected diagnostic report set are shown.',
    options: sessionTracks('qualifying').map((track) => ({
      value: track.event,
      label: track.label,
      sublabel: track.circuit,
      badge: 'Report',
    })),
  },
  {
    id: 'driver',
    label: 'Ego Driver',
    icon: User,
    accentColor: 'text-blue-300',
    note: 'Each choice runs the promoted neural vehicle profile for that entry.',
    options: EGO_PROFILES.map((profile) => ({
      value: profile.entry,
      label: profile.name,
      sublabel: profile.team,
      badge: `${profile.code} · #${profile.entry}`,
    })),
  },
  {
    id: 'policy',
    label: 'AI Deployment Policy',
    icon: Cpu,
    accentColor: 'text-red-400',
    note: 'The learned policy is the AI model — others are reference baselines.',
    options: [
      { value: 'learned', label: 'Learned Policy',      sublabel: 'Recurrent actor-critic', badge: 'RL' },
      { value: 'ecms',    label: 'ECMS',                sublabel: 'Equivalent Consumption', badge: 'EC' },
      { value: 'greedy',  label: 'Greedy',              sublabel: 'Threshold-based',        badge: 'GR' },
    ],
  },
];

// Shown in the setup bar — the AI deployment policy is no longer user-selectable here,
// but stays in CONFIG_ITEMS because the in-race Dashboard still exposes it.
const SETUP_ITEMS: ConfigItem[] = CONFIG_ITEMS.filter(c => c.id !== 'policy');

/**
 * Copy that changes with the selected session.
 */
const MODE_COPY: Record<SetupMode, {
  intro: string;
  driverLabel: string;
  driverNote: string;
  driverCaption: (circuit: string) => string;
}> = {
  qualifying: {
    intro: 'Pick the circuit and ego profile for the qualifying diagnostic.',
    driverLabel: 'Ego Driver / Profile',
    driverNote: 'The selected promoted profile is evaluated on that qualifying set.',
    driverCaption: circuit => `${circuit} qualifying profile`,
  },
  'full-race': {
    intro: 'Pick the circuit and the ego driver, then start the race.',
    driverLabel: 'Ego Driver',
    driverNote: 'The selected profile is added at P23 with learned energy and overtake intelligence.',
    driverCaption: circuit => `${circuit} full race`,
  },
};

export const CIRCUIT_META = Object.fromEntries(
  sessionTracks('qualifying').map((track) => [track.event, track]),
);

export const POLICY_META: Record<string, { type: string; speed: string; compute: string; desc: string }> = {
  greedy:  { type: 'Heuristic', speed: 'Ultra-fast', compute: 'O(1)', desc: 'Rule-based logic: spends available power whenever traction and regulations allow, with zero lookahead. Acts as the cheap baseline floor that every other policy must beat.' },
  dp:      { type: 'Oracle',    speed: 'Offline',    compute: 'O(N²)', desc: 'Dynamic programming over a discretised speed × energy grid, backward-solved for the globally optimal lap. Acts as the oracle generating training labels — far too slow to run at inference.' },
  ecms:    { type: 'Online',    speed: 'Fast',       compute: 'O(K)', desc: 'Equivalent Consumption Minimisation Strategy: prices stored energy with an equivalence factor and picks the locally cheapest deployment via a one-segment lookahead. Near-optimal without requiring a global solve.' },
  learned: { type: 'Model',     speed: 'Real-time',  compute: 'O(1)', desc: 'Recurrent actor-critic policy trained chronologically to select hold, attack or defend with a continuous deployment fraction.' },
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
  if (!url) {
    return <div className="flex h-full items-center justify-center text-xs uppercase tracking-widest text-white/30">No race map yet</div>;
  }
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
        <div aria-hidden className="absolute inset-0 flex flex-col items-center justify-center -z-10 bg-neutral-900/40">
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

export default function SetupPanel({ mode, onStart }: SetupPanelProps) {
  const availableTracks = sessionTracks(mode);
  const [selections, setSelections] = useState<Record<string, string>>({
    track: availableTracks[0].event, driver: EGO_PROFILES[0].entry, policy: 'learned',
  });
  const [isLoading, setIsLoading] = useState(false);
  const [showDriverModal, setShowDriverModal] = useState(false);

  const timerRef   = useRef<ReturnType<typeof setTimeout> | null>(null);
  const circuit    = CIRCUIT_META[selections.track];
  const driverMeta = egoProfile(selections.driver);
  const copy       = MODE_COPY[mode];

  // The driver means a different thing in each session, so it is relabelled rather
  // than duplicated — the options, and every other setting, are identical.
  const setupItems = SETUP_ITEMS.map((item) => {
    if (item.id === 'track') return {
      ...item,
      options: availableTracks.map((track) => ({ value: track.event, label: track.label, sublabel: track.circuit, badge: 'Report' })),
    };
    return item.id === 'driver' ? { ...item, label: copy.driverLabel, note: copy.driverNote } : item;
  });

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
    <BentoSection className="w-full flex flex-col gap-6">

      {/* ── TOP: Simulation Setup — title left, selectors right ───────────── */}
      <BentoCard className="relative isolate group z-30 bg-neutral-950/90 backdrop-blur-2xl border border-white/[0.08] rounded-3xl shadow-[0_20px_60px_rgba(0,0,0,0.8)] transition-colors duration-300 group-hover:border-blue-400/25">
        <div className="grid grid-cols-1 md:grid-cols-[2fr_3fr_3fr]">

          {/* Title block */}
          <div className="px-6 py-6 border-b md:border-b-0 md:border-r border-white/[0.06] flex flex-col justify-center">
            <h2 className="text-2xl font-black tracking-tight text-white mb-2 drop-shadow-md">Simulation Setup</h2>
            <p className="text-xs font-medium leading-relaxed text-white/35">{copy.intro}</p>
          </div>

          {/* Selectors — animated DropdownMenu per setting */}
          {setupItems.map((item, i) => {
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
      </BentoCard>

      {/* ── Ego Car — the simulated vehicle the AI controls ───────────────── */}
      <BentoCard className="relative isolate group bg-neutral-950/90 backdrop-blur-2xl border border-white/[0.08] rounded-3xl shadow-[0_12px_40px_rgba(0,0,0,0.6)] overflow-hidden transition-colors duration-300 group-hover:border-red-400/25">
        <div className="grid grid-cols-1 md:grid-cols-3">

          <div className="px-6 py-6 border-b md:border-b-0 md:border-r border-white/[0.06] flex flex-col justify-center">
            <EyebrowLabel className="text-red-400 mb-2">Simulated Vehicle</EyebrowLabel>
            <h2 className="text-2xl font-black tracking-tight text-white mb-2 drop-shadow-md">Ego Car</h2>
            <p className="text-xs font-medium leading-relaxed text-white/35">
              {mode === 'qualifying'
                ? 'The diagnostic ego uses learned energy deployment; overtake intelligence is masked.'
                : 'The diagnostic ego uses learned energy and overtake policy. It is not a physically admitted car.'}
            </p>
          </div>

          <div className="relative min-h-[140px] flex items-center justify-center px-6 py-6 border-b md:border-b-0 md:border-r border-white/[0.06]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/haas_car2.png" alt="Ego car" className="w-full max-w-[320px] object-contain drop-shadow-[0_10px_30px_rgba(0,0,0,0.8)]" />
          </div>

          <div className="grid grid-cols-2 gap-3 p-5">
            <StatChip label="Mass prior" value="800 kg" />
            <StatChip label="Electric prior" value="20% additive" />
            <StatChip label="Usable store" value="5 MJ" />
            <StatChip label="Policy" value="Recurrent RL" />
          </div>
        </div>
      </BentoCard>

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
        <BentoCard className="relative isolate group h-full flex flex-col bg-neutral-950/90 backdrop-blur-2xl border border-white/[0.08] rounded-3xl overflow-hidden shadow-[0_12px_40px_rgba(0,0,0,0.6)] transition-colors duration-300 group-hover:border-blue-400/25">
          <div className="px-6 pt-6 pb-5 border-b border-white/[0.06]">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h2 className="text-3xl font-bold tracking-tight text-white truncate">
                  {selections.track.replace(' Grand Prix', '')}
                </h2>
                <p className="text-xs text-white/30 mt-0.5 truncate">{selections.track}</p>
              </div>
              <div className="flex items-center gap-2 mt-1 flex-shrink-0">
                <span className="text-[10px] font-medium text-white/25 tracking-widest uppercase">{circuit.country}</span>
                <div className="w-px h-3 bg-white/10" />
                <Flag size={11} className="text-white/25" />
                <span className="text-[10px] font-medium text-white/25">{circuit.laps === 'Qualifying only' ? circuit.laps : `${circuit.laps} laps`}</span>
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
        </BentoCard>

        {/* Driver Info Card — photo, bio and stats; "Profile" opens the full profile */}
        <TrailCard
          className="h-full max-w-none rounded-3xl border border-white/[0.08] shadow-[0_12px_40px_rgba(0,0,0,0.5)]"
          imageUrl={['3', '16', '44'].includes(selections.driver) ? `/${driverMeta.code}.png` : '/haas_car2.png'}
          imageClassName="object-top"
          eyebrow={`Car #${driverMeta.entry}`}
          title={CONFIG_ITEMS[1].options.find(o => o.value === selections.driver)?.label ?? selections.driver}
          subtitle={driverMeta.team}
          description={`Promoted neural vehicle profile fitted to ${driverMeta.name}'s source controls for ${driverMeta.team}.`}
          caption={copy.driverCaption(selections.track.replace(' Grand Prix', ''))}
          stats={[
            { label: 'Profile', value: `#${driverMeta.entry}` },
            { label: 'Code', value: driverMeta.code },
            { label: 'Nationality', value: driverMeta.nationality },
          ]}
          actionLabel="Profile"
          onAction={() => setShowDriverModal(true)}
        />
      </div>

      {/* ── Start Race ────────────────────────────────────────────────────── */}
      <BentoCard enableStars className="relative isolate group bg-neutral-950/90 backdrop-blur-2xl border border-white/[0.08] rounded-3xl px-6 py-5 shadow-[0_12px_40px_rgba(0,0,0,0.6)] flex flex-col sm:flex-row sm:items-center gap-4 transition-colors duration-300 group-hover:border-red-400/25">
        <div className="min-w-0 flex-1">
          <p className="text-xl font-semibold text-white truncate">
            {selections.track.replace(' Grand Prix', '')}
            <span className="text-white/25 font-normal"> · </span>
            {CONFIG_ITEMS[1].options.find(o => o.value === selections.driver)?.label}
          </p>
        </div>
        <SpinningBorderButton
          text={mode === 'qualifying' ? 'Open Qualifying Report' : 'Start Race'}
          onClick={() => onStart(selections.track, selections.driver, selections.policy)}
        />
      </BentoCard>

      {/* ── BOTTOM: 2026 Regs caption ─────────────────────────────────────── */}
      <p className="px-6 text-center text-xs text-blue-300/40 leading-relaxed">
        <span className="text-blue-300/80 font-semibold">2026 F1 Regulations</span>
        {' · '}
        Diagnostic prior: <span className="text-blue-300/70 font-semibold">20% additive electric wheel power</span>,{' '}
        <span className="text-blue-300/70 font-semibold">5 MJ</span> usable storage and a 5 MJ per-lap harvest cap.
        These are declared assumptions, not physical admission.
      </p>

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
                    src={['3', '16', '44'].includes(selections.driver) ? `/${driverMeta.code}.png` : '/haas_car2.png'}
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
                    {driverMeta.entry}
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
                      <EyebrowLabel className="mb-1">Driver code</EyebrowLabel>
                      <p className="text-sm font-semibold text-white">{driverMeta.code}</p>
                    </div>
                    <div>
                      <EyebrowLabel className="mb-1">Nationality</EyebrowLabel>
                      <p className="text-sm font-semibold text-white uppercase">{driverMeta.nationality}</p>
                    </div>
                  </div>

                  <EyebrowLabel className="mb-2">Telemetry Profile</EyebrowLabel>
                  <p className="text-sm text-white/60 leading-relaxed font-medium">
                    Promoted neural vehicle profile fitted to this driver&apos;s source controls. The report keeps its
                    diagnostic result separate from the policy-free 22-car reference field.
                  </p>
                </div>

                <GradientBlur />
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </BentoSection>
  );
}
