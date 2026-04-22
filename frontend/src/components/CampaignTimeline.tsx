import type { TimelineEntry } from '@/lib/loop-types';

type Props = {
  entries: TimelineEntry[];
};

const angleBadge = (angle: string) => {
  if (angle === 'roi') return 'bg-[var(--success-soft)] text-[var(--success)]';
  if (angle === 'social_proof') return 'bg-[var(--accent-soft)] text-[var(--accent)]';
  return 'bg-[var(--error-soft)] text-[var(--error)]';
};

const angleLabel = (angle: string) => {
  if (angle === 'roi') return 'ROI';
  if (angle === 'social_proof') return 'Social Proof';
  return 'Competitor Gap';
};

export function CampaignTimeline({ entries }: Props) {
  if (entries.length === 0) {
    return (
      <aside className="panel p-5">
        <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-widest mb-4">
          Campaign Timeline
        </h2>
        <p className="text-xs text-[var(--text-muted)]">No cycles completed yet.</p>
      </aside>
    );
  }

  return (
    <aside className="panel p-5">
      <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-widest mb-5">
        Campaign Timeline
      </h2>

      <ol className="relative space-y-0">
        {entries.map((entry, idx) => (
          <li
            key={`${entry.cycle_n}-${entry.timestamp}-${idx}`}
            className="relative pl-6 pb-6 last:pb-0"
          >
            {idx < entries.length - 1 && (
              <div className="absolute left-[7px] top-3 bottom-0 w-px bg-[var(--border-subtle)]" />
            )}
            <div className="absolute left-0 top-1 w-[15px] h-[15px] rounded-full border-2 border-[var(--success)] bg-[var(--bg-base)] flex items-center justify-center">
              <div className="w-[5px] h-[5px] rounded-full bg-[var(--success)]" />
            </div>

            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-[10px] font-mono text-[var(--text-muted)]">Cycle {entry.cycle_n}</span>
                <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${angleBadge(entry.angle)}`}>
                  {angleLabel(entry.angle)}
                </span>
              </div>
              <p className="text-xs font-medium text-[var(--text-primary)] mb-1">{entry.winning_variant}</p>
              <p className="text-[11px] text-[var(--text-muted)] leading-snug mb-1 line-clamp-2">{entry.top_signal}</p>
              <div className="flex gap-3 text-[10px] font-mono text-[var(--text-muted)]">
                <span>Open {(entry.open_rate * 100).toFixed(1)}%</span>
                <span>Reply {(entry.reply_rate * 100).toFixed(1)}%</span>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </aside>
  );
}
