import type { SignalReference } from '@/lib/loop-types';

type Props = {
  signals: SignalReference[];
};

const badgeClass = (type?: string) => {
  if (type === 'competitor') return 'badge-competitor';
  if (type === 'audience') return 'badge-audience';
  if (type === 'pestel') return 'badge-pestel';
  return 'bg-white/5 text-neutral-400';
};

export function SignalIntelligenceBoard({ signals }: Props) {
  return (
    <section className="panel rounded-xl overflow-hidden anim-in">
      <div className="px-5 py-3 border-b border-white/5 bg-white/[0.02] flex items-center justify-between">
        <h2 className="text-xs font-semibold text-neutral-300 uppercase tracking-widest">
          Signal Intelligence Board
        </h2>
        <span className="text-[10px] font-mono text-emerald-400 bg-emerald-400/10 px-2 py-0.5 rounded">
          {signals.length} signals
        </span>
      </div>

      <div className="p-4 grid gap-3 sm:grid-cols-2">
        {signals.map((signal, idx) => (
          <article
            key={`${signal.source}-${idx}`}
            className="rounded-lg border border-white/5 bg-white/[0.02] p-4 hover:border-white/10 transition-colors anim-in"
            style={{ animationDelay: `${idx * 60}ms` }}
          >
            {/* Source badge */}
            <div className="flex items-center justify-between mb-3">
              <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded ${badgeClass(signal.source_type)}`}>
                {signal.source_type ?? signal.source}
              </span>
              {signal.source_url && (
                <a
                  href={signal.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[10px] text-neutral-500 hover:text-white transition-colors truncate max-w-[120px]"
                >
                  {signal.source}
                </a>
              )}
            </div>

            {/* Quote */}
            <p className="text-sm text-neutral-200 leading-relaxed mb-3">
              {signal.quote}
            </p>

            {/* Confidence bar */}
            <div className="flex items-center gap-3">
              <div className="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden">
                <div
                  className="h-full rounded-full bar-gradient transition-all duration-700"
                  style={{ width: `${Math.max(0, Math.min(100, signal.confidence * 100))}%` }}
                />
              </div>
              <span className="text-[11px] font-mono text-neutral-500 shrink-0">
                {(signal.confidence * 100).toFixed(0)}%
              </span>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
