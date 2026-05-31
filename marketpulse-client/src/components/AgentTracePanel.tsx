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
    <div className="bg-gray-900 border-l border-gray-800 h-full flex flex-col">
      <div
        className="flex items-center justify-between px-3 py-2 bg-gray-800 cursor-pointer"
        onClick={onToggle}
      >
        <span className="text-xs font-semibold text-gray-300 uppercase tracking-wide">
          Agent Trace ({agents.filter(a => a.status === 'done').length}/{agents.length})
        </span>
        <span className="text-gray-500 text-xs">{expanded ? '\u25B2' : '\u25BC'}</span>
      </div>

      {expanded && (
        <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
          {agents.map((agent, i) => {
            const statusColor =
              agent.status === 'done' ? 'border-green-600' :
              agent.status === 'running' ? 'border-blue-500 animate-pulse' :
              'border-gray-700';

            return (
              <div
                key={agent.agentName}
                className={`border-l-2 ${statusColor} bg-gray-800/50 rounded-r p-2 text-xs transition-all`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-gray-200">{agent.agentName}</span>
                  <span className={
                    agent.status === 'done' ? 'text-green-400' :
                    agent.status === 'running' ? 'text-blue-400' : 'text-gray-600'
                  }>
                    {agent.status === 'done' ? '\u2713' : agent.status === 'running' ? '\u25CB' : '\u2022'}
                  </span>
                </div>

                {agent.toolsUsed.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {agent.toolsUsed.map(tool => (
                      <span key={tool} className="px-1.5 py-0.5 bg-gray-700 rounded text-[10px] text-gray-400">
                        {tool}
                      </span>
                    ))}
                  </div>
                )}

                {agent.content && (
                  <div className="mt-1 text-gray-500 line-clamp-2 italic">
                    {agent.content.slice(0, 120)}...
                  </div>
                )}
              </div>
            );
          })}
          {agents.length === 0 && (
            <div className="text-gray-600 text-xs text-center py-4">
              Waiting for agents...
            </div>
          )}
        </div>
      )}
    </div>
  );
}
