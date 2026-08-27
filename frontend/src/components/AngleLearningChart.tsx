import type { TimelineEntry } from '@/lib/loop-types';

type Angle = TimelineEntry['angle'];

const ANGLES: Angle[] = ['competitor_gap', 'roi', 'social_proof'];

// Same fixed categorical order/colors already used for these angles
// elsewhere in the app (CampaignTimeline) -- validated (all checks pass:
// lightness band, chroma floor, CVD separation, normal-vision floor, contrast).
const ANGLE_COLOR: Record<Angle, string> = {
  competitor_gap: '#4f46e5', // indigo-600
  roi: '#059669', // emerald-600
  social_proof: '#7c3aed', // violet-600
};

const ANGLE_LABEL: Record<Angle, string> = {
  competitor_gap: 'Competitor gap',
  roi: 'ROI',
  social_proof: 'Social proof',
};

function performanceScore(entry: TimelineEntry): number {
  return Math.max(entry.reply_rate, entry.open_rate * 0.35, 0.01);
}

/** Mirrors the backend's _infer_winning_angle scoring exactly (recency-weighted
 * performance over the trailing 5 cycles) so this chart shows the literal
 * mechanism biasing the next cycle's copy -- not a decorative approximation. */
function angleScoresAtCycle(history: TimelineEntry[], upToIndex: number): Record<Angle, number> {
  const window = history.slice(Math.max(0, upToIndex - 4), upToIndex + 1);
  const scores: Record<Angle, number> = { competitor_gap: 0, roi: 0, social_proof: 0 };
  const total = window.length;

  window.forEach((entry, idx) => {
    const recencyWeight = 1 + (idx / Math.max(1, total - 1)) * 0.5;
    scores[entry.angle] += recencyWeight * performanceScore(entry);
  });

  return scores;
}

type Props = {
  entries: TimelineEntry[];
};

export function AngleLearningChart({ entries }: Props) {
  if (entries.length < 2) {
    return (
      <div className="mt-4 rounded-xl border border-dashed border-slate-300 bg-slate-50/80 p-4 text-xs leading-relaxed text-slate-600 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-400">
        Angle-preference chart needs at least 2 completed cycles to show a trend.
      </div>
    );
  }

  const chronological = [...entries].sort((a, b) => a.cycle_n - b.cycle_n);
  const series = chronological.map((_, idx) => angleScoresAtCycle(chronological, idx));

  const width = 400;
  const height = 140;
  const padding = { top: 12, right: 12, bottom: 24, left: 12 };
  const plotW = width - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;

  const maxScore = Math.max(0.05, ...series.flatMap((s) => ANGLES.map((a) => s[a])));
  const xFor = (idx: number) => padding.left + (idx / Math.max(1, chronological.length - 1)) * plotW;
  const yFor = (score: number) => padding.top + plotH - (score / maxScore) * plotH;

  const pathFor = (angle: Angle) =>
    series.map((s, idx) => `${idx === 0 ? 'M' : 'L'} ${xFor(idx).toFixed(1)} ${yFor(s[angle]).toFixed(1)}`).join(' ');

  const leader = series[series.length - 1];
  const leadingAngle = ANGLES.reduce((best, a) => (leader[a] > leader[best] ? a : best), ANGLES[0]);

  return (
    <div className="mt-4">
      <div className="mb-2 flex flex-wrap items-center gap-3">
        {ANGLES.map((angle) => (
          <span key={angle} className="flex items-center gap-1.5 text-[11px] text-slate-600 dark:text-slate-300">
            <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: ANGLE_COLOR[angle] }} />
            {ANGLE_LABEL[angle]}
          </span>
        ))}
      </div>

      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label="Angle preference score across cycles">
        <line
          x1={padding.left}
          y1={padding.top + plotH}
          x2={padding.left + plotW}
          y2={padding.top + plotH}
          stroke="currentColor"
          strokeOpacity={0.15}
          strokeWidth={1}
        />

        {ANGLES.map((angle) => (
          <path key={angle} d={pathFor(angle)} fill="none" stroke={ANGLE_COLOR[angle]} strokeWidth={2} strokeLinecap="round" />
        ))}

        {ANGLES.map((angle) =>
          series.map((s, idx) => (
            <circle key={`${angle}-${idx}`} cx={xFor(idx)} cy={yFor(s[angle])} r={3} fill={ANGLE_COLOR[angle]}>
              <title>
                Cycle {chronological[idx].cycle_n} · {ANGLE_LABEL[angle]}: {s[angle].toFixed(3)}
              </title>
            </circle>
          )),
        )}

        {chronological.map((entry, idx) => (
          <text
            key={entry.cycle_n}
            x={xFor(idx)}
            y={height - 6}
            textAnchor="middle"
            fontSize={9}
            fill="currentColor"
            fillOpacity={0.5}
          >
            C{entry.cycle_n}
          </text>
        ))}
      </svg>

      <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
        Currently biasing toward <span className="font-semibold">{ANGLE_LABEL[leadingAngle]}</span> for the next cycle.
      </p>
    </div>
  );
}
