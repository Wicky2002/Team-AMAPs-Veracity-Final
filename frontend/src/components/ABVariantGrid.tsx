import type { OutreachVariant } from '@/lib/loop-types';

type Props = {
  variants: OutreachVariant[];
  onDeploy: (variantIndex: number) => void;
};

export function ABVariantGrid({ variants, onDeploy }: Props) {
  return (
    <section className="rounded-xl border border-zinc-200 p-4 shadow-sm">
      <h2 className="text-lg font-semibold">A/B Variant Comparison</h2>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {variants.map((variant, index) => (
          <article key={`${variant.hypothesis}-${index}`} className="rounded-lg border border-zinc-200 p-3">
            <div className="text-xs uppercase text-zinc-500">Variant {String.fromCharCode(65 + index)}</div>
            <h3 className="mt-1 font-medium">{variant.subject_line}</h3>
            <p className="mt-2 text-sm text-zinc-700">{variant.hook}</p>
            <p className="mt-2 text-sm">
              <span className="font-medium">CTA:</span> {variant.cta}
            </p>
            <p className="mt-2 text-xs text-zinc-500">Hypothesis: {variant.hypothesis}</p>
            <button
              className="mt-3 rounded-md bg-black px-3 py-1.5 text-sm text-white hover:bg-zinc-800"
              onClick={() => onDeploy(index)}
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
