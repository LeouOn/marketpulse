'use client';

import React, { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, AlertCircle, Activity, Calendar } from 'lucide-react';
import { apiFetch } from '../lib/api';

interface OptionsContract {
  strike: number;
  type: 'call' | 'put';
  bid: number;
  ask: number;
  volume: number;
  open_interest: number;
  implied_volatility: number;
  delta?: number;
  gamma?: number;
  theta?: number;
  vega?: number;
}

interface MacroContext {
  vix_level: number;
  vix_trend: string;
  skew_ratio: number;
  put_call_ratio: number;
  interpretation: string;
}

export default function OptionsFlowTab() {
  const [symbol, setSymbol] = useState('SPY');
  const [expirations, setExpirations] = useState<string[]>([]);
  const [selectedExpiration, setSelectedExpiration] = useState('');
  const [optionsChain, setOptionsChain] = useState<{ calls: OptionsContract[]; puts: OptionsContract[] } | null>(null);
  const [macroContext, setMacroContext] = useState<MacroContext | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchExpirations();
    fetchMacroContext();
  }, [symbol]);

  useEffect(() => {
    if (selectedExpiration) {
      fetchOptionsChain();
    }
  }, [selectedExpiration]);

  const fetchExpirations = async () => {
    try {
      setError(null);
      const data = await apiFetch<any>(`/options/expirations/${symbol}`);
      if (data.success && data.data.expirations.length > 0) {
        setExpirations(data.data.expirations);
        setSelectedExpiration(data.data.expirations[0]);
      }
    } catch (err) {
      console.error('Failed to fetch expirations:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch expirations');
    }
  };

  const fetchOptionsChain = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<{ success: boolean; data: { calls: OptionsContract[]; puts: OptionsContract[] } }>(
        `/options/chain/${symbol}/${selectedExpiration}?include_greeks=true`
      );
      if (data.success) {
        setOptionsChain(data.data);
      }
    } catch (err) {
      console.error('Failed to fetch options chain:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch options chain');
    } finally {
      setLoading(false);
    }
  };

  const fetchMacroContext = async () => {
    try {
      const data = await apiFetch<{ success: boolean; data: MacroContext }>('/options/macro-context');
      if (data.success) {
        setMacroContext(data.data);
      }
    } catch (err) {
      console.error('Failed to fetch macro context:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch macro context');
    }
  };

  const findUnusualActivity = (contracts: OptionsContract[]) => {
    return contracts.filter(c => c.volume > c.open_interest * 2).slice(0, 5);
  };

  return (
    <div className="space-y-2.5">
      {error && (
        <div className="p-2.5 bg-neg-dim border border-line rounded-[2px] text-[12.5px] flex items-center gap-2">
          <span className="text-neg">{error}</span>
          <button
            onClick={() => { fetchExpirations(); fetchMacroContext(); }}
            className="ml-auto underline text-neg hover:text-ink"
          >
            Retry
          </button>
        </div>
      )}

      <div className="panel">
        <div className="border-b border-line-subtle px-3 h-8 flex items-center justify-between">
          <span className="panel-title">Options Flow</span>
          <div className="flex items-center gap-1.5 text-[11px] text-ink-secondary">
            <Activity className="w-3 h-3 text-pos" />
            <span className="font-mono uppercase tracking-[0.08em]">Live Options Data</span>
          </div>
        </div>

        {/* Symbol Selector */}
        <div className="p-2.5">
          <div className="grid grid-cols-2 gap-2.5">
            <div>
              <label className="block text-[11px] uppercase tracking-[0.08em] text-ink-secondary mb-1">
                Symbol
              </label>
              <select
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="input w-full"
              >
                <option value="SPY">SPY (S&amp;P 500)</option>
                <option value="QQQ">QQQ (Nasdaq 100)</option>
                <option value="IWM">IWM (Russell 2000)</option>
                <option value="AAPL">AAPL (Apple)</option>
                <option value="MSFT">MSFT (Microsoft)</option>
                <option value="TSLA">TSLA (Tesla)</option>
                <option value="NVDA">NVDA (Nvidia)</option>
              </select>
            </div>
            <div>
              <label className="block text-[11px] uppercase tracking-[0.08em] text-ink-secondary mb-1">
                Expiration
              </label>
              <select
                value={selectedExpiration}
                onChange={(e) => setSelectedExpiration(e.target.value)}
                className="input w-full"
              >
                {expirations.map(exp => (
                  <option key={exp} value={exp}>{exp}</option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Macro Context */}
      {macroContext && (
        <div className="panel">
          <div className="border-b border-line-subtle px-3 h-8 flex items-center">
            <span className="panel-title">Market Context</span>
          </div>
          <div className="p-2.5 space-y-2.5">
            <div className="grid grid-cols-3 gap-2.5">
              <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5">
                <div className="panel-title">VIX Level</div>
                <div
                  className={`text-[15px] leading-tight mt-0.5 font-mono tabular-nums ${
                    macroContext.vix_level > 25
                      ? 'text-neg'
                      : macroContext.vix_level > 20
                      ? 'text-warn'
                      : 'text-pos'
                  }`}
                >
                  {macroContext.vix_level.toFixed(2)}
                </div>
                <div className="text-[11px] font-mono tabular-nums text-ink-secondary mt-0.5">
                  {macroContext.vix_trend}
                </div>
              </div>
              <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5">
                <div className="panel-title">Put/Call Ratio</div>
                <div className="text-[15px] leading-tight mt-0.5 font-mono tabular-nums text-ink">
                  {macroContext.put_call_ratio.toFixed(2)}
                </div>
                <div className="text-[11px] font-mono tabular-nums text-ink-secondary mt-0.5">
                  {macroContext.put_call_ratio > 1.0 ? 'Bearish' : 'Bullish'}
                </div>
              </div>
              <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5">
                <div className="panel-title">Skew</div>
                <div className="text-[15px] leading-tight mt-0.5 font-mono tabular-nums text-sel">
                  {macroContext.skew_ratio.toFixed(2)}
                </div>
                <div className="text-[11px] font-mono tabular-nums text-ink-secondary mt-0.5">
                  Put skew
                </div>
              </div>
            </div>
            <div className="bg-sel-dim border border-line rounded-[2px] px-2.5 py-1.5">
              <div className="text-[12px] text-sel">{macroContext.interpretation}</div>
            </div>
          </div>
        </div>
      )}

      {/* Unusual Activity */}
      {optionsChain && (
        <div className="panel">
          <div className="border-b border-line-subtle px-3 h-8 flex items-center gap-2">
            <AlertCircle className="w-3 h-3 text-warn" />
            <span className="panel-title">Unusual Activity (Volume &gt; 2x OI)</span>
          </div>
          <div className="p-2.5 grid grid-cols-1 md:grid-cols-2 gap-2.5">
            {/* Unusual Calls */}
            <div>
              <div className="text-[11px] uppercase tracking-[0.08em] text-ink-secondary mb-1.5">
                Calls
              </div>
              <div className="space-y-1.5">
                {findUnusualActivity(optionsChain.calls).map((contract, idx) => (
                  <div
                    key={idx}
                    className="bg-warn-dim border border-line rounded-[2px] px-2 py-1.5"
                  >
                    <div className="flex justify-between items-center">
                      <span className="text-[12.5px] font-mono tabular-nums text-ink">
                        ${contract.strike}
                      </span>
                      <span className="border border-pos rounded-[2px] px-1.5 h-5 text-[11px] font-mono inline-flex items-center text-pos">
                        CALL
                      </span>
                    </div>
                    <div className="flex justify-between text-[11px] font-mono tabular-nums text-ink-secondary mt-0.5">
                      <span>Vol {contract.volume.toLocaleString()}</span>
                      <span>OI {contract.open_interest.toLocaleString()}</span>
                    </div>
                    <div className="text-[11px] font-mono tabular-nums text-ink-muted mt-0.5">
                      IV {(contract.implied_volatility * 100).toFixed(1)}%
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Unusual Puts */}
            <div>
              <div className="text-[11px] uppercase tracking-[0.08em] text-ink-secondary mb-1.5">
                Puts
              </div>
              <div className="space-y-1.5">
                {findUnusualActivity(optionsChain.puts).map((contract, idx) => (
                  <div
                    key={idx}
                    className="bg-warn-dim border border-line rounded-[2px] px-2 py-1.5"
                  >
                    <div className="flex justify-between items-center">
                      <span className="text-[12.5px] font-mono tabular-nums text-ink">
                        ${contract.strike}
                      </span>
                      <span className="border border-neg rounded-[2px] px-1.5 h-5 text-[11px] font-mono inline-flex items-center text-neg">
                        PUT
                      </span>
                    </div>
                    <div className="flex justify-between text-[11px] font-mono tabular-nums text-ink-secondary mt-0.5">
                      <span>Vol {contract.volume.toLocaleString()}</span>
                      <span>OI {contract.open_interest.toLocaleString()}</span>
                    </div>
                    <div className="text-[11px] font-mono tabular-nums text-ink-muted mt-0.5">
                      IV {(contract.implied_volatility * 100).toFixed(1)}%
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Options Chain */}
      {loading && (
        <div className="panel">
          <div className="p-12 text-center">
            <Activity className="w-8 h-8 mx-auto text-ink-muted mb-3 animate-spin" />
            <div className="text-[12.5px] text-ink-secondary">Loading options chain…</div>
          </div>
        </div>
      )}

      {!loading && optionsChain && (
        <div className="panel">
          <div className="border-b border-line-subtle px-3 h-8 flex items-center">
            <span className="panel-title">Options Chain</span>
          </div>
          <div className="p-2.5 grid grid-cols-1 md:grid-cols-2 gap-2.5">
            {/* Calls */}
            <div>
              <div className="text-[11px] uppercase tracking-[0.08em] text-pos mb-1.5">Calls</div>
              <div className="overflow-x-auto max-h-96 overflow-y-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th className="sticky top-0 bg-surface">Strike</th>
                      <th className="num sticky top-0 bg-surface">Bid</th>
                      <th className="num sticky top-0 bg-surface">Ask</th>
                      <th className="num sticky top-0 bg-surface">Vol</th>
                      <th className="num sticky top-0 bg-surface">IV</th>
                    </tr>
                  </thead>
                  <tbody>
                    {optionsChain.calls.slice(0, 20).map((contract, idx) => (
                      <tr key={idx}>
                        <td className="num">${contract.strike}</td>
                        <td className="num">${contract.bid.toFixed(2)}</td>
                        <td className="num">${contract.ask.toFixed(2)}</td>
                        <td className="num">{contract.volume}</td>
                        <td className="num">{(contract.implied_volatility * 100).toFixed(1)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Puts */}
            <div>
              <div className="text-[11px] uppercase tracking-[0.08em] text-neg mb-1.5">Puts</div>
              <div className="overflow-x-auto max-h-96 overflow-y-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th className="sticky top-0 bg-surface">Strike</th>
                      <th className="num sticky top-0 bg-surface">Bid</th>
                      <th className="num sticky top-0 bg-surface">Ask</th>
                      <th className="num sticky top-0 bg-surface">Vol</th>
                      <th className="num sticky top-0 bg-surface">IV</th>
                    </tr>
                  </thead>
                  <tbody>
                    {optionsChain.puts.slice(0, 20).map((contract, idx) => (
                      <tr key={idx}>
                        <td className="num">${contract.strike}</td>
                        <td className="num">${contract.bid.toFixed(2)}</td>
                        <td className="num">${contract.ask.toFixed(2)}</td>
                        <td className="num">{contract.volume}</td>
                        <td className="num">{(contract.implied_volatility * 100).toFixed(1)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}

      {!loading && !optionsChain && (
        <div className="panel">
          <div className="p-12 text-center">
            <Calendar className="w-8 h-8 mx-auto text-ink-muted mb-3" />
            <div className="text-[13px] text-ink-secondary mb-1">No Options Data</div>
            <p className="text-[12px] text-ink-muted">
              Select a symbol and expiration date to view options flow
            </p>
          </div>
        </div>
      )}
    </div>
  );
}