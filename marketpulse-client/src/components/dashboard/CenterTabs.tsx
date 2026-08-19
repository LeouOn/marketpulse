'use client';

import { useState, useEffect } from 'react';
import { Activity, BarChart2, Target, TrendingUp, Settings, Globe } from 'lucide-react';
import { Sparkline } from '@/components/ui/Sparkline';
import RiskManagerTab from '@/components/RiskManagerTab';
import BacktestTab from '@/components/BacktestTab';
import OptionsFlowTab from '@/components/OptionsFlowTab';
import StrategyTab from '@/components/StrategyTab';
import MacroDashboard from '@/components/MacroDashboard';
import { MiniTable } from './MiniTable';
import { generateSparklineData, formatPrice, formatVolume } from './sparkline';
import type { MarketData } from './types';

export interface CenterTabsProps {
  majorIndices: Record<string, MarketData>;
  indexLabels: Record<string, string>;
  /** Pre-filtered commodities / crypto map. Null/empty hides the panel. */
  commoditiesCrypto: Record<string, MarketData> | null;
  macroLabels: Record<string, string>;
  sectorData: Record<string, number>;
}

const TABS = [
  { id: 'overview', label: 'Overview', icon: Activity },
  { id: 'backtest', label: 'Backtests', icon: BarChart2 },
  { id: 'risk', label: 'Risk', icon: Target },
  { id: 'options', label: 'Options', icon: TrendingUp },
  { id: 'strategy', label: 'Strategy', icon: Settings },
  { id: 'macro', label: 'Macro', icon: Globe },
] as const;

type TabId = (typeof TABS)[number]['id'];

/**
 * Center column: dense tab strip + active tab content.
 *
 *  - Tab strip: 11px uppercase mono labels, active = teal with bottom border.
 *  - Number keys `1`-`5` switch tabs (first five). Ignored while typing in
 *    input/textarea/contenteditable so it doesn't fight with the AI chat box
 *    or any other form on the page.
 *  - Overview content is rendered with the new MiniTable / sector-bar
 *    primitives. The other tabs are rendered as-is — Task 6 restyles them.
 */
export function CenterTabs({
  majorIndices,
  indexLabels,
  commoditiesCrypto,
  macroLabels,
  sectorData,
}: CenterTabsProps) {
  const [activeTab, setActiveTab] = useState<TabId>('overview');

  // Number-key tab switching (1-5)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (!target) return;
      if (
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.isContentEditable
      ) {
        return;
      }
      const idx = parseInt(e.key, 10);
      if (idx >= 1 && idx <= 5) {
        const next = TABS[idx - 1];
        if (next) {
          e.preventDefault();
          setActiveTab(next.id);
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <div className="space-y-2.5">
      {/* Tab strip */}
      <div className="panel">
        <div className="flex">
          {TABS.map((tab, i) => {
            const active = activeTab === tab.id;
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex-1 h-8 px-2 flex items-center justify-center gap-1.5 text-[11px] uppercase tracking-[0.08em] font-mono border-b-2 ${
                  active
                    ? 'text-teal border-teal'
                    : 'text-ink-muted hover:text-ink border-transparent'
                }`}
                aria-current={active ? 'page' : undefined}
              >
                <Icon size={11} />
                {tab.label}
                {i < 5 && (
                  <span className="text-[10px] font-mono text-ink-muted ml-0.5 hidden sm:inline">
                    {i + 1}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Active tab content */}
      <div className="space-y-2.5">
        {activeTab === 'overview' && (
          <OverviewTab
            majorIndices={majorIndices}
            indexLabels={indexLabels}
            commoditiesCrypto={commoditiesCrypto}
            macroLabels={macroLabels}
            sectorData={sectorData}
          />
        )}
        {activeTab === 'backtest' && <BacktestTab />}
        {activeTab === 'risk' && <RiskManagerTab />}
        {activeTab === 'options' && <OptionsFlowTab />}
        {activeTab === 'strategy' && <StrategyTab />}
        {activeTab === 'macro' && <MacroDashboard />}
      </div>
    </div>
  );
}

interface OverviewTabProps {
  majorIndices: Record<string, MarketData>;
  indexLabels: Record<string, string>;
  commoditiesCrypto: Record<string, MarketData> | null;
  macroLabels: Record<string, string>;
  sectorData: Record<string, number>;
}

function OverviewTab({
  majorIndices,
  indexLabels,
  commoditiesCrypto,
  macroLabels,
  sectorData,
}: OverviewTabProps) {
  const indexRows = buildRows(majorIndices, indexLabels);
  const commodityRows = commoditiesCrypto ? buildRows(commoditiesCrypto, macroLabels) : [];

  return (
    <>
      {indexRows.length > 0 && (
        <MiniTable
          title="Major Indices"
          columns={INDICES_COLUMNS}
          rows={indexRows}
        />
      )}
      {commodityRows.length > 0 && (
        <MiniTable
          title="Commodities & Crypto"
          columns={INDICES_COLUMNS}
          rows={commodityRows}
        />
      )}
      {Object.keys(sectorData).length > 0 && (
        <SectorPerformance data={sectorData} />
      )}
    </>
  );
}

const INDICES_COLUMNS = [
  { key: 'symbol', label: 'Symbol' },
  { key: 'trend', label: 'Trend' },
  { key: 'price', label: 'Price', num: true },
  { key: 'change', label: 'Change', num: true },
  { key: 'pct', label: '%', num: true },
  { key: 'volume', label: 'Volume', num: true },
];

function buildRows(
  data: Record<string, MarketData>,
  labels: Record<string, string>,
): Array<Record<string, React.ReactNode>> {
  return Object.entries(data)
    .filter(([, md]) => md && md.price !== 0)
    .map(([symbol, md]) => {
      const sparklineData = generateSparklineData(md.price, md.change);
      const changeClass = md.change >= 0 ? 'text-pos' : 'text-neg';
      const sign = md.change >= 0 ? '+' : '';
      return {
        symbol: labels[symbol] || symbol,
        trend: (
          <Sparkline
            data={sparklineData}
            width={60}
            height={20}
            className="inline-block"
          />
        ),
        price: formatPrice(md.price, symbol),
        change: <span className={changeClass}>{sign}{md.change.toFixed(2)}</span>,
        pct: <span className={changeClass}>{sign}{md.change_pct.toFixed(2)}%</span>,
        volume: formatVolume(md.volume),
      };
    });
}

function SectorPerformance({ data }: { data: Record<string, number> }) {
  const sorted = Object.entries(data).sort(([, a], [, b]) => b - a);
  const maxAbs = sorted.length > 0 ? Math.max(...sorted.map(([, p]) => Math.abs(p))) : 1;

  return (
    <div className="panel">
      <div className="border-b border-line-subtle px-3 h-8 flex items-center">
        <span className="panel-title">Sector Performance</span>
      </div>
      <div className="p-2.5 space-y-2">
        {sorted.map(([sector, performance], index) => {
          const isPositive = performance >= 0;
          const width = (Math.abs(performance) / maxAbs) * 100;
          const isTop3 = index < 3;
          const isBottom3 = index >= sorted.length - 3;
          const labelClass = isTop3
            ? 'text-pos'
            : isBottom3
            ? 'text-neg'
            : 'text-ink-secondary';
          return (
            <div key={sector}>
              <div className="flex items-center justify-between mb-1">
                <span className={`text-[12px] ${isTop3 || isBottom3 ? 'font-semibold' : ''} ${labelClass}`}>
                  {sector}
                </span>
                <span
                  className={`text-[12px] font-mono tabular-nums font-semibold ${
                    isPositive ? 'text-pos' : 'text-neg'
                  }`}
                >
                  {isPositive ? '+' : ''}
                  {performance.toFixed(2)}%
                </span>
              </div>
              <div className="sector-bar-container">
                <div
                  className={`sector-bar ${isPositive ? 'sector-bar-positive' : 'sector-bar-negative'}`}
                  style={{ width: `${width}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}