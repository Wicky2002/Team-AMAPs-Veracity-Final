'use client';

import { useRef, useState } from 'react';

import { ABVariantGrid } from '@/components/ABVariantGrid';
import { CampaignTimeline } from '@/components/CampaignTimeline';
import { ChannelIntentPicker } from '@/components/ChannelIntentPicker';
import { FeedbackPanel } from '@/components/FeedbackPanel';
import { SignalIntelligenceBoard } from '@/components/SignalIntelligenceBoard';
import type { FeedbackMetric, OutreachVariant, SSEEvent, SignalReference, TimelineEntry } from '@/lib/loop-types';
import { UI_COMPONENT, normalizeUIRenderComponent } from '@/lib/ui-components';

/* ────────────────────────────────────────────────────
   Type coercion helpers (unchanged from skeleton)
   ──────────────────────────────────────────────────── */

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

const toSignals = (props: Record<string, unknown>): SignalReference[] => {
  const rawSignals = props.signals;
  if (!Array.isArray(rawSignals)) return [];
  return rawSignals.flatMap((signal) => {
    if (!isRecord(signal)) return [];
    return [{
      source: String(signal.source ?? 'unknown'),
      source_url: typeof signal.source_url === 'string' ? signal.source_url : undefined,
      quote: String(signal.quote ?? signal.content ?? ''),
      content: typeof signal.content === 'string' ? signal.content : undefined,
      confidence: Number(signal.confidence ?? 0.5),
      source_type: (['competitor','audience','pestel'].includes(String(signal.source_type)) ? signal.source_type : undefined) as SignalReference['source_type'],
      raw_quote: typeof signal.raw_quote === 'string' ? signal.raw_quote : undefined,
    }];
  });
};

const toVariants = (props: Record<string, unknown>): OutreachVariant[] => {
  const rawVariants = props.variants;
  if (!Array.isArray(rawVariants)) return [];
  return rawVariants.flatMap((variant) => {
    if (!isRecord(variant)) return [];
    const rawProvenance = Array.isArray(variant.provenance_chain) ? variant.provenance_chain : [];
    const provenanceChain = rawProvenance.flatMap((sig) => {
      if (!isRecord(sig)) return [];
      const sourceType = sig.source_type;
      const normalizedSourceType: SignalReference['source_type'] =
        sourceType === 'competitor' || sourceType === 'audience' || sourceType === 'pestel' ? sourceType : undefined;
      return [{
        source: String(sig.source ?? 'unknown'),
        source_url: typeof sig.source_url === 'string' ? sig.source_url : undefined,
        quote: String(sig.quote ?? ''),
        confidence: Number(sig.confidence ?? 0),
        content: typeof sig.content === 'string' ? sig.content : undefined,
        source_type: normalizedSourceType,
        raw_quote: typeof sig.raw_quote === 'string' ? sig.raw_quote : undefined,
      }];
    });
    return [{
      subject_line: String(variant.subject_line ?? 'Untitled'),
      hook: String(variant.hook ?? ''),
      cta: String(variant.cta ?? ''),
      hypothesis: String(variant.hypothesis ?? 'Unknown hypothesis'),
      provenance_chain: provenanceChain,
    }];
  });
};

const toMetrics = (props: Record<string, unknown>): FeedbackMetric[] => {
  const rawMetrics = props.metrics;
  if (!Array.isArray(rawMetrics)) return [];
  return rawMetrics.flatMap((metric) => {
    if (!isRecord(metric)) return [];
    return [{
      variant: Number(metric.variant ?? 0),
      open_rate: Number(metric.open_rate ?? 0),
      reply_rate: Number(metric.reply_rate ?? 0),
      click_rate: Number(metric.click_rate ?? 0),
    }];
  });
};

const toTimeline = (props: Record<string, unknown>): TimelineEntry[] => {
  const rawHistory = props.campaign_history;
  if (!Array.isArray(rawHistory)) return [];
  return rawHistory.flatMap((entry) => {
    if (!isRecord(entry)) return [];
    const angle = entry.angle;
    const normalizedAngle =
      angle === 'roi' || angle === 'social_proof' || angle === 'competitor_gap' ? angle : 'competitor_gap';
    return [{
      cycle_n: Number(entry.cycle_n ?? 0),
      top_signal: String(entry.top_signal ?? ''),
      winning_variant: String(entry.winning_variant ?? ''),
      open_rate: Number(entry.open_rate ?? 0),
      reply_rate: Number(entry.reply_rate ?? 0),
      angle: normalizedAngle,
      timestamp: String(entry.timestamp ?? new Date().toISOString()),
    }];
  });
};

const isSSEEvent = (value: unknown): value is SSEEvent => {
  if (!isRecord(value) || typeof value.type !== 'string') return false;
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
    case 'ui_render': {
      if (!isRecord(value.props) || typeof value.cycle_n !== 'number') return false;
      const component = normalizeUIRenderComponent(value.component);
      if (!component) return false;
      value.component = component;
      return true;
    }
    case 'loop_complete':
      return (
        typeof value.cycle_n === 'number' &&
        (value.next_action === 'awaiting_feedback' || value.next_action === 'refined_research' || value.next_action === 'end')
      );
    case 'warning':
      return typeof value.message === 'string' && typeof value.fallback_used === 'boolean';
    default:
      return false;
  }
};

/* ────────────────────────────────────────────────────
   Stage progress config
   ──────────────────────────────────────────────────── */

const STAGES = ['research', 'generate', 'ab', 'outreach', 'feedback'] as const;
const STAGE_LABELS: Record<string, string> = {
  research: 'Research',
  generate: 'Generate',
  ab: 'A/B Test',
  outreach: 'Outreach',
  feedback: 'Feedback',
};

const SUGGESTED = [
  'Is Lilian well-positioned in the AI SDR market?',
  'Research competitor signals for Vector Agents',
  'Generate outreach emails for VP Sales at Series B',
];

/* ────────────────────────────────────────────────────
   Component
   ──────────────────────────────────────────────────── */

export default function Home() {
  const [message, setMessage] = useState('Is Lilian well-positioned in the AI SDR market?');
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [rawEvents, setRawEvents] = useState<string[]>([]);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [status, setStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle');
  const [threadId, setThreadId] = useState('');
  const [currentStage, setCurrentStage] = useState<string>('');
  const [showRawLog, setShowRawLog] = useState(false);

  const eventSourceRef = useRef<EventSource | null>(null);
  const feedRef = useRef<HTMLDivElement>(null);

  const resolveThreadId = () => {
    if (threadId) return threadId;
    const generated = crypto.randomUUID();
    setThreadId(generated);
    return generated;
  };

  const appendEvent = (raw: string) => {
    setRawEvents((prev) => [raw, ...prev].slice(0, 160));
  };

  const applyTypedEvent = (parsed: SSEEvent) => {
    setEvents((prev) => [...prev, parsed].slice(-180));

    // Track current stage from node_started events
    if (parsed.type === 'node_started') {
      const nodeMap: Record<string, string> = {
        intent_router: 'research',
        market_intelligence: 'research',
        competitor_node: 'research',
        audience_node: 'research',
        pestel_node: 'research',
        content_gen: 'generate',
        ab_variant: 'ab',
        outreach: 'outreach',
        feedback_ingestor: 'feedback',
      };
      setCurrentStage(nodeMap[parsed.node] ?? currentStage);
    }

    if (parsed.type === 'ui_render' && parsed.component === UI_COMPONENT.FEEDBACK_PANEL) {
      const nextTimeline = toTimeline(parsed.props);
      if (nextTimeline.length > 0) setTimeline(nextTimeline);
    }

    if (parsed.type === 'loop_complete' && parsed.next_action !== 'refined_research') {
      setStatus('done');
      eventSourceRef.current?.close();
    }

    // Scroll to bottom
    setTimeout(() => feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: 'smooth' }), 50);
  };

  const startLoop = (msg?: string) => {
    const activeMessage = msg ?? message;
    if (!activeMessage.trim()) return;
    eventSourceRef.current?.close();
    setEvents([]);
    setRawEvents([]);
    setTimeline([]);
    setCurrentStage('research');
    if (msg) setMessage(msg);

    const activeThreadId = resolveThreadId();
    const params = new URLSearchParams({ thread_id: activeThreadId, message: activeMessage });
    setStatus('running');
    const source = new EventSource(`/api/loop/proxy?${params.toString()}`);
    eventSourceRef.current = source;

    source.onmessage = (event) => {
      appendEvent(event.data);
      try {
        const parsed = JSON.parse(event.data) as unknown;
        if (!isSSEEvent(parsed)) return;
        applyTypedEvent(parsed);
      } catch { /* ignore malformed */ }
    };
    source.onerror = () => { setStatus('error'); source.close(); };
  };

  const stopLoop = () => {
    eventSourceRef.current?.close();
    setStatus('done');
  };

  const sendAction = async (action_type: 'feedback' | 'channel_select' | 'deploy_variant', payload: Record<string, unknown>) => {
    const activeThreadId = resolveThreadId();
    const response = await fetch('/api/loop/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ thread_id: activeThreadId, action_type, payload }),
    });
    const actionResult = (await response.json().catch(() => null)) as { latest_events?: unknown[] } | null;
    if (!actionResult || !Array.isArray(actionResult.latest_events)) return;
    for (const event of actionResult.latest_events) {
      if (!isSSEEvent(event)) continue;
      appendEvent(JSON.stringify(event));
      applyTypedEvent(event);
    }
  };

  /* ── Event rendering ─────────────────────────────── */

  const renderEvent = (event: SSEEvent, index: number) => {
    if (event.type === 'node_started') {
      return (
        <div key={`node-${index}`} className="flex items-center gap-2.5 py-1.5 anim-in">
          <span className="w-2 h-2 rounded-full bg-emerald-500 anim-pulse shrink-0" />
          <span className="text-xs text-neutral-500 font-mono">
            <span className="text-neutral-300">{event.node}</span> · Cycle {event.cycle_n}
          </span>
        </div>
      );
    }

    if (event.type === 'signal_found') {
      const badgeMap: Record<string, string> = {
        competitor: 'badge-competitor',
        audience: 'badge-audience',
        pestel: 'badge-pestel',
      };
      return (
        <div key={`signal-${index}`} className="flex items-start gap-3 py-1.5 anim-in">
          <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded mt-0.5 shrink-0 ${badgeMap[event.source] ?? 'bg-white/5 text-neutral-400'}`}>
            {event.source}
          </span>
          <p className="text-xs text-neutral-400 leading-relaxed">{event.quote}</p>
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
              onDeploy={(variant) => { void sendAction('deploy_variant', { variant }); }}
            />
          );
        case UI_COMPONENT.CHANNEL_PICKER:
          return (
            <ChannelIntentPicker
              key={`ui-channel-${index}`}
              selected={typeof event.props.selected === 'string' ? event.props.selected : undefined}
              onSelect={(channel) => { void sendAction('channel_select', { channel }); }}
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
            <div key={`ui-stale-${index}`} className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-sm text-amber-300 anim-in">
              ⚠️ {typeof event.props.message === 'string' ? event.props.message : 'Signals may be stale.'}
            </div>
          );
        default:
          return null;
      }
    }

    if (event.type === 'warning') {
      return (
        <div key={`warning-${index}`} className="rounded-lg border border-amber-500/20 bg-amber-500/[0.06] p-3 text-sm text-amber-200 anim-in">
          ⚠️ {event.message}
          {event.fallback_used && <span className="ml-2 text-xs text-amber-500 opacity-70">Fallback used</span>}
        </div>
      );
    }

    if (event.type === 'loop_complete') {
      return (
        <div key={`complete-${index}`} className="rounded-lg border border-emerald-500/20 bg-emerald-500/[0.05] p-3 text-sm text-emerald-300 anim-in">
          ✓ Loop complete — Cycle {event.cycle_n} · Next: <span className="font-mono font-semibold">{event.next_action}</span>
        </div>
      );
    }

    return null;
  };

  /* ── Status badge ────────────────────────────────── */
  const statusConfig: Record<string, { dot: string; text: string; label: string }> = {
    idle: { dot: 'bg-neutral-500', text: 'text-neutral-500', label: 'Ready' },
    running: { dot: 'bg-emerald-500 anim-pulse', text: 'text-emerald-400', label: 'Running' },
    done: { dot: 'bg-blue-500', text: 'text-blue-400', label: 'Complete' },
    error: { dot: 'bg-red-500', text: 'text-red-400', label: 'Error' },
  };
  const sc = statusConfig[status];

  /* ── Render ──────────────────────────────────────── */

  return (
    <div className="flex flex-col h-screen overflow-hidden relative">
      {/* Ambient glow */}
      <div className="absolute top-[-10%] left-[15%] w-[600px] h-[500px] bg-emerald-600/[0.03] blur-[120px] rounded-full pointer-events-none" />

      {/* ── Header ───────────────────────────────────── */}
      <header className="glass-bar px-6 py-3.5 flex items-center justify-between z-20 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-md bg-white flex items-center justify-center">
            <span className="text-black font-bold text-[10px] tracking-tight">Vx</span>
          </div>
          <div>
            <h1 className="text-sm font-semibold text-white">Veracity Workspace</h1>
            <p className="text-[10px] text-neutral-500 font-mono">Signal → Action Growth Loop</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {/* Status badge */}
          <div className={`flex items-center gap-1.5 text-[11px] font-mono ${sc.text}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${sc.dot}`} />
            {sc.label}
          </div>

          {/* Thread ID */}
          {threadId && (
            <code className="text-[10px] text-neutral-600 font-mono hidden sm:block max-w-[160px] truncate">
              {threadId.slice(0, 8)}…
            </code>
          )}
        </div>
      </header>

      {/* ── Stage Progress ───────────────────────────── */}
      {status !== 'idle' && (
        <div className="px-6 py-2.5 border-b border-white/5 bg-[#0C0C0C] flex items-center gap-1 shrink-0 overflow-x-auto">
          {STAGES.map((stage, i) => {
            const stageIdx = STAGES.indexOf(currentStage as typeof stage);
            const isActive = stage === currentStage;
            const isPast = i < stageIdx;
            return (
              <div key={stage} className="flex items-center gap-1">
                {i > 0 && <div className={`w-6 h-px ${isPast ? 'bg-emerald-500/40' : 'bg-white/8'}`} />}
                <div className={`
                  px-2.5 py-1 rounded-md text-[10px] font-semibold uppercase tracking-wider transition-colors
                  ${isActive
                    ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                    : isPast
                      ? 'bg-white/[0.04] text-neutral-400'
                      : 'text-neutral-600'}
                `}>
                  {STAGE_LABELS[stage]}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ── Main content ─────────────────────────────── */}
      <div className="flex-1 flex min-h-0 overflow-hidden">

        {/* Left: Event feed */}
        <div ref={feedRef} className="flex-1 overflow-y-auto pb-40">
          <div className="max-w-4xl mx-auto px-6 pt-8">

            {/* Empty state */}
            {status === 'idle' && events.length === 0 && (
              <div className="anim-in py-12">
                <h2 className="text-2xl font-light text-gradient tracking-tight mb-2">
                  What shall we orchestrate?
                </h2>
                <p className="text-sm text-neutral-500 mb-8">Start a growth intelligence loop to research, generate, and deploy.</p>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  {SUGGESTED.map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      onClick={() => { setMessage(prompt); startLoop(prompt); }}
                      className="panel panel-hover p-4 rounded-xl text-left flex flex-col gap-2 group transition-all duration-200"
                    >
                      <span className="text-neutral-600 group-hover:text-emerald-400 transition-colors text-sm">→</span>
                      <span className="text-[13px] text-neutral-400 group-hover:text-white leading-snug transition-colors">
                        {prompt}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Events */}
            <div className="space-y-4">
              {events.map((event, i) => renderEvent(event, i))}
            </div>

            {/* Running indicator */}
            {status === 'running' && (
              <div className="flex items-center gap-2.5 py-3 mt-2">
                <span className="w-2 h-2 rounded-full bg-emerald-500 anim-pulse" />
                <span className="text-xs text-neutral-500">Agents processing…</span>
              </div>
            )}
          </div>
        </div>

        {/* Right: Timeline sidebar */}
        <div className="hidden lg:block w-72 border-l border-white/5 overflow-y-auto p-4 bg-[#0C0C0C]">
          <CampaignTimeline entries={timeline} />
        </div>
      </div>

      {/* ── Floating input ───────────────────────────── */}
      <div className="absolute bottom-0 left-0 right-0 z-20 px-6 pb-5 pt-4" style={{ background: 'linear-gradient(to top, #0A0A0A 70%, transparent)' }}>
        <div className="max-w-4xl mx-auto lg:mr-[288px]">
          <div className="panel rounded-2xl p-2 flex items-end gap-2 focus-within:border-white/15 transition-all">
            <input
              className="flex-1 bg-transparent border-none text-sm text-white placeholder-neutral-500 outline-none px-4 py-3"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') startLoop(); }}
              placeholder="Ask a research, generate, or feedback question…"
            />
            <div className="flex gap-1.5 mb-1 mr-1">
              <button
                type="button"
                onClick={() => startLoop()}
                disabled={status === 'running' || !message.trim()}
                className="h-10 px-5 rounded-xl bg-white text-black text-xs font-bold hover:bg-neutral-200 disabled:opacity-20 transition-all shrink-0"
              >
                {status === 'running' ? 'Running…' : 'Start Loop'}
              </button>
              {status === 'running' && (
                <button
                  type="button"
                  onClick={stopLoop}
                  className="h-10 px-3 rounded-xl border border-white/10 text-xs text-neutral-400 hover:text-white hover:border-white/20 transition-all"
                >
                  Stop
                </button>
              )}
            </div>
          </div>

          {/* Bottom bar: raw log toggle */}
          <div className="flex items-center justify-between mt-2 px-2">
            <p className="text-[10px] font-mono text-neutral-600">
              Multi-Agent Growth Loop · {events.length} events
            </p>
            <button
              type="button"
              onClick={() => setShowRawLog(!showRawLog)}
              className="text-[10px] font-mono text-neutral-600 hover:text-neutral-300 transition-colors"
            >
              {showRawLog ? 'Hide' : 'Show'} Raw Log
            </button>
          </div>
        </div>
      </div>

      {/* ── Raw event log drawer ─────────────────────── */}
      {showRawLog && (
        <div className="absolute bottom-28 left-6 right-6 z-30 max-h-60 overflow-y-auto rounded-xl panel p-4 lg:mr-[288px] max-w-4xl mx-auto">
          <h3 className="text-xs font-semibold text-neutral-400 uppercase tracking-widest mb-3">
            Raw SSE Events
          </h3>
          <div className="font-mono text-[11px] text-neutral-400 space-y-1">
            {rawEvents.map((event, index) => (
              <pre key={`${event.slice(0, 20)}-${index}`} className="whitespace-pre-wrap break-all border-b border-white/5 pb-1.5">
                {event}
              </pre>
            ))}
            {rawEvents.length === 0 && <p className="text-neutral-600">No events yet.</p>}
          </div>
        </div>
      )}
    </div>
  );
}
