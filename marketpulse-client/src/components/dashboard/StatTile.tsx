'use client';

import React from 'react';

export interface StatTileProps {
  label: string;
  value: React.ReactNode;
  /** Signed change: positive renders text-pos, negative text-neg, 0 neutral. */
  delta?: number;
  /** When true, the value renders in the JetBrains Mono face with tabular nums. */
  mono?: boolean;
  /** Optional suffix appended to delta (e.g. '%'). Ignored when delta is undefined. */
  deltaSuffix?: string;
  /** Tooltip / aria-label override; defaults to label. */
  title?: string;
}

/**
 * Dense stat tile used inside Command Center and other dashboard panels.
 *
 *  - Label: 11px uppercase tracking
 *  - Value: 15-22px (mono when `mono` is true)
 *  - Delta: small mono line colored via sign
 */
export function StatTile({ label, value, delta, mono, deltaSuffix = '', title }: StatTileProps) {
  const deltaClass =
    delta === undefined
      ? 'hidden'
      : delta > 0
      ? 'text-pos'
      : delta < 0
      ? 'text-neg'
      : 'text-ink-muted';

  const deltaSign = delta !== undefined ? (delta > 0 ? '+' : '') : '';

  return (
    <div className="bg-surface-raised border border-line-subtle rounded-[2px] px-2 py-1.5">
      <div className="panel-title">{label}</div>
      <div
        className={`text-[15px] leading-tight mt-0.5 ${mono ? 'font-mono tabular-nums' : ''}`}
        title={title ?? label}
      >
        {value}
      </div>
      {delta !== undefined && (
        <div className={`text-[11px] font-mono tabular-nums mt-0.5 ${deltaClass}`}>
          {deltaSign}
          {delta.toFixed(2)}
          {deltaSuffix}
        </div>
      )}
    </div>
  );
}