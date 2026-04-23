from __future__ import annotations

ROUTE_LOOP_BACK = "market_intelligence"
ROUTE_END = "END"
ROUTE_END_LEGACY = "end"


class UIComponent:
    SIGNAL_BOARD = "SignalIntelligenceBoard"
    AB_GRID = "ABVariantGrid"
    CHANNEL_PICKER = "ChannelIntentPicker"
    FEEDBACK_PANEL = "FeedbackPanel"
    STALE_WARNING = "StaleWarning"
    COMPARISON_CARD = "ComparisonCard"
    LINKEDIN_POST_GRID = "LinkedInPostGrid"
    CAMPAIGN_BRIEF_CARD = "CampaignBriefCard"


UI_COMPONENT_VALUES = (
    UIComponent.SIGNAL_BOARD,
    UIComponent.AB_GRID,
    UIComponent.CHANNEL_PICKER,
    UIComponent.FEEDBACK_PANEL,
    UIComponent.STALE_WARNING,
    UIComponent.COMPARISON_CARD,
    UIComponent.LINKEDIN_POST_GRID,
    UIComponent.CAMPAIGN_BRIEF_CARD,
)
UI_COMPONENT_SET = set(UI_COMPONENT_VALUES)

UI_COMPONENT_ALIASES: dict[str, str] = {
    "signal_board": UIComponent.SIGNAL_BOARD,
    "signal_intelligence_board": UIComponent.SIGNAL_BOARD,
    "ab_grid": UIComponent.AB_GRID,
    "ab_variant_grid": UIComponent.AB_GRID,
    "channel_picker": UIComponent.CHANNEL_PICKER,
    "channel_intent_picker": UIComponent.CHANNEL_PICKER,
    "feedback_panel": UIComponent.FEEDBACK_PANEL,
    "stale_warning": UIComponent.STALE_WARNING,
    "comparison_card": UIComponent.COMPARISON_CARD,
    "linkedin_post_grid": UIComponent.LINKEDIN_POST_GRID,
    "campaign_brief_card": UIComponent.CAMPAIGN_BRIEF_CARD,
}


def canonicalize_ui_component(component: str) -> str | None:
    value = (component or "").strip()
    if not value:
        return None

    if value in UI_COMPONENT_SET:
        return value

    folded = value.replace("-", "_").replace(" ", "_").lower()
    return UI_COMPONENT_ALIASES.get(folded)
