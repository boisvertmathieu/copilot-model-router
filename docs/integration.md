# WSL2: install and connect the orchestrator

In a WSL2 shell, install Git, uv and Python 3.10+ as prerequisites. Real launches also need
Copilot CLI authenticated with `copilot login`, and Herdr with an existing pane.
Set `ROUTER_REPOSITORY_URL` to this repository's clone URL, then run:

```bash
git clone "$ROUTER_REPOSITORY_URL" copilot-model-router
cd copilot-model-router
uv sync
```

## Refresh the org catalog

```bash
uv run python scripts/list_copilot_models.py --output copilot-models.local.json
uv run python scripts/sync_registry.py --from-cli-models copilot-models.local.json
```

The catalog and the generated `models.local.json` registry are gitignored. Sync writes this local
registry by default, leaving tracked `models.yaml` and `models.json` unchanged. The router and eval
prefer the sibling `.local.json` registry when present, including with `--registry PATH`.
`eval/run_eval.py --refresh` follows the same rule, even when Copilot discovery is unavailable.
Remove `models.local.json` to return to the bundled registry. Maintainers can explicitly request
`sync_registry.py --write-registry` to regenerate the tracked YAML/JSON and documentation snapshots.

Sync uses public GitHub docs for metadata; the org catalog wins on availability and CLI support.
An explicit `--available` overrides stale saved availability with the stderr warning
`registre périmé, relancer la sync`. IDs absent from the registry still need sync before selection.
Refresh before a new session or after org model changes.
`--available live` fetches the current catalog on each routing call, but new models still need sync
for their metadata. No additional service or API key is required.

Without account access, use this simulated catalog and the bundled documentation snapshots instead:

```bash
uv run python -c 'import json; from pathlib import Path; Path("copilot-models.local.json").write_text(json.dumps(["claude-sonnet-5.5", "gpt-6-luna", "gemini-4-argon"]))'
uv run python scripts/sync_registry.py --upstream-dir upstream --from-cli-models copilot-models.local.json
for role in dev test doc e2e-validator reviewer planner; do
  uv run python scripts/route.py --role "$role" --story "Add a filter" --dev-model claude-sonnet-5.5 --available copilot-models.local.json --pane 1 --json
done
```

This smoke check prints one decision per role and starts no agents. A simulated catalog does not
establish account access. Replace it with the real snapshot before a launch.

## Skill

The `herdr-route` skill chooses a model and opens the requested Herdr agent/session in
Autopilot without questions. It needs the same authenticated Copilot CLI, uv, and existing
Herdr pane as the examples below. Set the checkout's absolute path in the shell that starts
Copilot (and persist this export in your shell configuration):

```bash
export COPILOT_MODEL_ROUTER_HOME="/path/to/copilot-model-router"
```

Install the whole skill directory, including its tiny launch wrapper. Choose personal scope
for all projects (`~/.copilot/skills/herdr-route/`):

```bash
mkdir -p "$HOME/.copilot/skills"
cp -R "$COPILOT_MODEL_ROUTER_HOME/skills/herdr-route" "$HOME/.copilot/skills/herdr-route"
```

Or run these commands from the target project for project scope (`.github/skills/herdr-route/`):

```bash
mkdir -p .github/skills
cp -R "$COPILOT_MODEL_ROUTER_HOME/skills/herdr-route" .github/skills/herdr-route
```

For a symlink install, replace the chosen `cp -R` command with `ln -s` using the same source
and destination. Install into an absent destination; copies must be updated after skill changes.
Copilot discovers both locations; see its [skill command reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference#managing-skills-non-interactively).

Smoke test from the target project after installation (two commands). Confirm that the first
lists `herdr-route`, then run the second with a real task and an existing pane:

```bash
copilot skill list
copilot --autopilot --allow-all --no-ask-user -p 'Use /herdr-route to open one Herdr session for role dev, pane 1, name dev-filter, task: add a list filter. Use the live catalog and LLM classifier. Report the chosen model.'
```

Expect decision JSON followed by a Herdr launch with exactly its `herdr_command` model.
A heuristic fallback prints a notice and still launches. Missing/invalid
`COPILOT_MODEL_ROUTER_HOME` launches nothing. Nonzero router exits launch nothing and report
the code, JSON `error`, and the skill's action for that code, following the exit meanings
in the instructions below. Relative task/catalog file paths must be made absolute because
the wrapper runs routing from the router checkout; Herdr launches from the calling project.
`scripts/route.py` itself only prints JSON.

## Paste into the orchestrator instructions

Add the following block to `~/.copilot/copilot-instructions.md`. Replace `ROUTER_DIR` with the
absolute path to your checkout. These instructions apply to each sub-agent launch:

```text
Before every sub-agent, call the model router from ROUTER_DIR:
uv run python scripts/route.py --role ROLE --story "TASK" --available copilot-models.local.json --pane PANE --name NAME --json

Roles: dev, test, doc, e2e-validator, reviewer, planner. Call separately for every sub-agent;
do not reuse a previous task's choice. Use --story @FILE for longer tasks. Pass --files,
--diff-stats, and --story-type when known. PANE must be a positive integer. NAME must have 1 to 64
letters, digits, dots, underscores or hyphens, with no initial hyphen.
Add --classifier llm to request one economy-model classification. If none is available, the
cheapest available admissible model classifies the task and a stderr warning identifies it.
Classification has no tools; --timeout defaults to 30 seconds and kills the whole process group.
Heuristic fallback after a failed classification is a successful decision.
Pass the task budget using either --max-cost or --budget-profile, when one is provided.

Save the actual dev model returned in the JSON. For BOTH e2e-validator and reviewer, pass
--dev-model ID_OF_ACTUAL_DEV. The router must choose a different provider family.

Check the process exit code before launching. On exit 0, read the JSON and run herdr_command
verbatim, preserving its quoting, pane, name and model. Do not edit or reconstruct the command.
The router only prints it; you execute it. Review warnings on stderr. Never infer a model
from a failed response or ignore an error to continue with a guessed model.

On nonzero exit, do not launch that sub-agent. Read error and hint: 1 means fix input/registry
or unavailable models; 2 means the budget is impossible; 3 means dev-family information or
an independent model is missing; 4 means live catalog discovery failed; 5 means the role is unknown. Correct the input,
refresh the catalog or report the blocker, then call again. Do not relax budget/family bounds.
```

**Known limit:** Classifier and judge calls disable built-in MCP servers and server names from
`$COPILOT_HOME/mcp-config.json` (default `~/.copilot/mcp-config.json`). Plugin or workspace MCP
servers absent from that file may still load; deny-tool rules still apply to shell/write/read/url.

## Complete call and launch example

From the checkout, use a real catalog and an existing Herdr pane. This example uses pane 2.
The shell stops if routing fails; the Python block executes the returned command without changing it:

```bash
set -e
printf '%s\n' 'Add a filter to the list view and cover it with tests.' > /tmp/router-story.txt
uv run python scripts/route.py --role dev --story @/tmp/router-story.txt --available copilot-models.local.json --pane 2 --name dev-filter --json > /tmp/router-choice.json
uv run python - <<'PY'
import json
import shlex
import subprocess
from pathlib import Path

choice = json.loads(Path("/tmp/router-choice.json").read_text())
print(choice["herdr_command"])
subprocess.run(shlex.split(choice["herdr_command"]), check=True)
PY
```

For example, a selected model `claude-sonnet-5.5` produces exactly
`herdr agent start dev-filter --kind copilot --pane 2 -- --model claude-sonnet-5.5`.
To route its reviewer, read `model` from the saved dev choice and pass it as `--dev-model` on a new
routing call with `--role reviewer`, a new name and an existing independent pane. Do the same for
`e2e-validator`. The independence check is by provider, so another model from the same provider
will be rejected. [Selection details](router.md) explain budgets, tiers and provisional models;
[the eval guide](../eval/README.md) covers the final local and live checks.

A model without a known price inherits its direct predecessor's price within the same lineage.
The decision includes `prix_suppose: true`, a reason and a stderr warning. Without a known
predecessor price it is excluded with `pricing_missing`; add its price in `models.yaml`.
Explicit metadata in `models.yaml`, including family, price and `tier_override`, takes priority
over the local registry. Catalog availability still applies. Known ID prefixes can supply a missing
family; otherwise, set `family` explicitly. Failed selection lists each model's exclusion reasons.
Role bounds remain absolute: doc cannot exceed standard, even for a cheaper successor. A target
tier is a preference: test may use an equally cheap premium successor in the same lineage.
