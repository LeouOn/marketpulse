'use client';

import React from 'react';

export interface MiniTableColumn {
  key: string;
  label: string;
  /** When true, the cell renders as a right-aligned mono numeric. */
  num?: boolean;
}

export interface MiniTableProps {
  title: string;
  columns: MiniTableColumn[];
  /** Map of column key to rendered cell content (already formatted). */
  rows: Array<Record<string, React.ReactNode>>;
  /** Optional row key extractor; defaults to index. */
  rowKey?: (row: Record<string, React.ReactNode>, index: number) => React.Key;
  /** Optional className for the wrapping <table>. */
  className?: string;
}

/**
 * Thin wrapper over `.data-table` with a `panel-title` header row.
 *
 * Used by the Overview tab (Major Indices, Commodities & Crypto) and any
 * other panel that needs a compact dense table.
 */
export function MiniTable({ title, columns, rows, rowKey, className }: MiniTableProps) {
  return (
    <div className="panel">
      <div className="border-b border-line-subtle px-3 h-8 flex items-center">
        <span className="panel-title">{title}</span>
      </div>
      <div className="overflow-x-auto">
        <table className={`data-table ${className ?? ''}`}>
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c.key} className={c.num ? 'num' : ''}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={rowKey ? rowKey(row, i) : i} className="hover:bg-surface-hover transition-colors">
                {columns.map((c) => (
                  <td key={c.key} className={c.num ? 'num' : ''}>
                    {row[c.key]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}