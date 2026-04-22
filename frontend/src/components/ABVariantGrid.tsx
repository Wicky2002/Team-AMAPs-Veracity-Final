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
    if (deployed === index) {
      setDeployed(null);
      return;
    }
    setDeployed(index);
    onDeploy(variant);
  };

  return (
    <section className="panel overflow-hidden anim-in">
      <div className="px-5 py-3 border-b border-[var(--border-subtle)] bg-[var(--bg-surface)] flex items-center justify-between">
        <h2 className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-widest">
          A/B Variant Comparison
        </h2>
        {deployed !== null && (
          <span className="text-[10px] font-mono text-[var(--success)]">
            Variant {String.fromCharCode(65 + deployed)} selected
          </span>
        )}
      </div>

      <div className="p-4 grid gap-4 md:grid-cols-2">
        {variants.map((variant, index) => {
          const isDeployed = deployed === index;
          const label = String.fromCharCode(65 + index);

          return (
            <article
              key={`${variant.hypothesis}-${index}`}
              className={`
                rounded-lg border p-5 transition-all duration-300 overflow-hidden
                ${isDeployed
                  ? 'border-[var(--success)] bg-[var(--success-soft)]'
                  : 'border-[var(--border-subtle)] bg-[var(--bg-base)] hover:border-[var(--border-medium)] hover:bg-[var(--bg-surface-hover)]'}
              `}
            >
              <div className="flex items-center justify-between mb-4">
                <span className={`text-[10px] font-mono font-bold px-2.5 py-1 rounded ${
                  isDeployed ? 'bg-[var(--success)] text-[var(--bg-base)]' : 'bg-[var(--bg-elevated)] text-[var(--text-secondary)]'
                }`}>
                  Variant {label}
                </span>
                {isDeployed && (
                  <span className="text-[10px] font-mono text-[var(--success)]">✓ DEPLOYED</span>
                )}
              </div>

              <div className="mb-3">
                <span className="text-[10px] uppercase font-semibold text-[var(--text-muted)] block mb-1">Subject Line</span>
                <p className="text-sm font-medium text-[var(--text-primary)]">{variant.subject_line}</p>
              </div>

              <div className="mb-3">
                <span className="text-[10px] uppercase font-semibold text-[var(--text-muted)] block mb-1">Hook</span>
                <p className="text-[13px] text-[var(--text-secondary)] leading-relaxed">{variant.hook}</p>
              </div>

              <div className="mb-3">
                <span className="text-[10px] uppercase font-semibold text-[var(--text-muted)] block mb-1">CTA</span>
                <p className="text-[13px] text-[var(--text-secondary)]">{variant.cta}</p>
              </div>

              <div className="mb-4 rounded-md bg-[var(--bg-base)] border border-[var(--border-subtle)] px-3 py-2">
                <span className="text-[10px] uppercase font-semibold text-[var(--text-muted)] block mb-0.5">Hypothesis</span>
                <p className="text-xs text-[var(--text-secondary)]">{variant.hypothesis}</p>
              </div>

              {variant.provenance_chain.length > 0 && (
                <details className="mb-3">
                  <summary className="text-[10px] uppercase font-semibold text-[var(--text-muted)] cursor-pointer hover:text-[var(--text-secondary)] transition-colors">
                    Signal Sources ({variant.provenance_chain.length})
                  </summary>
                  <div className="mt-2 space-y-1.5 pl-2 border-l border-[var(--border-subtle)]">
                    {variant.provenance_chain.map((sig, si) => (
                      <div key={`prov-${si}`} className="text-xs text-[var(--text-muted)]">
                        <span className="text-[var(--text-secondary)]">[{sig.source_type ?? 'signal'}]</span>{' '}
                        {sig.quote?.slice(0, 80)}…
                      </div>
                    ))}
                  </div>
                </details>
              )}

              <button
                type="button"
                onClick={() => handleDeploy(variant, index)}
                className={`w-full mt-1 rounded-lg py-2.5 text-xs font-semibold transition-all duration-200 border cursor-pointer ${
                  isDeployed
                    ? 'bg-[var(--error-soft)] border-[var(--error)] text-[var(--error)] hover:bg-[var(--error)]/20'
                    : 'bg-[var(--bg-elevated)] border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--accent)] hover:text-[var(--bg-base)] hover:border-[var(--accent)]'
                }`}
              >
                {isDeployed ? 'Unselect Variant' : `Deploy Variant ${label}`}
              </button>
            </article>
          );
        })}
      </div>
    </section>
  );
}
