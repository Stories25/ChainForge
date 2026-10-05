# ChainForge — MCP integration architecture

An MCP endpoint for the locally running ChainForge server, focused on **building
workflows**: the agent can output a schema that adds single or multiple nodes in
chains, and manage the connections between nodes. This is version two of
`docs/architecture-mcp.md`; the illustrated version is `architecture-mcp.html`.

Scope note: this document covers only the OpenCode Zen backbone. It does not
touch anything marked deprecated, and does not cover local or third-party model
providers — Azure OpenAI, HuggingFace, Ollama, WebLLM, the browser AI modules.
Those keep their existing adapters and are out of scope.

---

## 1. The chain model — what an agent must know to wire nodes correctly

Before defining tools, the ground truth they operate on. ChainForge flows are
React Flow graphs on disk; the `.cforge` format is:

```json
{
  "flow":  { "nodes": [ ... ], "edges": [ ... ], "viewport": { } },
  "cache": { }
}
```

A **node** is `{ id, type, position, width, height, data }`. A **new node may be
created with `data: {}`** — every node component fills in its own defaults, so
an agent only needs to supply the settings it cares about. The 23 registered
node types (`nodeTypes` in `chainforge/react-server/src/App.tsx`):

| Family | Types |
|---|---|
| Text & input | `textfields`, `upload`, `csv`, `table`, `comment` |
| Prompting | `prompt`, `chat`, `selectvars` |
| Evaluation | `simpleval`, `evaluator`, `processor`, `llmeval`, `multieval` |
| Scripting & flow control | `script`, `join`, `split` |
| Output & visualisation | `inspect`, `vis`, `media` |
| RAG | `chunk`, `retrieval`, `rerank`, `ragchat` |

An **edge** is `{ id, source, target, sourceHandle?, targetHandle? }` — the
React Flow `Edge` type (reactflow.dev, "Edge" API reference). Handles are only
needed when a node has more than one, which in ChainForge is the common case.
The handle ids, verified in the node components:

| Node type | Source handles | Target handles |
|---|---|---|
| `textfields` | `output` | *(none — also renders a hook per template var)* |
| `prompt` | `prompt` | `prompt` (replace whole prompt), one per `{variable}` in the template, `__past_chats` on `chat` |
| `evaluator` / `processor` | `output` | `responseBatch` |
| `vis`, `inspect` | `output` | `input` |

The rule that makes chaining work, and that every tool below enforces:

> **The `targetHandle` of an edge into a prompt node is the template variable
> name.** A `{game}` placeholder in the prompt template renders a target handle
> with id `game` (`chainforge/react-server/src/TemplateHooksComponent.tsx` renders `id={name}` per var).
> An edge `textfields → prompt` with `targetHandle: "game"` is what binds the
> field list to `{game}`. A chain is therefore *declared in the prompt text*
> and *wired by handle id*.

```json
{ "id": "reactflow__edge-textfields-1output-prompt-2game",
  "source": "textfields-1", "sourceHandle": "output",
  "target": "prompt-2",     "targetHandle": "game" }
```

### Frameworks this design builds on

* **React Flow** (xyflow) — the graph model ChainForge is built on. The `Edge`
  contract (`id`, `source`, `target`, `sourceHandle`, `targetHandle`) and the
  handles documentation define what a valid connection is; ChainForge adds the
  convention that target handle ids double as variable names.
* **MCP tools primitive** (spec 2026-07-28) — every tool takes a JSON Schema
  `inputSchema` and is invoked via `tools/call`, so the graph schema below is
  validated the same way as any other tool argument.
* **Schema-validate-merge pattern** from structured-output practice — the agent
  emits a declarative graph against a published schema; the server, not the
  agent, validates and assigns real ids. The agent never invents React Flow
  internals like handle ids or node id formats.

---

## 2. Transport

**Streamable HTTP**, mounted as one route (`/mcp`) in the existing Flask
process. stdio was rejected: it would spawn a second process with its own copy
of `ProviderRegistry` and bind the server's lifecycle to one agent's session.
Streamable HTTP serves many agents, and the endpoint outlives any single
connection. The existing loopback and origin guards of `chainforge/local_access.py` apply
to it unchanged.

---

## 3. Tools exposed

Fifteen tools in three families. The graph-construction family is the focus of
this version; the other two are kept from v1 and trimmed.

| Family | Tools |
|---|---|
| **A. Graph construction & wiring** | `list_node_types`, `get_node_schema`, `build_graph`, `connect_nodes`, `update_node`, `remove_node`, `validate_flow` |
| B. Flows | `list_flows`, `get_flow`, `save_flow`, `delete_flow`, `export_flow_data` |
| C. Models & runs | `list_models`, `run_prompt`, `run_flow` |

All tool names carry the `chainforge_` prefix; it is omitted in the headings
below for brevity. Per Anthropic's guidance, the batch tool (`build_graph`) is
the consolidated path for multi-node work, and the granular tools exist for
small edits; both enforce the same validation.

### A. Graph construction & wiring

#### `chainforge_list_node_types`

The discovery tool — what an agent calls first.

```json
{
  "name": "chainforge_list_node_types",
  "title": "List node types",
  "description": "List every ChainForge node type that can appear in a flow,
with its purpose, its source and target handles, and a one-line summary of its
settings. Call this before building a graph, and chainforge_get_node_schema
for the full settings schema of the type you intend to add.",
  "inputSchema": { "type": "object", "properties": {} }
}
```

Returns, per type: `type`, `family`, `purpose`, `source_handles`,
`target_handles`, `settings_summary`. Example entry:

```json
{ "type": "prompt", "family": "prompting",
  "purpose": "Run a prompt template against one or more models",
  "source_handles": ["prompt"],
  "target_handles": ["prompt", "<each {variable} in the template>", "__past_chats (chat only)"],
  "settings_summary": "template text, models[], n, temperature, system_msg" }
```

#### `chainforge_get_node_schema`

The full contract for one node type.

```json
{
  "name": "chainforge_get_node_schema",
  "title": "Get a node type's schema",
  "description": "Return the full settings schema for one node type: every
field it accepts in `data`, types and defaults, plus its exact handle ids.
Use chainforge_list_node_types first to see valid type names.",
  "inputSchema": {
    "type": "object",
    "required": ["node_type"],
    "properties": { "node_type": { "type": "string" } }
  }
}
```

#### `chainforge_build_graph` — the schema tool

The tool this version exists for. The agent outputs a declarative schema of
nodes and chains; the server materialises real React Flow nodes and edges.

```json
{
  "name": "chainforge_build_graph",
  "title": "Build a graph of chained nodes",
  "description": "Add one or more nodes to a flow and chain them, from a
declarative schema. Each node gets a friendly 'ref' you invent; each chain
connects two refs, optionally 'as' a named variable for prompt templates.
The server validates every type, variable and handle, assigns real node ids
and positions, and merges atomically into the flow. You never write React
Flow edge ids or handle ids yourself. Use chainforge_list_node_types and
chainforge_get_node_schema to check valid types and settings first.",
  "inputSchema": {
    "type": "object",
    "required": ["flow_name", "nodes"],
    "properties": {
      "flow_name": { "type": "string" },
      "nodes": {
        "type": "array",
        "items": {
          "type": "object",
          "required": ["ref", "type"],
          "properties": {
            "ref":      { "type": "string",
              "description": "A short name you invent, unique in this call;
the server maps it to a real node id." },
            "type":     { "type": "string" },
            "position": { "type": "object",
              "description": "Optional {x, y}. Auto-assigned left to right
per chain depth if omitted." },
            "settings": { "type": "object",
              "description": "Type-specific data fields, per
chainforge_get_node_schema. Omitted fields take the node's defaults." }
          }
        }
      },
      "chains": {
        "type": "array",
        "items": {
          "type": "object",
          "required": ["from", "to"],
          "properties": {
            "from": { "type": "string", "description": "Source node ref." },
            "to":   { "type": "string", "description": "Target node ref." },
            "as":   { "type": "string",
              "description": "Target variable for prompt templates: must
match a {variable} in the target's template. Omit for plain
input-handle targets (vis, inspect, evaluator)." }
          }
        }
      }
    }
  }
}
```

A complete call, and what the server does with it:

```json
{ "flow_name": "pokemon-eval",
  "nodes": [
    { "ref": "games", "type": "textfields",
      "settings": { "fields": ["Pokemon", "Legend of Zelda", "Kirby"] } },
    { "ref": "ask",   "type": "prompt",
      "settings": { "template": "What was the first {game} game?",
                    "models": [{ "model": "space-bunny-free",
                                 "provider": "OpenCode Zen" }], "n": 3 } },
    { "ref": "out",   "type": "inspect" }
  ],
  "chains": [
    { "from": "games", "to": "ask", "as": "game" },
    { "from": "ask",   "to": "out" }
  ]
}
```

Server behaviour, in order:

1. **Resolve refs** → real node ids (`${type}-${uuid()}`), exactly as
   `addNode` in `chainforge/react-server/src/App.tsx` does; nodes arrive with `data: {}` plus supplied
   settings, and the component fills the rest.
2. **Validate each node** against the registry — unknown type or unknown
   setting field is a hard error naming the offending ref.
3. **Validate each chain** — the `as` variable must literally appear as
   `{as}` in the target prompt's template; the error lists the variables that
   do exist. Plain chains check the target has an input-capable handle.
4. **Materialise edges** — source handles per the table in §1 (`textfields`
   emits `output`, `prompt` emits `prompt`), target handle set to the `as`
   variable or the type's default input id, with React Flow edge ids.
5. **Auto-position** unpositioned nodes by chain depth, left to right.
6. **Merge and save atomically** through the same path the flow-save route
   uses (`chainforge/security/secure_save.py`).

Result — real ids mapped back to the agent's refs:

```json
{ "created": {
    "nodes": { "games": "textfields-1769...", "ask": "prompt-1769...",
               "out": "inspect-1769..." },
    "edges": ["reactflow__edge-textfields-1769...output-prompt-1769...game",
              "reactflow__edge-prompt-1769...prompt-inspect-1769...input"] },
  "warnings": [] }
```

`build_graph` into an **existing** flow is supported and is how an agent grows
a workflow: refs may point at existing nodes too, by their real id, so chains
can attach new nodes to old ones. Nothing is removed by this tool — use the
granular tools or `save_flow` for restructuring.

#### `chainforge_connect_nodes`

Manage connections between existing nodes — the single-edge counterpart to
`build_graph`'s chains.

```json
{
  "name": "chainforge_connect_nodes",
  "title": "Connect or disconnect two nodes",
  "description": "Add or remove one edge between two nodes in a flow. For
prompt targets, pass 'as' with the template variable to bind; the server
resolves it to the right target handle and refuses if the variable does not
appear in the template. For other targets the default input handle is used
unless you pass an explicit target_handle id.",
  "inputSchema": {
    "type": "object",
    "required": ["flow_name", "action", "source", "target"],
    "properties": {
      "flow_name": { "type": "string" },
      "action": { "enum": ["connect", "disconnect"] },
      "source": { "type": "string", "description": "Source node id." },
      "target": { "type": "string", "description": "Target node id." },
      "as":              { "type": "string", "description": "Template variable to bind." },
      "target_handle":   { "type": "string", "description": "Explicit handle id override." }
    }
  }
}
```

Disconnect accepts the same shape and removes the matching edge; `as` /
`target_handle` are optional there and act as filters when a node pair has
several edges between them.

#### `chainforge_update_node`

```json
{
  "name": "chainforge_update_node",
  "title": "Update a node",
  "description": "Patch one node's settings, prompt template, or position.
Settings are merged, not replaced: omitted fields keep their values. If the
new template text removes a {variable} that an incoming edge was bound to,
the tool reports the now-dangling edge and refuses, unless drop_orphans is
true.",
  "inputSchema": {
    "type": "object",
    "required": ["flow_name", "node_id", "settings"],
    "properties": {
      "flow_name": { "type": "string" },
      "node_id":   { "type": "string" },
      "settings":  { "type": "object", "description": "Merged into data." },
      "position":  { "type": "object", "description": "Optional {x, y}." },
      "drop_orphans": { "type": "boolean", "default": false }
    }
  }
}
```

#### `chainforge_remove_node`

```json
{
  "name": "chainforge_remove_node",
  "title": "Remove a node",
  "description": "Delete a node and every edge attached to it. Reports what
was removed so the agent can rebuild the right chains afterwards.",
  "inputSchema": {
    "type": "object",
    "required": ["flow_name", "node_id"],
    "properties": { "flow_name": { "type": "string" }, "node_id": { "type": "string" } }
  }
}
```

#### `chainforge_validate_flow`

The lint tool — what an agent calls after editing, and what `build_graph` runs
internally before saving.

```json
{
  "name": "chainforge_validate_flow",
  "title": "Validate a flow's graph",
  "description": "Check a flow for graph problems and return them as a list:
template variables with no incoming edge, edges pointing at handles that do
not exist, cycles (ChainForge runs nodes in topological order), and nodes
nothing feeds or consumes. Returns 'ok: true' and an empty problems list when
the graph is sound. Run this after any manual graph edit.",
  "inputSchema": {
    "type": "object",
    "required": ["flow_name"],
    "properties": { "flow_name": { "type": "string" } }
  }
}
```

```json
{ "ok": false, "problems": [
  { "kind": "dangling_variable", "node": "prompt-1769...", "variable": "game",
    "message": "Template uses {game} but no edge targets handle 'game'." },
  { "kind": "cycle", "nodes": ["eval-1", "script-2"],
    "message": "These nodes form a cycle; run order is undefined." } ] }
```

### B. Flows

Kept from v1, trimmed. `save_flow` remains the escape hatch for whole-document
rewrites; agents should prefer the graph tools, which validate handle and
variable wiring and never require knowledge of React Flow internals.

* **`chainforge_list_flows`** — saved flows, newest first. Wraps `GET /api/flows`.
* **`chainforge_get_flow`** — one flow's nodes, edges and settings;
  `response_format: concise | detailed`. Wraps `GET /api/flows/<filename>`.
* **`chainforge_save_flow`** — create or overwrite a whole flow document;
  refuses overwrite without `allow_overwrite`. Wraps `PUT /api/flows/<filename>`
  and its atomic write through `chainforge/security/secure_save.py`.
* **`chainforge_delete_flow`** — delete a flow; cannot be undone.
* **`chainforge_export_flow_data`** — responses from a flow's last run, as
  `text` / `csv` / `json`.

### C. Models & runs

* **`chainforge_list_models`** — the OpenCode Zen catalogue with prices.
  Wraps `ZEN_MODEL_CATALOG` in `chainforge/react-server/src/zenModels.ts`.
  Never exposes API keys. Free models are granted per model, so a listed free
  entry may still be refused at call time; the description says so.
* **`chainforge_run_prompt`** — one prompt, one Zen model, plain-text response.
  Model defaults to `space-bunny-free`. Accepts `{variables}` with a `vars`
  object, `n` responses, `temperature`.
* **`chainforge_run_flow`** — runs a saved flow; limited to single prompt-node
  graphs, because flow execution is orchestrated by the browser client, not the
  server. Returns an explanatory error for anything more connected; an agent
  needing more should chain `run_prompt` calls instead.

---

## 4. Resources and prompts

| Primitive | What to expose | Why |
|---|---|---|
| Resource | `chainforge://flow/<name>` — a flow document | Lets an agent read a flow without a tool round-trip, and lets the host refresh it |
| Resource | `chainforge://node-types` — the node registry as JSON | Cached by the host; cheaper than `list_node_types` on every turn |
| Resource | `chainforge://models` — the Zen catalogue as JSON | Cached by the host |
| Prompt | `chainforge://prompts/eval-gen` | Wraps the `buildGenEvalCodePrompt` template so an agent can request evaluator code the way the browser's EvalGen does |

---

## 5. What is deliberately out of scope

* Nothing marked deprecated in the codebase.
* No local or third-party model providers: Azure OpenAI, HuggingFace, Ollama,
  Together, Bedrock, OpenRouter, DeepSeek, MiniMax, WebLLM, and the in-browser
  AI modules (browser chunkers, embeddings, NLI, rerankers).
* No provider API keys are ever returned by any tool.
* The MCP client **sampling** primitive is not used; it is deprecated as of
  spec `2026-07-28`.

Model access is mediated by the OpenCode Zen custom provider only.

---

## 6. Implementation notes

* **SDK.** Official Python MCP SDK (JSON-RPC 2.0, Streamable HTTP).
* **Mount point.** One route, `/mcp`, in the existing Flask process, sharing
  `ProviderRegistry` and the flows directory by construction.
* **Reuse, do not wrap, the internals.** Graph tools call the same functions
  the Flask routes call; `build_graph` merges and saves through
  `chainforge/security/secure_save.py`, never a private write path.
* **Handle resolution is the single source of truth for wiring.** The
  source/target handle table in §1 lives in one module, used by `build_graph`,
  `connect_nodes` and `validate_flow` alike — the React components render
  whatever that module says.
* **Templating.** `{variables}` are resolved with the same code as
  `chainforge/react-server/src/backend/template.ts`; a literal `{` in
  agent-supplied text must not be read as a variable.
* **Testing.** Contract tests per tool against the Flask test client, plus
  graph-level tests: `build_graph` round-trips a three-node chain and
  `validate_flow` accepts it; a mismatched `as` variable is refused with the
  available variables listed; a cycle is detected. A live smoke test runs
  `chainforge_run_prompt` against a free Zen model.

---

## 7. Changes from v1

| Area | v1 | v2 |
|---|---|---|
| Focus | CRUD on whole flows, plus ad-hoc prompting | Building and wiring graphs: node types, settings, chains, connections |
| Schema output | Agent wrote full flow documents for `save_flow` | Agent outputs a declarative `{nodes, chains}` schema; `build_graph` materialises ids, handles and positions |
| Connections | Only via whole-document `save_flow` | `connect_nodes` / `disconnect_nodes` with variable-name binding and validation |
| Node knowledge | None — the agent had to guess node types | `list_node_types` / `get_node_schema` publish the registry and per-type settings schemas |
| Graph integrity | Not checked | `validate_flow` lints dangling variables, bad handles, cycles, orphans |
| Removed sections | — | Sources for the design; key architectural fact; endpoint topology; security model (transport rationale retained in §2) |
