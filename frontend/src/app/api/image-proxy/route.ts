import type { NextRequest } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

// Chromium's Opaque Response Blocking rejects some cross-origin <img> loads
// of slow/chunked responses even with correct headers (observed against
// image.pollinations.ai). Serving same-origin sidesteps ORB entirely.
const ALLOWED_HOSTS = new Set(['image.pollinations.ai']);

const GRADIENT_PAIRS: [string, string][] = [
  ['#4f46e5', '#0891b2'],
  ['#7c3aed', '#db2777'],
  ['#0284c7', '#059669'],
  ['#ea580c', '#d97706'],
];

function placeholderSvg(seedSource: string): string {
  let hash = 0;
  for (let i = 0; i < seedSource.length; i += 1) {
    hash = (hash * 31 + seedSource.charCodeAt(i)) >>> 0;
  }
  const [from, to] = GRADIENT_PAIRS[hash % GRADIENT_PAIRS.length];

  return `<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="576" viewBox="0 0 1024 576">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="${from}" />
      <stop offset="100%" stop-color="${to}" />
    </linearGradient>
  </defs>
  <rect width="1024" height="576" fill="url(#g)" />
</svg>`;
}

export async function GET(request: NextRequest) {
  const target = request.nextUrl.searchParams.get('url');
  if (!target) {
    return new Response('Missing url parameter', { status: 400 });
  }

  let parsed: URL;
  try {
    parsed = new URL(target);
  } catch {
    return new Response('Invalid url parameter', { status: 400 });
  }

  if (!ALLOWED_HOSTS.has(parsed.hostname)) {
    return new Response('Host not allowed', { status: 403 });
  }

  // Pollinations is a free, unauthenticated image service -- it can take
  // 30s+ under concurrent load (two variant images requested at once) and
  // occasionally 502s transiently. One retry with a generous timeout absorbs
  // that without the image staying permanently broken in the UI.
  const attempt = async (): Promise<Response | null> => {
    try {
      const res = await fetch(parsed.toString(), {
        cache: 'no-store',
        signal: AbortSignal.timeout(25000),
      });
      return res.ok && res.body ? res : null;
    } catch {
      return null;
    }
  };

  const upstream = (await attempt()) ?? (await attempt());

  if (!upstream) {
    // Pollinations is a free, unauthenticated service with no SLA -- under
    // load it can stall for 30s+ or fail outright. A demo can't depend on a
    // third party staying up, so fall back to a deterministic local gradient
    // (same seed -> same placeholder) rather than ever showing a broken image.
    return new Response(placeholderSvg(parsed.toString()), {
      status: 200,
      headers: {
        'Content-Type': 'image/svg+xml',
        'Cache-Control': 'no-store',
      },
    });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      'Content-Type': upstream.headers.get('content-type') ?? 'image/jpeg',
      'Cache-Control': 'public, max-age=86400, immutable',
    },
  });
}
