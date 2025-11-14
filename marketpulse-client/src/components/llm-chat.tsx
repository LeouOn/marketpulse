'use client';

import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Bot, User, RefreshCw, Sparkles } from 'lucide-react';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  isThinking?: boolean;
}

interface LLMChatProps {
  symbol?: string;
  marketData?: any;
}

export function LLMChat({ symbol = 'SPY', marketData }: LLMChatProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Add welcome message on mount
  useEffect(() => {
    setMessages([{
      id: '1',
      role: 'assistant',
      content: `Hello! I'm your AI trading assistant. I can help you analyze market conditions, discuss trading strategies, and provide insights about ${symbol} and other assets.

What would you like to know about the current market?`,
      timestamp: new Date().toISOString()
    }]);
    setIsConnected(true);
  }, [symbol]);

  const generateMarketContext = () => {
    if (!marketData) return "No market data available.";

    const context = {
      symbol,
      current_price: marketData.current_price || 'N/A',
      market_bias: marketData.market_bias || 'NEUTRAL',
      volatility_regime: marketData.market_context?.volatility_regime || 'UNKNOWN',
      key_levels: {
        support: marketData.key_levels?.support?.slice(0, 2) || [],
        resistance: marketData.key_levels?.resistance?.slice(0, 2) || []
      },
      recent_signals: marketData.signals?.slice(0, 3) || [],
      timeframe_consensus: marketData.timeframe_consensus || {}
    };

    return JSON.stringify(context, null, 2);
  };

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;

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
      const response = await fetch('/api/llm/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: userMessage.content,
          context: generateMarketContext(),
          symbol: symbol,
          conversation_history: messages.slice(-6).map(msg => ({
            role: msg.role,
            content: msg.content
          }))
        })
      });

      if (response.ok) {
        const data = await response.json();

        // Remove thinking message
        setMessages(prev => prev.filter(msg => !msg.isThinking));

        // Add AI response
        const aiMessage: Message = {
          id: (Date.now() + 2).toString(),
          role: 'assistant',
          content: data.response || "I apologize, but I couldn't generate a response at this time.",
          timestamp: new Date().toISOString()
        };
        setMessages(prev => [...prev, aiMessage]);
      } else {
        // Remove thinking message
        setMessages(prev => prev.filter(msg => !msg.isThinking));

        const errorText = await response.text();
        const errorMessage: Message = {
          id: (Date.now() + 2).toString(),
          role: 'assistant',
          content: `I encountered an error: ${errorText}. Please try again or contact support if the issue persists.`,
          timestamp: new Date().toISOString()
        };
        setMessages(prev => [...prev, errorMessage]);
      }
    } catch (error) {
      // Remove thinking message
      setMessages(prev => prev.filter(msg => !msg.isThinking));

      const errorMessage: Message = {
        id: (Date.now() + 2).toString(),
        role: 'assistant',
        content: "I'm having trouble connecting to my AI services right now. This could be due to network issues or the AI service being temporarily unavailable. Please try again in a moment.",
        timestamp: new Date().toISOString()
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
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
    <div className="flex flex-col h-full bg-gray-900/50 backdrop-blur rounded-xl border border-gray-800/50">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-800/50">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'} animate-pulse`} />
            {isConnected && (
              <div className="absolute inset-0 w-3 h-3 rounded-full bg-green-500 animate-ping" />
            )}
          </div>
          <div className="flex items-center gap-2">
            <Bot className="w-5 h-5 text-blue-400" />
            <h3 className="text-lg font-semibold text-white">AI Trading Assistant</h3>
            <span className="px-2 py-1 bg-blue-500/20 text-blue-400 text-xs rounded-full">
              {symbol}
            </span>
          </div>
        </div>
        <button
          onClick={clearChat}
          className="p-2 text-gray-400 hover:text-white hover:bg-gray-800/50 rounded-lg transition-colors"
          title="Clear chat"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
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
              <div className={`flex gap-3 max-w-[80%] ${message.role === 'user' ? 'flex-row-reverse' : ''}`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
                  message.role === 'user'
                    ? 'bg-blue-500'
                    : message.isThinking
                      ? 'bg-yellow-500 animate-pulse'
                      : 'bg-purple-500'
                }`}>
                  {message.isThinking ? (
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  ) : (
                    message.role === 'user' ? (
                      <User className="w-4 h-4 text-white" />
                    ) : (
                      <Bot className="w-4 h-4 text-white" />
                    )
                  )}
                </div>
                <div className={`rounded-lg px-4 py-3 ${
                  message.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : message.isThinking
                      ? 'bg-yellow-500/20 text-yellow-300 border border-yellow-500/30'
                      : 'bg-gray-800 text-gray-100 border border-gray-700'
                }`}>
                  {message.isThinking ? (
                    <div className="flex items-center gap-2">
                      <Sparkles className="w-4 h-4" />
                      <span>Thinking...</span>
                    </div>
                  ) : (
                    <div className="whitespace-pre-wrap">{message.content}</div>
                  )}
                  <div className="text-xs opacity-70 mt-1">
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
        <div className="px-4 py-3 border-t border-gray-800/50">
          <p className="text-xs text-gray-500 mb-2">Suggested questions:</p>
          <div className="flex flex-wrap gap-2">
            {suggestedQuestions.map((question, index) => (
              <button
                key={index}
                onClick={() => setInput(question)}
                className="px-3 py-1 bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs rounded-full transition-colors"
                disabled={isLoading}
              >
                {question}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div className="p-4 border-t border-gray-800/50">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder={`Ask about ${symbol} or market analysis...`}
            className="flex-1 px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all"
            disabled={isLoading}
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || isLoading}
            className="px-4 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white rounded-lg transition-all flex items-center gap-2"
          >
            {isLoading ? (
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
            <span className="hidden sm:inline">Send</span>
          </button>
        </div>
        <div className="mt-2 text-xs text-gray-500">
          Powered by AI • Market data integrated • {isConnected ? 'Connected' : 'Disconnected'}
        </div>
      </div>
    </div>
  );
}