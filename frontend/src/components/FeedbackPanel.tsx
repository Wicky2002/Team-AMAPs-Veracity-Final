import type { FeedbackMetric } from '@/lib/loop-types';

type Props = {
  metrics: FeedbackMetric[];
  onFeedback: () => void;
};

export function FeedbackPanel({ metrics, onFeedback }: Props) {
  const winner = metrics.length > 0
    ? metrics.reduce((a, b) => (a.reply_rate > b.reply_rate ? a : b))
    : null;

  return (
    <section className="panel rounded-xl overflow-hidden anim-in">
      <div className="px-5 py-3 border-b border-white/5 bg-white/[0.02] flex items-center justify-between">
        <h2 className="text-xs font-semibold text-neutral-300 uppercase tracking-widest">
          Campaign Performance
        </h2>
        {winner && (
          <span className="text-[10px] font-mono text-emerald-400 bg-emerald-400/10 px-2 py-0.5 rounded">
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
              className={`rounded-lg border p-4 transition-colors ${
                isWinner
                  ? 'border-emerald-500/30 bg-emerald-500/[0.04]'
                  : 'border-white/5 bg-white/[0.02]'
              }`}
            >
              <div className="flex items-center justify-between mb-3">
                <span className={`text-xs font-bold ${isWinner ? 'text-emerald-400' : 'text-neutral-400'}`}>
                  Variant {label} {isWinner && '★'}
                </span>
              </div>

              {/* Metric bars */}
              <div className="space-y-2.5">
                {[
                  { label: 'Open Rate', value: m.open_rate, color: 'bg-blue-500' },
                  { label: 'Reply Rate', value: m.reply_rate, color: 'bg-emerald-500' },
                  { label: 'Click Rate', value: m.click_rate, color: 'bg-amber-500' },
                ].map((bar) => (
                  <div key={bar.label}>
                    <div className="flex justify-between text-[11px] mb-1">
                      <span className="text-neutral-500">{bar.label}</span>
                      <span className="font-mono text-neutral-300">{(bar.value * 100).toFixed(1)}%</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
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

      <div className="px-4 pb-4">
        <button
          type="button"
          onClick={onFeedback}
          className="w-full rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold py-3 transition-colors"
        >
          Feed Results Back → Next Cycle
        </button>
      </div>
    </section>
  );
}
