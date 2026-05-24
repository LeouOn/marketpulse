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

export interface MarketSymbolData {
  price: number;
  change: number;
  change_pct: number;
  volume: number;
  timestamp: string;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
}

export interface DashboardData {
  timestamp: string;
  marketBias: string;
  volatilityRegime: string;
  symbols: Record<string, MarketSymbolData>;
  volumeFlow: {
    total_volume_60min: number;
    symbols_tracked: number;
  };
  aiAnalysis?: string;
  dataSource?: string;
  market_session?: string;
  sector_performance?: Record<string, number>;
  dataQuality?: string;
  qualityIssues?: string[];
  synthetic?: boolean;
  freshnessStatus?: string;
  dataAgeSeconds?: number;
  screener_summary?: any;
  breadth?: MarketBreadth;
}

export interface MacroData {
  [symbol: string]: MarketSymbolData | string | Record<string, number> | undefined;
  market_session?: string;
  economic_sentiment?: string;
  risk_appetite?: string;
  sector_performance?: Record<string, number>;
}

export interface MarketBreadth {
  nyse_advancing: number;
  nyse_declining: number;
  nyse_unchanged: number;
  nyse_ad_ratio: number;
  nyse_net_ad: number;
  nasdaq_advancing: number;
  nasdaq_declining: number;
  nasdaq_unchanged: number;
  nasdaq_ad_ratio: number;
  nasdaq_net_ad: number;
  interpretation: string;
  new_highs: number;
  new_lows: number;
  hl_ratio: number;
  net_hl: number;
  tick_value: number;
  tick_30min_avg: number;
  tick_4hr_avg: number;
  nyse_vold: number;
  nasdaq_vold: number;
  total_vold: number;
  mcclellan_oscillator: number;
  mcclellan_summation: number;
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