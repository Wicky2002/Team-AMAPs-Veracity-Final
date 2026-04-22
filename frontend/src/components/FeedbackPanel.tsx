'use client';

import { useState } from 'react';
import type { FeedbackMetric } from '@/lib/loop-types';

type Props = {
  metrics: FeedbackMetric[];
  onFeedback: () => void;
};

export function FeedbackPanel({ metrics, onFeedback }: Props) {
  const [showConfirm, setShowConfirm] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const winner = metrics.length > 0
    ? metrics.reduce((a, b) => (a.reply_rate > b.reply_rate ? a : b))
    : null;

  const handleConfirm = () => {
    setSubmitted(true);
    onFeedback();
  };

  return (
    <section className="panel overflow-hidden anim-in">
      <div className="px-5 py-3 border-b border-[var(--border-subtle)] bg-[var(--bg-surface)] flex items-center justify-between">
        <h2 className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-widest">
          Campaign Performance
        </h2>
        {winner && (
          <span className="text-[10px] font-mono text-[var(--success)] bg-[var(--success-soft)] px-2 py-0.5 rounded">
            Winner: Variant {String.fromCharCode(65 + winner.variant)}
          </span>
        )}
      </div>

      <div className="p-4 space-y-3">
        {metrics.map((m) => {
          const isWinner = winner?.variant === m.variant;
          const label = String.fromCharCode(65 + m.variant);

          return (
            <article
              key={m.variant}
              className={`rounded-lg border p-4 ${
                isWinner
                  ? 'border-[var(--success)] bg-[var(--success-soft)]'
                  : 'border-[var(--border-subtle)] bg-[var(--bg-base)]'
              }`}
            >
              <div className="flex items-center justify-between mb-3">
                <span className={`text-xs font-bold ${isWinner ? 'text-[var(--success)]' : 'text-[var(--text-secondary)]'}`}>
                  Variant {label} {isWinner && '★'}
                </span>
              </div>

              <div className="space-y-2.5">
                {[
                  { label: 'Open Rate', value: m.open_rate, color: 'bg-[var(--accent)]' },
                  { label: 'Reply Rate', value: m.reply_rate, color: 'bg-[var(--success)]' },
                  { label: 'Click Rate', value: m.click_rate, color: 'bg-[var(--warning)]' },
                ].map((bar) => (
                  <div key={bar.label}>
                    <div className="flex justify-between text-[11px] mb-1">
                      <span className="text-[var(--text-muted)]">{bar.label}</span>
                      <span className="font-mono text-[var(--text-secondary)]">{(bar.value * 100).toFixed(1)}%</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-[var(--bg-elevated)] overflow-hidden">
                      <div
                        className={`h-full rounded-full ${bar.color} transition-all duration-700`}
                        style={{ width: `${Math.min(100, bar.value * 400)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </article>
          );
        })}
      </div>

      {/* Manual feedback trigger — not automatic */}
      <div className="px-4 pb-4">
        {submitted ? (
          <div className="w-full rounded-lg bg-[var(--success-soft)] border border-[var(--success)] text-center text-[var(--success)] text-sm font-semibold py-3">
            ✓ Feedback submitted — next cycle starting
          </div>
        ) : !showConfirm ? (
          <button
            type="button"
            onClick={() => setShowConfirm(true)}
            className="w-full rounded-lg bg-[var(--bg-elevated)] border border-[var(--border-subtle)] text-[var(--text-secondary)] text-sm font-semibold py-3 hover:bg-[var(--accent)] hover:text-[var(--bg-base)] hover:border-[var(--accent)] transition-all cursor-pointer"
          >
            Feed Results Back → Next Cycle
          </button>
        ) : (
          <div className="space-y-2 anim-in">
            <p className="text-xs text-[var(--text-secondary)] text-center">
              This will start a new research cycle using these results. Continue?
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setShowConfirm(false)}
                className="flex-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] text-[var(--text-secondary)] text-sm font-semibold py-2.5 hover:bg-[var(--bg-surface-hover)] transition-all cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirm}
                className="flex-1 rounded-lg bg-[var(--success)] text-[var(--bg-base)] text-sm font-semibold py-2.5 hover:brightness-110 transition-all cursor-pointer"
              >
                Confirm & Start
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
