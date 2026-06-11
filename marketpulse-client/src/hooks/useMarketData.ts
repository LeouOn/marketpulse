import { useQuery } from '@tanstack/react-query';
import { marketPulseAPI } from '@/lib/api';

// Query keys for React Query. Re-used by tests and other hooks.
export const marketKeys = {
  all: ['market'] as const,
  dashboard: () => [...marketKeys.all, 'dashboard'] as const,
  macro: () => [...marketKeys.all, 'macro'] as const,
  ai: () => [...marketKeys.all, 'ai'] as const,
  screener: (type: string) => [...marketKeys.all, 'screener', type] as const,
  symbol: (symbol: string) => [...marketKeys.all, 'symbol', symbol] as const,
  stats: (symbol: string) => [...marketKeys.all, 'stats', symbol] as const,
  search: (query: string) => [...marketKeys.all, 'search', query] as const,
  historical: (symbol: string, tf: string) =>
    [...marketKeys.all, 'historical', symbol, tf] as const,
  ohlcAnalysis: (symbol: string) => [...marketKeys.all, 'ohlcAnalysis', symbol] as const,
};

export function useOHLCAnalysis(symbol: string) {
  return useQuery({
    queryKey: marketKeys.ohlcAnalysis(symbol),
    queryFn: () => marketPulseAPI.getOHLCAnalysis(symbol),
    staleTime: 60000,
    retry: 2,
    enabled: !!symbol,
  });
}

export function useTrendAnalysis(symbol: string) {
  return useQuery({
    queryKey: [...marketKeys.all, 'trends', symbol],
    queryFn: () => marketPulseAPI.getTrendAnalysis(symbol),
    staleTime: 60000,
    retry: 2,
    enabled: !!symbol,
  });
}
