import type { FeedbackMetric } from '@/lib/loop-types';

type Props = {
  metrics: FeedbackMetric[];
  onFeedBack: () => void;
};

export function FeedbackPanel({ metrics, onFeedBack }: Props) {
  return (
    <section className="rounded-xl border border-zinc-200 p-4 shadow-sm">
      <h2 className="text-lg font-semibold">Feedback Ingestion Panel</h2>
      <div className="mt-3 space-y-3">
        {metrics.map((m) => (
          <article key={m.variant} className="rounded-lg border border-zinc-200 p-3 text-sm">
            <p className="font-medium">Variant {String.fromCharCode(65 + m.variant)}</p>
            <p>Open Rate: {(m.open_rate * 100).toFixed(1)}%</p>
            <p>Reply Rate: {(m.reply_rate * 100).toFixed(1)}%</p>
            <p>Click Rate: {(m.click_rate * 100).toFixed(1)}%</p>
          </article>
        ))}
      </div>
      <button
        type="button"
        onClick={onFeedBack}
        className="mt-3 rounded-md bg-emerald-600 px-3 py-1.5 text-sm text-white hover:bg-emerald-700"
      >
        Feed Results Back →
      </button>
    </section>
  );
}
