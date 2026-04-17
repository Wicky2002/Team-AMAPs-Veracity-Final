'use client';
// components/VariantGrid.tsx
import { useState } from 'react';
import { VariantsResponse, selectVariant } from '@/lib/api';
import { PenTool, CheckCircle2 } from 'lucide-react';

interface Props {
  data: VariantsResponse;
  onSelected?: (variant: 'A' | 'B') => void;
}

export default function VariantGrid({ data, onSelected }: Props) {
  const [selected, setSelected] = useState<'A' | 'B' | null>(null);

  async function handleSelect(variant: 'A' | 'B') {
    if (selected) return;
    setSelected(variant);
    try {
      await selectVariant(variant);
      onSelected?.(variant);
    } catch {}
  }

  const variants = [
    { id: 'A' as const, data: data.variantA },
    { id: 'B' as const, data: data.variantB }
  ];

  return (
    <div className="panel rounded-xl overflow-hidden w-full max-w-3xl mt-2 animate-in">
      <div className="px-5 py-3 border-b border-white/5 bg-white/[0.02] flex items-center justify-between">
        <h3 className="text-xs font-semibold text-neutral-300 uppercase tracking-widest flex items-center gap-2">
          <PenTool size={14} className="text-neutral-500" />
          A/B Variants Generated
        </h3>
        {selected && <span className="text-[10px] font-mono text-emerald-400">Variant {selected} selected</span>}
      </div>
      
      <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
        {variants.map(({ id, data: v }) => {
          const isSelected = selected === id;
          const isDimmed = selected && !isSelected;

          return (
            <button
              key={id}
              onClick={() => handleSelect(id)}
              disabled={!!selected}
              className={`text-left border rounded-lg p-5 transition-all duration-300 relative overflow-hidden group
                ${isSelected ? 'border-white/30 bg-white/[0.03]' : isDimmed ? 'border-white/5 opacity-40' : 'border-white/10 hover:border-white/20 hover:bg-white/[0.02]'}
              `}
            >
              <div className="flex justify-between items-center mb-4">
                <span className={`text-[10px] font-mono px-2 py-0.5 rounded ${isSelected ? 'bg-white text-black' : 'bg-neutral-800 text-neutral-400'}`}>
                  Variant {id}
                </span>
                {isSelected && <CheckCircle2 size={16} className="text-white" />}
              </div>

              <div className="mb-4">
                <span className="text-[10px] uppercase font-semibold text-neutral-500 block mb-1">Subject</span>
                <p className="text-sm font-medium text-white">{v.subject}</p>
              </div>

              <div>
                <span className="text-[10px] uppercase font-semibold text-neutral-500 block mb-1">Body</span>
                <p className="text-xs text-neutral-300 leading-relaxed whitespace-pre-wrap">{v.body}</p>
              </div>

              {!selected && (
                <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px] opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                  <span className="bg-white text-black text-xs font-bold px-4 py-2 rounded-full transform translate-y-2 group-hover:translate-y-0 transition-all">
                    Select Variant {id}
                  </span>
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
