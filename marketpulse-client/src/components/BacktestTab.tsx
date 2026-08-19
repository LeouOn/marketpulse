'use client';

import React, { useState } from 'react';
import { TrendingUp, TrendingDown, BarChart2, DollarSign, Target, Activity } from 'lucide-react';
import { apiFetch } from '../lib/api';

interface BacktestResults {
  basic_metrics: {
    total_trades: number;
    winning_trades: number;
    losing_trades: number;
    win_rate: number;
  };
  pnl_metrics: {
    total_pnl: number;
    total_pnl_percent: number;
    average_winner: number;
    average_loser: number;
    largest_winner: number;
    largest_loser: number;
    profit_factor: number;
  };
  risk_metrics: {
    max_drawdown: number;
    max_drawdown_percent: number;
    sharpe_ratio: number;
    sortino_ratio: number;
  };
  trade_metrics: {
    average_trade_duration_minutes: number;
    average_trade_pnl: number;
    expectancy: number;
  };
  strategy_metrics: {
    fvg_success_rate: number;
    divergence_success_rate: number;
    best_hour_of_day: number;
    worst_hour_of_day: number;
    best_day_of_week: string;
  };
  performance_by_setup: Record<string, any>;
  sample_trades: any[];
}

export default function BacktestTab() {
  const [results, setResults] = useState<BacktestResults | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [symbol, setSymbol] = useState('NQ');
  const [startDate, setStartDate] = useState('2024-01-01');
  const [endDate, setEndDate] = useState('2024-11-15');
  const [contracts, setContracts] = useState(1);

  const runBacktest = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<any>('/backtest/run', {
        method: 'POST',
        body: JSON.stringify({
          symbol,
          start_date: startDate,
          end_date: endDate,
          initial_capital: 10000,
          contracts,
          interval: '5m'
        })
      });

      if (data.success) {
        setResults(data.data);
      }
    } catch (err) {
      console.error('Failed to run backtest:', err);
      setError(err instanceof Error ? err.message : 'Failed to run backtest');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-2.5">
      {error && (
        <div className="p-2.5 bg-neg-dim border border-line rounded-[2px] text-[12.5px] flex items-center gap-2">
          <span className="text-neg">{error}</span>
          <button onClick={runBacktest} className="ml-auto underline text-neg hover:text-ink">
            Retry
          </button>
        </div>
      )}

      <div className="panel">
        <div className="border-b border-line-subtle px-3 h-8 flex items-center justify-between">
          <span className="panel-title">Backtesting Engine</span>
          <div className="flex items-center gap-1.5 text-[11px] text-ink-secondary">
            <Activity className="w-3 h-3" />
            <span className="font-mono uppercase tracking-[0.08em]">FVG + Divergence</span>
          </div>
        </div>

        {/* Configuration */}
        <div className="p-2.5">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
            <div>
              <label className="block text-[11px] uppercase tracking-[0.08em] text-ink-secondary mb-1">
                Symbol
              </label>
              <select
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="input w-full"
              >
                <option value="NQ">NQ (Nasdaq 100)</option>
                <option value="ES">ES (S&amp;P 500)</option>
                <option value="YM">YM (Dow Jones)</option>
              </select>
            </div>
            <div>
              <label className="block text-[11px] uppercase tracking-[0.08em] text-ink-secondary mb-1">
                Start Date
              </label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="input w-full"
              />
            </div>
            <div>
              <label className="block text-[11px] uppercase tracking-[0.08em] text-ink-secondary mb-1">
                End Date
              </label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="input w-full"
              />
            </div>
            <div>
              <label className="block text-[11px] uppercase tracking-[0.08em] text-ink-secondary mb-1">
                Contracts
              </label>
              <input
                type="number"
                value={contracts}
                onChange={(e) => setContracts(parseInt(e.target.value))}
                min={1}
                max={10}
                className="input w-full"
              />
            </div>
          </div>
          <button
            onClick={runBacktest}
            disabled={loading}
            className="btn btn-primary mt-3 w-full"
          >
            {loading ? 'Running Backtest…' : 'Run Backtest'}
          </button>
        </div>
      </div>

      {/* Results Section */}
      {results && (
        <>
          {/* Performance Overview — 4 hero tiles */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
            <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5">
              <div className="flex items-center gap-1.5 panel-title">
                <DollarSign className="w-3 h-3 text-pos" />
                Total P&amp;L
              </div>
              <div
                className={`text-[15px] leading-tight mt-0.5 font-mono tabular-nums ${
                  results.pnl_metrics.total_pnl >= 0 ? 'text-pos' : 'text-neg'
                }`}
              >
                ${results.pnl_metrics.total_pnl.toLocaleString()}
              </div>
              <div className="text-[11px] font-mono tabular-nums text-ink-secondary mt-0.5">
                {results.pnl_metrics.total_pnl_percent >= 0 ? '+' : ''}
                {results.pnl_metrics.total_pnl_percent}%
              </div>
            </div>

            <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5">
              <div className="flex items-center gap-1.5 panel-title">
                <Target className="w-3 h-3 text-sel" />
                Win Rate
              </div>
              <div className="text-[15px] leading-tight mt-0.5 font-mono tabular-nums text-ink">
                {results.basic_metrics.win_rate}%
              </div>
              <div className="text-[11px] font-mono tabular-nums text-ink-secondary mt-0.5">
                {results.basic_metrics.winning_trades}W / {results.basic_metrics.losing_trades}L
              </div>
            </div>

            <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5">
              <div className="flex items-center gap-1.5 panel-title">
                <TrendingUp className="w-3 h-3 text-teal" />
                Profit Factor
              </div>
              <div className="text-[15px] leading-tight mt-0.5 font-mono tabular-nums text-ink">
                {results.pnl_metrics.profit_factor.toFixed(2)}
              </div>
              <div className="text-[11px] font-mono tabular-nums text-ink-secondary mt-0.5">
                Avg ${results.trade_metrics.average_trade_pnl}
              </div>
            </div>

            <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5">
              <div className="flex items-center gap-1.5 panel-title">
                <TrendingDown className="w-3 h-3 text-neg" />
                Max Drawdown
              </div>
              <div className="text-[15px] leading-tight mt-0.5 font-mono tabular-nums text-neg">
                {results.risk_metrics.max_drawdown_percent}%
              </div>
              <div className="text-[11px] font-mono tabular-nums text-ink-secondary mt-0.5">
                ${Math.abs(results.risk_metrics.max_drawdown).toLocaleString()}
              </div>
            </div>
          </div>

          {/* Risk-Adjusted Returns */}
          <div className="panel">
            <div className="border-b border-line-subtle px-3 h-8 flex items-center">
              <span className="panel-title">Risk-Adjusted Returns</span>
            </div>
            <div className="p-2.5 grid grid-cols-3 gap-2.5">
              <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5">
                <div className="panel-title">Sharpe Ratio</div>
                <div
                  className={`text-[15px] leading-tight mt-0.5 font-mono tabular-nums ${
                    results.risk_metrics.sharpe_ratio > 1
                      ? 'text-pos'
                      : results.risk_metrics.sharpe_ratio > 0.5
                      ? 'text-warn'
                      : 'text-neg'
                  }`}
                >
                  {results.risk_metrics.sharpe_ratio.toFixed(2)}
                </div>
                <div className="text-[11px] font-mono tabular-nums text-ink-secondary mt-0.5">
                  {results.risk_metrics.sharpe_ratio > 1
                    ? 'Excellent'
                    : results.risk_metrics.sharpe_ratio > 0.5
                    ? 'Good'
                    : 'Poor'}
                </div>
              </div>
              <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5">
                <div className="panel-title">Sortino Ratio</div>
                <div className="text-[15px] leading-tight mt-0.5 font-mono tabular-nums text-ink">
                  {results.risk_metrics.sortino_ratio.toFixed(2)}
                </div>
                <div className="text-[11px] font-mono tabular-nums text-ink-secondary mt-0.5">
                  Downside risk adj.
                </div>
              </div>
              <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5">
                <div className="panel-title">Expectancy</div>
                <div className="text-[15px] leading-tight mt-0.5 font-mono tabular-nums text-sel">
                  ${results.trade_metrics.expectancy}
                </div>
                <div className="text-[11px] font-mono tabular-nums text-ink-secondary mt-0.5">
                  Per trade
                </div>
              </div>
            </div>
          </div>

          {/* Strategy Breakdown */}
          <div className="panel">
            <div className="border-b border-line-subtle px-3 h-8 flex items-center">
              <span className="panel-title">Strategy Breakdown</span>
            </div>
            <div className="p-2.5 grid grid-cols-2 gap-2.5">
              <div>
                <div className="text-[11px] uppercase tracking-[0.08em] text-ink-secondary mb-1.5">
                  Setup Success Rates
                </div>
                <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5 space-y-1.5">
                  <div className="flex justify-between items-center">
                    <span className="text-[12px] text-ink-secondary">FVG Setups</span>
                    <span className="text-[12.5px] font-mono tabular-nums text-pos">
                      {results.strategy_metrics.fvg_success_rate}%
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-[12px] text-ink-secondary">Divergence Setups</span>
                    <span className="text-[12.5px] font-mono tabular-nums text-sel">
                      {results.strategy_metrics.divergence_success_rate}%
                    </span>
                  </div>
                </div>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-[0.08em] text-ink-secondary mb-1.5">
                  Best Trading Times
                </div>
                <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5 space-y-1.5">
                  <div className="flex justify-between items-center">
                    <span className="text-[12px] text-ink-secondary">Best Hour</span>
                    <span className="text-[12.5px] font-mono tabular-nums text-ink">
                      {results.strategy_metrics.best_hour_of_day}:00
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-[12px] text-ink-secondary">Best Day</span>
                    <span className="text-[12.5px] font-mono tabular-nums text-ink">
                      {results.strategy_metrics.best_day_of_week}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Sample Trades */}
          {results.sample_trades.length > 0 && (
            <div className="panel">
              <div className="border-b border-line-subtle px-3 h-8 flex items-center">
                <span className="panel-title">Recent Trades (Sample)</span>
              </div>
              <div className="overflow-x-auto max-h-96 overflow-y-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th className="sticky top-0 bg-surface">Entry Date</th>
                      <th className="sticky top-0 bg-surface">Direction</th>
                      <th className="num sticky top-0 bg-surface">Entry</th>
                      <th className="num sticky top-0 bg-surface">Exit</th>
                      <th className="num sticky top-0 bg-surface">P&amp;L</th>
                      <th className="sticky top-0 bg-surface">Setup</th>
                    </tr>
                  </thead>
                  <tbody>
                    {results.sample_trades.slice(0, 10).map((trade, idx) => {
                      const directionClass =
                        trade.direction === 'LONG' ? 'text-pos' : 'text-neg';
                      return (
                        <tr key={idx}>
                          <td>
                            {new Date(trade.entry_time).toLocaleDateString()}
                          </td>
                          <td>
                            <span className={`text-[11px] font-mono ${directionClass}`}>
                              {trade.direction}
                            </span>
                          </td>
                          <td className="num">{trade.entry_price}</td>
                          <td className="num">{trade.exit_price}</td>
                          <td
                            className={`num ${
                              trade.pnl >= 0 ? 'text-pos' : 'text-neg'
                            }`}
                          >
                            {trade.pnl >= 0 ? '+' : ''}${trade.pnl}
                          </td>
                          <td className="text-[11px] text-ink-secondary">
                            {trade.setup_type}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* Empty State */}
      {!results && !loading && (
        <div className="panel">
          <div className="p-12 text-center">
            <BarChart2 className="w-8 h-8 mx-auto text-ink-muted mb-3" />
            <div className="text-[13px] text-ink-secondary mb-1.5">No Backtest Results</div>
            <p className="text-[12px] text-ink-muted mb-3">
              Configure your backtest parameters above and click "Run Backtest" to see results.
            </p>
            <p className="text-[11px] text-ink-muted font-mono">
              Strategy: FVG + Divergence | Timeframe: 5 minutes | Risk: 1:2 R/R
            </p>
          </div>
        </div>
      )}
    </div>
  );
}