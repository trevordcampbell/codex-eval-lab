# Toolchain audit — October 1, 2026

The 0.2 upgrade targets the current compatible **stable** releases below. A newer
prerelease or an incompatible transitive major is not substituted merely to obtain
a larger version number. This is a dated verification, not a promise of automatic
future upgrades.

| Component | Selected version / policy | Primary source |
| --- | --- | --- |
| Python core | Python 3.11+; test current stable 3.14.8 and supported older minors | [Python 3.14.8](https://www.python.org/downloads/release/python-3148/) |
| MCP Python SDK, optional plugin | 2.2.0 stable; supported major range 2.x | [PyPI](https://pypi.org/project/mcp/2.2.0/) |
| OpenAI Python SDK, optional judge | 3.22.1 stable; supported major range 3.x | [PyPI](https://pypi.org/project/openai/3.22.1/) |
| Codex CLI compatibility check | 0.159.3 stable | [npm package metadata](https://registry.npmjs.org/@openai/codex/latest) |
| MCP Apps bridge | 2.0.3 | [npm metadata](https://registry.npmjs.org/@modelcontextprotocol/ext-apps/latest) |
| Node build/test runtime | 26.10.0 Current; also test 24.21.0 LTS | [Node Current](https://nodejs.org/en/blog/release/v26.10.0), [Node LTS](https://nodejs.org/en/blog/release/v24.21.0) |
| npm | 12.2.0 | [npm metadata](https://registry.npmjs.org/npm/latest) |
| esbuild | 0.28.2 | [npm metadata](https://registry.npmjs.org/esbuild/latest) |
| jsdom | 30.1.1 | [npm metadata](https://registry.npmjs.org/jsdom/latest) |
| pip | 26.2.1 | [PyPI](https://pypi.org/project/pip/26.2.1/) |
| setuptools | 84.0.0, exact build backend | [PyPI](https://pypi.org/project/setuptools/84.0.0/) |
| build | 1.6.1 | [PyPI](https://pypi.org/project/build/1.6.1/) |
| wheel | 0.48.0 | [PyPI](https://pypi.org/project/wheel/0.48.0/) |
| actions/checkout | 7.0.1, pinned commit | [Release](https://github.com/actions/checkout/releases/tag/v7.0.1) |
| actions/setup-python | 7.0.0, pinned commit | [Release](https://github.com/actions/setup-python/releases/tag/v7.0.0) |
| actions/setup-node | 7.0.0, pinned commit | [Release](https://github.com/actions/setup-node/releases/tag/v7.0.0) |

## Reproducibility

The standard-library core still has no third-party runtime dependencies. Optional
SDKs are isolated behind extras; their current transitive resolutions are recorded
with hashes in `requirements/plugin.txt` and `requirements/judge.txt`. Packaging
uses `requirements/ci.txt`. Install with `--require-hashes` to reproduce the
recorded resolution, then install the local project. `pip check` detects dependency
conflicts. The build backend uses modern SPDX license metadata.

The UI has an exact `package-lock.json`, `packageManager`, engine requirements and
`.node-version`. Its compiled browser assets are committed and included in the
wheel/plugin. CI rebuilds them and rejects a difference. Node/npm are build tools;
opening a standalone review page does not require Node or network access.

npm 12's lifecycle-script controls are respected. Only the declared esbuild version
receives its narrowly scoped install-script allowance. There is no blanket
permission to execute arbitrary dependency scripts.

## Deliberate compatibility pins

Latest stable Pydantic 2.13.5 requires `pydantic-core==2.46.5` exactly. That pin is
retained even though a numerically newer pydantic-core release exists; upgrading it
independently would violate the upstream contract. The JavaScript lock similarly
respects dependency ranges required by current upstream packages. An `npm outdated`
entry for a newer incompatible transitive major is not a reason to force an override.

Python 3.15 is still a prerelease at this audit date and is not the default target.
The official Actions Python binary manifest initially lagged the Python.org 3.14.8
source release and offered 3.14.7. CI requests each supported stable minor with
`check-latest: true`, so it uses the newest available patch without pretending a
missing hosted artifact is available. The local validation record separately
identifies source-built 3.14.8 and the actual hosted versions.

## Compatibility is tested, not inferred

MCP 2 required a real API migration: constructor-based request handlers, current
result types, explicit argument validation, and tests through both modern and
legacy stdio clients. Codex event handling was hardened to require an actual
completed turn and valid usage, while preserving unknown future object events.
A present proposal file cannot conceal a failed or truncated event stream.

The stable Codex CLI checks use isolated configuration and `--help`; they do not
start a model turn. Optional judge serialization uses the real released SDK with
an offline mock transport. Neither substitutes for authenticated live-provider
validation. See [validation](VALIDATION.md) for exact results and remaining limits.
