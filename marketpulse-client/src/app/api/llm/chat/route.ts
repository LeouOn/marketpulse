import { NextRequest, NextResponse } from 'next/server';

// This API route replaces the Next.js rewrite proxy for /api/llm/chat.
// The rewrite proxy (next.config.js) drops connections on long-running requests
// (ECONNRESET / socket hang up). This route uses fetch with an explicit 3-minute
// timeout so the backend has time to load models and generate responses.

const BACKEND_URL = 'http://localhost:8000/api/llm/chat';
const TIMEOUT_MS = 180_000; // 3 minutes — matches backend's asyncio.wait_for timeout

export const maxDuration = 300; // Allow up to 5 minutes for this route (Vercel compat)
export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

    console.log(`[LLM Proxy] -> POST ${BACKEND_URL} (timeout: ${TIMEOUT_MS / 1000}s)`);

    const startTime = Date.now();

    const response = await fetch(BACKEND_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    console.log(`[LLM Proxy] <- ${response.status} from backend (${elapsed}s)`);

    const data = await response.text();

    if (!response.ok) {
      console.error(`[LLM Proxy] Backend error ${response.status}: ${data.slice(0, 200)}`);
      return NextResponse.json(
        { success: false, error: `Backend returned ${response.status}: ${data.slice(0, 200)}` },
        { status: response.status }
      );
    }

    return new NextResponse(data, {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error: any) {
    const isTimeout = error.name === 'AbortError';
    const msg = isTimeout
      ? 'AI request timed out after 3 minutes. Try a shorter question.'
      : `Proxy error: ${error.message}`;

    console.error(`[LLM Proxy] ${msg}`);
    return NextResponse.json(
      { success: false, error: msg },
      { status: isTimeout ? 504 : 502 }
    );
  }
}
