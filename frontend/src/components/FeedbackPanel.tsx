import type { FeedbackMetric } from '@/lib/loop-types';
import { motion } from 'framer-motion';
import { MessagesSquare, Sparkles } from 'lucide-react';

type Props = {
  metrics: FeedbackMetric[];
  onFeedback: () => void;
};

export function FeedbackPanel({ metrics, onFeedback }: Props) {
  return (
    <motion.section 
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-panel border-emerald-500/20 rounded-3xl p-6 relative overflow-hidden"
    >
      <div className="absolute bottom-0 right-0 w-full h-32 bg-gradient-to-t from-emerald-500/10 to-transparent -z-10" />

      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <MessagesSquare className="text-emerald-500 w-5 h-5" />
          <h2 className="text-xl font-medium tracking-tight">Feedback Synapse</h2>
        </div>
        <div className="px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-xs flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
          Listening
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {metrics.map((m) => (
          <motion.article 
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            key={m.variant} 
            className="rounded-2xl border border-white/5 bg-white/5 p-4 text-sm hover:bg-white/10 transition-colors group"
          >
            <div className="flex items-center justify-between mb-3 border-b border-white/5 pb-2">
              <p className="font-mono text-[10px] uppercase tracking-widest text-emerald-500">Variant {String.fromCharCode(65 + m.variant)}</p>
              <Sparkles className="w-3 h-3 text-zinc-500 group-hover:text-emerald-400 transition-colors" />
            </div>
            <div className="space-y-2 font-mono text-xs">
              <div className="flex justify-between">
                <span className="text-zinc-500">Open</span>
                <span className="text-foreground">{(m.open_rate * 100).toFixed(1)}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-zinc-500">Reply</span>
                <span className="text-foreground">{(m.reply_rate * 100).toFixed(1)}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-zinc-500">Click</span>
                <span className="text-foreground">{(m.click_rate * 100).toFixed(1)}%</span>
              </div>
            </div>
          </motion.article>
        ))}
      </div>

      <motion.button
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        type="button"
        onClick={onFeedback}
        className="w-full mt-6 flex items-center justify-center gap-2 rounded-2xl bg-emerald-500 hover:bg-emerald-600 px-4 py-3 text-sm font-medium text-white shadow-lg shadow-emerald-500/20 transition-colors"
      >
        <Sparkles className="w-4 h-4" />
        Ingest & Recalibrate Matrix
      </motion.button>
    </motion.section>
  );
}
