import type { FeedbackMetric } from '@/lib/loop-types';

type Props = {
  metrics: FeedbackMetric[];
  onFeedback: () => void;
};

export function FeedbackPanel({ metrics, onFeedback }: Props) {
  const winner = metrics.length > 0 ? metrics.reduce((a, b) => (a.reply_rate > b.reply_rate ? a : b)) : null;

  const metricBar = (value: number) => `${Math.max(0, Math.min(100, value * 100))}%`;

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
      <button
        type="button"
        onClick={onFeedback}
        className="mt-4 rounded-lg bg-gradient-to-r from-emerald-600 to-teal-600 px-4 py-2 text-sm font-semibold text-white shadow-md transition hover:from-emerald-500 hover:to-teal-500"
      >
        Feed Results Back →
      </button>
    </section>
  );
}
