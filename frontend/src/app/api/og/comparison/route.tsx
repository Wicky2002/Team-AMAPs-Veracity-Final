import { ImageResponse } from 'next/og';
import type { NextRequest } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

interface CompetitorEntry {
  name: string;
  tagline: string;
  strengths: string[];
  weaknesses: string[];
  highlight?: boolean;
}

interface ComparisonPayload {
  title?: string;
  subtitle?: string;
  competitors?: CompetitorEntry[];
  market_insight?: string;
}

export async function POST(request: NextRequest) {
  let payload: ComparisonPayload;
  try {
    payload = (await request.json()) as ComparisonPayload;
  } catch {
    return new Response('Invalid JSON body', { status: 400 });
  }

  const title = payload.title?.trim() || 'Competitive Landscape';
  const subtitle = payload.subtitle?.trim() || 'Live signal comparison';
  const marketInsight = payload.market_insight?.trim() || '';
  const competitors = (payload.competitors ?? []).slice(0, 4);

  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          background: '#0f172a',
          padding: '56px',
          fontFamily: 'sans-serif',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', marginBottom: '32px' }}>
          <div style={{ fontSize: 42, fontWeight: 700, color: '#f8fafc' }}>{title}</div>
          <div style={{ fontSize: 20, color: '#94a3b8', marginTop: '8px' }}>{subtitle}</div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'row', gap: '20px', flexWrap: 'wrap' }}>
          {competitors.map((c, i) => (
            <div
              key={i}
              style={{
                display: 'flex',
                flexDirection: 'column',
                flex: 1,
                minWidth: '250px',
                background: c.highlight ? '#3730a3' : '#1e293b',
                borderRadius: '18px',
                padding: '26px',
                border: c.highlight ? '2px solid #818cf8' : '1px solid #334155',
              }}
            >
              <div style={{ fontSize: 23, fontWeight: 700, color: '#f8fafc' }}>{c.name}</div>
              <div style={{ fontSize: 14, color: '#cbd5e1', marginTop: '6px', marginBottom: '16px' }}>{c.tagline}</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {(c.strengths ?? []).slice(0, 3).map((s, j) => (
                  <div key={j} style={{ display: 'flex', fontSize: 13, color: '#86efac' }}>
                    + {s}
                  </div>
                ))}
                {(c.weaknesses ?? []).slice(0, 2).map((w, j) => (
                  <div key={j} style={{ display: 'flex', fontSize: 13, color: '#fca5a5' }}>
                    − {w}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {marketInsight && (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              marginTop: '32px',
              background: '#1e3a8a',
              borderRadius: '14px',
              padding: '20px 26px',
            }}
          >
            <div style={{ display: 'flex', fontSize: 13, textTransform: 'uppercase', color: '#93c5fd', fontWeight: 700 }}>
              Market Insight
            </div>
            <div style={{ display: 'flex', fontSize: 17, color: '#dbeafe', marginTop: '6px' }}>{marketInsight}</div>
          </div>
        )}
      </div>
    ),
    { width: 1200, height: 675 },
  );
}
