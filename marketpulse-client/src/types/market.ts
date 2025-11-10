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