import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export default async function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  // Skip LLM routes — they have their own API route handlers in src/app/api/llm/
  if (pathname.startsWith('/api/llm/')) {
    return NextResponse.next();
  }

  // Proxy all other /api/* requests to FastAPI backend
  if (pathname.startsWith('/api/')) {
    try {
      const url = `${BACKEND_URL}${pathname}${search}`;
      const res = await fetch(url, {
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
