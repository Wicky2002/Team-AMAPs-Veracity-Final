'use client';

import { useState } from 'react';

import type { LinkedInPost } from '@/lib/loop-types';

type Props = {
  title: string;
  subtitle: string;
  posts: LinkedInPost[];
};

const angleLabel = (angle: string) => {
  switch (angle) {
    case 'competitor_gap':
      return 'Competitor Gap';
    case 'roi_outcome':
      return 'ROI Outcome';
    case 'thought_leader':
      return 'Thought Leadership';
    default:
      return angle.replace(/[_-]/g, ' ');
  }
};

const formatPostForClipboard = (post: LinkedInPost) => {
  const hashtags = post.hashtags.join(' ');
  return [post.hook, '', post.body, '', `CTA: ${post.cta}`, '', hashtags].join('\n');
};

export function LinkedInPostGrid({ title, subtitle, posts }: Props) {
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  const copyPost = async (post: LinkedInPost, index: number) => {
    const text = formatPostForClipboard(post);

    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.setAttribute('readonly', 'true');
      textarea.style.position = 'absolute';
      textarea.style.left = '-9999px';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
    }

    setCopiedIndex(index);
    window.setTimeout(() => {
      setCopiedIndex((current) => (current === index ? null : current));
    }, 1400);
  };

  return (
    <section className="rounded-2xl border border-slate-200/70 bg-white/80 p-4 shadow-lg shadow-slate-200/40 backdrop-blur dark:border-slate-800 dark:bg-slate-950/65 dark:shadow-none">
      <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">{title}</h2>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{subtitle}</p>

      {posts.length === 0 ? (
        <div className="mt-4 rounded-xl border border-dashed border-slate-300 bg-slate-50/80 p-4 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-400">
          No LinkedIn drafts were generated for this cycle.
        </div>
      ) : (
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          {posts.map((post, index) => (
            <article
              key={`${post.angle}-${index}`}
              className="rounded-xl border border-slate-200 bg-white/95 p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900/70"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="rounded-full border border-indigo-300 bg-indigo-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-indigo-700 dark:border-indigo-500/40 dark:bg-indigo-900/40 dark:text-indigo-200">
                  {angleLabel(post.angle)}
                </span>
                <button
                  type="button"
                  onClick={() => void copyPost(post, index)}
                  className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-700 transition hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  {copiedIndex === index ? 'Copied!' : 'Copy'}
                </button>
              </div>

              <p className="mt-3 text-sm font-semibold text-slate-900 dark:text-slate-100">{post.hook}</p>
              <p className="mt-2 text-sm leading-relaxed text-slate-700 dark:text-slate-200">{post.body}</p>
              <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">
                <span className="font-semibold">CTA:</span> {post.cta}
              </p>

              <div className="mt-3 flex flex-wrap gap-1.5">
                {post.hashtags.map((tag) => (
                  <span
                    key={tag}
                    className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
