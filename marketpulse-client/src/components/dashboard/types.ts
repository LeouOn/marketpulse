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
  // Provenance (T7a) — optional so index/dashboard payloads without them
  // still typecheck.
  instrument?: string;
  is_proxy?: boolean;
  source?: string;
}

export type MarketRegime = 'favorable' | 'mixed' | 'avoid';

export interface SessionInfo {
  status: string;
  countdown: string;
  time: string;
}