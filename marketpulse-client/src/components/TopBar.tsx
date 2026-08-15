'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Clock, Search, Menu, Sun, Moon } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useTheme } from '@/components/theme-provider';

interface TopBarProps {
  onMenuToggle: () => void;
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export function TopBar({ onMenuToggle }: TopBarProps) {
  const [now, setNow] = useState<Date | null>(null);
  const { theme, toggleTheme } = useTheme();
  const queryClient = useQueryClient();

  useEffect(() => {
    setNow(new Date());
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const dashboardState = queryClient.getQueryState(['market', 'dashboard']);
  const isConnected = dashboardState?.status === 'success';
  const lastUpdate = dashboardState?.dataUpdatedAt
    ? new Date(dashboardState.dataUpdatedAt)
    : null;

  return (
    <header className="h-11 bg-surface border-b border-line-subtle px-3 flex items-center gap-3 shrink-0">
      <button onClick={onMenuToggle} className="lg:hidden p-1 text-ink-secondary hover:text-ink" aria-label="Toggle menu">
        <Menu size={16} />
      </button>

      <Link href="/" className="font-mono text-[13px] font-bold tracking-[0.12em] text-ink flex items-center gap-2">
        <span className="w-2 h-2 bg-teal inline-block" aria-hidden />
        MARKETPULSE
      </Link>

      <div className="flex-1 flex justify-center">
        <button
          onClick={() => window.dispatchEvent(new CustomEvent('mp:open-palette'))}
          data-testid="palette-trigger"
          className="hidden md:flex w-[280px] h-7 pl-2 pr-1.5 bg-surface-raised border border-line rounded-[3px] text-[12px] text-ink-muted text-left hover:border-line-strong items-center justify-between cursor-pointer"
        >
          <span className="flex items-center gap-1.5"><Search size={12} /> Search symbols, pages…</span>
          <span className="kbd">Ctrl K</span>
        </button>
      </div>

      {/* live status — StateDot pattern */}
      <div className="flex items-center gap-1.5 text-[11px] font-mono">
        {isConnected ? (
          <><span className="w-1.5 h-1.5 rounded-full bg-pos" /><span className="text-pos">LIVE</span></>
        ) : (
          <><span className="w-1.5 h-1.5 rounded-full bg-neg" /><span className="text-neg">OFFLINE</span></>
        )}
      </div>
      {lastUpdate && (
        <span className="hidden sm:block text-[11px] font-mono text-ink-muted">
          UPD {formatTime(lastUpdate)}
        </span>
      )}
      <button
        onClick={toggleTheme}
        data-testid="theme-toggle"
        aria-label="Toggle theme"
        className="p-1 text-ink-secondary hover:text-ink border border-line rounded-[3px] h-7 w-7 flex items-center justify-center"
      >
        {theme === 'dark' ? <Sun size={13} /> : <Moon size={13} />}
      </button>
      <div className="flex items-center gap-1.5 text-[11px] font-mono text-ink-secondary">
        <Clock size={12} />
        <span>{now ? formatTime(now) : '--:--:--'}</span>
      </div>
    </header>
  );
}
