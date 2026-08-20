'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { apiFetch } from '../lib/api';
import { PipelineProgress } from './PipelineProgress';
import { AgentTracePanel } from './AgentTracePanel';
// Custom icon components
const SendIcon = () => (
  <div className="w-5 h-5 bg-teal flex items-center justify-center rounded-[2px]">
    <div className="w-2 h-2 bg-ink rounded-sm" style={{transform: 'rotate(-45deg) translateY(1px)'}}></div>
  </div>
);

const BotIcon = () => (
  <div className="w-5 h-5 bg-teal-dim text-teal flex items-center justify-center text-[10px] font-mono font-bold rounded-[2px]">AI</div>
);

const UserIcon = () => (
  <div className="w-5 h-5 bg-sel-dim text-sel flex items-center justify-center text-[10px] font-mono font-bold rounded-[2px]">U</div>
);

const RefreshIcon = () => (
  <div className="w-4 h-4 border border-line" />
);

const SparklesIcon = () => (
  <div className="w-4 h-4 flex gap-0.5">
    <div className="w-1 h-1 bg-warn"></div>
    <div className="w-1 h-1 bg-warn"></div>
    <div className="w-1 h-1 bg-warn"></div>
  </div>
);

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  isThinking?: boolean;
}

interface ModelInfo {
  id: string;
  object: string;
  owned_by: string;
  size: string;
  recommended: boolean;
}

interface ModelStatus {
  lm_studio_connected: boolean;
  current_model: string;
  last_check: string;
  response_time_ms?: number;
  connection_error?: string;
}

interface SymbolMapping {
  symbol: string;
  aliases: string[];
  category: 'stock' | 'crypto' | 'future' | 'commodity' | 'forex';
  description: string;
}

interface LLMChatProps {
  symbol?: string;
  marketData?: any;
}

// Sector to keyword/topic mapping for enriched AI context
const SECTOR_CONTEXT_MAP: Record<string, { keywords: string[]; description: string }> = {
  'Real Estate': {
    keywords: ['housing', 'mortgages', 'interest rates', 'real estate market', 'home prices', 'REIT', 'property'],
    description: 'Real estate sector including residential and commercial property markets'
  },
  'Technology': {
    keywords: ['tech stocks', 'semiconductors', 'software', 'cloud computing', 'AI', 'innovation', 'FAANG'],
    description: 'Technology sector including hardware, software, and semiconductors'
  },
  'Financials': {
    keywords: ['banks', 'interest rates', 'lending', 'financial services', 'insurance', 'credit'],
    description: 'Financial sector including banks, insurance, and investment firms'
  },
  'Healthcare': {
    keywords: ['pharmaceuticals', 'biotech', 'medical devices', 'hospitals', 'healthcare services'],
    description: 'Healthcare sector including pharma, biotech, and medical services'
  },
  'Consumer Discretionary': {
    keywords: ['retail', 'e-commerce', 'consumer spending', 'luxury goods', 'automobiles', 'restaurants'],
    description: 'Consumer discretionary including retail and non-essential goods'
  },
  'Consumer Staples': {
    keywords: ['food', 'beverages', 'household products', 'essentials', 'groceries'],
    description: 'Consumer staples including food, beverages, and household items'
  },
  'Energy': {
    keywords: ['oil', 'gas', 'crude', 'renewable energy', 'utilities', 'petroleum', 'OPEC'],
    description: 'Energy sector including oil, gas, and renewables'
  },
  'Materials': {
    keywords: ['commodities', 'metals', 'mining', 'chemicals', 'construction materials'],
    description: 'Materials sector including mining, metals, and chemicals'
  },
  'Industrials': {
    keywords: ['manufacturing', 'aerospace', 'defense', 'machinery', 'transportation', 'logistics'],
    description: 'Industrial sector including manufacturing and transportation'
  },
  'Communication Services': {
    keywords: ['telecom', 'media', 'entertainment', 'social media', 'streaming', 'advertising'],
    description: 'Communication services including telecom and media companies'
  },
  'Utilities': {
    keywords: ['electricity', 'water', 'gas utilities', 'power generation', 'infrastructure'],
    description: 'Utilities sector including electric, water, and gas providers'
  }
};

export function LLMChat({ symbol = 'SPY', marketData }: LLMChatProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isConnected, setIsConnected] = useState(true);
  const [availableModels, setAvailableModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('aquif-3.5-max-42b-a3b-i1');
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null);
  const [showModelSelector, setShowModelSelector] = useState(false);
  const [detectedSymbols, setDetectedSymbols] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // -- Agentic streaming state --
  const [pipelinePhase, setPipelinePhase] = useState<string>('');
  const [agentDoneCount, setAgentDoneCount] = useState(0);
  const [totalAgents, setTotalAgents] = useState(0);
  const [agentTraces, setAgentTraces] = useState<{agentName: string; status: 'pending' | 'running' | 'done'; content: string; toolsUsed: string[]}[]>([]);
  const [showAgentTrace, setShowAgentTrace] = useState(false);
  const [streamingSynthesis, setStreamingSynthesis] = useState('');
  const wsRef = useRef<WebSocket | null>(null);

  const connectAgentStream = useCallback((query: string, syms: string[]) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname === 'localhost' ? 'localhost:8000' : window.location.host;
    const ws = new WebSocket(`${protocol}//${host}/ws/stream-analysis`);
    wsRef.current = ws;

    setPipelinePhase('plan');
    setAgentTraces([]);
    setAgentDoneCount(0);
    setStreamingSynthesis('');

    ws.onopen = () => {
      ws.send(JSON.stringify({ query, symbols: syms, include_breadth: true }));
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setPipelinePhase(data.phase);

      if (data.phase === 'agent_done') {
        setAgentDoneCount(c => c + 1);
        setAgentTraces(prev => [...prev, {
          agentName: data.agent_name || 'Unknown',
          status: 'done',
          content: data.content || '',
          toolsUsed: data.tools_used || [],
        }]);
      } else if (data.phase === 'agents_running') {
        const agents = data.data?.agents || [];
        setTotalAgents(agents.length);
      } else if (data.phase === 'data_fetching') {
        setAgentTraces(prev => [...prev, {
          agentName: 'DataAgent', status: 'running', content: '', toolsUsed: [],
        }]);
      } else if (data.phase === 'data_complete') {
        setAgentTraces(prev => prev.map(a =>
          a.agentName === 'DataAgent' ? {...a, status: 'done', content: data.content || '', toolsUsed: data.tools_used || []} : a
        ));
      } else if (data.phase === 'draft_ready' || data.phase === 'final_ready') {
        setStreamingSynthesis(data.content || '');
      }
    };

    ws.onerror = () => { setPipelinePhase(''); };
    ws.onclose = () => { wsRef.current = null; };
  }, []);

  // -- End streaming state --

  // Symbol mapping dictionary for pattern recognition
  const symbolMappings: SymbolMapping[] = [
    // Stocks & ETFs
    { symbol: 'SPY', aliases: ['spy', 'spdr', 's&p', 's&p500', 'sp500'], category: 'stock', description: 'SPDR S&P 500 ETF Trust' },
    { symbol: 'QQQ', aliases: ['qqq', 'nasdaq', 'nasdaq100', 'ndx'], category: 'stock', description: 'Invesco QQQ Trust' },
    { symbol: 'NQ=F', aliases: ['nq=f', 'nq', 'nasdaq future', 'nasdaq futures', 'nq future'], category: 'future', description: 'Nasdaq 100 Futures' },
    { symbol: 'ES=F', aliases: ['es=f', 'es', 's&p future', 's&p futures', 'sp future', 'es future'], category: 'future', description: 'S&P 500 Futures' },
    { symbol: 'YM=F', aliases: ['ym=f', 'ym', 'dow future', 'dow futures', 'dji future'], category: 'future', description: 'Dow Jones Futures' },
    { symbol: 'AAPL', aliases: ['aapl', 'apple'], category: 'stock', description: 'Apple Inc.' },
    { symbol: 'MSFT', aliases: ['msft', 'microsoft'], category: 'stock', description: 'Microsoft Corporation' },
    { symbol: 'GOOGL', aliases: ['googl', 'google', 'alphabet'], category: 'stock', description: 'Alphabet Inc.' },
    { symbol: 'TSLA', aliases: ['tsla', 'tesla'], category: 'stock', description: 'Tesla, Inc.' },

    // Crypto
    { symbol: 'BTC-USD', aliases: ['btc-usd', 'btc', 'bitcoin'], category: 'crypto', description: 'Bitcoin US Dollar' },
    { symbol: 'ETH-USD', aliases: ['eth-usd', 'eth', 'ethereum', 'ether'], category: 'crypto', description: 'Ethereum US Dollar' },
    { symbol: 'BNB-USD', aliases: ['bnb-usd', 'bnb', 'binance'], category: 'crypto', description: 'Binance Coin US Dollar' },
    { symbol: 'SOL-USD', aliases: ['sol-usd', 'sol', 'solana'], category: 'crypto', description: 'Solana US Dollar' },
    { symbol: 'ADA-USD', aliases: ['ada-usd', 'ada', 'cardano'], category: 'crypto', description: 'Cardano US Dollar' },
    { symbol: 'XRP-USD', aliases: ['xrp-usd', 'xrp', 'ripple'], category: 'crypto', description: 'Ripple US Dollar' },
    { symbol: 'DOGE-USD', aliases: ['doge-usd', 'doge', 'dogecoin'], category: 'crypto', description: 'Dogecoin US Dollar' },
    { symbol: 'AVAX-USD', aliases: ['avax-usd', 'avax', 'avalanche'], category: 'crypto', description: 'Avalanche US Dollar' },
    { symbol: 'DOT-USD', aliases: ['dot-usd', 'dot', 'polkadot'], category: 'crypto', description: 'Polkadot US Dollar' },
    { symbol: 'MATIC-USD', aliases: ['matic-usd', 'matic', 'polygon'], category: 'crypto', description: 'Polygon US Dollar' },

    // Commodities
    { symbol: 'GC=F', aliases: ['gc=f', 'gc', 'gold', 'gold future', 'xauusd'], category: 'commodity', description: 'Gold Futures' },
    { symbol: 'CL=F', aliases: ['cl=f', 'cl', 'oil', 'crude oil', 'wti', 'oil future'], category: 'commodity', description: 'Crude Oil Futures' },
    { symbol: 'SI=F', aliases: ['si=f', 'si', 'silver', 'silver future', 'xagusd'], category: 'commodity', description: 'Silver Futures' },

    // Volatility
    { symbol: 'VIX', aliases: ['vix', 'volatility', 'vixx'], category: 'stock', description: 'CBOE Volatility Index' },
    { symbol: 'UVXY', aliases: ['uvxy', 'volatility etf'], category: 'stock', description: 'ProShares Ultra VIX Short-Term Futures ETF' },

    // Forex
    { symbol: 'EURUSD=X', aliases: ['eurusd=x', 'eurusd', 'euro', 'euro dollar'], category: 'forex', description: 'EUR/USD Exchange Rate' },
    { symbol: 'GBPUSD=X', aliases: ['gbpusd=x', 'gbpusd', 'pound', 'british pound'], category: 'forex', description: 'GBP/USD Exchange Rate' },
    { symbol: 'USDJPY=X', aliases: ['usdjpy=x', 'usdjpy', 'yen', 'japanese yen'], category: 'forex', description: 'USD/JPY Exchange Rate' }
  ];

  // Create symbol lookup dictionary for fast matching
  const symbolLookup = React.useMemo(() => {
    const lookup: { [key: string]: SymbolMapping } = {};
    symbolMappings.forEach(mapping => {
      mapping.aliases.forEach(alias => {
        lookup[alias.toLowerCase()] = mapping;
      });
    });
    return lookup;
  }, []);

  // Scan text for symbol patterns using regex and dictionary lookup
  const scanTextForSymbols = (text: string): string[] => {
    const detected = new Set<string>();
    const words = text.toLowerCase().split(/\s+/);

    // Dictionary-based lookup for exact matches
    words.forEach(word => {
      // Clean word: remove punctuation and common suffixes
      const cleanWord = word.replace(/[^\w]/g, '');
      if (symbolLookup[cleanWord]) {
        detected.add(symbolLookup[cleanWord].symbol);
      }
    });

    // Pattern-based matching for more complex cases
    const patterns = [
      // Crypto patterns
      /\b(btc|bitcoin)\b/gi,
      /\b(eth|ethereum|ether)\b/gi,
      /\b(bnb|binance\s*coin)\b/gi,
      /\b(sol|solana)\b/gi,
      /\b(ada|cardano)\b/gi,
      /\b(xrp|ripple)\b/gi,
      /\b(doge|dogecoin)\b/gi,

      // Stock patterns
      /\b(spy|spdr|s&p\s*500)\b/gi,
      /\b(qqq|nasdaq\s*100)\b/gi,
      /\b(nq\s*=\s*f|nasdaq\s*futures?)\b/gi,
      /\b(es\s*=\s*f|s&p\s*futures?)\b/gi,
      /\b(ym\s*=\s*f|dow\s*futures?)\b/gi,

      // Commodity patterns
      /\b(gc\s*=\s*f|gold\s*futures?)\b/gi,
      /\b(cl\s*=\s*f|oil|crude\s*oil)\b/gi,
      /\b(si\s*=\s*f|silver\s*futures?)\b/gi,

      // Volatility patterns
      /\b(vix|cboe\s*volatility)\b/gi,

      // Individual stock patterns
      /\b(aapl|apple)\b/gi,
      /\b(msft|microsoft)\b/gi,
      /\b(googl|google|alphabet)\b/gi,
      /\b(tsla|tesla)\b/gi,
    ];

    patterns.forEach(pattern => {
      const matches = text.match(pattern);
      if (matches) {
        matches.forEach(match => {
          const cleanMatch = match.toLowerCase().replace(/[^\w\s]/g, '').replace(/\s+/g, ' ');
          if (symbolLookup[cleanMatch]) {
            detected.add(symbolLookup[cleanMatch].symbol);
          }
        });
      }
    });

    return Array.from(detected);
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Fetch available models on mount
  useEffect(() => {
    fetchAvailableModels();
    fetchModelStatus();
  }, []);

  // Add welcome message on mount
  useEffect(() => {
    setMessages([{
      id: '1',
      role: 'assistant',
      content: `Hello! I'm your AI trading assistant. I can help you analyze market conditions, discuss trading strategies, and provide insights about ${symbol} and other assets.

I have access to:
• Real-time market data (indices, crypto, commodities)
• Sector performance and analysis
• Market breadth indicators (TICK, A/D ratio, McClellan)
• Technical levels and patterns

Try asking about specific sectors (e.g., "How's Real Estate performing?") or assets (e.g., "What's the trend for BTC?")`,
      timestamp: new Date().toISOString()
    }]);
  }, [symbol]);

  // Close model selector when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (showModelSelector) {
        const target = event.target as Element;
        if (!target.closest('.model-selector-container')) {
          setShowModelSelector(false);
        }
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showModelSelector]);

  const fetchAvailableModels = async () => {
    try {
      setError(null);
      const data = await apiFetch<any>('/llm/models');
      if (data.success && data.data?.models) {
        setAvailableModels(data.data.models);
      }
    } catch (error) {
      console.error('Failed to fetch models:', error);
      setError(error instanceof Error ? error.message : 'Failed to fetch models');
    }
  };

  const fetchModelStatus = async () => {
    try {
      const data = await apiFetch<{ success: boolean; data: ModelStatus }>('/llm/model-status');
      if (data.success && data.data) {
        setModelStatus(data.data);
        setSelectedModel(data.data.current_model);
        setIsConnected(data.data.lm_studio_connected);
      }
    } catch (err) {
      console.error('Failed to fetch model status:', err);
      setIsConnected(false);
      setError(err instanceof Error ? err.message : 'Failed to fetch model status');
    }
  };

  const selectModel = async (modelId: string) => {
    try {
      setError(null);
      const data = await apiFetch<{ success: boolean }>('/llm/select-model', {
        method: 'POST',
        body: JSON.stringify({ model_id: modelId, provider: 'lm_studio' })
      });

      if (data.success) {
        setSelectedModel(modelId);
        setShowModelSelector(false);
        fetchModelStatus();
      }
    } catch (err) {
      console.error('Failed to select model:', err);
      setError(err instanceof Error ? err.message : 'Failed to select model');
    }
  };

  const generateMarketContext = () => {
    const context = {
      symbol,
      current_price: marketData?.current_price || 'Could not get current price - N/A',
      market_bias: marketData?.market_bias || 'Market bias not available',
      volatility_regime: marketData?.market_context?.volatility_regime || 'Volatility regime not available',
      key_levels: {
        support: marketData?.key_levels?.support?.slice(0, 2) || [],
        resistance: marketData?.key_levels?.resistance?.slice(0, 2) || []
      },
      recent_signals: marketData?.signals?.slice(0, 3) || [],
      timeframe_consensus: marketData?.timeframe_consensus || {},
      market_data_available: !!marketData,
      message: marketData ? null : "No market data available.",
      detected_symbols: detectedSymbols,
      symbol_context: detectedSymbols.map(sym => {
        const mapping = symbolMappings.find(m => m.symbol === sym);
        return {
          symbol: sym,
          category: mapping?.category || 'unknown',
          description: mapping?.description || sym,
          aliases: mapping?.aliases || []
        };
      })
    };

    return context;
  };

  const generateEnhancedContext = (query: string) => {
    const symbolsInQuery = scanTextForSymbols(query);

    // Prioritize NQ=F over QQQ for nasdaq queries
    const enhancedSymbols = symbolsInQuery.map(sym => {
      if (sym === 'QQQ' && (query.toLowerCase().includes('nq') || query.toLowerCase().includes('future'))) {
        return 'NQ=F';
      }
      return sym;
    });

    // Detect sector mentions in the query
    const detectedSectors: string[] = [];
    const sectorContext: any[] = [];

    Object.entries(SECTOR_CONTEXT_MAP).forEach(([sectorName, sectorInfo]) => {
      // Check if sector name is mentioned
      if (query.toLowerCase().includes(sectorName.toLowerCase())) {
        detectedSectors.push(sectorName);
        sectorContext.push({
          sector: sectorName,
          keywords: sectorInfo.keywords,
          description: sectorInfo.description,
          performance: marketData?.sector_performance?.[sectorName] || null
        });
      }
      // Check if any sector keywords are mentioned
      sectorInfo.keywords.forEach(keyword => {
        if (query.toLowerCase().includes(keyword.toLowerCase()) && !detectedSectors.includes(sectorName)) {
          detectedSectors.push(sectorName);
          sectorContext.push({
            sector: sectorName,
            keywords: sectorInfo.keywords,
            description: sectorInfo.description,
            performance: marketData?.sector_performance?.[sectorName] || null
          });
        }
      });
    });

    // Build comprehensive context
    return {
      primary_symbol: symbol,
      detected_symbols: enhancedSymbols,
      detected_sectors: detectedSectors,
      sector_context: sectorContext,
      query_type: determineQueryType(query),
      symbol_context: enhancedSymbols.map(sym => {
        const mapping = symbolMappings.find(m => m.symbol === sym);
        return {
          symbol: sym,
          category: mapping?.category || 'unknown',
          description: mapping?.description || sym,
          aliases: mapping?.aliases || []
        };
      }),
      market_data_available: !!marketData,
      market_bias: marketData?.marketBias || marketData?.market_bias || 'Market bias not available',
      volatility_regime: marketData?.volatilityRegime || marketData?.market_context?.volatility_regime || 'Volatility regime not available',
      sector_performance: marketData?.sector_performance || {},
      market_breadth: marketData?.breadth_data ? {
        nyse_ad_ratio: marketData.breadth_data.nyse_ad_ratio,
        nasdaq_ad_ratio: marketData.breadth_data.nasdaq_ad_ratio,
        tick_value: marketData.breadth_data.tick_value,
        mcclellan_oscillator: marketData.breadth_data.mcclellan_oscillator,
        interpretation: marketData.breadth_data.interpretation
      } : null,
      current_prices: marketData?.symbols || {},
      macro_data: marketData?.macro_data || {},
      key_levels: {
        support: marketData?.key_levels?.support?.slice(0, 2) || [],
        resistance: marketData?.key_levels?.resistance?.slice(0, 2) || []
      },
      recent_signals: marketData?.signals?.slice(0, 3) || [],
      timeframe_consensus: marketData?.timeframe_consensus || {}
    };
  };

  const determineQueryType = (query: string): string => {
    const lowerQuery = query.toLowerCase();

    if (lowerQuery.includes('trend') || lowerQuery.includes('direction') || lowerQuery.includes('bullish') || lowerQuery.includes('bearish')) {
      return 'trend_analysis';
    } else if (lowerQuery.includes('support') || lowerQuery.includes('resistance') || lowerQuery.includes('levels')) {
      return 'technical_levels';
    } else if (lowerQuery.includes('volatility') || lowerQuery.includes('vix') || lowerQuery.includes('risk')) {
      return 'volatility_analysis';
    } else if (lowerQuery.includes('buy') || lowerQuery.includes('sell') || lowerQuery.includes('trade') || lowerQuery.includes('entry') || lowerQuery.includes('exit')) {
      return 'trading_strategy';
    } else if (lowerQuery.includes('news') || lowerQuery.includes('catalyst') || lowerQuery.includes('event')) {
      return 'fundamental_analysis';
    } else if (detectedSymbols.length > 0) {
      return 'symbol_specific';
    } else {
      return 'general_market';
    }
  };

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;

    // Scan input for symbols before clearing it
    const detected = scanTextForSymbols(input.trim());
    setDetectedSymbols(detected);

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date().toISOString()
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    // Add thinking message
    const thinkingMessage: Message = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
      isThinking: true
    };
    setMessages(prev => [...prev, thinkingMessage]);

    try {
      // Create AbortController for timeout handling
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 180000); // 3 minutes timeout

      const data = await apiFetch<{ data?: { response?: string }; response?: string }>('/llm/chat', {
        method: 'POST',
        body: JSON.stringify({
          message: userMessage.content,
          context: generateEnhancedContext(userMessage.content),
          symbol: symbol,
          conversation_history: messages.slice(-6).map(msg => ({
            role: msg.role,
            content: msg.content
          }))
        }),
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      setMessages(prev => prev.filter(msg => !msg.isThinking));

      let responseContent = '';
      if (data.data?.response) {
        responseContent = data.data.response;
      } else if (data.response) {
        responseContent = data.response;
      } else {
        responseContent = 'Sorry, I received an empty response.';
      }

      const aiMessage: Message = {
        id: (Date.now() + 2).toString(),
        role: 'assistant',
        content: responseContent,
        timestamp: new Date().toISOString()
      };
      setMessages(prev => [...prev, aiMessage]);
    } catch (error) {
      // Remove thinking message
      setMessages(prev => prev.filter(msg => !msg.isThinking));

      let errorMessage = "I'm having trouble connecting to my AI services right now. This could be due to network issues or the AI service being temporarily unavailable. Please try again in a moment.";

      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          errorMessage = "The request took too long to complete (3 minutes timeout). This might happen if the AI is processing a complex query. Please try again with a more specific question.";
        } else {
          errorMessage = `Connection error: ${error.message}. Please check if the server is running and try again.`;
        }
      }

      const errorResponse: Message = {
        id: (Date.now() + 2).toString(),
        role: 'assistant',
        content: errorMessage,
        timestamp: new Date().toISOString()
      };
      setMessages(prev => [...prev, errorResponse]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
    // Allow Shift+Enter for new lines
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setInput(value);

    // Real-time symbol detection as user types
    if (value.length > 2) {
      const detected = scanTextForSymbols(value);
      setDetectedSymbols(detected);
    } else {
      setDetectedSymbols([]);
    }
  };

  const clearChat = () => {
    setMessages([{
      id: Date.now().toString(),
      role: 'assistant',
      content: `Chat cleared. How can I help you analyze ${symbol} and the current market conditions?`,
      timestamp: new Date().toISOString()
    }]);
  };

  const suggestedQuestions = [
    `What's the current trend for ${symbol}?`,
    `What are the key support and resistance levels?`,
    `How does the current volatility affect trading strategy?`,
    `What trading signals should I watch for?`,
    `Explain the current market bias and its implications`
  ];

  return (
    <div className="flex flex-col h-full panel overflow-hidden">
      {/* Agentic Pipeline UI */}
      {pipelinePhase && (
        <PipelineProgress
          currentPhase={pipelinePhase}
          agentDoneCount={agentDoneCount}
          totalAgents={totalAgents || 8}
        />
      )}
      <div className="flex flex-1 overflow-hidden">
        {/* Agent Trace Sidebar */}
        {pipelinePhase && (
          <div className="w-64 flex-shrink-0">
            <AgentTracePanel
              agents={agentTraces}
              expanded={showAgentTrace}
              onToggle={() => setShowAgentTrace(!showAgentTrace)}
            />
          </div>
        )}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Streaming Synthesis Preview */}
          {streamingSynthesis && (
            <div className="px-2.5 py-2 bg-sel-dim border-b border-line-subtle text-sel text-[12.5px] max-h-32 overflow-y-auto">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {streamingSynthesis.slice(0, 800)}
              </ReactMarkdown>
            </div>
          )}
      {error && (
        <div className="p-2.5 bg-neg-dim border border-line rounded-[2px] text-neg text-[12.5px] m-2.5">
          {error}
          <button onClick={() => { setError(null); fetchModelStatus(); }} className="ml-2 underline">Retry</button>
        </div>
      )}
      {/* Header */}
      <div className="flex items-center justify-between px-2.5 h-8 border-b border-line-subtle">
        <div className="flex items-center gap-2">
          <div className="relative">
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-pos' : 'bg-neg'} animate-pulse`} />
            {isConnected && (
              <div className="absolute inset-0 w-2 h-2 rounded-full bg-pos animate-ping" />
            )}
          </div>
          <div className="flex items-center gap-2">
            <BotIcon />
            <h3 className="panel-title">AI ANALYST</h3>
            <span className="border border-sel rounded-[2px] px-1.5 h-5 text-[11px] font-mono inline-flex items-center text-sel">
              {symbol}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Model Status */}
          <div className="flex items-center gap-2 px-1.5 h-7 bg-surface-raised">
            <div className={`w-2 h-2 rounded-full ${modelStatus?.lm_studio_connected ? 'bg-pos' : 'bg-neg'}`} />
            <span className="text-[11px] font-mono text-ink-muted">
              {modelStatus?.current_model?.split('-')[0] || 'Loading...'}
            </span>
          </div>

          {/* Model Selector */}
          <div className="relative model-selector-container">
            <button
              onClick={() => setShowModelSelector(!showModelSelector)}
              className="btn text-[11px]"
              title="Select Model"
            >
              Model
            </button>

            {showModelSelector && (
              <div className="absolute right-0 top-full mt-1 w-80 panel p-0 z-50">
                <div className="p-2.5 border-b border-line-subtle">
                  <h4 className="panel-title">Select AI Model</h4>
                  <p className="text-[11px] text-ink-muted">
                    {modelStatus?.lm_studio_connected ? 'LM Studio Connected' : 'LM Studio Disconnected'}
                    {modelStatus?.response_time_ms && ` • ${modelStatus.response_time_ms}ms`}
                  </p>
                </div>

                <div className="max-h-64 overflow-y-auto">
                  {availableModels.map((model) => (
                    <button
                      key={model.id}
                      onClick={() => selectModel(model.id)}
                      className={`w-full px-2.5 py-1.5 text-left hover:bg-surface-hover border-b border-line-subtle last:border-b-0 ${
                        selectedModel === model.id ? 'bg-sel-dim' : ''
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-[12.5px] font-medium text-ink truncate">
                              {model.id.split('-')[0]}
                            </span>
                            {model.recommended && (
                              <span className="border border-sel rounded-[2px] px-1.5 h-5 text-[11px] font-mono inline-flex items-center text-sel">
                                Recommended
                              </span>
                            )}
                          </div>
                          <div className="text-[11px] text-ink-muted truncate font-mono">
                            {model.id}
                          </div>
                          <div className="flex items-center gap-2 mt-1">
                            <span className="text-[11px] text-ink-muted font-mono">{model.size}</span>
                            <span className="text-[11px] text-ink-muted">•</span>
                            <span className="text-[11px] text-ink-muted">{model.owned_by}</span>
                          </div>
                        </div>
                        {selectedModel === model.id && (
                          <div className="w-3 h-3 bg-teal flex items-center justify-center">
                            <div className="w-1.5 h-1.5 bg-ink" />
                          </div>
                        )}
                      </div>
                    </button>
                  ))}
                </div>

                <div className="p-2.5 border-t border-line-subtle">
                  <button
                    onClick={() => {
                      fetchAvailableModels();
                      fetchModelStatus();
                    }}
                    className="btn w-full justify-center"
                  >
                    Refresh Models
                  </button>
                </div>
              </div>
            )}
          </div>

          <button
            onClick={clearChat}
            className="btn"
            title="Clear chat"
          >
            <RefreshIcon />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-2.5 space-y-2" style={{ maxHeight: 'calc(100% - 250px)' }}>
        <AnimatePresence>
          {messages.map((message) => (
            <motion.div
              key={message.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3 }}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div className={`flex gap-2 max-w-[95%] ${message.role === 'user' ? 'flex-row-reverse' : ''}`}>
                <div className={`w-5 h-5 flex items-center justify-center flex-shrink-0 rounded-[2px] ${
                  message.role === 'user'
                    ? 'bg-sel-dim'
                    : message.isThinking
                      ? 'bg-warn-dim animate-pulse'
                      : 'bg-teal-dim'
                }`}>
                  {message.isThinking ? (
                    <div className="w-3 h-3 border border-line border-t-teal animate-spin" />
                  ) : (
                    message.role === 'user' ? (
                      <UserIcon />
                    ) : (
                      <BotIcon />
                    )
                  )}
                </div>
                <div className={`rounded-[2px] p-2 text-[12.5px] ${
                  message.role === 'user'
                    ? 'bg-surface-raised text-ink border-l-2 border-teal'
                    : message.isThinking
                      ? 'bg-warn-dim text-warn border-l-2 border-warn'
                      : 'bg-surface text-ink border-l-2 border-line-subtle'
                }`}>
                  {message.isThinking ? (
                    <div className="flex items-center gap-2">
                      <SparklesIcon />
                      <span className="text-teal animate-pulse">Thinking...</span>
                    </div>
                  ) : (
                    <div className={`prose max-w-none ${message.role === 'user' ? 'prose-p:text-ink prose-strong:text-ink prose-headings:text-ink' : ''}`}>
                      {message.role === 'assistant' ? (
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={{
                            h1: ({node, ...props}) => <h1 className="text-[15px] font-bold mb-2 text-ink" {...props} />,
                            h2: ({node, ...props}) => <h2 className="text-[15px] font-bold mb-2 text-ink" {...props} />,
                            h3: ({node, ...props}) => <h3 className="text-[12.5px] font-bold mb-1 text-ink" {...props} />,
                            p: ({node, ...props}) => <p className="mb-2 text-ink" {...props} />,
                            ul: ({node, ...props}) => <ul className="list-disc list-inside mb-2 text-ink" {...props} />,
                            ol: ({node, ...props}) => <ol className="list-decimal list-inside mb-2 text-ink" {...props} />,
                            li: ({node, ...props}) => <li className="mb-1 text-ink" {...props} />,
                            strong: ({node, ...props}) => <strong className="font-bold text-ink" {...props} />,
                            em: ({node, ...props}) => <em className="italic text-ink-secondary" {...props} />,
                            code: ({node, className, children, ...props}) => {
                              const inline = !className;
                              return inline ? (
                                <code className="bg-canvas border border-line-subtle px-1 py-0.5 rounded-[2px] text-sel font-mono text-[11.5px]" {...props}>{children}</code>
                              ) : (
                                <code className="block bg-canvas border border-line-subtle p-2 rounded-[2px] text-pos font-mono text-[11.5px] overflow-x-auto" {...props}>{children}</code>
                              );
                            },
                            table: ({node, ...props}) => <table className="border-collapse border border-line my-2 text-[12.5px]" {...props} />,
                            th: ({node, ...props}) => <th className="border border-line px-2 py-1 bg-surface-raised font-semibold text-ink" {...props} />,
                            td: ({node, ...props}) => <td className="border border-line px-2 py-1 text-ink" {...props} />,
                            blockquote: ({node, ...props}) => <blockquote className="border-l-2 border-teal pl-3 italic text-ink-secondary my-2" {...props} />,
                          }}
                        >
                          {message.content}
                        </ReactMarkdown>
                      ) : (
                        <div className="whitespace-pre-wrap text-ink">{message.content}</div>
                      )}
                    </div>
                  )}
                  <div className="text-[11px] opacity-60 mt-2 text-ink-muted font-mono">
                    {new Date(message.timestamp).toLocaleTimeString()}
                  </div>
                </div>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Questions */}
      {messages.length <= 2 && (
        <div className="px-2.5 py-2 border-t border-line-subtle">
          <p className="text-[11px] text-ink-muted mb-2">Suggested questions:</p>
          <div className="flex flex-wrap gap-2">
            {suggestedQuestions.map((question, index) => (
              <button
                key={index}
                onClick={() => setInput(question)}
                className="btn h-6 text-[11px]"
                disabled={isLoading}
              >
                {question}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div className="p-2.5 border-t border-line-subtle">
        {/* Detected Symbols Display */}
        {detectedSymbols.length > 0 && (
          <div className="mb-2 p-2 bg-sel-dim border border-line rounded-[2px]">
            <div className="flex items-center gap-2 text-[11px] text-sel">
              <span>Detected symbols:</span>
              <div className="flex flex-wrap gap-1">
                {detectedSymbols.map(sym => {
                  const mapping = symbolMappings.find(m => m.symbol === sym);
                  return (
                    <span key={sym} className="border border-sel rounded-[2px] px-1.5 h-5 text-[11px] font-mono inline-flex items-center text-sel">
                      {sym} {mapping?.category && `(${mapping.category})`}
                    </span>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        <div className="flex gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyPress}
            placeholder={`Ask about ${symbol} or market analysis...\n\nTry: "How's Real Estate performing?", "Compare BTC to gold", "NQ futures analysis"\n\nPress Enter to send, Shift+Enter for new line`}
            className="input flex-1 resize-none min-h-[72px] h-auto py-1.5"
            disabled={isLoading}
            rows={3}
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || isLoading}
            className="btn btn-primary self-end disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <div className="w-4 h-4 border border-line border-t-teal animate-spin" />
            ) : (
              <SendIcon />
            )}
            <span className="hidden sm:inline">Send</span>
          </button>
        </div>
        <div className="mt-2 text-[11px] text-ink-muted">
          <span className="font-semibold text-ink-secondary">Tip:</span> Press <kbd className="kbd">Enter</kbd> to send, <kbd className="kbd">Shift+Enter</kbd> for new line •
          {isConnected ? <span className="text-pos ml-1 font-mono">Connected</span> : <span className="text-neg ml-1 font-mono">Disconnected</span>}
        </div>
      </div>
        </div>{/* close flex-1 flex-col */}
      </div>{/* close flex overflow-hidden */}
    </div>
  );
}