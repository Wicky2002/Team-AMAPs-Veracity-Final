'use client';

import { useRef, useState, useCallback, useEffect } from 'react';

import { ABVariantGrid } from '@/components/ABVariantGrid';
import { CampaignTimeline } from '@/components/CampaignTimeline';
import { ChannelIntentPicker } from '@/components/ChannelIntentPicker';
import { FeedbackPanel } from '@/components/FeedbackPanel';
import { SignalIntelligenceBoard } from '@/components/SignalIntelligenceBoard';
import type { FeedbackMetric, OutreachVariant, SSEEvent, SignalReference, TimelineEntry } from '@/lib/loop-types';
import { UI_COMPONENT, normalizeUIRenderComponent } from '@/lib/ui-components';

/* ────────────────────────────────────────────────────
   Type coercion helpers (preserved from backend contract)
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
   Stage & tab config
   ──────────────────────────────────────────────────── */

type Stage = 'research' | 'generate' | 'ab' | 'outreach' | 'feedback';
const STAGES: Stage[] = ['research', 'generate', 'ab', 'outreach', 'feedback'];
const STAGE_LABELS: Record<Stage, string> = {
  research: 'Research',
  generate: 'Generate',
  ab: 'A/B Test',
  outreach: 'Outreach',
  feedback: 'Feedback',
};
const STAGE_ICONS: Record<Stage, string> = {
  research: '🔍',
  generate: '✍️',
  ab: '⚖️',
  outreach: '📡',
  feedback: '📊',
};

const NODE_TO_STAGE: Record<string, Stage> = {
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

const UI_TO_STAGE: Record<string, Stage> = {
  [UI_COMPONENT.SIGNAL_BOARD]: 'research',
  [UI_COMPONENT.AB_GRID]: 'ab',
  [UI_COMPONENT.CHANNEL_PICKER]: 'ab',
  [UI_COMPONENT.FEEDBACK_PANEL]: 'feedback',
  [UI_COMPONENT.STALE_WARNING]: 'research',
};

function tagStage(event: SSEEvent, currentStage: Stage): Stage {
  if (event.type === 'node_started') return NODE_TO_STAGE[event.node] ?? currentStage;
  if (event.type === 'signal_found') return 'research';
  if (event.type === 'ui_render') return UI_TO_STAGE[event.component] ?? currentStage;
  if (event.type === 'loop_complete') return 'feedback';
  if (event.type === 'warning') return currentStage;
  return currentStage;
}

type TaggedEvent = SSEEvent & { _stage: Stage };

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
  const [taggedEvents, setTaggedEvents] = useState<TaggedEvent[]>([]);
  const [rawEvents, setRawEvents] = useState<string[]>([]);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [status, setStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle');
  const [threadId, setThreadId] = useState('');
  const [currentStage, setCurrentStage] = useState<Stage>('research');
  const [activeTab, setActiveTab] = useState<Stage>('research');
  const [visitedStages, setVisitedStages] = useState<Set<Stage>>(new Set());
  const [showRawLog, setShowRawLog] = useState(false);
  const [isDark, setIsDark] = useState(true);

  const eventSourceRef = useRef<EventSource | null>(null);
  const currentStageRef = useRef<Stage>('research');
  const feedRef = useRef<HTMLDivElement>(null);

  // Apply theme class
  useEffect(() => {
    document.documentElement.classList.toggle('light', !isDark);
  }, [isDark]);

  const resolveThreadId = () => {
    if (threadId) return threadId;
    const generated = crypto.randomUUID();
    setThreadId(generated);
    return generated;
  };

  const appendEvent = (raw: string) => {
    setRawEvents((prev) => [raw, ...prev].slice(0, 160));
  };

  const applyTypedEvent = useCallback((parsed: SSEEvent) => {
    const stage = tagStage(parsed, currentStageRef.current);

    if (parsed.type === 'node_started') {
      const newStage = NODE_TO_STAGE[parsed.node];
      if (newStage) {
        currentStageRef.current = newStage;
        setCurrentStage(newStage);
        setActiveTab(newStage);
        setVisitedStages((prev) => new Set(prev).add(newStage));
      }
    }

    setTaggedEvents((prev) => [...prev, { ...parsed, _stage: stage }].slice(-250));

    // Update timeline from any event that has campaign_history
    if (parsed.type === 'ui_render') {
      const props = parsed.props as Record<string, unknown>;
      const nextTimeline = toTimeline(props);
      if (nextTimeline.length > 0) setTimeline(nextTimeline);
    }

    if (parsed.type === 'loop_complete' && parsed.next_action !== 'refined_research') {
      setStatus('done');
      eventSourceRef.current?.close();
    }

    setTimeout(() => feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: 'smooth' }), 50);
  }, []);

  const startLoop = (msg?: string) => {
    const activeMessage = msg ?? message;
    if (!activeMessage.trim()) return;
    eventSourceRef.current?.close();
    setTaggedEvents([]);
    setRawEvents([]);
    setTimeline([]);
    setCurrentStage('research');
    setActiveTab('research');
    setVisitedStages(new Set(['research']));
    currentStageRef.current = 'research';
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
      } catch { /* ignore */ }
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

  /* ── Event renderer ──────────────────────────────── */

  const renderEvent = (event: TaggedEvent, index: number) => {
    if (event.type === 'node_started') {
      return (
        <div key={`node-${index}`} className="flex items-center gap-2.5 py-2 anim-in">
          <span className="w-2 h-2 rounded-full bg-[var(--success)] anim-pulse shrink-0" />
          <span className="text-[13px] text-[var(--text-secondary)] font-mono">
            <span className="text-[var(--text-primary)]">{event.node}</span> · Cycle {event.cycle_n}
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
        <div key={`signal-${index}`} className="flex items-start gap-3 py-2 anim-in">
          <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded mt-0.5 shrink-0 ${badgeMap[event.source] ?? ''}`}>
            {event.source}
          </span>
          <p className="text-[13px] text-[var(--text-secondary)] leading-relaxed">{event.quote}</p>
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
            <div key={`ui-stale-${index}`} className="rounded-lg border border-[var(--warning)] bg-[var(--warning-soft)] p-3 text-sm text-[var(--warning)] anim-in">
              ⚠️ {typeof event.props.message === 'string' ? event.props.message : 'Signals may be stale.'}
            </div>
          );
        default:
          return null;
      }
    }

    if (event.type === 'warning') {
      return (
        <div key={`warning-${index}`} className="rounded-lg border border-[var(--warning)] bg-[var(--warning-soft)] p-3.5 text-[13px] text-[var(--warning)] anim-in">
          ⚠️ {event.message}
          {event.fallback_used && <span className="ml-2 text-[11px] opacity-60">Fallback used</span>}
        </div>
      );
    }

    if (event.type === 'loop_complete') {
      return (
        <div key={`complete-${index}`} className="rounded-lg border border-[var(--success)] bg-[var(--success-soft)] p-3.5 text-[13px] text-[var(--success)] anim-in">
          ✓ Loop complete — Cycle {event.cycle_n} · Next: <span className="font-mono font-semibold">{event.next_action}</span>
        </div>
      );
    }
    return null;
  };

  /* ── Filter events for active tab ────────────────── */
  const filteredEvents = taggedEvents.filter((e) => e._stage === activeTab);

  /* ── Status badge ────────────────────────────────── */
  const statusConfig: Record<string, { dot: string; text: string; label: string }> = {
    idle:    { dot: 'bg-[var(--text-muted)]', text: 'text-[var(--text-muted)]', label: 'Ready' },
    running: { dot: 'bg-[var(--success)] anim-pulse', text: 'text-[var(--success)]', label: 'Running' },
    done:    { dot: 'bg-[var(--accent)]', text: 'text-[var(--accent)]', label: 'Complete' },
    error:   { dot: 'bg-[var(--error)]', text: 'text-[var(--error)]', label: 'Error' },
  };
  const sc = statusConfig[status];

  const eventCounts: Record<Stage, number> = { research: 0, generate: 0, ab: 0, outreach: 0, feedback: 0 };
  for (const e of taggedEvents) eventCounts[e._stage]++;

  /* ── Render ──────────────────────────────────────── */

  return (
    <div className="flex flex-col h-screen overflow-hidden relative">

      {/* ── Header ───────────────────────────────────── */}
      <header className="glass-bar px-6 py-3 flex items-center justify-between z-20 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-md bg-[var(--accent)] flex items-center justify-center">
            <span className="text-[var(--bg-base)] font-bold text-[10px] tracking-tight">Vx</span>
          </div>
          <div>
            <h1 className="text-sm font-semibold text-[var(--text-primary)]">Veracity Workspace</h1>
            <p className="text-[10px] text-[var(--text-muted)] font-mono">Signal → Action Growth Loop</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Status badge */}
          <div className={`flex items-center gap-1.5 text-[11px] font-mono ${sc.text}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${sc.dot}`} />
            {sc.label}
          </div>

          {threadId && (
            <code className="text-[10px] text-[var(--text-muted)] font-mono hidden sm:block max-w-[140px] truncate">
              {threadId.slice(0, 8)}…
            </code>
          )}

          {/* Dark/Light toggle */}
          <button
            type="button"
            onClick={() => setIsDark(!isDark)}
            className="theme-toggle"
            title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {isDark ? '☀️' : '🌙'}
          </button>
        </div>
      </header>

      {/* ── Tab bar ──────────────────────────────────── */}
      {status !== 'idle' && (
        <div className="tab-bar px-4 py-2 flex items-center gap-1 shrink-0 overflow-x-auto z-10">
          {STAGES.map((stage) => {
            const isActive = activeTab === stage;
            const isCurrent = currentStage === stage && status === 'running';
            const isVisited = visitedStages.has(stage);
            const count = eventCounts[stage];

            return (
              <button
                key={stage}
                type="button"
                onClick={() => isVisited && setActiveTab(stage)}
                className={`
                  tab-item flex items-center gap-2
                  ${isActive ? 'active' : ''}
                  ${!isVisited ? 'disabled' : ''}
                `}
              >
                <span>{STAGE_ICONS[stage]}</span>
                <span>{STAGE_LABELS[stage]}</span>
                {isCurrent && (
                  <span className="w-1.5 h-1.5 rounded-full bg-[var(--success)] anim-pulse" />
                )}
                {count > 0 && !isActive && (
                  <span className="text-[9px] font-mono bg-[var(--bg-elevated)] text-[var(--text-muted)] px-1.5 py-0.5 rounded-full">
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* ── Main content ─────────────────────────────── */}
      <div className="flex-1 flex min-h-0 overflow-hidden">

        {/* Left: Event feed for active tab */}
        <div ref={feedRef} className="flex-1 overflow-y-auto pb-36">
          <div className="max-w-4xl mx-auto px-6 pt-6">

            {/* Empty state */}
            {status === 'idle' && taggedEvents.length === 0 && (
              <div className="anim-in py-16">
                <h2 className="text-2xl font-light text-gradient tracking-tight mb-2">
                  What shall we orchestrate?
                </h2>
                <p className="text-sm text-[var(--text-muted)] mb-8">
                  Start a growth intelligence loop to research, generate, and deploy.
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  {SUGGESTED.map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      onClick={() => { setMessage(prompt); startLoop(prompt); }}
                      className="panel panel-hover p-4 rounded-xl text-left flex flex-col gap-2 group transition-all duration-200 cursor-pointer"
                    >
                      <span className="text-[var(--text-muted)] group-hover:text-[var(--accent)] transition-colors text-sm">→</span>
                      <span className="text-[13px] text-[var(--text-secondary)] group-hover:text-[var(--text-primary)] leading-snug transition-colors">
                        {prompt}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Tab content heading */}
            {status !== 'idle' && (
              <div className="mb-4 flex items-center gap-3">
                <span className="text-lg">{STAGE_ICONS[activeTab]}</span>
                <div>
                  <h2 className="text-base font-semibold text-[var(--text-primary)]">
                    {STAGE_LABELS[activeTab]}
                  </h2>
                  <p className="text-[11px] text-[var(--text-muted)]">
                    {filteredEvents.length} event{filteredEvents.length !== 1 ? 's' : ''} in this stage
                  </p>
                </div>
              </div>
            )}

            {/* Filtered events */}
            <div className="space-y-4">
              {filteredEvents.map((event, i) => renderEvent(event, i))}
            </div>

            {/* Inline Campaign Timeline on feedback tab */}
            {activeTab === 'feedback' && timeline.length > 0 && (
              <div className="mt-6">
                <CampaignTimeline entries={timeline} />
              </div>
            )}

            {/* Empty tab state */}
            {status !== 'idle' && filteredEvents.length === 0 && (
              <div className="text-center py-12">
                <p className="text-sm text-[var(--text-muted)]">
                  {visitedStages.has(activeTab)
                    ? 'No events recorded in this stage yet.'
                    : 'This stage hasn\'t started yet. It will unlock as the loop progresses.'}
                </p>
              </div>
            )}

            {/* Running indicator */}
            {status === 'running' && activeTab === currentStage && (
              <div className="flex items-center gap-2.5 py-4 mt-2">
                <span className="w-2 h-2 rounded-full bg-[var(--success)] anim-pulse" />
                <span className="text-[13px] text-[var(--text-muted)]">Agents processing…</span>
              </div>
            )}
          </div>
        </div>

        {/* Right sidebar: Campaign Timeline (desktop) */}
        <div className="hidden lg:block w-72 border-l border-[var(--border-subtle)] overflow-y-auto p-4 bg-[var(--bg-surface)]">
          <CampaignTimeline entries={timeline} />
        </div>
      </div>

      {/* ── Floating input ───────────────────────────── */}
      <div
        className="absolute bottom-0 left-0 right-0 z-20 px-6 pb-5 pt-4"
        style={{ background: 'linear-gradient(to top, var(--bg-base) 70%, transparent)' }}
      >
        <div className="max-w-4xl mx-auto lg:mr-[288px]">
          <div className="panel p-2 flex items-end gap-2 focus-within:border-[var(--border-medium)] transition-all">
            <input
              className="flex-1 bg-transparent border-none text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] outline-none px-4 py-3"
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
                className="h-10 px-5 rounded-xl bg-[var(--accent)] text-[var(--bg-base)] text-xs font-bold hover:brightness-110 disabled:opacity-20 transition-all shrink-0 cursor-pointer"
              >
                {status === 'running' ? 'Running…' : 'Start Loop'}
              </button>
              {status === 'running' && (
                <button
                  type="button"
                  onClick={stopLoop}
                  className="h-10 px-3 rounded-xl border border-[var(--border-subtle)] text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:border-[var(--border-medium)] transition-all cursor-pointer"
                >
                  Stop
                </button>
              )}
            </div>
          </div>

          <div className="flex items-center justify-between mt-2 px-2">
            <p className="text-[10px] font-mono text-[var(--text-muted)]">
              Multi-Agent Growth Loop · {taggedEvents.length} events
            </p>
            <button
              type="button"
              onClick={() => setShowRawLog(!showRawLog)}
              className="text-[10px] font-mono text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors cursor-pointer"
            >
              {showRawLog ? 'Hide' : 'Show'} Raw Log
            </button>
          </div>
        </div>
      </div>

      {/* ── Raw event log drawer ─────────────────────── */}
      {showRawLog && (
        <div className="absolute bottom-28 left-6 right-6 z-30 max-h-60 overflow-y-auto panel p-4 lg:mr-[288px] max-w-4xl mx-auto">
          <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-widest mb-3">
            Raw SSE Events
          </h3>
          <div className="font-mono text-[11px] text-[var(--text-secondary)] space-y-1">
            {rawEvents.map((event, index) => (
              <pre key={`${event.slice(0, 20)}-${index}`} className="whitespace-pre-wrap break-all border-b border-[var(--border-subtle)] pb-1.5">
                {event}
              </pre>
            ))}
            {rawEvents.length === 0 && <p className="text-[var(--text-muted)]">No events yet.</p>}
          </div>
        </div>
      )}
    </div>
  );
}
