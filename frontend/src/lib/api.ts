// lib/api.ts — Backend communication helpers
// All JSON shapes are from the veracity_frontend_spec contract

export type AgentResponseType =
  | "research"
  | "variants"
  | "channel_select"
  | "feedback"
  | "text";

export interface ResearchResponse {
  type: "research";
  signal: string;
  competitor: string;
  audience: string;
}

export interface VariantsResponse {
  type: "variants";
  variantA: { subject: string; body: string };
  variantB: { subject: string; body: string };
}

export interface ChannelSelectResponse {
  type: "channel_select";
  options: string[];
}

export interface FeedbackResponse {
  type: "feedback";
  winner: string;
  stats: { replyRate: number };
}

export interface TextResponse {
  type: "text";
  content: string;
}

export type AgentResponse =
  | ResearchResponse
  | VariantsResponse
  | ChannelSelectResponse
  | FeedbackResponse
  | TextResponse;

export interface Message {
  id: string;
  role: "user" | "assistant";
  text?: string;
  component?: AgentResponse;
  timestamp: Date;
}

// ─── Core API functions ───────────────────────────────────────────────────────

/**
 * POST /api/chat — send user message with full conversation history.
 * Returns a typed AgentResponse JSON from the backend.
 */
export async function postMessage(
  message: string,
  history: Message[]
): Promise<AgentResponse> {
  const historyPayload = history.map((m) => ({
    role: m.role,
    content: m.text || JSON.stringify(m.component),
  }));

  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history: historyPayload }),
  });

  if (!res.ok) {
    const err = await res.text().catch(() => "Unknown error");
    throw new Error(`Backend error ${res.status}: ${err}`);
  }

  return parseJSONResponse(await res.json());
}

/**
 * POST /api/feedback — send the selected A/B variant back for the feedback loop.
 */
export async function selectVariant(variantId: "A" | "B"): Promise<void> {
  await fetch("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ selected: variantId }),
  });
}

/**
 * POST /api/channel — send the chosen outreach channel to trigger the agent.
 */
export async function selectChannel(channel: string): Promise<void> {
  await fetch("/api/channel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ channel }),
  });
}

/**
 * Validates and casts the raw JSON from the backend into a typed AgentResponse.
 * Falls back to a plain text response on unknown types.
 */
export function parseJSONResponse(raw: unknown): AgentResponse {
  if (typeof raw !== "object" || raw === null) {
    return { type: "text", content: String(raw) };
  }

  const obj = raw as Record<string, unknown>;
  const type = obj.type as AgentResponseType | undefined;

  switch (type) {
    case "research":
    case "variants":
    case "channel_select":
    case "feedback":
      return raw as AgentResponse;
    case "text":
      return raw as TextResponse;
    default:
      // Graceful fallback: wrap unexpected shapes as plain text
      return {
        type: "text",
        content:
          typeof obj.content === "string"
            ? obj.content
            : JSON.stringify(raw, null, 2),
      };
  }
}
