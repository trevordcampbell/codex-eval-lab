# Security

Read [the threat model and deployment requirements](docs/SECURITY.md) before
running untrusted applications or optimizing against private data.

This alpha release is not an audited security boundary. Local processes and
local Codex read-only mode do not isolate held-out files from the same OS user.
Never put credentials, production transcripts, or private experiment state in
issues, pull requests, or publicly shared reports. Report a suspected vulnerability
privately through the repository owner's available security contact or GitHub's
private reporting facility when it is enabled; do not assume such a facility is enabled.
