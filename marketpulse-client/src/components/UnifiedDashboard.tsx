'use client';

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { LLMChat } from './llm-chat';
import { Sparkline } from './ui/Sparkline';
import { RefreshCw, Activity, TrendingUp, TrendingDown, Clock, Globe, BarChart3, Bot } from 'lucide-react';

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

export function UnifiedDashboard() {
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [macroData, setMacroData] = useState<MacroData | null>(null);
  const [breadthData, setBreadthData] = useState<MarketBreadth | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [sessionTime, setSessionTime] = useState('');
  const [sessionCountdown, setSessionCountdown] = useState('');

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

  // Generate simple sparkline data based on price change
  // In production, this would come from historical data API
  const generateSparklineData = (currentPrice: number, change: number): number[] => {
    const points = 12; // 12 data points for smooth line
    const data: number[] = [];
    const previousPrice = currentPrice - change;
    const priceRange = Math.abs(change);

    for (let i = 0; i < points; i++) {
      const progress = i / (points - 1);
      // Create a natural-looking curve with some randomness
      const baseValue = previousPrice + (change * progress);
      const noise = (Math.random() - 0.5) * priceRange * 0.2; // 20% noise
      data.push(baseValue + noise);
    }

    // Ensure last point matches current price
    data[data.length - 1] = currentPrice;
    return data;
  };

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

  const formatBreadthValue = (value: number, type: 'ratio' | 'count' | 'large' = 'count') => {
    if (type === 'ratio') return value.toFixed(2);
    if (type === 'large') return (value / 1000000).toFixed(0) + 'M';
    return value.toLocaleString();
  };

  const getBreadthColor = (interpretation: string) => {
    const lower = interpretation.toLowerCase();
    if (lower.includes('bullish') || lower.includes('buying')) return 'text-green-400';
    if (lower.includes('bearish') || lower.includes('selling')) return 'text-red-400';
    return 'text-yellow-400';
  };

  const renderMarketInternals = () => {
    return (
      <div className="bg-gray-900/50 backdrop-blur rounded-xl border border-gray-800/50 p-4">
        <div className="flex items-center gap-2 mb-4">
          <Activity className="w-5 h-5 text-blue-400" />
          <h3 className="text-lg font-semibold text-white">Market Internals</h3>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {/* NYSE Advance/Decline */}
          <div className="bg-gray-800/50 rounded-lg p-3 hover:bg-gray-800/70 transition-colors">
            <div className="text-xs text-gray-400 mb-1">NYSE A/D Ratio</div>
            <div className="text-xl font-bold text-white">
              {breadthData?.nyse_ad_ratio ? formatBreadthValue(breadthData.nyse_ad_ratio, 'ratio') : '--'}
            </div>
            <div className="text-xs text-gray-500">
              {breadthData ? `${breadthData.nyse_advancing}↑ / ${breadthData.nyse_declining}↓` : 'Loading...'}
            </div>
          </div>

          {/* NASDAQ Advance/Decline */}
          <div className="bg-gray-800/50 rounded-lg p-3 hover:bg-gray-800/70 transition-colors">
            <div className="text-xs text-gray-400 mb-1">NASDAQ A/D Ratio</div>
            <div className="text-xl font-bold text-white">
              {breadthData?.nasdaq_ad_ratio ? formatBreadthValue(breadthData.nasdaq_ad_ratio, 'ratio') : '--'}
            </div>
            <div className="text-xs text-gray-500">
              {breadthData ? `${breadthData.nasdaq_advancing}↑ / ${breadthData.nasdaq_declining}↓` : 'Loading...'}
            </div>
          </div>

          {/* New Highs/Lows */}
          <div className="bg-gray-800/50 rounded-lg p-3 hover:bg-gray-800/70 transition-colors">
            <div className="text-xs text-gray-400 mb-1">52W High/Low</div>
            <div className="text-xl font-bold text-white">
              {breadthData ? `${breadthData.new_highs} / ${breadthData.new_lows}` : '-- / --'}
            </div>
            <div className={`text-xs font-medium ${breadthData ? getBreadthColor(breadthData.interpretation || '') : 'text-gray-500'}`}>
              {breadthData?.interpretation || 'Loading...'}
            </div>
          </div>

          {/* TICK Index */}
          <div className="bg-gray-800/50 rounded-lg p-3 hover:bg-gray-800/70 transition-colors">
            <div className="text-xs text-gray-400 mb-1">$TICK (30min avg)</div>
            <div className={`text-xl font-bold ${breadthData ? (breadthData.tick_30min_avg > 0 ? 'text-green-400' : breadthData.tick_30min_avg < 0 ? 'text-red-400' : 'text-white') : 'text-white'}`}>
              {breadthData?.tick_30min_avg ? (breadthData.tick_30min_avg > 0 ? '+' : '') + breadthData.tick_30min_avg : '--'}
            </div>
            <div className="text-xs text-gray-500">
              {breadthData ? `Current: ${breadthData.tick_value > 0 ? '+' : ''}${breadthData.tick_value}` : 'Loading...'}
            </div>
          </div>

          {/* VOLD */}
          <div className="bg-gray-800/50 rounded-lg p-3 hover:bg-gray-800/70 transition-colors">
            <div className="text-xs text-gray-400 mb-1">$VOLD (Total)</div>
            <div className={`text-xl font-bold ${breadthData ? (breadthData.total_vold > 0 ? 'text-green-400' : breadthData.total_vold < 0 ? 'text-red-400' : 'text-white') : 'text-white'}`}>
              {breadthData?.total_vold ? formatBreadthValue(breadthData.total_vold, 'large') : '--'}
            </div>
            <div className="text-xs text-gray-500">
              {breadthData ? `NYSE: ${formatBreadthValue(breadthData.nyse_vold, 'large')}` : 'Loading...'}
            </div>
          </div>

          {/* McClellan Oscillator */}
          <div className="bg-gray-800/50 rounded-lg p-3 hover:bg-gray-800/70 transition-colors">
            <div className="text-xs text-gray-400 mb-1">McClellan Osc</div>
            <div className={`text-xl font-bold ${breadthData ? (breadthData.mcclellan_oscillator > 0 ? 'text-green-400' : breadthData.mcclellan_oscillator < 0 ? 'text-red-400' : 'text-white') : 'text-white'}`}>
              {breadthData?.mcclellan_oscillator ? (breadthData.mcclellan_oscillator > 0 ? '+' : '') + breadthData.mcclellan_oscillator.toFixed(1) : '--'}
            </div>
            <div className="text-xs text-gray-500">
              {breadthData ? `Sum: ${breadthData.mcclellan_summation.toFixed(0)}` : 'Loading...'}
            </div>
          </div>
        </div>
      </div>
    );
  };

  const renderMarketSession = () => {
    const session = dashboardData?.data?.market_session || macroData?.market_session || 'Unknown';

    return (
      <div className="bg-gray-900/50 backdrop-blur rounded-xl border border-gray-800/50 p-4">
        <div className="flex items-center gap-2 mb-4">
          <Clock className="w-5 h-5 text-green-400" />
          <h3 className="text-lg font-semibold text-white">Market Session</h3>
        </div>
        <div className="space-y-3">
          <div>
            <div className="text-sm text-gray-400">Current Session</div>
            <div className="text-2xl font-bold text-green-400">{session}</div>
          </div>
          <div>
            <div className="text-sm text-gray-400">Current Time (Local)</div>
            <div className="text-lg font-mono font-semibold text-white session-timer">{sessionTime}</div>
          </div>
          <div>
            <div className="text-sm text-gray-400">Market Close In</div>
            <div className="text-lg font-mono font-semibold text-orange-400 session-timer">{sessionCountdown}</div>
          </div>
        </div>
      </div>
    );
  };

  const renderMarketBias = () => {
    const bias = dashboardData?.data?.marketBias || 'Unknown';
    const volatility = dashboardData?.data?.volatilityRegime || 'Unknown';
    const sentiment = macroData?.economic_sentiment || 'Unknown';
    const risk = macroData?.risk_appetite || 'Unknown';

    const getBiasColor = (val: string) => {
      switch (val.toLowerCase()) {
        case 'bullish': return 'text-green-400 bg-green-400/10';
        case 'bearish': return 'text-red-400 bg-red-400/10';
        case 'mixed': return 'text-yellow-400 bg-yellow-400/10';
        default: return 'text-gray-400 bg-gray-400/10';
      }
    };

    return (
      <div className="bg-gray-900/50 backdrop-blur rounded-xl border border-gray-800/50 p-4">
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp className="w-5 h-5 text-yellow-400" />
          <h3 className="text-lg font-semibold text-white">Market Sentiment</h3>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className={`rounded-lg p-3 text-center ${getBiasColor(bias)}`}>
            <div className="text-xs opacity-70 mb-1">Market Bias</div>
            <div className="text-lg font-bold">{bias}</div>
          </div>
          <div className={`rounded-lg p-3 text-center ${getBiasColor(volatility)}`}>
            <div className="text-xs opacity-70 mb-1">Volatility</div>
            <div className="text-lg font-bold">{volatility}</div>
          </div>
          <div className={`rounded-lg p-3 text-center ${getBiasColor(sentiment)}`}>
            <div className="text-xs opacity-70 mb-1">Sentiment</div>
            <div className="text-lg font-bold">{sentiment}</div>
          </div>
          <div className={`rounded-lg p-3 text-center ${getBiasColor(risk)}`}>
            <div className="text-xs opacity-70 mb-1">Risk</div>
            <div className="text-lg font-bold">{risk}</div>
          </div>
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="w-12 h-12 text-blue-400 animate-spin mx-auto mb-4" />
          <p className="text-xl text-gray-300">Loading market data...</p>
        </div>
      </div>
    );
  }

  const majorIndices = dashboardData?.data?.symbols || {};
  const macroLabels: Record<string, string> = {
    // Commodities & Indices
    'DXY': 'US Dollar',
    'TNX': '10Y Treasury',
    'CL': 'Crude Oil (WTI)',
    'CLF': 'Crude Oil Future',
    'GC': 'Gold',

    // Cryptocurrencies
    'BTC': 'Bitcoin',
    'ETH': 'Ethereum',
    'SOL': 'Solana',
    'XRP': 'Ripple',

    // Asian Markets
    'NIKKEI': 'Nikkei 225',
    'HSI': 'Hang Seng',
    'SSE': 'Shanghai Comp',
    'ASX': 'ASX 200',

    // European Markets
    'FTSE': 'FTSE 100',
    'DAX': 'DAX',
    'CAC': 'CAC 40',
    'STOXX': 'Euro Stoxx 50',

    // Forex
    'EURUSD': 'EUR/USD',
    'GBPUSD': 'GBP/USD',
    'USDJPY': 'USD/JPY',
    'AUDUSD': 'AUD/USD',
    'USDCAD': 'USD/CAD',
    'USDCHF': 'USD/CHF'
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

  const sectorData = macroData?.sector_performance || dashboardData?.data?.sector_performance || {};

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
          </div>
        </div>
      </div>

      {/* Main Dashboard Grid */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 mb-6">
        {/* Column 1: Major Indices + Market Session + Bias */}
        <div className="space-y-6">
          {renderDataTable('Major Indices', <TrendingUp className="w-5 h-5 text-blue-400" />, majorIndices, indexLabels)}
          {renderMarketSession()}
          {renderMarketBias()}
        </div>

        {/* Column 2: Commodities, Crypto, Treasuries */}
        <div className="space-y-6">
          {macroData && (() => {
            const commoditiesAndTreasury = Object.fromEntries(
              Object.entries(macroData).filter(([key]) =>
                ['DXY', 'TNX', 'CL', 'CLF', 'GC'].includes(key)
              )
            );
            return Object.keys(commoditiesAndTreasury).length > 0
              ? renderDataTable('Commodities & Treasuries', <Globe className="w-5 h-5 text-yellow-400" />, commoditiesAndTreasury as any, macroLabels)
              : null;
          })()}

          {macroData && (() => {
            const crypto = Object.fromEntries(
              Object.entries(macroData).filter(([key]) =>
                ['BTC', 'ETH', 'SOL', 'XRP'].includes(key)
              )
            );
            return Object.keys(crypto).length > 0
              ? renderDataTable('Cryptocurrencies', <Activity className="w-5 h-5 text-orange-400" />, crypto as any, macroLabels)
              : null;
          })()}

          {renderMarketInternals()}
        </div>

        {/* Column 3: Sector Performance + AI Assistant */}
        <div className="space-y-6">
          {Object.keys(sectorData).length > 0 && renderSectorPerformance(sectorData)}
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

      {/* Secondary Grid: International Markets & Forex */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Asian Markets */}
        {macroData && (() => {
          const asianMarkets = Object.fromEntries(
            Object.entries(macroData).filter(([key]) =>
              ['NIKKEI', 'HSI', 'SSE', 'ASX'].includes(key)
            )
          );
          return Object.keys(asianMarkets).length > 0
            ? renderDataTable('Asian Markets', <Globe className="w-5 h-5 text-orange-400" />, asianMarkets as any, macroLabels)
            : null;
        })()}

        {/* European Markets */}
        {macroData && (() => {
          const europeanMarkets = Object.fromEntries(
            Object.entries(macroData).filter(([key]) =>
              ['FTSE', 'DAX', 'CAC', 'STOXX'].includes(key)
            )
          );
          return Object.keys(europeanMarkets).length > 0
            ? renderDataTable('European Markets', <Globe className="w-5 h-5 text-blue-400" />, europeanMarkets as any, macroLabels)
            : null;
        })()}
      </div>

      {/* Forex Grid */}
      {macroData && (() => {
        const forex = Object.fromEntries(
          Object.entries(macroData).filter(([key]) =>
            ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF'].includes(key)
          )
        );
        return Object.keys(forex).length > 0 ? (
          <div className="mb-6">
            {renderDataTable('Forex (Major Pairs)', <Globe className="w-5 h-5 text-green-400" />, forex as any, macroLabels)}
          </div>
        ) : null;
      })()}

      {/* Footer */}
      <footer className="mt-8 pt-6 border-t border-gray-800">
        <div className="flex items-center justify-between text-sm text-gray-500">
          <div>MarketPulse v0.2.0 - Multi-column Professional Dashboard</div>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
            <span>Live Data • Refreshing every 60s</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
