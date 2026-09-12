'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { SetupScreen } from '@/components/SetupScreen';

export default function SetupQualifyingPage() {
  const router = useRouter();

  const handleStart = (track: string, driver: string, policy: string) => {
    const params = new URLSearchParams({ track, driver, policy, year: '2026' });
    router.push(`/race?${params.toString()}`);
  };

  return <SetupScreen mode="qualifying" onStart={handleStart} />;
}
