'use client';

/**
 * Asset picker dropdown for the Multi-Asset Macro Research Lab (W5 T22).
 *
 * Renders the 5 supported assets (BTC / GOLD / OIL / EQUITIES / HOUSING) as a
 * compact dropdown whose visual tokens match the dashboard tab control in
 * `ThreeColumnDashboard.tsx` (bg-gray-900, border-gray-700, emerald-400 accent).
 *
 * The options list is hard-coded so the picker works without a network round
 * trip. If T20's `GET /api/research/assets` returns extra metadata later, the
 * caller may pass `options` to override the default set.
 */

import { useEffect, useRef, useState } from 'react';
import { ChevronDown, Check } from 'lucide-react';

export interface AssetOption {
  /** Registry key used in URLs + API paths (e.g. "BTC"). */
  key: string;
  /** Human label shown in the trigger + menu (e.g. "Bitcoin"). */
  label: string;
  /** Optional secondary line (e.g. ticker / source). */
  sublabel?: string;
}

/**
 * Canonical asset list. Keys MUST match `AssetRegistry` in
 * `src/research/assets.py` (T11) and the parametrized tests in
 * `tests/test_research_router_multiasset.py`.
 */
export const ASSET_OPTIONS: AssetOption[] = [
  { key: 'BTC', label: 'Bitcoin', sublabel: 'BTC-USD' },
  { key: 'GOLD', label: 'Gold', sublabel: 'XAUUSD spot' },
  { key: 'OIL', label: 'Oil (WTI)', sublabel: 'CL=F front month' },
  { key: 'EQUITIES', label: 'US Equities', sublabel: 'S&P 500' },
  { key: 'HOUSING', label: 'Housing', sublabel: 'Case-Shiller' },
];

/** Valid registry keys — used by the route page for cheap validation. */
export const ASSET_KEYS: ReadonlySet<string> = new Set(
  ASSET_OPTIONS.map((o) => o.key),
);

interface AssetPickerProps {
  /** Currently selected asset key (case-insensitive — upper-cased internally). */
  value: string;
  /** Override the default option set (e.g. from `GET /api/research/assets`). */
  options?: AssetOption[];
  /** Called with the new asset key when the user picks one. */
  onChange: (assetKey: string) => void;
  /** Disable interaction (e.g. while a chat turn is streaming). */
  disabled?: boolean;
}

export function AssetPicker({
  value,
  options = ASSET_OPTIONS,
  onChange,
  disabled,
}: AssetPickerProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const normalized = value.toUpperCase();
  const current = options.find((o) => o.key === normalized) ?? options[0];

  // Close on outside click / Escape. Matches the pattern used by the model
  // selector in `components/llm-chat.tsx`.
  useEffect(() => {
    if (!open) return;
    const handleDown = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', handleDown);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handleDown);
      document.removeEventListener('keydown', handleKey);
    };
  }, [open]);

  return (
    <div ref={containerRef} className="relative inline-block">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 bg-gray-900 border border-gray-700 hover:border-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg pl-3 pr-2 py-2 text-sm text-white transition-colors"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Select asset, currently ${current?.label ?? value}`}
      >
        <span className="font-mono text-[10px] tracking-wide bg-emerald-500/15 text-emerald-400 px-1.5 py-0.5 rounded">
          {current?.key ?? normalized}
        </span>
        <span className="font-medium">{current?.label ?? normalized}</span>
        <ChevronDown
          className={`w-4 h-4 text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open && (
        <ul
          role="listbox"
          className="absolute right-0 z-50 mt-1 w-64 max-h-80 overflow-auto bg-gray-900 border border-gray-700 rounded-lg shadow-xl"
        >
          {options.map((opt) => {
            const active = opt.key === normalized;
            return (
              <li key={opt.key} role="option" aria-selected={active}>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => {
                    onChange(opt.key);
                    setOpen(false);
                  }}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 text-left transition-colors ${
                    active
                      ? 'bg-emerald-600/15 text-emerald-300'
                      : 'text-gray-300 hover:bg-gray-800'
                  }`}
                >
                  <span className="font-mono text-[10px] tracking-wide bg-gray-800 text-gray-400 px-1.5 py-0.5 rounded min-w-[3.75rem] text-center">
                    {opt.key}
                  </span>
                  <span className="flex-1 min-w-0">
                    <span className="block text-sm font-medium text-white truncate">
                      {opt.label}
                    </span>
                    {opt.sublabel && (
                      <span className="block text-[11px] text-gray-500 truncate">
                        {opt.sublabel}
                      </span>
                    )}
                  </span>
                  {active && <Check className="w-4 h-4 text-emerald-400 shrink-0" />}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export default AssetPicker;
