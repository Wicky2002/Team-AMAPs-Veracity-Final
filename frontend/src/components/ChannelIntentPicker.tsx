'use client';

import { useState } from 'react';

type Channel = 'LinkedIn' | 'Email' | 'Both';

type Props = {
  selected?: string;
  onSelect: (channel: Channel) => Promise<void> | void;
};

const CHANNELS: Channel[] = ['LinkedIn', 'Email', 'Both'];

export function ChannelIntentPicker({ selected, onSelect }: Props) {
  const [pendingChannel, setPendingChannel] = useState<Channel | null>(null);

  return (
    <section className="rounded-2xl border border-slate-200/70 bg-white/80 p-4 shadow-lg shadow-slate-200/40 backdrop-blur dark:border-slate-800 dark:bg-slate-950/65 dark:shadow-none">
      <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Channel Intent Picker</h2>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Select the deployment channel for this cycle.</p>

      <div className="mt-3 inline-flex flex-wrap gap-2 rounded-xl border border-slate-200 bg-slate-50 p-1 dark:border-slate-800 dark:bg-slate-900">
        {CHANNELS.map((channel) => {
          const isPending = pendingChannel === channel;

          return (
            <button
              key={channel}
              type="button"
              disabled={pendingChannel !== null}
              onClick={async () => {
                setPendingChannel(channel);
                try {
                  await onSelect(channel);
                } finally {
                  setPendingChannel(null);
                }
              }}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed ${
                selected === channel
                  ? 'bg-slate-900 text-white shadow dark:bg-indigo-600'
                  : 'text-slate-700 hover:bg-white hover:shadow-sm disabled:opacity-60 dark:text-slate-200 dark:hover:bg-slate-800'
              }`}
            >
              {isPending ? 'Setting…' : channel}
            </button>
          );
        })}
      </div>
    </section>
  );
}
