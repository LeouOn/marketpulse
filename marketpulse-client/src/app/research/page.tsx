'use client';

/**
 * BTC Research Lab chat page (B10).
 *
 * Layout:
 *  - Left: chat conversation (with the LLM agent, streaming NDJSON)
 *  - Center: current assistant message + tool cards as they appear
 *  - Right: example queries + saved reports links
 */

import { useState, useRef, useEffect, FormEvent } from 'react';
import { Send, Loader2, FlaskConical, FileText, BarChart3, Database, Bot, User, AlertTriangle } from 'lucide-react';
import Link from 'next/link';
import { marketPulseAPI } from '@/lib/api';

interface ChatMessage {
  role: 'user' | 'assistant' | 'tool';
  content: string;
  pending?: boolean;
  toolCalls?: Array<{ name: string; arguments: Record<string, any>; result?: any; error?: string }>;
}

const EXAMPLE_QUERIES = [
  "What strategies are available?",
  "Summarize BTC's performance since 2018.",
  "Compare BuyAndHold vs DCA $100/week on BTC since 2018.",
  "Run a Monte Carlo: GBM with mu=0.5, sigma=0.8, 5000 paths, 1 year.",
  "Explain the Sharpe ratio in plain English.",
];

export default function ResearchPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  async function send(text: string) {
    if (!text.trim() || busy) return;
    setError(null);
    setBusy(true);
    const userMsg: ChatMessage = { role: 'user', content: text };
    const assistantMsg: ChatMessage = { role: 'assistant', content: '', pending: true };
    setMessages((m) => [...m, userMsg, assistantMsg]);
    setInput('');

    try {
      const res = await marketPulseAPI.streamResearchChat([{ role: 'user', content: text }]);
      if (!res.ok || !res.body) {
        throw new Error(`Chat API error: ${res.status} ${res.statusText}`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let assembled = '';
      const toolCalls: ChatMessage['toolCalls'] = [];

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let nlIdx;
        while ((nlIdx = buffer.indexOf('\n')) >= 0) {
          const line = buffer.slice(0, nlIdx).trim();
          buffer = buffer.slice(nlIdx + 1);
          if (!line) continue;
          let event: any;
          try { event = JSON.parse(line); } catch { continue; }
          if (event.type === 'token' && typeof event.content === 'string') {
            assembled += event.content;
            setMessages((m) => {
              const next = m.slice();
              next[next.length - 1] = { role: 'assistant', content: assembled, pending: true, toolCalls: toolCalls.slice() };
              return next;
            });
          } else if (event.type === 'tool_call') {
            toolCalls.push({ name: event.name, arguments: event.arguments });
            setMessages((m) => {
              const next = m.slice();
              next[next.length - 1] = { role: 'assistant', content: assembled, pending: true, toolCalls: toolCalls.slice() };
              return next;
            });
          } else if (event.type === 'tool_result') {
            if (toolCalls.length > 0) {
              toolCalls[toolCalls.length - 1] = {
                ...toolCalls[toolCalls.length - 1],
                result: event.data,
                error: event.error,
              };
              setMessages((m) => {
                const next = m.slice();
                next[next.length - 1] = { role: 'assistant', content: assembled, pending: true, toolCalls: toolCalls.slice() };
                return next;
              });
            }
          } else if (event.type === 'final') {
            assembled = typeof event.content === 'string' ? event.content : assembled;
            setMessages((m) => {
              const next = m.slice();
              next[next.length - 1] = { role: 'assistant', content: assembled, toolCalls: toolCalls.slice() };
              return next;
            });
          } else if (event.type === 'error') {
            setError(String(event.error ?? 'Unknown error'));
          }
        }
      }
      // Finalize the pending flag
      setMessages((m) => {
        const next = m.slice();
        if (next.length > 0 && next[next.length - 1].pending) {
          next[next.length - 1] = { ...next[next.length - 1], pending: false };
        }
        return next;
      });
    } catch (e: any) {
      setError(e?.message ?? String(e));
      setMessages((m) => m.slice(0, -1)); // drop the empty assistant message
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    send(input);
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="mb-6 flex items-center gap-3">
        <FlaskConical className="w-7 h-7 text-emerald-400" />
        <div>
          <h1 className="text-2xl font-bold text-white">BTC Research Lab</h1>
          <p className="text-sm text-gray-400">
            Ask an LLM agent to run backtests, compare strategies, and explore Monte Carlo
            outcomes for Bitcoin. Powered by MiniMax-M3.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Chat column */}
        <div className="lg:col-span-3 flex flex-col h-[70vh] bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
          <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.length === 0 && (
              <div className="text-center text-gray-500 py-12">
                <Bot className="w-12 h-12 mx-auto mb-3 text-gray-600" />
                <p>Ask anything about BTC long-term strategy research.</p>
                <p className="text-xs mt-2">The agent has tools to run backtests, Monte Carlo, and explain metrics.</p>
              </div>
            )}
            {messages.map((m, i) => (
              <MessageBubble key={i} msg={m} />
            ))}
            {error && (
              <div className="flex items-start gap-2 text-red-400 bg-red-900/20 border border-red-800 rounded p-3">
                <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                <span className="text-sm">{error}</span>
              </div>
            )}
          </div>
          <form onSubmit={onSubmit} className="border-t border-gray-800 p-3 flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={busy}
              placeholder="Ask the research agent..."
              className="flex-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500"
            />
            <button
              type="submit"
              disabled={busy || !input.trim()}
              className="bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-700 disabled:text-gray-500 text-white px-4 py-2 rounded flex items-center gap-2 text-sm"
            >
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              <span>Send</span>
            </button>
          </form>
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <h2 className="text-sm font-semibold text-gray-300 mb-2 flex items-center gap-2">
              <BarChart3 className="w-4 h-4" /> Try a question
            </h2>
            <ul className="space-y-1">
              {EXAMPLE_QUERIES.map((q) => (
                <li key={q}>
                  <button
                    onClick={() => send(q)}
                    disabled={busy}
                    className="w-full text-left text-xs text-gray-400 hover:text-emerald-400 hover:bg-gray-800 rounded px-2 py-1.5 transition-colors disabled:opacity-50"
                  >
                    {q}
                  </button>
                </li>
              ))}
            </ul>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <h2 className="text-sm font-semibold text-gray-300 mb-2 flex items-center gap-2">
              <FileText className="w-4 h-4" /> Reports
            </h2>
            <Link
              href="/research/reports"
              className="text-xs text-emerald-400 hover:text-emerald-300"
            >
              View all saved reports &rarr;
            </Link>
            <p className="text-xs text-gray-500 mt-2">
              Every backtest or Monte Carlo run the agent makes is persisted with
              its metrics, params, and chart artifacts.
            </p>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <h2 className="text-sm font-semibold text-gray-300 mb-2 flex items-center gap-2">
              <Database className="w-4 h-4" /> Data
            </h2>
            <p className="text-xs text-gray-500">
              Daily BTC-USD from 2010+ (Yahoo Finance).
              Hourly BTC-USD from 2018+ (CryptoCompare).
              Cached locally as CSV.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === 'user';
  const Icon = isUser ? User : Bot;
  return (
    <div className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && (
        <div className="w-8 h-8 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center shrink-0">
          <Icon className="w-4 h-4" />
        </div>
      )}
      <div className={`max-w-2xl ${isUser ? 'bg-blue-600/20 border-blue-500/30' : 'bg-gray-800 border-gray-700'} border rounded-lg p-3 space-y-2`}>
        {msg.toolCalls && msg.toolCalls.length > 0 && (
          <div className="space-y-2">
            {msg.toolCalls.map((tc, i) => (
              <ToolCallCard key={i} call={tc} />
            ))}
          </div>
        )}
        {msg.content && (
          <div className="text-sm text-gray-200 whitespace-pre-wrap">
            {msg.content}
            {msg.pending && <span className="inline-block w-1.5 h-4 ml-0.5 bg-emerald-400 animate-pulse" />}
          </div>
        )}
        {!msg.content && msg.pending && (
          <div className="flex items-center gap-2 text-gray-400 text-xs">
            <Loader2 className="w-3 h-3 animate-spin" />
            <span>thinking...</span>
          </div>
        )}
      </div>
      {isUser && (
        <div className="w-8 h-8 rounded-full bg-blue-500/20 text-blue-400 flex items-center justify-center shrink-0">
          <Icon className="w-4 h-4" />
        </div>
      )}
    </div>
  );
}

function ToolCallCard({ call }: { call: NonNullable<ChatMessage['toolCalls']>[number] }) {
  return (
    <div className="bg-gray-900/60 border border-gray-700 rounded p-2 text-xs">
      <div className="flex items-center gap-2 text-emerald-400 font-mono mb-1">
        <span className="bg-emerald-500/20 px-1.5 py-0.5 rounded">{call.name}</span>
        {call.error && <span className="text-red-400">error: {call.error}</span>}
      </div>
      {call.arguments && Object.keys(call.arguments).length > 0 && (
        <pre className="text-gray-400 text-[10px] overflow-x-auto mb-1">
          {JSON.stringify(call.arguments, null, 2)}
        </pre>
      )}
      {call.result !== undefined && (
        <details className="text-gray-400">
          <summary className="cursor-pointer text-emerald-400 text-[10px]">result</summary>
          <pre className="overflow-x-auto mt-1 text-[10px]">{JSON.stringify(call.result, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}
