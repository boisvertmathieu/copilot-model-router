# Repository instructions

Use `uv sync`, then `uv run python scripts/route.py ... --json` for routing.
The router emits one JSON object and prepares commands; only the orchestrator executes Herdr.
Read [the routing policy](../docs/router.md) and [the integration guide](../docs/integration.md).
The paste-ready orchestrator instructions live only in the integration guide.

Preserve availability, budget, role bounds and independent provider families for both e2e validation
and review. Pass the actual dev model using `--dev-model`. Org availability takes precedence over
documented CLI support. Older generations dominated by an eligible newer model must not be chosen.

Run `uv run python -m unittest discover -s tests` and `uv run python eval/run_eval.py` after changes.
Keep eval expectations justified by task behavior and anonymized. Use [the eval guide](../eval/README.md)
for the live catalog and Copilot judge; fake fixtures do not establish real account or Herdr access.
