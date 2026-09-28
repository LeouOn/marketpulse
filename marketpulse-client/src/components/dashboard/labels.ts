// Display labels for the symbols we render in the dashboard Overview tab.
// Lives in its own module so ThreeColumnDashboard stays under 120 LOC.

export const INDEX_LABELS: Record<string, string> = {
  SPY: 'S&P 500 (SPY)',
  spy: 'S&P 500 (SPY)',
  QQQ: 'NASDAQ (QQQ)',
  qqq: 'NASDAQ (QQQ)',
  VIX: 'Volatility (VIX)',
  vix: 'Volatility (VIX)',
  '^VIX': 'Volatility (VIX)',
};

export const MACRO_LABELS: Record<string, string> = {
  DXY: 'US Dollar Index',
  TNX: '10Y Treasury',
  CL: 'Crude Oil (WTI)',
  GC: 'Gold futures',
  BTC: 'Bitcoin',
  ETH: 'Ethereum',
  SOL: 'Solana',
  XRP: 'Ripple',
};

export const MACRO_SYMBOLS = ['DXY', 'TNX', 'CL', 'GC', 'BTC', 'ETH', 'SOL', 'XRP'];