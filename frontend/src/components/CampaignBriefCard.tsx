'use client';

import { jsPDF } from 'jspdf';

import type { CampaignBrief } from '@/lib/loop-types';

type Props = {
  brief: CampaignBrief;
};

const slugify = (value: string) =>
  value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '') || 'campaign-brief';

const fallbackTextDownload = (brief: CampaignBrief) => {
  const lines = [
    brief.title,
    '',
    `Positioning Statement: ${brief.positioning_statement}`,
    `Target Audience: ${brief.target_audience}`,
    '',
    'Key Messages:',
    ...brief.key_messages.map((msg, idx) => `${idx + 1}. ${msg}`),
    '',
    'Competitor Gaps:',
    ...brief.competitor_gaps.map((gap, idx) => `${idx + 1}. ${gap}`),
    '',
    `Recommended Channels: ${brief.recommended_channels.join(', ')}`,
    '',
    'Next Actions:',
    ...brief.next_actions.map((action, idx) => `${idx + 1}. ${action}`),
    '',
    `Context: ${brief.context ?? 'N/A'}`,
  ];

  const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${slugify(brief.title)}.txt`;
  a.click();
  URL.revokeObjectURL(url);
};

const generateBriefPDF = (brief: CampaignBrief) => {
  const doc = new jsPDF({ unit: 'pt', format: 'a4' });
  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  const margin = 48;
  const maxWidth = pageWidth - margin * 2;
  let y = margin;

  const ensureSpace = (needed = 24) => {
    if (y + needed <= pageHeight - margin) {
      return;
    }

    doc.addPage();
    y = margin;
  };

  const heading = (text: string) => {
    ensureSpace(30);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(13);
    doc.text(text, margin, y);
    y += 18;
  };

  const paragraph = (text: string, fontSize = 11) => {
    const safe = text.trim() || '—';
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(fontSize);
    const wrapped = doc.splitTextToSize(safe, maxWidth);

    for (const line of wrapped) {
      ensureSpace(15);
      doc.text(line, margin, y);
      y += 15;
    }

    y += 6;
  };

  const bulletList = (items: string[]) => {
    const normalized = items.length > 0 ? items : ['—'];

    for (const item of normalized) {
      const wrapped = doc.splitTextToSize(`• ${item}`, maxWidth);
      for (const line of wrapped) {
        ensureSpace(15);
        doc.setFont('helvetica', 'normal');
        doc.setFontSize(11);
        doc.text(line, margin, y);
        y += 15;
      }
    }

    y += 6;
  };

  doc.setFont('helvetica', 'bold');
  doc.setFontSize(18);
  doc.text(brief.title || 'Campaign Brief', margin, y);
  y += 26;

  heading('Positioning Statement');
  paragraph(brief.positioning_statement);

  heading('Target Audience');
  paragraph(brief.target_audience);

  heading('Key Messages');
  bulletList(brief.key_messages);

  heading('Competitor Gaps');
  bulletList(brief.competitor_gaps);

  heading('Recommended Channels');
  paragraph(brief.recommended_channels.join(', '));

  heading('Next Actions');
  bulletList(brief.next_actions);

  if (brief.context) {
    heading('Context');
    paragraph(brief.context, 10);
  }

  doc.save(`${slugify(brief.title)}.pdf`);
};

export function CampaignBriefCard({ brief }: Props) {
  const downloadPDF = () => {
    try {
      generateBriefPDF(brief);
    } catch {
      fallbackTextDownload(brief);
    }
  };

  return (
    <section className="rounded-2xl border border-slate-200/70 bg-white/80 p-4 shadow-lg shadow-slate-200/40 backdrop-blur dark:border-slate-800 dark:bg-slate-950/65 dark:shadow-none">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">{brief.title}</h2>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">One-pager generated from signal + performance context.</p>
        </div>
        <button
          type="button"
          onClick={downloadPDF}
          className="rounded-lg bg-linear-to-r from-indigo-600 to-blue-600 px-3 py-1.5 text-xs font-semibold text-white shadow transition hover:from-indigo-500 hover:to-blue-500"
        >
          Download PDF
        </button>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <article className="rounded-xl border border-slate-200 bg-white/95 p-3 shadow-sm dark:border-slate-800 dark:bg-slate-900/70 md:col-span-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-300">Positioning statement</p>
          <p className="mt-1 text-sm text-slate-700 dark:text-slate-200">{brief.positioning_statement}</p>
        </article>

        <article className="rounded-xl border border-slate-200 bg-white/95 p-3 shadow-sm dark:border-slate-800 dark:bg-slate-900/70">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-300">Target audience</p>
          <p className="mt-1 text-sm text-slate-700 dark:text-slate-200">{brief.target_audience}</p>
        </article>

        <article className="rounded-xl border border-slate-200 bg-white/95 p-3 shadow-sm dark:border-slate-800 dark:bg-slate-900/70">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-300">Recommended channels</p>
          <p className="mt-1 text-sm text-slate-700 dark:text-slate-200">{brief.recommended_channels.join(', ') || 'LinkedIn, Email'}</p>
        </article>

        <article className="rounded-xl border border-slate-200 bg-white/95 p-3 shadow-sm dark:border-slate-800 dark:bg-slate-900/70">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-300">Key messages</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700 dark:text-slate-200">
            {brief.key_messages.map((message, idx) => (
              <li key={`${message}-${idx}`}>{message}</li>
            ))}
          </ul>
        </article>

        <article className="rounded-xl border border-slate-200 bg-white/95 p-3 shadow-sm dark:border-slate-800 dark:bg-slate-900/70">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-300">Competitor gaps</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700 dark:text-slate-200">
            {brief.competitor_gaps.map((gap, idx) => (
              <li key={`${gap}-${idx}`}>{gap}</li>
            ))}
          </ul>
        </article>
      </div>

      <article className="mt-3 rounded-xl border border-slate-200 bg-white/95 p-3 shadow-sm dark:border-slate-800 dark:bg-slate-900/70">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-300">Next actions</p>
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-slate-700 dark:text-slate-200">
          {brief.next_actions.map((action, idx) => (
            <li key={`${action}-${idx}`}>{action}</li>
          ))}
        </ol>
      </article>

      {brief.context ? (
        <article className="mt-3 rounded-xl border border-indigo-200 bg-indigo-50/80 p-3 text-xs text-indigo-950 dark:border-indigo-500/30 dark:bg-indigo-950/40 dark:text-indigo-100">
          <span className="font-semibold">Context:</span> {brief.context}
        </article>
      ) : null}
    </section>
  );
}
