import type { NextRequest } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const BACKEND_URL = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000';

export async function POST(request: NextRequest) {
  const payload = await request.json();

  const upstream = await fetch(`${BACKEND_URL}/loop/action`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
    cache: 'no-store',
  });

  const data = await upstream.json().catch(() => ({ error: 'Invalid upstream response' }));

  if (!upstream.ok) {
    return Response.json(data, { status: upstream.status });
  }

  return Response.json(data, { status: 200 });
}
