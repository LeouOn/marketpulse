'use client';

import { useState, useEffect, useRef } from 'react';
import { Search, X } from 'lucide-react';
import { clsx } from 'clsx';

interface SymbolSearchProps {
  onSelect: (symbol: string) => void;
  placeholder?: string;
  className?: string;
}

const KNOWN_SYMBOLS = [
  { symbol: 'SPY', name: 'S&P 500 ETF', type: 'etf' },
  { symbol: 'QQQ', name: 'Nasdaq 100 ETF', type: 'etf' },
  { symbol: 'AAPL', name: 'Apple Inc.', type: 'stock' },
  { symbol: 'TSLA', name: 'Tesla Inc.', type: 'stock' },
  { symbol: 'NVDA', name: 'NVIDIA Corp.', type: 'stock' },
  { symbol: 'BTC-USD', name: 'Bitcoin', type: 'crypto' },
  { symbol: 'ETH-USD', name: 'Ethereum', type: 'crypto' },
  { symbol: 'VIX', name: 'CBOE Volatility Index', type: 'index' },
  { symbol: 'IWM', name: 'Russell 2000 ETF', type: 'etf' },
  { symbol: 'DIA', name: 'Dow Jones ETF', type: 'etf' },
];

const TYPE_COLORS: Record<string, string> = {
  stock: 'bg-blue-500/20 text-blue-400',
  etf: 'bg-purple-500/20 text-purple-400',
  crypto: 'bg-amber-500/20 text-amber-400',
  index: 'bg-emerald-500/20 text-emerald-400',
};

export function SymbolSearch({ onSelect, placeholder = 'Search symbol...', className }: SymbolSearchProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<typeof KNOWN_SYMBOLS>([]);
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      setOpen(false);
      return;
    }

    const timer = setTimeout(() => {
      const q = query.toLowerCase();
      const filtered = KNOWN_SYMBOLS.filter(
        (s) => s.symbol.toLowerCase().includes(q) || s.name.toLowerCase().includes(q)
      );
      setResults(filtered);
      setOpen(filtered.length > 0);
    }, 300);

    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    function handleEsc(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, []);

  function handleSelect(symbol: string) {
    onSelect(symbol);
    setQuery('');
    setOpen(false);
    inputRef.current?.blur();
  }

  return (
    <div ref={wrapperRef} className={clsx('relative', className)}>
      <div className="relative">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => {
            if (results.length > 0) setOpen(true);
          }}
          placeholder={placeholder}
          className="w-full h-9 pl-9 pr-8 bg-gray-900 border border-gray-700 rounded-lg text-sm text-gray-300 placeholder-gray-500 focus:outline-none focus:border-blue-500 transition-colors"
        />
        {query && (
          <button
            onClick={() => {
              setQuery('');
              setResults([]);
              setOpen(false);
            }}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
          >
            <X size={14} />
          </button>
        )}
      </div>

      {open && results.length > 0 && (
        <div className="absolute z-50 mt-1 w-full bg-gray-800 border border-gray-700 rounded-lg shadow-xl max-h-64 overflow-auto">
          {results.map((item) => (
            <button
              key={item.symbol}
              onClick={() => handleSelect(item.symbol)}
              className="w-full px-3 py-2 flex items-center gap-2 hover:bg-gray-700/50 transition-colors text-left"
            >
              <span className="font-semibold text-white text-sm">{item.symbol}</span>
              <span className="text-gray-400 text-sm truncate flex-1">{item.name}</span>
              <span className={clsx('text-[10px] px-1.5 py-0.5 rounded font-medium', TYPE_COLORS[item.type] ?? 'bg-gray-700 text-gray-400')}>
                {item.type.toUpperCase()}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
