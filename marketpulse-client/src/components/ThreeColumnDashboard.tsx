'use client';

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { LLMChat } from './llm-chat';
import { Sparkline } from './ui/Sparkline';
import {
  RefreshCw, Activity, TrendingUp, TrendingDown, Clock, Globe,
  BarChart3, Bot, Target, BarChart2, Settings, AlertCircle
} from 'lucide-react';

// Keep all the original interfaces
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
  CL?: MarketData;
  CLF?: MarketData;
  GC?: MarketData;
  BTC?: MarketData;
  ETH?: MarketData;
  SOL?: MarketData;
  XRP?: MarketData;
  market_session?: string;
  economic_sentiment?: string;
  risk_appetite?: string;
  sector_performance?: Record<string, number>;
}

interface MarketBreadth {
  nyse_advancing: number;
  nyse_declining: number;
  nyse_unchanged: number;
  nyse_ad_ratio: number;
  nyse_net_ad: number;
  nasdaq_advancing: number;
  nasdaq_declining: number;
  nasdaq_unchanged: number;
  nasdaq_ad_ratio: number;
  nasdaq_net_ad: number;
  interpretation: string;
  new_highs: number;
  new_lows: number;
  hl_ratio: number;
  net_hl: number;
  tick_value: number;
  tick_30min_avg: number;
  tick_4hr_avg: number;
  nyse_vold: number;
  nasdaq_vold: number;
  total_vold: number;
  mcclellan_oscillator: number;
  mcclellan_summation: number;
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

export function ThreeColumnDashboard() {
  const [activeTab, setActiveTab] = useState('overview');
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [macroData, setMacroData] = useState<MacroData | null>(null);
  const [breadthData, setBreadthData] = useState<MarketBreadth | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [sessionTime, setSessionTime] = useState('');
  const [sessionCountdown, setSessionCountdown] = useState('');
  const [sessionPnL] = useState(385.00);
  const dailyLimit = 1000;

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
    const interval = setInterval(fetchData, 60000);
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

      const marketClose = new Date();
      marketClose.setHours(16, 0, 0, 0);

      let diff = marketClose.getTime() - now.getTime();
      if (diff < 0) {
        diff += 24 * 60 * 60 * 1000;
      }

      const hoursLeft = Math.floor(diff / (1000 * 60 * 60));
      const minutesLeft = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
      setSessionCountdown(`${hoursLeft}h ${minutesLeft}m`);
    };

    updateSessionTimer();
    const interval = setInterval(updateSessionTimer, 1000);
    return () => clearInterval(interval);
  }, []);

  const formatPrice = (price: number, symbol: string) => {
    if (symbol.includes('-USD') || symbol === 'BTC' || symbol === 'ETH') {
      return `$${price.toLocaleString()}`;
    }
    return `$${price.toFixed(2)}`;
  };

  const formatChange = (change: number, changePct: number) => {
    const sign = change >= 0 ? '+' : '';
    return {
      value: `${sign}${change.toFixed(2)}`,
      percent: `${sign}${changePct.toFixed(2)}%`,
      color: change >= 0 ? 'text-positive' : 'text-negative',
      bgColor: change >= 0 ? 'bg-positive' : 'bg-negative'
    };
  };

  const formatVolume = (volume: number) => {
    if (volume >= 1e9) return `${(volume / 1e9).toFixed(1)}B`;
    if (volume >= 1e6) return `${(volume / 1e6).toFixed(1)}M`;
    if (volume >= 1e3) return `${(volume / 1e3).toFixed(1)}K`;
    return volume.toString();
  };

  const generateSparklineData = (currentPrice: number, change: number): number[] => {
    const points = 12;
    const data: number[] = [];
    const previousPrice = currentPrice - change;
    const priceRange = Math.abs(change);

    for (let i = 0; i < points; i++) {
      const progress = i / (points - 1);
      const baseValue = previousPrice + (change * progress);
      const noise = (Math.random() - 0.5) * priceRange * 0.2;
      data.push(baseValue + noise);
    }

    data[data.length - 1] = currentPrice;
    return data;
  };

  // Get NQ data (use QQQ as proxy)
  const nqData = dashboardData?.data?.symbols?.['qqq'] || {
    price: 0,
    change: 0,
    change_pct: 0,
    volume: 0,
    symbol: 'QQQ',
    timestamp: ''
  };

  // Market regime calculation
  const getMarketRegime = (): 'favorable' | 'mixed' | 'avoid' => {
    const bias = dashboardData?.data?.marketBias?.toLowerCase() || '';
    const volatility = dashboardData?.data?.volatilityRegime?.toLowerCase() || '';

    if (bias === 'bullish' && (volatility === 'low' || volatility === 'normal')) return 'favorable';
    if (bias === 'bearish' || volatility === 'high' || volatility === 'extreme') return 'avoid';
    return 'mixed';
  };

  const marketRegime = getMarketRegime();

  const RegimeIndicator = ({ regime }: { regime: 'favorable' | 'mixed' | 'avoid' }) => {
    const config = {
      favorable: { color: 'bg-green-500', text: 'High Confidence', desc: 'All signals aligned' },
      mixed: { color: 'bg-yellow-500', text: 'Mixed Signals', desc: 'Reduce position size' },
      avoid: { color: 'bg-red-500', text: 'Choppy Market', desc: 'Stay flat or minimal risk' }
    };

    const { color, text, desc } = config[regime];

    return (
      <div className="bg-gray-900/50 border border-gray-800/50 rounded-xl p-4">
        <div className="flex items-center gap-3 mb-2">
          <div className={`w-4 h-4 rounded-full ${color} animate-pulse`}></div>
          <span className="text-white font-semibold">{text}</span>
        </div>
        <p className="text-gray-400 text-sm">{desc}</p>
      </div>
    );
  };

  const tabs = [
    { id: 'overview', label: 'Market Overview', icon: Activity },
    { id: 'backtest', label: 'Backtests', icon: BarChart2, missing: true },
    { id: 'risk', label: 'Risk Manager', icon: Target, missing: true },
    { id: 'options', label: 'Options', icon: TrendingUp, missing: true },
    { id: 'strategy', label: 'Strategy', icon: Settings, missing: true }
  ];

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="w-12 h-12 text-blue-400 animate-spin mx-auto mb-4" />
          <p className="text-xl text-gray-300">Loading market data...</p>
        </div>
      </div>
    );
  }

  const majorIndices = dashboardData?.data?.symbols || {};
  const sectorData = macroData?.sector_performance || dashboardData?.data?.sector_performance || {};

  const renderDataTable = (title: string, icon: React.ReactNode, data: Record<string, MarketData>, labels: Record<string, string>) => {
    return (
      <div className="bg-gray-900/50 backdrop-blur rounded-xl border border-gray-800/50 p-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            {icon}
            <h3 className="text-lg font-semibold text-white">{title}</h3>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th className="text-center">Trend</th>
                <th className="text-right">Price</th>
                <th className="text-right">Change</th>
                <th className="text-right">%</th>
                <th className="text-right">Volume</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data).map(([symbol, marketData]) => {
                if (!marketData || marketData.price === 0) return null;
                const changeInfo = formatChange(marketData.change, marketData.change_pct);
                const displayLabel = labels[symbol] || symbol;
                const sparklineData = generateSparklineData(marketData.price, marketData.change);

                return (
                  <tr key={symbol} className="hover:bg-gray-800/50 transition-colors">
                    <td className="font-medium text-white">{displayLabel}</td>
                    <td className="text-center">
                      <Sparkline
                        data={sparklineData}
                        width={60}
                        height={20}
                        className="inline-block"
                      />
                    </td>
                    <td className="text-right text-white font-mono">{formatPrice(marketData.price, symbol)}</td>
                    <td className={`text-right font-mono ${changeInfo.color}`}>{changeInfo.value}</td>
                    <td className={`text-right font-mono ${changeInfo.color}`}>{changeInfo.percent}</td>
                    <td className="text-right text-gray-400 font-mono text-sm">{formatVolume(marketData.volume)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  const renderSectorPerformance = (sectorData: Record<string, number>) => {
    const sortedSectors = Object.entries(sectorData).sort(([, a], [, b]) => b - a);

    return (
      <div className="bg-gray-900/50 backdrop-blur rounded-xl border border-gray-800/50 p-4">
        <div className="flex items-center gap-2 mb-4">
          <BarChart3 className="w-5 h-5 text-purple-400" />
          <h3 className="text-lg font-semibold text-white">Sector Performance</h3>
        </div>
        <div className="space-y-2">
          {sortedSectors.map(([sector, performance], index) => {
            const isPositive = performance >= 0;
            const maxAbs = Math.max(...sortedSectors.map(([, p]) => Math.abs(p)));
            const width = (Math.abs(performance) / maxAbs) * 100;
            const isTop3 = index < 3;
            const isBottom3 = index >= sortedSectors.length - 3;

            return (
              <div key={sector}>
                <div className="flex items-center justify-between mb-1">
                  <span className={`text-sm ${isTop3 || isBottom3 ? 'font-semibold' : ''} ${
                    isTop3 ? 'text-green-400' : isBottom3 ? 'text-red-400' : 'text-gray-300'
                  }`}>
                    {sector}
                  </span>
                  <span className={`text-sm font-mono font-semibold ${isPositive ? 'text-positive' : 'text-negative'}`}>
                    {isPositive ? '+' : ''}{performance.toFixed(2)}%
                  </span>
                </div>
                <div className="sector-bar-container">
                  <div
                    className={`sector-bar ${isPositive ? 'sector-bar-positive' : 'sector-bar-negative'}`}
                    style={{ width: `${width}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const indexLabels: Record<string, string> = {
    'SPY': 'S&P 500 (SPY)',
    'spy': 'S&P 500 (SPY)',
    'QQQ': 'NASDAQ (QQQ)',
    'qqq': 'NASDAQ (QQQ)',
    'VIX': 'Volatility (VIX)',
    'vix': 'Volatility (VIX)',
    '^VIX': 'Volatility (VIX)'
  };

  const macroLabels: Record<string, string> = {
    'DXY': 'US Dollar',
    'TNX': '10Y Treasury',
    'CL': 'Crude Oil (WTI)',
    'CLF': 'Crude Oil Future',
    'GC': 'Gold',
    'BTC': 'Bitcoin',
    'ETH': 'Ethereum',
    'SOL': 'Solana',
    'XRP': 'Ripple',
  };

  return (
    <div className="min-h-screen bg-gray-950 p-4 lg:p-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl lg:text-4xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
              MarketPulse
            </h1>
            <p className="text-gray-400 text-sm mt-1">Professional Trading Dashboard</p>
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
      </div>

      {/* 3-Column Layout */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        {/* LEFT COLUMN - Command Center */}
        <div className="xl:col-span-3 space-y-6">
          {/* NQ/MNQ Hero Widget */}
          <div className="bg-gray-900/50 border border-blue-500/50 rounded-xl p-4">
            <div className="mb-2">
              <div className="text-gray-400 text-sm">NASDAQ 100</div>
              <div className="text-4xl font-bold text-white">
                {nqData.price > 0 ? formatPrice(nqData.price, 'QQQ') : '--'}
              </div>
              {nqData.price > 0 && (
                <div className={`text-lg ${nqData.change < 0 ? 'text-red-500' : 'text-green-500'}`}>
                  {nqData.change > 0 ? '+' : ''}{nqData.change.toFixed(2)} ({nqData.change_pct.toFixed(2)}%)
                </div>
              )}
            </div>

            {/* Mini indicators */}
            {breadthData && (
              <div className="grid grid-cols-3 gap-2 mt-4">
                <div className="bg-gray-800 rounded p-2 text-center">
                  <div className="text-xs text-gray-400">TICK</div>
                  <div className={`text-sm font-semibold ${
                    breadthData.tick_30min_avg > 0 ? 'text-green-400' : 'text-red-400'
                  }`}>
                    {breadthData.tick_30min_avg > 0 ? '↑' : '↓'}
                  </div>
                </div>
                <div className="bg-gray-800 rounded p-2 text-center">
                  <div className="text-xs text-gray-400">A/D</div>
                  <div className={`text-sm font-semibold ${
                    breadthData.nyse_ad_ratio > 1 ? 'text-green-400' : 'text-red-400'
                  }`}>
                    {breadthData.nyse_ad_ratio.toFixed(2)}
                  </div>
                </div>
                <div className="bg-gray-800 rounded p-2 text-center">
                  <div className="text-xs text-gray-400">VOLD</div>
                  <div className={`text-sm font-semibold ${
                    breadthData.total_vold > 0 ? 'text-green-400' : 'text-red-400'
                  }`}>
                    {breadthData.total_vold > 0 ? '↑' : '↓'}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Market Regime */}
          <RegimeIndicator regime={marketRegime} />

          {/* Quick Risk Calculator */}
          <div className="bg-gray-900/50 border border-gray-800/50 rounded-xl p-4">
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

          {/* Session Stats */}
          <div className="bg-gray-900/50 backdrop-blur rounded-xl border border-gray-800/50 p-4">
            <h3 className="text-white font-semibold mb-3 flex items-center gap-2">
              <Clock size={16} />
              Session
            </h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-400">Status:</span>
                <span className="text-green-500">{dashboardData?.data?.market_session || 'Regular Hours'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Time Left:</span>
                <span className="text-white">{sessionCountdown}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Time:</span>
                <span className="text-white font-mono">{sessionTime}</span>
              </div>
            </div>
          </div>
        </div>

        {/* CENTER COLUMN - Analysis Hub */}
        <div className="xl:col-span-6 space-y-6">
          {/* Tab Navigation */}
          <div className="bg-gray-900/50 border border-gray-800/50 rounded-xl p-1">
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
          <div className="space-y-6">
            {activeTab === 'overview' && (
              <>
                {/* Major Indices */}
                {renderDataTable('Major Indices', <TrendingUp className="w-5 h-5 text-blue-400" />, majorIndices, indexLabels)}

                {/* Commodities & Crypto */}
                {macroData && (() => {
                  const commoditiesAndCrypto = Object.fromEntries(
                    Object.entries(macroData).filter(([key]) =>
                      ['DXY', 'TNX', 'CL', 'CLF', 'GC', 'BTC', 'ETH', 'SOL', 'XRP'].includes(key)
                    )
                  );
                  return Object.keys(commoditiesAndCrypto).length > 0
                    ? renderDataTable('Commodities & Crypto', <Globe className="w-5 h-5 text-yellow-400" />, commoditiesAndCrypto as any, macroLabels)
                    : null;
                })()}

                {/* Sector Performance */}
                {Object.keys(sectorData).length > 0 && renderSectorPerformance(sectorData)}
              </>
            )}

            {(activeTab === 'backtest' || activeTab === 'risk' || activeTab === 'options' || activeTab === 'strategy') && (
              <div className="bg-gray-900/50 backdrop-blur rounded-xl border border-gray-800/50 p-6 flex flex-col items-center justify-center" style={{ minHeight: '400px' }}>
                <AlertCircle size={48} className="text-yellow-500 mb-4" />
                <h3 className="text-xl font-semibold text-white mb-2">Feature Coming Soon</h3>
                <p className="text-gray-400 text-center max-w-md">
                  This tab will show {activeTab === 'backtest' ? 'historical backtesting results' :
                  activeTab === 'risk' ? 'risk management and position sizing' :
                  activeTab === 'options' ? 'options flow and unusual activity' :
                  'strategy testing and pattern scanning'}.
                </p>
              </div>
            )}
          </div>
        </div>

        {/* RIGHT COLUMN - Context & AI */}
        <div className="xl:col-span-3 space-y-6">
          {/* AI Assistant */}
          <div className="bg-gray-900/50 backdrop-blur rounded-xl border border-gray-800/50 p-4">
            <div className="flex items-center gap-2 mb-4">
              <Bot className="w-5 h-5 text-green-400" />
              <h3 className="text-lg font-semibold text-white">AI Assistant</h3>
            </div>
            <div className="h-[500px]">
              <LLMChat marketData={dashboardData?.data} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
