// app/api/chat/route.ts — Next.js API Route that proxies to FastAPI backend
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    const res = await fetch(`${BACKEND_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      // 30 s timeout for AI agent processing
      signal: AbortSignal.timeout(30_000),
    });

    if (!res.ok) {
      const errText = await res.text().catch(() => "Backend unavailable");
      return NextResponse.json(
        { type: "text", content: `Backend error: ${errText}` },
        { status: res.status }
      );
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    // Return a graceful text fallback so the UI never hard-crashes
    return NextResponse.json(
      {
        type: "text",
        content: `⚠️ Could not reach the backend: ${message}. Make sure FastAPI is running on ${BACKEND_URL}.`,
      },
      { status: 502 }
    );
  }
}
