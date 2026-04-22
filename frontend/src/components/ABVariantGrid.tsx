import type { OutreachVariant } from '@/lib/loop-types';

type Props = {
  variants: OutreachVariant[];
  onDeploy: (variant: OutreachVariant) => void;
};

export function ABVariantGrid({ variants, onDeploy }: Props) {
  return (
    <section className="rounded-2xl border border-slate-200/70 bg-white/80 p-4 shadow-lg shadow-slate-200/40 backdrop-blur dark:border-slate-800 dark:bg-slate-950/65 dark:shadow-none">
      <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">A/B Variant Comparison</h2>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
        Pick the strongest narrative and push to outreach.
      </p>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {variants.map((variant, index) => (
          <article
            key={`${variant.hypothesis}-${index}`}
            className="rounded-xl border border-slate-200 bg-white/95 p-4 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md dark:border-slate-800 dark:bg-slate-900/70"
          >
            <div className="flex items-center justify-between">
              <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-300">
                Variant {String.fromCharCode(65 + index)}
              </div>
              <span className="rounded-full border border-indigo-300 bg-indigo-50 px-2 py-0.5 text-[10px] font-semibold text-indigo-700 dark:border-indigo-500/40 dark:bg-indigo-900/40 dark:text-indigo-200">
                Candidate
              </span>
            </div>

            <h3 className="mt-2 text-base font-semibold text-slate-900 dark:text-slate-100">{variant.subject_line}</h3>
            <p className="mt-2 text-sm text-slate-700 dark:text-slate-200">{variant.hook}</p>
            <p className="mt-2 text-sm text-slate-700 dark:text-slate-200">
              <span className="font-semibold">CTA:</span> {variant.cta}
            </p>
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">Hypothesis: {variant.hypothesis}</p>
            <button
              className="mt-4 rounded-lg bg-gradient-to-r from-slate-900 to-indigo-700 px-3 py-2 text-sm font-semibold text-white shadow-md transition hover:from-slate-800 hover:to-indigo-600 dark:from-indigo-600 dark:to-blue-600"
              onClick={() => onDeploy(variant)}
              type="button"
            >
              Deploy This Variant
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}
