'use client';

import React from 'react';

interface PhaseInfo {
  phase: string;
  label: string;
  icon: string;
}

const PHASES: PhaseInfo[] = [
  { phase: 'plan', label: 'Plan', icon: '\u25CB' },
  { phase: 'data_fetching', label: 'Data', icon: '\u2B24' },
  { phase: 'data_complete', label: 'Data Done', icon: '\u25C9' },
  { phase: 'agents_running', label: 'Agents', icon: '\u2B24' },
  { phase: 'agent_done', label: 'Agents Done', icon: '\u25C9' },
  { phase: 'draft_ready', label: 'Draft', icon: '\u25C9' },
  { phase: 'critiquing', label: 'Critique', icon: '\u2B24' },
  { phase: 'final_ready', label: 'Final', icon: '\u2714' },
];

interface PipelineProgressProps {
  currentPhase: string;
  agentDoneCount: number;
  totalAgents: number;
}

export function PipelineProgress({ currentPhase, agentDoneCount, totalAgents }: PipelineProgressProps) {
  const currentIdx = PHASES.findIndex(p => p.phase === currentPhase);

  return (
    <div className="w-full px-4 py-2 bg-surface border-b border-line-subtle">
      <div className="flex items-center gap-1">
        {PHASES.map((p, i) => {
          const isPast = i < currentIdx;
          const isCurrent = i === currentIdx;
          const isFuture = i > currentIdx;

          // Status-dot palette: pos for past, teal for current, ink-muted for future.
          let dotBg = 'bg-surface-hover';
          let labelColor = 'text-ink-muted';
          if (isPast) { dotBg = 'bg-pos'; labelColor = 'text-pos'; }
          if (isCurrent) { dotBg = 'bg-teal'; labelColor = 'text-teal'; }

          return (
            <React.Fragment key={p.phase}>
              <div className="flex flex-col items-center">
                <div className={`w-3 h-3 rounded-full ${dotBg} transition-colors duration-300`} />
                <span className={`text-[10.5px] font-mono uppercase tracking-wide mt-0.5 ${labelColor}`}>
                  {p.label}
                </span>
              </div>
              {i < PHASES.length - 1 && (
                <div className={`flex-1 h-1 ${isPast ? 'bg-pos' : 'bg-surface-raised'} transition-colors duration-300`} />
              )}
            </React.Fragment>
          );
        })}
      </div>
      {currentPhase === 'agents_running' && (
        <div className="text-xs text-teal mt-1 text-center font-mono">
          Agents: {agentDoneCount}/{totalAgents} complete
        </div>
      )}
    </div>
  );
}