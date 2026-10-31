# copilot-model-router

Choose a Copilot model before each Herdr sub-agent. The router prints the command; the orchestrator runs it. Python enforces availability, budget, role bounds and a different provider for `e2e-validator` and `reviewer`.

```bash
uv sync
uv run python scripts/route.py --role dev --story "Add a filter" --available gpt-6-luna,claude-sonnet-5.5 --pane 2 --json
```

The example uses a simulated catalog. For real launches, pass your org catalog with `--available FILE` or `--available live`. Add `--classifier llm` for one economy-model Copilot classification call (30-second timeout, heuristic fallback).

stdout always contains one JSON object, including errors (`error`, `hint`, `exit_code`, `decision_source: null`). Warnings go to stderr. Success includes `model`, `tier`, `level`, `reasons`, `decision_source` and `herdr_command` with `--pane` (default `1`).

| Exit | Meaning |
| ---: | --- |
| 0 | Routed successfully, including LLM fallback. |
| 1 | Invalid arguments, registry/files, or no eligible model. |
| 2 | No eligible model within budget. |
| 3 | Dev family missing/conflicting, or no independent family. |
| 4 | Live catalog discovery failed. |
| 5 | Unknown role. |

[WSL2 installation and orchestrator instructions](docs/integration.md) · [Selection policy](docs/router.md) · [Evaluation and tests](eval/README.md)
