'use client';

import React, { useState } from 'react';
import { TrendingUp, TrendingDown, BarChart2, Calendar, DollarSign, Target, Activity } from 'lucide-react';

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
  const [symbol, setSymbol] = useState('NQ');
  const [startDate, setStartDate] = useState('2024-01-01');
  const [endDate, setEndDate] = useState('2024-11-15');
  const [contracts, setContracts] = useState(1);

  const runBacktest = async () => {
    setLoading(true);
    try {
      const response = await fetch('http://localhost:8000/api/backtest/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol,
          start_date: startDate,
          end_date: endDate,
          initial_capital: 10000,
          contracts,
          interval: '5m'
        })
      });

      const data = await response.json();
      if (data.success) {
        setResults(data.data);
      }
    } catch (err) {
      console.error('Failed to run backtest:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white">Backtesting Engine</h2>
        <div className="flex items-center gap-2 text-xs text-gray-400">
          <Activity size={14} />
          <span>FVG + Divergence Strategy</span>
        </div>
      </div>

      {/* Configuration Section */}
      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-3 text-white">Backtest Configuration</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <label className="text-xs text-gray-400">Symbol</label>
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
            >
              <option value="NQ">NQ (Nasdaq 100)</option>
              <option value="ES">ES (S&P 500)</option>
              <option value="YM">YM (Dow Jones)</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-400">Start Date</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-gray-400">End Date</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-gray-400">Contracts</label>
            <input
              type="number"
              value={contracts}
              onChange={(e) => setContracts(parseInt(e.target.value))}
              min={1}
              max={10}
              className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
            />
          </div>
        </div>
        <button
          onClick={runBacktest}
          disabled={loading}
          className="mt-4 w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 rounded py-2 text-white font-semibold transition-colors"
        >
          {loading ? 'Running Backtest...' : 'Run Backtest'}
        </button>
      </div>

      {/* Results Section */}
      {results && (
        <>
          {/* Performance Overview */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-gray-800 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-2">
                <DollarSign size={16} className="text-green-400" />
                <span className="text-xs text-gray-400">Total P&L</span>
              </div>
              <div className={`text-2xl font-bold ${results.pnl_metrics.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                ${results.pnl_metrics.total_pnl.toLocaleString()}
              </div>
              <div className="text-xs text-gray-500 mt-1">
                {results.pnl_metrics.total_pnl_percent >= 0 ? '+' : ''}{results.pnl_metrics.total_pnl_percent}%
              </div>
            </div>

            <div className="bg-gray-800 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-2">
                <Target size={16} className="text-blue-400" />
                <span className="text-xs text-gray-400">Win Rate</span>
              </div>
              <div className="text-2xl font-bold text-white">
                {results.basic_metrics.win_rate}%
              </div>
              <div className="text-xs text-gray-500 mt-1">
                {results.basic_metrics.winning_trades}W / {results.basic_metrics.losing_trades}L
              </div>
            </div>

            <div className="bg-gray-800 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-2">
                <TrendingUp size={16} className="text-purple-400" />
                <span className="text-xs text-gray-400">Profit Factor</span>
              </div>
              <div className="text-2xl font-bold text-white">
                {results.pnl_metrics.profit_factor.toFixed(2)}
              </div>
              <div className="text-xs text-gray-500 mt-1">
                Avg: ${results.trade_metrics.average_trade_pnl}
              </div>
            </div>

            <div className="bg-gray-800 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-2">
                <TrendingDown size={16} className="text-red-400" />
                <span className="text-xs text-gray-400">Max Drawdown</span>
              </div>
              <div className="text-2xl font-bold text-red-400">
                {results.risk_metrics.max_drawdown_percent}%
              </div>
              <div className="text-xs text-gray-500 mt-1">
                ${Math.abs(results.risk_metrics.max_drawdown).toLocaleString()}
              </div>
            </div>
          </div>

          {/* Risk Metrics */}
          <div className="bg-gray-800 rounded-lg p-4">
            <h3 className="text-sm font-semibold mb-3 text-white">Risk-Adjusted Returns</h3>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <div className="text-xs text-gray-400 mb-1">Sharpe Ratio</div>
                <div className={`text-xl font-bold ${results.risk_metrics.sharpe_ratio > 1 ? 'text-green-400' : 'text-yellow-400'}`}>
                  {results.risk_metrics.sharpe_ratio.toFixed(2)}
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  {results.risk_metrics.sharpe_ratio > 1 ? 'Excellent' : results.risk_metrics.sharpe_ratio > 0.5 ? 'Good' : 'Poor'}
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-400 mb-1">Sortino Ratio</div>
                <div className="text-xl font-bold text-white">
                  {results.risk_metrics.sortino_ratio.toFixed(2)}
                </div>
                <div className="text-xs text-gray-500 mt-1">Downside risk adj.</div>
              </div>
              <div>
                <div className="text-xs text-gray-400 mb-1">Expectancy</div>
                <div className="text-xl font-bold text-blue-400">
                  ${results.trade_metrics.expectancy}
                </div>
                <div className="text-xs text-gray-500 mt-1">Per trade</div>
              </div>
            </div>
          </div>

          {/* Strategy Performance */}
          <div className="bg-gray-800 rounded-lg p-4">
            <h3 className="text-sm font-semibold mb-3 text-white">Strategy Breakdown</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="text-xs text-gray-400 mb-2">Setup Success Rates</div>
                <div className="space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-300">FVG Setups</span>
                    <span className="text-sm font-semibold text-green-400">
                      {results.strategy_metrics.fvg_success_rate}%
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-300">Divergence Setups</span>
                    <span className="text-sm font-semibold text-blue-400">
                      {results.strategy_metrics.divergence_success_rate}%
                    </span>
                  </div>
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-400 mb-2">Best Trading Times</div>
                <div className="space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-300">Best Hour</span>
                    <span className="text-sm font-semibold text-white">
                      {results.strategy_metrics.best_hour_of_day}:00
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-300">Best Day</span>
                    <span className="text-sm font-semibold text-white">
                      {results.strategy_metrics.best_day_of_week}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Sample Trades */}
          {results.sample_trades.length > 0 && (
            <div className="bg-gray-800 rounded-lg p-4">
              <h3 className="text-sm font-semibold mb-3 text-white">Recent Trades (Sample)</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-gray-400 border-b border-gray-700">
                    <tr>
                      <th className="text-left pb-2">Entry</th>
                      <th className="text-left pb-2">Direction</th>
                      <th className="text-right pb-2">Entry</th>
                      <th className="text-right pb-2">Exit</th>
                      <th className="text-right pb-2">P&L</th>
                      <th className="text-left pb-2">Setup</th>
                    </tr>
                  </thead>
                  <tbody className="text-gray-300">
                    {results.sample_trades.slice(0, 10).map((trade, idx) => (
                      <tr key={idx} className="border-b border-gray-700/50">
                        <td className="py-2">
                          {new Date(trade.entry_time).toLocaleDateString()}
                        </td>
                        <td className="py-2">
                          <span className={`px-2 py-0.5 rounded text-xs ${
                            trade.direction === 'LONG' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                          }`}>
                            {trade.direction}
                          </span>
                        </td>
                        <td className="text-right py-2 font-mono">{trade.entry_price}</td>
                        <td className="text-right py-2 font-mono">{trade.exit_price}</td>
                        <td className={`text-right py-2 font-mono font-semibold ${
                          trade.pnl >= 0 ? 'text-green-400' : 'text-red-400'
                        }`}>
                          {trade.pnl >= 0 ? '+' : ''}${trade.pnl}
                        </td>
                        <td className="py-2 text-xs text-gray-400">{trade.setup_type}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* Empty State */}
      {!results && !loading && (
        <div className="bg-gray-800 rounded-lg p-12 text-center">
          <BarChart2 size={48} className="mx-auto text-gray-600 mb-4" />
          <h3 className="text-lg font-semibold text-gray-400 mb-2">No Backtest Results</h3>
          <p className="text-sm text-gray-500 mb-4">
            Configure your backtest parameters above and click "Run Backtest" to see results.
          </p>
          <p className="text-xs text-gray-600">
            Strategy: FVG + Divergence | Timeframe: 5 minutes | Risk: 1:2 R/R
          </p>
        </div>
      )}
    </div>
  );
}
