'use client';

import { clsx } from 'clsx';

interface PriceCellProps {
  price: number;
  change?: number;
  changePct?: number;
  isCrypto?: boolean;
  className?: string;
}

function formatPrice(price: number, isCrypto?: boolean): string {
  if (isCrypto) return price.toLocaleString('en-US', { maximumFractionDigits: 0 });
  return price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatChange(change: number): string {
  const sign = change >= 0 ? '+' : '';
  return `${sign}${change.toFixed(2)}`;
}

function formatChangePct(pct: number): string {
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(2)}%`;
}

export function PriceCell({ price, change, changePct, isCrypto, className }: PriceCellProps) {
  const isPositive = change !== undefined && change >= 0;

  return (
    <div className={clsx('flex flex-col items-end', className)}>
      <span className="text-ink font-medium font-mono tabular-nums transition-colors duration-300">
        {formatPrice(price, isCrypto)}
      </span>

      {change !== undefined && (
        <span
          className={clsx(
            'text-sm font-mono tabular-nums transition-colors duration-300',
            isPositive ? 'text-pos' : 'text-neg'
          )}
        >
          {formatChange(change)}
        </span>
      )}

      {changePct !== undefined && (
        <span
          className={clsx(
            'h-4 px-1 inline-flex items-center text-[10.5px] font-mono tabular-nums transition-colors duration-300',
            isPositive ? 'bg-pos-dim text-pos' : 'bg-neg-dim text-neg'
          )}
        >
          {formatChangePct(changePct)}
        </span>
      )}
    </div>
  );
}