'use client';

import React, { useState, useEffect } from 'react';
import { AlertTriangle, TrendingUp, TrendingDown, Target, Shield } from 'lucide-react';
import { apiFetch } from '../lib/api';

interface Trade {
  timestamp: string;
  symbol: string;
  direction: 'LONG' | 'SHORT';
  entry_price: number;
  exit_price: number;
  pnl: number;
  contracts: number;
}

interface RiskMetrics {
  daily_pnl: number;
  daily_limit: number;
  weekly_pnl: number;
  trades_today: number;
  max_trades_per_day: number;
  current_drawdown: number;
  max_drawdown_limit: number;
  win_streak: number;
  loss_streak: number;
  recommended_contracts: number;
}

const STATUS_TONE = {
  safe: { text: 'text-pos', border: 'border-pos' },
  warning: { text: 'text-warn', border: 'border-warn' },
  danger: { text: 'text-neg', border: 'border-neg' },
} as const;

export default function RiskManagerTab() {
  const [riskMetrics, setRiskMetrics] = useState<RiskMetrics>({
    daily_pnl: 385.00,
    daily_limit: 1000,
    weekly_pnl: 1250.00,
    trades_today: 3,
    max_trades_per_day: 5,
    current_drawdown: 2.5,
    max_drawdown_limit: 15,
    win_streak: 3,
    loss_streak: 0,
    recommended_contracts: 2
  });

  const [recentTrades, setRecentTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Calculate percentage used of daily limit
  const dailyLimitUsed = (Math.abs(riskMetrics.daily_pnl) / riskMetrics.daily_limit) * 100;
  const tradesUsed = (riskMetrics.trades_today / riskMetrics.max_trades_per_day) * 100;

  // Determine risk status
  const getRiskStatus = (): keyof typeof STATUS_TONE => {
    if (riskMetrics.daily_pnl < -riskMetrics.daily_limit * 0.8) return 'danger';
    if (riskMetrics.daily_pnl < -riskMetrics.daily_limit * 0.5) return 'warning';
    return 'safe';
  };

  const riskStatus = getRiskStatus();
  const statusTone = STATUS_TONE[riskStatus];

  // P&L bar color: track uses bg-surface-raised; fill is bg-pos / bg-neg flat.
  const pnlBarColor =
    riskMetrics.daily_pnl < 0 && riskMetrics.daily_pnl < -riskMetrics.daily_limit * 0.5
      ? riskMetrics.daily_pnl < -riskMetrics.daily_limit * 0.8
        ? 'bg-neg'
        : 'bg-warn'
      : 'bg-pos';

  // Drawdown meter color
  const drawdownBarColor =
    riskMetrics.current_drawdown > 10
      ? 'bg-neg'
      : riskMetrics.current_drawdown > 5
      ? 'bg-warn'
      : 'bg-pos';

  const fetchPositionSize = async () => {
    try {
      setError(null);
      const data = await apiFetch<any>('/backtest/position-size', {
        method: 'POST',
        body: JSON.stringify({
          recent_trades: recentTrades,
          account_balance: 10000,
          base_contracts: 1,
          max_contracts: 8,
          use_kelly: true
        })
      });

      if (data.success) {
        setRiskMetrics(prev => ({
          ...prev,
          recommended_contracts: data.data.recommended_contracts,
          win_streak: data.data.consecutive_wins || 0,
          loss_streak: data.data.consecutive_losses || 0
        }));
      }
    } catch (err) {
      console.error('Failed to fetch position size:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch position size');
    }
  };

  useEffect(() => {
    fetchPositionSize();
  }, [recentTrades]);

  return (
    <div className="space-y-2.5">
      {error && (
        <div className="p-2.5 bg-neg-dim border border-line rounded-[2px] text-[12.5px] flex items-center gap-2">
          <span className="text-neg">{error}</span>
          <button onClick={fetchPositionSize} className="ml-auto underline text-neg hover:text-ink">
            Retry
          </button>
        </div>
      )}

      {/* Main panel */}
      <div className="panel">
        <div className="border-b border-line-subtle px-3 h-8 flex items-center justify-between">
          <span className="panel-title">Risk Manager</span>
          <span
            className={`border rounded-[2px] px-1.5 h-5 text-[11px] font-mono inline-flex items-center ${statusTone.border} ${statusTone.text}`}
          >
            {riskStatus.toUpperCase()}
          </span>
        </div>

        <div className="p-2.5 space-y-2.5">
          {/* Daily Limits — 2 stat tiles */}
          <div className="grid grid-cols-2 gap-2.5">
            {/* Daily P&L tile */}
            <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5">
              <div className="flex items-center justify-between">
                <span className="panel-title">Daily P&L</span>
                <Shield className="w-3 h-3 text-ink-muted" />
              </div>
              <div
                className={`text-[15px] leading-tight mt-0.5 font-mono tabular-nums ${
                  riskMetrics.daily_pnl >= 0 ? 'text-pos' : 'text-neg'
                }`}
              >
                {riskMetrics.daily_pnl >= 0 ? '+' : ''}${riskMetrics.daily_pnl.toFixed(2)}
              </div>
              <div className="flex justify-between text-[10px] text-ink-muted mt-1.5">
                <span>Limit: ${riskMetrics.daily_limit}</span>
                <span>{dailyLimitUsed.toFixed(0)}%</span>
              </div>
              <div className="w-full bg-surface-raised border border-line rounded-[2px] h-3 mt-0.5">
                <div
                  className={`h-full ${pnlBarColor}`}
                  style={{ width: `${Math.min(dailyLimitUsed, 100)}%` }}
                />
              </div>
            </div>

            {/* Trades Today tile */}
            <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5">
              <div className="flex items-center justify-between">
                <span className="panel-title">Trades Today</span>
                <Target className="w-3 h-3 text-ink-muted" />
              </div>
              <div className="text-[15px] leading-tight mt-0.5 font-mono tabular-nums text-sel">
                {riskMetrics.trades_today} / {riskMetrics.max_trades_per_day}
              </div>
              <div className="flex justify-between text-[10px] text-ink-muted mt-1.5">
                <span>Remaining: {riskMetrics.max_trades_per_day - riskMetrics.trades_today}</span>
                <span>{tradesUsed.toFixed(0)}%</span>
              </div>
              <div className="w-full bg-surface-raised border border-line rounded-[2px] h-3 mt-0.5">
                <div
                  className="h-full bg-sel"
                  style={{ width: `${Math.min(tradesUsed, 100)}%` }}
                />
              </div>
            </div>
          </div>

          {/* Position Sizing Section */}
          <div>
            <div className="text-[11px] uppercase tracking-[0.08em] text-ink-secondary mb-1.5 flex items-center gap-1.5">
              <TrendingUp className="w-3 h-3" />
              Auto-Scaling Position Size
            </div>
            <div className="grid grid-cols-3 gap-2.5">
              <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5">
                <div className="panel-title">Win Streak</div>
                <div className="text-[15px] leading-tight mt-0.5 font-mono tabular-nums text-pos">
                  {riskMetrics.win_streak}
                </div>
              </div>
              <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5">
                <div className="panel-title">Loss Streak</div>
                <div className="text-[15px] leading-tight mt-0.5 font-mono tabular-nums text-neg">
                  {riskMetrics.loss_streak}
                </div>
              </div>
              <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5">
                <div className="panel-title">Recommended</div>
                <div className="text-[15px] leading-tight mt-0.5 font-mono tabular-nums text-sel">
                  {riskMetrics.recommended_contracts}
                </div>
              </div>
            </div>

            {/* Scaling Rules */}
            <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5 mt-2">
              <div className="panel-title">Scaling Rules</div>
              <div className="mt-1 space-y-1 text-[12px]">
                <div
                  className={`flex items-center justify-between ${
                    riskMetrics.win_streak >= 3
                      ? 'text-pos font-semibold'
                      : 'text-ink-muted'
                  }`}
                >
                  <span>3 wins → 2 contracts</span>
                  {riskMetrics.win_streak >= 3 && <span>✓</span>}
                </div>
                <div
                  className={`flex items-center justify-between ${
                    riskMetrics.win_streak >= 6
                      ? 'text-pos font-semibold'
                      : 'text-ink-muted'
                  }`}
                >
                  <span>6 wins → 4 contracts</span>
                  {riskMetrics.win_streak >= 6 && <span>✓</span>}
                </div>
                <div
                  className={`flex items-center justify-between ${
                    riskMetrics.loss_streak >= 2
                      ? 'text-neg font-semibold'
                      : 'text-ink-muted'
                  }`}
                >
                  <span>2 losses → reset to 1</span>
                  {riskMetrics.loss_streak >= 2 && <span>⚠</span>}
                </div>
              </div>
            </div>
          </div>

          {/* Drawdown Warning */}
          <div>
            <div className="text-[11px] uppercase tracking-[0.08em] text-ink-secondary mb-1.5 flex items-center gap-1.5">
              <AlertTriangle className="w-3 h-3 text-warn" />
              Drawdown Monitor
            </div>
            <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5">
              <div className="flex justify-between items-center mb-1.5">
                <span className="text-[12px] text-ink-secondary">Current Drawdown</span>
                <span className="text-[13px] font-mono tabular-nums text-ink">
                  {riskMetrics.current_drawdown.toFixed(1)}%
                </span>
              </div>
              <div className="w-full bg-surface-raised border border-line rounded-[2px] h-3">
                <div
                  className={`h-full ${drawdownBarColor}`}
                  style={{
                    width: `${(riskMetrics.current_drawdown / riskMetrics.max_drawdown_limit) * 100}%`,
                  }}
                />
              </div>
              <div className="flex justify-between text-[10px] text-ink-muted mt-1">
                <span>Safe: &lt;5%</span>
                <span>Warning: 5-10%</span>
                <span>Danger: &gt;10%</span>
              </div>
            </div>

            {riskMetrics.current_drawdown > 10 && (
              <div className="mt-2 bg-neg-dim border border-line rounded-[2px] px-2 py-1.5">
                <div className="text-[12px] text-neg font-semibold">
                  ⚠ High Drawdown Alert
                </div>
                <div className="text-[11px] text-ink-secondary mt-0.5">
                  Consider reducing position size or taking a break
                </div>
              </div>
            )}
          </div>

          {/* Weekly Performance */}
          <div>
            <div className="text-[11px] uppercase tracking-[0.08em] text-ink-secondary mb-1.5 flex items-center gap-1.5">
              <TrendingDown className="w-3 h-3" />
              Weekly Performance
            </div>
            <div className="grid grid-cols-2 gap-2.5">
              <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5">
                <div className="panel-title">Week P&L</div>
                <div
                  className={`text-[15px] leading-tight mt-0.5 font-mono tabular-nums ${
                    riskMetrics.weekly_pnl >= 0 ? 'text-pos' : 'text-neg'
                  }`}
                >
                  {riskMetrics.weekly_pnl >= 0 ? '+' : ''}${riskMetrics.weekly_pnl.toFixed(2)}
                </div>
              </div>
              <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5">
                <div className="panel-title">Goal</div>
                <div className="text-[15px] leading-tight mt-0.5 font-mono tabular-nums text-ink">
                  $2,000
                </div>
              </div>
            </div>
          </div>

          {/* Trade Journal Link */}
          <div className="bg-sel-dim border border-line rounded-[2px] px-2.5 py-1.5 flex items-center justify-between">
            <div>
              <div className="text-[12.5px] text-ink">Trade Journal</div>
              <div className="text-[11px] text-ink-secondary">
                Review your recent trades and identify patterns
              </div>
            </div>
            <button className="btn">View Journal</button>
          </div>

          {/* Quick Actions */}
          <div className="grid grid-cols-2 gap-2.5">
            <button className="btn">Export Risk Report</button>
            <button className="btn">Adjust Limits</button>
          </div>
        </div>
      </div>
    </div>
  );
}