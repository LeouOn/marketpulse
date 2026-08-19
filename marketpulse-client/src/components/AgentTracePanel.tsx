'use client';

import React from 'react';

interface AgentTrace {
  agentName: string;
  status: 'pending' | 'running' | 'done';
  content: string;
  toolsUsed: string[];
}

interface AgentTracePanelProps {
  agents: AgentTrace[];
  expanded: boolean;
  onToggle: () => void;
}

export function AgentTracePanel({ agents, expanded, onToggle }: AgentTracePanelProps) {
  return (
    <div className="bg-surface border-l border-line-subtle h-full flex flex-col">
      <div
        className="flex items-center justify-between px-3 py-2 bg-surface-raised cursor-pointer"
        onClick={onToggle}
      >
        <span className="panel-title">
          Agent Trace ({agents.filter(a => a.status === 'done').length}/{agents.length})
        </span>
        <span className="text-ink-muted text-xs">{expanded ? '\u25B2' : '\u25BC'}</span>
      </div>

      {expanded && (
        <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
          {agents.map((agent) => {
            const statusBorder =
              agent.status === 'done' ? 'border-pos' :
              agent.status === 'running' ? 'border-sel animate-pulse' :
              'border-line';

            const statusText =
              agent.status === 'done' ? 'text-pos' :
              agent.status === 'running' ? 'text-sel' :
              'text-ink-muted';

            return (
              <div
                key={agent.agentName}
                className={`border-l-2 ${statusBorder} bg-surface-raised p-2 text-xs transition-all`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-ink">{agent.agentName}</span>
                  <span className={`text-[10.5px] font-mono uppercase ${statusText}`}>
                    {agent.status === 'done' ? 'DONE' : agent.status === 'running' ? 'RUNNING' : 'PENDING'}
                  </span>
                </div>

                {agent.toolsUsed.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {agent.toolsUsed.map(tool => (
                      <span key={tool} className="px-1.5 py-0.5 bg-surface-hover text-[10px] text-ink-secondary font-mono">
                        {tool}
                      </span>
                    ))}
                  </div>
                )}

                {agent.content && (
                  <div className="mt-1 text-ink-muted line-clamp-2 italic">
                    {agent.content.slice(0, 120)}...
                  </div>
                )}
              </div>
            );
          })}
          {agents.length === 0 && (
            <div className="text-ink-muted text-xs text-center py-4">
              Waiting for agents...
            </div>
          )}
        </div>
      )}
    </div>
  );
}