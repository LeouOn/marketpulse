'use client';

/**
 * Multi-asset Research Lab chat page (W5 T22).
 *
 * Dynamic route: ``/research/{asset}`` where ``asset`` is one of the keys in
 * ``AssetRegistry`` (BTC / GOLD / OIL / EQUITIES / HOUSING). The page is a
 * direct extension of the original BTC-only page — same layout, same streaming
 * chat, same tool-call cards — now parameterized by asset:
 *
 *  - URL picks the asset (e.g. ``/research/GOLD``).
 *  - An ``<AssetPicker>`` dropdown at the top swaps the asset by navigating to
 *    ``/research/{key}``. Changing asset remounts the chat (via React
 *    ``key``) so message history resets cleanly per asset context.
 *  - The chat stream is wired to T20's ``POST /api/research/chat/{asset}``
 *    route so the backend can scope the system prompt + tool defaults.
 *  - Sidebar copy (data source, example queries) is asset-aware.
 *
 * Invalid asset keys redirect to ``/research/BTC`` (the original default).
 */

import { useState, useRef, useEffect, FormEvent } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  Send,
  Loader2,
  FlaskConical,
  FileText,
  BarChart3,
  Database,
  Bot,
  User,
  AlertTriangle,
} from 'lucide-react';
import Link from 'next/link';
import { marketPulseAPI } from '@/lib/api';
import { AssetPicker, ASSET_KEYS } from '@/components/AssetPicker';

interface ChatMessage {
  role: 'user' | 'assistant' | 'tool';
  content: string;
  pending?: boolean;
  toolCalls?: Array<{
    name: string;
    arguments: Record<string, any>;
    result?: any;
    error?: string;
  }>;
}

/** Per-asset copy + example queries. Keys mirror ``AssetRegistry``. */
const ASSET_META: Record<
  string,
  { label: string; subtitle: string; dataCard: string; examples: string[] }
> = {
  BTC: {
    label: 'Bitcoin',
    subtitle:
      'Ask an LLM agent to run backtests, compare strategies, and explore Monte Carlo outcomes for Bitcoin. Powered by MiniMax-M3.',
    dataCard:
      'Daily BTC-USD from 2010+ (Yahoo Finance). Hourly BTC-USD from 2018+ (CryptoCompare). Cached locally as CSV.',
    examples: [
      'What strategies are available?',
      "Summarize BTC's performance since 2018.",
      'Compare BuyAndHold vs DCA $100/week on BTC since 2018.',
      'Run a Monte Carlo: GBM with mu=0.5, sigma=0.8, 5000 paths, 1 year.',
      'Explain the Sharpe ratio in plain English.',
    ],
  },
  GOLD: {
    label: 'Gold',
    subtitle:
      'Backtest strategies and explore Monte Carlo scenarios for Gold spot (XAUUSD).',
    dataCard:
      'Daily Gold spot (XAUUSD) from LBMA, via FRED. Cached locally as CSV.',
    examples: [
      'What strategies are available?',
      "Summarize Gold's performance since 2010.",
      'Compare BuyAndHold vs DCA $100/week on Gold since 2010.',
      'Run a Monte Carlo: GBM on Gold, 5000 paths, 1 year.',
      'How does Gold typically behave across macro regimes?',
    ],
  },
  OIL: {
    label: 'Oil (WTI)',
    subtitle:
      'Backtest strategies and explore Monte Carlo scenarios for WTI Crude Oil.',
    dataCard:
      'Daily WTI spot (CL=F front month) from the EIA. Cached locally as CSV.',
    examples: [
      'What strategies are available?',
      "Summarize WTI Oil's performance since 2010.",
      'Compare BuyAndHold vs DCA on Oil since 2010.',
      'Run a Monte Carlo: block_bootstrap on Oil, 2000 paths, 1 year.',
      'How does Oil behave across macro regimes?',
    ],
  },
  EQUITIES: {
    label: 'US Equities (S&P 500)',
    subtitle:
      'Backtest strategies and explore Monte Carlo scenarios for the S&P 500.',
    dataCard:
      'Daily S&P 500 (SPX / SPY) from FRED & Yahoo Finance. Cached locally as CSV.',
    examples: [
      'What strategies are available?',
      'Summarize S&P 500 performance since 2010.',
      'Compare BuyAndHold vs DCA $500/month on equities since 2010.',
      'Run a Monte Carlo: regime_switching on equities, 3000 paths, 1 year.',
      'Which regime favors momentum vs mean-reversion?',
    ],
  },
  HOUSING: {
    label: 'Housing (Case-Shiller)',
    subtitle:
      'Backtest strategies on the Case-Shiller National Home Price Index.',
    dataCard:
      'Monthly Case-Shiller US National Home Price Index (CSUSHPINSA) via FRED. Cached locally as CSV.',
    examples: [
      'What strategies are available?',
      'Summarize Case-Shiller home price trends since 2000.',
      'Compare BuyAndHold vs DCA on the Case-Shiller index.',
      'How does housing perform across interest-rate regimes?',
      'Run a Monte Carlo: block_bootstrap on housing, 1000 paths, 10 years.',
    ],
  },
};

export default function AssetResearchPage() {
  const params = useParams();
  const router = useRouter();

  // Dynamic segment is case-insensitive on the client; registry keys are
  // upper-case so normalize once.
  const rawAsset = (params?.asset as string | undefined) ?? 'BTC';
  const asset = rawAsset.toUpperCase();
  const isValid = ASSET_KEYS.has(asset);

  // Redirect unknown asset keys to the BTC default (back-compat). Done in an
  // effect (not during render) to avoid side-effects inside the render body.
  useEffect(() => {
    if (!isValid) {
      router.replace('/research/BTC');
    }
  }, [isValid, router]);

  if (!isValid) {
    // Brief render before the redirect kicks in.
    return (
      <div className="max-w-7xl mx-auto px-4 py-6 text-sm text-gray-500">
        Unknown asset &ldquo;{rawAsset}&rdquo;. Redirecting to BTC&hellip;
      </div>
    );
  }

  const meta = ASSET_META[asset] ?? ASSET_META.BTC;

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="mb-6 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <FlaskConical className="w-7 h-7 text-emerald-400" />
          <div>
            <h1 className="text-2xl font-bold text-white">{meta.label} Research Lab</h1>
            <p className="text-sm text-gray-400 max-w-2xl">{meta.subtitle}</p>
          </div>
        </div>
        <AssetPicker
          value={asset}
          onChange={(a) => router.push(`/research/${a}`)}
        />
      </div>

      {/*
        Keying the chat surface by `asset` forces a clean remount on asset
        change so message history, streaming state, and errors reset cleanly
        when the user picks a new asset from the dropdown.
      */}
      <ResearchChat key={asset} asset={asset} meta={meta} />
    </div>
  );
}

interface ResearchChatProps {
  asset: string;
  meta: { label: string; subtitle: string; dataCard: string; examples: string[] };
}

function ResearchChat({ asset, meta }: ResearchChatProps) {
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
      // T20: asset-scoped chat route threads the asset into the system prompt
      // and tool defaults server-side.
      const res = await marketPulseAPI.streamResearchChat(
        [{ role: 'user', content: text }],
        asset,
      );
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
          try {
            event = JSON.parse(line);
          } catch {
            continue;
          }
          if (event.type === 'token' && typeof event.content === 'string') {
            assembled += event.content;
            setMessages((m) => {
              const next = m.slice();
              next[next.length - 1] = {
                role: 'assistant',
                content: assembled,
                pending: true,
                toolCalls: toolCalls.slice(),
              };
              return next;
            });
          } else if (event.type === 'tool_call') {
            toolCalls.push({ name: event.name, arguments: event.arguments });
            setMessages((m) => {
              const next = m.slice();
              next[next.length - 1] = {
                role: 'assistant',
                content: assembled,
                pending: true,
                toolCalls: toolCalls.slice(),
              };
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
                next[next.length - 1] = {
                  role: 'assistant',
                  content: assembled,
                  pending: true,
                  toolCalls: toolCalls.slice(),
                };
                return next;
              });
            }
          } else if (event.type === 'final') {
            assembled = typeof event.content === 'string' ? event.content : assembled;
            setMessages((m) => {
              const next = m.slice();
              next[next.length - 1] = {
                role: 'assistant',
                content: assembled,
                toolCalls: toolCalls.slice(),
              };
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
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
      {/* Chat column */}
      <div className="lg:col-span-3 flex flex-col h-[70vh] bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && (
            <div className="text-center text-gray-500 py-12">
              <Bot className="w-12 h-12 mx-auto mb-3 text-gray-600" />
              <p>
                Ask anything about {meta.label} long-term strategy research.
              </p>
              <p className="text-xs mt-2">
                The agent has tools to run backtests, Monte Carlo, and explain metrics.
              </p>
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
            placeholder={`Ask the research agent about ${meta.label}...`}
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
            {meta.examples.map((q) => (
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
          <Link href="/research/reports" className="text-xs text-emerald-400 hover:text-emerald-300">
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
          <p className="text-xs text-gray-500">{meta.dataCard}</p>
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
      <div
        className={`max-w-2xl ${
          isUser
            ? 'bg-blue-600/20 border-blue-500/30'
            : 'bg-gray-800 border-gray-700'
        } border rounded-lg p-3 space-y-2`}
      >
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
            {msg.pending && (
              <span className="inline-block w-1.5 h-4 ml-0.5 bg-emerald-400 animate-pulse" />
            )}
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

function ToolCallCard({
  call,
}: {
  call: NonNullable<ChatMessage['toolCalls']>[number];
}) {
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
          <pre className="overflow-x-auto mt-1 text-[10px]">
            {JSON.stringify(call.result, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}
