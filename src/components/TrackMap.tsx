import React from 'react';
import { TrackGeometry, CarState } from '../lib/types';

interface TrackMapProps {
  geometry: TrackGeometry | null;
  carState: CarState | null;
  color: string;
}

export function TrackMap({ geometry, carState, color }: TrackMapProps) {
  if (!geometry) {
    return (
      <div className="w-full aspect-video bg-neutral-900 rounded flex items-center justify-center text-neutral-500">
        Waiting for track data...
      </div>
    );
  }

  // Calculate bounding box to set viewBox
  const minX = Math.min(...geometry.x) - 100;
  const maxX = Math.max(...geometry.x) + 100;
  const minY = Math.min(...geometry.y) - 100;
  const maxY = Math.max(...geometry.y) + 100;
  const width = maxX - minX;
  const height = maxY - minY;

    // Generate path string for the track outline
  const points = geometry.x.map((x, i) => `${x},${geometry.y[i]}`).join(' L ');
  const pathData = `M ${points} Z`;

  const scale = Math.max(width, height);

  return (
    <div className="flex flex-col gap-3">
      <div className="w-full aspect-video bg-transparent rounded p-0 relative overflow-hidden flex items-center justify-center">
        <svg
          className="w-[95%] h-[95%]"
          viewBox={`${minX} ${minY} ${width} ${height}`}
          preserveAspectRatio="xMidYMid meet"
          style={{ filter: 'drop-shadow(0 0 10px rgba(255,255,255,0.1))' }}
        >
          {/* Track Outline Background */}
          <path
            d={pathData}
            fill="none"
            stroke="rgba(59,130,246,0.15)"
            strokeWidth="30"
            vectorEffect="non-scaling-stroke"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          {/* Track Outline Highlight */}
          <path
            d={pathData}
            fill="none"
            stroke="rgba(255,255,255,0.4)"
            strokeWidth="6"
            vectorEffect="non-scaling-stroke"
            strokeLinejoin="round"
            strokeLinecap="round"
          />

          {/* Car Marker */}
          {carState && (
            <g className="transition-all duration-200 ease-linear cursor-pointer pointer-events-none">
              {/* Outer faint glow */}
              <circle
                cx={carState.x}
                cy={carState.y}
                r={scale * 0.03}
                fill={color}
                opacity="0.2"
                className="animate-pulse"
              />
              {/* Outer glow */}
              <circle
                cx={carState.x}
                cy={carState.y}
                r={scale * 0.015}
                fill={color}
                style={{
                  filter: `drop-shadow(0 0 10px ${color}) drop-shadow(0 0 20px ${color})`,
                }}
              />
              {/* Solid core */}
              <circle
                cx={carState.x}
                cy={carState.y}
                r={scale * 0.0075}
                fill="#fff"
              />
            </g>
          )}
        </svg>
      </div>
      
      {/* Inline Stats (Replaces absolute overlay) */}
      {carState && (
        <div className="flex justify-between items-center bg-white/[0.03] border border-white/[0.05] rounded-2xl p-4 px-6">
          <div className="flex flex-col">
            <span className="text-[10px] text-white/40 uppercase tracking-widest font-bold mb-1">Speed</span>
            <div className="flex items-baseline gap-1.5">
              <span className="text-white font-bold text-xl leading-none">{Math.round(carState.v)}</span>
              <span className="text-xs text-white/50 font-medium">km/h</span>
            </div>
          </div>
          
          <div className="w-px h-8 bg-white/10" />

          <div className="flex flex-col">
            <span className="text-[10px] text-white/40 uppercase tracking-widest font-bold mb-1">Power</span>
            <div className="flex items-baseline gap-1.5">
              <span className={`text-[10px] ${carState.p_kw > 0 ? 'text-red-400' : carState.p_kw < 0 ? 'text-green-400' : ''}`}>
                {Math.abs(carState.p_kw) > 1 ? (carState.p_kw > 0 ? '▼' : '▲') : ''}
              </span>
              <span className={`font-bold text-xl leading-none ${carState.p_kw > 0 ? 'text-red-400' : carState.p_kw < 0 ? 'text-green-400' : 'text-white'}`}>
                {Math.round(Math.abs(carState.p_kw))}
              </span>
              <span className="text-xs text-white/50 font-medium">kW</span>
            </div>
          </div>

          <div className="w-px h-8 bg-white/10" />

          <div className="flex flex-col">
            <span className="text-[10px] text-white/40 uppercase tracking-widest font-bold mb-1">Battery</span>
            <div className="flex items-baseline gap-1.5">
              <span className="text-white font-bold text-xl leading-none">{carState.soc.toFixed(2)}</span>
              <span className="text-xs text-white/50 font-medium">MJ</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
