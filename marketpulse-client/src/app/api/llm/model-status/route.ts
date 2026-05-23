import { NextRequest, NextResponse } from 'next/server';

const BACKEND_BASE = process.env.BACKEND_URL || 'http://localhost:8000';
const BACKEND_URL = `${BACKEND_BASE}/api/llm/model-status`;

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
