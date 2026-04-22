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
  const [picked, setPicked] = useState<Set<string>>(
    initialSelected ? new Set([initialSelected]) : new Set()
  );

  const handleToggle = (channelId: Channel) => {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(channelId)) {
        next.delete(channelId);
      } else {
        next.add(channelId);
      }

      // Send the resolved channel to backend
      if (next.size === 0) {
        // nothing selected — don't fire
      } else if (next.has('Both') || (next.has('LinkedIn') && next.has('Email'))) {
        onSelect('Both');
      } else if (next.has('LinkedIn')) {
        onSelect('LinkedIn');
      } else if (next.has('Email')) {
        onSelect('Email');
      }

      return next;
    });
  };

  return (
    <section className="panel overflow-hidden anim-in">
      <div className="px-5 py-3 border-b border-[var(--border-subtle)] bg-[var(--bg-surface)] flex items-center justify-between">
        <h2 className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-widest">
          Select Deployment Channels
        </h2>
        {picked.size > 0 && (
          <span className="text-[10px] font-mono text-[var(--success)]">
            {picked.size} selected
          </span>
        )}
      </div>

      <div className="p-4 flex flex-col gap-2">
        {CHANNELS.map((ch) => {
          const isActive = picked.has(ch.id);
          return (
            <button
              key={ch.id}
              type="button"
              onClick={() => handleToggle(ch.id)}
              className={`
                flex items-center gap-4 p-4 rounded-lg border text-left transition-all duration-200 group cursor-pointer
                ${isActive
                  ? 'border-[var(--success)] bg-[var(--success-soft)]'
                  : 'border-[var(--border-subtle)] bg-[var(--bg-base)] hover:bg-[var(--bg-surface-hover)] hover:border-[var(--border-medium)]'}
              `}
            >
              {/* Checkbox */}
              <div className={`w-5 h-5 rounded border-2 flex items-center justify-center shrink-0 transition-all ${
                isActive
                  ? 'border-[var(--success)] bg-[var(--success)]'
                  : 'border-[var(--border-medium)] bg-transparent group-hover:border-[var(--text-muted)]'
              }`}>
                {isActive && <span className="text-[var(--bg-base)] text-xs font-bold">✓</span>}
              </div>

              <div className={`text-xl w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${
                isActive ? 'bg-[var(--success-soft)]' : 'bg-[var(--bg-elevated)] group-hover:bg-[var(--bg-surface-hover)]'
              }`}>
                {ch.icon}
              </div>
              <div className="flex-1 min-w-0">
                <p className={`text-sm font-semibold ${isActive ? 'text-[var(--success)]' : 'text-[var(--text-primary)]'}`}>
                  {ch.label}
                </p>
                <p className="text-xs text-[var(--text-muted)] mt-0.5">{ch.desc}</p>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
