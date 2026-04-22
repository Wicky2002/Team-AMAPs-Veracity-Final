'use client';

import { useRef, useState } from 'react';

import { ABVariantGrid } from '@/components/ABVariantGrid';
import { CampaignTimeline } from '@/components/CampaignTimeline';
import { ChannelIntentPicker } from '@/components/ChannelIntentPicker';
import { FeedbackPanel } from '@/components/FeedbackPanel';
import { SignalIntelligenceBoard } from '@/components/SignalIntelligenceBoard';
import type { FeedbackMetric, OutreachVariant, SSEEvent, SignalReference, TimelineEntry } from '@/lib/loop-types';
import { UI_COMPONENT, normalizeUIRenderComponent } from '@/lib/ui-components';

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

const toSignals = (props: Record<string, unknown>): SignalReference[] => {
  const rawSignals = props.signals;
  if (!Array.isArray(rawSignals)) {
    return [];
  }

  return rawSignals.flatMap((signal) => {
    if (!isRecord(signal)) {
      return [];
    }

    return [
      {
        source: String(signal.source ?? 'unknown'),
        source_url: typeof signal.source_url === 'string' ? signal.source_url : undefined,
        quote: String(signal.quote ?? signal.content ?? ''),
        content: typeof signal.content === 'string' ? signal.content : undefined,
        confidence: Number(signal.confidence ?? 0.5),
      },
    ];
  });
};

const toVariants = (props: Record<string, unknown>): OutreachVariant[] => {
  const rawVariants = props.variants;
  if (!Array.isArray(rawVariants)) {
    return [];
  }

  return rawVariants.flatMap((variant) => {
    if (!isRecord(variant)) {
      return [];
    }

    const rawProvenance = Array.isArray(variant.provenance_chain) ? variant.provenance_chain : [];
    const provenanceChain = rawProvenance.flatMap((sig) => {
      if (!isRecord(sig)) {
        return [];
      }

      const sourceType = sig.source_type;
      const normalizedSourceType: SignalReference['source_type'] =
        sourceType === 'competitor' || sourceType === 'audience' || sourceType === 'pestel' ? sourceType : undefined;

      return [
        {
          source: String(sig.source ?? 'unknown'),
          source_url: typeof sig.source_url === 'string' ? sig.source_url : undefined,
          quote: String(sig.quote ?? ''),
          confidence: Number(sig.confidence ?? 0),
          content: typeof sig.content === 'string' ? sig.content : undefined,
          source_type: normalizedSourceType,
          raw_quote: typeof sig.raw_quote === 'string' ? sig.raw_quote : undefined,
        },
      ];
    });

    return [
      {
        subject_line: String(variant.subject_line ?? 'Untitled'),
        hook: String(variant.hook ?? ''),
        cta: String(variant.cta ?? ''),
        hypothesis: String(variant.hypothesis ?? 'Unknown hypothesis'),
        provenance_chain: provenanceChain,
      },
    ];
  });
};

const toMetrics = (props: Record<string, unknown>): FeedbackMetric[] => {
  const rawMetrics = props.metrics;
  if (!Array.isArray(rawMetrics)) {
    return [];
  }

  return rawMetrics.flatMap((metric) => {
    if (!isRecord(metric)) {
      return [];
    }

    return [
      {
        variant: Number(metric.variant ?? 0),
        open_rate: Number(metric.open_rate ?? 0),
        reply_rate: Number(metric.reply_rate ?? 0),
        click_rate: Number(metric.click_rate ?? 0),
      },
    ];
  });
};

const toTimeline = (props: Record<string, unknown>): TimelineEntry[] => {
  const rawHistory = props.campaign_history;
  if (!Array.isArray(rawHistory)) {
    return [];
  }

  return rawHistory.flatMap((entry) => {
    if (!isRecord(entry)) {
      return [];
    }

    const angle = entry.angle;
    const normalizedAngle =
      angle === 'roi' || angle === 'social_proof' || angle === 'competitor_gap' ? angle : 'competitor_gap';

    return [
      {
        cycle_n: Number(entry.cycle_n ?? 0),
        top_signal: String(entry.top_signal ?? ''),
        winning_variant: String(entry.winning_variant ?? ''),
        open_rate: Number(entry.open_rate ?? 0),
        reply_rate: Number(entry.reply_rate ?? 0),
        angle: normalizedAngle,
        timestamp: String(entry.timestamp ?? new Date().toISOString()),
      },
    ];
  });
};

const isSSEEvent = (value: unknown): value is SSEEvent => {
  if (!isRecord(value) || typeof value.type !== 'string') {
    return false;
  }

  switch (value.type) {
    case 'node_started':
      return typeof value.node === 'string' && typeof value.cycle_n === 'number';
    case 'signal_found':
      return (
        (value.source === 'competitor' || value.source === 'audience' || value.source === 'pestel') &&
        typeof value.content === 'string' &&
        typeof value.quote === 'string' &&
        typeof value.confidence === 'number'
      );
    case 'ui_render':
      if (!isRecord(value.props) || typeof value.cycle_n !== 'number') {
        return false;
      }

      const component = normalizeUIRenderComponent(value.component);
      if (!component) {
        return false;
      }

      value.component = component;
      return true;
    case 'loop_complete':
      return (
        typeof value.cycle_n === 'number' &&
        (value.next_action === 'awaiting_feedback' ||
          value.next_action === 'refined_research' ||
          value.next_action === 'end')
      );
    case 'warning':
      return typeof value.message === 'string' && typeof value.fallback_used === 'boolean';
    default:
      return false;
  }
};

export default function Home() {
  const [message, setMessage] = useState('Is Lilian well-positioned in the AI SDR market?');
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [rawEvents, setRawEvents] = useState<string[]>([]);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [status, setStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle');
  const [threadId, setThreadId] = useState('');

  const eventSourceRef = useRef<EventSource | null>(null);

  const resolveThreadId = () => {
    if (threadId) {
      return threadId;
    }

    const generated =
  typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : Math.random().toString(36).substring(2) + Date.now().toString(36);
    setThreadId(generated);
    return generated;
  };

  const appendEvent = (raw: string) => {
    setRawEvents((prev) => [raw, ...prev].slice(0, 160));
  };

  const applyTypedEvent = (parsed: SSEEvent) => {
    setEvents((prev) => [...prev, parsed].slice(-180));

    if (parsed.type === 'ui_render' && parsed.component === UI_COMPONENT.FEEDBACK_PANEL) {
      const nextTimeline = toTimeline(parsed.props);
      if (nextTimeline.length > 0) {
        setTimeline(nextTimeline);
      }
    }

    if (parsed.type === 'loop_complete' && parsed.next_action !== 'refined_research') {
      setStatus('done');
      eventSourceRef.current?.close();
    }
  };

  const startLoop = () => {
    eventSourceRef.current?.close();
    setEvents([]);
    setRawEvents([]);
    setTimeline([]);

    const activeThreadId = resolveThreadId();

    const params = new URLSearchParams({
      thread_id: activeThreadId,
      message,
    });

    setStatus('running');
    const source = new EventSource(`/api/loop/proxy?${params.toString()}`);
    eventSourceRef.current = source;

    source.onmessage = (event) => {
      appendEvent(event.data);

      try {
        const parsed = JSON.parse(event.data) as unknown;
        if (!isSSEEvent(parsed)) {
          return;
        }

        applyTypedEvent(parsed);
      } catch {
        // Ignore malformed event chunks in UI layer.
      }
    };

    source.onerror = () => {
      setStatus('error');
      source.close();
    };
  };

  const stopLoop = () => {
    eventSourceRef.current?.close();
    setStatus('done');
  };

  const sendAction = async (action_type: 'feedback' | 'channel_select' | 'deploy_variant', payload: Record<string, unknown>) => {
    const activeThreadId = resolveThreadId();

    const response = await fetch('/api/loop/action', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        thread_id: activeThreadId,
        action_type,
        payload,
      }),
    });

    const actionResult = (await response.json().catch(() => null)) as
      | {
          latest_events?: unknown[];
        }
      | null;

    if (!actionResult || !Array.isArray(actionResult.latest_events)) {
      return;
    }

    for (const event of actionResult.latest_events) {
      if (!isSSEEvent(event)) {
        continue;
      }

      appendEvent(JSON.stringify(event));
      applyTypedEvent(event);
    }
  };

  const renderEvent = (event: SSEEvent, index: number) => {
    if (event.type === 'node_started') {
      return (
        <div key={`node-${index}`} className="flex items-center gap-2 px-1 py-1 text-xs text-zinc-500">
          <span className="h-2 w-2 animate-pulse rounded-full bg-green-400" />
          Running {event.node} — Cycle {event.cycle_n}
        </div>
      );
    }

    if (event.type === 'signal_found') {
      return (
        <div key={`signal-${index}`} className="rounded-md border border-blue-200 bg-blue-50 p-2 text-xs text-blue-900">
          <span className="font-medium">{event.source}</span>: {event.quote}
        </div>
      );
    }

    if (event.type === 'ui_render') {
      switch (event.component) {
        case UI_COMPONENT.SIGNAL_BOARD:
          return <SignalIntelligenceBoard key={`ui-signal-${index}`} signals={toSignals(event.props)} />;
        case UI_COMPONENT.AB_GRID:
          return (
            <ABVariantGrid
              key={`ui-ab-${index}`}
              variants={toVariants(event.props)}
              onDeploy={(variant) => {
                void sendAction('deploy_variant', { variant });
              }}
            />
          );
        case UI_COMPONENT.CHANNEL_PICKER:
          return (
            <ChannelIntentPicker
              key={`ui-channel-${index}`}
              selected={typeof event.props.selected === 'string' ? event.props.selected : undefined}
              onSelect={(channel) => {
                void sendAction('channel_select', { channel });
              }}
            />
          );
        case UI_COMPONENT.FEEDBACK_PANEL:
          return (
            <FeedbackPanel
              key={`ui-feedback-${index}`}
              metrics={toMetrics(event.props)}
              onFeedback={() => {
                const metrics = toMetrics(event.props);
                const winner = metrics.length > 0 ? metrics.reduce((a, b) => (a.reply_rate > b.reply_rate ? a : b)) : null;
                void sendAction('feedback', {
                  note: 'The ROI angle got 3x the reply rate.',
                  angle: 'roi',
                  winning_variant: winner ? `Variant ${String.fromCharCode(65 + winner.variant)}` : 'Variant B',
                  open_rate: winner?.open_rate,
                  reply_rate: winner?.reply_rate,
                  click_rate: winner?.click_rate,
                });
              }}
            />
          );
        case UI_COMPONENT.STALE_WARNING:
          return (
            <div
              key={`ui-stale-${index}`}
              className="rounded-lg border border-amber-400/30 bg-amber-50 p-3 text-sm text-amber-900"
            >
              {typeof event.props.message === 'string' ? event.props.message : 'Signals may be stale.'}
            </div>
          );
        default:
          return null;
      }
    }

    if (event.type === 'warning') {
      return (
        <div key={`warning-${index}`} className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-3 text-sm">
          ⚠️ {event.message}
          {event.fallback_used && <span className="ml-2 text-xs underline">Fallback used</span>}
        </div>
      );
    }

    if (event.type === 'loop_complete') {
      return (
        <div key={`complete-${index}`} className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
          Loop complete for cycle {event.cycle_n}. Next action: {event.next_action}
        </div>
      );
    }

    return null;
  };

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-4 p-6">
      <header className="rounded-xl border border-zinc-200 p-4 shadow-sm">
        <h1 className="text-2xl font-bold">Signal → Action Skeleton</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Phase 1/2 scaffold: LangGraph SSE stream → FastAPI → Next.js interactive shell.
        </p>
        <div className="mt-3 flex flex-col gap-2 md:flex-row">
          <input
            className="flex-1 rounded-md border border-zinc-300 px-3 py-2 text-sm"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Ask a research/generate/feedback question..."
          />
          <button
            type="button"
            onClick={startLoop}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
          >
            Start Loop
          </button>
          <button
            type="button"
            onClick={stopLoop}
            className="rounded-md border border-zinc-300 px-4 py-2 text-sm hover:bg-zinc-50"
          >
            Stop
          </button>
        </div>
        <p className="mt-2 text-xs text-zinc-500">
          Thread: <code>{threadId || 'initializing...'}</code> • Status: <strong>{status}</strong>
        </p>
      </header>

      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <div className="space-y-4">{events.map((event, i) => renderEvent(event, i))}</div>

        <CampaignTimeline entries={timeline} />
      </div>

      <section className="rounded-xl border border-zinc-200 p-4 shadow-sm">
        <h2 className="text-lg font-semibold">Raw SSE Event Log</h2>
        <div className="mt-3 max-h-80 overflow-y-auto rounded-md bg-zinc-950 p-3 font-mono text-xs text-zinc-100">
          {rawEvents.map((event, index) => (
            <pre key={`${event}-${index}`} className="whitespace-pre-wrap wrap-break-word border-b border-zinc-800 py-2">
              {event}
            </pre>
          ))}
          {rawEvents.length === 0 && <p className="text-zinc-400">No events yet. Start the loop.</p>}
        </div>
      </section>
    </main>
  );
}
