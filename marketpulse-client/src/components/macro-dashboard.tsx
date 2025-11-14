'use client';

import { motion } from 'framer-motion';
import { TrendingUp, TrendingDown, DollarSign, BarChart3, Globe, Bitcoin, Timer, Brain, RefreshCw, Activity } from 'lucide-react';
import { MacroData } from '@/types/market';
import { useMacroData } from '@/hooks/useMarketData';
import { LoadingSpinner } from './ui/LoadingSpinner';

export function MacroDashboard() {
  const { data: macroData, isLoading, error, refetch } = useMacroData();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" text="Loading macro economic data..." />
      </div>
    );
  }

  if (error) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="bg-yellow-900/20 backdrop-blur border border-yellow-500/30 rounded-xl p-6"
      >
        <div className="flex items-start gap-3">
          <Activity className="w-5 h-5 text-yellow-400 mt-0.5" />
          <div>
            <h3 className="text-yellow-400 font-medium mb-1">Macro Data Unavailable</h3>
            <p className="text-yellow-300 text-sm mb-3">{typeof error === 'string' ? error : error?.message || 'Unknown error'}</p>
            <button
              onClick={() => refetch()}
              className="px-4 py-2 bg-yellow-500/20 hover:bg-yellow-500/30 text-yellow-400 rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
            >
              <RefreshCw className="w-4 h-4" />
              Retry
            </button>
          </div>
        </div>
      </motion.div>
    );
  }

  if (!macroData) {
    return (
      <div className="text-center text-gray-400">
        <Globe className="w-12 h-12 mx-auto mb-4 opacity-50" />
        <p>No macro data available</p>
      </div>
    );
  }

  const renderMacroCard = (data: any, label: string, icon: React.ReactNode, format: 'price' | 'percentage' | 'yield' = 'price') => {
    const isPositive = data.change >= 0;
    const TrendIcon = isPositive ? TrendingUp : TrendingDown;
    const trendColor = isPositive ? 'text-green-400' : 'text-red-400';

    const formatValue = (value: number, type: string) => {
      switch (type) {
        case 'percentage':
        case 'yield':
          return `${value.toFixed(2)}%`;
        case 'price':
        default:
          return value >= 1000 ? `$${value.toLocaleString()}` : `$${value.toFixed(2)}`;
      }
    };

    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        whileHover={{ y: -5, transition: { duration: 0.2 } }}
        className="bg-gray-900/50 backdrop-blur rounded-xl p-4 border border-gray-800/50 hover:border-gray-700/50 transition-all"
      >
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className="p-1.5 bg-blue-500/10 rounded">
              {icon}
            </div>
            <h4 className="text-sm font-medium text-gray-300">{label}</h4>
          </div>
          <div className={`p-1.5 rounded ${isPositive ? 'bg-green-500/10' : 'bg-red-500/10'}`}>
            <TrendIcon className={`w-4 h-4 ${trendColor}`} />
          </div>
        </div>
        <div className="text-xl font-bold text-white mb-1">
          {formatValue(data.price, format)}
        </div>
        <div className={`text-xs ${trendColor} flex items-center gap-1`}>
          <span>{isPositive ? '+' : ''}{data.change.toFixed(2)}</span>
          <span>•</span>
          <span>{isPositive ? '+' : ''}{data.change_pct.toFixed(2)}%</span>
        </div>
      </motion.div>
    );
  };

  const getSentimentColor = (sentiment: string) => {
    switch (sentiment.toLowerCase()) {
      case 'very bullish': return 'text-green-500 bg-green-500/10';
      case 'bullish': return 'text-green-400 bg-green-400/10';
      case 'neutral': return 'text-yellow-400 bg-yellow-400/10';
      case 'bearish': return 'text-red-400 bg-red-400/10';
      case 'very bearish': return 'text-red-500 bg-red-500/10';
      default: return 'text-gray-400 bg-gray-400/10';
    }
  };

  const getRiskAppetiteColor = (appetite: string) => {
    switch (appetite.toLowerCase()) {
      case 'risk on': return 'text-green-400 bg-green-400/10';
      case 'risk off': return 'text-red-400 bg-red-400/10';
      case 'balanced': return 'text-yellow-400 bg-yellow-400/10';
      default: return 'text-gray-400 bg-gray-400/10';
    }
  };

  const getMarketSessionColor = (session: string) => {
    switch (session.toLowerCase()) {
      case 'us regular': return 'text-blue-400 bg-blue-400/10';
      case 'us after hours': return 'text-purple-400 bg-purple-400/10';
      case 'asian session': return 'text-orange-400 bg-orange-400/10';
      case 'european session': return 'text-green-400 bg-green-400/10';
      default: return 'text-gray-400 bg-gray-400/10';
    }
  };

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
            <Globe className="w-6 h-6 text-blue-400" />
          </div>
          <div>
            <h2 className="text-2xl font-bold text-white">Macro Economic Dashboard</h2>
            <p className="text-gray-400 text-sm">Global market indicators and sentiment</p>
          </div>
        </div>
        <button
          onClick={() => refetch()}
          className="p-2 bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors group"
        >
          <RefreshCw className="w-4 h-4 group-hover:rotate-180 transition-transform duration-500" />
        </button>
      </motion.div>

      {/* Key Macro Indicators */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {renderMacroCard(macroData.DXY, 'DXY', <DollarSign className="w-4 h-4 text-blue-400" />, 'price')}
        {renderMacroCard(macroData.TNX, '10Y Yield', <BarChart3 className="w-4 h-4 text-green-400" />, 'yield')}
        {renderMacroCard(macroData.CLF, 'Crude Oil', <Timer className="w-4 h-4 text-orange-400" />, 'price')}
        {renderMacroCard(macroData.GC, 'Gold', <DollarSign className="w-4 h-4 text-yellow-400" />, 'price')}
        {renderMacroCard(macroData.BTC, 'Bitcoin', <Bitcoin className="w-4 h-4 text-orange-400" />, 'price')}
        {renderMacroCard(macroData.ETH, 'Ethereum', <Bitcoin className="w-4 h-4 text-blue-400" />, 'price')}
      </div>

      {/* Market Sentiment Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-gray-900/50 backdrop-blur rounded-xl p-6 border border-gray-800/50"
        >
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 bg-blue-500/10 rounded-lg">
              <Timer className="w-5 h-5 text-blue-400" />
            </div>
            <h3 className="text-lg font-semibold text-gray-300">Market Session</h3>
          </div>
          <div className={`text-xl font-bold px-4 py-2 rounded-lg text-center ${getMarketSessionColor(macroData.market_session)}`}>
            {macroData.market_session}
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="bg-gray-900/50 backdrop-blur rounded-xl p-6 border border-gray-800/50"
        >
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 bg-purple-500/10 rounded-lg">
              <Brain className="w-5 h-5 text-purple-400" />
            </div>
            <h3 className="text-lg font-semibold text-gray-300">Economic Sentiment</h3>
          </div>
          <div className={`text-xl font-bold px-4 py-2 rounded-lg text-center ${getSentimentColor(macroData.economic_sentiment)}`}>
            {macroData.economic_sentiment}
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.3 }}
          className="bg-gray-900/50 backdrop-blur rounded-xl p-6 border border-gray-800/50"
        >
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 bg-green-500/10 rounded-lg">
              <TrendingUp className="w-5 h-5 text-green-400" />
            </div>
            <h3 className="text-lg font-semibold text-gray-300">Risk Appetite</h3>
          </div>
          <div className={`text-xl font-bold px-4 py-2 rounded-lg text-center ${getRiskAppetiteColor(macroData.risk_appetite)}`}>
            {macroData.risk_appetite}
          </div>
        </motion.div>
      </div>

      {/* Sector Performance */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="bg-gray-900/50 backdrop-blur rounded-xl p-6 border border-gray-800/50"
      >
        <h3 className="text-lg font-semibold text-gray-300 mb-4">Sector Performance</h3>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {Object.entries(macroData.sector_performance || {}).map(([sector, performance], index) => {
            const perf = typeof performance === 'number' ? performance : 0;
            const isPositive = perf >= 0;
            return (
              <motion.div
                key={sector}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.5 + index * 0.05 }}
                className={`flex items-center justify-between rounded-lg p-3 border ${
                  isPositive
                    ? 'bg-green-500/5 border-green-500/20'
                    : 'bg-red-500/5 border-red-500/20'
                }`}
              >
                <span className="text-sm text-gray-400 truncate">{sector}</span>
                <span className={`text-sm font-medium ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                  {isPositive ? '+' : ''}{perf.toFixed(1)}%
                </span>
              </motion.div>
            );
          })}
        </div>
      </motion.div>
    </div>
  );
}