'use client';

import { useEffect, useState } from 'react';
import { AppBar } from '@/ui-kit';
import { HealthIndicators } from './HealthIndicators';
import { checkAIServiceHealth } from '../lib/api';
import { AIServiceHealthStatus } from '../types';

export function Header() {
  const [health, setHealth] = useState<AIServiceHealthStatus>({
    vlm: 'checking',
    llm: 'checking',
    flux: 'checking',
    trellis: 'checking'
  });

  useEffect(() => {
    // Initial health check
    const performHealthCheck = async () => {
      const status = await checkAIServiceHealth();
      setHealth(status);
    };

    performHealthCheck();

    // Poll every 5 seconds
    const interval = setInterval(performHealthCheck, 5000);

    // Cleanup on unmount
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="transparent-header">
      <AppBar
        slotLeft={
          <div className="brand-lockup">Lingi7<span>Enrichment</span></div>
        }
        slotRight={
          <div className="system-health"><HealthIndicators health={health} /></div>
        }
      />
    </div>
  );
}
