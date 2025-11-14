'use client';

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
// Custom icon components
const ActivityIcon = () => (
  <div className="w-5 h-5 bg-blue-400 rounded-full" />
);

const TrendingUpIcon = () => (
  <div className="w-5 h-5 bg-green-400 rounded-sm" style={{clipPath: 'polygon(0 100%, 50% 0%, 100% 50%)'}} />
);

const TrendingDownIcon = () => (
  <div className="w-5 h-5 bg-red-400 rounded-sm" style={{clipPath: 'polygon(0 0%, 50% 100%, 100% 50%)'}} />
);

const BarChartIcon = () => (
  <div className="w-5 h-5 bg-purple-400 rounded flex gap-0.5 p-1">
    <div className="bg-white w-1 h-3 rounded-sm"></div>
    <div className="bg-white w-1 h-5 rounded-sm"></div>
    <div className="bg-white w-1 h-2 rounded-sm"></div>
  </div>
);

const AlertIcon = () => (
  <div className="w-5 h-5 bg-yellow-400 rounded-full flex items-center justify-center text-white font-bold">!</div>
);

const TargetIcon = () => (
  <div className="w-5 h-5 border-2 border-red-400 rounded-full flex items-center justify-center">
    <div className="w-1 h-1 bg-red-400 rounded-full"></div>
  </div>
);

const ClockIcon = () => (
  <div className="w-5 h-5 border-2 border-gray-400 rounded-full flex items-center justify-center">
    <div className="w-2 h-0.5 bg-gray-400 rounded-sm"></div>
  </div>
);

const RefreshIcon = () => (
  <div className="w-5 h-5 border-2 border-blue-400 rounded-full" />
);

const SignalIcon = () => (
  <div className="w-5 h-5 bg-green-400 rounded flex items-center justify-center gap-1 p-1">
    <div className="bg-white w-1 h-1 rounded-full"></div>
    <div className="bg-white w-1 h-1 rounded-full"></div>
  </div>
);
import { useDashboardData } from '@/hooks/useMarketData';
import { LoadingSpinner } from './ui/LoadingSpinner';

interface OHLCAnalysis {
  symbol: string;
  timestamp: string;
  timeframes: {
    [key: string]: {
      current_price: number;
      price_change: number;
      price_change_pct: number;
      trend: {
        direction: string;
        strength: string;
        momentum: number;
      };
      indicators: {
        atr: number;
        sma_20?: number;
        sma_50?: number;
      };
      support_levels: Array<{ price: number; strength: number }>;
      resistance_levels: Array<{ price: number; strength: number }>;
      patterns: Array<{
        name: string;
        signal: string;
        strength: string;
      }>;
    };
  };
  overall_trend: string;
  overall_strength: number;
  key_levels: {
    support: Array<{ price: number; strength: number; confirmations: number }>;
    resistance: Array<{ price: number; strength: number; confirmations: number }>;
  };
  signals: Array<{
    type: string;
    direction: string;
    strength: string;
    reasoning: string;
    confidence: number;
  }>;
}

export function OHLCAnalysisDashboard() {
  const [analysisData, setAnalysisData] = useState<OHLCAnalysis | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState<string>('SPY');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const symbols = ['SPY', 'QQQ', 'BTC', 'ETH', 'VIX'];

  const fetchAnalysis = async (symbol: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(`http://localhost:8000/api/market/ohlc-analysis/${symbol}`);
      const data = await response.json();

      if (data.success) {
        setAnalysisData(data.data);
      } else {
        setError(data.error || 'Failed to fetch analysis');
      }
    } catch (err) {
      setError('Network error while fetching analysis');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchAnalysis(selectedSymbol);
  }, [selectedSymbol]);

  const getTrendColor = (trend: string) => {
    switch (trend.toLowerCase()) {
      case 'bullish':
      case 'strongly_bullish':
        return 'text-green-400';
      case 'bearish':
      case 'strongly_bearish':
        return 'text-red-400';
      default:
        return 'text-yellow-400';
    }
  };

  const getTrendIcon = (trend: string) => {
    if (trend.toLowerCase().includes('bullish')) {
      return <TrendingUpIcon />;
    } else if (trend.toLowerCase().includes('bearish')) {
      return <TrendingDownIcon />;
    }
    return <ActivityIcon />;
  };

  const getStrengthColor = (strength: string) => {
    switch (strength.toLowerCase()) {
      case 'strong':
        return 'bg-green-500/20 border-green-500/50';
      case 'moderate':
        return 'bg-yellow-500/20 border-yellow-500/50';
      default:
        return 'bg-gray-500/20 border-gray-500/50';
    }
  };

  const getSignalColor = (signal: string) => {
    if (signal.toLowerCase().includes('bullish')) {
      return 'bg-green-500/10 border-green-500/30 text-green-400';
    } else if (signal.toLowerCase().includes('bearish')) {
      return 'bg-red-500/10 border-red-500/30 text-red-400';
    }
    return 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400';
  };

  if (isLoading && !analysisData) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" text="Loading OHLC analysis..." />
      </div>
    );
  }

  if (error && !analysisData) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="bg-red-900/20 backdrop-blur border border-red-500/30 rounded-xl p-6"
      >
        <div className="flex items-start gap-3">
          <AlertIcon />
          <div>
            <h3 className="text-red-400 font-medium mb-1">Analysis Unavailable</h3>
            <p className="text-red-300 text-sm mb-3">{error}</p>
            <button
              onClick={() => fetchAnalysis(selectedSymbol)}
              className="px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
            >
              <RefreshIcon />
              Retry
            </button>
          </div>
        </div>
      </motion.div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between"
      >
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-500/10 rounded-lg">
            <BarChartIcon />
          </div>
          <div>
            <h2 className="text-2xl font-bold text-white">OHLC Technical Analysis</h2>
            <p className="text-gray-400 text-sm">Multi-timeframe candlestick analysis and trend detection</p>
          </div>
        </div>

        {/* Symbol Selector */}
        <div className="flex items-center gap-4">
          <div className="flex bg-gray-800/50 rounded-lg p-1">
            {symbols.map(symbol => (
              <button
                key={symbol}
                onClick={() => setSelectedSymbol(symbol)}
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                  selectedSymbol === symbol
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-400 hover:text-white hover:bg-gray-700/50'
                }`}
              >
                {symbol}
              </button>
            ))}
          </div>

          <button
            onClick={() => fetchAnalysis(selectedSymbol)}
            disabled={isLoading}
            className="p-2 bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors disabled:opacity-50"
          >
            <div className={isLoading ? 'animate-spin' : ''}>
              <RefreshIcon />
            </div>
          </button>
        </div>
      </motion.div>

      {analysisData && (
        <>
          {/* Overall Trend Summary */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="grid grid-cols-1 md:grid-cols-3 gap-6"
          >
            <motion.div
              className="bg-gray-900/50 backdrop-blur rounded-xl p-6 border border-gray-800/50"
              whileHover={{ y: -5, transition: { duration: 0.2 } }}
            >
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-300">Overall Trend</h3>
                {getTrendIcon(analysisData.overall_trend)}
              </div>
              <div className={`text-2xl font-bold mb-2 ${getTrendColor(analysisData.overall_trend)}`}>
                {analysisData.overall_trend.replace('_', ' ')}
              </div>
              <div className="text-sm text-gray-400">
                Strength: {(analysisData.overall_strength * 100).toFixed(1)}%
              </div>
              <div className="mt-4 w-full bg-gray-700 rounded-full h-2">
                <div
                  className="bg-blue-500 h-2 rounded-full transition-all duration-500"
                  style={{ width: `${analysisData.overall_strength * 100}%` }}
                />
              </div>
            </motion.div>

            <motion.div
              className="bg-gray-900/50 backdrop-blur rounded-xl p-6 border border-gray-800/50"
              whileHover={{ y: -5, transition: { duration: 0.2 } }}
            >
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-300">Current Price</h3>
                <TargetIcon />
              </div>
              {Object.values(analysisData.timeframes).length > 0 && (
                <>
                  <div className="text-2xl font-bold text-white mb-2">
                    ${Object.values(analysisData.timeframes)[0]?.current_price.toFixed(2)}
                  </div>
                  <div className="text-sm text-gray-400">
                    Last updated: {new Date(analysisData.timestamp).toLocaleTimeString()}
                  </div>
                </>
              )}
            </motion.div>

            <motion.div
              className="bg-gray-900/50 backdrop-blur rounded-xl p-6 border border-gray-800/50"
              whileHover={{ y: -5, transition: { duration: 0.2 } }}
            >
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-300">Active Signals</h3>
                <SignalIcon />
              </div>
              <div className="text-2xl font-bold text-white mb-2">
                {analysisData.signals.length}
              </div>
              <div className="space-y-1">
                {analysisData.signals.slice(0, 3).map((signal, index) => (
                  <div key={index} className="text-xs text-gray-400 truncate">
                    {signal.type}: {signal.reasoning}
                  </div>
                ))}
              </div>
            </motion.div>
          </motion.div>

          {/* Timeframe Analysis */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="bg-gray-900/50 backdrop-blur rounded-xl p-6 border border-gray-800/50"
          >
            <h3 className="text-lg font-semibold text-gray-300 mb-4">Multi-Timeframe Analysis</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {Object.entries(analysisData.timeframes).map(([tf, data]) => (
                <motion.div
                  key={tf}
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: 0.2 }}
                  className={`p-4 rounded-lg border ${getStrengthColor(data.trend.strength)}`}
                >
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-sm font-medium text-gray-300">{tf.toUpperCase()}</span>
                    {getTrendIcon(data.trend.direction)}
                  </div>
                  <div className={`text-lg font-bold mb-2 ${getTrendColor(data.trend.direction)}`}>
                    {data.trend.direction.replace('_', ' ')}
                  </div>
                  <div className="text-xs text-gray-400 mb-2">
                    Change: {data.price_change_pct >= 0 ? '+' : ''}{data.price_change_pct.toFixed(2)}%
                  </div>
                  <div className="text-xs text-gray-400">
                    ATR: {data.indicators.atr?.toFixed(2) || 'N/A'}
                  </div>
                  {data.patterns.length > 0 && (
                    <div className="mt-2 text-xs text-blue-400">
                      {data.patterns[0].name} pattern
                    </div>
                  )}
                </motion.div>
              ))}
            </div>
          </motion.div>

          {/* Key Levels */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.2 }}
              className="bg-gray-900/50 backdrop-blur rounded-xl p-6 border border-gray-800/50"
            >
              <h3 className="text-lg font-semibold text-gray-300 mb-4 flex items-center gap-2">
                <TrendingDownIcon />
                Support Levels
              </h3>
              <div className="space-y-3">
                {analysisData.key_levels.support.slice(0, 4).map((level, index) => (
                  <motion.div
                    key={index}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.3 + index * 0.1 }}
                    className="flex items-center justify-between p-3 bg-green-500/5 border border-green-500/20 rounded-lg"
                  >
                    <div>
                      <div className="text-white font-medium">${level.price.toFixed(2)}</div>
                      <div className="text-xs text-gray-400">
                        {level.confirmations} timeframe confirmation{level.confirmations > 1 ? 's' : ''}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs text-green-400">Strength: {level.strength}</div>
                    </div>
                  </motion.div>
                ))}
              </div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.2 }}
              className="bg-gray-900/50 backdrop-blur rounded-xl p-6 border border-gray-800/50"
            >
              <h3 className="text-lg font-semibold text-gray-300 mb-4 flex items-center gap-2">
                <TrendingUpIcon />
                Resistance Levels
              </h3>
              <div className="space-y-3">
                {analysisData.key_levels.resistance.slice(0, 4).map((level, index) => (
                  <motion.div
                    key={index}
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.3 + index * 0.1 }}
                    className="flex items-center justify-between p-3 bg-red-500/5 border border-red-500/20 rounded-lg"
                  >
                    <div>
                      <div className="text-white font-medium">${level.price.toFixed(2)}</div>
                      <div className="text-xs text-gray-400">
                        {level.confirmations} timeframe confirmation{level.confirmations > 1 ? 's' : ''}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs text-red-400">Strength: {level.strength}</div>
                    </div>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          </div>

          {/* Trading Signals */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="bg-gray-900/50 backdrop-blur rounded-xl p-6 border border-gray-800/50"
          >
            <h3 className="text-lg font-semibold text-gray-300 mb-4">Trading Signals</h3>
            <div className="space-y-3">
              {analysisData.signals.slice(0, 5).map((signal, index) => (
                <motion.div
                  key={index}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.5 + index * 0.1 }}
                  className={`p-4 rounded-lg border ${getSignalColor(signal.reasoning)}`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-sm font-medium text-white">{signal.type}</span>
                        <span className="text-xs px-2 py-1 bg-white/10 rounded">
                          {signal.direction}
                        </span>
                        <span className="text-xs px-2 py-1 bg-white/10 rounded">
                          {signal.strength}
                        </span>
                      </div>
                      <div className="text-sm text-gray-300">{signal.reasoning}</div>
                    </div>
                    <div className="ml-4 text-right">
                      <div className="text-xs text-gray-400">Confidence</div>
                      <div className="text-lg font-bold">{signal.confidence.toFixed(0)}%</div>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.div>
        </>
      )}
    </div>
  );
}