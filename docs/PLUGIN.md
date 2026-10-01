# Local plugin and human review UI

Codex Eval Lab 0.2 ships a **local plugin source and reproducible distribution
builder**, not a hosted service. It combines the four evaluation skills with
three read-only MCP tools. A bundled MCP Apps review component appears in hosts
that support that protocol. Codex CLI and hosts without UI support retain skills,
structured tool summaries, and offline HTML exports.

Do not interpret a plugin installation as proof that every Codex client can open
an arbitrary native panel. UI availability depends on the host. No public app ID,
OAuth registration, remote HTTPS endpoint, or directory submission is included.

## Build a distributable

The Python core remains standard-library-only. Python 3.11+ is required. To run
the optional MCP transport, install the official SDK extra into the Python
environment that the plugin's `python3` command will use:

```sh
python -m pip install '.[plugin]'
python scripts/build_plugin.py --out /a/new/plugin-build
python scripts/validate_plugin.py /a/new/plugin-build/catalog/plugins/codex-eval-lab
```

For the checked dependency set, install the optional hash-locked dependencies
first, then the package:

```sh
python -m pip install --require-hashes -r requirements/plugin.txt
python -m pip install -e '.[plugin]'
```

The output includes:

- `catalog/plugins/codex-eval-lab/`: a relocatable plugin containing the core, bundled UI, skills,
  public documentation, examples, and helper scripts
- `catalog/.agents/plugins/marketplace.json`: a disposable, local catalog
- `codex-eval-lab-plugin-v0.2.0.zip`: deterministic archive of the catalog
- A SHA-256 checksum and per-file `PLUGIN_MANIFEST.json`

A build requires a fresh output directory and rejects source symlinks. It never
installs a plugin, writes a personal marketplace, discovers credentials, starts a
model run, or publishes anything. The source template at `plugin/codex-eval-lab/`
is not itself the complete installable artifact: build it first.

The root `plugin.json` / `mcp.json` implement the portable plugin contract.
`.codex-plugin/plugin.json` / `.mcp.json` provide compatibility metadata. Both
launch the same bundled `scripts/mcp_server.py` using `${PLUGIN_ROOT}`; the
launcher never reaches back into the original repository.

### Optional local Codex installation

The generated catalog is ready to add locally. With a Codex version supporting
local plugins, run:

```sh
codex plugin marketplace add /a/new/plugin-build/catalog
codex plugin add codex-eval-lab@codex-eval-lab-local
codex plugin list --json
```

Alternatively, extract the ZIP and add its `codex-eval-lab-local/` directory as
the catalog. Its generated entry uses the canonical `./plugins/codex-eval-lab`
path and `AVAILABLE` / `ON_INSTALL` policies. Creating that disposable output is
not installation and never changes the user's personal marketplace.

These commands change your local plugin configuration; run them only when you
intend to install it. A new conversation may be needed to discover installed
skills/tools. This explicit catalog is separate from a personal marketplace.

An isolated installation with temporary HOME and CODEX_HOME was tested on the
available CLI: marketplace add, plugin add, and plugin list returned version
0.2.0 installed and enabled. That test did not use the user's normal
configuration, make a model call, authenticate an account, or prove native UI
rendering in every host.

## Select an intentionally narrow artifact scope

**The default review-packet catalog is empty.** Installing the plugin does not grant it a home
directory scan. Select a review-only directory or explicit files at startup:

```sh
eval-lab-plugin --packet /approved/review/packet.json --check
eval-lab-plugin --workspace-root /approved/review --check
eval-lab-plugin --packet /approved/review/packet.json \
  --calibration /approved/review/evidence.json
```

`--check` validates inputs and prints only the safe catalog. Without it the
process speaks MCP over stdio; it does not bind a TCP port. A selected root reads
only direct children named `packet.json`, `*.packet.json`, `*.calibration.json`,
or `*.evidence.json`. It does not recurse or inspect other JSON files. Explicit
files may have other names; if a root is also selected they must be inside it.
The limits are 5 MiB per artifact and 200 selected artifacts.

For a native plugin host, configure the server's environment with an explicit
`EVAL_LAB_REVIEW_ROOT` value, or add `--workspace-root` and the chosen absolute
directory to the server args in the local `mcp.json` and compatibility
`.mcp.json` before building/installing. Do not assume a desktop app inherits a
shell's custom environment. Keep the selection narrow and restart the server to
register newly created artifacts. No model tool can expand this selection.

Symlinks are rejected; POSIX leaf reads use `O_NOFOLLOW` and file-descriptor
checks. Files are validated and snapshotted once at startup. Later calls use
registered SHA-256 IDs and do not reopen model-supplied paths. This is defense in
depth in a **cooperative local** workflow, not a guarantee against a malicious OS
user racing ancestor directories or editing both data and hashes.

## What each tool can do

| Tool | Result | Write or execution capability |
| --- | --- | --- |
| `list_review_packets` | Registered packet IDs, tuning counts, calibration IDs and qualified status | None |
| `open_review` | Empty args open the registered-packet chooser; a selected packet ID opens tuning-only traces in `_meta` | None |
| `get_calibration_summary` | Per-criterion aggregate counts, failure-positive rates and bounds, threshold basis, confidence, and verification caveat | None |

No arbitrary-file, private-data toggle, command, approve, save, run, or label tool
exists. A calibration report alone is an unverified record: its claimed result
cannot become `ready` in the MCP projection. Evidence bundles are recomputed,
but that does not verify the current external evaluator's identity or authorize
execution. Point-estimate-only calibration is not readiness evidence.

Only tuning traces go into the MCP review payload. Calibration-validation IDs,
inputs, outputs, reasons and private labels are excluded from both the model
summary and UI `_meta`. The resource itself contains no packet. `_meta` is a
host/model presentation distinction, **not encryption, authentication, or a
hostile-client boundary**. Assume the connected host can inspect any data sent
to it. There are no app-only write tools to mistake for authenticated human
review.

## Human review, offline first

```sh
eval-lab review render --packet /approved/review/packet.json --out review.html
```

Open the generated file in a browser. This initial, blind review contains only
tuning traces and no judge verdicts. Enter pass/fail/uncertain, rationale,
observed failure modes, and your reviewer name. Filtering and navigation preserve
your selections. Export JSON before closing; the page warns about unsaved edits.
You can restore an exported draft locally. No browser storage autosave or server
upload occurs.

The download is an **unsealed draft**, with `kind: "annotation_draft"`, the packet
hash, entered reviewer name, and trace-bound annotations. It never automatically
claims human provenance or execution approval. Finish all tuning annotations and
import through the CLI with explicit human-review confirmation. The CLI validates
hashes, completeness, schema and reviewer identity consistency; an entered name
still is not authenticated proof of who did the work.

After reviewing failures and freezing the rubric, add `--rubric rubric.json` to
render criterion labeling. This separate offline mode includes calibration
validation for human labeling against the frozen criteria. Its draft kind is
`criterion_labels_draft`, additionally bound to the rubric hash. Do not provide
that private validation view to the optimizer or rubric author.

### Inspect the calls the judge got wrong

```sh
eval-lab calibration-review --packet packet.json --rubric rubric.json \
  --labels labels.json --judge-config judge-config.json --outputs outputs.json \
  --policy policy.json --out calibration-review.html
```

This dedicated read-only viewer recomputes the report from its source artifacts.
It filters by criterion, partition, missed failure, false alarm, unresolved row,
or agreement. Each selected call shows its actual input/output/trace alongside
separate human verdict/rationale and judge status/reason. Missing decisions stay
visible. Per-criterion support and group-level bounds accompany the rates.

The full disagreement viewer is deliberately offline-only. Its
calibration-validation examples do not travel through the model-facing MCP
server. These are development calibration partitions; importing experiment
validation/final-test traces is forbidden by the packet schema.

All viewers inline their assets and use a restrictive Content Security Policy.
Untrusted trace text is assigned with `textContent`, never active HTML, media,
links, or code. Static exports do not initialize an MCP bridge or make network
calls. Treat exported files as potentially sensitive data; they contain the
visible evidence and must not be publicly hosted by default.

## Rebuild and test the UI

The committed browser bundles are included in the Python wheel and local plugin.
Node is needed only to rebuild/test them, not to use the Python core or open an
export. From the source repository:

```sh
cd plugin-ui
npm ci --ignore-scripts
npm run build
npm test
```

The build pins `@modelcontextprotocol/ext-apps` 2.0.3 and esbuild through the
lockfile and includes notices for every bundled dependency. The MCP transport
uses the optional official Python `mcp>=2.2.0,<3` API, tested with 2.2.0. Low-level handlers
use the v2 constructor registration and snake-case Python fields, with explicit
input validation because v2 no longer supplies decorator-based schema checks. The
browser component registers its tool-result handler before connecting, then
consumes `_meta` without an extra initial fetch.

Validation covers Python unit/adversarial tests, real legacy-handshake and modern-auto stdio MCP
resource/tool exchanges, portable and compatibility manifest schemas, relocated
launching, deterministic archives, and DOM-level annotation/disagreement
interactions. Cloud-browser loopback navigation was blocked in the build
environment; visual browser and real hosted-iframe download behavior remain
unverified. A host may restrict downloads; the offline export remains the
fallback.

## Hosted publication is a separate project

A public remote plugin needs an explicitly authorized HTTPS deployment,
authentication/authorization, per-user storage and isolation, sensitive-data
review, support/privacy information, and directory review. A local source plugin
or a passing manifest validator does not satisfy those requirements. No such
deployment or registration is performed here.

### Official references

- [Portable plugin packaging](https://developers.openai.com/plugins/build/plugins)
- [Local MCP configuration](https://agent-plugins.org/plugin-authors/mcp-servers)
- [Optional MCP Apps UI](https://developers.openai.com/plugins/build/chatgpt-ui)
- [MCP Apps bridge quickstart](https://apps.extensions.modelcontextprotocol.io/api/documents/quickstart.html)
- [MCP Apps authorization boundaries](https://apps.extensions.modelcontextprotocol.io/api/documents/authorization.html)
- [Official Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Official v2 migration guide](https://py.sdk.modelcontextprotocol.io/migration/)
