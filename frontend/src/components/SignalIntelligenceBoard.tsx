import type { SignalReference } from '@/lib/loop-types';

type Props = {
  signals: SignalReference[];
};

const badgeClass = (type?: string) => {
  if (type === 'competitor') return 'badge-competitor';
  if (type === 'audience') return 'badge-audience';
  if (type === 'pestel') return 'badge-pestel';
  return 'bg-[var(--bg-elevated)] text-[var(--text-secondary)]';
};

export function SignalIntelligenceBoard({ signals }: Props) {
  return (
    <section className="panel overflow-hidden anim-in">
      <div className="px-5 py-3 border-b border-[var(--border-subtle)] bg-[var(--bg-surface)] flex items-center justify-between">
        <h2 className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-widest">
          Signal Intelligence Board
        </h2>
        <span className="text-[10px] font-mono text-[var(--success)] bg-[var(--success-soft)] px-2 py-0.5 rounded">
          {signals.length} signals
        </span>
      </div>

      <div className="p-4 grid gap-3 sm:grid-cols-2">
        {signals.map((signal, idx) => (
          <article
            key={`${signal.source}-${idx}`}
            className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] p-4 hover:border-[var(--border-medium)] transition-colors anim-in"
            style={{ animationDelay: `${idx * 60}ms` }}
          >
            <div className="flex items-center justify-between mb-3">
              <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded ${badgeClass(signal.source_type)}`}>
                {signal.source_type ?? signal.source}
              </span>
              {signal.source_url && (
                <a
                  href={signal.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[10px] text-[var(--text-muted)] hover:text-[var(--accent)] transition-colors truncate max-w-[120px]"
                >
                  {signal.source}
                </a>
              )}
            </div>

            <p className="text-sm text-[var(--text-primary)] leading-relaxed mb-3">
              {signal.quote}
            </p>

            <div className="flex items-center gap-3">
              <div className="flex-1 h-1.5 rounded-full bg-[var(--bg-elevated)] overflow-hidden">
                <div
                  className="h-full rounded-full bar-gradient transition-all duration-700"
                  style={{ width: `${Math.max(0, Math.min(100, signal.confidence * 100))}%` }}
                />
              </div>
              <span className="text-[11px] font-mono text-[var(--text-muted)] shrink-0">
                {(signal.confidence * 100).toFixed(0)}%
              </span>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
