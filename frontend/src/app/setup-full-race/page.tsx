'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { SetupScreen } from '@/components/SetupScreen';

export default function SetupFullRacePage() {
  const router = useRouter();

  const handleStart = (track: string, profile: string) => {
    const params = new URLSearchParams({ track, profile });
    router.push(`/full-race?${params.toString()}`);
  };

  return <SetupScreen mode="full-race" onStart={handleStart} />;
}
