import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, useEffect } from 'react';
import { marketPulseAPI } from '@/lib/api';
import { DashboardData, MacroData } from '@/types/market';

// Query keys for React Query
export const marketKeys = {
  all: ['market'] as const,
  dashboard: () => [...marketKeys.all, 'dashboard'] as const,
  macro: () => [...marketKeys.all, 'macro'] as const,
  ai: () => [...marketKeys.all, 'ai'] as const,
  screener: (type: string) => [...marketKeys.all, 'screener', type] as const,
  symbol: (symbol: string) => [...marketKeys.all, 'symbol', symbol] as const,
  stats: (symbol: string) => [...marketKeys.all, 'stats', symbol] as const,
  search: (query: string) => [...marketKeys.all, 'search', query] as const,
  historical: (symbol: string, tf: string) => [...marketKeys.all, 'historical', symbol, tf] as const,
  breadth: () => [...marketKeys.all, 'breadth'] as const,
  ohlcAnalysis: (symbol: string) => [...marketKeys.all, 'ohlcAnalysis', symbol] as const,
};

// Hook for dashboard data
export function useDashboardData(refreshInterval = 60000) {
  const queryClient = useQueryClient();

  const result = useQuery({
    queryKey: marketKeys.dashboard(),
    queryFn: () => marketPulseAPI.getDashboardData(),
    refetchInterval: refreshInterval,
    retry: 3,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
    staleTime: 30000,
  });

  // Manual refresh function
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: marketKeys.dashboard() });
  };

  return {
    ...result,
    refresh,
  };
}

// Hook for macro data
export function useMacroData(refreshInterval = 120000) {
  const queryClient = useQueryClient();

  const result = useQuery({
    queryKey: marketKeys.macro(),
    queryFn: () => marketPulseAPI.getMacroData(),
    refetchInterval: refreshInterval,
    retry: 3,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
    staleTime: 60000,
  });

  // Manual refresh function
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: marketKeys.macro() });
  };

  return {
    ...result,
    refresh,
  };
}

// Hook for AI analysis
export function useAIAnalysis() {
  const queryClient = useQueryClient();

  const result = useQuery({
    queryKey: marketKeys.ai(),
    queryFn: () => marketPulseAPI.getAIAnalysis(),
    refetchInterval: 300000, // 5 minutes
    retry: 2,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 15000),
    staleTime: 120000, // 2 minutes
  });

  // Manual refresh function
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: marketKeys.ai() });
  };

  return {
    ...result,
    refresh,
  };
}

// Hook for market breadth data
export function useBreadthData(refreshInterval = 120000) {
  const queryClient = useQueryClient();

  const result = useQuery({
    queryKey: marketKeys.breadth(),
    queryFn: () => marketPulseAPI.getMarketBreadth(),
    refetchInterval: refreshInterval,
    retry: 3,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
    staleTime: 60000,
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: marketKeys.breadth() });
  };

  return {
    ...result,
    refresh,
  };
}

// Hook for real-time updates
export function useRealTimeMarketData() {
  const [isConnected, setIsConnected] = useState(false);
  const dashboard = useDashboardData(15000); // 15 seconds
  const macro = useMacroData(30000); // 30 seconds

  useEffect(() => {
    // Simulate connection status
    setIsConnected(!dashboard.isLoading && !macro.isLoading);
  }, [dashboard.isLoading, macro.isLoading]);

  return {
    isConnected,
    dashboard,
    macro,
    isLoading: dashboard.isLoading || macro.isLoading,
    hasError: dashboard.isError || macro.isError,
  };
}

export function useOHLCAnalysis(symbol: string) {
  return useQuery({
    queryKey: [...marketKeys.all, 'ohlc', symbol],
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