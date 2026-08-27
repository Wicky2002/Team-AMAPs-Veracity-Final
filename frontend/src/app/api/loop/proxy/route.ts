import type { NextRequest } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const BACKEND_URL = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000';

export async function GET(request: NextRequest) {
  const message = request.nextUrl.searchParams.get('message') ?? 'Is Lilian well-positioned in AI SDR?';
  const threadId = request.nextUrl.searchParams.get('thread_id') ?? crypto.randomUUID();
  const productName = request.nextUrl.searchParams.get('product_name') || undefined;

  const upstream = await fetch(`${BACKEND_URL}/loop/start`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      message,
      thread_id: threadId,
      product_name: productName,
    }),
    cache: 'no-store',
  });

  if (!upstream.ok || !upstream.body) {
    return Response.json(
      {
        error: 'Unable to open upstream loop stream.',
        status: upstream.status,
      },
      { status: 502 },
    );
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
    },
  });
}
