'use client';
// components/FeedbackPanel.tsx
import { FeedbackResponse } from '@/lib/api';
import { BarChart3 } from 'lucide-react';

export default function FeedbackPanel({ data }: { data: FeedbackResponse }) {
  const replyPct = Math.round(data.stats.replyRate * 100);

  return (
    <div className="panel rounded-xl overflow-hidden w-full max-w-sm mt-2 animate-in">
      <div className="px-5 py-3 border-b border-white/5 bg-white/[0.02] flex items-center gap-2">
        <BarChart3 size={14} className="text-neutral-500" />
        <h3 className="text-xs font-semibold text-neutral-300 uppercase tracking-widest">Feedback Loop Closed</h3>
      </div>
      
      <div className="p-6">
        <div className="flex justify-between items-end mb-6">
          <div>
            <span className="text-[10px] font-mono text-neutral-500 block mb-1">WINNING VARIANT</span>
            <span className="text-3xl font-light text-white">{data.winner}</span>
          </div>
          <div className="text-right">
            <span className="text-[10px] font-mono text-neutral-500 block mb-1">REPLY RATE</span>
            <span className="text-xl font-medium text-emerald-400">{replyPct}%</span>
          </div>
        </div>

        <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
          <div 
            className="h-full bg-gradient-to-r from-emerald-500 to-cyan-400" 
            style={{ width: `${Math.min(replyPct * 4, 100)}%` }} 
          />
        </div>
        
        <p className="mt-4 text-xs text-neutral-500">
          Intelligence updated. Next cycle will optimize based on Variant {data.winner} signals.
        </p>
      </div>
    </div>
  );
}
