export const UI_COMPONENT = {
  SIGNAL_BOARD: 'SignalIntelligenceBoard',
  AB_GRID: 'ABVariantGrid',
  CHANNEL_PICKER: 'ChannelIntentPicker',
  FEEDBACK_PANEL: 'FeedbackPanel',
  STALE_WARNING: 'StaleWarning',
  COMPARISON_CARD: 'ComparisonCard',
} as const;

export type UIRenderComponent = (typeof UI_COMPONENT)[keyof typeof UI_COMPONENT];

export const UI_COMPONENT_VALUES = Object.values(UI_COMPONENT) as readonly UIRenderComponent[];

const UI_COMPONENT_SET = new Set<string>(UI_COMPONENT_VALUES);

const ALIAS_TO_COMPONENT: Record<string, UIRenderComponent> = {
  signal_board: UI_COMPONENT.SIGNAL_BOARD,
  signal_intelligence_board: UI_COMPONENT.SIGNAL_BOARD,
  ab_grid: UI_COMPONENT.AB_GRID,
  ab_variant_grid: UI_COMPONENT.AB_GRID,
  channel_picker: UI_COMPONENT.CHANNEL_PICKER,
  channel_intent_picker: UI_COMPONENT.CHANNEL_PICKER,
  feedback_panel: UI_COMPONENT.FEEDBACK_PANEL,
  stale_warning: UI_COMPONENT.STALE_WARNING,
  comparison_card: UI_COMPONENT.COMPARISON_CARD,
};

export const UI_COMPONENT_ALIAS_MAP: Readonly<Record<string, UIRenderComponent>> = ALIAS_TO_COMPONENT;

export const normalizeUIRenderComponent = (value: unknown): UIRenderComponent | null => {
  if (typeof value !== 'string') {
    return null;
  }

  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  if (UI_COMPONENT_SET.has(trimmed)) {
    return trimmed as UIRenderComponent;
  }

  const folded = trimmed.replace(/[\s-]+/g, '_').toLowerCase();
  return UI_COMPONENT_ALIAS_MAP[folded] ?? null;
};
