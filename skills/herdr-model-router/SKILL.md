---
name: herdr-model-router
description: Choose a Copilot model for Herdr; use when asked to launch, open, or start a Herdr agent or session with automatic model choice.
---

# Herdr route

Work non-interactively in Autopilot: do not ask questions or request confirmation.
Require `COPILOT_MODEL_ROUTER_HOME` to point to the router checkout. If unset or
`scripts/route.py` is missing there, clearly report the problem and launch nothing.

Run the wrapper beside this loaded `SKILL.md` (replace the skill directory placeholder
with its actual installed location):

```sh
sh "<skill-directory>/herdr-model-router.sh" --role dev --story "TASK" --available live --classifier llm --pane 1 --name dev-task
```

Use the requested role: `dev`, `test`, `doc`, `e2e-validator`, `reviewer`, or `planner`;
default to `dev` when unspecified. Use the task text and supplied pane/name (defaults:
pane `1`, name equal to the role). Use `--available live` or a real catalog snapshot.
Pass known `--files`, `--diff-stats`, `--story-type`, and either `--max-cost` or
`--budget-profile`. Resolve file arguments to absolute paths before calling the wrapper;
use `--story @FILE` for long tasks. For reviewer and e2e-validator, pass the actual
dev model from its decision JSON as `--dev-model`; never invent it.

The wrapper runs `uv run --project "$COPILOT_MODEL_ROUTER_HOME" python scripts/route.py`
with these arguments from the router checkout. It prints the decision JSON and, only
on exit `0`, executes its `herdr_command` verbatim, preserving quoting, pane, name and
model, in the calling project. Do not launch separately or reconstruct the command. Report the chosen `model`.
If `decision_source` is `"heuristic"`, it prints a one-line fallback notice and still
launches. Each agent needs a fresh routing call.

On nonzero router exit, launch nothing: the wrapper reports the code and JSON `error`
in one sentence with the action below. Use the JSON `hint` for details; stop and report
the blocker if it cannot be corrected without user input. Never relax budget or family bounds.

| Code | Action |
| ---: | --- |
| 1 | Fix input/registry or refresh unavailable models, then retry. |
| 2 | Report the impossible budget; keep the budget bound. |
| 3 | Supply the actual dev model/family or refresh independent models; keep family separation. |
| 4 | Restore Copilot login/license/CLI access and refresh the live catalog, then retry. |
| 5 | Use a supported role, then retry. |
