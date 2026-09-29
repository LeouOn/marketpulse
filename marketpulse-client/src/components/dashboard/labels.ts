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

// Fallback display names; the live value from /market/macro
// (`instrument` per series, T7a) wins wherever buildRows finds it.
// GC is the COMEX gold futures contract (GC=F) and DXY is the ICE dollar
// index (DX-Y.NYB) — neither is spot, and gold is NOT the GLD ETF here.
export const MACRO_LABELS: Record<string, string> = {
  DXY: 'US Dollar (ICE Index)',
  TNX: '10Y Treasury',
  CL: 'Crude Oil (WTI)',
  GC: 'Gold (GC=F futures)',
  BTC: 'Bitcoin',
  ETH: 'Ethereum',
  SOL: 'Solana',
  XRP: 'Ripple',
};

export const MACRO_SYMBOLS = ['DXY', 'TNX', 'CL', 'GC', 'BTC', 'ETH', 'SOL', 'XRP'];

/**
 * Explain a withheld /market/macro response, if that is what we got.
 *
 * The backend returns HTTP 200 with `{success: false, error, timestamp}`
 * when the live source failed and MARKETPULSE_ALLOW_MOCK is not set (T7a).
 * apiFetch only throws on HTTP errors, so that envelope flows through as
 * if it were data and the macro section would silently disappear. This
 * helper detects the envelope and returns the backend's reason for the
 * UI to render instead of nothing.
 */
export function macroUnavailableReason(data: unknown): string | null {
  if (data == null || typeof data !== 'object') return null;
  const envelope = data as { success?: unknown; error?: unknown };
  if (envelope.success === false && typeof envelope.error === 'string' && envelope.error) {
    return envelope.error;
  }
  return null;
}
