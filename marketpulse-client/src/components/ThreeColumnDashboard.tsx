'use client';

import { useState, useEffect } from 'react';
import { RefreshCw } from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { marketKeys } from '@/hooks/useMarketData';
import type { DashboardData, MacroData, MarketBreadth } from '@/types/market';
import { CommandCenter } from './dashboard/CommandCenter';
import { CenterTabs } from './dashboard/CenterTabs';
import { AiChatPanel } from './dashboard/AiChatPanel';
import { INDEX_LABELS, MACRO_LABELS, MACRO_SYMBOLS, macroUnavailableReason } from './dashboard/labels';
import type { MarketData, MarketRegime, SessionInfo } from './dashboard/types';

export function ThreeColumnDashboard() {
  const queryClient = useQueryClient();
  const dashQ = useQuery({
    queryKey: marketKeys.dashboard(),
    queryFn: () => apiFetch<DashboardData>('/market/dashboard'),
    refetchInterval: 60_000,
    retry: 1,
  });
  const macroQ = useQuery({
    queryKey: marketKeys.macro(),
    queryFn: () => apiFetch<MacroData>('/market/macro'),
    refetchInterval: 60_000,
    retry: 1,
  });
  const breadthQ = useQuery({
    queryKey: [...marketKeys.all, 'breadth'] as const,
    queryFn: () => apiFetch<MarketBreadth>('/market/breadth'),
    refetchInterval: 60_000,
    retry: 1,
  });

  const dashboardData = dashQ.data ?? null;
  const macroData = macroQ.data ?? null;
  // T7a withholds fabricated macro data with an HTTP-200 success:false
  // envelope, which apiFetch does not throw for — extract the reason so
  // the overview can explain the missing section instead of hiding it.
  const macroUnavailable = macroUnavailableReason(macroData);
  // apiFetch already unwraps `{ data }`; do not read `.data` again.
  const breadthData = breadthQ.data ?? null;
  const loading = dashQ.isPending && !dashQ.data;
  const failed = [dashQ, macroQ, breadthQ].filter((q) => q.isError);
  const error = failed.length
    ? `Failed to load some market data: ${failed.map((q) => (q.error as Error)?.message ?? 'error').join('; ')}`
    : null;
  const lastUpdate = dashQ.dataUpdatedAt ? new Date(dashQ.dataUpdatedAt) : null;
  const [sessionTime, setSessionTime] = useState('');
  const [sessionCountdown, setSessionCountdown] = useState('');

  const fetchData = () => {
    void queryClient.invalidateQueries({ queryKey: marketKeys.all });
  };

  useEffect(() => {
    const p2 = (n: number) => n.toString().padStart(2, '0');
    const tick = () => {
      const now = new Date();
      setSessionTime(`${p2(now.getHours())}:${p2(now.getMinutes())}:${p2(now.getSeconds())}`);
      const close = new Date(); close.setHours(16, 0, 0, 0);
      let diff = close.getTime() - now.getTime();
      if (diff < 0) diff += 86_400_000;
      setSessionCountdown(`${Math.floor(diff / 36e5)}h ${Math.floor((diff % 36e5) / 6e4)}m`);
    };
    tick(); const i = setInterval(tick, 1000); return () => clearInterval(i);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="text-center">
          <RefreshCw className="w-10 h-10 text-sel animate-spin mx-auto mb-3" />
          <p className="text-[13px] text-ink-secondary">Loading market data...</p>
        </div>
      </div>
    );
  }
  const sym = dashboardData?.symbols || {};
  const nqData = sym['qqq'] || sym['QQQ'];
  const sectorData = macroData?.sector_performance || dashboardData?.sector_performance || {};
  const commoditiesCrypto = macroData
    ? (Object.fromEntries(Object.entries(macroData).filter(([k, v]) => MACRO_SYMBOLS.includes(k) && v && typeof v === 'object')) as Record<string, MarketData>)
    : null;
  const bias = dashboardData?.marketBias?.toLowerCase() || '';
  const vol = dashboardData?.volatilityRegime?.toLowerCase() || '';
  const regime: MarketRegime =
    bias === 'bullish' && (vol === 'low' || vol === 'normal') ? 'favorable'
    : bias === 'bearish' || vol === 'high' || vol === 'extreme' ? 'avoid' : 'mixed';
  const session: SessionInfo = { status: dashboardData?.market_session || 'Regular Hours', countdown: sessionCountdown, time: sessionTime };
  const llmMarketData = { ...dashboardData, symbols: dashboardData?.symbols || {}, sector_performance: sectorData, macro_data: macroData, breadth_data: breadthData };

  return (
    <div className="p-2.5">
      {error && (
        <div role="alert" aria-live="polite" className="mb-2.5 px-3 min-h-8 py-1.5 border border-neg bg-neg-dim rounded-[2px] flex items-center text-neg text-[12px]">
          {error}<button onClick={fetchData} className="ml-2 underline">Retry</button>
        </div>
      )}
      <div className="mp-dash-head">
        <div>
          <h1 className="font-mono text-[15px] font-bold tracking-[0.12em] text-ink">MarketPulse</h1>
          <p className="text-[11px] text-ink-muted tracking-[0.04em]">Professional Trading Dashboard</p>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdate && <span className="text-[11px] font-mono text-ink-muted hidden sm:block">UPD {lastUpdate.toLocaleTimeString()}</span>}
          <button onClick={fetchData} disabled={dashQ.isFetching} className="btn btn-primary" title="Refresh data" aria-label="Refresh data">
            <RefreshCw className={`w-3.5 h-3.5 ${dashQ.isFetching ? 'animate-spin' : ''}`} />
          </button>
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-[0.08em] text-ink-muted">Session P&amp;L</div>
            <div className="font-mono tabular-nums text-[15px] text-ink-muted">—</div>
            <div className="text-[10px] font-mono text-ink-muted">not wired</div>
          </div>
        </div>
      </div>
      <div className="mp-dash">
        <div>
          <CommandCenter heroSymbol="NASDAQ 100" heroCode="QQQ"
            heroPrice={nqData?.price ?? 0} heroChange={nqData?.change ?? 0} heroChangePct={nqData?.change_pct ?? 0}
            breadth={breadthData} regime={regime} session={session} />
        </div>
        <div>
          <CenterTabs majorIndices={sym as Record<string, MarketData>} indexLabels={INDEX_LABELS}
            commoditiesCrypto={commoditiesCrypto} macroLabels={MACRO_LABELS} sectorData={sectorData}
            macroUnavailable={macroUnavailable} />
        </div>
        <div>
          <AiChatPanel marketData={llmMarketData} />
        </div>
      </div>
    </div>
  );
}