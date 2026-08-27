'use client';

import { useState } from 'react';

import type { SignalReference } from '@/lib/loop-types';

type Props = {
  signals: SignalReference[];
  onDrill?: (signal: SignalReference) => Promise<void> | void;
};

export function SignalIntelligenceBoard({ signals, onDrill }: Props) {
  const [drillingKey, setDrillingKey] = useState<string | null>(null);

  const sourceTypeClasses: Record<string, string> = {
    competitor:
      'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-500/40 dark:bg-rose-900/30 dark:text-rose-200',
    audience:
      'border-indigo-300 bg-indigo-50 text-indigo-700 dark:border-indigo-500/40 dark:bg-indigo-900/30 dark:text-indigo-200',
    pestel:
      'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-500/40 dark:bg-emerald-900/30 dark:text-emerald-200',
    adjacent:
      'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-500/40 dark:bg-amber-900/30 dark:text-amber-200',
    temporal:
      'border-cyan-300 bg-cyan-50 text-cyan-700 dark:border-cyan-500/40 dark:bg-cyan-900/30 dark:text-cyan-200',
    channel:
      'border-violet-300 bg-violet-50 text-violet-700 dark:border-violet-500/40 dark:bg-violet-900/30 dark:text-violet-200',
  };

  return (
    <section className="rounded-2xl border border-slate-200/70 bg-white/80 p-4 shadow-lg shadow-slate-200/40 backdrop-blur dark:border-slate-800 dark:bg-slate-950/65 dark:shadow-none">
      <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Signal Intelligence Board</h2>
      <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Live market findings with confidence scoring.</p>

      {signals.length === 0 ? (
        <div className="mt-4 rounded-xl border border-dashed border-slate-300 bg-slate-50/80 p-4 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-400">
          No validated signals yet.
        </div>
      ) : (
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {signals.map((signal, idx) => {
            const confidencePct = Math.max(0, Math.min(100, signal.confidence * 100));
            const type = signal.source_type ?? 'audience';
            const key = `${signal.source}-${idx}`;
            const isDrilling = drillingKey === key;

            return (
              <article
                key={key}
                className="rounded-xl border border-slate-200 bg-white/95 p-3 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md dark:border-slate-800 dark:bg-slate-900/70"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-300">
                    {signal.source}
                  </div>
                  <div className="flex items-center gap-1">
                    {signal.credibility_tier === 'high' && (
                      <span
                        title="Verified high-credibility source"
                        className="rounded-full border border-yellow-400 bg-yellow-50 px-1.5 py-0.5 text-[9px] font-bold text-yellow-700 dark:border-yellow-500/40 dark:bg-yellow-900/30 dark:text-yellow-300"
                      >
                        ★ verified
                      </span>
                    )}
                    {signal.credibility_tier === 'mid' && (
                      <span
                        title="Identifiable, verifiable source (community/social)"
                        className="rounded-full border border-sky-400 bg-sky-50 px-1.5 py-0.5 text-[9px] font-bold text-sky-700 dark:border-sky-500/40 dark:bg-sky-900/30 dark:text-sky-300"
                      >
                        ◇ sourced
                      </span>
                    )}
                    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${sourceTypeClasses[type]}`}>
                      {type}
                    </span>
                  </div>
                </div>

                <p className="mt-1 text-sm leading-relaxed text-slate-700 dark:text-slate-200">{signal.quote}</p>

                <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                  <div
                    className="h-2 rounded-full bg-linear-to-r from-indigo-500 to-blue-500"
                    style={{ width: `${confidencePct}%` }}
                  />
                </div>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Confidence: {confidencePct.toFixed(0)}%</p>

                {onDrill && (
                  <button
                    type="button"
                    disabled={isDrilling}
                    onClick={async () => {
                      setDrillingKey(key);
                      try {
                        await onDrill(signal);
                      } finally {
                        setDrillingKey(null);
                      }
                    }}
                    className="mt-2 text-xs font-semibold text-indigo-600 transition hover:text-indigo-500 disabled:opacity-50 dark:text-indigo-300 dark:hover:text-indigo-200"
                  >
                    {isDrilling ? 'Investigating…' : 'Investigate further →'}
                  </button>
                )}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
