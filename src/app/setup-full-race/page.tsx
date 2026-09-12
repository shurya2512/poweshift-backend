'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { SetupScreen } from '@/components/SetupScreen';

export default function SetupFullRacePage() {
  const router = useRouter();

  // The full race still runs on its fixture, so the choices made here are not carried
  // into the URL — a query string the page ignores would claim they were.
  const handleStart = () => router.push('/full-race');

  return <SetupScreen mode="full-race" onStart={handleStart} />;
}
