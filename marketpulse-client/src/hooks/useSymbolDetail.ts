'use client';

import { useQuery } from '@tanstack/react-query';
import { marketPulseAPI } from '@/lib/api';
import { marketKeys } from './useMarketData';

export function useSymbolDetail(symbol: string) {
  return useQuery({
    queryKey: marketKeys.symbol(symbol),
    queryFn: () => marketPulseAPI.getSymbolDetail(symbol),
    enabled: !!symbol,
    staleTime: 5 * 60 * 1000,
    retry: 2,
  });
}

export function useSymbolStats(symbol: string) {
  return useQuery({
    queryKey: marketKeys.stats(symbol),
    queryFn: () => marketPulseAPI.getSymbolStats(symbol),
    enabled: !!symbol,
    staleTime: 5 * 60 * 1000,
    retry: 2,
  });
}

export function use52WRange(symbol: string) {
  return useQuery({
    queryKey: [...marketKeys.stats(symbol), '52w'],
    queryFn: () => marketPulseAPI.get52WRange(symbol),
    enabled: !!symbol,
    staleTime: 5 * 60 * 1000,
    retry: 2,
  });
}

export function useHistoricalOHLC(symbol: string, timeframe: string = '1d', period: string = '1mo') {
  return useQuery({
    queryKey: marketKeys.historical(symbol, timeframe),
    queryFn: () => marketPulseAPI.getHistoricalFromDB(symbol, timeframe, period),
    enabled: !!symbol,
    staleTime: 5 * 60 * 1000,
    retry: 2,
  });
}
