'use client';

import { useState } from 'react';

import type { EmailStatus, FeedbackMetric } from '@/lib/loop-types';

type Props = {
  metrics: FeedbackMetric[];
  onFeedback: () => Promise<void> | void;
  onRefresh?: () => Promise<void> | void;
  emailStatuses?: EmailStatus[];
  onRefreshEmail?: () => Promise<void> | void;
};

type PendingAction = 'reactions' | 'email' | 'feedback' | null;

export function FeedbackPanel({ metrics, onFeedback, onRefresh, emailStatuses = [], onRefreshEmail }: Props) {
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);
  const winner = metrics.length > 0 ? metrics.reduce((a, b) => (a.reply_rate > b.reply_rate ? a : b)) : null;

  const metricBar = (value: number) => `${Math.max(0, Math.min(100, value * 100))}%`;

  const runAction = async (action: Exclude<PendingAction, null>, handler: () => Promise<void> | void) => {
    setPendingAction(action);
    try {
      await handler();
    } finally {
      setPendingAction(null);
    }
  };

  return (
    <section className="rounded-2xl border border-slate-200/70 bg-white/80 p-4 shadow-lg shadow-slate-200/40 backdrop-blur dark:border-slate-800 dark:bg-slate-950/65 dark:shadow-none">
      <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Feedback Ingestion Panel</h2>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
        Capture outcome metrics and close the loop for the next cycle.
      </p>

      <div className="mt-3 space-y-3">
        {metrics.map((m) => {
          const isWinner = winner?.variant === m.variant;

          return (
            <article
              key={m.variant}
              className={`rounded-xl border p-3 text-sm shadow-sm ${
                isWinner
                  ? 'border-emerald-300 bg-emerald-50/80 dark:border-emerald-500/40 dark:bg-emerald-900/30'
                  : 'border-slate-200 bg-white/95 dark:border-slate-800 dark:bg-slate-900/70'
              }`}
            >
              <div className="flex items-center justify-between">
                <p className="font-semibold text-slate-800 dark:text-slate-100">Variant {String.fromCharCode(65 + m.variant)}</p>
                {isWinner && (
                  <span className="rounded-full border border-emerald-300 bg-emerald-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-emerald-700 dark:border-emerald-500/40 dark:bg-emerald-900/50 dark:text-emerald-200">
                    Current Winner
                  </span>
                )}
              </div>

              <div className="mt-2 space-y-1.5 text-xs text-slate-600 dark:text-slate-300">
                <p>Open Rate: {(m.open_rate * 100).toFixed(1)}%</p>
                <div className="h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                  <div className="h-full rounded-full bg-blue-500" style={{ width: metricBar(m.open_rate) }} />
                </div>

                <p>Reply Rate: {(m.reply_rate * 100).toFixed(1)}%</p>
                <div className="h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                  <div className="h-full rounded-full bg-emerald-500" style={{ width: metricBar(m.reply_rate) }} />
                </div>

                <p>Click Rate: {(m.click_rate * 100).toFixed(1)}%</p>
                <div className="h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                  <div className="h-full rounded-full bg-violet-500" style={{ width: metricBar(m.click_rate) }} />
                </div>
              </div>
            </article>
          );
        })}
      </div>

      {emailStatuses.length > 0 && (
        <div className="mt-4 space-y-1 rounded-xl border border-slate-200 bg-slate-50/80 p-3 text-xs dark:border-slate-800 dark:bg-slate-900/50">
          <p className="font-semibold text-slate-700 dark:text-slate-200">Email Delivery</p>
          {emailStatuses.map((e) => (
            <p key={e.email_id} className="text-slate-600 dark:text-slate-300">
              Variant {String.fromCharCode(65 + e.variant)}: {e.status}
            </p>
          ))}
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        {onRefresh && (
          <button
            type="button"
            disabled={pendingAction !== null}
            onClick={() => void runAction('reactions', onRefresh)}
            className="rounded-lg border border-slate-300 bg-white/90 px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            {pendingAction === 'reactions' ? 'Refreshing…' : '↻ Refresh Reactions'}
          </button>
        )}
        {onRefreshEmail && (
          <button
            type="button"
            disabled={pendingAction !== null}
            onClick={() => void runAction('email', onRefreshEmail)}
            className="rounded-lg border border-slate-300 bg-white/90 px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            {pendingAction === 'email' ? 'Refreshing…' : '↻ Refresh Email Status'}
          </button>
        )}
        <button
          type="button"
          disabled={pendingAction !== null}
          onClick={() => void runAction('feedback', onFeedback)}
          className="rounded-lg bg-linear-to-r from-emerald-600 to-teal-600 px-4 py-2 text-sm font-semibold text-white shadow-md transition hover:from-emerald-500 hover:to-teal-500 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {pendingAction === 'feedback' ? 'Sending Feedback…' : 'Feed Results Back →'}
        </button>
      </div>
    </section>
  );
}
