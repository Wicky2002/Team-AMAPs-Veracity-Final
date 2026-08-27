'use client';

import { useState } from 'react';

import type { OutreachVariant } from '@/lib/loop-types';

type Props = {
  variants: OutreachVariant[];
  onDeploy: (variant: OutreachVariant) => Promise<void> | void;
};

const SOURCE_TYPE_CLASSES: Record<string, string> = {
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
};

export function ABVariantGrid({ variants, onDeploy }: Props) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [deployingKey, setDeployingKey] = useState<string | null>(null);

  return (
    <section className="rounded-2xl border border-slate-200/70 bg-white/80 p-4 shadow-lg shadow-slate-200/40 backdrop-blur dark:border-slate-800 dark:bg-slate-950/65 dark:shadow-none">
      <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">A/B Variant Comparison</h2>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
        Pick the strongest narrative and push to outreach.
      </p>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {variants.map((variant, index) => {
          const key = `${variant.hypothesis}-${index}`;
          const isExpanded = expandedKey === key;
          const sourceCount = variant.provenance_chain?.length ?? 0;

          return (
            <article
              key={key}
              className="rounded-xl border border-slate-200 bg-white/95 p-4 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md dark:border-slate-800 dark:bg-slate-900/70"
            >
              <div className="flex items-center justify-between">
                <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-300">
                  Variant {String.fromCharCode(65 + index)}
                </div>
                <span className="rounded-full border border-indigo-300 bg-indigo-50 px-2 py-0.5 text-[10px] font-semibold text-indigo-700 dark:border-indigo-500/40 dark:bg-indigo-900/40 dark:text-indigo-200">
                  Candidate
                </span>
              </div>

              {variant.image_url && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={
                    variant.image_url.startsWith('data:')
                      ? variant.image_url
                      : `/api/image-proxy?url=${encodeURIComponent(variant.image_url)}`
                  }
                  alt={`Generated visual for ${variant.subject_line}`}
                  className="mt-3 h-32 w-full rounded-lg border border-slate-200 object-cover dark:border-slate-800"
                  loading="lazy"
                  onError={(event) => {
                    event.currentTarget.style.display = 'none';
                  }}
                />
              )}

              <h3 className="mt-2 text-base font-semibold text-slate-900 dark:text-slate-100">{variant.subject_line}</h3>
              <p className="mt-2 text-sm text-slate-700 dark:text-slate-200">{variant.hook}</p>
              <p className="mt-2 text-sm text-slate-700 dark:text-slate-200">
                <span className="font-semibold">CTA:</span> {variant.cta}
              </p>
              <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">Hypothesis: {variant.hypothesis}</p>

              {sourceCount > 0 && (
                <button
                  type="button"
                  onClick={() => setExpandedKey(isExpanded ? null : key)}
                  className="mt-3 flex items-center gap-1 text-xs font-semibold text-indigo-600 transition hover:text-indigo-500 dark:text-indigo-300 dark:hover:text-indigo-200"
                >
                  📎 {isExpanded ? 'Hide' : 'Show'} sources ({sourceCount})
                </button>
              )}

              {isExpanded && (
                <div className="mt-2 space-y-2 border-l-2 border-indigo-200 pl-3 dark:border-indigo-500/30">
                  {variant.provenance_chain.map((signal, sigIdx) => {
                    const confidencePct = Math.max(0, Math.min(100, signal.confidence * 100));
                    const type = signal.source_type ?? 'audience';
                    return (
                      <div key={`${signal.source}-${sigIdx}`} className="text-xs">
                        <div className="flex items-center gap-1.5">
                          <span
                            className={`rounded-full border px-1.5 py-0.5 text-[9px] font-semibold ${SOURCE_TYPE_CLASSES[type] ?? SOURCE_TYPE_CLASSES.audience}`}
                          >
                            {type}
                          </span>
                          <span className="font-semibold text-slate-600 dark:text-slate-300">{signal.source}</span>
                        </div>
                        <p className="mt-1 text-slate-600 dark:text-slate-300">&ldquo;{signal.quote}&rdquo;</p>
                        <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                          <div
                            className="h-1 rounded-full bg-linear-to-r from-indigo-500 to-blue-500"
                            style={{ width: `${confidencePct}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              <button
                className="mt-4 rounded-lg bg-linear-to-r from-slate-900 to-indigo-700 px-3 py-2 text-sm font-semibold text-white shadow-md transition hover:from-slate-800 hover:to-indigo-600 disabled:cursor-not-allowed disabled:opacity-60 dark:from-indigo-600 dark:to-blue-600"
                disabled={deployingKey === key}
                onClick={async () => {
                  setDeployingKey(key);
                  try {
                    await onDeploy(variant);
                  } finally {
                    setDeployingKey(null);
                  }
                }}
                type="button"
              >
                {deployingKey === key ? 'Deploying…' : 'Deploy This Variant'}
              </button>
            </article>
          );
        })}
      </div>
    </section>
  );
}
