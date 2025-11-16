'use client';

import React, { useState, useEffect } from 'react';
import { AlertTriangle, TrendingUp, TrendingDown, Target, Shield } from 'lucide-react';

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

  // Calculate percentage used of daily limit
  const dailyLimitUsed = (Math.abs(riskMetrics.daily_pnl) / riskMetrics.daily_limit) * 100;
  const tradesUsed = (riskMetrics.trades_today / riskMetrics.max_trades_per_day) * 100;

  // Determine risk status
  const getRiskStatus = () => {
    if (riskMetrics.daily_pnl < -riskMetrics.daily_limit * 0.8) return 'danger';
    if (riskMetrics.daily_pnl < -riskMetrics.daily_limit * 0.5) return 'warning';
    return 'safe';
  };

  const riskStatus = getRiskStatus();

  const fetchPositionSize = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/backtest/position-size', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          recent_trades: recentTrades,
          account_balance: 10000,
          base_contracts: 1,
          max_contracts: 8,
          use_kelly: true
        })
      });

      const data = await response.json();
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
    }
  };

  useEffect(() => {
    fetchPositionSize();
  }, [recentTrades]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white">Risk Manager</h2>
        <div className={`px-3 py-1 rounded-full text-sm font-semibold ${
          riskStatus === 'danger' ? 'bg-red-500/20 text-red-400' :
          riskStatus === 'warning' ? 'bg-yellow-500/20 text-yellow-400' :
          'bg-green-500/20 text-green-400'
        }`}>
          {riskStatus.toUpperCase()}
        </div>
      </div>

      {/* Daily Limits Section */}
      <div className="grid grid-cols-2 gap-4">
        {/* Daily P&L */}
        <div className="bg-gray-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-gray-400">Daily P&L</span>
            <Shield size={16} className="text-gray-400" />
          </div>
          <div className={`text-3xl font-bold ${
            riskMetrics.daily_pnl >= 0 ? 'text-green-400' : 'text-red-400'
          }`}>
            {riskMetrics.daily_pnl >= 0 ? '+' : ''}${riskMetrics.daily_pnl.toFixed(2)}
          </div>
          <div className="mt-2">
            <div className="flex justify-between text-xs text-gray-400 mb-1">
              <span>Limit: ${riskMetrics.daily_limit}</span>
              <span>{dailyLimitUsed.toFixed(0)}%</span>
            </div>
            <div className="w-full bg-gray-700 rounded-full h-2">
              <div
                className={`h-2 rounded-full ${
                  dailyLimitUsed > 80 ? 'bg-red-500' :
                  dailyLimitUsed > 50 ? 'bg-yellow-500' :
                  'bg-green-500'
                }`}
                style={{ width: `${Math.min(dailyLimitUsed, 100)}%` }}
              ></div>
            </div>
          </div>
        </div>

        {/* Trades Remaining */}
        <div className="bg-gray-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-gray-400">Trades Today</span>
            <Target size={16} className="text-gray-400" />
          </div>
          <div className="text-3xl font-bold text-blue-400">
            {riskMetrics.trades_today} / {riskMetrics.max_trades_per_day}
          </div>
          <div className="mt-2">
            <div className="flex justify-between text-xs text-gray-400 mb-1">
              <span>Remaining: {riskMetrics.max_trades_per_day - riskMetrics.trades_today}</span>
              <span>{tradesUsed.toFixed(0)}%</span>
            </div>
            <div className="w-full bg-gray-700 rounded-full h-2">
              <div
                className="h-2 rounded-full bg-blue-500"
                style={{ width: `${Math.min(tradesUsed, 100)}%` }}
              ></div>
            </div>
          </div>
        </div>
      </div>

      {/* Position Sizing Section */}
      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-4 flex items-center gap-2">
          <TrendingUp size={16} />
          Auto-Scaling Position Size
        </h3>

        <div className="grid grid-cols-3 gap-4 mb-4">
          <div className="text-center">
            <div className="text-xs text-gray-400">Win Streak</div>
            <div className="text-2xl font-bold text-green-400">{riskMetrics.win_streak}</div>
          </div>
          <div className="text-center">
            <div className="text-xs text-gray-400">Loss Streak</div>
            <div className="text-2xl font-bold text-red-400">{riskMetrics.loss_streak}</div>
          </div>
          <div className="text-center">
            <div className="text-xs text-gray-400">Recommended</div>
            <div className="text-2xl font-bold text-blue-400">{riskMetrics.recommended_contracts}</div>
          </div>
        </div>

        {/* Scaling Rules */}
        <div className="bg-gray-900 rounded p-3">
          <div className="text-xs text-gray-400 mb-2">Scaling Rules</div>
          <div className="space-y-1 text-xs">
            <div className={`flex items-center justify-between ${
              riskMetrics.win_streak >= 3 ? 'text-green-400 font-semibold' : 'text-gray-500'
            }`}>
              <span>3 wins → 2 contracts</span>
              {riskMetrics.win_streak >= 3 && <span>✓</span>}
            </div>
            <div className={`flex items-center justify-between ${
              riskMetrics.win_streak >= 6 ? 'text-green-400 font-semibold' : 'text-gray-500'
            }`}>
              <span>6 wins → 4 contracts</span>
              {riskMetrics.win_streak >= 6 && <span>✓</span>}
            </div>
            <div className={`flex items-center justify-between ${
              riskMetrics.loss_streak >= 2 ? 'text-red-400 font-semibold' : 'text-gray-500'
            }`}>
              <span>2 losses → reset to 1</span>
              {riskMetrics.loss_streak >= 2 && <span>⚠</span>}
            </div>
          </div>
        </div>
      </div>

      {/* Drawdown Warning */}
      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
          <AlertTriangle size={16} className="text-yellow-400" />
          Drawdown Monitor
        </h3>

        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-sm text-gray-400">Current Drawdown</span>
            <span className="text-lg font-bold text-white">
              {riskMetrics.current_drawdown.toFixed(1)}%
            </span>
          </div>

          <div className="w-full bg-gray-700 rounded-full h-3">
            <div
              className={`h-3 rounded-full ${
                riskMetrics.current_drawdown > 10 ? 'bg-red-500' :
                riskMetrics.current_drawdown > 5 ? 'bg-yellow-500' :
                'bg-green-500'
              }`}
              style={{ width: `${(riskMetrics.current_drawdown / riskMetrics.max_drawdown_limit) * 100}%` }}
            ></div>
          </div>

          <div className="flex justify-between text-xs text-gray-400">
            <span>Safe: &lt;5%</span>
            <span>Warning: 5-10%</span>
            <span>Danger: &gt;10%</span>
          </div>
        </div>

        {riskMetrics.current_drawdown > 10 && (
          <div className="mt-3 bg-red-500/10 border border-red-500/30 rounded p-2">
            <div className="text-xs text-red-400 font-semibold">
              ⚠ High Drawdown Alert
            </div>
            <div className="text-xs text-red-300 mt-1">
              Consider reducing position size or taking a break
            </div>
          </div>
        )}
      </div>

      {/* Weekly Performance */}
      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-3">Weekly Performance</h3>
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs text-gray-400">Week P&L</div>
            <div className={`text-2xl font-bold ${
              riskMetrics.weekly_pnl >= 0 ? 'text-green-400' : 'text-red-400'
            }`}>
              {riskMetrics.weekly_pnl >= 0 ? '+' : ''}${riskMetrics.weekly_pnl.toFixed(2)}
            </div>
          </div>
          <div className="text-right">
            <div className="text-xs text-gray-400">Goal</div>
            <div className="text-lg font-semibold text-white">$2,000</div>
          </div>
        </div>
      </div>

      {/* Trade Journal Link */}
      <div className="bg-blue-900/20 border border-blue-500/30 rounded-lg p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-semibold text-white mb-1">Trade Journal</div>
            <div className="text-xs text-gray-400">
              Review your recent trades and identify patterns
            </div>
          </div>
          <button className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded text-sm">
            View Journal
          </button>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-2 gap-3">
        <button className="bg-gray-800 hover:bg-gray-700 rounded py-3 text-sm font-semibold">
          Export Risk Report
        </button>
        <button className="bg-gray-800 hover:bg-gray-700 rounded py-3 text-sm font-semibold">
          Adjust Limits
        </button>
      </div>
    </div>
  );
}
