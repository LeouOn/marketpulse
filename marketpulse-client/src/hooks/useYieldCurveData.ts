import { useQuery } from '@tanstack/react-query';
import { marketPulseAPI } from '../lib/api';
import type {
  YieldCurveSnapshot,
  YieldCurveHistoryPoint,
  YieldCurveAlert,
  YieldCurveConfig,
} from '../types/market';

export function useYieldCurveCurrent() {
  return useQuery<YieldCurveSnapshot | null>({
    queryKey: ['yield-curve', 'current'],
    queryFn: () => marketPulseAPI.getYieldCurve(),
    refetchInterval: 60_000,        // 1 min (data only changes daily but cheap)
    staleTime: 30_000,
  });
}

export function useYieldCurveHistory(days = 90) {
  return useQuery<YieldCurveHistoryPoint[]>({
    queryKey: ['yield-curve', 'history', days],
    queryFn: () => marketPulseAPI.getYieldCurveHistory(days),
    refetchInterval: 5 * 60_000,    // 5 min
    staleTime: 60_000,
  });
}

export function useYieldCurveAlerts(days = 30) {
  return useQuery<YieldCurveAlert[]>({
    queryKey: ['yield-curve', 'alerts', days],
    queryFn: () => marketPulseAPI.getYieldCurveAlerts(days),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}

export function useYieldCurveConfig() {
  return useQuery<YieldCurveConfig | null>({
    queryKey: ['yield-curve', 'config'],
    queryFn: () => marketPulseAPI.getYieldCurveConfig(),
    staleTime: 10 * 60_000,         // 10 min
  });
}