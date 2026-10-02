# Compatibility and integration status

Unreleased upgrade reviewed October 2, 2026. Historical toolchain checks below
retain their original scope. Separately recorded post-score release checks below
use newly acquired dependencies; they do not relabel the benchmark environment.
This file separates implemented contracts from integrations actually exercised.

## Core

The unreleased source targeting 0.5.0 adds opt-in archive search, counted native
author handoffs and generated exact-JSON controls. Existing configuration files may
omit both opt-ins and retain conservative selection/original oracle control sets.
The proposal JSON and application/grader contracts remain unchanged. New runtime
bytes still invalidate a frozen experiment's runtime fingerprint: source-format
compatibility does not mean in-place state compatibility. Preserve each original
runtime and create a new experiment after upgrading. See [migration](UPGRADE_0.5.0.md).

The frozen comparative implementation ran 510 tests: 507 passed and 3 optional
checks were skipped in Python 3.12.14/MCP 2.2.0. Later native hardening ran 560
tests on Python 3.12.14/MCP 2.2.0 (557 passed, 3 skipped) and on Python
3.14.8/MCP 2.2.0/OpenAI 3.23.0 (559 passed, 1 disabled installed-CLI check).
The final integrated runtime/test bytes match the separately tested `ff3f164`
revision: **577 tests passed, no skips**, on the latter release environment,
including the Codex 0.160.0 help-only argument check. None of these later revisions
was inserted into the frozen study. Earlier checks retain their historical scope.
Consult exact-commit GitHub Actions results for hosted CI; local checks do not
establish its status.

Requires Python 3.11+ (`tomllib` is used). No third-party runtime dependencies.
The 0.2 implementation was tested on Linux/Python 3.11.16, 3.14.7, and a
source-built 3.14.8 with the optional MCP/judge SDKs installed. The dependency-free
core was also checked separately. CI covers stable Python 3.11–3.14 with latest
available patch selection. See [validation](VALIDATION.md) for exact counts and
[the toolchain audit](DEPENDENCIES.md) for source-build and hosted-artifact limits.
macOS should use the POSIX path but was not executed here. Native Windows kills only
the immediate timed-out child; use WSL or a properly isolated worker for agents.

Applications can be written in any language executable from argv. Environment,
interpreter versions, dependencies and source entrypoints remain the operator's
responsibility. `{python}` resolves to the controller's Python (or `python3` inside
Docker); use an explicit pinned interpreter/adapter for other environments.

## Codex

The adapter uses the documented CLI contract, not a model-specific API or a session
memory trick:

```sh
codex exec --sandbox read-only --json --skip-git-repo-check \
  --output-schema <schema> --output-last-message <proposal> -
```

A fresh invocation receives development evidence through stdin. The trusted CLI
writes its structured last message; the model is not granted workspace-write access.
The adapter checks `codex exec --help` for required flags. When available it also
passes `--ignore-user-config`; absence is recorded in execution metadata. There is
no deprecated `--full-auto` or unrestricted-access fallback. An explicit model is
optional; the selected account/CLI default applies otherwise.

Tests simulate the CLI process response and verify flags, strict JSON, event
capture, failed-turn handling and output consumption. Stable Codex 0.159.3 and
0.160.0 help/argument checks made no model request. A separate October 2 check
confirmed existing ChatGPT authentication on 0.160.0, then made one bounded
`automate` attempt. Its author process failed during in-process app-server
initialization with a read-only-filesystem error, before any model events,
proposal or usage. The counted failure and unopened final test were preserved.
The precise failing subsystem is unknown. See the
[sanitized integration record](validation/codex-cli-0.160.0-integration.json).
Live one-command completion, model quality, inference cost and successful runtime
sandbox operation remain unverified. Incomplete/error JSONL streams are rejected
even when a proposal file exists. Run the
[live Codex smoke workflow](OPERATING_GUIDE.md#live-codex-smoke-workflow) in an
appropriately provisioned environment.

The native `start-native` / `prepare-turn` / `submit-turn` / `evaluate-turn`
alternative uses protected plan initialization and a counted local file handoff.
The active-only evaluation command has no optimizer-dispatch fallback, and final
admission blocks active rounds and unresolved trial/author work. An authorized
host must actually dispatch the author and preserve admission,
elapsed-time and available usage evidence. This bridge can operate without the
standalone CLI; it neither calls that CLI nor verifies a live `automate` integration.
Its public workspace must remain available and unchanged through submission;
authoritative controller receipts survive cleanup after successful submission.

Saved authentication remains local to your Codex installation. The adapter does not
copy `auth.json`. Treat HOME, CODEX_HOME and any custom agent plugins/settings as part
of your trust boundary. Existing CLI integrations may have side effects; inspect them.

## Skills

Each skill has `SKILL.md`, optional `agents/openai.yaml`, and its own reference files.
The installer supports repository `.agents/skills` and user `~/.agents/skills`.
Explicit `$skill-name` is documented for supported CLI/IDE workflows; interfaces
with a different picker should use that picker. The engine remains an ordinary
local CLI; a cloud Codex environment needs the package, executable tools and data
provisioned there. Installing skills on one computer does not install them everywhere.

## Optional provider grader

The optional judge extra retains its declared `openai>=3.22.1,<4` range; the
current release lock pins **OpenAI 3.23.0**. Its structured grader tests passed with
real-SDK offline transports on the separate Python 3.14.8 release environment,
including both installed-SDK checks. The prior 3.22.1 lock is preserved verbatim
under `requirements/history/`. Tests cover request shape,
approval/rate prerequisites, usage calculation, served-model checks and invalid
verdicts. It requires the operator to install/pin the official SDK and select a
supported exact model identifier. Live provider compatibility was not tested.

## Plugin transport and UI

The optional plugin uses the current stable Python MCP 2.2 SDK and pinned MCP Apps
bridge 2.0.3. Tests exercise both modern and legacy client protocol paths, strict
arguments, read-only tools and the zero-argument thread entrypoint. The plugin
includes portable and compatibility manifests and a relocatable local catalog.
Native CLI installation was tested in an isolated profile. UI behavior is tested
with DOM and real released App/AppBridge protocol harnesses; actual native visual
rendering, host download behavior and public-directory registration remain
separately unverified. See [plugin guide](PLUGIN.md).

## Docker

The application runner constructs a restricted no-network/read-only container command,
mounting application source read-only and a dedicated artifact directory read-write.
A timeout explicitly removes the daemon-side container. Docker must be installed and
an operator-approved image available. Prefer a digest-pinned image. API-calling apps
will not work with the supplied no-network policy; design an explicit trusted broker
instead of silently enabling unrestricted network access.

Command construction and missing-runtime behavior are tested. Container execution,
image compatibility, Docker Desktop mounts and resource enforcement are not tested
in this release environment. Docker isolates the application only, not the optimizer,
grader or host credentials. See SECURITY.md.

## GitHub

The publishing script uses the documented `gh repo create --private --source --push`
path. It requires local GitHub CLI authentication and new-repository permissions.
Its manifest checks and refusal behavior are unit tested; the script itself has
not been live-tested. The public repository was published through a separate
authenticated GitHub workflow, with full file-integrity verification and successful
[historical hosted CI](https://github.com/trevordcampbell/codex-eval-lab/actions/runs/36675694829).
That run does not establish CI for this unreleased source or later packaging commit.

## Official references

- https://developers.openai.com/codex/skills
- https://developers.openai.com/codex/noninteractive
- https://developers.openai.com/codex/cli
- https://cli.github.com/manual/gh_repo_create

Current compatibility should be checked against these sources before upgrading a
production installation. Pin environments and rerun tests; do not reuse an old
baseline after changing the runtime or provider/model assumptions.

A failed remote push after repository creation can leave a private repository behind.
The publishing script never deletes remote repositories to undo an uncertain outcome.
