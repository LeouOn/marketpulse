import { useState, useEffect, useCallback } from 'react';

interface TrendAnalysis {
  symbol: string;
  timestamp: string;
  current_price: number;
  market_bias: string;
  trend_analysis: {
    [timeframe: string]: {
      direction: string;
      strength: string;
      momentum: number;
      price_change_pct: number;
      atr: number;
    };
  };
  key_levels: {
    support: Array<{ price: number; strength: number; confirmations: number }>;
    resistance: Array<{ price: number; strength: number; confirmations: number }>;
  };
  signals: Array<{
    type: string;
    direction: string;
    strength: string;
    reasoning: string;
    confidence: number;
  }>;
  timeframe_consensus: {
    bullish_timeframes: string[];
    bearish_timeframes: string[];
    neutral_timeframes: string[];
  };
  market_context?: {
    volatility_regime: string;
    volume_flow: any;
    correlation_strength?: number;
  };
}

export function useOHLCData(symbol: string) {
  const [data, setData] = useState<TrendAnalysis | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!symbol) return;

    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(`/api/market/trends/${symbol}`);
      const result = await response.json();

      if (result.success) {
        setData(result.data);
      } else {
        setError(result.error || 'Failed to fetch trend analysis');
      }
    } catch (err) {
      setError('Network error while fetching trend analysis');
    } finally {
      setIsLoading(false);
    }
  }, [symbol]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return {
    data,
    isLoading,
    error,
    refetch: fetchData
  };
}

export function useOHLCDashboard() {
  const [data, setData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/market/ohlc-dashboard');
      const result = await response.json();

      if (result.success) {
        setData(result.data);
      } else {
        setError(result.error || 'Failed to fetch OHLC dashboard');
      }
    } catch (err) {
      setError('Network error while fetching OHLC dashboard');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return {
    data,
    isLoading,
    error,
    refetch: fetchData
  };
}