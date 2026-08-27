'use client';

import { useEffect, useRef, useState } from 'react';

import { ABVariantGrid } from '@/components/ABVariantGrid';
import { CampaignBriefCard } from '@/components/CampaignBriefCard';
import { CampaignTimeline } from '@/components/CampaignTimeline';
import { ChannelIntentPicker } from '@/components/ChannelIntentPicker';
import { ComparisonCard } from '@/components/ComparisonCard';
import { FeedbackPanel } from '@/components/FeedbackPanel';
import { LinkedInPostGrid } from '@/components/LinkedInPostGrid';
import { SignalIntelligenceBoard } from '@/components/SignalIntelligenceBoard';
import type {
  CampaignBrief,
  EmailStatus,
  FeedbackMetric,
  LinkedInPost,
  OutreachVariant,
  SSEEvent,
  SignalReference,
  TimelineEntry,
} from '@/lib/loop-types';
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

    const sourceType = signal.source_type;
    const normalizedSourceType: SignalReference['source_type'] =
      sourceType === 'competitor' ||
      sourceType === 'audience' ||
      sourceType === 'pestel' ||
      sourceType === 'adjacent' ||
      sourceType === 'temporal'
        ? sourceType
        : undefined;

    const credibilityTier = signal.credibility_tier;
    const normalizedCredibilityTier: SignalReference['credibility_tier'] =
      credibilityTier === 'high' || credibilityTier === 'mid' || credibilityTier === 'unverified'
        ? credibilityTier
        : undefined;

    return [
      {
        source: String(signal.source ?? 'unknown'),
        source_url: typeof signal.source_url === 'string' ? signal.source_url : undefined,
        quote: String(signal.quote ?? signal.content ?? ''),
        content: typeof signal.content === 'string' ? signal.content : undefined,
        confidence: Number(signal.confidence ?? 0.5),
        source_type: normalizedSourceType,
        credibility_tier: normalizedCredibilityTier,
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
        sourceType === 'competitor' ||
        sourceType === 'audience' ||
        sourceType === 'pestel' ||
        sourceType === 'adjacent' ||
        sourceType === 'temporal'
          ? sourceType
          : undefined;

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
        image_url: typeof variant.image_url === 'string' ? variant.image_url : undefined,
      },
    ];
  });
};

const toEmailStatuses = (props: Record<string, unknown>): EmailStatus[] => {
  const raw = props.email_statuses;
  if (!Array.isArray(raw)) {
    return [];
  }

  return raw.flatMap((item) => {
    if (!isRecord(item)) {
      return [];
    }

    return [
      {
        variant: Number(item.variant ?? 0),
        email_id: String(item.email_id ?? ''),
        status: String(item.status ?? 'unknown'),
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

const toLinkedInPosts = (props: Record<string, unknown>): LinkedInPost[] => {
  const rawPosts = props.posts;
  if (!Array.isArray(rawPosts)) {
    return [];
  }

  return rawPosts.flatMap((post) => {
    if (!isRecord(post)) {
      return [];
    }

    const hashtags = Array.isArray(post.hashtags)
      ? post.hashtags.flatMap((tag) => (typeof tag === 'string' && tag.trim() ? [tag] : []))
      : [];

    return [
      {
        angle: String(post.angle ?? 'general'),
        hook: String(post.hook ?? ''),
        body: String(post.body ?? ''),
        cta: String(post.cta ?? ''),
        hashtags,
      },
    ];
  });
};

const toCampaignBrief = (props: Record<string, unknown>): CampaignBrief => {
  const toStringList = (value: unknown): string[] => {
    if (!Array.isArray(value)) {
      return [];
    }

    return value.flatMap((item) => {
      if (typeof item !== 'string') {
        return [];
      }

      const trimmed = item.trim();
      return trimmed ? [trimmed] : [];
    });
  };

  return {
    title: typeof props.title === 'string' && props.title.trim() ? props.title : 'Campaign Positioning Brief',
    positioning_statement:
      typeof props.positioning_statement === 'string' && props.positioning_statement.trim()
        ? props.positioning_statement
        : 'Position this campaign around measurable, signal-driven outcomes.',
    target_audience:
      typeof props.target_audience === 'string' && props.target_audience.trim()
        ? props.target_audience
        : 'Revenue leaders in B2B growth teams',
    key_messages: toStringList(props.key_messages),
    competitor_gaps: toStringList(props.competitor_gaps),
    recommended_channels: toStringList(props.recommended_channels),
    next_actions: toStringList(props.next_actions),
    context: typeof props.context === 'string' ? props.context : undefined,
  };
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
        (value.source === 'competitor' ||
          value.source === 'audience' ||
          value.source === 'pestel' ||
          value.source === 'adjacent' ||
          value.source === 'temporal') &&
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
  const [productName, setProductName] = useState('Lilian (Vector Agents AI SDR)');
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [rawEvents, setRawEvents] = useState<string[]>([]);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [status, setStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle');
  const [threadId, setThreadId] = useState('');
  const [starting, setStarting] = useState(false);
  const [justCleared, setJustCleared] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const noticeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showNotice = (text: string) => {
    setNotice(text);
    if (noticeTimeoutRef.current) {
      clearTimeout(noticeTimeoutRef.current);
    }
    noticeTimeoutRef.current = setTimeout(() => setNotice(null), 4000);
  };

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem('veracity_thread_id');
      if (stored) {
        setThreadId(stored);
      }
    } catch {
      // localStorage unavailable (private mode, etc.) -- fall back to in-memory only.
    }
  }, []);

  const resolveThreadId = () => {
    if (threadId) {
      return threadId;
    }

    const generated = crypto.randomUUID();
    setThreadId(generated);
    try {
      window.localStorage.setItem('veracity_thread_id', generated);
    } catch {
      // localStorage unavailable -- thread id still works for this page session.
    }
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
      product_name: productName,
    });

    setStarting(true);
    setStatus('running');
    const source = new EventSource(`/api/loop/proxy?${params.toString()}`);
    eventSourceRef.current = source;

    source.onopen = () => {
      setStarting(false);
    };

    source.onmessage = (event) => {
      setStarting(false);
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
      setStarting(false);
      setStatus('error');
      source.close();
    };
  };

  const stopLoop = () => {
    eventSourceRef.current?.close();
    setStarting(false);
    setStatus('done');
  };

  const newThread = () => {
    eventSourceRef.current?.close();
    try {
      window.localStorage.removeItem('veracity_thread_id');
    } catch {
      // localStorage unavailable -- clearing in-memory state below is still enough.
    }
    setThreadId('');
    setEvents([]);
    setRawEvents([]);
    setTimeline([]);
    setStatus('idle');
    setJustCleared(true);
    setTimeout(() => setJustCleared(false), 1500);
  };

  const emitActionWarning = (message: string) => {
    const warningEvent: SSEEvent = {
      type: 'warning',
      message,
      fallback_used: true,
    };

    appendEvent(JSON.stringify(warningEvent));
    applyTypedEvent(warningEvent);
    setStatus('error');
  };

  const extractActionErrorMessage = (payload: unknown): string | null => {
    if (!isRecord(payload)) {
      return null;
    }

    if (typeof payload.error === 'string' && payload.error.trim()) {
      return payload.error;
    }

    if (typeof payload.detail === 'string' && payload.detail.trim()) {
      return payload.detail;
    }

    if (Array.isArray(payload.detail) && payload.detail.length > 0) {
      try {
        return JSON.stringify(payload.detail);
      } catch {
        return 'Unknown backend validation error';
      }
    }

    return null;
  };

  const sendAction = async (action_type: 'feedback' | 'channel_select' | 'deploy_variant', payload: Record<string, unknown>) => {
    const activeThreadId = resolveThreadId();

    try {
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
            error?: unknown;
            detail?: unknown;
          }
        | null;

      if (!response.ok) {
        const reason = extractActionErrorMessage(actionResult) ?? `HTTP ${response.status}`;
        emitActionWarning(`Action request failed. ${reason}`);
        return;
      }

      if (!actionResult || !Array.isArray(actionResult.latest_events)) {
        emitActionWarning('Action completed, but the backend returned no renderable events.');
        return;
      }

      for (const event of actionResult.latest_events) {
        if (!isSSEEvent(event)) {
          continue;
        }

        appendEvent(JSON.stringify(event));
        applyTypedEvent(event);
      }
    } catch (error) {
      const reason = error instanceof Error ? error.message : 'Unknown network error';
      emitActionWarning(`Could not reach action endpoint. ${reason}`);
    }
  };

  const refreshEngagement = async () => {
    const activeThreadId = resolveThreadId();

    try {
      const response = await fetch('/api/loop/refresh', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ thread_id: activeThreadId }),
      });

      const result = (await response.json().catch(() => null)) as
        | {
            latest_events?: unknown[];
            error?: unknown;
            detail?: unknown;
          }
        | null;

      if (!response.ok) {
        const reason = extractActionErrorMessage(result) ?? `HTTP ${response.status}`;
        emitActionWarning(`Refresh failed. ${reason}`);
        return;
      }

      if (!result || !Array.isArray(result.latest_events)) {
        emitActionWarning('Refresh completed, but the backend returned no renderable events.');
        return;
      }

      for (const event of result.latest_events) {
        if (!isSSEEvent(event)) {
          continue;
        }

        appendEvent(JSON.stringify(event));
        applyTypedEvent(event);
      }
    } catch (error) {
      const reason = error instanceof Error ? error.message : 'Unknown network error';
      emitActionWarning(`Could not reach refresh endpoint. ${reason}`);
    }
  };

  const refreshEmailStatus = async () => {
    const activeThreadId = resolveThreadId();

    try {
      const response = await fetch('/api/loop/refresh-email', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ thread_id: activeThreadId }),
      });

      const result = (await response.json().catch(() => null)) as
        | {
            latest_events?: unknown[];
            error?: unknown;
            detail?: unknown;
          }
        | null;

      if (!response.ok) {
        const reason = extractActionErrorMessage(result) ?? `HTTP ${response.status}`;
        emitActionWarning(`Email status refresh failed. ${reason}`);
        return;
      }

      if (!result || !Array.isArray(result.latest_events)) {
        emitActionWarning('Email status refresh completed, but the backend returned no renderable events.');
        return;
      }

      for (const event of result.latest_events) {
        if (!isSSEEvent(event)) {
          continue;
        }

        appendEvent(JSON.stringify(event));
        applyTypedEvent(event);
      }
    } catch (error) {
      const reason = error instanceof Error ? error.message : 'Unknown network error';
      emitActionWarning(`Could not reach email status endpoint. ${reason}`);
    }
  };

  const drillSignal = async (signal: SignalReference) => {
    const activeThreadId = resolveThreadId();

    try {
      const response = await fetch('/api/loop/drill', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          thread_id: activeThreadId,
          source_type: signal.source_type ?? 'audience',
          source: signal.source,
          quote: signal.raw_quote ?? signal.quote,
        }),
      });

      const result = (await response.json().catch(() => null)) as
        | {
            latest_events?: unknown[];
            error?: unknown;
            detail?: unknown;
          }
        | null;

      if (!response.ok) {
        const reason = extractActionErrorMessage(result) ?? `HTTP ${response.status}`;
        emitActionWarning(`Drill-down failed. ${reason}`);
        return;
      }

      if (!result || !Array.isArray(result.latest_events)) {
        emitActionWarning('Drill-down completed, but the backend returned no renderable events.');
        return;
      }

      for (const event of result.latest_events) {
        if (!isSSEEvent(event)) {
          continue;
        }

        appendEvent(JSON.stringify(event));
        applyTypedEvent(event);
      }
    } catch (error) {
      const reason = error instanceof Error ? error.message : 'Unknown network error';
      emitActionWarning(`Could not reach drill-down endpoint. ${reason}`);
    }
  };

  const renderEvent = (event: SSEEvent, index: number) => {
    if (event.type === 'node_started') {
      return (
        <div
          key={`node-${index}`}
          className="flex items-center gap-2 rounded-xl border border-slate-200/80 bg-white/75 px-3 py-2 text-xs text-slate-600 shadow-sm backdrop-blur dark:border-slate-800 dark:bg-slate-900/60 dark:text-slate-300"
        >
          <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" />
          Running <span className="font-semibold capitalize">{event.node.replace(/_/g, ' ')}</span> — Cycle {event.cycle_n}
        </div>
      );
    }

    if (event.type === 'signal_found') {
      return (
        <div
          key={`signal-${index}`}
          className="rounded-xl border border-indigo-200/80 bg-linear-to-br from-indigo-50 to-white p-3 text-xs text-indigo-950 shadow-sm dark:border-indigo-500/30 dark:from-indigo-950/50 dark:to-slate-900 dark:text-indigo-100"
        >
          <span className="mr-1 inline-flex rounded-full border border-indigo-300/80 bg-indigo-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-indigo-700 dark:border-indigo-500/40 dark:bg-indigo-900/60 dark:text-indigo-200">
            {event.source}
          </span>
          {event.quote}
        </div>
      );
    }

    if (event.type === 'ui_render') {
      switch (event.component) {
        case UI_COMPONENT.SIGNAL_BOARD:
          return (
            <SignalIntelligenceBoard
              key={`ui-signal-${index}`}
              signals={toSignals(event.props)}
              onDrill={(signal) => drillSignal(signal)}
            />
          );
        case UI_COMPONENT.AB_GRID:
          return (
            <ABVariantGrid
              key={`ui-ab-${index}`}
              variants={toVariants(event.props)}
              onDeploy={async (variant) => {
                showNotice(`Deploying "${variant.subject_line}"…`);
                await sendAction('deploy_variant', { variant });
                showNotice('Variant deployed. Checking delivery status…');
                await refreshEmailStatus();
              }}
            />
          );
        case UI_COMPONENT.CHANNEL_PICKER:
          return (
            <ChannelIntentPicker
              key={`ui-channel-${index}`}
              selected={typeof event.props.selected === 'string' ? event.props.selected : undefined}
              onSelect={async (channel) => {
                showNotice(`Setting channel to ${channel}…`);
                await sendAction('channel_select', { channel });
                if (channel === 'Email' || channel === 'Both') {
                  showNotice('Channel set. Checking email delivery status…');
                  await refreshEmailStatus();
                } else {
                  showNotice(`Channel set to ${channel}.`);
                }
              }}
            />
          );
        case UI_COMPONENT.FEEDBACK_PANEL:
          return (
            <FeedbackPanel
              key={`ui-feedback-${index}`}
              metrics={toMetrics(event.props)}
              emailStatuses={toEmailStatuses(event.props)}
              onRefresh={async () => {
                showNotice('Refreshing reactions…');
                await refreshEngagement();
                showNotice('Reactions refreshed.');
              }}
              onRefreshEmail={async () => {
                showNotice('Refreshing email delivery status…');
                await refreshEmailStatus();
                showNotice('Email status refreshed.');
              }}
              onFeedback={async () => {
                const metrics = toMetrics(event.props);
                const winner = metrics.length > 0 ? metrics.reduce((a, b) => (a.reply_rate > b.reply_rate ? a : b)) : null;
                const winnerLabel = winner ? `Variant ${String.fromCharCode(65 + winner.variant)}` : 'Variant A';
                showNotice('Feedback sent — starting next research cycle…');
                await sendAction('feedback', {
                  note: winner
                    ? `${winnerLabel} led with a ${(winner.reply_rate * 100).toFixed(1)}% share of live Discord engagement.`
                    : 'No engagement recorded yet for this cycle.',
                  // angle is intentionally omitted here -- the backend infers it
                  // from the actual winning variant's hypothesis instead of us
                  // guessing/overriding it from the frontend.
                  winning_variant: winnerLabel,
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
              className="rounded-xl border border-amber-300/70 bg-amber-50/95 p-3 text-sm text-amber-900 shadow-sm dark:border-amber-500/30 dark:bg-amber-950/50 dark:text-amber-100"
            >
              {typeof event.props.message === 'string' ? event.props.message : 'Signals may be stale.'}
            </div>
          );
        case UI_COMPONENT.COMPARISON_CARD:
          return (
            <ComparisonCard
              key={`ui-comparison-${index}`}
              title={typeof event.props.title === 'string' ? event.props.title : 'AI SDR Competitive Landscape'}
              subtitle={typeof event.props.subtitle === 'string' ? event.props.subtitle : 'Comparison'}
              competitors={Array.isArray(event.props.competitors) ? (event.props.competitors as { name: string; tagline: string; strengths: string[]; weaknesses: string[]; highlight?: boolean }[]) : []}
              market_insight={typeof event.props.market_insight === 'string' ? event.props.market_insight : ''}
            />
          );
        case UI_COMPONENT.LINKEDIN_POST_GRID:
          return (
            <LinkedInPostGrid
              key={`ui-linkedin-${index}`}
              title={typeof event.props.title === 'string' ? event.props.title : 'LinkedIn Content Angles'}
              subtitle={typeof event.props.subtitle === 'string' ? event.props.subtitle : 'Social-ready drafts'}
              posts={toLinkedInPosts(event.props)}
            />
          );
        case UI_COMPONENT.CAMPAIGN_BRIEF_CARD:
          return <CampaignBriefCard key={`ui-brief-${index}`} brief={toCampaignBrief(event.props)} />;
        default:
          return null;
      }
    }

    if (event.type === 'warning') {
      return (
        <div
          key={`warning-${index}`}
          className="rounded-xl border border-amber-300/70 bg-amber-50/90 p-3 text-sm text-amber-950 shadow-sm dark:border-amber-500/30 dark:bg-amber-950/50 dark:text-amber-100"
        >
          ⚠️ {event.message}
          {event.fallback_used && <span className="ml-2 text-xs underline">Fallback used</span>}
        </div>
      );
    }

    if (event.type === 'loop_complete') {
      return (
        <div
          key={`complete-${index}`}
          className="rounded-xl border border-emerald-300/70 bg-emerald-50/90 p-3 text-sm text-emerald-950 shadow-sm dark:border-emerald-500/30 dark:bg-emerald-950/50 dark:text-emerald-100"
        >
          Loop complete for cycle {event.cycle_n}. Next action: {event.next_action}
        </div>
      );
    }

    return null;
  };

  // ui_render events are re-emitted "current state" snapshots (e.g. the
  // backend resends the full LinkedIn post grid / channel picker / variant
  // grid every time outreach re-runs) rather than incremental deltas -- so
  // rendering every historical instance just stacks up duplicates of the
  // same card. Keep only the latest instance of each ui_render component;
  // node_started/signal_found/warning/loop_complete stay as a true log.
  const lastUiRenderIndexByComponent = new Map<string, number>();
  events.forEach((event, index) => {
    if (event.type === 'ui_render') {
      lastUiRenderIndexByComponent.set(event.component, index);
    }
  });
  const visibleEvents = events.filter(
    (event, index) => event.type !== 'ui_render' || lastUiRenderIndexByComponent.get(event.component) === index,
  );

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-4 md:p-6">
      <header className="rounded-2xl border border-slate-200/70 bg-white/75 p-5 shadow-lg shadow-slate-200/40 backdrop-blur dark:border-slate-800 dark:bg-slate-950/65 dark:shadow-none">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-indigo-600 dark:text-indigo-300">
              Revenue Intelligence Workspace
            </p>
            <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-50 md:text-3xl">
              Signal → Action Command Center
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-600 dark:text-slate-300">
              Run the market loop, compare variants, and capture performance learnings cycle by cycle.
            </p>
          </div>
          <div className="inline-flex h-fit items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs shadow-sm dark:border-slate-700 dark:bg-slate-900">
            <span className="font-medium text-slate-500 dark:text-slate-300">Status</span>
            <span
              className={`rounded-full px-2 py-0.5 font-semibold capitalize ${
                status === 'running'
                  ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/60 dark:text-emerald-200'
                  : status === 'error'
                    ? 'bg-red-100 text-red-700 dark:bg-red-900/60 dark:text-red-200'
                    : status === 'done'
                      ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/60 dark:text-indigo-200'
                      : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200'
              }`}
            >
              {status}
            </span>
          </div>
        </div>

        <div className="mt-4 flex flex-col gap-2 md:flex-row">
          <input
            className="w-full rounded-xl border border-slate-300 bg-white/90 px-4 py-2.5 text-sm shadow-inner outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 md:w-56 dark:border-slate-700 dark:bg-slate-900/90 dark:focus:border-indigo-400 dark:focus:ring-indigo-900"
            value={productName}
            onChange={(e) => setProductName(e.target.value)}
            placeholder="Product name (any product, not just Lilian)"
            title="The loop generalises to any product -- change this to run it against something else"
          />
          <input
            className="flex-1 rounded-xl border border-slate-300 bg-white/90 px-4 py-2.5 text-sm shadow-inner outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 dark:border-slate-700 dark:bg-slate-900/90 dark:focus:border-indigo-400 dark:focus:ring-indigo-900"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Ask a research/generate/feedback question..."
          />
          <button
            type="button"
            onClick={startLoop}
            disabled={starting || status === 'running'}
            className="rounded-xl bg-linear-to-r from-indigo-600 to-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/25 transition hover:from-indigo-500 hover:to-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {starting ? 'Starting…' : 'Start Loop'}
          </button>
          <button
            type="button"
            onClick={stopLoop}
            disabled={status !== 'running'}
            className="rounded-xl border border-slate-300 bg-white/90 px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            Stop
          </button>
          <button
            type="button"
            onClick={newThread}
            title="Start a brand-new thread (clears the saved thread id)"
            className="rounded-xl border border-slate-300 bg-white/90 px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            {justCleared ? 'Cleared ✓' : 'New Thread'}
          </button>
        </div>

        <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
          Thread: <code className="rounded bg-slate-100 px-1.5 py-0.5 dark:bg-slate-800">{threadId || 'initializing...'}</code> • Events: {events.length} • Cycles logged: {timeline.length}
        </p>

        {notice && (
          <div className="mt-3 rounded-lg border border-indigo-200 bg-indigo-50/90 px-3 py-2 text-xs font-medium text-indigo-800 shadow-sm dark:border-indigo-500/30 dark:bg-indigo-950/40 dark:text-indigo-200">
            {notice}
          </div>
        )}
      </header>

      <div className="grid gap-5 lg:grid-cols-[1.8fr_1fr]">
        <section className="space-y-4 rounded-2xl border border-slate-200/70 bg-white/70 p-4 shadow-lg shadow-slate-200/40 backdrop-blur dark:border-slate-800 dark:bg-slate-950/60 dark:shadow-none">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">Execution Feed</h2>
            <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
              Live SSE
            </span>
          </div>

          {events.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50/80 p-6 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-400">
              No runtime events yet. Start the loop to stream research, variant generation, and feedback actions.
            </div>
          ) : (
            <div className="space-y-3">{visibleEvents.map((event, i) => renderEvent(event, i))}</div>
          )}
        </section>

        <CampaignTimeline entries={timeline} />
      </div>

      <details className="group rounded-2xl border border-slate-200/70 bg-white/75 p-4 shadow-lg shadow-slate-200/40 backdrop-blur dark:border-slate-800 dark:bg-slate-950/65 dark:shadow-none">
        <summary className="flex cursor-pointer list-none items-center justify-between text-lg font-semibold text-slate-900 dark:text-slate-100">
          <span>
            Developer Log
            <span className="ml-2 align-middle text-xs font-medium text-slate-400 dark:text-slate-500">({rawEvents.length} raw events)</span>
          </span>
          <span className="text-xs font-medium text-indigo-600 group-open:hidden dark:text-indigo-300">Show ▸</span>
          <span className="hidden text-xs font-medium text-indigo-600 group-open:inline dark:text-indigo-300">Hide ▾</span>
        </summary>
        <div className="mt-3 max-h-80 overflow-y-auto rounded-xl border border-slate-800 bg-slate-950 p-3 font-mono text-xs text-slate-100 shadow-inner">
          {rawEvents.map((event, index) => (
            <pre key={`${event}-${index}`} className="whitespace-pre-wrap wrap-break-word border-b border-slate-800/80 py-2">
              {event}
            </pre>
          ))}
          {rawEvents.length === 0 && <p className="text-slate-400">No events yet. Start the loop.</p>}
        </div>
      </details>
    </main>
  );
}
