'use client';

import { LLMChat } from '@/components/llm-chat';

export interface AiChatPanelProps {
  /** Pass-through context bundle for the LLM. Shape matches what
   *  LLMChat's marketData prop accepts (`any` upstream). */
  marketData: any;
}

/**
 * Right column of the dashboard: `AI ANALYST` panel wrapping the
 * existing `LLMChat` component. Visual-only — LLMChat itself is not
 * touched in this task (Task 10 does that).
 */
export function AiChatPanel({ marketData }: AiChatPanelProps) {
  return (
    <div className="panel flex flex-col" style={{ height: 'calc(100vh - 200px)', minHeight: '700px' }}>
      <div className="border-b border-line-subtle px-3 h-8 flex items-center">
        <span className="panel-title">AI Analyst</span>
      </div>
      <div className="flex-1 min-h-0 p-2.5">
        <LLMChat marketData={marketData} />
      </div>
    </div>
  );
}