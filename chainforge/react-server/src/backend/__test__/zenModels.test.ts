import {
  ZEN_MODEL_CATALOG,
  ZEN_PROVIDERS,
  makeZenModelSpec,
  OPENCODE_ZEN_BASE_MODEL,
  sortZenModelsNewestFirst,
  zenProviderModels,
  zenModelInfo,
} from "../../zenModels";

describe("zenModels", () => {
  test("every provider has at least one model and every model has a provider", () => {
    const categories = new Set(ZEN_MODEL_CATALOG.map((m) => m.category));
    ZEN_PROVIDERS.forEach((p) => expect(categories.has(p.category)).toBe(true));
    ZEN_MODEL_CATALOG.forEach((m) =>
      expect(ZEN_PROVIDERS.some((p) => p.category === m.category)).toBe(true),
    );
  });

  test("provider model lists are sorted by release date, newest first", () => {
    ZEN_PROVIDERS.forEach((p) => {
      const dates = zenProviderModels(p.category).map((m) => m.released);
      const sorted = [...dates].sort((a, b) => b.localeCompare(a));
      expect(dates).toEqual(sorted);
    });
  });

  test("sortZenModelsNewestFirst is stable for equal dates", () => {
    const models = zenProviderModels("zhipu");
    // GLM 5.3 Flash and GLM 5.3 share a release date; catalogue order wins.
    const ids = models.map((m) => m.id);
    expect(ids.indexOf("glm-5.3-flash")).toBeLessThan(ids.indexOf("glm-5.3"));
    expect([...models]).toEqual(sortZenModelsNewestFirst(models));
  });

  test("newest models come first per provider", () => {
    // Anthropic: Fable 5.1 is the newest Claude on Zen.
    expect(zenProviderModels("anthropic")[0].id).toBe("claude-fable-5-1");
    // OpenAI: the 6.1 refresh postdates the GPT 6 launch models.
    expect(zenProviderModels("openai")[0].id).toBe("gpt-6.1-sol");
    // Google: 3.8 Flash is the newest Gemini.
    expect(zenProviderModels("google")[0].id).toBe("gemini-3.8-flash");
  });

  test("makeZenModelSpec builds a spec under the Zen backbone", () => {
    const info = zenModelInfo("claude-opus-5-5")!;
    const spec = makeZenModelSpec(info, "🎭");
    expect(spec.base_model).toBe(OPENCODE_ZEN_BASE_MODEL);
    expect(spec.model).toBe(`${OPENCODE_ZEN_BASE_MODEL}/claude-opus-5-5`);
    expect(spec.name).toBe("Claude Opus 5.5");
    expect(spec.emoji).toBe("🎭");
    expect(spec.temp).toBe(0.7);
    // Keys are unique across all models (needed for menu React keys).
    const keys = new Set(
      ZEN_MODEL_CATALOG.map((m) =>
        makeZenModelSpec(m, "x").key,
      ),
    );
    expect(keys.size).toBe(ZEN_MODEL_CATALOG.length);
  });
});
