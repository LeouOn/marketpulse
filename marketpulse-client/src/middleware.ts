import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export default async function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  // Only the streaming chat route lives in Next (src/app/api/llm/chat).
  // models / model-status / select-model must reach FastAPI.
  if (pathname === '/api/llm/chat' || pathname.startsWith('/api/llm/chat/')) {
    return NextResponse.next();
  }

  // Proxy all other /api/* requests to FastAPI backend
  if (pathname.startsWith('/api/')) {
    try {
      const url = `${BACKEND_URL}${pathname}${search}`;
      const method = request.method;
      const body = method !== 'GET' && method !== 'HEAD' ? await request.text() : undefined;
      const res = await fetch(url, {
        method,
        body,
        headers: {
          'Content-Type': 'application/json',
        },
      });

      const data = await res.json();
      return NextResponse.json(data, {
        status: res.status,
      });
    } catch {
      return NextResponse.json(
        { success: false, error: 'Backend unavailable' },
        { status: 502 }
      );
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: '/api/:path*',
};
