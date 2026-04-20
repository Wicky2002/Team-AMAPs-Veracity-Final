'use client';

import { useMemo, useRef, useState } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { ABVariantGrid } from '@/components/ABVariantGrid';
import { CampaignTimeline } from '@/components/CampaignTimeline';
import { ChannelIntentPicker } from '@/components/ChannelIntentPicker';
import { FeedbackPanel } from '@/components/FeedbackPanel';
import { SignalIntelligenceBoard } from '@/components/SignalIntelligenceBoard';
import type { FeedbackMetric, LoopEnvelope, OutreachVariant, SignalReference, TimelineEntry } from '@/lib/loop-types';

export default function Home() {
  const [message, setMessage] = useState('Is Lilian well-positioned in the AI SDR market?');
  const [events, setEvents] = useState<string[]>([]);
  const [signals, setSignals] = useState<SignalReference[]>([]);
  const [variants, setVariants] = useState<OutreachVariant[]>([]);
  const [metrics, setMetrics] = useState<FeedbackMetric[]>([]);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [selectedChannel, setSelectedChannel] = useState<string | undefined>();
  const [status, setStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle');

  const eventSourceRef = useRef<EventSource | null>(null);
  const threadId = useMemo(() => uuidv4(), []);

  const appendEvent = (raw: string) => {
    setEvents((prev) => [raw, ...prev].slice(0, 120));
  };

  const isRecord = (value: unknown): value is Record<string, unknown> =>
    typeof value === 'object' && value !== null;

  const applyEnvelope = (envelope: LoopEnvelope) => {
    if (envelope.mode !== 'custom' || !envelope.payload) {
      return;
    }

    if (!isRecord(envelope.payload)) {
      return;
    }

    const payload = envelope.payload;

    if (payload.type === 'signal_found') {
      setSignals((prev) => [
        ...prev,
        {
          source: String(payload.source ?? 'unknown'),
          quote: String(payload.quote ?? ''),
          confidence: Number(payload.confidence ?? 0.5),
        },
      ]);
      return;
    }

    if (payload.type === 'ui_render') {
      const component = String(payload.component ?? '');
      const props = isRecord(payload.props) ? payload.props : {};

      if (component === 'SignalIntelligenceBoard') {
        const signalList = Array.isArray(props.signals) ? props.signals : [];
        setSignals(
          signalList.map((signal) => ({
            source: String(isRecord(signal) ? signal.source ?? 'unknown' : 'unknown'),
            quote: String(isRecord(signal) ? signal.quote ?? '' : ''),
            confidence: Number(isRecord(signal) ? signal.confidence ?? 0.5 : 0.5),
          })),
        );
      }

      if (component === 'ABVariantGrid') {
        setVariants(Array.isArray(props.variants) ? (props.variants as OutreachVariant[]) : []);
      }

      if (component === 'ChannelIntentPicker') {
        setSelectedChannel(typeof props.selected === 'string' ? props.selected : undefined);
      }

      if (component === 'FeedbackPanel') {
        setMetrics(Array.isArray(props.metrics) ? (props.metrics as FeedbackMetric[]) : []);
      }

      if (component === 'CampaignTimeline') {
        setTimeline(Array.isArray(props.entries) ? (props.entries as TimelineEntry[]) : []);
      }
    }
  };

  const startLoop = () => {
    eventSourceRef.current?.close();
    setEvents([]);
    setSignals([]);
    setVariants([]);
    setMetrics([]);
    setTimeline([]);

    const params = new URLSearchParams({
      thread_id: threadId,
      message,
    });

    setStatus('running');
    const source = new EventSource(`/api/loop/proxy?${params.toString()}`);
    eventSourceRef.current = source;

    source.onmessage = (event) => {
      appendEvent(event.data);

      try {
        const envelope = JSON.parse(event.data) as LoopEnvelope;
        applyEnvelope(envelope);

        const type = envelope.payload?.type;
        if (type === 'loop_completed') {
          setStatus('done');
          source.close();
        }
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

  const sendAction = async (action_type: string, payload: Record<string, unknown>) => {
    await fetch('/api/loop/action', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        thread_id: threadId,
        action_type,
        payload,
      }),
    });
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
          Thread: <code>{threadId}</code> • Status: <strong>{status}</strong>
        </p>
      </header>

      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <div className="space-y-4">
          {signals.length > 0 && <SignalIntelligenceBoard signals={signals} />}
          {variants.length > 0 && (
            <ABVariantGrid
              variants={variants}
              onDeploy={(variantIndex) => {
                void sendAction('deploy_variant', { variant: variantIndex });
              }}
            />
          )}
          <ChannelIntentPicker
            selected={selectedChannel}
            onSelect={(channel) => {
              setSelectedChannel(channel);
              void sendAction('channel_select', { channel });
            }}
          />
          {metrics.length > 0 && (
            <FeedbackPanel
              metrics={metrics}
              onFeedBack={() => {
                void sendAction('feedback', {
                  note: 'ROI angle got 3x higher replies in simulation',
                });
              }}
            />
          )}
        </div>

        <CampaignTimeline entries={timeline} />
      </div>

      <section className="rounded-xl border border-zinc-200 p-4 shadow-sm">
        <h2 className="text-lg font-semibold">Raw SSE Event Log</h2>
        <div className="mt-3 max-h-80 overflow-y-auto rounded-md bg-zinc-950 p-3 font-mono text-xs text-zinc-100">
          {events.map((event, index) => (
            <pre key={`${event}-${index}`} className="whitespace-pre-wrap wrap-break-word border-b border-zinc-800 py-2">
              {event}
            </pre>
          ))}
          {events.length === 0 && <p className="text-zinc-400">No events yet. Start the loop.</p>}
        </div>
      </section>
    </main>
  );
}
