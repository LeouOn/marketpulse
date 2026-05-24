'use client';

import { useQuery } from '@tanstack/react-query';
import { marketPulseAPI } from '@/lib/api';
import { marketKeys } from './useMarketData';

export function useScreener(type: 'gainers' | 'losers' | 'most_active') {
  return useQuery({
    queryKey: marketKeys.screener(type),
    queryFn: () => marketPulseAPI.getScreenerData(type),
    refetchInterval: 300000,
    staleTime: 120000,
    retry: 2,
    placeholderData: (previousData) => previousData,
  });
}
