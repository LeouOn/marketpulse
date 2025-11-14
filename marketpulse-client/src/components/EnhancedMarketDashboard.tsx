'use client';

import { motion } from 'framer-motion';
import { TrendingUp, TrendingDown, Activity, RefreshCw, AlertCircle, CheckCircle } from 'lucide-react';
import { DashboardData } from '@/types/market';
import { LoadingSpinner, SkeletonCard } from './ui/LoadingSpinner';

interface EnhancedMarketDashboardProps {
  data: DashboardData | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  lastUpdate: Date | null;
}

export function EnhancedMarketDashboard({ data, loading, error, onRefresh, lastUpdate }: EnhancedMarketDashboardProps) {
  const getBiasColor = (bias: string) => {
    switch (bias?.toLowerCase()) {
      case 'bullish': return 'text-green-400 bg-green-400/10';
      case 'bearish': return 'text-red-400 bg-red-400/10';
      case 'mixed': return 'text-yellow-400 bg-yellow-400/10';
      default: return 'text-gray-400 bg-gray-400/10';
    }
  };

  const getVolatilityColor = (regime: string) => {
    switch (regime?.toLowerCase()) {
      case 'extreme': return 'text-red-500 bg-red-500/10';
      case 'high': return 'text-orange-400 bg-orange-400/10';
      case 'normal': return 'text-yellow-400 bg-yellow-400/10';
      case 'low': return 'text-green-400 bg-green-400/10';
      default: return 'text-gray-400 bg-gray-400/10';
    }
  };

  const renderSymbolCard = (symbol: any, label: string, icon: React.ReactNode) => {
    if (!symbol || symbol.price === 0) {
      return (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-gray-900/50 backdrop-blur rounded-xl p-6 border border-gray-800/50"
        >
          <div className="flex items-center justify-center h-32">
            <div className="text-center">
              <div className="text-gray-500 mb-2">{icon}</div>
              <p className="text-sm text-gray-400">No {label} data</p>
            </div>
          </div>
        </motion.div>
      );
    }

    const isPositive = symbol.change >= 0;
    const TrendIcon = isPositive ? TrendingUp : TrendingDown;
    const trendColor = isPositive ? 'text-green-400' : 'text-red-400';

    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        whileHover={{ y: -5, transition: { duration: 0.2 } }}
        className="bg-gray-900/50 backdrop-blur rounded-xl p-6 border border-gray-800/50 hover:border-gray-700/50 transition-all"
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-500/10 rounded-lg">
              {icon}
            </div>
            <h3 className="text-lg font-semibold text-gray-300">{label}</h3>
          </div>
          <div className={`p-2 rounded-lg ${isPositive ? 'bg-green-500/10' : 'bg-red-500/10'}`}>
            <TrendIcon className={`w-5 h-5 ${trendColor}`} />
          </div>
        </div>

        <div className="space-y-2">
          <div className="text-3xl font-bold text-white">
            ${symbol.price.toFixed(2)}
          </div>
          <div className={`flex items-center gap-2 text-sm ${trendColor}`}>
            <span>{isPositive ? '+' : ''}{symbol.change.toFixed(2)}</span>
            <span>•</span>
            <span>{isPositive ? '+' : ''}{symbol.change_pct.toFixed(2)}%</span>
          </div>
          <div className="text-xs text-gray-500 flex items-center gap-1">
            <Activity className="w-3 h-3" />
            <span>Vol: {(symbol.volume / 1000000).toFixed(1)}M</span>
          </div>
        </div>
      </motion.div>
    );
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" text="Loading market data..." />
      </div>
    );
  }

  if (error) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="bg-red-900/20 backdrop-blur border border-red-500/30 rounded-xl p-6"
      >
        <div className="flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-400 mt-0.5" />
          <div>
            <h3 className="text-red-400 font-medium mb-1">Connection Error</h3>
            <p className="text-red-300 text-sm">{error}</p>
            <button
              onClick={onRefresh}
              className="mt-3 px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
            >
              <RefreshCw className="w-4 h-4" />
              Try Again
            </button>
          </div>
        </div>
      </motion.div>
    );
  }

  if (!data) {
    return (
      <div className="text-center text-gray-400">
        <AlertCircle className="w-12 h-12 mx-auto mb-4 opacity-50" />
        <p>No market data available</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header with status */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between"
      >
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
            <span>Live Market Data</span>
          </div>
          {data.dataSource && (
            <span className="text-xs text-gray-500 bg-gray-800 px-2 py-1 rounded">
              {data.dataSource === 'mock' ? 'Mock Data' : 'Real API'}
            </span>
          )}
        </div>

        <div className="flex items-center gap-4">
          {lastUpdate && (
            <span className="text-sm text-gray-500">
              {lastUpdate.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={onRefresh}
            className="p-2 bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors group"
          >
            <RefreshCw className="w-4 h-4 group-hover:rotate-180 transition-transform duration-500" />
          </button>
        </div>
      </motion.div>

      {/* Market Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {renderSymbolCard(data.symbols?.spy, 'S&P 500',
          <div className="w-6 h-6 text-blue-400">📈</div>)}
        {renderSymbolCard(data.symbols?.qqq, 'NASDAQ',
          <div className="w-6 h-6 text-purple-400">🚀</div>)}
        {renderSymbolCard(data.symbols?.vix, 'VIX',
          <div className="w-6 h-6 text-orange-400">📊</div>)}
      </div>

      {/* Market Analysis */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.2 }}
          className="bg-gray-900/50 backdrop-blur rounded-xl p-6 border border-gray-800/50"
        >
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-300">Market Bias</h3>
            <CheckCircle className="w-5 h-5 text-green-400" />
          </div>
          <div className={`text-2xl font-bold px-4 py-2 rounded-lg text-center ${getBiasColor(data.marketBias)}`}>
            {data.marketBias}
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.3 }}
          className="bg-gray-900/50 backdrop-blur rounded-xl p-6 border border-gray-800/50"
        >
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-300">Volatility</h3>
            <Activity className="w-5 h-5 text-yellow-400" />
          </div>
          <div className={`text-2xl font-bold px-4 py-2 rounded-lg text-center ${getVolatilityColor(data.volatilityRegime)}`}>
            {data.volatilityRegime}
          </div>
        </motion.div>
      </div>

      {/* Volume Flow */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="bg-gray-900/50 backdrop-blur rounded-xl p-6 border border-gray-800/50"
      >
        <h3 className="text-lg font-semibold text-gray-300 mb-4">Volume Flow (60min)</h3>
        <div className="grid grid-cols-2 gap-6">
          <div>
            <div className="text-3xl font-bold text-white">
              {(data.volumeFlow?.totalVolume60min / 1000000).toFixed(1)}M
            </div>
            <div className="text-sm text-gray-400">Total Volume</div>
          </div>
          <div>
            <div className="text-3xl font-bold text-white">
              {data.volumeFlow?.symbolsTracked}
            </div>
            <div className="text-sm text-gray-400">Symbols Tracked</div>
          </div>
        </div>
      </motion.div>

      {/* AI Analysis */}
      {data.aiAnalysis && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
          className="bg-gradient-to-r from-blue-900/30 to-purple-900/30 backdrop-blur rounded-xl p-6 border border-blue-800/50"
        >
          <div className="flex items-center gap-2 mb-4">
            <div className="w-6 h-6 text-blue-400">🤖</div>
            <h3 className="text-lg font-semibold text-gray-300">AI Analysis</h3>
          </div>
          <div className="text-gray-300 whitespace-pre-wrap leading-relaxed">
            {data.aiAnalysis}
          </div>
        </motion.div>
      )}
    </div>
  );
}