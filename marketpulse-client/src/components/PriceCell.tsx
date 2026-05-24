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
      <span className="text-white font-medium transition-colors duration-300">
        {formatPrice(price, isCrypto)}
      </span>

      {change !== undefined && (
        <span
          className={clsx('text-sm transition-colors duration-300', {
            'text-emerald-400': isPositive,
            'text-red-400': !isPositive,
          })}
        >
          {formatChange(change)}
        </span>
      )}

      {changePct !== undefined && (
        <span
          className={clsx(
            'text-xs px-1.5 py-0.5 rounded font-medium transition-colors duration-300',
            {
              'bg-emerald-500/20 text-emerald-400': isPositive,
              'bg-red-500/20 text-red-400': !isPositive,
            }
          )}
        >
          {formatChangePct(changePct)}
        </span>
      )}
    </div>
  );
}
