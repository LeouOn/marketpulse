'use client';

import React, { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, AlertCircle, BarChart2, Activity, Settings, Target, RefreshCw, Clock, Bot } from 'lucide-react';
import RiskManagerTab from './RiskManagerTab';

// ==================== TYPES ====================

interface MarketData {
  symbol: string;
  price: number;
  change: number;
  change_pct: number;
  volume: number;
  timestamp: string;
}

interface DashboardData {
  success: boolean;
  data: {
    marketBias?: string;
    volatilityRegime?: string;
    symbols?: Record<string, MarketData>;
    volumeFlow?: {
      total_volume_60min: number;
      symbols_tracked: number;
    };
    market_session?: string;
    sector_performance?: Record<string, number>;
  };
}

interface MacroData {
  DXY?: MarketData;
  TNX?: MarketData;
  VIX?: MarketData;
  market_session?: string;
  economic_sentiment?: string;
  risk_appetite?: string;
  sector_performance?: Record<string, number>;
}

interface MarketBreadth {
  nyse_ad_ratio: number;
  tick_30min_avg: number;
  tick_value: number;
  total_vold: number;
  mcclellan_oscillator: number;
  interpretation: string;
}

interface BacktestResults {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  profit_factor: number;
  sharpe_ratio: number;
  max_drawdown: number;
  total_return: number;
}

// ==================== MAIN COMPONENT ====================

export default function MarketPulseRefactoredDashboard() {
  const [activeTab, setActiveTab] = useState('overview');
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);

  // Data state
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [macroData, setMacroData] = useState<MacroData | null>(null);
  const [breadthData, setBreadthData] = useState<MarketBreadth | null>(null);
  const [backtestResults, setBacktestResults] = useState<BacktestResults | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [sessionTime, setSessionTime] = useState('');
  const [sessionCountdown, setSessionCountdown] = useState('');

  // Sample P&L data (would come from real trading system)
  const [sessionPnL, setSessionPnL] = useState(385.00);
  const dailyLimit = 1000;

  // Fetch all data
  const fetchData = async () => {
    try {
      const [dashboardResponse, macroResponse, breadthResponse] = await Promise.all([
        fetch('http://localhost:8000/api/market/dashboard'),
        fetch('http://localhost:8000/api/market/macro'),
        fetch('http://localhost:8000/api/market/breadth')
      ]);

      const dashboard = await dashboardResponse.json();
      const macro = await macroResponse.json();
      const breadth = await breadthResponse.json();

      setDashboardData(dashboard);
      setMacroData(macro.data || macro);
      setBreadthData(breadth.data || null);
      setLastUpdate(new Date());
      setLoading(false);
    } catch (err) {
      console.error('Failed to fetch data:', err);
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, []);

  // Update session timer every second
  useEffect(() => {
    const updateSessionTimer = () => {
      const now = new Date();
      const hours = now.getHours();
      const minutes = now.getMinutes();
      const seconds = now.getSeconds();

      setSessionTime(`${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`);

      // Calculate countdown to market close (4:00 PM ET = 16:00)
      const marketClose = new Date();
      marketClose.setHours(16, 0, 0, 0);

      let diff = marketClose.getTime() - now.getTime();
      if (diff < 0) {
        diff += 24 * 60 * 60 * 1000; // Next day
      }

      const hoursLeft = Math.floor(diff / (1000 * 60 * 60));
      const minutesLeft = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
      setSessionCountdown(`${hoursLeft}h ${minutesLeft}m`);
    };

    updateSessionTimer();
    const interval = setInterval(updateSessionTimer, 1000);
    return () => clearInterval(interval);
  }, []);

  // Get NQ data
  const nqData = dashboardData?.data?.symbols?.['qqq'] || {
    price: 20423.50,
    change: -87.25,
    change_pct: -0.43,
    volume: 0
  };

  // Determine market regime
  const getMarketRegime = (): 'favorable' | 'mixed' | 'avoid' => {
    const bias = dashboardData?.data?.marketBias?.toLowerCase() || '';
    const volatility = dashboardData?.data?.volatilityRegime?.toLowerCase() || '';

    if (bias === 'bullish' && volatility === 'low') return 'favorable';
    if (bias === 'bearish' || volatility === 'high') return 'avoid';
    return 'mixed';
  };

  const marketRegime = getMarketRegime();

  const tabs = [
    { id: 'overview', label: 'Market Overview', icon: Activity },
    { id: 'backtest', label: 'Backtests', icon: BarChart2, missing: false },
    { id: 'risk', label: 'Risk Manager', icon: Target, missing: false }, // Now implemented!
    { id: 'options', label: 'Options Flow', icon: TrendingUp, missing: true },
    { id: 'strategy', label: 'Strategy Test', icon: Settings, missing: true }
  ];

  // ==================== COMPONENTS ====================

  const RegimeIndicator = ({ regime }: { regime: 'favorable' | 'mixed' | 'avoid' }) => {
    const config = {
      favorable: { color: 'bg-green-500', text: 'High Confidence', desc: 'All signals aligned' },
      mixed: { color: 'bg-yellow-500', text: 'Mixed Signals', desc: 'Reduce position size' },
      avoid: { color: 'bg-red-500', text: 'Choppy Market', desc: 'Stay flat or minimal risk' }
    };

    const { color, text, desc } = config[regime];

    return (
      <div className="bg-gray-900 border border-gray-700 rounded-lg p-4">
        <div className="flex items-center gap-3 mb-2">
          <div className={`w-4 h-4 rounded-full ${color} animate-pulse`}></div>
          <span className="text-white font-semibold">{text}</span>
        </div>
        <p className="text-gray-400 text-sm">{desc}</p>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="w-12 h-12 text-blue-400 animate-spin mx-auto mb-4" />
          <p className="text-xl text-gray-300">Loading market data...</p>
        </div>
      </div>
    );
  }

  const sectorData = macroData?.sector_performance || dashboardData?.data?.sector_performance || {};

  return (
    <div className="min-h-screen bg-black text-white p-4">
      {/* Header */}
      <div className="mb-6 flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold">MarketPulse</h1>
          <p className="text-gray-400 text-sm">Professional Trading Dashboard</p>
        </div>
        <div className="flex items-center gap-4">
          {lastUpdate && (
            <span className="text-sm text-gray-500 hidden sm:block">
              Updated: {lastUpdate.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={fetchData}
            disabled={loading}
            className="p-2 bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors"
            title="Refresh data"
          >
            <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <div className="text-right">
            <div className="text-sm text-gray-400">Session P&L</div>
            <div className={`text-2xl font-bold ${sessionPnL >= 0 ? 'text-green-500' : 'text-red-500'}`}>
              {sessionPnL >= 0 ? '+' : ''}${sessionPnL.toFixed(2)}
            </div>
            <div className="text-xs text-gray-500">Daily Limit: ${dailyLimit}</div>
          </div>
        </div>
      </div>

      {/* 3-Column Layout */}
      <div className="grid grid-cols-12 gap-4">

        {/* LEFT COLUMN - Command Center */}
        <div className={`${leftCollapsed ? 'col-span-1' : 'col-span-3'} space-y-4 transition-all`}>

          {!leftCollapsed && (
            <>
              {/* NQ/MNQ Hero Widget */}
              <div className="bg-gray-900 border border-blue-500 rounded-lg p-4">
                <div className="flex justify-between items-start mb-3">
                  <div>
                    <div className="text-gray-400 text-sm">NASDAQ 100 (QQQ)</div>
                    <div className="text-4xl font-bold text-white">
                      ${nqData.price.toFixed(2)}
                    </div>
                    <div className={`text-lg ${nqData.change < 0 ? 'text-red-500' : 'text-green-500'}`}>
                      {nqData.change > 0 ? '+' : ''}{nqData.change.toFixed(2)} ({nqData.change_pct.toFixed(2)}%)
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-xs text-gray-500">VIX</div>
                    <div className="text-sm text-gray-300">
                      {macroData?.VIX?.price.toFixed(2) || '--'}
                    </div>
                  </div>
                </div>

                {/* Mini indicators */}
                <div className="grid grid-cols-3 gap-2 mt-4">
                  <div className="bg-gray-800 rounded p-2 text-center">
                    <div className="text-xs text-gray-400">TICK</div>
                    <div className={`text-sm font-semibold ${
                      breadthData?.tick_30min_avg && breadthData.tick_30min_avg > 0 ? 'text-green-400' : 'text-red-400'
                    }`}>
                      {breadthData?.tick_30min_avg ? (breadthData.tick_30min_avg > 0 ? '↑' : '↓') : '--'}
                    </div>
                  </div>
                  <div className="bg-gray-800 rounded p-2 text-center">
                    <div className="text-xs text-gray-400">A/D</div>
                    <div className={`text-sm font-semibold ${
                      breadthData?.nyse_ad_ratio && breadthData.nyse_ad_ratio > 1 ? 'text-green-400' : 'text-red-400'
                    }`}>
                      {breadthData?.nyse_ad_ratio ? breadthData.nyse_ad_ratio.toFixed(2) : '--'}
                    </div>
                  </div>
                  <div className="bg-gray-800 rounded p-2 text-center">
                    <div className="text-xs text-gray-400">VOLD</div>
                    <div className={`text-sm font-semibold ${
                      breadthData?.total_vold && breadthData.total_vold > 0 ? 'text-green-400' : 'text-red-400'
                    }`}>
                      {breadthData?.total_vold ? (breadthData.total_vold > 0 ? '↑' : '↓') : '--'}
                    </div>
                  </div>
                </div>
              </div>

              {/* Market Regime */}
              <RegimeIndicator regime={marketRegime} />

              {/* Quick Risk Calculator */}
              <div className="bg-gray-900 border border-gray-700 rounded-lg p-4">
                <h3 className="text-white font-semibold mb-3 flex items-center gap-2">
                  <Target size={16} />
                  Position Calculator
                </h3>

                <div className="space-y-3">
                  <div>
                    <label className="text-xs text-gray-400">Risk per Trade</label>
                    <div className="bg-gray-800 rounded px-3 py-2 text-lg font-semibold text-white">
                      $250.00
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-xs text-gray-400">Stop Distance</label>
                      <input
                        type="number"
                        placeholder="Points"
                        className="w-full bg-gray-800 rounded px-2 py-1 text-white text-sm"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-400">R:R Ratio</label>
                      <input
                        type="number"
                        placeholder="2.0"
                        defaultValue="2.0"
                        className="w-full bg-gray-800 rounded px-2 py-1 text-white text-sm"
                      />
                    </div>
                  </div>

                  <div className="bg-blue-900 bg-opacity-30 border border-blue-600 rounded p-2">
                    <div className="text-xs text-gray-400">Max Contracts (MNQ)</div>
                    <div className="text-2xl font-bold text-blue-400">4</div>
                  </div>
                </div>
              </div>

              {/* Active Position (if in trade) */}
              <div className="bg-gray-900 border border-green-600 rounded-lg p-4">
                <h3 className="text-white font-semibold mb-3">Active Position</h3>
                <div className="text-center py-4 text-gray-500 text-sm">
                  No active positions
                </div>
              </div>
            </>
          )}
        </div>

        {/* CENTER COLUMN - Analysis Hub */}
        <div className="col-span-6 space-y-4">

          {/* Tab Navigation */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-1">
            <div className="flex gap-1">
              {tabs.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded transition-all relative ${
                    activeTab === tab.id
                      ? 'bg-blue-600 text-white'
                      : 'text-gray-400 hover:text-white hover:bg-gray-800'
                  }`}
                >
                  <tab.icon size={16} />
                  <span className="text-sm">{tab.label}</span>
                  {tab.missing && (
                    <span className="absolute -top-1 -right-1 w-2 h-2 bg-red-500 rounded-full"></span>
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Tab Content */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6 min-h-[600px]">
            {activeTab === 'overview' && (
              <OverviewTab
                dashboardData={dashboardData}
                macroData={macroData}
                breadthData={breadthData}
                sectorData={sectorData}
              />
            )}

            {activeTab === 'backtest' && (
              <BacktestTab />
            )}

            {activeTab === 'risk' && (
              <RiskManagerTab />
            )}

            {activeTab === 'options' && (
              <PlaceholderTab
                title="Options Flow Missing"
                description="This would show unusual options activity, dark pool prints, and gamma exposure."
              />
            )}

            {activeTab === 'strategy' && (
              <PlaceholderTab
                title="Strategy Tester Missing"
                description="Build hypothesis testing, pattern scanning, and custom indicator combinations here."
              />
            )}
          </div>
        </div>

        {/* RIGHT COLUMN - Context & Tools */}
        <div className={`${rightCollapsed ? 'col-span-1' : 'col-span-3'} space-y-4 transition-all`}>

          {!rightCollapsed && (
            <>
              {/* AI Assistant - Collapsed */}
              <div className="bg-gray-900 border border-gray-700 rounded-lg p-4">
                <h3 className="text-white font-semibold mb-3 flex items-center gap-2">
                  <Bot size={16} />
                  AI Assistant
                </h3>
                <div className="space-y-2">
                  <button className="w-full bg-blue-600 hover:bg-blue-700 rounded py-2 text-sm">
                    Analyze Current Setup
                  </button>
                  <button className="w-full bg-gray-700 hover:bg-gray-600 rounded py-2 text-sm">
                    Similar Patterns
                  </button>
                  <button className="w-full bg-gray-700 hover:bg-gray-600 rounded py-2 text-sm">
                    What's Driving This?
                  </button>
                </div>
              </div>

              {/* Market Calendar */}
              <div className="bg-gray-900 border border-gray-700 rounded-lg p-4">
                <h3 className="text-white font-semibold mb-3">Today's Events</h3>
                <div className="space-y-2">
                  <div className="text-sm">
                    <div className="text-gray-400">8:30 AM</div>
                    <div className="text-white">Retail Sales</div>
                  </div>
                  <div className="text-sm">
                    <div className="text-gray-400">10:00 AM</div>
                    <div className="text-white">Consumer Sentiment</div>
                  </div>
                </div>
              </div>

              {/* Watchlist */}
              <div className="bg-gray-900 border border-gray-700 rounded-lg p-4">
                <h3 className="text-white font-semibold mb-3">Watchlist</h3>
                <div className="space-y-2">
                  {dashboardData?.data?.symbols && Object.entries(dashboardData.data.symbols)
                    .filter(([symbol]) => ['SPY', 'AAPL', 'NVDA'].includes(symbol.toUpperCase()))
                    .slice(0, 3)
                    .map(([symbol, data]) => (
                      <div key={symbol} className="flex justify-between items-center text-sm">
                        <span className="text-gray-300">{symbol.toUpperCase()}</span>
                        <span className={data.change_pct >= 0 ? 'text-green-500' : 'text-red-500'}>
                          {data.change_pct >= 0 ? '+' : ''}{data.change_pct.toFixed(1)}%
                        </span>
                      </div>
                    ))}
                </div>
              </div>

              {/* Session Stats */}
              <div className="bg-gray-900 border border-gray-700 rounded-lg p-4">
                <h3 className="text-white font-semibold mb-3">Session Stats</h3>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-400">Session:</span>
                    <span className="text-green-500">
                      {dashboardData?.data?.market_session || 'Regular Hours'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Time Left:</span>
                    <span className="text-white">{sessionCountdown}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Trades:</span>
                    <span className="text-white">0 / 5 max</span>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ==================== TAB COMPONENTS ====================

function OverviewTab({ dashboardData, macroData, breadthData, sectorData }: any) {
  const symbols = dashboardData?.data?.symbols || {};

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-white">Market Overview</h2>

      {/* Major Indices - Condensed */}
      <div className="grid grid-cols-3 gap-3">
        {['SPY', 'QQQ', 'DIA'].map(symbol => {
          const data = symbols[symbol.toLowerCase()];
          if (!data) return null;

          return (
            <div key={symbol} className="bg-gray-800 rounded p-3">
              <div className="text-xs text-gray-400">{symbol}</div>
              <div className="text-xl font-bold">${data.price.toFixed(2)}</div>
              <div className={`text-sm ${data.change_pct >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                {data.change_pct >= 0 ? '+' : ''}{data.change_pct.toFixed(2)}%
              </div>
            </div>
          );
        })}
      </div>

      {/* Market Internals Cards */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-gray-800 rounded p-3">
          <div className="text-xs text-gray-400">NYSE TICK</div>
          <div className={`text-2xl font-bold ${
            breadthData?.tick_30min_avg > 0 ? 'text-green-400' : 'text-red-400'
          }`}>
            {breadthData?.tick_30min_avg || '--'}
          </div>
        </div>
        <div className="bg-gray-800 rounded p-3">
          <div className="text-xs text-gray-400">VIX</div>
          <div className="text-2xl font-bold text-yellow-400">
            {macroData?.VIX?.price.toFixed(2) || '--'}
          </div>
        </div>
        <div className="bg-gray-800 rounded p-3">
          <div className="text-xs text-gray-400">ADV/DEC</div>
          <div className={`text-2xl font-bold ${
            breadthData?.nyse_ad_ratio > 1 ? 'text-green-400' : 'text-red-400'
          }`}>
            {breadthData?.nyse_ad_ratio?.toFixed(2) || '--'}
          </div>
        </div>
      </div>

      {/* Sector Performance */}
      {Object.keys(sectorData).length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-300 mb-3">Sector Performance</h3>
          <div className="space-y-2">
            {Object.entries(sectorData)
              .sort(([, a]: any, [, b]: any) => b - a)
              .map(([name, value]: any) => (
                <div key={name} className="flex items-center gap-2">
                  <div className="w-32 text-xs text-gray-400 truncate">{name}</div>
                  <div className="flex-1 bg-gray-800 rounded-full h-6 relative overflow-hidden">
                    <div
                      className={`h-full ${value > 0 ? 'bg-green-600' : 'bg-red-600'}`}
                      style={{ width: `${Math.min(Math.abs(value) * 20, 100)}%` }}
                    ></div>
                    <span className="absolute inset-0 flex items-center justify-end pr-2 text-xs font-semibold">
                      {value > 0 ? '+' : ''}{value.toFixed(2)}%
                    </span>
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}

function BacktestTab() {
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<BacktestResults | null>(null);

  const runBacktest = async () => {
    setLoading(true);
    try {
      const response = await fetch('http://localhost:8000/api/backtest/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: 'NQ',
          start_date: '2024-01-01',
          end_date: '2024-11-15',
          initial_capital: 10000,
          contracts: 1,
          interval: '5m'
        })
      });

      const data = await response.json();
      if (data.success) {
        setResults(data.data);
      }
    } catch (err) {
      console.error('Backtest failed:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white">Backtest Results</h2>
        <button
          onClick={runBacktest}
          disabled={loading}
          className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded text-sm disabled:opacity-50"
        >
          {loading ? 'Running...' : 'Run Backtest'}
        </button>
      </div>

      {results ? (
        <div className="space-y-4">
          {/* Performance Metrics Grid */}
          <div className="grid grid-cols-4 gap-4">
            <div className="bg-gray-800 rounded p-4">
              <div className="text-xs text-gray-400">Win Rate</div>
              <div className="text-2xl font-bold text-green-400">
                {results.win_rate.toFixed(1)}%
              </div>
            </div>
            <div className="bg-gray-800 rounded p-4">
              <div className="text-xs text-gray-400">Profit Factor</div>
              <div className="text-2xl font-bold text-blue-400">
                {results.profit_factor.toFixed(2)}
              </div>
            </div>
            <div className="bg-gray-800 rounded p-4">
              <div className="text-xs text-gray-400">Sharpe Ratio</div>
              <div className="text-2xl font-bold text-purple-400">
                {results.sharpe_ratio.toFixed(2)}
              </div>
            </div>
            <div className="bg-gray-800 rounded p-4">
              <div className="text-xs text-gray-400">Max Drawdown</div>
              <div className="text-2xl font-bold text-red-400">
                {results.max_drawdown.toFixed(1)}%
              </div>
            </div>
          </div>

          {/* Trade Summary */}
          <div className="bg-gray-800 rounded p-4">
            <h3 className="text-sm font-semibold mb-3">Trade Summary</h3>
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <span className="text-gray-400">Total Trades:</span>
                <span className="ml-2 text-white font-semibold">{results.total_trades}</span>
              </div>
              <div>
                <span className="text-gray-400">Winners:</span>
                <span className="ml-2 text-green-400 font-semibold">{results.winning_trades}</span>
              </div>
              <div>
                <span className="text-gray-400">Losers:</span>
                <span className="ml-2 text-red-400 font-semibold">{results.losing_trades}</span>
              </div>
            </div>
          </div>

          {/* Returns */}
          <div className="bg-gray-800 rounded p-4">
            <h3 className="text-sm font-semibold mb-2">Total Return</h3>
            <div className={`text-4xl font-bold ${results.total_return >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {results.total_return >= 0 ? '+' : ''}{results.total_return.toFixed(2)}%
            </div>
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center h-64">
          <BarChart2 size={48} className="text-gray-600 mb-4" />
          <p className="text-gray-400">Click "Run Backtest" to test your FVG + Divergence strategy</p>
        </div>
      )}
    </div>
  );
}

function PlaceholderTab({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-full">
      <AlertCircle size={48} className="text-yellow-500 mb-4" />
      <h3 className="text-xl font-semibold text-white mb-2">{title}</h3>
      <p className="text-gray-400 text-center max-w-md">{description}</p>
    </div>
  );
}
