'use client';

export type DotState = 'live' | 'offline' | 'stale' | 'error';

const STATE_STYLE: Record<DotState, { dot: string; text: string; fallbackLabel: string }> = {
  live: { dot: 'bg-pos', text: 'text-pos', fallbackLabel: 'LIVE' },
  offline: { dot: 'bg-neg', text: 'text-neg', fallbackLabel: 'OFFLINE' },
  stale: { dot: 'bg-warn', text: 'text-warn', fallbackLabel: 'STALE' },
  error: { dot: 'bg-neg', text: 'text-neg', fallbackLabel: 'ERROR' },
};

export function StateDot({ state, label, age }: { state: DotState; label?: string; age?: string }) {
  const s = STATE_STYLE[state];
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] font-mono">
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} aria-hidden />
      <span className={s.text}>{label ?? s.fallbackLabel}</span>
      {age && <span className="text-ink-muted">{age}</span>}
    </span>
  );
}
