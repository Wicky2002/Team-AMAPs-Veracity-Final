import { motion } from 'framer-motion';
import { Send, Link, SplitSquareVertical } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

type Channel = 'LinkedIn' | 'Email' | 'Both';

type Props = {
  selected?: string;
  onSelect: (channel: Channel) => void;
};

const CHANNELS: { id: Channel; icon: LucideIcon; label: string }[] = [
  { id: 'LinkedIn', icon: Link, label: 'LinkedIn' },
  { id: 'Email', icon: Send, label: 'Email' },
  { id: 'Both', icon: SplitSquareVertical, label: 'Multi-Modal' }
];

export function ChannelIntentPicker({ selected, onSelect }: Props) {
  return (
    <motion.section 
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-panel rounded-3xl p-6 relative"
    >
      <h2 className="text-sm font-medium tracking-widest uppercase text-zinc-500 mb-4">
        Transmission Intent
      </h2>
      
      <div className="flex flex-wrap gap-2 p-1 bg-white/5 border border-white/5 rounded-2xl w-fit">
        {CHANNELS.map((channel) => {
          const isSelected = selected === channel.id;
          const Icon = channel.icon;
          
          return (
            <button
              key={channel.id}
              type="button"
              onClick={() => onSelect(channel.id)}
              className={`relative flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm transition-all duration-300 ${
                isSelected ? 'text-white' : 'text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-300'
              }`}
            >
              {isSelected && (
                <motion.div
                  layoutId="active-channel"
                  className="absolute inset-0 bg-foreground dark:bg-zinc-800 rounded-xl shadow-md border border-white/10"
                  transition={{ type: "spring", stiffness: 400, damping: 30 }}
                />
              )}
              <span className="relative z-10 flex items-center gap-2">
                <Icon className={`w-4 h-4 ${isSelected ? 'opacity-100' : 'opacity-70'}`} />
                <span className="font-medium">{channel.label}</span>
              </span>
            </button>
          );
        })}
      </div>
    </motion.section>
  );
}