'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTheme } from '@/components/theme-provider';

interface Command {
  id: string;
  label: string;
  hint?: string;
  run: () => void;
}

const SYMBOL_RE = /^[A-Z0-9.\-]{1,10}$/;

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(0);
  const router = useRouter();
  const { toggleTheme } = useTheme();
  const inputRef = useRef<HTMLInputElement>(null);

  const close = useCallback(() => {
    setOpen(false);
    setQuery('');
    setSelected(0);
  }, []);

  useEffect(() => {
    const openPalette = () => setOpen(true);
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const typing =
        target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === '/' && !typing) {
        e.preventDefault();
        setOpen(true);
      } else if (e.key === 'Escape') {
        close();
      }
    };
    window.addEventListener('mp:open-palette', openPalette);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('mp:open-palette', openPalette);
      window.removeEventListener('keydown', onKey);
    };
  }, [close]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const commands = useMemo<Command[]>(() => {
    const nav: Command[] = [
      { id: 'dashboard', label: 'Dashboard', hint: '/', run: () => router.push('/') },
      { id: 'trending', label: 'Trending', hint: '/trending', run: () => router.push('/trending') },
      { id: 'charts', label: 'Charts', hint: '/chart/SPY', run: () => router.push('/chart/SPY') },
      { id: 'symbol', label: 'Symbol', hint: '/symbol/SPY', run: () => router.push('/symbol/SPY') },
      { id: 'research', label: 'Research', hint: '/research/BTC', run: () => router.push('/research/BTC') },
      { id: 'compare', label: 'Compare assets', hint: '/research/compare', run: () => router.push('/research/compare') },
      { id: 'reports', label: 'Reports', hint: '/research/reports', run: () => router.push('/research/reports') },
      { id: 'theme', label: 'Toggle light/dark theme', run: toggleTheme },
    ];
    const q = query.trim().toUpperCase();
    if (q && SYMBOL_RE.test(q)) {
      nav.unshift({ id: `sym-${q}`, label: `Go to ${q}`, hint: `/chart/${q}`, run: () => router.push(`/chart/${q}`) });
    }
    return nav;
  }, [query, router, toggleTheme]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((c) => c.label.toLowerCase().includes(q) || c.id.includes(q));
  }, [commands, query]);

  const runSelected = useCallback(
    (cmd: Command | undefined) => {
      if (!cmd) return;
      close();
      cmd.run();
    },
    [close]
  );

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh]" role="dialog" aria-label="Command palette">
      <div className="absolute inset-0 bg-canvas/70" onClick={close} />
      <div className="relative w-[480px] max-w-[92vw] panel shadow-none">
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setSelected(0);
          }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') { e.preventDefault(); setSelected((s) => Math.min(filtered.length - 1, s + 1)); }
            if (e.key === 'ArrowUp') { e.preventDefault(); setSelected((s) => Math.max(0, s - 1)); }
            if (e.key === 'Enter') { e.preventDefault(); runSelected(filtered[selected]); }
          }}
          placeholder="Search symbols, pages, actions…"
          className="w-full h-9 bg-transparent border-0 border-b border-line-subtle px-3 text-[13px] font-mono text-ink placeholder:text-ink-muted focus:outline-none"
          aria-label="Search symbols pages actions"
        />
        <ul className="max-h-[320px] overflow-y-auto py-1">
          {filtered.map((c, i) => (
            <li
              key={c.id}
              onMouseEnter={() => setSelected(i)}
              onClick={() => runSelected(c)}
              className={`h-7 px-3 flex items-center justify-between cursor-pointer text-[12.5px] ${
                i === selected ? 'bg-sel-dim text-ink' : 'text-ink-secondary'
              }`}
            >
              <span>{c.label}</span>
              {c.hint && <span className="font-mono text-[10.5px] text-ink-muted">{c.hint}</span>}
            </li>
          ))}
          {filtered.length === 0 && (
            <li className="h-7 px-3 flex items-center text-[12px] text-ink-muted">No matches</li>
          )}
        </ul>
        <div className="border-t border-line-subtle px-3 h-6 flex items-center gap-2 text-[10px] font-mono text-ink-muted">
          <span className="kbd">↑↓</span> navigate <span className="kbd">↵</span> run <span className="kbd">esc</span> close
        </div>
      </div>
    </div>
  );
}
