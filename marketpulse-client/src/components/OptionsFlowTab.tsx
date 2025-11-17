'use client';

import React, { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, AlertCircle, DollarSign, Activity, Calendar } from 'lucide-react';

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
      const response = await fetch(`http://localhost:8000/api/options/expirations/${symbol}`);
      const data = await response.json();
      if (data.success && data.data.expirations.length > 0) {
        setExpirations(data.data.expirations);
        setSelectedExpiration(data.data.expirations[0]); // Select first expiration
      }
    } catch (err) {
      console.error('Failed to fetch expirations:', err);
    }
  };

  const fetchOptionsChain = async () => {
    setLoading(true);
    try {
      const response = await fetch(
        `http://localhost:8000/api/options/chain/${symbol}/${selectedExpiration}?include_greeks=true`
      );
      const data = await response.json();
      if (data.success) {
        setOptionsChain(data.data);
      }
    } catch (err) {
      console.error('Failed to fetch options chain:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchMacroContext = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/options/macro-context');
      const data = await response.json();
      if (data.success) {
        setMacroContext(data.data);
      }
    } catch (err) {
      console.error('Failed to fetch macro context:', err);
    }
  };

  const findUnusualActivity = (contracts: OptionsContract[]) => {
    return contracts.filter(c => c.volume > c.open_interest * 2).slice(0, 5);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white">Options Flow</h2>
        <div className="flex items-center gap-2">
          <Activity size={16} className="text-green-400" />
          <span className="text-xs text-gray-400">Live Options Data</span>
        </div>
      </div>

      {/* Symbol Selector */}
      <div className="bg-gray-800 rounded-lg p-4">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Symbol</label>
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-white"
            >
              <option value="SPY">SPY (S&P 500)</option>
              <option value="QQQ">QQQ (Nasdaq 100)</option>
              <option value="IWM">IWM (Russell 2000)</option>
              <option value="AAPL">AAPL (Apple)</option>
              <option value="MSFT">MSFT (Microsoft)</option>
              <option value="TSLA">TSLA (Tesla)</option>
              <option value="NVDA">NVDA (Nvidia)</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Expiration</label>
            <select
              value={selectedExpiration}
              onChange={(e) => setSelectedExpiration(e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-white"
            >
              {expirations.map(exp => (
                <option key={exp} value={exp}>{exp}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Macro Context */}
      {macroContext && (
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3 text-white">Market Context</h3>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <div className="text-xs text-gray-400 mb-1">VIX Level</div>
              <div className={`text-2xl font-bold ${
                macroContext.vix_level > 25 ? 'text-red-400' :
                macroContext.vix_level > 20 ? 'text-yellow-400' :
                'text-green-400'
              }`}>
                {macroContext.vix_level.toFixed(2)}
              </div>
              <div className="text-xs text-gray-500 mt-1">{macroContext.vix_trend}</div>
            </div>
            <div>
              <div className="text-xs text-gray-400 mb-1">Put/Call Ratio</div>
              <div className="text-2xl font-bold text-white">
                {macroContext.put_call_ratio.toFixed(2)}
              </div>
              <div className="text-xs text-gray-500 mt-1">
                {macroContext.put_call_ratio > 1.0 ? 'Bearish' : 'Bullish'}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-400 mb-1">Skew</div>
              <div className="text-2xl font-bold text-blue-400">
                {macroContext.skew_ratio.toFixed(2)}
              </div>
              <div className="text-xs text-gray-500 mt-1">Put skew</div>
            </div>
          </div>
          <div className="mt-3 p-3 bg-blue-900/20 border border-blue-500/30 rounded">
            <div className="text-xs text-blue-300">{macroContext.interpretation}</div>
          </div>
        </div>
      )}

      {/* Unusual Activity */}
      {optionsChain && (
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3 text-white flex items-center gap-2">
            <AlertCircle size={16} className="text-yellow-400" />
            Unusual Activity (Volume &gt; 2x OI)
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Unusual Calls */}
            <div>
              <div className="text-xs text-gray-400 mb-2">Calls</div>
              <div className="space-y-2">
                {findUnusualActivity(optionsChain.calls).map((contract, idx) => (
                  <div key={idx} className="bg-gray-900 rounded p-2">
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-white font-semibold">${contract.strike}</span>
                      <span className="text-xs text-green-400">CALL</span>
                    </div>
                    <div className="flex justify-between text-xs text-gray-400 mt-1">
                      <span>Vol: {contract.volume.toLocaleString()}</span>
                      <span>OI: {contract.open_interest.toLocaleString()}</span>
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      IV: {(contract.implied_volatility * 100).toFixed(1)}%
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Unusual Puts */}
            <div>
              <div className="text-xs text-gray-400 mb-2">Puts</div>
              <div className="space-y-2">
                {findUnusualActivity(optionsChain.puts).map((contract, idx) => (
                  <div key={idx} className="bg-gray-900 rounded p-2">
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-white font-semibold">${contract.strike}</span>
                      <span className="text-xs text-red-400">PUT</span>
                    </div>
                    <div className="flex justify-between text-xs text-gray-400 mt-1">
                      <span>Vol: {contract.volume.toLocaleString()}</span>
                      <span>OI: {contract.open_interest.toLocaleString()}</span>
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      IV: {(contract.implied_volatility * 100).toFixed(1)}%
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
        <div className="bg-gray-800 rounded-lg p-12 text-center">
          <Activity size={48} className="mx-auto text-gray-600 mb-4 animate-spin" />
          <p className="text-gray-400">Loading options chain...</p>
        </div>
      )}

      {!loading && optionsChain && (
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3 text-white">Options Chain</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Calls */}
            <div>
              <div className="text-xs text-gray-400 mb-2 font-semibold">CALLS</div>
              <div className="overflow-x-auto max-h-96 overflow-y-auto">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-gray-800 text-gray-400 border-b border-gray-700">
                    <tr>
                      <th className="text-left pb-2">Strike</th>
                      <th className="text-right pb-2">Bid</th>
                      <th className="text-right pb-2">Ask</th>
                      <th className="text-right pb-2">Vol</th>
                      <th className="text-right pb-2">IV</th>
                    </tr>
                  </thead>
                  <tbody className="text-gray-300">
                    {optionsChain.calls.slice(0, 20).map((contract, idx) => (
                      <tr key={idx} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                        <td className="py-1.5 font-mono">${contract.strike}</td>
                        <td className="text-right py-1.5 font-mono">${contract.bid.toFixed(2)}</td>
                        <td className="text-right py-1.5 font-mono">${contract.ask.toFixed(2)}</td>
                        <td className="text-right py-1.5">{contract.volume}</td>
                        <td className="text-right py-1.5">{(contract.implied_volatility * 100).toFixed(1)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Puts */}
            <div>
              <div className="text-xs text-gray-400 mb-2 font-semibold">PUTS</div>
              <div className="overflow-x-auto max-h-96 overflow-y-auto">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-gray-800 text-gray-400 border-b border-gray-700">
                    <tr>
                      <th className="text-left pb-2">Strike</th>
                      <th className="text-right pb-2">Bid</th>
                      <th className="text-right pb-2">Ask</th>
                      <th className="text-right pb-2">Vol</th>
                      <th className="text-right pb-2">IV</th>
                    </tr>
                  </thead>
                  <tbody className="text-gray-300">
                    {optionsChain.puts.slice(0, 20).map((contract, idx) => (
                      <tr key={idx} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                        <td className="py-1.5 font-mono">${contract.strike}</td>
                        <td className="text-right py-1.5 font-mono">${contract.bid.toFixed(2)}</td>
                        <td className="text-right py-1.5 font-mono">${contract.ask.toFixed(2)}</td>
                        <td className="text-right py-1.5">{contract.volume}</td>
                        <td className="text-right py-1.5">{(contract.implied_volatility * 100).toFixed(1)}%</td>
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
        <div className="bg-gray-800 rounded-lg p-12 text-center">
          <Calendar size={48} className="mx-auto text-gray-600 mb-4" />
          <h3 className="text-lg font-semibold text-gray-400 mb-2">No Options Data</h3>
          <p className="text-sm text-gray-500">
            Select a symbol and expiration date to view options flow
          </p>
        </div>
      )}
    </div>
  );
}
