"""Faux Copilot pour le contrat subprocess du juge, sans réseau."""

import argparse
import json
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument("--model", required=True)
parser.add_argument("-p", required=True)
parser.add_argument("--excluded-tools", required=True)
parser.add_argument("--deny-tool", action="append", required=True)
parser.add_argument("--no-ask-user", action="store_true", required=True)
parser.add_argument("--disable-builtin-mcps", action="store_true", required=True)
parser.add_argument("--no-custom-instructions", action="store_true", required=True)
parser.add_argument("-s", action="store_true", required=True)
args = parser.parse_args()
payload = json.loads(args.p.split("\n", 1)[1])
assert {"case", "decision"} == payload.keys()
assert payload["case"]["inputs"]["story"]
verdict = json.dumps({"score": 0.9, "justification": "Choix cohérent avec le récit."}, ensure_ascii=False)
if args.model == "timeout":
    time.sleep(2)
elif args.model == "error":
    print("Erreur simulée : aucun accès au compte.", file=sys.stderr)
    sys.exit(9)
elif args.model == "invalid":
    print("Le résultat semble bon, mais aucun JSON n'est fourni.")
elif args.model == "fenced":
    print("Diagnostic simulé avant la réponse.\n```json\n" + verdict + "\n```\nFin.")
elif args.model == "progress":
    print('{"progress": true}\n' + verdict)
elif args.model == "ambiguous":
    print(verdict + "\n" + verdict)
elif args.model == "boolean":
    print('{"score": true, "justification": "Non numérique"}')
elif args.model == "nan":
    print('{"score": NaN, "justification": "Non fini"}')
elif args.model == "duplicate":
    print('{"score": 0.1, "score": 0.9, "justification": "Doublon"}')
else:
    print(verdict)
