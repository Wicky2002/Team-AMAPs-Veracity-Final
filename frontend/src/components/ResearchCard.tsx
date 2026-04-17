'use client';
// components/ResearchCard.tsx
import { ResearchResponse } from '@/lib/api';
import { Radar, Building2, Users } from 'lucide-react';

export default function ResearchCard({ data }: { data: ResearchResponse }) {
  const rows = [
    {
      icon: <Radar size={16} />,
      label: 'Signal',
      value: data.signal,
    },
    {
      icon: <Building2 size={16} />,
      label: 'Competitor',
      value: data.competitor,
    },
    {
      icon: <Users size={16} />,
      label: 'Audience',
      value: data.audience,
    },
  ];

  return (
    <div className="panel rounded-xl overflow-hidden w-full max-w-2xl mt-2 animate-in">
      <div className="px-5 py-3 border-b border-white/5 bg-white/[0.02] flex items-center justify-between">
        <h3 className="text-xs font-semibold text-neutral-300 uppercase tracking-widest">Research Intelligence</h3>
        <span className="text-[10px] font-mono text-emerald-400 bg-emerald-400/10 px-2 py-0.5 rounded">LIVE</span>
      </div>
      <div className="p-2 flex flex-col">
        {rows.map((row, i) => (
          <div key={row.label} className={`p-4 flex gap-4 items-start ${i !== rows.length - 1 ? 'border-b border-white/5' : ''}`}>
            <div className="text-neutral-500 mt-0.5 shrink-0">{row.icon}</div>
            <div className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-neutral-500 uppercase tracking-wider">{row.label}</span>
              <p className="text-sm text-neutral-200 leading-relaxed">{row.value}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
