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
          <li key={`${entry.stage}-${entry.at}-${idx}`} className="rounded-md border border-zinc-200 p-2">
            <div className="text-xs uppercase text-zinc-500">{entry.stage}</div>
            <p>{entry.summary}</p>
            <p className="mt-1 text-xs text-zinc-500">{new Date(entry.at).toLocaleString()}</p>
          </li>
        ))}
      </ol>
    </aside>
  );
}
