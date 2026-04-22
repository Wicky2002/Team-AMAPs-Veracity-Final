'use client';

import { useState } from 'react';

type Channel = 'LinkedIn' | 'Email' | 'Both';

type Props = {
  selected?: string;
  onSelect: (channel: Channel) => void;
};

const CHANNELS: { id: Channel; label: string; desc: string; icon: string }[] = [
  { id: 'LinkedIn', label: 'LinkedIn', desc: 'Direct outreach via LinkedIn InMail & connection notes', icon: '🔗' },
  { id: 'Email', label: 'Email', desc: 'Personalized cold email sequences with follow-ups', icon: '✉️' },
  { id: 'Both', label: 'Multi-Channel', desc: 'Coordinated LinkedIn + Email cadence for maximum coverage', icon: '🚀' },
];

export function ChannelIntentPicker({ selected: initialSelected, onSelect }: Props) {
  const [picked, setPicked] = useState<string | null>(initialSelected ?? null);

  const handlePick = (channel: Channel) => {
    if (picked) return;
    setPicked(channel);
    onSelect(channel);
  };

  return (
    <section className="panel rounded-xl overflow-hidden anim-in">
      <div className="px-5 py-3 border-b border-white/5 bg-white/[0.02]">
        <h2 className="text-xs font-semibold text-neutral-300 uppercase tracking-widest">
          Select Deployment Channel
        </h2>
      </div>

      <div className="p-4 flex flex-col gap-2">
        {CHANNELS.map((ch) => {
          const isActive = picked === ch.id;
          const isDimmed = picked !== null && !isActive;

          return (
            <button
              key={ch.id}
              type="button"
              onClick={() => handlePick(ch.id)}
              disabled={!!picked}
              className={`
                flex items-center gap-4 p-4 rounded-lg border text-left transition-all duration-200 group
                ${isActive
                  ? 'border-emerald-500/40 bg-emerald-500/[0.06]'
                  : isDimmed
                    ? 'border-white/5 opacity-35 cursor-default'
                    : 'border-white/5 bg-[#131313] hover:bg-[#1A1A1A] hover:border-white/15'}
              `}
            >
              <div className={`text-xl w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${
                isActive ? 'bg-emerald-500/20' : 'bg-white/[0.04] group-hover:bg-white/[0.08]'
              }`}>
                {ch.icon}
              </div>
              <div className="flex-1 min-w-0">
                <p className={`text-sm font-semibold ${isActive ? 'text-emerald-300' : 'text-neutral-200'}`}>
                  {ch.label}
                </p>
                <p className="text-xs text-neutral-500 mt-0.5">{ch.desc}</p>
              </div>
              {isActive && (
                <span className="text-[10px] font-mono font-bold text-emerald-400 shrink-0">SELECTED</span>
              )}
            </button>
          );
        })}
      </div>
    </section>
  );
}
