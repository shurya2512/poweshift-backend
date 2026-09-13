'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { SetupScreen } from '@/components/SetupScreen';

export default function SetupQualifyingPage() {
  const router = useRouter();

  const handleStart = (track: string, profile: string) => {
    const params = new URLSearchParams({ mode: 'qualifying', track, profile });
    router.push(`/report?${params.toString()}`);
  };

  return <SetupScreen mode="qualifying" onStart={handleStart} />;
}
