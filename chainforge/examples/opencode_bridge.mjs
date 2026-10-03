#!/usr/bin/env node
/**
 * ChainForge <-> OpenCode Zen bridge.
 *
 * ChainForge's OpenCode Zen provider cannot call the Zen gateway directly for
 * the free models: the gateway answers `403 FreeTierError - OpenCode's free
 * tier can only be used from within OpenCode`. The free tier is gated on the
 * request coming from the real OpenCode agent, so this bridge puts the real
 * agent in the path.
 *
 * This script uses the official OpenCode JavaScript SDK (`@opencode-ai/sdk`):
 *
 *   createOpencode()            spawns `opencode serve` and returns a client
 *   client.session.create()     opens a throw-away session
 *   client.session.prompt()     runs one completion on OpenCode Zen
 *   client.session.delete()     cleans the session up
 *
 * Because the call travels through `opencode serve`, OpenCode attaches its own
 * identity headers (x-opencode-session, x-opencode-request, the OpenCode
 * user agent), which is what the free tier requires. It also means OpenCode
 * itself resolves the gateway protocol of each model (Responses / Anthropic /
 * Google / chat completions), so this provider no longer needs a protocol map.
 *
 * The bridge speaks a small OpenAI-compatible surface so the Python provider
 * can talk to it with plain HTTP:
 *
 *   GET  /health              -> { ok, version, models }
 *   GET  /v1/models           -> OpenAI model list of the Zen provider
 *   POST /v1/chat/completions -> OpenAI chat completion (non-streaming)
 *
 * Usage:
 *   node chainforge/examples/opencode_bridge.mjs
 *
 * Environment:
 *   OPENCODE_BRIDGE_PORT  port for this bridge      (default 8765)
 *   OPENCODE_SERVER_PORT  port for `opencode serve` (default 4096)
 *   OPENCODE_BIN          path to the opencode CLI  (default "opencode")
 *
 * The Python provider starts this bridge on demand, so running it by hand is
 * only needed for debugging.
 */

import fs from "node:fs"
import http from "node:http"
import os from "node:os"
import path from "node:path"
import process from "node:process"
import { createOpencode, createOpencodeClient } from "@opencode-ai/sdk"

const BRIDGE_PORT = Number(process.env.OPENCODE_BRIDGE_PORT || 8765)
const SERVER_PORT = Number(process.env.OPENCODE_SERVER_PORT || 4096)
const HOST = "127.0.0.1"
const PROVIDER_ID = "opencode"

// OpenCode offers per-agent model options, but the SDK prompt API takes no
// sampling parameters. So the bridge pre-declares one agent per temperature
// step and picks the nearest one for each request.
const TEMPERATURE_GRID = [0, 0.2, 0.4, 0.7, 1.0, 1.5]

function agentNameForTemperature(temperature) {
  const value = Number.isFinite(temperature) ? temperature : 0.7
  let best = TEMPERATURE_GRID[0]
  let bestDelta = Math.abs(best - value)
  for (const step of TEMPERATURE_GRID) {
    const delta = Math.abs(step - value)
    if (delta < bestDelta) {
      best = step
      bestDelta = delta
    }
  }
  return `chainforge-t${String(best).replace(".", "")}`
}

function buildAgentConfig() {
  const agents = {}
  for (const step of TEMPERATURE_GRID) {
    agents[agentNameForTemperature(step)] = {
      description: `ChainForge bridge agent (temperature ${step}, no tools).`,
      mode: "primary",
      // ChainForge is a prompt test bench, not a coding agent: no tools, no
      // shell, no file writes. maxSteps is deliberately left unset, because a
      // value of 1 makes OpenCode append a "maximum steps" notice to the answer.
      options: { temperature: step },
      permission: {
        edit: "deny",
        bash: { "*": "deny" },
        webfetch: "deny",
        doom_loop: "deny",
        external_directory: "deny",
      },
    }
  }
  return { agent: agents }
}

// A neutral working directory, so the agent never treats the ChainForge repo
// as its project.
const WORKDIR = path.join(os.tmpdir(), "chainforge-opencode-bridge")

// ChainForge reads this file to find a bridge it left behind after a crash.
const PID_FILE = path.join(
  os.tmpdir(),
  `chainforge-opencode-bridge-${process.env.OPENCODE_BRIDGE_PORT || 8765}.pid`,
)

const log = (...args) => {
  if (process.env.OPENCODE_BRIDGE_QUIET === "1") return
  console.log("[opencode-bridge]", ...args)
}

async function connectToRunningServer() {
  // If an `opencode serve` is already up on the server port (the user's own, or
  // one this bridge spawned before a crash), attach to it instead of failing
  // with "Failed to start server on port N".
  try {
    const client = createOpencodeClient({ baseUrl: `http://${HOST}:${SERVER_PORT}` })
    await Promise.race([
      client.app.agents(),
      new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), 3000)),
    ])
    return client
  } catch {
    return null
  }
}

async function main() {
  let client = await connectToRunningServer()
  let server = null
  if (client) {
    log(`attached to the opencode server already on port ${SERVER_PORT}`)
  } else {
    const created = await createOpencode({
      hostname: HOST,
      port: SERVER_PORT,
      timeout: 60_000,
      config: buildAgentConfig(),
    })
    client = created.client
    server = created.server
    log(`opencode server up at ${server.url}`)
  }

  // The SDK exposes liveness through the config routes (there is no
  // global.health() in this version), so a successful call means the server is
  // ready to serve prompts.
  await client.app.agents()

  // Optional: an explicit Zen key. Without one the server falls back to the
  // credentials stored by `opencode auth login`, then to OPENCODE_API_KEY in
  // the environment it inherited from ChainForge.
  const apiKey = process.env.OPENCODE_API_KEY
  if (apiKey) {
    await client.auth.set({
      path: { id: PROVIDER_ID },
      body: { type: "api", key: apiKey },
    })
    log("Zen API key applied to the opencode server")
  } else {
    log("no OPENCODE_API_KEY set; using opencode's stored credentials")
  }

  // Collect the built-in tool names once, then turn them all off per request.
  let disabledTools = {}
  try {
    const agents = await client.app.agents()
    const names = new Set()
    for (const agent of agents?.data ?? []) {
      for (const name of Object.keys(agent?.tools ?? {})) names.add(name)
    }
    // Belt and braces: names seen in the wild that a build may not report.
    for (const name of ["bash", "edit", "write", "read", "grep", "glob", "list",
                        "patch", "todowrite", "todoread", "webfetch", "task"]) {
      names.add(name)
    }
    disabledTools = Object.fromEntries([...names].map((name) => [name, false]))
    log(`${Object.keys(disabledTools).length} tools disabled for every call`)
  } catch (error) {
    log(`could not read agent tool list: ${error?.message ?? error}`)
  }

  let zenModels = []
  async function refreshModels() {
    try {
      const providers = await client.config.providers()
      const zen = (providers?.data?.providers ?? []).find((p) => p.id === PROVIDER_ID)
      // `models` is a record keyed by model id, not an array.
      zenModels = Object.values(zen?.models ?? {}).map((m) => m.id).filter(Boolean)
    } catch (error) {
      log(`could not list Zen models: ${error?.message ?? error}`)
    }
    return zenModels
  }
  await refreshModels()
  log(`${zenModels.length} Zen models available`)

  function sendJson(res, status, payload) {
    const body = JSON.stringify(payload)
    res.writeHead(status, {
      "content-type": "application/json",
      "content-length": Buffer.byteLength(body),
    })
    res.end(body)
  }

  function readBody(req) {
    return new Promise((resolve, reject) => {
      const chunks = []
      req.on("data", (chunk) => chunks.push(chunk))
      req.on("end", () => {
        const raw = Buffer.concat(chunks).toString("utf8")
        if (!raw.trim()) return resolve({})
        try {
          resolve(JSON.parse(raw))
        } catch (error) {
          reject(new Error(`invalid JSON body: ${error.message}`))
        }
      })
      req.on("error", reject)
    })
  }

  function describeError(failure) {
  // ApiError nests the real text under data.message; the other kinds use
  // message/name directly.
  const detail = failure?.data?.message || failure?.message || failure?.name
  const status = failure?.data?.statusCode
  const body = failure?.data?.responseBody
  let text = status ? `${status} ${detail}` : String(detail ?? "opencode error")
  if (body) {
    // Pull out the gateway's own type, e.g. FreeTierError.
    const match = /"type"\s*:\s*"([^"]+)"/.exec(body)
    const message = /"message"\s*:\s*"([^"]+)"/.exec(body)
    if (match || message) {
      text += ` (${match?.[1] ?? "error"}: ${message?.[1] ?? ""})`.trim()
    }
  }
  return text
}

async function complete(body) {
    const modelId = String(body.model || "").replace(/^opencode\//, "")
    if (!modelId) throw new Error("model is required")

    // A key supplied per request (ChainForge's settings modal) overrides the
    // one the server started with.
    if (body.api_key) {
      await client.auth.set({
        path: { id: PROVIDER_ID },
        body: { type: "api", key: String(body.api_key) },
      })
    }

    const messages = Array.isArray(body.messages) ? body.messages : []
    const systemText = messages
      .filter((m) => m.role === "system")
      .map((m) => (typeof m.content === "string" ? m.content : ""))
      .filter(Boolean)
      .join("\n\n")

    // One throw-away session per request. History is replayed into a single
    // text part, because the session API has no multi-turn replay that keeps
    // roles intact without spending extra model calls.
    const lines = []
    for (const message of messages) {
      if (message.role === "system") continue
      const content = typeof message.content === "string"
        ? message.content
        : (message.content ?? []).map((c) => c?.text ?? "").join("")
      const label = message.role === "assistant" ? "Assistant" : "User"
      lines.push(`${label}: ${content}`)
    }
    const prompt = lines.length ? lines.join("\n\n") : ""

    const created = await client.session.create({
      body: { title: "chainforge" },
      query: { directory: WORKDIR },
    })
    const sessionId = created?.data?.id
    if (!sessionId) throw new Error("could not create opencode session")

    const promptBody = {
      agent: agentNameForTemperature(body.temperature),
      model: { providerID: PROVIDER_ID, modelID: modelId },
      parts: [{ type: "text", text: prompt }],
    }
    if (systemText) promptBody.system = systemText
    if (Object.keys(disabledTools).length) promptBody.tools = disabledTools

    try {
      const result = await client.session.prompt({
        path: { id: sessionId },
        body: promptBody,
        query: { directory: WORKDIR },
      })
      const data = result?.data
      // The assistant message carries the failure, not the envelope.
      const failure = data?.info?.error ?? data?.error
      if (failure) {
        throw new Error(describeError(failure))
      }
      const text = (data?.parts ?? [])
        .filter((part) => part?.type === "text" && typeof part.text === "string")
        .map((part) => part.text)
        .join("")
      return { text, info: data?.info }
    } finally {
      await client.session.delete({ path: { id: sessionId } }).catch(() => {})
    }
  }

  const httpServer = http.createServer(async (req, res) => {
    const url = new URL(req.url, `http://${HOST}:${BRIDGE_PORT}`)

    if (req.method === "GET" && url.pathname === "/health") {
      let ready = false
      try {
        await client.app.agents()
        ready = true
      } catch {
        ready = false
      }
      return sendJson(res, ready ? 200 : 503, {
        ok: ready,
        service: "chainforge-opencode-bridge",
        models: zenModels.length,
      })
    }

    if (req.method === "POST" && url.pathname === "/v1/models/refresh") {
      const models = await refreshModels()
      return sendJson(res, 200, { object: "list", data: models.map((id) => ({ id })) })
    }

    if (req.method === "GET" && url.pathname === "/v1/models") {
      return sendJson(res, 200, {
        object: "list",
        data: zenModels.map((id) => ({ id, object: "model", owned_by: PROVIDER_ID })),
      })
    }

    if (req.method === "POST" && url.pathname === "/v1/chat/completions") {
      const started = Date.now()
      let body
      try {
        body = await readBody(req)
      } catch (error) {
        return sendJson(res, 400, { error: { message: error.message, type: "invalid_request_error" } })
      }
      try {
        const { text, info } = await complete(body)
        log(`${body.model} -> ${text.length} chars in ${Date.now() - started}ms`)
        return sendJson(res, 200, {
          id: `chainforge-${started}`,
          object: "chat.completion",
          created: Math.floor(started / 1000),
          model: body.model,
          choices: [{
            index: 0,
            message: { role: "assistant", content: text },
            finish_reason: "stop",
          }],
          usage: {
            prompt_tokens: info?.tokens?.input ?? 0,
            completion_tokens: info?.tokens?.output ?? 0,
            total_tokens: (info?.tokens?.input ?? 0) + (info?.tokens?.output ?? 0),
          },
        })
      } catch (error) {
        const message = error?.message || String(error)
        log(`${body.model} failed: ${message}`)
        return sendJson(res, 502, { error: { message, type: "opencode_error", model: body.model } })
      }
    }

    return sendJson(res, 404, { error: { message: `no route for ${req.method} ${url.pathname}` } })
  })

  httpServer.listen(BRIDGE_PORT, HOST, () => {
    log(`bridge listening on http://${HOST}:${BRIDGE_PORT}`)
  })

  fs.writeFileSync(PID_FILE, String(process.pid), "utf8")
  log(`pid file: ${PID_FILE}`)

  let closed = false
  const shutdown = async () => {
    if (closed) return
    closed = true
    httpServer.close()
    try { fs.unlinkSync(PID_FILE) } catch {}
    // Only kill the server this bridge started; a reused one is left alone.
    try { await server?.close?.() } catch {}
    process.exit(0)
  }
  process.on("SIGINT", shutdown)
  process.on("SIGTERM", shutdown)
  process.on("exit", () => {
    try { fs.unlinkSync(PID_FILE) } catch {}
  })
}

main().catch((error) => {
  console.error("[opencode-bridge] fatal:", error)
  process.exit(1)
})
