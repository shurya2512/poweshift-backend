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

  return (
    <div className="w-full aspect-video bg-neutral-900 rounded p-4 relative overflow-hidden">
      <svg
        className="w-full h-full"
        viewBox={`${minX} ${minY} ${width} ${height}`}
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Track Outline */}
        <path
          d={pathData}
          fill="none"
          stroke="#333"
          strokeWidth="20"
          strokeLinejoin="round"
        />

        {/* Car Marker */}
        {carState && (
          <g className="transition-all duration-200 ease-linear hover:opacity-80 cursor-pointer">
            <circle
              cx={carState.x}
              cy={carState.y}
              r="30"
              fill={color}
              style={{
                filter: `drop-shadow(0 0 10px ${color})`,
              }}
            />
            <title>{`Speed: ${carState.v.toFixed(1)} km/h | Power: ${carState.p_kw.toFixed(1)} kW | Battery: ${carState.soc.toFixed(2)} MJ`}</title>
          </g>
        )}
      </svg>
      
      {/* Overlay Stats */}
      {carState && (
        <div className="absolute top-4 left-4 bg-black/80 p-3 rounded border border-neutral-800 font-mono text-sm shadow-xl backdrop-blur-sm z-10 transition-colors hover:border-neutral-600">
          <div className="flex justify-between gap-4 border-b border-neutral-800 pb-1 mb-1">
            <span className="text-neutral-500 text-xs">SPEED</span>
            <span className="text-white font-bold">{Math.round(carState.v)} km/h</span>
          </div>
          <div className="flex justify-between gap-4 border-b border-neutral-800 pb-1 mb-1">
            <span className="text-neutral-500 text-xs">POWER</span>
            <span className={carState.p_kw > 0 ? 'text-red-400 font-bold' : carState.p_kw < 0 ? 'text-green-400 font-bold' : 'text-neutral-400'}>
              {Math.abs(carState.p_kw) > 0 ? (carState.p_kw > 0 ? '▼ ' : '▲ ') : ''}{Math.round(Math.abs(carState.p_kw))} kW
            </span>
          </div>
          <div className="flex justify-between gap-4">
            <span className="text-neutral-500 text-xs">BATTERY</span>
            <span className="text-white">{carState.soc.toFixed(2)} MJ</span>
          </div>
        </div>
      )}
    </div>
  );
}
