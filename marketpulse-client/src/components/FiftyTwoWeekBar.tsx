'use client';

import { clsx } from 'clsx';

interface FiftyTwoWeekBarProps {
  currentPrice: number;
  high52w: number;
  low52w: number;
  showLabels?: boolean;
  className?: string;
}

function formatNumber(n: number): string {
  return n.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function getFillClass(pct: number): string {
  if (pct < 0.3) return 'bg-neg';
  if (pct <= 0.7) return 'bg-sel';
  return 'bg-pos';
}

export function FiftyTwoWeekBar({
  currentPrice,
  high52w,
  low52w,
  showLabels = false,
  className,
}: FiftyTwoWeekBarProps) {
  const pct =
    high52w === low52w
      ? 0.5
      : Math.max(0, Math.min(1, (currentPrice - low52w) / (high52w - low52w)));

  return (
    <div className={clsx('w-full', className)}>
      <div className="h-1 bg-surface-raised w-full relative">
        <div
          className={clsx('absolute left-0 top-0 h-full', getFillClass(pct))}
          style={{ width: `${pct * 100}%` }}
        />
        <div
          className="absolute top-1/2 -translate-y-1/2 w-1.5 h-1.5 bg-ink"
          style={{ left: `${pct * 100}%`, transform: 'translate(-50%, -50%)' }}
        />
      </div>

      {showLabels && (
        <div className="flex justify-between mt-1 text-[10px] text-ink-muted font-mono tabular-nums">
          <span>{formatNumber(low52w)}</span>
          <span>{formatNumber(high52w)}</span>
        </div>
      )}
    </div>
  );
}