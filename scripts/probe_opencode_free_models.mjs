#!/usr/bin/env node
// Ad-hoc probe: call every OpenCode Zen free model through the bridge and
// report which ones the gateway accepts. Used to verify provider health.
const BRIDGE = process.env.BRIDGE || "http://127.0.0.1:8765"
const MODELS = [
  "longcat-2.5-preview-free",
  "space-bunny-free",
  "big-pickle",
  "mimo-v2.6-flash-free",
  "mimo-v2.5-free",
  "ling-3.0-flash-fin-free",
  "nemotron-3-ultra-free",
  "nemotron-3.5-lightning-free",
  "muse-spark-1.3-contributor-free",
  "fledge-alpha-free",
  "jev-1.13-free",
]

const run = async (model) => {
  const started = Date.now()
  try {
    const res = await fetch(`${BRIDGE}/v1/chat/completions`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        model,
        temperature: 0,
        max_tokens: 120,
        messages: [
          { role: "system", content: "Reply with one short sentence." },
          { role: "user", content: "What is 1+1?" },
        ],
      }),
    })
    const payload = await res.json()
    const text = payload?.choices?.[0]?.message?.content
    if (!res.ok || !text) {
      return { model, status: res.status, ok: false, note: payload?.error?.message?.slice(0, 120) || "empty response" }
    }
    return { model, status: res.status, ok: true, ms: Date.now() - started, text: text.replace(/\s+/g, " ").slice(0, 90) }
  } catch (error) {
    return { model, status: 0, ok: false, note: error.message.slice(0, 120) }
  }
}

const results = []
for (const model of MODELS) {
  const result = await run(model)
  results.push(result)
  const tag = result.ok ? "PASS" : "FAIL"
  console.log(`${tag} ${model.padEnd(34)} ${result.status} ${result.ms ? result.ms + "ms " : ""}${result.ok ? result.text : result.note}`)
}
const passed = results.filter((r) => r.ok).length
console.log(`\n${passed}/${results.length} free models accepted`)
