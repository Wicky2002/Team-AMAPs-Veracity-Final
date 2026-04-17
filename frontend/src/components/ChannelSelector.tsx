'use client';
// components/ChannelSelector.tsx
import { useState } from 'react';
import { ChannelSelectResponse, selectChannel } from '@/lib/api';
import { Mail, Link2, Rocket, ArrowRight } from 'lucide-react';

interface Props {
  data: ChannelSelectResponse;
  onSelected?: (channel: string) => void;
}

export default function ChannelSelector({ data, onSelected }: Props) {
  const [selected, setSelected] = useState<string | null>(null);

  async function handleSelect(channel: string) {
    if (selected) return;
    setSelected(channel);
    try {
      await selectChannel(channel);
      onSelected?.(channel);
    } catch {}
  }

  const getIcon = (ch: string) => {
    if (ch.toLowerCase().includes('email')) return <Mail size={20} />;
    if (ch.toLowerCase().includes('linkedin')) return <Link2 size={20} />;
    return <Rocket size={20} />;
  }

  return (
    <div className="panel rounded-xl overflow-hidden w-full max-w-2xl mt-2 animate-in">
      <div className="px-5 py-3 border-b border-white/5 bg-white/[0.02] flex items-center justify-between">
        <h3 className="text-xs font-semibold text-neutral-300 uppercase tracking-widest">Select Deployment Channel</h3>
      </div>
      
      <div className="p-4 flex flex-col gap-2">
        {data.options.map((channel) => {
          const isSelected = selected === channel;
          const isDimmed = selected && !isSelected;

          return (
            <button
              key={channel}
              onClick={() => handleSelect(channel)}
              disabled={!!selected}
              className={`flex items-center justify-between p-4 rounded-lg border transition-all duration-300 group
                ${isSelected ? 'border-white bg-white/[0.05]' : isDimmed ? 'border-white/5 opacity-40' : 'border-white/5 bg-[#141414] hover:bg-[#1A1A1A] hover:border-white/20'}
              `}
            >
              <div className="flex items-center gap-4">
                <div className={`p-2 rounded-md ${isSelected ? 'bg-white text-black' : 'bg-neutral-800 text-neutral-400 group-hover:text-white'}`}>
                  {getIcon(channel)}
                </div>
                <div className="flex flex-col items-start">
                  <span className={`text-sm font-semibold ${isSelected ? 'text-white' : 'text-neutral-300'}`}>{channel}</span>
                </div>
              </div>
              
              {!selected ? (
                <ArrowRight size={16} className="text-neutral-600 opacity-0 group-hover:opacity-100 group-hover:-translate-x-1 transition-all" />
              ) : isSelected ? (
                <span className="text-[10px] uppercase font-bold text-emerald-400">Deployed</span>
              ) : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}
