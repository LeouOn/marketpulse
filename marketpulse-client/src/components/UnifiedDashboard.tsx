'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import Link from 'next/link';
import { LLMChat } from './llm-chat';
import { Sparkline } from './ui/Sparkline';
import { SkeletonCard } from './ui/LoadingSpinner';
import { RefreshCw, Activity, TrendingUp, TrendingDown, Clock, Globe, BarChart3, Bot, AlertTriangle, Wifi, WifiOff } from 'lucide-react';
import { useDashboardData, useMacroData, useBreadthData } from '@/hooks/useMarketData';
import { useScreener } from '@/hooks/useScreenerData';

interface MarketData {
  symbol: string;
  price: number;
  change: number;
  change_pct: number;
  volume: number;
  timestamp: string;
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

const cardVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.05, duration: 0.3 }
  })
};

export function UnifiedDashboard() {
  const { data: dashboardData, isLoading: dashLoading, isError: dashIsError, error: dashError, refetch: refreshDashboard, dataUpdatedAt } = useDashboardData() as any;
  const { data: macroData, isLoading: macroLoading } = useMacroData() as any;
  const { data: breadthData } = useBreadthData() as any;
  const { data: gainersData } = useScreener('gainers');
  const { data: losersData } = useScreener('losers');
  const gainers = Array.isArray(gainersData) ? gainersData : (gainersData as any)?.results;
  const losers = Array.isArray(losersData) ? losersData : (losersData as any)?.results;

  const loading = (dashLoading || macroLoading) && !dashboardData;
  const error = dashIsError ? (dashError as any)?.message || 'Failed to load market data' : null;
  const lastUpdate = dashboardData ? new Date(dataUpdatedAt) : null;
  const dataSource = dashboardData?.dataSource || dashboardData?.data?.dataSource || 'unknown';

  const [sessionTime, setSessionTime] = useState('');
  const [sessionCountdown, setSessionCountdown] = useState('');

  const refreshAll = () => {
    refreshDashboard();
  };

  useEffect(() => {
    const updateSessionTimer = () => {
      const now = new Date();
      setSessionTime(now.toLocaleTimeString('en-US', { hour12: false }));

      const marketClose = new Date();
      marketClose.setHours(16, 0, 0, 0);
      let diff = marketClose.getTime() - now.getTime();
      if (diff < 0) diff += 86400000;

      const h = Math.floor(diff / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      setSessionCountdown(`${h}h ${m}m`);
    };

    updateSessionTimer();
    const interval = setInterval(updateSessionTimer, 1000);
    return () => clearInterval(interval);
  }, []);

  const formatPrice = (price: number, symbol: string) => {
    if (symbol.includes('-USD') || symbol === 'BTC' || symbol === 'ETH') {
      return `$${price.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
    }
    return `$${price.toFixed(2)}`;
  };

  const formatChange = (change: number, changePct: number) => {
    const sign = change >= 0 ? '+' : '';
    return {
      value: `${sign}${change.toFixed(2)}`,
      percent: `${sign}${changePct.toFixed(2)}%`,
      color: change >= 0 ? 'text-positive' : 'text-negative',
    };
  };

  const formatVolume = (volume: number) => {
    if (volume >= 1e9) return `${(volume / 1e9).toFixed(1)}B`;
    if (volume >= 1e6) return `${(volume / 1e6).toFixed(1)}M`;
    if (volume >= 1e3) return `${(volume / 1e3).toFixed(1)}K`;
    return volume.toString();
  };

  /** Deterministic seeded PRNG so server and client produce identical sparklines */
  const seededRandom = (seed: string) => {
    let hash = 0;
    for (let i = 0; i < seed.length; i++) {
      hash = ((hash << 5) - hash + seed.charCodeAt(i)) | 0;
    }
    let state = Math.abs(hash) || 1;
    return () => {
      state = (state * 1664525 + 1013904223) >>> 0;
      return state / 0xffffffff;
    };
  };

  const generateSparklineData = (currentPrice: number, change: number, symbol: string): number[] => {
    const points = 12;
    const data: number[] = [];
    const previousPrice = currentPrice - change;
    const priceRange = Math.abs(change) || currentPrice * 0.005;
    const rand = seededRandom(symbol);

    for (let i = 0; i < points; i++) {
      const progress = i / (points - 1);
      const baseValue = previousPrice + (change * progress);
      const noise = (rand() - 0.5) * priceRange * 0.15;
      data.push(baseValue + noise);
    }
    data[data.length - 1] = currentPrice;
    return data;
  };

  const renderDataTable = (title: string, icon: React.ReactNode, data: Record<string, MarketData>, labels: Record<string, string>, cardIndex: number) => {
    const entries = Object.entries(data).filter(([, d]) => d && d.price !== 0);
    if (entries.length === 0) return null;

    return (
      <motion.div
        custom={cardIndex}
        variants={cardVariants}
        initial="hidden"
        animate="visible"
        className="bg-gray-900 border border-gray-800 rounded-xl p-4 hover:border-gray-700 transition-colors interactive-card"
      >
        <div className="flex items-center gap-2 mb-3">
          {icon}
          <h3 className="text-sm font-medium text-gray-400">{title}</h3>
          <span className="ml-auto text-xs text-gray-600">{entries.length} symbols</span>
        </div>
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th className="text-center w-16">Trend</th>
                <th className="text-right">Price</th>
                <th className="text-right">Chg</th>
                <th className="text-right">%</th>
                <th className="text-right">Vol</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(([symbol, marketData]) => {
                const changeInfo = formatChange(marketData.change, marketData.change_pct);
                const displayLabel = labels[symbol] || symbol;
                const sparklineData = generateSparklineData(marketData.price, marketData.change, symbol);

                return (
                  <tr key={symbol} className="group">
                    <td className="font-medium text-white text-sm">
                      {displayLabel}
                    </td>
                    <td className="text-center">
                      <Sparkline data={sparklineData} width={56} height={18} className="inline-block opacity-70 group-hover:opacity-100 transition-opacity" />
                    </td>
                    <td className="text-right text-white font-mono text-sm">{formatPrice(marketData.price, symbol)}</td>
                    <td className={`text-right font-mono text-sm ${changeInfo.color}`}>{changeInfo.value}</td>
                    <td className={`text-right font-mono text-sm font-semibold ${changeInfo.color}`}>{changeInfo.percent}</td>
                    <td className="text-right text-gray-500 font-mono text-xs">{formatVolume(marketData.volume)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </motion.div>
    );
  };

  const renderSectorPerformance = (sectorData: Record<string, number>, cardIndex: number) => {
    const sortedSectors = Object.entries(sectorData).sort(([, a], [, b]) => b - a);
    if (sortedSectors.length === 0) return null;

    return (
      <motion.div
        custom={cardIndex}
        variants={cardVariants}
        initial="hidden"
        animate="visible"
        className="bg-gray-900 border border-gray-800 rounded-xl p-4 hover:border-gray-700 transition-colors interactive-card"
      >
        <div className="flex items-center gap-2 mb-3">
          <BarChart3 className="w-4 h-4 text-purple-400" />
          <h3 className="text-sm font-medium text-gray-400">Sector Performance</h3>
        </div>
        <div className="space-y-1.5">
          {sortedSectors.map(([sector, perf], idx) => {
            const isPositive = perf >= 0;
            const maxAbs = Math.max(...sortedSectors.map(([, p]) => Math.abs(p)));
            const width = maxAbs ? (Math.abs(perf) / maxAbs) * 100 : 0;
            const isTop = idx < 3;
            const isBottom = idx >= sortedSectors.length - 3;

            return (
              <div key={sector} className="group hover:bg-gray-800/30 rounded px-1 py-0.5 transition-colors">
                <div className="flex items-center justify-between mb-0.5">
                  <span className={`text-xs ${isTop ? 'font-bold text-green-400' : isBottom ? 'font-bold text-red-400' : 'text-gray-400'}`}>
                    {sector}
                  </span>
                  <span className={`text-xs font-mono font-semibold ${isPositive ? 'text-positive' : 'text-negative'}`}>
                    {isPositive ? '+' : ''}{perf.toFixed(2)}%
                  </span>
                </div>
                <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${width}%` }}
                    transition={{ duration: 0.6, delay: idx * 0.03 }}
                    className={`h-full rounded-full ${isPositive ? 'bg-gradient-to-r from-emerald-900 to-emerald-400' : 'bg-gradient-to-r from-red-900 to-red-400'}`}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </motion.div>
    );
  };

  const renderMarketInternals = (cardIndex: number) => {
    const metrics = [
      { label: 'NYSE A/D Ratio', value: breadthData?.nyse_ad_ratio, format: 'ratio' as const, sub: breadthData ? `${breadthData.nyse_advancing}↑ / ${breadthData.nyse_declining}↓` : '' },
      { label: 'NASDAQ A/D Ratio', value: breadthData?.nasdaq_ad_ratio, format: 'ratio' as const, sub: breadthData ? `${breadthData.nasdaq_advancing}↑ / ${breadthData.nasdaq_declining}↓` : '' },
      { label: '52W High/Low', value: breadthData?.hl_ratio, format: 'ratio' as const, sub: breadthData ? `${breadthData.new_highs}H / ${breadthData.new_lows}L` : '', raw: breadthData ? `${breadthData.new_highs} / ${breadthData.new_lows}` : '--' },
      { label: '$TICK (30m)', value: breadthData?.tick_30min_avg, format: 'count' as const, sub: breadthData ? `Now: ${breadthData.tick_value > 0 ? '+' : ''}${breadthData.tick_value}` : '', signed: true },
      { label: '$VOLD', value: breadthData?.total_vold, format: 'large' as const, sub: breadthData ? `NYSE: ${(breadthData.nyse_vold / 1e6).toFixed(0)}M` : '', signed: true },
      { label: 'McClellan Osc', value: breadthData?.mcclellan_oscillator, format: 'count' as const, sub: breadthData ? `Sum: ${breadthData.mcclellan_summation.toFixed(0)}` : '', signed: true },
    ];

    return (
      <motion.div
        custom={cardIndex}
        variants={cardVariants}
        initial="hidden"
        animate="visible"
        className="bg-gray-900 border border-gray-800 rounded-xl p-4 hover:border-gray-700 transition-colors interactive-card"
      >
        <div className="flex items-center gap-2 mb-3">
          <Activity className="w-4 h-4 text-blue-400" />
          <h3 className="text-sm font-medium text-gray-400">Market Internals</h3>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {metrics.map(({ label, value, format, sub, raw, signed }) => {
            const numVal = value as number | undefined;
            const displayVal = raw
              || (numVal !== undefined && numVal !== 0
                ? (format === 'ratio' ? numVal.toFixed(2) : format === 'large' ? `${(numVal / 1e6).toFixed(0)}M` : numVal.toFixed(1))
                : '--');
            const prefix = signed && numVal !== undefined && numVal > 0 ? '+' : '';
            const valColor = numVal === undefined ? 'text-gray-600' : numVal > 0 ? 'text-green-400' : numVal < 0 ? 'text-red-400' : 'text-white';

            return (
              <div key={label} className="bg-gray-800/40 rounded-lg p-2.5 hover:bg-gray-800/60 transition-colors">
                <div className="text-[10px] text-gray-500 mb-0.5">{label}</div>
                <div className={`text-lg font-bold font-mono ${valColor}`}>
                  {raw ? raw : `${prefix}${displayVal}`}
                </div>
                {sub && <div className="text-[10px] text-gray-600">{sub}</div>}
              </div>
            );
          })}
        </div>
      </motion.div>
    );
  };

  const renderMarketSession = (cardIndex: number) => {
    const session = dashboardData?.market_session || macroData?.market_session || 'Unknown';
    const isLive = session === 'US Regular';

    return (
      <motion.div
        custom={cardIndex}
        variants={cardVariants}
        initial="hidden"
        animate="visible"
        className="bg-gray-900 border border-gray-800 rounded-xl p-4 hover:border-gray-700 transition-colors interactive-card"
      >
        <div className="flex items-center gap-2 mb-3">
          <Clock className="w-4 h-4 text-green-400" />
          <h3 className="text-sm font-medium text-gray-400">Session</h3>
          {isLive && <span className="ml-auto flex items-center gap-1 text-[10px] text-green-400"><span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse" />LIVE</span>}
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <div className="text-[10px] text-gray-500">Session</div>
            <div className={`text-sm font-bold ${isLive ? 'text-green-400' : 'text-gray-300'}`}>{session}</div>
          </div>
          <div>
            <div className="text-[10px] text-gray-500">Local</div>
            <div className="text-sm font-mono font-semibold text-white session-timer">{sessionTime}</div>
          </div>
          <div>
            <div className="text-[10px] text-gray-500">Close In</div>
            <div className="text-sm font-mono font-semibold text-orange-400 session-timer">{sessionCountdown}</div>
          </div>
        </div>
      </motion.div>
    );
  };

  const renderMarketBias = (cardIndex: number) => {
    const bias = dashboardData?.marketBias || 'Unknown';
    const volatility = dashboardData?.volatilityRegime || 'Unknown';
    const sentiment = macroData?.economic_sentiment || 'Unknown';
    const risk = macroData?.risk_appetite || 'Unknown';

    const getStyle = (val: string) => {
      const v = val.toLowerCase();
      if (['bullish', 'risk on', 'very bullish'].includes(v)) return 'bg-green-500/10 text-green-400 border-green-500/20';
      if (['bearish', 'risk off', 'very bearish'].includes(v)) return 'bg-red-500/10 text-red-400 border-red-500/20';
      if (['high', 'extreme'].includes(v)) return 'bg-orange-500/10 text-orange-400 border-orange-500/20';
      if (['low', 'normal'].includes(v)) return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
      return 'bg-gray-500/10 text-gray-400 border-gray-500/20';
    };

    const items = [
      { label: 'Bias', value: bias },
      { label: 'Volatility', value: volatility },
      { label: 'Sentiment', value: sentiment },
      { label: 'Risk', value: risk },
    ];

    return (
      <motion.div
        custom={cardIndex}
        variants={cardVariants}
        initial="hidden"
        animate="visible"
        className="bg-gray-900 border border-gray-800 rounded-xl p-4 hover:border-gray-700 transition-colors interactive-card"
      >
        <div className="flex items-center gap-2 mb-3">
          <TrendingUp className="w-4 h-4 text-yellow-400" />
          <h3 className="text-sm font-medium text-gray-400">Sentiment</h3>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {items.map(({ label, value }) => (
            <div key={label} className={`rounded-lg px-3 py-2 text-center border ${getStyle(value)}`}>
              <div className="text-[10px] opacity-60">{label}</div>
              <div className="text-sm font-bold">{value}</div>
            </div>
          ))}
        </div>
      </motion.div>
    );
  };

  // --- Loading state with skeleton ---
  if (loading) {
    return (
    <div className="p-4 lg:p-6 h-full">
        <div className="mb-6">
          <div className="h-10 w-48 bg-gray-800 rounded-lg animate-pulse" />
        </div>
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      </div>
    );
  }

  // --- Error state with retry ---
  if (error && !dashboardData) {
    return (
      <div className="flex items-center justify-center p-4">
        <div className="text-center max-w-md">
          <AlertTriangle className="w-16 h-16 text-red-400 mx-auto mb-4" />
          <h2 className="text-2xl font-bold text-white mb-2">Connection Failed</h2>
          <p className="text-gray-400 mb-4">{error}</p>
          <button
            onClick={refreshAll}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white font-medium transition-colors"
          >
            <RefreshCw className="w-4 h-4 inline mr-2" />
            Retry
          </button>
        </div>
      </div>
    );
  }

  const majorIndices = dashboardData?.symbols || {};
  const macroLabels: Record<string, string> = {
    'DXY': 'US Dollar', 'TNX': '10Y Treasury', 'CL': 'Crude Oil', 'CLF': 'Crude Oil Fut',
    'GC': 'Gold', 'BTC': 'Bitcoin', 'ETH': 'Ethereum', 'SOL': 'Solana', 'XRP': 'Ripple',
    'NIKKEI': 'Nikkei 225', 'HSI': 'Hang Seng', 'SSE': 'Shanghai', 'ASX': 'ASX 200',
    'FTSE': 'FTSE 100', 'DAX': 'DAX', 'CAC': 'CAC 40', 'STOXX': 'Euro Stoxx',
    'EURUSD': 'EUR/USD', 'GBPUSD': 'GBP/USD', 'USDJPY': 'USD/JPY',
    'AUDUSD': 'AUD/USD', 'USDCAD': 'USD/CAD', 'USDCHF': 'USD/CHF'
  };
  const indexLabels: Record<string, string> = {
    'SPY': 'S&P 500', 'spy': 'S&P 500', 'QQQ': 'NASDAQ', 'qqq': 'NASDAQ',
    'VIX': 'VIX', 'vix': 'VIX', '^VIX': 'VIX'
  };
  const sectorData = macroData?.sector_performance || dashboardData?.sector_performance || {};
  const isMock = dataSource === 'mock';

  return (
    <div className="p-4 lg:p-6">
      {/* Data source banner */}
      <AnimatePresence>
        {isMock && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="mb-4 bg-yellow-900/30 border border-yellow-600/30 rounded-lg px-4 py-2.5 flex items-center gap-3"
          >
            <AlertTriangle className="w-4 h-4 text-yellow-400 flex-shrink-0" />
            <p className="text-yellow-200 text-xs">
              <strong>Mock Data</strong> &mdash; Live data unavailable. Showing simulated prices.
            </p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Data quality warning banner */}
      <AnimatePresence>
        {dashboardData?.dataQuality === 'poor' && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="mb-4 bg-red-900/30 border border-red-600/30 rounded-lg px-4 py-2.5 flex items-center gap-3"
          >
            <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
            <p className="text-red-200 text-xs">
              <strong>Data Quality Issues</strong> &mdash; {dashboardData?.qualityIssues?.join('; ') || 'Validation failed'}
            </p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Stale data warning */}
      <AnimatePresence>
        {dashboardData?.freshnessStatus === 'stale' && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="mb-4 bg-orange-900/30 border border-orange-600/30 rounded-lg px-4 py-2.5 flex items-center gap-3"
          >
            <Clock className="w-4 h-4 text-orange-400 flex-shrink-0" />
            <p className="text-orange-200 text-xs">
              <strong>Stale Data</strong> &mdash; Data is {dashboardData?.dataAgeSeconds ? `${Math.floor(dashboardData.dataAgeSeconds / 60)}m old` : 'old'}. Prices may be outdated.
            </p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Connection error toast */}
      <AnimatePresence>
        {error && dashboardData && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="mb-4 bg-red-900/30 border border-red-600/30 rounded-lg px-4 py-2.5 flex items-center gap-3"
          >
            <WifiOff className="w-4 h-4 text-red-400 flex-shrink-0" />
            <p className="text-red-200 text-xs">Refresh failed: {error}. Showing cached data.</p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl lg:text-3xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
              MarketPulse
            </h1>
            <p className="text-gray-500 text-xs mt-0.5">Real-time Market Dashboard</p>
          </div>
          <div className="flex items-center gap-3">
            {dashboardData?.dataQuality && dashboardData.dataQuality !== 'unknown' && (
              <span className={`px-2 py-1 rounded text-xs font-medium ${
                dashboardData.dataQuality === 'good' ? 'bg-green-900/50 text-green-400 border border-green-700/30' :
                dashboardData.dataQuality === 'partial' ? 'bg-yellow-900/50 text-yellow-400 border border-yellow-700/30' :
                'bg-red-900/50 text-red-400 border border-red-700/30'
              }`}>
                {dashboardData.dataQuality.toUpperCase()} QUALITY
              </span>
            )}
            {lastUpdate && (
              <span className="text-xs text-gray-600 hidden sm:block">
                {lastUpdate.toLocaleTimeString()}
              </span>
            )}
            <button
              onClick={refreshAll}
              className="p-2 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors border border-gray-700"
              title="Refresh"
            >
              <RefreshCw className="w-4 h-4 text-gray-300" />
            </button>
          </div>
        </div>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 mb-4">
        {/* Col 1 */}
        <div className="space-y-4">
          {renderDataTable('Major Indices', <TrendingUp className="w-4 h-4 text-blue-400" />, majorIndices, indexLabels, 0)}
          {renderMarketSession(1)}
          {renderMarketBias(2)}
        </div>

        {/* Col 2 */}
        <div className="space-y-4">
          {macroData && (() => {
            const c = Object.fromEntries(Object.entries(macroData).filter(([k]) => ['DXY', 'TNX', 'CL', 'CLF', 'GC'].includes(k)));
            return Object.keys(c).length > 0 ? renderDataTable('Commodities & Rates', <Globe className="w-4 h-4 text-yellow-400" />, c as any, macroLabels, 1) : null;
          })()}
          {macroData && (() => {
            const c = Object.fromEntries(Object.entries(macroData).filter(([k]) => ['BTC', 'ETH', 'SOL', 'XRP'].includes(k)));
            return Object.keys(c).length > 0 ? renderDataTable('Crypto', <Activity className="w-4 h-4 text-orange-400" />, c as any, macroLabels, 2) : null;
          })()}
          {renderMarketInternals(3)}
        </div>

        {/* Col 3 */}
        <div className="space-y-4">
          {Object.keys(sectorData).length > 0 && renderSectorPerformance(sectorData, 1)}

          {/* Top Movers */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 hover:border-gray-700 transition-colors">
            <h3 className="text-sm font-medium text-gray-400 mb-3 flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-emerald-400" />
              Top Movers
            </h3>
            <div className="space-y-2">
              {gainers?.slice(0, 3).map((item: any) => (
                <Link key={item.symbol} href={`/chart/${item.symbol}`}
                  className="flex items-center justify-between py-1.5 px-2 rounded hover:bg-gray-800 transition-colors">
                  <span className="font-medium text-sm">{item.symbol}</span>
                  <span className="text-emerald-400 text-sm">+{item.change_pct?.toFixed(2)}%</span>
                </Link>
              ))}
            </div>
            <div className="border-t border-gray-800 mt-2 pt-2 space-y-2">
              {losers?.slice(0, 3).map((item: any) => (
                <Link key={item.symbol} href={`/chart/${item.symbol}`}
                  className="flex items-center justify-between py-1.5 px-2 rounded hover:bg-gray-800 transition-colors">
                  <span className="font-medium text-sm">{item.symbol}</span>
                  <span className="text-red-400 text-sm">{item.change_pct?.toFixed(2)}%</span>
                </Link>
              ))}
            </div>
          </div>

          <motion.div
            custom={4}
            variants={cardVariants}
            initial="hidden"
            animate="visible"
            className="bg-gray-900 border border-gray-800 rounded-xl p-4 hover:border-gray-700 transition-colors flex flex-col"
          >
            <div className="flex items-center gap-2 mb-3">
              <Bot className="w-4 h-4 text-green-400" />
              <h3 className="text-sm font-medium text-gray-400">AI Assistant</h3>
            </div>
            <div className="flex-1 min-h-[420px]">
              <LLMChat marketData={dashboardData} />
            </div>
          </motion.div>
        </div>
      </div>

      {/* International Markets */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        {macroData && (() => {
          const m = Object.fromEntries(Object.entries(macroData).filter(([k]) => ['NIKKEI', 'HSI', 'SSE', 'ASX'].includes(k)));
          return Object.keys(m).length > 0 ? renderDataTable('Asian Markets', <Globe className="w-4 h-4 text-orange-400" />, m as any, macroLabels, 5) : null;
        })()}
        {macroData && (() => {
          const m = Object.fromEntries(Object.entries(macroData).filter(([k]) => ['FTSE', 'DAX', 'CAC', 'STOXX'].includes(k)));
          return Object.keys(m).length > 0 ? renderDataTable('European Markets', <Globe className="w-4 h-4 text-blue-400" />, m as any, macroLabels, 6) : null;
        })()}
      </div>

      {macroData && (() => {
        const f = Object.fromEntries(Object.entries(macroData).filter(([k]) => ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF'].includes(k)));
        return Object.keys(f).length > 0 ? <div className="mb-4">{renderDataTable('Forex', <Globe className="w-4 h-4 text-green-400" />, f as any, macroLabels, 7)}</div> : null;
      })()}

      {/* Footer */}
        <footer className="mt-6 pt-4 border-t border-gray-800/50">
          <div className="flex items-center justify-between text-xs text-gray-600">
            <div className="flex items-center gap-2">
              <Wifi className={`w-3 h-3 ${isMock ? 'text-yellow-500' : 'text-green-500'}`} />
              <span>{isMock ? 'Mock Data' : 'Live'} &bull; 60s refresh</span>
              {dashboardData?.freshnessStatus && (
                <span className={`ml-2 ${dashboardData.freshnessStatus === 'fresh' ? 'text-green-600' : 'text-orange-600'}`}>
                  ({dashboardData.freshnessStatus})
                </span>
              )}
            </div>
            <div>MarketPulse v0.2.0</div>
          </div>
        </footer>
    </div>
  );
}
