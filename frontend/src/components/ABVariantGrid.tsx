import type { OutreachVariant } from '@/lib/loop-types';
import { motion } from 'framer-motion';
import { Layers } from 'lucide-react';

type Props = {
  variants: OutreachVariant[];
  onDeploy: (variant: OutreachVariant) => void;
};

export function ABVariantGrid({ variants, onDeploy }: Props) {
  return (
    <motion.section 
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-panel rounded-3xl p-6 relative overflow-hidden"
    >
      <div className="absolute -top-32 -left-32 w-96 h-96 bg-purple-500/5 rounded-full blur-3xl -z-10" />

      <div className="flex items-center gap-3">
        <Layers className="text-purple-500 w-5 h-5" />
        <h2 className="text-xl font-medium tracking-tight">Dimensional A/B Synthesis</h2>
      </div>
      <p className="mt-1 text-sm text-zinc-500/80 font-light">
        Hypothesis-driven variant projection
      </p>

      <div className="mt-8 grid gap-6 md:grid-cols-2 relative perspective-1000">
        {variants.map((variant, index) => (
          <motion.article 
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: index * 0.1, type: "spring", stiffness: 300, damping: 25 }}
            whileHover={{ y: -5, rotateX: 2, rotateY: -2, zIndex: 10, boxShadow: "0 25px 50px -12px rgba(0,0,0,0.25)" }}
            key={`${variant.hypothesis}-${index}`} 
            className="rounded-[2rem] border border-white/10 bg-white/5 p-6 backdrop-blur-xl relative group flex flex-col h-full transform-gpu transition-all duration-500 ease-out"
          >
            <div className="absolute inset-0 bg-gradient-to-br from-purple-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity rounded-[2rem]" />

            <div className="flex items-center justify-between mb-6">
              <div className="px-3 py-1 rounded-full bg-purple-500/10 text-purple-400 text-[10px] font-mono tracking-widest font-bold uppercase ring-1 ring-purple-500/20">
                Variant {String.fromCharCode(65 + index)}
              </div>
            </div>

            <div className="flex-1 space-y-4 relative z-10">
              <div>
                <h4 className="text-[10px] uppercase tracking-widest text-zinc-500 mb-1">Subject Line</h4>
                <h3 className="text-lg font-medium leading-tight text-foreground">{variant.subject_line}</h3>
              </div>
              
              <div>
                <h4 className="text-[10px] uppercase tracking-widest text-zinc-500 mb-1">Hook</h4>
                <p className="text-sm leading-relaxed text-zinc-400 font-light">{variant.hook}</p>
              </div>

              <div className="p-4 rounded-xl bg-zinc-900/5 dark:bg-zinc-100/5 border border-zinc-200/50 dark:border-white/5">
                <h4 className="text-[10px] uppercase tracking-widest text-zinc-500 mb-1">Call To Action</h4>
                <p className="text-sm font-medium text-purple-600 dark:text-purple-400">{variant.cta}</p>
              </div>
            </div>

            <div className="mt-8 pt-6 border-t border-white/5">
              <p className="text-xs text-zinc-500 font-mono mb-4 leading-relaxed line-clamp-2" title={variant.hypothesis}>
                <span className="text-purple-400/80 mr-2">H:</span>
                {variant.hypothesis}
              </p>
              <button
                className="w-full relative overflow-hidden rounded-xl bg-foreground px-4 py-3 text-sm font-medium text-background transition-all hover:scale-[1.02] active:scale-95 group/btn shadow-lg"
                onClick={() => onDeploy(variant)}
                type="button"
              >
                <div className="absolute inset-0 bg-gradient-to-r from-purple-500/20 to-blue-500/20 opacity-0 group-hover/btn:opacity-100 transition-opacity" />
                <span className="relative z-10">Deploy Variant {String.fromCharCode(65 + index)}</span>
              </button>
            </div>
          </motion.article>
        ))}
      </div>
    </motion.section>
  );
}
