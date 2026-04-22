import type { TimelineEntry } from '@/lib/loop-types';
import { motion, AnimatePresence } from 'framer-motion';
import { Clock } from 'lucide-react';

type Props = {
  entries: TimelineEntry[];
};

export function CampaignTimeline({ entries }: Props) {
  return (
    <motion.aside 
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      className="glass-panel rounded-3xl p-6 relative col-span-1"
    >
      <div className="absolute top-0 right-0 w-64 h-64 bg-emerald-500/5 rounded-full blur-3xl -z-10" />

      <div className="flex items-center gap-3">
        <Clock className="text-emerald-500 w-5 h-5" />
        <h2 className="text-xl font-medium tracking-tight">Temporal Arc</h2>
      </div>

      <div className="mt-8 relative border-l border-white/10 dark:border-white/5 ml-3 space-y-8">
        <AnimatePresence>
          {entries.map((entry, idx) => (
            <motion.div
              layout
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ delay: idx * 0.1, type: "spring", stiffness: 200, damping: 20 }}
              key={`${entry.cycle_n}-${entry.timestamp}-${idx}`} 
              className="relative pl-6"
            >
              <div className="absolute -left-[5px] top-1.5 h-2.5 w-2.5 rounded-full bg-emerald-400 ring-4 ring-background" />
              
              <div className="group rounded-2xl bg-white/5 border border-white/10 p-4 transition-all hover:bg-white/10">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono tracking-widest uppercase text-emerald-500">
                    Cycle {entry.cycle_n}
                  </span>
                  <span className="text-[10px] font-mono text-zinc-500">
                    {new Date(entry.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
                
                <h3 className="mt-2 text-sm font-semibold tracking-tight text-foreground">
                  <span className="text-zinc-500 font-normal mr-1">Apex:</span> 
                  {entry.winning_variant}
                </h3>
                
                <p className="mt-2 text-xs leading-relaxed text-zinc-400 font-light truncate">
                  <span className="text-zinc-500 mr-2">Signal:</span>
                  {entry.top_signal}
                </p>
                
                <div className="mt-4 flex gap-4 text-xs font-mono text-zinc-500">
                  <div className="flex items-center gap-1">
                    <div className="w-1.5 h-1.5 rounded-full bg-blue-400/50" />
                    Open {(entry.open_rate * 100).toFixed(1)}%
                  </div>
                  <div className="flex items-center gap-1">
                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-400/50" />
                    Reply {(entry.reply_rate * 100).toFixed(1)}%
                  </div>
                </div>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </motion.aside>
  );
}
