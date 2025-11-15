'use client';

import { useState, useEffect } from 'react';
import { MarketDashboard } from "@/components/market-dashboard";
import { ConnectedMarketDashboard } from "@/components/ConnectedMarketDashboard";
import { MacroDashboard } from "@/components/macro-dashboard";
import { OHLCAnalysisDashboard } from "@/components/ohlc-analysis-dashboard";
import { LLMChat } from "@/components/llm-chat";
import { BarChart3, Globe, TrendingUp, MessageSquare, Bot, Activity } from 'lucide-react';

export default function Home() {
  const [activeTab, setActiveTab] = useState<'connected' | 'market' | 'macro' | 'technical' | 'ai'>('connected');
  const [marketData, setMarketData] = useState(null);

  // Fetch market data for AI chat
  useEffect(() => {
    const fetchMarketData = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/market/internals');
        if (response.ok) {
          const data = await response.json();
          if (data.success && data.data) {
            setMarketData(data.data);
          }
        }
      } catch (error) {
        console.error('Failed to fetch market data for AI chat:', error);
      }
    };

    // Fetch immediately and then every 60 seconds
    fetchMarketData();
    const interval = setInterval(fetchMarketData, 60000);

    return () => clearInterval(interval);
  }, []);

  return (
    <main className="min-h-screen bg-gray-950 text-white">
      <div className="container mx-auto px-4 py-8">
        <header className="mb-8">
          <h1 className="text-4xl font-bold text-blue-400 mb-2">MarketPulse</h1>
          <p className="text-gray-400">Real-time Market Analysis, AI Trading Assistant & Macro Economic Insights</p>
        </header>

        {/* Navigation Tabs */}
        <div className="flex space-x-1 mb-8 bg-gray-900 rounded-lg p-1 w-fit">
          <button
            onClick={() => setActiveTab('connected')}
            className={`flex items-center gap-2 px-6 py-3 rounded-md font-medium transition-all ${
              activeTab === 'connected'
                ? 'bg-blue-600 text-white'
                : 'text-gray-400 hover:text-white hover:bg-gray-800'
            }`}
          >
            <Activity className="w-4 h-4" />
            Live Dashboard
          </button>
          <button
            onClick={() => setActiveTab('market')}
            className={`flex items-center gap-2 px-6 py-3 rounded-md font-medium transition-all ${
              activeTab === 'market'
                ? 'bg-blue-600 text-white'
                : 'text-gray-400 hover:text-white hover:bg-gray-800'
            }`}
          >
            <BarChart3 className="w-4 h-4" />
            Market Internals
          </button>
          <button
            onClick={() => setActiveTab('macro')}
            className={`flex items-center gap-2 px-6 py-3 rounded-md font-medium transition-all ${
              activeTab === 'macro'
                ? 'bg-blue-600 text-white'
                : 'text-gray-400 hover:text-white hover:bg-gray-800'
            }`}
          >
            <Globe className="w-4 h-4" />
            Macro Economics
          </button>
          <button
            onClick={() => setActiveTab('technical')}
            className={`flex items-center gap-2 px-6 py-3 rounded-md font-medium transition-all ${
              activeTab === 'technical'
                ? 'bg-blue-600 text-white'
                : 'text-gray-400 hover:text-white hover:bg-gray-800'
            }`}
          >
            <TrendingUp className="w-4 h-4" />
            OHLC Analysis
          </button>
          <button
            onClick={() => setActiveTab('ai')}
            className={`flex items-center gap-2 px-6 py-3 rounded-md font-medium transition-all ${
              activeTab === 'ai'
                ? 'bg-blue-600 text-white'
                : 'text-gray-400 hover:text-white hover:bg-gray-800'
            }`}
          >
            <Bot className="w-4 h-4" />
            AI Assistant
          </button>
        </div>

        {/* Active Tab Content */}
        {activeTab === 'connected' && <ConnectedMarketDashboard />}
        {activeTab === 'market' && <MarketDashboard />}
        {activeTab === 'macro' && <MacroDashboard />}
        {activeTab === 'technical' && <OHLCAnalysisDashboard />}
        {activeTab === 'ai' && (
          <div className="h-[calc(100vh-200px)]">
            <LLMChat marketData={marketData} />
          </div>
        )}

        {/* Footer */}
        <footer className="mt-16 pt-8 border-t border-gray-800">
          <div className="flex items-center justify-between">
            <div className="text-sm text-gray-500">
              MarketPulse v0.1.0 - Real-time market analysis
            </div>
            <div className="flex items-center gap-4 text-sm text-gray-500">
              <span>Data refreshed every 30-60 seconds</span>
              <MessageSquare className="w-4 h-4" />
            </div>
          </div>
        </footer>
      </div>
    </main>
  );
}