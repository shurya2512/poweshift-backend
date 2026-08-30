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
          stroke="#666"
          strokeWidth="4"
          vectorEffect="non-scaling-stroke"
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {/* Car Marker */}
        {carState && (
          <g className="transition-all duration-200 ease-linear hover:opacity-80 cursor-pointer">
            <circle
              cx={carState.x}
              cy={carState.y}
              r={width * 0.015} // Scale dot radius relative to track size
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
        <div className="absolute top-4 left-4 bg-[#0a0a0a]/90 p-3 rounded-md border border-neutral-800 font-mono shadow-xl z-10 transition-colors hover:border-neutral-600 min-w-[200px] backdrop-blur-sm">
          <div className="grid grid-cols-[auto_20px_1fr_40px] items-center text-[13px]">
            
            {/* SPEED */}
            <div className="text-neutral-500 text-xs tracking-wider">SPEED</div>
            <div></div>
            <div className="text-white font-bold text-right pr-2 text-[15px]">{Math.round(carState.v)}</div>
            <div className="text-white font-bold">km/h</div>
            
            <div className="col-span-4 border-b border-neutral-800/80 my-2"></div>

            {/* POWER */}
            <div className="text-neutral-500 text-xs tracking-wider">POWER</div>
            <div className={`text-right text-[11px] ${carState.p_kw > 0 ? 'text-red-500' : carState.p_kw < 0 ? 'text-[#00e676]' : ''}`}>
              {Math.abs(carState.p_kw) > 1 ? (carState.p_kw > 0 ? '▼' : '▲') : ''}
            </div>
            <div className={`font-bold text-right pr-2 text-[15px] ${carState.p_kw > 0 ? 'text-red-500' : carState.p_kw < 0 ? 'text-[#00e676]' : 'text-neutral-500'}`}>
              {Math.round(Math.abs(carState.p_kw))}
            </div>
            <div className={`font-bold ${carState.p_kw > 0 ? 'text-red-500' : carState.p_kw < 0 ? 'text-[#00e676]' : 'text-neutral-500'}`}>kW</div>
            
            <div className="col-span-4 border-b border-neutral-800/80 my-2"></div>

            {/* BATTERY */}
            <div className="text-neutral-500 text-xs tracking-wider">BATTERY</div>
            <div></div>
            <div className="text-neutral-200 text-right pr-2 text-[15px]">{carState.soc.toFixed(2)}</div>
            <div className="text-neutral-200">MJ</div>

          </div>
        </div>
      )}
    </div>
  );
}
