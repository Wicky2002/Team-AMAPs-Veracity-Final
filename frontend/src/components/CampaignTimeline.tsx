import type { TimelineEntry } from '@/lib/loop-types';

type Props = {
  entries: TimelineEntry[];
};

export function CampaignTimeline({ entries }: Props) {
  return (
    <aside className="rounded-xl border border-zinc-200 p-4 shadow-sm">
      <h2 className="text-lg font-semibold">Campaign Timeline</h2>
      <ol className="mt-3 space-y-2 text-sm">
        {entries.map((entry, idx) => (
          <li key={`${entry.cycle_n}-${entry.timestamp}-${idx}`} className="rounded-md border border-zinc-200 p-2">
            <div className="text-xs uppercase text-zinc-500">Cycle {entry.cycle_n}</div>
            <p className="mt-1">
              <span className="font-medium">Winner:</span> {entry.winning_variant}
            </p>
            <p className="text-xs text-zinc-600">Top signal: {entry.top_signal}</p>
            <p className="text-xs text-zinc-600">
              Open {(entry.open_rate * 100).toFixed(1)}% · Reply {(entry.reply_rate * 100).toFixed(1)}%
            </p>
            <p className="mt-1 text-xs text-zinc-500">{new Date(entry.timestamp).toLocaleString()}</p>
          </li>
        ))}
      </ol>
    </aside>
  );
}
