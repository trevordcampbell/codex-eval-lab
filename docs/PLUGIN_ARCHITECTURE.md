# Eval Lab: native plugin architecture and distribution

Research date: 2026-10-01. This is an implementation recommendation, with verified protocol shapes and explicit limits. No plugin was installed, registered, uploaded, or published in this research.

## Recommendation

Keep the existing Python standard-library eval engine. Add an optional Python MCP adapter and a separately built, bundled MCP Apps review UI. Ship a local, distributable plugin first, with a browser-based workstation as a functional fallback. Reuse the same read models and review-store API across both UIs. A future hosted edition can reuse the UI and engine, but needs tenant isolation, authentication, hosting, and a separate public-submission package.

The meaningful product is a trace/grader workstation: inspect execution evidence, assign human review labels, compare those labels with grader decisions, inspect disagreements, and export a versioned calibration set. A skill is useful workflow guidance around that product; it cannot itself provide a native panel.

### Architecture boundaries

1. **Core engine:** preserve deterministic CLI behavior and existing on-disk run artifacts. Add stable run, trace, grader, and annotation IDs; expose reusable Python functions instead of shelling out through arbitrary command strings.
2. **Read projection:** summary, paginated trace events, grader evidence, annotation coverage, confusion matrices, disagreements, comparison cohorts, and calibration-set export. The model receives compact summaries and stable IDs, not every full trace by default.
3. **MCP adapter:** optional dependency on the official `mcp` Python SDK; stdio for local installations, Streamable HTTP for a future hosted service. Tools remain useful in headless clients.
4. **UI:** standalone HTML with bundled JavaScript using `@modelcontextprotocol/ext-apps`. Render the initial tool result, then use `app.callServerTool` for selection, pagination, filtering, and save actions. Do not trigger an extra initial data fetch or remount the iframe for every interaction.
5. **Human review store:** immutable or revisioned reviews, with provenance and explicit Save. Model suggestions and imported labels remain distinct from human-reviewed anchors. Keep raw evidence immutable; store review decisions separately.
6. **Skill:** guide users from run selection through evidence review and calibration. Explicitly prohibit the model from claiming its own labels are human judgment.

These divisions follow the documented separation of skills, server authorization/actions, structured results, and optional UI. [Plugin architecture](https://developers.openai.com/plugins/concepts/plugins), [MCP server](https://developers.openai.com/plugins/build/mcp-server), [Skills](https://developers.openai.com/plugins/build/skills)

## Supported UI surfaces, precisely

OpenAI documents MCP Apps UI inside ChatGPT and compatible hosts, not a generic extension API for arbitrary panels in every Codex client. Codex CLI needs text/structured-result fallback. Do not claim that an HTML file or local skill installs a native Codex sidebar. Test actual host capabilities instead of branching on a product name. [Add UI](https://developers.openai.com/plugins/build/chatgpt-ui)

The OpenAI MCP Extensions specification currently describes:

- Global/sidebar and conversation-panel entrypoints on Desktop, Work Web, iOS, and Android
- File viewers, local-file opening, file resources, and composer mentions on Desktop only
- Rich form elicitation on Desktop and Web
- Deep links on Desktop, Web, and iOS; not Android

Its matrix is explicitly described as expected DevDay-launch support, and its Web column means Work browser, excluding classic ChatGPT. Treat installed-host verification as an acceptance test. [OpenAI extension specification](https://github.com/openai/mcp-extensions/blob/main/docs/spec.md)

### Exact UI metadata shapes

Tool that opens a review component:

```json
{
  "_meta": {
    "ui": { "resourceUri": "ui://eval-lab/review-v1.html" },
    "openai/ui": {
      "entrypoints": [{ "type": "thread" }]
    }
  }
}
```

Add `{ "type": "global" }` only when a useful global run catalog exists. Resource content returned by `resources/read`:

```json
{
  "uri": "ui://eval-lab/review-v1.html",
  "mimeType": "text/html;profile=mcp-app",
  "text": "<!doctype html><html>...bundled component...</html>",
  "_meta": {
    "ui": {
      "csp": { "connectDomains": [], "resourceDomains": [] }
    },
    "openai/ui": {
      "preferredDisplayMode": "fullscreen",
      "availableDisplayModes": ["inline", "fullscreen"]
    }
  }
}
```

This is a composition of independently verified fields, not a running server. Inlining the component and using the host bridge avoids external asset/CDN dependencies. Add only exact necessary origins if networking is added. Version the resource URI when its bundle changes. [UI resource guide](https://developers.openai.com/plugins/build/chatgpt-ui), [TypeScript extension examples](https://github.com/openai/mcp-extensions/blob/main/typescript/README.md)

App-only interaction tool:

```json
{
  "name": "save_review",
  "_meta": { "ui": { "visibility": ["app"] } },
  "annotations": {
    "readOnlyHint": false,
    "destructiveHint": false,
    "openWorldHint": false
  }
}
```

The example intentionally omits `resourceUri`: saving a review need not render a new component. `visibility: ["app"]` hides the tool from the model on conforming hosts. A normal shared tool defaults to model-and-app visibility. This is a routing boundary, not authorization or proof that a human clicked. An arbitrary MCP client can still issue requests; enforce authorization in the server. [MCP Apps patterns](https://apps.extensions.modelcontextprotocol.io/api/documents/Patterns.html), [MCP Apps authorization](https://apps.extensions.modelcontextprotocol.io/api/documents/authorization.html)

### Python compatibility

Yes, a Python server can emit this metadata and serve a bundled JavaScript client. OpenAI's Python Pizzaz example uses `mcp.types.Tool(..., _meta=...)`, `TextResourceContents(..., _meta=...)`, `ReadResourceResult`, and typed request handlers. It is an example of Python transport wiring, but some of its widget metadata is legacy `openai/outputTemplate`; use the modern fields above for new code. [Python Pizzaz server](https://github.com/openai/openai-apps-sdk-examples/blob/main/pizzaz_server_python/main.py)

The newer Python extension SDK documents `mcp.server.apps.Apps`, `MCPServer`, `@apps.tool(resource_uri=...)`, and `openai_mcp_extensions.OpenAIExtensions`. The shipped adapter now targets released Python MCP 2.2 and its tested handler API; do not copy older 1.x example handlers unchanged. [Python extension SDK](https://github.com/openai/mcp-extensions/blob/main/python/README.md)

The frontend MCP Apps wire protocol is unchanged between ext-apps 1.x and 2.x, although TypeScript package dependencies changed. Pin and test the versions used for builds instead of assuming current examples and installed packages match. [MCP Apps v2 migration](https://apps.extensions.modelcontextprotocol.io/api/documents/migrate-to-v2.html)

### Optional file viewer, later

Prefer a dedicated `.evaltrace` or `.evalreview` file type rather than claiming every JSON/JSONL file. The authoritative extension spec requires a leading dot in file extensions, despite the short developer guide showing an undotted example.

```json
{
  "ui": { "resourceUri": "ui://eval-lab/file-review-v1.html" },
  "openai/ui": {
    "entrypoints": [{ "type": "file", "extensions": [".evaltrace"] }]
  }
}
```

Its tool input is `{"file":{"name":"run.evaltrace","resourceUri":"host-resource://..."}}`. The URI is opaque. The app reads through host `resources/read`; it must not turn the URI into a filesystem path. Writes are available only for the opened resource when metadata says `writable: true`; `openai/resources/write` supports an `ifMatch` ETag. [File extension and resource APIs](https://github.com/openai/mcp-extensions/blob/main/docs/spec.md#file-extension-entrypoint)

## Package layout and verified configuration

Current official guidance prefers a portable root `plugin.json` plus root `mcp.json`, with fixed `skills/` discovery. `.codex-plugin/plugin.json` remains supported as a compatibility manifest. Root identity is canonical; an `extensions.com.openai` object replaces the compatibility overlay rather than merging with it. [Packaging](https://developers.openai.com/plugins/build/plugins)

Suggested local release shape:

```text
codex-eval-lab/
  plugin.json
  mcp.json
  .codex-plugin/plugin.json       optional older-client compatibility
  .mcp.json                      optional older-client compatibility
  skills/review-evaluations/SKILL.md
  scripts/mcp_server.py
  eval_lab/                      core package, or existing equivalent
  web/dist/review.html            bundled UI
  assets/
  README.md
  LICENSE
```

Keep versions synchronized if generating compatibility files. Do not assume the old bundled validator validates the portable format or all newer fields.

The development repository may keep this package under `plugin/codex-eval-lab/`. The release builder must make that directory self-contained: include the required engine code and UI bundle, or build a self-contained release staging directory. A launcher that imports `../../eval_lab` from the checkout will fail after the plugin is copied into a client cache. Do not install dependencies or modify persistent client configuration as a side effect of importing or listing tools.

Minimal portable manifest, validated against the published JSON Schema:

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
  "name": "codex-eval-lab",
  "version": "0.1.0",
  "description": "Review evaluation traces and calibrate graders."
}
```

Local stdio `mcp.json`, also schema-validated:

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
  "mcpServers": {
    "eval_lab": {
      "type": "stdio",
      "command": "python3",
      "args": ["${PLUGIN_ROOT}/scripts/mcp_server.py"],
      "cwd": "${PLUGIN_ROOT}"
    }
  }
}
```

These demonstrate package schema, not a tested launcher or completed public listing. `python3` and optional adapter dependencies must exist in the executing environment. The local server should fail with a useful installation message when the extra is missing.

Portable `command` is a single executable token, not a shell command. Placeholders expand in `args`, `env` values, and `cwd`, not `command`. `PLUGIN_ROOT` is installed package content; `PLUGIN_DATA` is persistent writable storage. Do not place mutable runs in the plugin installation/cache. Plugin cwd is not the user's project: choose project access explicitly and enforce allowed roots. No secrets belong in packaged `headers` or `env` values. [Agent Plugins MCP configuration](https://agent-plugins.org/plugin-authors/mcp-servers), [MCP runtime](https://agent-plugins.org/client-implementers/mcp-runtime)

Schema sources: [plugin.schema.json](https://agent-plugins.org/schemas/1.0.0/plugin.schema.json), [mcp.schema.json](https://agent-plugins.org/schemas/1.0.0/mcp.schema.json)

## Review integrity and security design

Broader future tool split (the first release deliberately implements a smaller read-only set):

- Model-readable: `list_runs`, `get_run_summary`, `list_traces`, `get_trace`, `get_grader_results`, `get_calibration_report`, `open_review`
- App-only reads: high-volume pagination, polling, detailed evidence chunks
- App-only writes: `save_review`, `revise_review`, `export_calibration_set`; explicit user gesture and revision checks

For a narrower first release, omit all MCP write tools: keep annotation edits inside the UI and export a JSON review file from an explicit user action. That is compatible with a read-only MCP adapter, provided the UI clearly distinguishes unsaved/exported reviews from persisted backend records. The CLI can validate/import the exported file in a separately authorized workflow. This avoids implying that an app-only visibility tag provides write authorization.

For each review store run/trace/grader IDs, reviewer identity where verifiable, timestamp, schema version, label, rationale, evidence references, rubric version, source channel, prior revision, and content hashes. Distinguish proposed, imported, reviewed, adjudicated, and held-out data. Report disagreement and sample size; do not turn a small convenience sample into a general accuracy claim. These are product recommendations, not platform-imposed schemas.

For local deployment: loopback bind, allowed-root containment with resolved paths, symlink traversal rejection, no arbitrary shell/SQL/path tools, HTML escaping, strict request schemas, bounded trace sizes, pagination, server-side file ownership checks, and atomic writes. A local web fallback needs origin/Host checks and CSRF protection. A browser Save action alone cannot cryptographically prove a human if an agent or arbitrary local process can write the same store; describe provenance honestly.

For hosted deployment: per-user/per-tenant access checks on every tool, OAuth 2.1 authorization-code + PKCE, validated issuer/audience/expiry/scopes, resource metadata, and a documented retention/deletion policy. `_meta` is hidden from the model, not secret storage. Treat trace text, grader rationale, tool output, and HTML content as untrusted data, including embedded prompt injections. [Authentication](https://developers.openai.com/plugins/build/auth), [Security and privacy](https://developers.openai.com/plugins/guides/security-privacy)

## Events: useful later, not required for the first release

Use UI polling or manual refresh for an open dashboard. MCP Events is a different capability: ChatGPT subscribes to backend events and receives webhook deliveries. It requires MCP 2.0 (`2026-07-28`), persistent subscription state, and outbound HTTPS. Methods are `events/list`, `events/subscribe`, and `events/unsubscribe`, advertised via `server/discover` capabilities. Current ChatGPT integration does not implement polling/streaming delivery.

Appropriate future event: `evaluation.completed` filtered by project/run. Deliver identifiers and a short status, then fetch the actual record with a read tool. Validate callback destinations against SSRF, verify callbacks, sign Standard Webhooks requests, and make delivery and downstream writes idempotent. One event per POST, maximum 256 KiB. Do not add this infrastructure merely to update visible trace rows. [MCP Events](https://developers.openai.com/plugins/build/mcp-events)

## Distribution: three separate readiness levels

### 1. Local/repository release, achievable now

Ship reproducible source, tests, deterministic UI bundle, versioned plugin package, installation instructions, and a marketplace catalog. A Git-backed marketplace can be added with `codex plugin marketplace add owner/repo --ref <release>`. This is distinct from universal-directory approval. Local marketplace discovery and installation must be tested in an actual supported client; CLI/SDK tests alone cannot establish native-panel rendering.

### 2. Private workspace, permission-dependent

Private developer registration can map an existing registered MCP connection through `.app.json`. Never invent the `plugin_asdk_app...` ID. Workspace publication requires an admin, an intended role audience, and applicable workspace policy. An installation does not automatically deploy or trust hook scripts. Avoid hooks in the first release because the workflow needs no lifecycle interception. [Packaging and workspace distribution](https://developers.openai.com/plugins/build/plugins)

### 3. Public directory, later deployment work

Important current submission restrictions:

- Include MCP in the first submission; adding MCP to an existing skills-only plugin is currently unsupported
- Public ZIPs cannot contain `apps`/`.app.json` references or lifecycle hooks; declare MCP URLs directly
- Only one MCP server can currently be connected per plugin
- Upload, automated checks, review, and deliberate publication are distinct steps

Prepare identity verification and Apps Management Write permission, a public production HTTPS endpoint, domain verification, a real product/support/privacy/terms site, accurate metadata/assets, review credentials with sample data, five positive and three negative tests, and a video walkthrough. Do not put credentials in the ZIP. [Submission requirements](https://developers.openai.com/plugins/deploy/submission)

Remote review requires a production-accessible domain rather than localhost/testing endpoints and an accurate UI CSP. EU-data-residency projects currently cannot submit MCP plugins. Review timelines are not guaranteed. A local engine plus an archive is therefore **distribution-ready locally**, not automatically **public-directory-ready**. [Remote MCP review](https://developers.openai.com/plugins/deploy/app-review)

## Acceptance tests before claiming completion

1. Core regression suite works without the optional MCP dependency
2. Clean environment installs the MCP extra, launches stdio, initializes, lists tools/resources, reads the HTML resource, and calls each read tool
3. Invalid run IDs, path escapes, oversized data, malformed labels, stale review revisions, and duplicate writes are handled safely
4. MCP Apps harness checks initialization, first render, tool-result updates, app-only visibility, host theme changes, teardown, and unsupported-host fallback
5. Browser workstation verifies selecting a trace, inspecting grader evidence, saving/revising a review, reopening it, and producing a changed calibration report
6. Tests distinguish human review from model suggestions and reject annotation provenance escalation through ordinary model tools
7. Bundled manifest/schema validation and packaged-file completeness pass; launch works from installed/cache paths with spaces
8. Real host test separately verifies native rendering, sidebar/thread entrypoints, app-only tool filtering, and optional file operations
9. Public readiness remains blocked until hosting/authentication/domain/account/review requirements are actually completed

## Example-source caveats

The requested [OpenAI Apps SDK examples](https://github.com/openai/openai-apps-sdk-examples) provide useful Python server and React UI wiring. Prefer the standards-first current docs where an example still uses legacy `window.openai` aliases. Do not copy development advice to weaken browser security settings.

The requested [Viticci post](https://x.com/viticci/status/2105318261898322344?s=20) could not be retrieved: the web tool returned HTTP 403 and exact-ID search returned no usable content. No technical claim here relies on that post.


## Implemented local subset

The 0.2 package provides `list_review_packets`, `open_review`, and
`get_calibration_summary`; none accepts filesystem paths or performs writes.
Annotation drafts export explicitly. Detailed calibration disagreement review is
an offline human-only viewer, not a model-facing tool. The bundled stdio server
uses the optional Python MCP 2.2 SDK; Events/HTTP/OAuth are not implemented.

Actual native Codex CLI installation was exercised in an isolated temporary
profile, as were MCP initialize/list/call/resource exchanges. This does not prove
native app UI rendering or public-directory acceptance. Refer to [validation](VALIDATION.md)
for the exact current verification scope and [plugin guide](PLUGIN.md) for use.


The final 0.2 toolchain audit supersedes any earlier SDK-version assumptions in
this research snapshot. See [DEPENDENCIES](DEPENDENCIES.md) for exact selected
versions and compatible transitive pins.
