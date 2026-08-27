import type { NextRequest } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const BACKEND_URL = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000';

export async function POST(request: NextRequest) {
  try {
    const payload = await request.json();

    const upstream = await fetch(`${BACKEND_URL}/loop/refresh_email_status`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
      cache: 'no-store',
    });

    const contentType = upstream.headers.get('content-type') ?? '';
    const data = contentType.includes('application/json')
      ? await upstream.json().catch(() => ({ error: 'Invalid JSON from backend /loop/refresh_email_status' }))
      : {
          error: 'Non-JSON response from backend /loop/refresh_email_status',
          detail: (await upstream.text()).slice(0, 400),
        };

    if (!upstream.ok) {
      return Response.json(data, { status: upstream.status });
    }

    return Response.json(data, { status: 200 });
  } catch (error) {
    const reason = error instanceof Error ? error.message : 'Unknown proxy error';
    return Response.json(
      {
        error: 'Unable to reach backend /loop/refresh_email_status',
        detail: reason,
      },
      { status: 502 },
    );
  }
}
