import type { SignalReference } from '@/lib/loop-types';

type Props = {
  signals: SignalReference[];
};

export function SignalIntelligenceBoard({ signals }: Props) {
  return (
    <section className="rounded-xl border border-zinc-200 p-4 shadow-sm">
      <h2 className="text-lg font-semibold">Signal Intelligence Board</h2>
      <p className="mt-1 text-sm text-zinc-500">Live research findings with confidence scores.</p>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {signals.map((signal, idx) => (
          <article key={`${signal.source}-${idx}`} className="rounded-lg border border-zinc-200 p-3">
            <div className="text-xs uppercase text-zinc-500">{signal.source}</div>
            <p className="mt-1 text-sm">{signal.quote}</p>
            <div className="mt-2 h-2 w-full rounded bg-zinc-100">
              <div
                className="h-2 rounded bg-blue-500"
                style={{ width: `${Math.max(0, Math.min(100, signal.confidence * 100))}%` }}
              />
            </div>
            <p className="mt-1 text-xs text-zinc-500">Confidence: {(signal.confidence * 100).toFixed(0)}%</p>
          </article>
        ))}
      </div>
    </section>
  );
}
