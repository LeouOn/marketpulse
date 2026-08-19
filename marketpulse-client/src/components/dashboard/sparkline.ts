// Pure helper used by CommandCenter (NQ hero) and CenterTabs (table row trend
// sparklines). Lives outside the component modules so both can import without
// cycles.

export function generateSparklineData(currentPrice: number, change: number, points = 12): number[] {
  const data: number[] = [];
  const previousPrice = currentPrice - change;
  const priceRange = Math.abs(change) || currentPrice * 0.01 || 1;

  for (let i = 0; i < points; i++) {
    const progress = i / (points - 1);
    const baseValue = previousPrice + change * progress;
    const noise = (Math.random() - 0.5) * priceRange * 0.2;
    data.push(baseValue + noise);
  }

  data[data.length - 1] = currentPrice;
  return data;
}

export function formatPrice(price: number, symbol: string): string {
  if (symbol.includes('-USD') || symbol === 'BTC' || symbol === 'ETH') {
    return `$${price.toLocaleString()}`;
  }
  return `$${price.toFixed(2)}`;
}

export function formatVolume(volume: number): string {
  if (volume >= 1e9) return `${(volume / 1e9).toFixed(1)}B`;
  if (volume >= 1e6) return `${(volume / 1e6).toFixed(1)}M`;
  if (volume >= 1e3) return `${(volume / 1e3).toFixed(1)}K`;
  return volume.toString();
}