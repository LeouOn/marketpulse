import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = 'http://localhost:8000/api/llm/model-status';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const response = await fetch(BACKEND_URL, {
      signal: AbortSignal.timeout(10_000),
    });
    const data = await response.text();
    return new NextResponse(data, {
      status: response.status,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error: any) {
    return NextResponse.json(
      { success: false, error: error.message },
      { status: 502 }
    );
  }
}
