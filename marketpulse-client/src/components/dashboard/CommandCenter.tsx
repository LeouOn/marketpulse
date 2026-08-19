'use client';

import { Target, Clock, Activity } from 'lucide-react';
import { Sparkline } from '@/components/ui/Sparkline';
import type { MarketBreadth } from '@/types/market';
import type { MarketData, MarketRegime, SessionInfo } from './types';
import { StatTile } from './StatTile';
import { generateSparklineData, formatPrice } from './sparkline';

export interface CommandCenterProps {
  /** Symbol label displayed above the price (e.g. "NASDAQ 100"). */
  heroSymbol: string;
  /** Symbol code for the price formatter (e.g. "QQQ"). */
  heroCode: string;
  /** Current price for the hero. 0 / negative renders "--". */
  heroPrice: number;
  heroChange: number;
  heroChangePct: number;
  /** Breadth snapshot for the TICK / A:D / VOLD mini tiles. */
  breadth: MarketBreadth | null;
  /** Computed market regime for the regime chip. */
  regime: MarketRegime;
  /** Live session data (status, countdown, wall time). */
  session: SessionInfo;
}

/**
 * Left column of the dashboard: dense flat command center.
 *
 *  - NQ hero: mono 2xl price + signed change + sparkline + breadth mini tiles.
 *  - Regime indicator: pos/warn/neg chip with description.
 *  - Position calculator: Risk / Stop / R:R inputs and max-contracts readout.
 *  - Session stats: status, countdown, wall time.
 */
export function CommandCenter({
  heroSymbol,
  heroCode,
  heroPrice,
  heroChange,
  heroChangePct,
  breadth,
  regime,
  session,
}: CommandCenterProps) {
  const hasPrice = heroPrice > 0;
  const regimeChip = REGIME_CHIP[regime];

  // Sparkline for the hero block. Guarded so we don't pass NaN into the
  // SVG when no price is available yet.
  const heroSparkline = hasPrice ? generateSparklineData(heroPrice, heroChange, 24) : [];

  return (
    <div className="space-y-2.5">
      {/* NQ / Hero block */}
      <div className="panel">
        <div className="border-b border-line-subtle px-3 h-8 flex items-center justify-between">
          <span className="panel-title">{heroSymbol}</span>
          <span className="text-[10px] font-mono text-ink-muted tracking-[0.08em]">
            {heroCode}
          </span>
        </div>
        <div className="p-2.5">
          <div className="flex items-baseline gap-2">
            <span className="font-mono tabular-nums text-2xl text-ink">
              {hasPrice ? formatPrice(heroPrice, heroCode) : '--'}
            </span>
            {hasPrice && (
              <span
                className={`font-mono tabular-nums text-[12.5px] ${
                  heroChange < 0 ? 'text-neg' : 'text-pos'
                }`}
              >
                {heroChange > 0 ? '+' : ''}
                {heroChange.toFixed(2)} ({heroChangePct.toFixed(2)}%)
              </span>
            )}
          </div>
          <div className="h-8 mt-1.5">
            {heroSparkline.length > 1 && (
              <Sparkline
                data={heroSparkline}
                width={240}
                height={32}
                className="inline-block"
              />
            )}
          </div>

          {/* Breadth mini tiles (TICK / A:D / VOLD) */}
          <div className="grid grid-cols-3 gap-1.5 mt-2">
            <StatTile
              label="TICK"
              value={
                breadth
                  ? breadth.tick_30min_avg > 0
                    ? '↑'
                    : breadth.tick_30min_avg < 0
                    ? '↓'
                    : '·'
                  : '--'
              }
            />
            <StatTile
              label="A/D"
              value={breadth ? breadth.nyse_ad_ratio.toFixed(2) : '--'}
              mono
            />
            <StatTile
              label="VOLD"
              value={
                breadth
                  ? breadth.total_vold > 0
                    ? '↑'
                    : breadth.total_vold < 0
                    ? '↓'
                    : '·'
                  : '--'
              }
            />
          </div>
        </div>
      </div>

      {/* Market Regime */}
      <div className="panel">
        <div className="border-b border-line-subtle px-3 h-8 flex items-center">
          <span className="panel-title">
            <Activity size={11} className="inline-block -mt-0.5 mr-1" />
            REGIME
          </span>
        </div>
        <div className="p-2.5 flex items-center gap-2">
          <span
            className={`inline-flex items-center h-5 px-1.5 border rounded-[2px] text-[11px] font-mono ${regimeChip.chip}`}
          >
            <span className={`w-1.5 h-1.5 rounded-full mr-1.5 ${regimeChip.dot}`} />
            {regimeChip.text}
          </span>
          <span className="text-[11px] text-ink-secondary">{regimeChip.desc}</span>
        </div>
      </div>

      {/* Position Calculator */}
      <div className="panel">
        <div className="border-b border-line-subtle px-3 h-8 flex items-center">
          <span className="panel-title">
            <Target size={11} className="inline-block -mt-0.5 mr-1" />
            POSITION CALCULATOR
          </span>
        </div>
        <div className="p-2.5 space-y-2">
          <div>
            <div className="panel-title">RISK PER TRADE</div>
            <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 h-7 flex items-center font-mono tabular-nums text-[15px] text-ink">
              $250.00
            </div>
          </div>
          <div className="grid grid-cols-2 gap-1.5">
            <div>
              <div className="panel-title">STOP DISTANCE</div>
              <input
                type="number"
                placeholder="Points"
                className="input w-full font-mono tabular-nums"
              />
            </div>
            <div>
              <div className="panel-title">R:R RATIO</div>
              <input
                type="number"
                placeholder="2.0"
                defaultValue="2.0"
                className="input w-full font-mono tabular-nums"
              />
            </div>
          </div>
          <div className="bg-sel-dim border border-line rounded-[2px] px-2 py-1 flex items-center justify-between">
            <div className="panel-title text-sel">MAX CONTRACTS (MNQ)</div>
            <div className="font-mono tabular-nums text-2xl text-sel">4</div>
          </div>
        </div>
      </div>

      {/* Session */}
      <div className="panel">
        <div className="border-b border-line-subtle px-3 h-8 flex items-center">
          <span className="panel-title">
            <Clock size={11} className="inline-block -mt-0.5 mr-1" />
            SESSION
          </span>
        </div>
        <div className="p-2.5 space-y-1 text-[12.5px]">
          <SessionRow label="Status" value={session.status} valueClass="text-pos" />
          <SessionRow label="Time Left" value={session.countdown} />
          <SessionRow label="Time" value={session.time} valueClass="font-mono tabular-nums" />
        </div>
      </div>
    </div>
  );
}

const REGIME_CHIP: Record<
  MarketRegime,
  { chip: string; dot: string; text: string; desc: string }
> = {
  favorable: {
    chip: 'border-pos text-pos',
    dot: 'bg-pos',
    text: 'HIGH CONFIDENCE',
    desc: 'All signals aligned',
  },
  mixed: {
    chip: 'border-warn text-warn',
    dot: 'bg-warn',
    text: 'MIXED SIGNALS',
    desc: 'Reduce position size',
  },
  avoid: {
    chip: 'border-neg text-neg',
    dot: 'bg-neg',
    text: 'CHOPPY MARKET',
    desc: 'Stay flat or minimal risk',
  },
};

function SessionRow({
  label,
  value,
  valueClass = '',
}: {
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="flex justify-between">
      <span className="text-ink-muted">{label}:</span>
      <span className={`text-ink ${valueClass}`}>{value}</span>
    </div>
  );
}

// Helper kept exported for back-compat with any future inline use; not used
// inside the module today.
export type { MarketData };