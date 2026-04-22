import type { SignalReference } from '@/lib/loop-types';
import { motion } from 'framer-motion';
import { Activity } from 'lucide-react';

type Props = {
  signals: SignalReference[];
};

export function SignalIntelligenceBoard({ signals }: Props) {
  return (
    <motion.section 
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-panel rounded-3xl p-6 relative overflow-hidden"
    >
      <div className="absolute top-0 right-0 w-64 h-64 bg-blue-500/5 rounded-full blur-3xl -z-10" />
      
      <div className="flex items-center gap-3">
        <Activity className="text-blue-500 w-5 h-5 animate-pulse" />
        <h2 className="text-xl font-medium tracking-tight">Signal Intelligence</h2>
      </div>
      <p className="mt-1 text-sm text-zinc-500/80 font-light">Real-time semantic layer processing</p>
      
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        {signals.map((signal, idx) => (
          <motion.article 
            key={`${signal.source}-${idx}`} 
            whileHover={{ scale: 1.02, backgroundColor: 'var(--glass-bg)' }}
            transition={{ type: "spring", stiffness: 300, damping: 20 }}
            className="rounded-2xl border border-white/10 bg-white/5 p-5 relative overflow-hidden group"
          >
            <div className="absolute inset-0 bg-gradient-to-br from-blue-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
            
            <div className="flex justify-between items-center relative z-10">
              <span className="text-[10px] font-mono tracking-widest uppercase text-zinc-400 bg-zinc-800/10 dark:bg-zinc-100/10 px-2 py-1 rounded-full">
                {signal.source}
              </span>
              <span className="text-[10px] font-mono text-blue-500">
                {(signal.confidence * 100).toFixed(0)}% CONF
              </span>
            </div>
            
            <p className="mt-4 text-sm font-medium leading-relaxed relative z-10">"{signal.quote}"</p>
            
            <div className="mt-4 h-1 w-full rounded-full bg-zinc-800/5 dark:bg-zinc-100/5 overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${Math.max(0, Math.min(100, signal.confidence * 100))}%` }}
                transition={{ duration: 1, ease: "easeOut" }}
                className="h-full rounded-full bg-gradient-to-r from-blue-500 to-indigo-400"
              />
            </div>
          </motion.article>
        ))}
      </div>
    </motion.section>
  );
}
