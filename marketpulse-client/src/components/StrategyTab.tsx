'use client';

import React, { useState } from 'react';
import { Target, TrendingUp, AlertCircle, Activity, Settings, CheckCircle } from 'lucide-react';

interface Strategy {
  id: string;
  name: string;
  description: string;
  conditions: string[];
  risk_reward: string;
  win_rate: number;
  status: 'active' | 'testing' | 'disabled';
}

interface SignalResult {
  symbol: string;
  signal_type: string;
  confidence: number;
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  risk_reward_ratio: number;
  setup_description: string;
  timestamp: string;
}

export default function StrategyTab() {
  const [selectedStrategy, setSelectedStrategy] = useState<string>('fvg_divergence');
  const [signals, setSignals] = useState<SignalResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);

  const strategies: Strategy[] = [
    {
      id: 'fvg_divergence',
      name: 'FVG + Divergence',
      description: 'Fair Value Gap with volume divergence confirmation',
      conditions: ['FVG identified', 'RSI divergence', 'CVD confirmation'],
      risk_reward: '1:2',
      win_rate: 68,
      status: 'active'
    },
    {
      id: 'ict_killzone',
      name: 'ICT Kill Zone',
      description: 'London/New York session high-probability setups',
      conditions: ['Kill zone time', 'Liquidity sweep', 'Order block'],
      risk_reward: '1:3',
      win_rate: 72,
      status: 'active'
    },
    {
      id: 'breakout_retest',
      name: 'Breakout & Retest',
      description: 'Break and retest of key structural levels',
      conditions: ['Break of structure', 'Volume confirmation', 'Successful retest'],
      risk_reward: '1:2.5',
      win_rate: 65,
      status: 'testing'
    },
    {
      id: 'reversal_pattern',
      name: 'Reversal Patterns',
      description: 'Double tops/bottoms with momentum confirmation',
      conditions: ['Pattern completion', 'Momentum divergence', 'Volume spike'],
      risk_reward: '1:3',
      win_rate: 60,
      status: 'testing'
    },
    {
      id: 'regime_filter',
      name: 'Regime-Filtered Trades',
      description: 'Only trade when market regime is favorable',
      conditions: ['Bullish regime', 'Low volatility', 'Positive breadth'],
      risk_reward: '1:2',
      win_rate: 75,
      status: 'active'
    }
  ];

  const scanMarket = async () => {
    setScanning(true);
    setSignals([]);

    try {
      // Simulated market scan (in production, would call actual backend)
      await new Promise(resolve => setTimeout(resolve, 2000));

      const mockSignals: SignalResult[] = [
        {
          symbol: 'NQ',
          signal_type: 'FVG + Divergence',
          confidence: 82,
          entry_price: 20400,
          stop_loss: 20375,
          take_profit: 20450,
          risk_reward_ratio: 2.0,
          setup_description: 'Bullish FVG at 20390 with RSI divergence and positive CVD',
          timestamp: new Date().toISOString()
        },
        {
          symbol: 'ES',
          signal_type: 'ICT Kill Zone',
          confidence: 75,
          entry_price: 5950,
          stop_loss: 5940,
          take_profit: 5980,
          risk_reward_ratio: 3.0,
          setup_description: 'London session liquidity sweep with order block at 5945',
          timestamp: new Date().toISOString()
        }
      ];

      setSignals(mockSignals);
    } catch (err) {
      console.error('Failed to scan market:', err);
    } finally {
      setScanning(false);
    }
  };

  const currentStrategy = strategies.find(s => s.id === selectedStrategy);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white">Strategy Testing</h2>
        <div className="flex items-center gap-2">
          <Settings size={16} className="text-blue-400" />
          <span className="text-xs text-gray-400">Pattern Scanner</span>
        </div>
      </div>

      {/* Strategy Selector */}
      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-3 text-white">Active Strategies</h3>
        <div className="grid grid-cols-1 gap-2">
          {strategies.map(strategy => (
            <button
              key={strategy.id}
              onClick={() => setSelectedStrategy(strategy.id)}
              className={`text-left p-3 rounded-lg border transition-all ${
                selectedStrategy === strategy.id
                  ? 'bg-blue-900/30 border-blue-500/50'
                  : 'bg-gray-900 border-gray-700 hover:border-gray-600'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-semibold text-white">{strategy.name}</span>
                <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                  strategy.status === 'active' ? 'bg-green-500/20 text-green-400' :
                  strategy.status === 'testing' ? 'bg-yellow-500/20 text-yellow-400' :
                  'bg-gray-500/20 text-gray-400'
                }`}>
                  {strategy.status.toUpperCase()}
                </span>
              </div>
              <p className="text-xs text-gray-400 mb-2">{strategy.description}</p>
              <div className="flex items-center gap-4 text-xs">
                <span className="text-gray-500">Win Rate: <span className="text-green-400 font-semibold">{strategy.win_rate}%</span></span>
                <span className="text-gray-500">R:R: <span className="text-blue-400 font-semibold">{strategy.risk_reward}</span></span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Strategy Details */}
      {currentStrategy && (
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3 text-white">Strategy Conditions</h3>
          <div className="space-y-2">
            {currentStrategy.conditions.map((condition, idx) => (
              <div key={idx} className="flex items-center gap-2 text-sm">
                <CheckCircle size={16} className="text-green-400" />
                <span className="text-gray-300">{condition}</span>
              </div>
            ))}
          </div>

          <div className="mt-4 pt-4 border-t border-gray-700">
            <button
              onClick={scanMarket}
              disabled={scanning}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 rounded py-3 text-white font-semibold transition-colors flex items-center justify-center gap-2"
            >
              {scanning ? (
                <>
                  <Activity size={16} className="animate-spin" />
                  Scanning Market...
                </>
              ) : (
                <>
                  <Target size={16} />
                  Scan for {currentStrategy.name} Setups
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Signals */}
      {signals.length > 0 && (
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3 text-white flex items-center gap-2">
            <AlertCircle size={16} className="text-green-400" />
            Active Signals ({signals.length})
          </h3>
          <div className="space-y-3">
            {signals.map((signal, idx) => (
              <div key={idx} className="bg-gray-900 rounded-lg p-4 border border-gray-700">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <span className="text-lg font-bold text-white">{signal.symbol}</span>
                    <span className="px-2 py-1 bg-blue-500/20 text-blue-400 rounded text-xs font-semibold">
                      {signal.signal_type}
                    </span>
                  </div>
                  <div className="text-right">
                    <div className="text-xs text-gray-400">Confidence</div>
                    <div className={`text-lg font-bold ${
                      signal.confidence >= 80 ? 'text-green-400' :
                      signal.confidence >= 65 ? 'text-yellow-400' :
                      'text-gray-400'
                    }`}>
                      {signal.confidence}%
                    </div>
                  </div>
                </div>

                <p className="text-sm text-gray-300 mb-3">{signal.setup_description}</p>

                <div className="grid grid-cols-4 gap-3">
                  <div>
                    <div className="text-xs text-gray-400">Entry</div>
                    <div className="text-sm font-mono font-semibold text-white">
                      {signal.entry_price.toLocaleString()}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-400">Stop</div>
                    <div className="text-sm font-mono font-semibold text-red-400">
                      {signal.stop_loss.toLocaleString()}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-400">Target</div>
                    <div className="text-sm font-mono font-semibold text-green-400">
                      {signal.take_profit.toLocaleString()}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-400">R:R</div>
                    <div className="text-sm font-mono font-semibold text-blue-400">
                      1:{signal.risk_reward_ratio.toFixed(1)}
                    </div>
                  </div>
                </div>

                <div className="mt-3 flex gap-2">
                  <button className="flex-1 bg-green-600 hover:bg-green-700 rounded py-2 text-white text-sm font-semibold">
                    Execute Trade
                  </button>
                  <button className="flex-1 bg-gray-700 hover:bg-gray-600 rounded py-2 text-white text-sm font-semibold">
                    Add to Watchlist
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Performance Stats */}
      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-3 text-white">Strategy Performance (Last 30 Days)</h3>
        <div className="grid grid-cols-4 gap-4">
          <div className="text-center">
            <div className="text-xs text-gray-400 mb-1">Total Signals</div>
            <div className="text-2xl font-bold text-white">42</div>
          </div>
          <div className="text-center">
            <div className="text-xs text-gray-400 mb-1">Win Rate</div>
            <div className="text-2xl font-bold text-green-400">68%</div>
          </div>
          <div className="text-center">
            <div className="text-xs text-gray-400 mb-1">Avg R:R</div>
            <div className="text-2xl font-bold text-blue-400">1:2.3</div>
          </div>
          <div className="text-center">
            <div className="text-xs text-gray-400 mb-1">Total P&L</div>
            <div className="text-2xl font-bold text-green-400">+$3,450</div>
          </div>
        </div>
      </div>

      {/* Empty State */}
      {signals.length === 0 && !scanning && (
        <div className="bg-gray-800 rounded-lg p-12 text-center">
          <Target size={48} className="mx-auto text-gray-600 mb-4" />
          <h3 className="text-lg font-semibold text-gray-400 mb-2">No Active Signals</h3>
          <p className="text-sm text-gray-500 mb-4">
            Select a strategy and click "Scan Market" to find trading opportunities
          </p>
          <p className="text-xs text-gray-600">
            Strategies are automatically evaluated based on current market conditions
          </p>
        </div>
      )}
    </div>
  );
}
