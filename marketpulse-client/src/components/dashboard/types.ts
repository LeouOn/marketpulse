// Local type shapes shared across the dashboard/ modules.
// The brief forbids touching src/types/market.ts, so the
// `MarketData` shape used by the legacy dashboard view (price +
// change + change_pct + volume + symbol + timestamp) is declared
// here and imported by the composition modules that need it.

export interface MarketData {
  symbol: string;
  price: number;
  change: number;
  change_pct: number;
  volume: number;
  timestamp: string;
}

export type MarketRegime = 'favorable' | 'mixed' | 'avoid';

export interface SessionInfo {
  status: string;
  countdown: string;
  time: string;
}