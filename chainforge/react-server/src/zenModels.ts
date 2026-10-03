/**
 * OpenCode Zen model catalogue, mirrored from
 * chainforge/examples/custom_provider_opencode.py (ZEN_CATALOG).
 *
 * Used to render model pickers with pricing, and to label models in the UI.
 * `protocol` is the Zen gateway protocol the model speaks (the provider
 * script routes each model to the right endpoint automatically):
 *   "responses" -> /v1/responses            (OpenAI Responses API; GPT, Grok, Muse)
 *   "messages"  -> /v1/messages             (Anthropic protocol; Claude, Qwen Plus)
 *   "google"    -> /v1/models/<id>:generateContent (Google protocol; Gemini)
 *   "chat"      -> /v1/chat/completions     (OpenAI-compatible; DeepSeek, GLM, Kimi, ...)
 *   "systemone" -> /v1/systemone            (Jev; not supported by the chat UI)
 *
 * Prices are USD per 1M tokens (base/short-context tier); "Free" marks
 * limited-time free models; null = not offered.
 *
 * `released` is the model's release date (ISO YYYY-MM-DD). Model pickers sort
 * by it, newest first. It only affects display order — update it here when
 * adding models; the backend's ZEN_CATALOG order is irrelevant to the UI.
 */
import { LLMSpec } from "./backend/typing";

export type ZenProtocol =
  | "responses"
  | "messages"
  | "google"
  | "chat"
  | "systemone";

export interface ZenModelInfo {
  id: string;
  name: string;
  category: string;
  protocol: ZenProtocol;
  priceIn: number | "Free" | null;
  priceOut: number | "Free" | null;
  released: string;
}

export const ZEN_MODEL_CATALOG: ZenModelInfo[] = [
  {
    id: "gpt-6-astra",
    name: "GPT 6 Astra",
    category: "openai",
    protocol: "responses",
    priceIn: 10.0,
    priceOut: 50.0,
    released: "2026-08-31",
  },
  {
    id: "gpt-6-sol",
    name: "GPT 6 Sol",
    category: "openai",
    protocol: "responses",
    priceIn: 2.0,
    priceOut: 10.0,
    released: "2026-08-31",
  },
  {
    id: "gpt-6.1-sol",
    name: "GPT 6.1 Sol",
    category: "openai",
    protocol: "responses",
    priceIn: 2.0,
    priceOut: 10.0,
    released: "2026-09-15",
  },
  {
    id: "gpt-6-luna",
    name: "GPT 6 Luna",
    category: "openai",
    protocol: "responses",
    priceIn: 0.1,
    priceOut: 0.5,
    released: "2026-08-31",
  },
  {
    id: "gpt-5.6-sol",
    name: "GPT 5.6 Sol",
    category: "openai",
    protocol: "responses",
    priceIn: 4.0,
    priceOut: 20.0,
    released: "2026-06-10",
  },
  {
    id: "gpt-5.6-terra",
    name: "GPT 5.6 Terra",
    category: "openai",
    protocol: "responses",
    priceIn: 2.0,
    priceOut: 12.0,
    released: "2026-06-10",
  },
  {
    id: "gpt-5.6-luna",
    name: "GPT 5.6 Luna",
    category: "openai",
    protocol: "responses",
    priceIn: 0.2,
    priceOut: 1.2,
    released: "2026-06-10",
  },
  {
    id: "gpt-5.5",
    name: "GPT 5.5",
    category: "openai",
    protocol: "responses",
    priceIn: 5.0,
    priceOut: 30.0,
    released: "2026-03-05",
  },
  {
    id: "gpt-5.5-pro",
    name: "GPT 5.5 Pro",
    category: "openai",
    protocol: "responses",
    priceIn: 30.0,
    priceOut: 180.0,
    released: "2026-03-05",
  },
  {
    id: "gpt-5.4",
    name: "GPT 5.4",
    category: "openai",
    protocol: "responses",
    priceIn: 2.5,
    priceOut: 15.0,
    released: "2025-12-04",
  },
  {
    id: "gpt-5.4-pro",
    name: "GPT 5.4 Pro",
    category: "openai",
    protocol: "responses",
    priceIn: 30.0,
    priceOut: 180.0,
    released: "2025-12-04",
  },
  {
    id: "gpt-5.4-mini",
    name: "GPT 5.4 Mini",
    category: "openai",
    protocol: "responses",
    priceIn: 0.75,
    priceOut: 4.5,
    released: "2025-12-04",
  },
  {
    id: "gpt-5.4-nano",
    name: "GPT 5.4 Nano",
    category: "openai",
    protocol: "responses",
    priceIn: 0.2,
    priceOut: 1.25,
    released: "2025-12-04",
  },
  {
    id: "gpt-5.3-codex",
    name: "GPT 5.3 Codex",
    category: "openai",
    protocol: "responses",
    priceIn: 1.75,
    priceOut: 14.0,
    released: "2025-10-15",
  },
  {
    id: "gpt-5.3-codex-spark",
    name: "GPT 5.3 Codex Spark",
    category: "openai",
    protocol: "responses",
    priceIn: 1.75,
    priceOut: 14.0,
    released: "2025-10-15",
  },
  {
    id: "gpt-5.2",
    name: "GPT 5.2",
    category: "openai",
    protocol: "responses",
    priceIn: 1.75,
    priceOut: 14.0,
    released: "2025-08-07",
  },
  {
    id: "gpt-5.2-codex",
    name: "GPT 5.2 Codex",
    category: "openai",
    protocol: "responses",
    priceIn: 1.75,
    priceOut: 14.0,
    released: "2025-08-07",
  },
  {
    id: "gpt-5.1",
    name: "GPT 5.1",
    category: "openai",
    protocol: "responses",
    priceIn: 1.07,
    priceOut: 8.5,
    released: "2025-06-12",
  },
  {
    id: "gpt-5.1-codex",
    name: "GPT 5.1 Codex",
    category: "openai",
    protocol: "responses",
    priceIn: 1.07,
    priceOut: 8.5,
    released: "2025-06-12",
  },
  {
    id: "gpt-5.1-codex-max",
    name: "GPT 5.1 Codex Max",
    category: "openai",
    protocol: "responses",
    priceIn: 1.25,
    priceOut: 10.0,
    released: "2025-07-24",
  },
  {
    id: "gpt-5.1-codex-mini",
    name: "GPT 5.1 Codex Mini",
    category: "openai",
    protocol: "responses",
    priceIn: 0.25,
    priceOut: 2.0,
    released: "2025-06-12",
  },
  {
    id: "gpt-5",
    name: "GPT 5",
    category: "openai",
    protocol: "responses",
    priceIn: 1.07,
    priceOut: 8.5,
    released: "2025-02-20",
  },
  {
    id: "gpt-5-codex",
    name: "GPT 5 Codex",
    category: "openai",
    protocol: "responses",
    priceIn: 1.07,
    priceOut: 8.5,
    released: "2025-03-20",
  },
  {
    id: "gpt-5-nano",
    name: "GPT 5 Nano",
    category: "openai",
    protocol: "responses",
    priceIn: 0.05,
    priceOut: 0.4,
    released: "2025-02-20",
  },
  {
    id: "claude-fable-5-1",
    name: "Claude Fable 5.1",
    category: "anthropic",
    protocol: "messages",
    priceIn: 10.0,
    priceOut: 50.0,
    released: "2026-09-10",
  },
  {
    id: "claude-fable-5",
    name: "Claude Fable 5",
    category: "anthropic",
    protocol: "messages",
    priceIn: 10.0,
    priceOut: 50.0,
    released: "2026-07-02",
  },
  {
    id: "claude-opus-5-5",
    name: "Claude Opus 5.5",
    category: "anthropic",
    protocol: "messages",
    priceIn: 4.0,
    priceOut: 20.0,
    released: "2026-05-28",
  },
  {
    id: "claude-opus-5",
    name: "Claude Opus 5",
    category: "anthropic",
    protocol: "messages",
    priceIn: 5.0,
    priceOut: 25.0,
    released: "2026-03-19",
  },
  {
    id: "claude-opus-4-8",
    name: "Claude Opus 4.8",
    category: "anthropic",
    protocol: "messages",
    priceIn: 5.0,
    priceOut: 25.0,
    released: "2025-11-20",
  },
  {
    id: "claude-opus-4-7",
    name: "Claude Opus 4.7",
    category: "anthropic",
    protocol: "messages",
    priceIn: 5.0,
    priceOut: 25.0,
    released: "2025-09-25",
  },
  {
    id: "claude-opus-4-6",
    name: "Claude Opus 4.6",
    category: "anthropic",
    protocol: "messages",
    priceIn: 5.0,
    priceOut: 25.0,
    released: "2025-07-15",
  },
  {
    id: "claude-opus-4-5",
    name: "Claude Opus 4.5",
    category: "anthropic",
    protocol: "messages",
    priceIn: 5.0,
    priceOut: 25.0,
    released: "2025-05-22",
  },
  {
    id: "claude-sonnet-5",
    name: "Claude Sonnet 5",
    category: "anthropic",
    protocol: "messages",
    priceIn: 2.0,
    priceOut: 10.0,
    released: "2026-04-16",
  },
  {
    id: "claude-sonnet-4-6",
    name: "Claude Sonnet 4.6",
    category: "anthropic",
    protocol: "messages",
    priceIn: 3.0,
    priceOut: 15.0,
    released: "2025-12-09",
  },
  {
    id: "claude-sonnet-4-5",
    name: "Claude Sonnet 4.5",
    category: "anthropic",
    protocol: "messages",
    priceIn: 3.0,
    priceOut: 15.0,
    released: "2025-04-30",
  },
  {
    id: "claude-haiku-4-5",
    name: "Claude Haiku 4.5",
    category: "anthropic",
    protocol: "messages",
    priceIn: 1.0,
    priceOut: 5.0,
    released: "2025-10-15",
  },
  {
    id: "gemini-3.8-flash",
    name: "Gemini 3.8 Flash",
    category: "google",
    protocol: "google",
    priceIn: 1.5,
    priceOut: 7.5,
    released: "2026-09-01",
  },
  {
    id: "gemini-3.7-flash",
    name: "Gemini 3.7 Flash",
    category: "google",
    protocol: "google",
    priceIn: 1.5,
    priceOut: 7.5,
    released: "2026-07-15",
  },
  {
    id: "gemini-3.6-flash",
    name: "Gemini 3.6 Flash",
    category: "google",
    protocol: "google",
    priceIn: 1.5,
    priceOut: 7.5,
    released: "2026-05-20",
  },
  {
    id: "gemini-3.5-flash",
    name: "Gemini 3.5 Flash",
    category: "google",
    protocol: "google",
    priceIn: 1.5,
    priceOut: 9.0,
    released: "2026-03-11",
  },
  {
    id: "gemini-3.5-flash-lite",
    name: "Gemini 3.5 Flash Lite",
    category: "google",
    protocol: "google",
    priceIn: 0.3,
    priceOut: 2.5,
    released: "2026-04-08",
  },
  {
    id: "gemini-3.1-pro",
    name: "Gemini 3.1 Pro",
    category: "google",
    protocol: "google",
    priceIn: 2.0,
    priceOut: 12.0,
    released: "2025-12-17",
  },
  {
    id: "gemini-3-flash",
    name: "Gemini 3 Flash",
    category: "google",
    protocol: "google",
    priceIn: 0.5,
    priceOut: 3.0,
    released: "2025-10-22",
  },
  {
    id: "grok-4.7",
    name: "Grok 4.7",
    category: "xai",
    protocol: "responses",
    priceIn: 2.0,
    priceOut: 6.0,
    released: "2026-06-25",
  },
  {
    id: "grok-4.6",
    name: "Grok 4.6",
    category: "xai",
    protocol: "responses",
    priceIn: 2.0,
    priceOut: 6.0,
    released: "2026-03-12",
  },
  {
    id: "grok-4.5",
    name: "Grok 4.5",
    category: "xai",
    protocol: "responses",
    priceIn: 2.0,
    priceOut: 6.0,
    released: "2025-11-26",
  },
  {
    id: "grok-build-0.1",
    name: "Grok Build 0.1",
    category: "xai",
    protocol: "responses",
    priceIn: 1.0,
    priceOut: 2.0,
    released: "2026-08-19",
  },
  {
    id: "muse-spark-1.3",
    name: "Muse Spark 1.3",
    category: "muse",
    protocol: "responses",
    priceIn: 1.25,
    priceOut: 4.25,
    released: "2026-05-06",
  },
  {
    id: "muse-spark-1.2",
    name: "Muse Spark 1.2",
    category: "muse",
    protocol: "responses",
    priceIn: 1.25,
    priceOut: 4.25,
    released: "2026-01-14",
  },
  {
    id: "muse-spark-1.3-contributor-free",
    name: "Muse Spark 1.3 Contributor Free",
    category: "free",
    protocol: "responses",
    priceIn: "Free",
    priceOut: "Free",
    released: "2026-05-06",
  },
  {
    id: "qwen3.8-max",
    name: "Qwen3.8 Max",
    category: "alibaba",
    protocol: "chat",
    priceIn: 2.0,
    priceOut: 6.0,
    released: "2026-08-05",
  },
  {
    id: "qwen3.8-flash",
    name: "Qwen3.8 Flash",
    category: "alibaba",
    protocol: "messages",
    priceIn: 0.15,
    priceOut: 0.47,
    released: "2026-08-05",
  },
  {
    id: "qwen3.7-max",
    name: "Qwen3.7 Max",
    category: "alibaba",
    protocol: "messages",
    priceIn: 2.5,
    priceOut: 7.5,
    released: "2026-04-22",
  },
  {
    id: "qwen3.7-plus",
    name: "Qwen3.7 Plus",
    category: "alibaba",
    protocol: "messages",
    priceIn: 0.4,
    priceOut: 1.6,
    released: "2026-04-22",
  },
  {
    id: "qwen3.6-plus",
    name: "Qwen3.6 Plus",
    category: "alibaba",
    protocol: "messages",
    priceIn: 0.5,
    priceOut: 3.0,
    released: "2025-12-10",
  },
  {
    id: "qwen3.5-plus",
    name: "Qwen3.5 Plus",
    category: "alibaba",
    protocol: "messages",
    priceIn: 0.2,
    priceOut: 1.2,
    released: "2025-09-03",
  },
  {
    id: "deepseek-v4.1-flash",
    name: "DeepSeek V4.1 Flash",
    category: "deepseek",
    protocol: "chat",
    priceIn: 0.3,
    priceOut: 1.2,
    released: "2026-07-29",
  },
  {
    id: "deepseek-v4-pro",
    name: "DeepSeek V4 Pro",
    category: "deepseek",
    protocol: "chat",
    priceIn: 1.74,
    priceOut: 3.48,
    released: "2026-03-25",
  },
  {
    id: "deepseek-v4-flash",
    name: "DeepSeek V4 Flash",
    category: "deepseek",
    protocol: "chat",
    priceIn: 0.14,
    priceOut: 0.28,
    released: "2026-03-25",
  },
  {
    id: "deepseek-v4-flash-vision-exp",
    name: "DeepSeek V4 Flash Vision Exp",
    category: "deepseek",
    protocol: "chat",
    priceIn: 0.14,
    priceOut: 0.28,
    released: "2026-04-15",
  },
  {
    id: "minimax-m3",
    name: "MiniMax M3",
    category: "minimax",
    protocol: "chat",
    priceIn: 0.3,
    priceOut: 1.2,
    released: "2026-06-17",
  },
  {
    id: "minimax-m2.7",
    name: "MiniMax M2.7",
    category: "minimax",
    protocol: "chat",
    priceIn: 0.3,
    priceOut: 1.2,
    released: "2026-02-11",
  },
  {
    id: "minimax-m2.5",
    name: "MiniMax M2.5",
    category: "minimax",
    protocol: "chat",
    priceIn: 0.3,
    priceOut: 1.2,
    released: "2025-10-29",
  },
  {
    id: "glm-5.3-flash",
    name: "GLM 5.3 Flash",
    category: "zhipu",
    protocol: "chat",
    priceIn: 0.15,
    priceOut: 0.5,
    released: "2026-07-08",
  },
  {
    id: "glm-5.3",
    name: "GLM 5.3",
    category: "zhipu",
    protocol: "chat",
    priceIn: 1.4,
    priceOut: 4.4,
    released: "2026-07-08",
  },
  {
    id: "glm-5.2",
    name: "GLM 5.2",
    category: "zhipu",
    protocol: "chat",
    priceIn: 1.4,
    priceOut: 4.4,
    released: "2026-02-25",
  },
  {
    id: "glm-5.1",
    name: "GLM 5.1",
    category: "zhipu",
    protocol: "chat",
    priceIn: 1.4,
    priceOut: 4.4,
    released: "2025-11-12",
  },
  {
    id: "glm-5",
    name: "GLM 5",
    category: "zhipu",
    protocol: "chat",
    priceIn: 1.0,
    priceOut: 3.2,
    released: "2025-08-13",
  },
  {
    id: "kimi-k3",
    name: "Kimi K3",
    category: "moonshot",
    protocol: "chat",
    priceIn: 3.0,
    priceOut: 15.0,
    released: "2026-06-03",
  },
  {
    id: "kimi-k2.7-code",
    name: "Kimi K2.7 Code",
    category: "moonshot",
    protocol: "chat",
    priceIn: 0.95,
    priceOut: 4.0,
    released: "2026-01-28",
  },
  {
    id: "kimi-k2.6",
    name: "Kimi K2.6",
    category: "moonshot",
    protocol: "chat",
    priceIn: 0.95,
    priceOut: 4.0,
    released: "2025-12-16",
  },
  {
    id: "kimi-k2.5",
    name: "Kimi K2.5",
    category: "moonshot",
    protocol: "chat",
    priceIn: 0.6,
    priceOut: 3.0,
    released: "2025-09-17",
  },
  {
    id: "jev-1.13",
    name: "Jev 1.13",
    category: "typesafe",
    protocol: "systemone",
    priceIn: 0.042,
    priceOut: "Free",
    released: "2026-04-01",
  },
  {
    id: "jev-1.13-free",
    name: "Jev 1.13 Free",
    category: "free",
    protocol: "systemone",
    priceIn: "Free",
    priceOut: "Free",
    released: "2026-04-01",
  },
  {
    id: "big-pickle",
    name: "Big Pickle",
    category: "free",
    protocol: "chat",
    priceIn: "Free",
    priceOut: "Free",
    released: "2026-06-30",
  },
  {
    id: "space-bunny-free",
    name: "Space Bunny Free",
    category: "free",
    protocol: "chat",
    priceIn: "Free",
    priceOut: "Free",
    released: "2026-05-14",
  },
  {
    id: "longcat-2.5-preview-free",
    name: "LongCat 2.5 Preview Free",
    category: "free",
    protocol: "chat",
    priceIn: "Free",
    priceOut: "Free",
    released: "2026-03-31",
  },
  {
    id: "mimo-v2.6-flash-free",
    name: "MiMo-V2.6-Flash Free",
    category: "free",
    protocol: "chat",
    priceIn: "Free",
    priceOut: "Free",
    released: "2026-08-12",
  },
  {
    id: "mimo-v2.5-free",
    name: "MiMo-V2.5 Free",
    category: "free",
    protocol: "chat",
    priceIn: "Free",
    priceOut: "Free",
    released: "2026-01-21",
  },
  {
    id: "ling-3.0-flash-fin-free",
    name: "Ling 3.0 Flash Fin Free",
    category: "free",
    protocol: "chat",
    priceIn: "Free",
    priceOut: "Free",
    released: "2026-02-18",
  },
  {
    id: "nemotron-3-ultra-free",
    name: "Nemotron 3 Ultra Free",
    category: "free",
    protocol: "chat",
    priceIn: "Free",
    priceOut: "Free",
    released: "2025-12-03",
  },
  {
    id: "nemotron-3.5-lightning-free",
    name: "Nemotron 3.5 Lightning Free",
    category: "free",
    protocol: "chat",
    priceIn: "Free",
    priceOut: "Free",
    released: "2026-09-24",
  },
];

const BY_ID = new Map<string, ZenModelInfo>(
  ZEN_MODEL_CATALOG.map((m) => [m.id, m]),
);

export const zenModelInfo = (id: string): ZenModelInfo | undefined =>
  BY_ID.get(id);

/** Sort models by release date, newest first. Stable: ties keep catalogue order. */
export const sortZenModelsNewestFirst = (
  models: ZenModelInfo[],
): ZenModelInfo[] =>
  [...models].sort((a, b) => b.released.localeCompare(a.released));

/** The Zen backbone's base_model in ChainForge. */
export const OPENCODE_ZEN_BASE_MODEL = "__custom/OpenCode Zen";

/** A ready-to-add LLMSpec for a Zen model, under the Zen backbone. */
export const makeZenModelSpec = (
  model: ZenModelInfo,
  emoji: string,
): LLMSpec => ({
  key: `zen-${model.category}-${model.id}`,
  name: model.name,
  emoji,
  base_model: OPENCODE_ZEN_BASE_MODEL,
  model: `${OPENCODE_ZEN_BASE_MODEL}/${model.id}`,
  temp: 0.7,
});

/** Display metadata for each upstream provider OpenCode Zen powers. */
export interface ZenProviderInfo {
  /** The catalogue `category` this provider maps to. */
  category: string;
  /** Human-readable provider name (no emoji). */
  label: string;
  emoji: string;
}

/**
 * Providers powered by OpenCode Zen, in the order they appear in pickers.
 * The first five keep the classic ChainForge menu order; the rest follow.
 */
export const ZEN_PROVIDERS: ZenProviderInfo[] = [
  { category: "openai", label: "OpenAI", emoji: "🤖" },
  { category: "anthropic", label: "Anthropic (Claude)", emoji: "🎭" },
  { category: "google", label: "Google AI (Gemini)", emoji: "✨" },
  { category: "deepseek", label: "DeepSeek", emoji: "🐋" },
  { category: "minimax", label: "MiniMax", emoji: "🪶" },
  { category: "xai", label: "xAI (Grok)", emoji: "𝕏" },
  { category: "alibaba", label: "Alibaba (Qwen)", emoji: "🐉" },
  { category: "zhipu", label: "Zhipu (GLM)", emoji: "🔮" },
  { category: "moonshot", label: "Moonshot (Kimi)", emoji: "🌙" },
  { category: "muse", label: "Muse", emoji: "🎼" },
  { category: "typesafe", label: "TypeSafe (Jev)", emoji: "🛡️" },
  { category: "free", label: "Free models", emoji: "🎁" },
];

const PROVIDER_BY_CATEGORY = new Map(ZEN_PROVIDERS.map((p) => [p.category, p]));

export const zenProviderInfo = (
  category: string,
): ZenProviderInfo | undefined => PROVIDER_BY_CATEGORY.get(category);

/** All models of a provider, sorted newest first. */
export const zenProviderModels = (category: string): ZenModelInfo[] =>
  sortZenModelsNewestFirst(
    ZEN_MODEL_CATALOG.filter((m) => m.category === category),
  );

const fmtPrice = (p: number | "Free" | null): string => {
  if (p === "Free") return "Free";
  if (typeof p !== "number") return "—";
  return `$${p.toFixed(2)}`;
};

/** Short label, e.g. "$5.00 in / $30.00 out per 1M tokens" or "Free". */
export const zenModelPriceLabel = (id: string): string => {
  const info = BY_ID.get(id);
  if (!info) return "";
  if (info.priceIn === "Free" || info.priceOut === "Free") return "Free";
  return `${fmtPrice(info.priceIn)} in / ${fmtPrice(info.priceOut)} out per 1M tokens`;
};

/** Long dropdown label, e.g. "GPT 5.5 — $5.00 in / $30.00 out per 1M". */
export const zenModelDropdownLabel = (id: string): string => {
  const info = BY_ID.get(id);
  if (!info) return id;
  return `${info.name} — ${zenModelPriceLabel(id)}`;
};
