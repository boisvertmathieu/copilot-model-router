#!/bin/sh
# Route once, then execute only a successful decision's command.
if [ -z "${COPILOT_MODEL_ROUTER_HOME:-}" ] || [ ! -f "$COPILOT_MODEL_ROUTER_HOME/scripts/route.py" ]; then
    printf '%s\n' 'COPILOT_MODEL_ROUTER_HOME must point to a checkout containing scripts/route.py; nothing launched.' >&2
    exit 1
fi
decision=$(
    cd "$COPILOT_MODEL_ROUTER_HOME" || exit 1
    uv run --project "$COPILOT_MODEL_ROUTER_HOME" python scripts/route.py "$@" --json </dev/null
)
code=$?
printf '%s\n' "$decision" | uv run --project "$COPILOT_MODEL_ROUTER_HOME" python -c '
import json
import shlex
import subprocess
import sys

actions = {
    1: "Fix input/registry or refresh unavailable models, then retry",
    2: "Report the impossible budget; keep the budget bound",
    3: "Supply the actual dev model/family or refresh independent models; keep family separation",
    4: "Restore Copilot login/license/CLI access and refresh the live catalog, then retry",
    5: "Use a supported role, then retry",
}
code = int(sys.argv[1])
try:
    choice = json.load(sys.stdin)
except ValueError:
    print(f"Router exit {code}: no valid JSON response; check uv and the router installation before retrying.", file=sys.stderr)
    sys.exit(code or 1)
print(json.dumps(choice, ensure_ascii=False), flush=True)
if code:
    error = json.dumps(" ".join(choice["error"].split()), ensure_ascii=False)
    action = actions.get(code, "Check the router installation before retrying")
    print(f"Router exit {code}: {error}; {action}.", file=sys.stderr)
    sys.exit(code)
if choice["decision_source"] == "heuristic":
    print("Heuristic fallback: launching Herdr with the routed model.", file=sys.stderr, flush=True)
sys.exit(subprocess.run(shlex.split(choice["herdr_command"]), stdin=subprocess.DEVNULL).returncode)
' "$code"
