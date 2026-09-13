'use client';

import { useSearchParams } from 'next/navigation';
import { Dashboard } from '@/components/Dashboard';

export function DashboardWrapper() {
  const searchParams = useSearchParams();
  
  const track = searchParams.get('track') || 'Monaco Grand Prix';
  const driver = searchParams.get('driver') || 'VER';
  const policy = searchParams.get('policy') || 'learned';
  const year = searchParams.get('year') || '2026';

  return (
    <Dashboard 
      track={track} 
      driver={driver} 
      policy={policy} 
      year={year} 
    />
  );
}
