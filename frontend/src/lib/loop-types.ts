export type LoopStage = 'research' | 'generate' | 'ab' | 'outreach' | 'feedback';

export interface SignalReference {
  source_type?: 'competitor' | 'audience' | 'pestel';
  source: string;
  source_url?: string;
  content?: string;
  quote: string;
  confidence: number;
  raw_quote?: string;
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
  cycle_n: number;
  top_signal: string;
  winning_variant: string;
  open_rate: number;
  reply_rate: number;
  angle: 'competitor_gap' | 'roi' | 'social_proof';
  timestamp: string;
}

export interface NodeStartedEvent {
  type: 'node_started';
  node: string;
  cycle_n: number;
}

export interface SignalFoundEvent {
  type: 'signal_found';
  source: 'competitor' | 'audience' | 'pestel';
  content: string;
  confidence: number;
  quote: string;
}

export type UIRenderComponent =
  | 'SignalIntelligenceBoard'
  | 'ABVariantGrid'
  | 'ChannelIntentPicker'
  | 'FeedbackPanel';

export interface UIRenderEvent {
  type: 'ui_render';
  component: UIRenderComponent;
  props: Record<string, unknown>;
  cycle_n: number;
}

export interface LoopCompleteEvent {
  type: 'loop_complete';
  cycle_n: number;
  next_action: 'awaiting_feedback' | 'refined_research' | 'end';
}

export interface WarningEvent {
  type: 'warning';
  message: string;
  fallback_used: boolean;
}

export type SSEEvent =
  | NodeStartedEvent
  | SignalFoundEvent
  | UIRenderEvent
  | LoopCompleteEvent
  | WarningEvent;
