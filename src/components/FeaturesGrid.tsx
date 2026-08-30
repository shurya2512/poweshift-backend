"use client";

import React, { useState } from 'react';
import { Cpu, Zap, Trophy, X, BrainCircuit } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const featureData = [
  {
    id: 'ml',
    title: 'Machine Learning',
    description: 'A HistGradientBoostingClassifier dynamically evaluates the track and telemetry to predict optimal battery deployment.',
    icon: Cpu,
    color: 'text-blue-500',
    borderColor: 'hover:border-blue-500/50',
    shadowColor: 'shadow-blue-500/20'
  },
  {
    id: 'dp',
    title: 'Dynamic Programming',
    description: 'The theoretical global optimal oracle. Calculates the perfect energy deployment for any lap with O(N²) complexity, providing flawless training data for our AI.',
    icon: BrainCircuit,
    color: 'text-purple-500',
    borderColor: 'hover:border-purple-500/50',
    shadowColor: 'shadow-purple-500/20'
  },
  {
    id: 'physics',
    title: 'Real Physics Engine',
    description: 'Every lap is simulated in real-time, accounting for 798kg mass, aero drag, tyre traction limits, and the 4MJ battery cap.',
    icon: Zap,
    color: 'text-orange-400',
    borderColor: 'hover:border-orange-400/50',
    shadowColor: 'shadow-orange-400/20'
  },
  {
    id: 'testing',
    title: 'Adversarial Testing',
    description: 'The AI is tested strictly on held-out circuits it has never seen, racing against the actual historical team telemetry.',
    icon: Trophy,
    color: 'text-red-500',
    borderColor: 'hover:border-red-500/50',
    shadowColor: 'shadow-red-500/20'
  }
];

export default function FeaturesGrid() {
  const [selectedFeature, setSelectedFeature] = useState<typeof featureData[0] | null>(null);

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8 mt-12 text-left w-full border-t border-neutral-800/60 pt-16 pointer-events-auto z-10 relative">
        {featureData.map((feature) => (
          <div 
            key={feature.id}
            onClick={() => setSelectedFeature(feature)}
            className={`bg-[#0a0a0a]/80 backdrop-blur-md p-6 rounded-xl border border-neutral-800 transition-all cursor-pointer ${feature.borderColor} hover:shadow-lg ${feature.shadowColor} hover:-translate-y-1`}
          >
            <feature.icon className={`${feature.color} mb-4`} size={32} />
            <h3 className="text-lg font-bold mb-2">{feature.title}</h3>
            <p className="text-neutral-500 text-sm">{feature.description}</p>
          </div>
        ))}
      </div>

      <AnimatePresence>
        {selectedFeature && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[99999] flex items-center justify-center p-4 bg-black/40 backdrop-blur-md pointer-events-auto"
            onClick={() => setSelectedFeature(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              transition={{ type: "spring", duration: 0.5 }}
              onClick={(e) => e.stopPropagation()}
              className="w-full max-w-md bg-neutral-950/40 backdrop-blur-2xl rounded-[28px] overflow-hidden border border-white/15 p-8 shadow-[0_16px_40px_rgba(0,0,0,0.6)] relative"
            >
              <button 
                onClick={() => setSelectedFeature(null)}
                className="absolute top-4 right-4 p-2 rounded-full bg-white/10 hover:bg-white/20 border border-white/10 transition-colors text-white/70 hover:text-white"
              >
                <X size={20} />
              </button>
              
              <selectedFeature.icon className={`${selectedFeature.color} mb-6`} size={48} />
              <h2 className="text-2xl font-bold mb-4 text-white">{selectedFeature.title}</h2>
              <p className="text-neutral-300 leading-relaxed text-lg">
                {selectedFeature.description}
              </p>
              
              <div className="mt-8 pt-6 border-t border-white/10 flex justify-end">
                <button 
                  onClick={() => setSelectedFeature(null)}
                  className="px-6 py-2.5 rounded-full bg-white text-black font-semibold tracking-wide hover:bg-neutral-200 transition-colors"
                >
                  Got it
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
