'use client';

import { useState } from 'react';
import type { OutreachVariant } from '@/lib/loop-types';

type Props = {
  variants: OutreachVariant[];
  onDeploy: (variant: OutreachVariant) => void;
};

export function ABVariantGrid({ variants, onDeploy }: Props) {
  const [deployed, setDeployed] = useState<number | null>(null);

  const handleDeploy = (variant: OutreachVariant, index: number) => {
    if (deployed !== null) return;
    setDeployed(index);
    onDeploy(variant);
  };

  return (
    <section className="panel rounded-xl overflow-hidden anim-in">
      <div className="px-5 py-3 border-b border-white/5 bg-white/[0.02] flex items-center justify-between">
        <h2 className="text-xs font-semibold text-neutral-300 uppercase tracking-widest">
          A/B Variant Comparison
        </h2>
        {deployed !== null && (
          <span className="text-[10px] font-mono text-emerald-400">
            Variant {String.fromCharCode(65 + deployed)} deployed
          </span>
        )}
      </div>

      <div className="p-4 grid gap-4 md:grid-cols-2">
        {variants.map((variant, index) => {
          const isDeployed = deployed === index;
          const isDimmed = deployed !== null && !isDeployed;
          const label = String.fromCharCode(65 + index);

          return (
            <article
              key={`${variant.hypothesis}-${index}`}
              className={`
                relative rounded-lg border p-5 transition-all duration-300 group overflow-hidden
                ${isDeployed
                  ? 'border-emerald-500/40 bg-emerald-500/[0.04]'
                  : isDimmed
                    ? 'border-white/5 opacity-40'
                    : 'border-white/8 bg-white/[0.02] hover:border-white/15 hover:bg-white/[0.04]'}
              `}
            >
              {/* Header */}
              <div className="flex items-center justify-between mb-4">
                <span className={`text-[10px] font-mono font-bold px-2.5 py-1 rounded ${
                  isDeployed ? 'bg-emerald-500 text-black' : 'bg-white/5 text-neutral-400'
                }`}>
                  Variant {label}
                </span>
                {isDeployed && (
                  <span className="text-[10px] font-mono text-emerald-400">✓ DEPLOYED</span>
                )}
              </div>

              {/* Subject */}
              <div className="mb-3">
                <span className="text-[10px] uppercase font-semibold text-neutral-500 block mb-1">Subject Line</span>
                <p className="text-sm font-medium text-white">{variant.subject_line}</p>
              </div>

              {/* Hook */}
              <div className="mb-3">
                <span className="text-[10px] uppercase font-semibold text-neutral-500 block mb-1">Hook</span>
                <p className="text-[13px] text-neutral-300 leading-relaxed">{variant.hook}</p>
              </div>

              {/* CTA */}
              <div className="mb-3">
                <span className="text-[10px] uppercase font-semibold text-neutral-500 block mb-1">CTA</span>
                <p className="text-[13px] text-neutral-300">{variant.cta}</p>
              </div>

              {/* Hypothesis */}
              <div className="mb-4 rounded-md bg-white/[0.03] border border-white/5 px-3 py-2">
                <span className="text-[10px] uppercase font-semibold text-neutral-500 block mb-0.5">Hypothesis</span>
                <p className="text-xs text-neutral-400">{variant.hypothesis}</p>
              </div>

              {/* Provenance */}
              {variant.provenance_chain.length > 0 && (
                <details className="mb-3">
                  <summary className="text-[10px] uppercase font-semibold text-neutral-500 cursor-pointer hover:text-neutral-300 transition-colors">
                    Signal Sources ({variant.provenance_chain.length})
                  </summary>
                  <div className="mt-2 space-y-1.5 pl-2 border-l border-white/5">
                    {variant.provenance_chain.map((sig, si) => (
                      <div key={`prov-${si}`} className="text-xs text-neutral-500">
                        <span className="text-neutral-400">[{sig.source_type ?? 'signal'}]</span>{' '}
                        {sig.quote?.slice(0, 80)}…
                      </div>
                    ))}
                  </div>
                </details>
              )}

              {/* Deploy overlay */}
              {deployed === null && (
                <button
                  type="button"
                  onClick={() => handleDeploy(variant, index)}
                  className="w-full mt-1 rounded-lg bg-white/[0.06] border border-white/8 py-2.5 text-xs font-semibold text-neutral-300 hover:bg-white hover:text-black hover:border-white transition-all duration-200"
                >
                  Deploy Variant {label}
                </button>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
