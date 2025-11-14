'use client';

import { useState } from 'react';
import { EnhancedMarketDashboard } from './EnhancedMarketDashboard';
import { useDashboardData } from '@/hooks/useMarketData';

export function MarketDashboard() {
  const { data, isLoading, error, refetch } = useDashboardData();
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  const handleRefresh = () => {
    setLastUpdate(new Date());
    refetch();
  };

  return (
    <EnhancedMarketDashboard
      data={data || null}
      loading={isLoading}
      error={typeof error === 'string' ? error : error?.message || null}
      onRefresh={handleRefresh}
      lastUpdate={lastUpdate}
    />
  );
}