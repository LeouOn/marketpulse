'use client';

import { useState, useEffect } from 'react';
import { Clock, Wifi, WifiOff, Search, Menu } from 'lucide-react';

interface TopBarProps {
  onMenuToggle: () => void;
  isConnected: boolean;
  lastUpdate: Date | null;
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function formatLastUpdate(date: Date): string {
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function TopBar({ onMenuToggle, isConnected, lastUpdate }: TopBarProps) {
  const [now, setNow] = useState<Date | null>(null);

  useEffect(() => {
    setNow(new Date());
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <header className="h-14 bg-gray-900 border-b border-gray-800 px-4 flex items-center gap-4 shrink-0">
      <button
        onClick={onMenuToggle}
        className="lg:hidden p-1 text-gray-400 hover:text-white transition-colors"
        aria-label="Toggle menu"
      >
        <Menu size={20} />
      </button>

      <span className="text-lg font-bold bg-gradient-to-r from-blue-500 to-purple-500 bg-clip-text text-transparent">
        MarketPulse
      </span>

      <div className="flex-1 flex justify-center">
        <div className="relative hidden md:block">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            placeholder="Search symbol..."
            className="w-[300px] h-9 pl-9 pr-3 bg-gray-800 border border-gray-700 rounded-lg text-sm text-gray-300 placeholder-gray-500 focus:outline-none focus:border-blue-500 transition-colors"
          />
        </div>
      </div>

      <div className="flex items-center gap-4 text-sm text-gray-400">
        <div className="flex items-center gap-1.5">
          {isConnected ? (
            <>
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              <span className="text-emerald-400">Live</span>
            </>
          ) : (
            <>
              <span className="w-2 h-2 rounded-full bg-red-500" />
              <span className="text-red-400">Offline</span>
            </>
          )}
        </div>

        {lastUpdate && (
          <span className="hidden sm:block text-gray-500">
            Updated {formatLastUpdate(lastUpdate)}
          </span>
        )}

        <div className="flex items-center gap-1.5 text-gray-500">
          <Clock size={14} />
          <span>{now ? formatTime(now) : '--:--:--'}</span>
        </div>
      </div>
    </header>
  );
}
