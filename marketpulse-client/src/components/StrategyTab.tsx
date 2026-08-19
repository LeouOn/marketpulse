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

const STATUS_TONE = {
  active: { text: 'text-pos', border: 'border-pos' },
  testing: { text: 'text-warn', border: 'border-warn' },
  disabled: { text: 'text-ink-muted', border: 'border-line' },
} as const;

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
    <div className="space-y-2.5">
      <div className="panel">
        <div className="border-b border-line-subtle px-3 h-8 flex items-center justify-between">
          <span className="panel-title">Strategy Testing</span>
          <div className="flex items-center gap-1.5 text-[11px] text-ink-secondary">
            <Settings className="w-3 h-3 text-sel" />
            <span className="font-mono uppercase tracking-[0.08em]">Pattern Scanner</span>
          </div>
        </div>

        {/* Strategy Selector — flat panel rows */}
        <div className="p-2.5">
          <div className="text-[11px] uppercase tracking-[0.08em] text-ink-secondary mb-1.5">
            Active Strategies
          </div>
          <div className="space-y-1.5">
            {strategies.map(strategy => {
              const tone = STATUS_TONE[strategy.status];
              const isSelected = selectedStrategy === strategy.id;
              return (
                <button
                  key={strategy.id}
                  onClick={() => setSelectedStrategy(strategy.id)}
                  className={`w-full text-left bg-surface-raised border rounded-[2px] px-2.5 py-1.5 transition-colors ${
                    isSelected
                      ? 'border-sel'
                      : 'border-line-subtle hover:border-line'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[13px] font-semibold text-ink">{strategy.name}</span>
                    <span
                      className={`border rounded-[2px] px-1.5 h-5 text-[11px] font-mono inline-flex items-center ${tone.border} ${tone.text}`}
                    >
                      {strategy.status.toUpperCase()}
                    </span>
                  </div>
                  <p className="text-[11px] text-ink-secondary mt-0.5">{strategy.description}</p>
                  <div className="flex items-center gap-4 text-[11px] font-mono tabular-nums mt-1">
                    <span className="text-ink-muted">
                      Win Rate <span className="text-pos">{strategy.win_rate}%</span>
                    </span>
                    <span className="text-ink-muted">
                      R:R <span className="text-sel">{strategy.risk_reward}</span>
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Strategy Details */}
      {currentStrategy && (
        <div className="panel">
          <div className="border-b border-line-subtle px-3 h-8 flex items-center">
            <span className="panel-title">Strategy Conditions</span>
          </div>
          <div className="p-2.5 space-y-3">
            <div className="space-y-1.5">
              {currentStrategy.conditions.map((condition, idx) => (
                <div key={idx} className="flex items-center gap-2 text-[12.5px]">
                  <CheckCircle className="w-3 h-3 text-pos" />
                  <span className="text-ink-secondary">{condition}</span>
                </div>
              ))}
            </div>

            <div className="pt-2 border-t border-line-subtle">
              <button
                onClick={scanMarket}
                disabled={scanning}
                className="btn btn-primary w-full"
              >
                {scanning ? (
                  <>
                    <Activity className="w-3 h-3 animate-spin" />
                    Scanning Market…
                  </>
                ) : (
                  <>
                    <Target className="w-3 h-3" />
                    Scan for {currentStrategy.name} Setups
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Signals — flat panel rows */}
      {signals.length > 0 && (
        <div className="panel">
          <div className="border-b border-line-subtle px-3 h-8 flex items-center gap-2">
            <AlertCircle className="w-3 h-3 text-pos" />
            <span className="panel-title">Active Signals ({signals.length})</span>
          </div>
          <div className="p-2.5 space-y-2">
            {signals.map((signal, idx) => {
              const confidenceTone =
                signal.confidence >= 80 ? 'text-pos' :
                signal.confidence >= 65 ? 'text-warn' :
                'text-ink-muted';
              return (
                <div
                  key={idx}
                  className="bg-surface-raised border border-line-subtle rounded-[2px] p-2.5"
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-[14px] font-bold text-ink font-mono tabular-nums">
                        {signal.symbol}
                      </span>
                      <span className="border border-sel rounded-[2px] px-1.5 h-5 text-[11px] font-mono inline-flex items-center text-sel">
                        {signal.signal_type}
                      </span>
                    </div>
                    <div className="text-right">
                      <div className="text-[11px] uppercase tracking-[0.08em] text-ink-secondary">
                        Confidence
                      </div>
                      <div className={`text-[14px] font-mono tabular-nums ${confidenceTone}`}>
                        {signal.confidence}%
                      </div>
                    </div>
                  </div>

                  <p className="text-[12px] text-ink-secondary mb-2">{signal.setup_description}</p>

                  <div className="grid grid-cols-4 gap-2">
                    <div>
                      <div className="text-[10px] uppercase tracking-[0.08em] text-ink-muted">Entry</div>
                      <div className="text-[13px] font-mono tabular-nums text-ink">
                        {signal.entry_price.toLocaleString()}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] uppercase tracking-[0.08em] text-ink-muted">Stop</div>
                      <div className="text-[13px] font-mono tabular-nums text-neg">
                        {signal.stop_loss.toLocaleString()}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] uppercase tracking-[0.08em] text-ink-muted">Target</div>
                      <div className="text-[13px] font-mono tabular-nums text-pos">
                        {signal.take_profit.toLocaleString()}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] uppercase tracking-[0.08em] text-ink-muted">R:R</div>
                      <div className="text-[13px] font-mono tabular-nums text-sel">
                        1:{signal.risk_reward_ratio.toFixed(1)}
                      </div>
                    </div>
                  </div>

                  <div className="mt-2 grid grid-cols-2 gap-2">
                    <button className="btn btn-primary">Execute Trade</button>
                    <button className="btn">Add to Watchlist</button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Performance Stats — mono tile strip */}
      <div className="panel">
        <div className="border-b border-line-subtle px-3 h-8 flex items-center">
          <span className="panel-title">Strategy Performance (Last 30 Days)</span>
        </div>
        <div className="p-2.5 grid grid-cols-4 gap-2.5">
          <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5">
            <div className="panel-title">Total Signals</div>
            <div className="text-[15px] leading-tight mt-0.5 font-mono tabular-nums text-ink">
              42
            </div>
          </div>
          <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5">
            <div className="panel-title">Win Rate</div>
            <div className="text-[15px] leading-tight mt-0.5 font-mono tabular-nums text-pos">
              68%
            </div>
          </div>
          <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5">
            <div className="panel-title">Avg R:R</div>
            <div className="text-[15px] leading-tight mt-0.5 font-mono tabular-nums text-sel">
              1:2.3
            </div>
          </div>
          <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5">
            <div className="panel-title">Total P&amp;L</div>
            <div className="text-[15px] leading-tight mt-0.5 font-mono tabular-nums text-pos">
              +$3,450
            </div>
          </div>
        </div>
      </div>

      {/* Empty State */}
      {signals.length === 0 && !scanning && (
        <div className="panel">
          <div className="p-12 text-center">
            <Target className="w-8 h-8 mx-auto text-ink-muted mb-3" />
            <div className="text-[13px] text-ink-secondary mb-1.5">No Active Signals</div>
            <p className="text-[12px] text-ink-muted mb-3">
              Select a strategy and click "Scan Market" to find trading opportunities
            </p>
            <p className="text-[11px] text-ink-muted font-mono">
              Strategies are automatically evaluated based on current market conditions
            </p>
          </div>
        </div>
      )}
    </div>
  );
}