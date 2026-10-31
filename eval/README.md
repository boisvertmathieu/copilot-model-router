# Router evaluation

The 104 synthetic cases call the real router and assert levels, tiers, budgets, family separation,
availability and exit codes. They check properties rather than pinning model IDs. No network or
inference is used by default. From the checkout:

```bash
uv run python -m unittest discover -s tests
uv run python eval/run_eval.py
```

The report is generated at `eval/.reports/report.md` (gitignored); the default run does not modify
tracked files. Override it with `--report PATH`, use `--json` for structured output, or filter with
`--filter role/reviewer` or `--filter id/budget`. `--judge --fake-judge` adds the deterministic CI judge.
Exit 0 means all executed cases and invariants pass; failures return nonzero.

On an authenticated workstation, rerun in these **three commands**. Replace `gpt-6-luna` in the
third command with an economy model allowed by your org if needed. Copilot CLI must already be
installed and logged in:

```bash
uv sync
uv run python eval/run_eval.py --refresh --available live
uv run python eval/run_eval.py --available live --judge --copilot --judge-model gpt-6-luna
```

`--refresh` updates the gitignored `models.local.json` registry before the live run; tracked
`models.yaml`, `models.json` and upstream snapshots remain unchanged. Router and eval prefer this
local registry when present. Use `sync_registry.py --write-registry` only to explicitly regenerate
the tracked registry and snapshots. Live
availability restricts every scenario; scenarios that add fictitious models are skipped in this mode.
Insufficient model coverage can cause scenario failures. New org IDs without a tier or missing active
registry models fail the drift check; refresh the catalog and inspect its metadata. Without live
input, drift is reported as skipped and makes no account-access claim.

The Copilot judge runs through the authenticated CLI, validates its JSON score and justification,
and requires an average score of at least 0.85 (`--threshold` overrides it). Judge errors count as
zero and fail the run. `--timeout` defaults to 30 seconds per operation. Fake judges and fake CLI
fixtures exercise failures, timeouts and parsing locally. Real org access, real Copilot inference
and real Herdr launches require workstation verification.
