'use client';

import { LLMChat } from '@/components/llm-chat';

export interface AiChatPanelProps {
  /** Pass-through context bundle for the LLM. Shape matches what
   *  LLMChat's marketData prop accepts (`any` upstream). */
  marketData: any;
}

/**
 * Right column of the dashboard: height wrapper around `LLMChat`.
 * Chrome (`.panel` + `AI ANALYST` title) lives on `LLMChat` (Task 10)
 * so the home column is a single panel, not nested ones.
 */
export function AiChatPanel({ marketData }: AiChatPanelProps) {
  return (
    <div className="flex flex-col h-[min(calc(100vh-9rem),42rem)] min-h-[28rem]">
      <div className="flex-1 min-h-0">
        <LLMChat marketData={marketData} />
      </div>
    </div>
  );
}