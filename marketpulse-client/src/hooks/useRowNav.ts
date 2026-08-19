'use client';

import { useCallback, useState } from 'react';

export interface RowNavOptions {
  onEnter?: (index: number) => void;
  enabled?: boolean;
}

export function useRowNav(count: number, opts: RowNavOptions = {}) {
  const { onEnter, enabled = true } = opts;
  const [focusedIndex, setFocusedIndex] = useState(0);

  const move = useCallback(
    (delta: number) => {
      setFocusedIndex((prev) => Math.min(count - 1, Math.max(0, prev + delta)));
    },
    [count]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!enabled) return;
      switch (e.key) {
        case 'j':
        case 'ArrowDown':
          e.preventDefault();
          move(1);
          break;
        case 'k':
        case 'ArrowUp':
          e.preventDefault();
          move(-1);
          break;
        case 'Home':
          e.preventDefault();
          setFocusedIndex(0);
          break;
        case 'End':
          e.preventDefault();
          setFocusedIndex(count - 1);
          break;
        case 'Enter':
          e.preventDefault();
          onEnter?.(focusedIndex);
          break;
        default:
          break;
      }
    },
    [enabled, move, count, onEnter, focusedIndex]
  );

  return { focusedIndex, setFocusedIndex, handleKeyDown };
}
