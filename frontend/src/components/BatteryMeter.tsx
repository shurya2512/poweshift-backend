import React from 'react';

interface BatteryMeterProps {
  socMj: number; // 0 to 4.0
  p_kw: number;
  color: string;
  ghostSocMj?: number;
  label: string;
  isFinished?: boolean;
}

export function BatteryMeter({ socMj, p_kw, color, ghostSocMj, label, isFinished }: BatteryMeterProps) {
  const percentage = Math.max(0, Math.min(100, (socMj / 4.0) * 100));
  const ghostPercentage = ghostSocMj !== undefined ? Math.max(0, Math.min(100, (ghostSocMj / 4.0) * 100)) : undefined;
  
  const isDeploying = p_kw > 0;
  const isHarvesting = p_kw < 0;

  return (
    <div className="flex flex-col gap-1 w-full mt-4 relative">
      <div className="flex justify-between items-end text-xs font-mono font-semibold uppercase tracking-wider text-neutral-400">
        <span className="flex items-center gap-2">
          {label}
          {isFinished && <span className="text-[10px] px-1.5 py-0.5 bg-neutral-700 text-white rounded">FINISHED</span>}
        </span>
        <span className={isFinished ? 'text-white font-bold text-base' : 'text-white'}>
          {socMj.toFixed(2)} MJ
        </span>
      </div>
      
      <div className="relative h-6 w-full bg-neutral-900 border border-neutral-800 rounded-sm overflow-hidden">
        {/* Fill bar */}
        <div
          className={`absolute top-0 left-0 h-full transition-all duration-200 ease-linear flex items-center justify-end overflow-visible
            ${isDeploying && !isFinished ? 'animate-pulse' : ''}
          `}
          style={{ 
            width: `${percentage}%`, 
            backgroundColor: color,
            boxShadow: isDeploying && !isFinished ? `0 0 10px ${color}` : 'none'
          }}
        >
          {/* Edge glowing line */}
          {(!isFinished && (isDeploying || isHarvesting)) && (
            <div className={`absolute top-0 right-0 w-1 h-full bg-white shadow-[0_0_8px_white] ${isHarvesting ? 'bg-green-300' : ''}`}></div>
          )}
        </div>
        
        {/* Ghost tick */}
        {ghostPercentage !== undefined && (
          <div
            className="absolute top-0 h-full w-0.5 bg-white/50 z-10 transition-all duration-200"
            style={{ left: `${ghostPercentage}%` }}
          />
        )}
      </div>

      {/* Deployment / Harvest readout at the edge, floating */}
      {(!isFinished && Math.abs(p_kw) > 1) && (
        <div 
          className="absolute top-8 text-[10px] font-mono font-bold whitespace-nowrap z-20 transition-all duration-200 drop-shadow-md"
          style={{ 
            left: `calc(${percentage}% + 4px)`,
            color: isDeploying ? '#ef4444' : '#10b981' // red for drain, green for harvest
          }}
        >
          {isDeploying ? '▼' : '▲'} {Math.abs(p_kw).toFixed(0)} kW
        </div>
      )}

      <div className="flex justify-between text-[10px] font-mono text-neutral-500 mt-2">
        <span>0.0 MJ</span>
        <span>4.0 MJ</span>
      </div>
    </div>
  );
}
