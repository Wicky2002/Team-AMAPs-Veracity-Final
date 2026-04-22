import type { TimelineEntry } from '@/lib/loop-types';

type Props = {
  entries: TimelineEntry[];
};

const angleBadge = (angle: string) => {
  if (angle === 'roi') return 'bg-emerald-500/12 text-emerald-400';
  if (angle === 'social_proof') return 'bg-blue-500/12 text-blue-400';
  return 'bg-red-500/12 text-red-400'; // competitor_gap
};

const angleLabel = (angle: string) => {
  if (angle === 'roi') return 'ROI';
  if (angle === 'social_proof') return 'Social Proof';
  return 'Competitor Gap';
};

export function CampaignTimeline({ entries }: Props) {
  if (entries.length === 0) {
    return (
      <aside className="panel rounded-xl p-5">
        <h2 className="text-xs font-semibold text-neutral-400 uppercase tracking-widest mb-4">
          Campaign Timeline
        </h2>
        <p className="text-xs text-neutral-600">No cycles completed yet.</p>
      </aside>
    );
  }

  return (
    <aside className="panel rounded-xl p-5">
      <h2 className="text-xs font-semibold text-neutral-400 uppercase tracking-widest mb-5">
        Campaign Timeline
      </h2>

      <ol className="relative space-y-0">
        {entries.map((entry, idx) => (
          <li
            key={`${entry.cycle_n}-${entry.timestamp}-${idx}`}
            className="relative pl-6 pb-6 last:pb-0"
          >
            {/* Vertical line */}
            {idx < entries.length - 1 && (
              <div className="absolute left-[7px] top-3 bottom-0 w-px bg-white/8" />
            )}
            {/* Dot */}
            <div className="absolute left-0 top-1 w-[15px] h-[15px] rounded-full border-2 border-emerald-500/50 bg-[#0A0A0A] flex items-center justify-center">
              <div className="w-[5px] h-[5px] rounded-full bg-emerald-500" />
            </div>

            {/* Content */}
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-[10px] font-mono text-neutral-500">Cycle {entry.cycle_n}</span>
                <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${angleBadge(entry.angle)}`}>
                  {angleLabel(entry.angle)}
                </span>
              </div>
              <p className="text-xs font-medium text-neutral-200 mb-1">{entry.winning_variant}</p>
              <p className="text-[11px] text-neutral-500 leading-snug mb-1 line-clamp-2">{entry.top_signal}</p>
              <div className="flex gap-3 text-[10px] font-mono text-neutral-600">
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
