# Security and trust boundaries

## What v0.1 enforces

The controller freezes approved evaluator files and candidate snapshots, checks
fingerprints before/after execution, validates proposal scope, reserves budget
before calls, forbids direct test execution, seals the final selection, escapes
report content, and never automatically mutates the user's working tree. Processes
receive an explicit environment allowlist rather than all host credentials. Commands
use argv with `shell=False`; no model-provided command string is executed as a patch.
Completed trials live transactionally in SQLite. Indeterminate attempts are not
silently retried. The experiment lock is cooperative and never automatically stolen.

These measures prevent many accidents. They are **not a hostile-code security sandbox**.

## Cooperative local mode

Application and grader run as the operator's OS user. A program can read other files
that user can read, inspect parent environments on some systems, mutate state, call
networks, write arbitrary files, or exhaust disk outside stdout/stderr limits. A
separate working directory, process or Codex `read-only` sandbox does not protect
private holdout files from all reads. Hashes detect many changes but are not immutable
if an attacker controls both the filesystem and database. Approval flags are not
cryptographic proof that a human approved anything.

Use local mode only for trusted applications and cooperative agents. Do not give it
production credentials, unreviewed code, sensitive datasets, or attacker-controlled
plugins. Reports/traces may contain sensitive data even when the original requests
were redacted. Gitignore rules are defense in depth, not a data-loss prevention system.

## Docker app-execution mode

With `execution.mode="docker"`, the **application** runs in a container with only its
source, this case's assets, and an output mount. The evaluator, answers and lab state
are not mounted. Network is disabled; root filesystem is read-only; capabilities are
dropped; no-new-privileges, memory/CPU/process limits and a temporary filesystem are
configured. Docker client timeouts are followed by explicit daemon-side container
removal. Prefer a digest-pinned, prebuilt image; no implicit fallback to local mode.

This only isolates app execution. The grader remains trusted host code, and the local
optimizer still needs a separate trust domain to hide evaluation storage from it.
Docker/OS security, image supply chain, resource/disk quotas, mounted paths and runtime
patches are the operator's responsibility. The Docker command construction has unit
tests; actual container execution was not available in the build environment and
must be validated on a Docker-equipped machine before relying on it.

## Stronger optimizer/evaluator separation

1. Keep the controller, immutable grader, answers, test files and database on an
   evaluator machine or under an OS account the optimizer cannot access.
2. Use `export-workspace` to export **only** approved source and development evidence.
   Review that archive and its source for secrets before transfer.
3. Run Codex on a different trust domain, with no evaluator volume, credentials,
   remote shell access, network endpoint or shared parent directory that exposes
   holdouts. Do not mount the Docker socket into the optimizer. Restrict network
   access; public benchmark solutions can contaminate results too.
4. Return the structured proposal, not arbitrary shell instructions. The controller
   validates and imports it using `import-proposal`, then evaluates privately.
5. Only human-approved aggregate results leave the evaluator. Do not feed private
   reports, test transcripts or held-out case lists into the next proposal.

The export/import protocol is implemented. Automatic remote deployment, secret
brokering, hardened multi-tenant evaluation services and policy enforcement across
machines are **not** included. Separate machines/accounts provide the boundary; the
export function alone does not. Repeated validation acceptance feedback still
allows adaptive selection, which is why the final test is separate.

## Credentials and spending

Do not commit `.env`, provider credentials, Codex auth files, raw production data or
state directories. The local Codex adapter may reuse saved CLI authentication. The
lab never reads or copies auth.json. Its events can still contain sensitive task
content. Newer supported CLIs can ignore user config; older ones may load configured
MCP/tools. Inspect those configurations or use a dedicated profile/host. The lab does
not override all possible host policy or promise that a local CLI can read only its
working directory.

Evaluation reservations are scheduling limits conditional on honest, conservative
per-trial cost bounds (including SDK retries and judge calls). They cannot undo an
already-incurred provider charge. When reported cost exceeds its bound, execution
halts and records the overrun. Missing costs/errors are conservatively charged at
least the reservation. Configure provider-side spend limits as well. Codex/custom
optimizer dollar charges are **separate**; call limits/timeouts and token usage are
recorded, but not represented as a universal dollar cap.

## Process and artifact limitations

POSIX subprocess groups are killed on timeout or stdout/stderr overflow. Native
Windows only guarantees terminating the direct process; use WSL or external job
object/container isolation for descendant-heavy agents. Arbitrary disk writes need
OS quotas. The grader can deliberately execute code: it is part of the trusted
computing base. The report never executes app-supplied HTML or SVG; use a separate,
sandboxed artifact viewer for active content. Never open untrusted generated files
in a privileged browser context.
