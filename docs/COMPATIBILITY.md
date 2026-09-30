# Compatibility and integration status

Documentation checked September 30, 2026. This file separates documented APIs from
integrations actually exercised during development.

## Core

Requires Python 3.11+ (`tomllib` is used). No third-party runtime dependencies.
Development was exercised on Linux/Python 3.13.5 and rechecked on Python 3.12.14.
Hosted CI passed on Linux/Python 3.11, 3.12, and 3.13 for publication commit
`d01b1770bcee381f77b54b417874016c1880aaab`. Check GitHub Actions for later revisions.
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

Authenticated CLI execution was **not available in the development environment**.
Tests simulate the CLI's process response and verify flags, strict JSON, event capture,
failed-turn handling and output consumption. This establishes an integration contract,
not proof of actual CLI authentication, model quality, prompt-budget fit, API billing
or sandbox operation. Run the [live Codex smoke workflow](OPERATING_GUIDE.md#live-codex-smoke-workflow) on your own machine.

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

The OpenAI structured grader example has fake-client tests for request shape,
approval/rate prerequisites, usage calculation, served-model checks and invalid
verdicts. It requires the operator to install/pin the official SDK and select a
supported exact model identifier. Live provider compatibility was not tested.

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
[hosted CI](https://github.com/trevordcampbell/codex-eval-lab/actions/runs/36675694829).

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
