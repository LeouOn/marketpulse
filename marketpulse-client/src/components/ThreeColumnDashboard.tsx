'use client';

import { useState, useEffect } from 'react';
import { RefreshCw } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import type { DashboardData, MacroData, MarketBreadth } from '@/types/market';
import { CommandCenter } from './dashboard/CommandCenter';
import { CenterTabs } from './dashboard/CenterTabs';
import { AiChatPanel } from './dashboard/AiChatPanel';
import { INDEX_LABELS, MACRO_LABELS, MACRO_SYMBOLS } from './dashboard/labels';
import type { MarketData, MarketRegime, SessionInfo } from './dashboard/types';

export function ThreeColumnDashboard() {
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [macroData, setMacroData] = useState<MacroData | null>(null);
  const [breadthData, setBreadthData] = useState<MarketBreadth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [sessionTime, setSessionTime] = useState('');
  const [sessionCountdown, setSessionCountdown] = useState('');

  const fetchData = async () => {
    try {
      setError(null);
      const [d, m, b] = await Promise.allSettled([apiFetch<any>('/market/dashboard'), apiFetch<any>('/market/macro'), apiFetch<any>('/market/breadth')]);
      if (d.status === 'fulfilled') setDashboardData(d.value);
      if (m.status === 'fulfilled') setMacroData(m.value?.data || m.value);
      if (b.status === 'fulfilled') setBreadthData(b.value?.data || null);
      const fail = [d, m, b].find((r) => r.status === 'rejected') as PromiseRejectedResult | undefined;
      if (fail) setError(`Failed to load some market data: ${fail.reason?.message || 'Unknown error'}`);
      setLastUpdate(new Date()); setLoading(false);
    } catch (err) {
      console.error('Failed to fetch data:', err);
      setError('Failed to load market data. Please check your connection.');
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); const i = setInterval(fetchData, 60000); return () => clearInterval(i); }, []);

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
      <div className="min-h-screen bg-canvas flex items-center justify-center">
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
    <div className="min-h-screen bg-canvas p-2.5">
      {error && (
        <div className="mb-2.5 px-3 h-8 border border-neg bg-neg-dim rounded-[2px] flex items-center text-neg text-[12px]">
          {error}<button onClick={fetchData} className="ml-2 underline">Retry</button>
        </div>
      )}
      <div className="mb-2.5 flex items-center justify-between">
        <div>
          <h1 className="font-mono text-[15px] font-bold tracking-[0.12em] text-ink">MarketPulse</h1>
          <p className="text-[11px] text-ink-muted tracking-[0.04em]">Professional Trading Dashboard</p>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdate && <span className="text-[11px] font-mono text-ink-muted hidden sm:block">UPD {lastUpdate.toLocaleTimeString()}</span>}
          <button onClick={fetchData} disabled={loading} className="btn btn-primary" title="Refresh data" aria-label="Refresh data">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-[0.08em] text-ink-muted">Session P&amp;L</div>
            <div className="font-mono tabular-nums text-[15px] text-pos">+$385.00</div>
            <div className="text-[10px] font-mono text-ink-muted">Limit $1000</div>
          </div>
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-2.5">
        <div className="lg:col-span-3">
          <CommandCenter heroSymbol="NASDAQ 100" heroCode="QQQ"
            heroPrice={nqData?.price ?? 0} heroChange={nqData?.change ?? 0} heroChangePct={nqData?.change_pct ?? 0}
            breadth={breadthData} regime={regime} session={session} />
        </div>
        <div className="lg:col-span-6">
          <CenterTabs majorIndices={sym as Record<string, MarketData>} indexLabels={INDEX_LABELS}
            commoditiesCrypto={commoditiesCrypto} macroLabels={MACRO_LABELS} sectorData={sectorData} />
        </div>
        <div className="lg:col-span-3">
          <AiChatPanel marketData={llmMarketData} />
        </div>
      </div>
    </div>
  );
}