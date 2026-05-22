export interface MarketSymbol {
  symbol: string;
  price: number;
  change: number;
  changePct: number;
  volume: number;
  timestamp: string;
}

export interface MarketInternals {
  spy?: MarketSymbol;
  qqq?: MarketSymbol;
  vix?: MarketSymbol;
  volumeFlow: {
    totalVolume60min: number;
    symbolsTracked: number;
    timestamp: string;
  };
}

export interface DashboardData {
  timestamp: string;
  marketBias: 'BULLISH' | 'BEARISH' | 'MIXED' | 'NEUTRAL';
  volatilityRegime: 'EXTREME' | 'HIGH' | 'NORMAL' | 'LOW' | 'UNKNOWN';
  symbols: {
    spy?: MarketSymbol;
    qqq?: MarketSymbol;
    vix?: MarketSymbol;
  };
  volumeFlow: {
    totalVolume60min: number;
    symbolsTracked: number;
  };
  aiAnalysis?: string;
  dataSource?: string;
}

export interface MacroData {
  DXY: MarketSymbol;
  TNX: MarketSymbol;
  CLF: MarketSymbol;
  GC: MarketSymbol;
  BTC: MarketSymbol;
  ETH: MarketSymbol;
  market_session: string;
  economic_sentiment: string;
  sector_performance: Record<string, number>;
  risk_appetite: string;
}

export interface PriceData {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface ChartData {
  time: string;
  value: number;
}

export interface ScreenerResult {
  rank: number;
  symbol: string;
  name?: string;
  price: number;
  change_pct: number;
  volume: number;
  relative_volume?: number;
  high_52w?: number;
  low_52w?: number;
  pct_from_52w_high?: number;
  market_cap?: number;
}

export interface SymbolProfile {
  symbol: string;
  name?: string;
  asset_type?: string;
  exchange?: string;
  sector?: string;
  industry?: string;
  market_cap?: number;
  pe_ratio?: number;
  currency?: string;
  yahoo_symbol?: string;
}

export interface SymbolStats {
  date: string;
  high_52w?: number;
  low_52w?: number;
  pct_from_52w_high?: number;
  pct_from_52w_low?: number;
  sma_20?: number;
  sma_50?: number;
  sma_200?: number;
  atr_14?: number;
  avg_volume_20d?: number;
  avg_volume_50d?: number;
  prev_close?: number;
}

export interface FiftyTwoWeekRange {
  symbol: string;
  current_price: number;
  high_52w: number;
  low_52w: number;
  pct_from_high: number;
  pct_from_low: number;
  high_date?: string;
  low_date?: string;
}

export interface OHLCVBar {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}