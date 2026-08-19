'use client';

import { useCallback, useEffect, useState } from 'react';

interface Shortcut {
  keys: string[];
  label: string;
}

const SHORTCUTS: Shortcut[] = [
  { keys: ['Ctrl', 'K'], label: 'command palette' },
  { keys: ['/'], label: 'command palette' },
  { keys: ['?'], label: 'this help' },
  { keys: ['j', '/', 'k'], label: 'row focus (down / up)' },
  { keys: ['↑', '↓'], label: 'row focus (down / up)' },
  { keys: ['Enter'], label: 'open focused row' },
  { keys: ['Esc'], label: 'clear focus / close' },
  { keys: ['1'], label: 'switch dashboard tab' },
  { keys: ['2'], label: 'switch dashboard tab' },
  { keys: ['3'], label: 'switch dashboard tab' },
  { keys: ['4'], label: 'switch dashboard tab' },
  { keys: ['5'], label: 'switch dashboard tab' },
  { keys: ['palette'], label: 'toggle light / dark theme' },
];

export function KbdHelp() {
  const [open, setOpen] = useState(false);

  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const typing =
        target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable;
      // ? is shift+/ on US layouts; e.key === '?' is the cleanest detector.
      if (e.key === '?' && !typing) {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === 'Escape') {
        close();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [close]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center"
      role="dialog"
      aria-label="Keyboard shortcuts"
    >
      <div className="absolute inset-0 bg-canvas/70" onClick={close} />
      <div className="relative w-[520px] max-w-[92vw] panel shadow-none">
        <div className="border-b border-line-subtle px-3 h-8 flex items-center justify-between">
          <span className="panel-title">KEYBOARD SHORTCUTS</span>
          <button
            onClick={close}
            className="text-ink-muted hover:text-ink text-[12px] font-mono"
            aria-label="Close keyboard shortcuts"
          >
            esc
          </button>
        </div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-2 px-3 py-3">
          {SHORTCUTS.map((s, i) => (
            <div key={i} className="flex items-center gap-2 text-[12px]">
              <div className="flex items-center gap-1 shrink-0 min-w-[72px]">
                {s.keys.map((k, ki) => (
                  <span key={ki} className="kbd">
                    {k}
                  </span>
                ))}
              </div>
              <span className="text-ink-secondary">{s.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
