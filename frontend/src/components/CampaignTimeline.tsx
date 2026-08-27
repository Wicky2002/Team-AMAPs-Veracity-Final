import { AngleLearningChart } from '@/components/AngleLearningChart';
import type { TimelineEntry } from '@/lib/loop-types';

type Props = {
  entries: TimelineEntry[];
};

export function CampaignTimeline({ entries }: Props) {
  const angleLabel = (angle: TimelineEntry['angle']) => {
    if (angle === 'roi') return 'ROI';
    if (angle === 'social_proof') return 'Social proof';
    return 'Competitor gap';
  };

  const angleColor = (angle: TimelineEntry['angle']) => {
    if (angle === 'roi') {
      return 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-500/40 dark:bg-emerald-900/30 dark:text-emerald-200';
    }
    if (angle === 'social_proof') {
      return 'border-violet-300 bg-violet-50 text-violet-700 dark:border-violet-500/40 dark:bg-violet-900/30 dark:text-violet-200';
    }
    return 'border-indigo-300 bg-indigo-50 text-indigo-700 dark:border-indigo-500/40 dark:bg-indigo-900/30 dark:text-indigo-200';
  };

  return (
    <aside className="sticky top-6 h-fit rounded-2xl border border-slate-200/70 bg-white/75 p-4 shadow-lg shadow-slate-200/40 backdrop-blur dark:border-slate-800 dark:bg-slate-950/65 dark:shadow-none">
      <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Campaign Timeline</h2>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
        Tracks what won each cycle so your next prompts and variants learn from previous performance.
      </p>

      {entries.length === 0 ? (
        <div className="mt-4 rounded-xl border border-dashed border-slate-300 bg-slate-50/80 p-4 text-xs leading-relaxed text-slate-600 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-400">
          No cycle history yet. After feedback is fed back, you’ll see winner trends, signal quality, and performance by angle.
        </div>
      ) : (
        <>
          <AngleLearningChart entries={entries} />
          <ol className="mt-4 space-y-3 text-sm">
          {entries.map((entry, idx) => (
            <li
              key={`${entry.cycle_n}-${entry.timestamp}-${idx}`}
              className="relative rounded-xl border border-slate-200 bg-white/90 p-3 shadow-sm dark:border-slate-800 dark:bg-slate-900/70"
            >
              <div className="flex items-center justify-between">
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-300">
                  Cycle {entry.cycle_n}
                </div>
                <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${angleColor(entry.angle)}`}>
                  {angleLabel(entry.angle)}
                </span>
              </div>

              <p className="mt-2 text-sm text-slate-700 dark:text-slate-200">
                <span className="font-semibold">Winner:</span> {entry.winning_variant}
              </p>
              <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">Top signal: {entry.top_signal}</p>
              <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
                Open {(entry.open_rate * 100).toFixed(1)}% · Reply {(entry.reply_rate * 100).toFixed(1)}%
              </p>
              <p className="mt-2 text-[11px] text-slate-500 dark:text-slate-400">{new Date(entry.timestamp).toLocaleString()}</p>
            </li>
          ))}
          </ol>
        </>
      )}
    </aside>
  );
}
