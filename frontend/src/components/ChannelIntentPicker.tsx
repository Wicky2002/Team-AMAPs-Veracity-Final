type Channel = 'LinkedIn' | 'Email' | 'Both';

type Props = {
  selected?: string;
  onSelect: (channel: Channel) => void;
};

const CHANNELS: Channel[] = ['LinkedIn', 'Email', 'Both'];

export function ChannelIntentPicker({ selected, onSelect }: Props) {
  return (
    <section className="rounded-xl border border-zinc-200 p-4 shadow-sm">
      <h2 className="text-lg font-semibold">Channel Intent Picker</h2>
      <div className="mt-3 flex flex-wrap gap-2">
        {CHANNELS.map((channel) => (
          <button
            key={channel}
            type="button"
            onClick={() => onSelect(channel)}
            className={`rounded-md border px-3 py-1.5 text-sm ${
              selected === channel
                ? 'border-black bg-black text-white'
                : 'border-zinc-300 bg-white text-zinc-800 hover:bg-zinc-50'
            }`}
          >
            {channel}
          </button>
        ))}
      </div>
    </section>
  );
}
