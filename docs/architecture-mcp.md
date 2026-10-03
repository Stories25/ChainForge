# ChainForge — MCP integration architecture

A new version of the architecture canvas (`architecture-canvas.html`) covering
an MCP endpoint on the locally running ChainForge server, and the tools it
would expose.

Scope note, honoured throughout: this document covers only the OpenCode Zen
backbone. It does **not** touch anything marked deprecated, and does not cover
local or third-party model providers — Azure OpenAI, HuggingFace, Ollama,
WebLLM, Together, Bedrock or the in-browser AI modules. Those keep their
existing adapters and are out of scope here.

---

## 1. Sources for the design

Best practices gathered from three authoritative sources, in the order they
were consulted.

### Anthropic — engineering guidance

* **Writing effective tools for agents** (2025-09-11). The principles that
  shaped the tool list below:
  * *Fewer, thoughtful tools beat many thin wrappers.* Tools that merely wrap
    an endpoint waste an agent's context. Consolidate multi-step chains into
    one call.
  * *Namespacing.* Group tools under a common prefix so agents can tell
    boundaries apart when several MCP servers are connected at once.
  * *Return high-signal context.* Prefer natural-language names over UUIDs;
    expose a `response_format` of `concise` or `detailed` so the agent controls
    verbosity.
  * *Token efficiency.* Paginate, filter and truncate; cap responses (~25k
    tokens is Anthropic's own default for Claude Code).
  * *Prompt-engineer the descriptions.* Tool descriptions are loaded into the
    agent's context and steer behaviour more than anything else.
* **Code execution with MCP** (2025-11-04). Agents should write code against
  tools rather than forcing every operation through a discrete tool call;
  Anthropic measured context overhead falling by up to 98.7%. This argues for
  a bulk `run_flow` tool over a per-node API.
* **Building effective agents** (2025). Tool definitions should carry example
  usage, edge cases, input-format requirements, and clear boundaries from other
  tools.

### MCP specification — modelcontextprotocol.io

From the architecture overview (spec `2026-07-28`, with `2025-06-18` as the
widely deployed earlier version):

* MCP is client–server. An **MCP host** (Claude Desktop, Claude Code, VS Code)
  creates one **client** per **server** connection.
* Two layers. A **data layer** (JSON-RPC 2.0: discovery, capabilities,
  primitives) and a **transport layer**.
* Server primitives are **tools** (executable actions), **resources** (context
  data) and **prompts** (interaction templates), each with `*/list`, `*/get`
  and in the tool case `tools/call`.
* Transports: **stdio** for a same-machine server serving one client, and
  **Streamable HTTP** for a server that many clients reach over a network.
* Every request carries `_meta` with the protocol version and client
  capabilities; `server/discover` returns capabilities, identity and caching
  hints.
* Sampling is deprecated as of `2026-07-28`. A new server should not depend on
  it, and should not use the client-logging primitive.

### Google Cloud — AI security and safety for MCP servers

* Distinguish **human-in-the-middle** from **agent-only** operation. An
  agent-only MCP server takes actions with no approval, so it is vulnerable to
  prompt injection and insecure tool chaining.
* **Least privilege.** Give the agent its own identity and only the permissions
  it needs.
* **Separate data from instructions.** User-supplied or database-derived
  content is data, never instructions. Use strong delimiters and explicit
  instructions so content cannot inject tool calls.
* **Only allow specific tool use.** Review the tool list periodically; servers
  can silently add tools.
* **Audit logging** of all tool invocations.
* **Data recovery.** Plan for the worst case before granting write access.

---

## 2. What ChainForge actually is, for an MCP agent

The single most important architectural fact, and the one that shapes the whole
design:

> **Flow execution lives in the browser, not on the Flask server.**

`chainforge/react-server/src/backend/runGraph.ts` runs `runInOrder` inside the React client. It walks a topological
order of node IDs and calls each node's runner — a `NodeRunner` registered
through `chainforge/react-server/src/backend/nodeRunnerRegistry.ts` and
`chainforge/react-server/src/useNodeRunner.ts`. The Flask server has no
"run flow" route at all. The server is a service layer: persistence, secrets,
Python execution, RAG, file parsing and proxying.

So an MCP server that wants an agent to *operate ChainForge* has two honest
options:

| Option | What it means | Consequence |
|---|---|---|
| **A. MCP wraps the Flask server** | Expose flows, providers, RAG and ad-hoc prompting. | Straightforward, and everything it needs is already a route. It cannot run a saved flow end-to-end, because the orchestrator is in the browser. |
| **B. MCP wraps a headless runner** | Re-implement `runInOrder` in Python against the same node registry. | Full flow execution, but a second implementation of the graph semantics to keep in step with the React one. |

**This document specifies Option A**, plus one bridge tool that runs a single
prompt node directly, which covers most agent workflows without duplicating
the graph engine. Option B is noted as future work.

---

## 3. Where the MCP endpoint sits

The MCP server is a new Python module beside the existing Flask app, mounted
in the same process so it shares `ProviderRegistry`, the flows directory and
the configuration store. The app already serves on `127.0.0.1:8000` by default
(`chainforge/flask_app.py:80`), configurable with `--port`.

```
                       ┌──────────────────────────────────────────┐
 Claude Code /         │  chainforge serve                        │
 Claude Desktop,       │                                          │
 VS Code, Gemini CLI   │  ┌────────────────┐   ┌───────────────┐  │
   │                   │  │ Flask app      │   │ MCP server    │  │
   │ Streamable HTTP   │  │ (browser API)  │   │ (agents)      │  │
   └───────────────────┼─▶│ /app/* /api/*  │   │ /mcp          │  │
                       │  └───────┬────────┘   └──────┬────────┘  │
                       │          │                   │           │
                       │          │  shared, in-process  │        │
                       │          ▼                   ▼        │
                       │  ┌─────────────────────────────────┐   │
                       │  │ ProviderRegistry · flows dir ·  │   │
                       │  │ config store · RAG registries   │   │
                       │  └─────────────────────────────────┘   │
                       │         │                              │
                       │         ▼ OpenCode Zen custom provider │
                       │  ┌─────────────────────────────────┐   │
                       │  │ custom_provider_opencode.py     │   │
                       │  │  transport="sdk" → bridge 8765  │   │
                       │  │  transport="direct" → Zen /v1   │   │
                       │  └─────────────────────────────────┘   │
                       └──────────────────────────────────────────┘
```

### Transport choice: Streamable HTTP, not stdio

MCP offers stdio for a same-machine server and Streamable HTTP for one reached
over a network. Both would work here, because the agent runs on the same
machine as the local ChainForge server.

**Streamable HTTP is specified**, for three reasons:

1. ChainForge's server is already a long-lived HTTP process on
   `127.0.0.1:8000`. The MCP endpoint mounts as one more route, `/mcp`, and
   inherits the existing `chainforge/local_access.py` host and origin guards
   for free. A stdio server would be a second process with its own security
   surface and its own copy of `ProviderRegistry`.
2. It serves many clients, so more than one agent can connect without
   launching more processes.
3. stdio would bind the MCP lifecycle to the agent's, which is the wrong shape
   for a server that must outlive any single connection.

### Security model

Applied from Google's guidance, given that ChainForge binds to localhost and
the browser is the existing client:

* **Bind to loopback only.** `/mcp` must refuse non-loopback connections
  exactly as the rest of the app already does in
  `chainforge/local_access.py`, which checks the host, the `Origin` header and
  a per-session token.
* **Human-in-the-middle by default.** Every mutating tool
  (`save_flow`, `delete_flow`, `run_prompt`) requires an explicit approval step
  before it takes effect. An `agent_only` flag, off by default and set in
  config, lifts this for trusted automation.
* **Least privilege.** The tool list below is read-mostly by design. Nothing
  exposes the provider API keys. No tool returns configuration that contains
  secrets; the existing `/app/fetchEnvironAPIKeys` route reports which key
  names are present, not their values, and no MCP tool even needs that.
* **Separate data from instructions.** Every tool that takes prompt text passes
  it as a template body, never as a system message, and the parameter is
  delimited so flow content cannot be read as an instruction.
* **Audit log.** Each `tools/call` is logged with timestamp, client name,
  tool name, arguments and outcome.
* **No silent tool changes.** The tool list is static per release; the server
  does not advertise `listChanged`.

---

## 4. Tools exposed

Namespaced under a `chainforge_` prefix, per Anthropic's namespacing guidance,
so they are unambiguous next to any other MCP server the agent has connected.

Eight tools. Deliberately few: each targets one high-impact workflow, and the
read tools return high-signal fields rather than raw internal objects.

| # | Tool | Kind | Purpose |
|---|---|---|---|
| 1 | `chainforge_list_flows` | read | Saved flows with last-modified time |
| 2 | `chainforge_get_flow` | read | One flow's graph: nodes, edges, settings |
| 3 | `chainforge_save_flow` | write | Create or overwrite a flow |
| 4 | `chainforge_delete_flow` | write | Delete a flow |
| 5 | `chainforge_list_models` | read | OpenCode Zen catalogue with prices |
| 6 | `chainforge_run_prompt` | write | Run one prompt through one Zen model |
| 7 | `chainforge_run_flow` | write | Run a saved flow (see §2) |
| 8 | `chainforge_export_flow_data` | read | Responses from the last run of a flow |

Detailed contracts follow. All input schemas are JSON Schema, as
`tools/list` requires.

---

### 1. `chainforge_list_flows`

Lists flows in the flows directory. Wraps `GET /api/flows`.

```json
{
  "name": "chainforge_list_flows",
  "title": "List saved flows",
  "description": "List ChainForge flows saved on disk, newest first.
Returns each flow's name, when it was last modified, and its size.
Use this to discover what flows exist before opening one with
chainforge_get_flow.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "limit": { "type": "integer", "default": 20,
                 "description": "Max flows to return, 1-100." }
    }
  }
}
```

Concise result:

```json
{ "flows": [
  { "name": "sentiment-eval", "last_modified": "2026-10-02T13:31:00",
    "size_bytes": 18432 }
]}
```

### 2. `chainforge_get_flow`

Reads one flow's graph. Wraps `GET /api/flows/<filename>`.

```json
{
  "name": "chainforge_get_flow",
  "title": "Read a flow",
  "description": "Read one saved flow and return its graph: the node list
with each node's type and settings, and the edges between them. Use
chainforge_list_flows first to find valid names. Response format defaults
to 'concise', which omits per-node UI positions and cached results.",
  "inputSchema": {
    "type": "object",
    "required": ["flow_name"],
    "properties": {
      "flow_name": { "type": "string",
                     "description": "Flow file name, without the .cforge
extension. Get valid names from chainforge_list_flows." },
      "response_format": { "enum": ["concise", "detailed"],
                           "default": "concise" }
    }
  }
}
```

`concise` returns node type, title and settings. `detailed` adds the React
Flow `position` fields and any cached response payloads, which is what you
want when you intend to write the flow back with `chainforge_save_flow`.

### 3. `chainforge_save_flow`

Writes a flow. Wraps `PUT /api/flows/<filename>`, which already performs an
atomic write through `chainforge/security/secure_save.py`.

```json
{
  "name": "chainforge_save_flow",
  "title": "Save a flow",
  "description": "Create or overwrite a ChainForge flow. Pass the same
graph shape that chainforge_get_flow returns with response_format
'detailed'. Overwriting an existing flow is refused unless allow_overwrite
is true, so an agent cannot destroy work by accident. Always read the flow
first with chainforge_get_flow rather than guessing its shape.",
  "inputSchema": {
    "type": "object",
    "required": ["flow_name", "flow"],
    "properties": {
      "flow_name":   { "type": "string" },
      "flow":        { "type": "object",
                       "description": "Full flow document: nodes and edges." },
      "allow_overwrite": { "type": "boolean", "default": false }
    }
  }
}
```

### 4. `chainforge_delete_flow`

Deletes a flow. Wraps `DELETE /api/flows/<filename>`.

```json
{
  "name": "chainforge_delete_flow",
  "title": "Delete a flow",
  "description": "Delete a saved ChainForge flow. This cannot be undone.
Requires the exact flow name. Refuses to run unless the flow exists.",
  "inputSchema": {
    "type": "object",
    "required": ["flow_name"],
    "properties": { "flow_name": { "type": "string" } }
  }
}
```

### 5. `chainforge_list_models`

Surfaces the Zen catalogue. Wraps `ZEN_MODEL_CATALOG` in
`chainforge/react-server/src/zenModels.ts`, which mirrors
`ZEN_CATALOG` in `chainforge/examples/custom_provider_opencode.py`.

```json
{
  "name": "chainforge_list_models",
  "title": "List OpenCode Zen models",
  "description": "List the models available on the OpenCode Zen backbone,
with their per-1M-token input and output prices and their release dates.
Every model on this list runs through the OpenCode Zen provider; free
models are marked as such. Note that Zen grants free models per model, so
some free entries may be refused at call time even though they are listed
here. Default response format is 'concise'.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "provider": { "type": "string",
        "description": "Optional catalogue category to filter by, for
example 'free', 'openai', 'anthropic'. Omit for all." },
      "response_format": { "enum": ["concise", "detailed"],
                           "default": "concise" }
    }
  }
}
```

`concise` returns `id`, `name`, `category`, and a price label. `detailed` adds
`protocol` and the raw `priceIn` / `priceOut` numbers.

This tool never exposes API keys.

### 6. `chainforge_run_prompt`

The tool an agent will use most. Runs one prompt through one Zen model by
calling the OpenCode Zen custom provider directly, the same path the browser's
`callCustomProvider` route takes.

```json
{
  "name": "chainforge_run_prompt",
  "title": "Run one prompt",
  "description": "Send one prompt to one OpenCode Zen model and return the
text response. This is the fastest way to get a model response without
building a flow. Model defaults to Space Bunny Free, which needs no
balance. Prompts may contain ChainForge template variables in {curly
braces}; supply their values in 'vars'. Temperature defaults to 0.7.",
  "inputSchema": {
    "type": "object",
    "required": ["prompt"],
    "properties": {
      "prompt": { "type": "string",
                  "description": "The prompt text. May contain {variables}." },
      "model":  { "type": "string", "default": "space-bunny-free",
                  "description": "A Zen model id. Get valid ids from
chainforge_list_models." },
      "vars":   { "type": "object",
                  "description": "Values for {variables} in the prompt." },
      "n":      { "type": "integer", "default": 1, "minimum": 1,
                  "maximum": 10 },
      "temperature": { "type": "number", "default": 0.7, "minimum": 0,
                       "maximum": 2 }
    }
  }
}
```

Result:

```json
{ "responses": [
  { "model": "space-bunny-free", "text": "- strawberry\n- mint chocolate chip\n- cookie dough" }
]}
```

The responses are returned as plain text, not as provider-specific JSON, so an
agent does not need to know which Zen protocol the model speaks. That mapping
lives in the provider, as it already does for the browser.

### 7. `chainforge_run_flow`

Included for completeness, and to be explicit about its limit.

```json
{
  "name": "chainforge_run_flow",
  "title": "Run a saved flow",
  "description": "Run a saved ChainForge flow and return the responses of its
terminal nodes. LIMITATION: flow execution in ChainForge is orchestrated by
the browser client, so this tool can only run flows whose graph is a single
prompt node feeding an inspector. Attempting anything more connected returns
an explanatory error rather than a partial result. Build that workflow by
chaining chainforge_run_prompt calls instead.",
  "inputSchema": {
    "type": "object",
    "required": ["flow_name"],
    "properties": { "flow_name": { "type": "string" } }
  }
}
```

The tool validates the graph shape up front and refuses honestly rather than
returning something that looks like a result but is not. Lifting this
restriction is Option B in §2.

### 8. `chainforge_export_flow_data`

Reads back what a flow produced. Wraps the export path used by
`InspectorNode`.

```json
{
  "name": "chainforge_export_flow_data",
  "title": "Export flow responses",
  "description": "Read the responses a flow produced on its last run, as
rows. Use after chainforge_run_flow, or any time you want to inspect what a
flow returned. Returns plain text by default; ask for 'json' if you want the
full per-response record including scores and metadata.",
  "inputSchema": {
    "type": "object",
    "required": ["flow_name"],
    "properties": {
      "flow_name": { "type": "string" },
      "format": { "enum": ["text", "csv", "json"], "default": "text" }
    }
  }
}
```

---

## 5. Resources and prompts

MCP offers resources and prompts alongside tools. Both are worth exposing, but
neither blocks the tool set above, so they are specified only briefly.

| Primitive | What to expose | Why |
|---|---|---|
| Resource | `chainforge://flow/<name>` — a flow document | Lets an agent read a flow without a tool round-trip, and lets the host refresh it |
| Resource | `chainforge://models` — the Zen catalogue as JSON | Cached by the host; cheaper than `chainforge_list_models` on every turn |
| Prompt | `chainforge://prompts/eval-gen` | Wraps the `buildGenEvalCodePrompt` template so an agent can request evaluator code the same way the browser's EvalGen does |

---

## 6. What is deliberately out of scope

Restating the scope constraint so it is unambiguous for whoever implements
this:

* Nothing marked deprecated in the codebase.
* No local or third-party model providers. Specifically **not** covered: Azure
  OpenAI, HuggingFace, Ollama, Together, Bedrock, OpenRouter, DeepSeek,
  MiniMax as standalone providers, WebLLM, and the in-browser AI modules
  (browser chunkers, embeddings, NLI, rerankers).
* No provider API keys are ever returned by any tool. `chainforge_list_models`
  reads the static catalogue and touches no credentials.
* The MCP client **sampling** primitive is not used. It is deprecated as of
  spec `2026-07-28`, and the server has no need to ask the agent's host for a
  completion.

Model access is mediated by the OpenCode Zen custom provider only, which is
the backbone the rest of this repository is already standardised on.

---

## 7. Implementation notes

* **SDK.** Use the official Python MCP SDK, which speaks JSON-RPC 2.0 and
  Streamable HTTP so the transport details stay out of this codebase.
* **Mount point.** One route, `/mcp`, in the existing Flask process. It shares
  `ProviderRegistry` and the flows directory by construction, so there is no
  second source of truth to drift.
* **Reuse, do not wrap, the internals.** `chainforge_save_flow` calls the same
  function the Flask route calls. Duplicating the route's logic would create a
  path that bypasses `chainforge/security/secure_save.py`'s atomic writes.
* **Templating.** `chainforge_run_prompt` resolves `{variables}` with the same
  code as `chainforge/react-server/src/backend/template.ts` so agent behaviour matches what a prompt node does.
  Escaping rules matter here: a literal `{` in agent-supplied text must not be
  read as a variable.
* **Testing.** Each tool gets a contract test against the Flask test client,
  mirroring `scripts/test_opencode_provider.py` for the provider path, plus a
  live smoke test that runs `chainforge_run_prompt` against a free Zen model.

---

## 8. Summary of changes from the previous version

| Area | Previous version (`architecture-canvas.html`) | This version |
|---|---|---|
| Entry points | Browser UI plus Flask routes | Adds one agent entry point, `/mcp` |
| Flow execution | Implicit; described via `chainforge/react-server/src/backend/runGraph.ts` | Made explicit: it is client-side, and the MCP surface is honest about that |
| Model access | Zen provider for prompt nodes | Same Zen provider, now reachable by an agent |
| Security | Host and origin guards on the browser API | Same guards, extended to agents, with least-privilege and approval on mutating tools |
| Tool surface | None | Eight namespaced tools, two resources, one prompt |
