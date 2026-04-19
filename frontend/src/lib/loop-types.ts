export type LoopStage = 'research' | 'generate' | 'ab' | 'feedback';

export interface SignalReference {
  source: string;
  quote: string;
  confidence: number;
}

export interface OutreachVariant {
  subject_line: string;
  hook: string;
  cta: string;
  hypothesis: string;
  provenance_chain: SignalReference[];
}

export interface FeedbackMetric {
  variant: number;
  open_rate: number;
  reply_rate: number;
  click_rate: number;
}

export interface TimelineEntry {
  stage: string;
  summary: string;
  at: string;
}

export interface LoopEnvelope {
  mode: string;
  payload: unknown;
}
