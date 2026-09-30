# Contributing

Open a focused issue or pull request describing the behavior, reproduction,
expected outcome, and a regression test. Do not attach private evaluation data.
The core has no third-party runtime dependencies; adapters can use their own
pinned environments. Preserve the JSON protocol and fail-closed defaults.

```sh
python -m pip install -e .
python -m unittest discover -v
python scripts/sync_skill_references.py --check
python scripts/demo.py --out ../eval-lab-contribution-demo
```

The source and human-operating procedures are both part of the product. Update
`docs/` and run `python scripts/sync_skill_references.py` after changing shared
procedures. Mark live integration results separately from mocked or scripted tests.

Before a release, update CHANGELOG.md and docs/VALIDATION.md, verify local tests,
then run `python scripts/package_release.py --out ../release`. This creates a
hash-verified source archive. No release or GitHub publication occurs implicitly.
