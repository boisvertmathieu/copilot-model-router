# Preuves exécutées du routeur

Exécution locale du 2026-10-31T01:25:28.975209+00:00, depuis la racine du dépôt. Interpréteur : `3.13.5`. Empreinte SHA-256 de `models.yaml` : `ea15f6b3f3196fdf79c11effdf59168226b019dce2bbc455ac97067cade4baed`.

Les commandes ci-dessous ont été exécutées; stdout, stderr et codes sont copiés intégralement. Les commandes Herdr sont produites sans être lancées. Aucune organisation Copilot ni installation Herdr n’est accessible ici. Les clients LLM, catalogues et modèles explicitement simulés sont identifiés. Les prix et IDs des scénarios ordinaires viennent du registre livré; leur disponibilité au compte reste inconnue.

## Petit bug dans la doc → trivial → economy

Entrée :

```bash
python3 scripts/route.py --role doc --story-type bug --story 'Corriger une typo dans la doc' --diff-stats '1 file changed, 1 insertion(+), 1 deletion(-)' --pane 1
```

stdout :

```text
trivial → economy : claude-haiku-5.5 (anthropic)
Portée mesurée : 1 fichier(s), 2 ligne(s) modifiée(s) → trivial. Mots-clés : doc, typo → trivial. Signal le plus exigeant retenu : trivial. Classe trivial → préférence economy. Rôle doc plafonné à standard; préférence economy. Rôle doc, niveau souhaité economy; niveau retenu economy, puis coût minimal dans ce niveau (égalité tranchée par ID). Coût estimé : 2.1 crédits par tâche de référence. Bornes du rôle respectées : economy à standard.
À vérifier : Disponibilité du compte non vérifiée; fournir --available après connexion au poste de travail.
herdr agent start doc --kind copilot --pane 1 -- --model claude-haiku-5.5
```

stderr :

```text
(vide)
```

Code de sortie observé : **0**.

## Gros refactor multi-fichiers → complexe → premium

Entrée :

```bash
python3 scripts/route.py --role dev --story-type refactor --story 'Refactor multi-modules' --diff-stats '12 files changed, 340 insertions(+), 80 deletions(-)' --pane 2
```

stdout :

```text
complexe → premium : gemini-4-argon (google)
Portée mesurée : 12 fichier(s), 420 ligne(s) modifiée(s) → complexe. Mots-clés : multi-modules, refactor → complexe. Type de récit refactor → complexe. Signal le plus exigeant retenu : complexe. Classe complexe → préférence premium. Rôle dev, niveau souhaité premium; niveau retenu premium, puis coût minimal dans ce niveau (égalité tranchée par ID). Coût estimé : 41 crédits par tâche de référence.
À vérifier : Disponibilité du compte non vérifiée; fournir --available après connexion au poste de travail.
herdr agent start dev --kind copilot --pane 2 -- --model gemini-4-argon
```

stderr :

```text
(vide)
```

Code de sortie observé : **0**.

## Sécurité → critique → frontier

Entrée :

```bash
python3 scripts/route.py --role dev --story 'Corriger la sécurité de l’auth et du paiement' --pane 3
```

stdout :

```text
critique → frontier : claude-opus-4.8 (anthropic)
Mots-clés : auth, paiement, securite → critique. Signal le plus exigeant retenu : critique. Classe critique → préférence frontier. Rôle dev, niveau souhaité frontier; niveau retenu frontier, puis coût minimal dans ce niveau (égalité tranchée par ID). Coût estimé : 105 crédits par tâche de référence.
À vérifier : Disponibilité du compte non vérifiée; fournir --available après connexion au poste de travail.
herdr agent start dev --kind copilot --pane 3 -- --model claude-opus-4.8
```

stderr :

```text
(vide)
```

Code de sortie observé : **0**.

## Validateur e2e avec dev Claude Sonnet 5.5 → autre famille

Entrée :

```bash
python3 scripts/route.py --role e2e-validator --story 'Valider la feature' --dev-model claude-sonnet-5.5 --pane 4 --json
```

stdout :

```text
{
  "id": "gemini-4-argon",
  "display_name": "Gemini 4 Argon",
  "family": "google",
  "tier": "premium",
  "requested_level": "premium",
  "role": "e2e-validator",
  "tier_provisoire": false,
  "cost_index": 41.0,
  "max_cost": null,
  "budget_profile": null,
  "dev_family": "anthropic",
  "id_verified": true,
  "available": null,
  "reason": "Aucun signal décisif; travail courant → standard. Signal le plus exigeant retenu : standard. Classe standard → préférence standard. Validation e2e non triviale : minimum premium; préférence premium. Rôle e2e-validator, niveau souhaité premium; niveau retenu premium, puis coût minimal dans ce niveau (égalité tranchée par ID). Coût estimé : 41 crédits par tâche de référence. Famille google différente de celle du dev (anthropic). Bornes du rôle respectées : premium à frontier.",
  "fallback": "none",
  "warnings": [
    "Disponibilité du compte non vérifiée; fournir --available après connexion au poste de travail."
  ],
  "herdr_command": "herdr agent start e2e-validator --kind copilot --pane 4 -- --model gemini-4-argon",
  "herdr_argv": [
    "herdr",
    "agent",
    "start",
    "e2e-validator",
    "--kind",
    "copilot",
    "--pane",
    "4",
    "--",
    "--model",
    "gemini-4-argon"
  ],
  "model": "gemini-4-argon",
  "level": "standard",
  "classifier_requested": "heuristic",
  "classification": "heuristic",
  "classifier_model": null,
  "heuristic_level": "standard",
  "classification_reasons": [
    "Aucun signal décisif; travail courant → standard.",
    "Signal le plus exigeant retenu : standard."
  ],
  "signals": {
    "files": null,
    "insertions": null,
    "deletions": null,
    "changed_lines": null,
    "story_type": null
  },
  "requested_tier": "premium",
  "herdr_cmd": "herdr agent start e2e-validator --kind copilot --pane 4 -- --model gemini-4-argon"
}
```

stderr :

```text
(vide)
```

Code de sortie observé : **0**.

## Budget serré → repli economy sans changer la classe

Entrée :

```bash
python3 scripts/route.py --role dev --story 'Refactor multi-modules' --files 12 --max-cost 5 --pane 5
```

stdout :

```text
complexe → economy : claude-haiku-5.5 (anthropic)
Portée mesurée : 12 fichier(s), nombre de lignes inconnu → complexe. Mots-clés : multi-modules, refactor → complexe. Signal le plus exigeant retenu : complexe. Classe complexe → préférence premium. Rôle dev, niveau souhaité premium; niveau retenu economy, puis coût minimal dans ce niveau (égalité tranchée par ID). Repli vers un niveau inférieur : aucun candidat admissible au niveau souhaité. Coût estimé : 2.1 crédits par tâche de référence. Plafond respecté : 5 crédits.
À vérifier : Disponibilité du compte non vérifiée; fournir --available après connexion au poste de travail.
herdr agent start dev --kind copilot --pane 5 -- --model claude-haiku-5.5
```

stderr :

```text
(vide)
```

Code de sortie observé : **0**.

## Budget impossible → code 2

Entrée :

```bash
python3 scripts/route.py --role dev --story Refactor --max-cost 0 --json
```

stdout :

```text
{
  "error": "Aucun modèle admissible ne respecte le plafond de 0 crédits par tâche de référence. Le budget ne peut pas être dépassé.",
  "exit_code": 2
}
```

stderr :

```text
(vide)
```

Code de sortie observé : **2**.

## Famille impossible → code 3

Entrée :

```bash
python3 scripts/route.py --role e2e-validator --story 'Valider la feature' --dev-model claude-sonnet-5.5 --available claude-sonnet-5.5 --json
```

stdout :

```text
{
  "error": "Aucun modèle CLI admissible d'une famille différente de anthropic. La contrainte de famille ne peut pas être relâchée.",
  "exit_code": 3
}
```

stderr :

```text
(vide)
```

Code de sortie observé : **3**.

## Serveur stdio → deux requêtes dans le même processus

Entrée :

```bash
python3 scripts/route.py --serve <<'JSONL'
{"jsonrpc":"2.0","id":1,"method":"route","params":{"role":"doc","story":"Corriger une typo","files":1,"pane":1}}
{"jsonrpc":"2.0","id":2,"method":"route","params":{"role":"e2e-validator","story":"Valider la feature","dev_model":"claude-sonnet-5.5","pane":2}}
JSONL
```

stdout :

```text
{"jsonrpc": "2.0", "id": 1, "result": {"id": "claude-haiku-5.5", "display_name": "Claude Haiku 5.5", "family": "anthropic", "tier": "economy", "requested_level": "economy", "role": "doc", "tier_provisoire": false, "cost_index": 2.1, "max_cost": null, "budget_profile": null, "dev_family": null, "id_verified": true, "available": null, "reason": "Portée mesurée : 1 fichier(s), nombre de lignes inconnu → trivial. Mots-clés : typo → trivial. Signal le plus exigeant retenu : trivial. Classe trivial → préférence economy. Rôle doc plafonné à standard; préférence economy. Rôle doc, niveau souhaité economy; niveau retenu economy, puis coût minimal dans ce niveau (égalité tranchée par ID). Coût estimé : 2.1 crédits par tâche de référence. Bornes du rôle respectées : economy à standard.", "fallback": "none", "warnings": ["Disponibilité du compte non vérifiée; fournir --available après connexion au poste de travail."], "herdr_command": "herdr agent start doc --kind copilot --pane 1 -- --model claude-haiku-5.5", "herdr_argv": ["herdr", "agent", "start", "doc", "--kind", "copilot", "--pane", "1", "--", "--model", "claude-haiku-5.5"], "model": "claude-haiku-5.5", "level": "trivial", "classifier_requested": "heuristic", "classification": "heuristic", "classifier_model": null, "heuristic_level": "trivial", "classification_reasons": ["Portée mesurée : 1 fichier(s), nombre de lignes inconnu → trivial.", "Mots-clés : typo → trivial.", "Signal le plus exigeant retenu : trivial."], "signals": {"files": 1, "insertions": null, "deletions": null, "changed_lines": null, "story_type": null}, "requested_tier": "economy", "herdr_cmd": "herdr agent start doc --kind copilot --pane 1 -- --model claude-haiku-5.5"}}
{"jsonrpc": "2.0", "id": 2, "result": {"id": "gemini-4-argon", "display_name": "Gemini 4 Argon", "family": "google", "tier": "premium", "requested_level": "premium", "role": "e2e-validator", "tier_provisoire": false, "cost_index": 41.0, "max_cost": null, "budget_profile": null, "dev_family": "anthropic", "id_verified": true, "available": null, "reason": "Aucun signal décisif; travail courant → standard. Signal le plus exigeant retenu : standard. Classe standard → préférence standard. Validation e2e non triviale : minimum premium; préférence premium. Rôle e2e-validator, niveau souhaité premium; niveau retenu premium, puis coût minimal dans ce niveau (égalité tranchée par ID). Coût estimé : 41 crédits par tâche de référence. Famille google différente de celle du dev (anthropic). Bornes du rôle respectées : premium à frontier.", "fallback": "none", "warnings": ["Disponibilité du compte non vérifiée; fournir --available après connexion au poste de travail."], "herdr_command": "herdr agent start e2e-validator --kind copilot --pane 2 -- --model gemini-4-argon", "herdr_argv": ["herdr", "agent", "start", "e2e-validator", "--kind", "copilot", "--pane", "2", "--", "--model", "gemini-4-argon"], "model": "gemini-4-argon", "level": "standard", "classifier_requested": "heuristic", "classification": "heuristic", "classifier_model": null, "heuristic_level": "standard", "classification_reasons": ["Aucun signal décisif; travail courant → standard.", "Signal le plus exigeant retenu : standard."], "signals": {"files": null, "insertions": null, "deletions": null, "changed_lines": null, "story_type": null}, "requested_tier": "premium", "herdr_cmd": "herdr agent start e2e-validator --kind copilot --pane 2 -- --model gemini-4-argon"}}
```

stderr :

```text
(vide)
```

Code de sortie observé : **0**.

## Classifieur LLM avec FakeClient injecté, sans Copilot

Entrée :

```bash
python3 - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, "scripts")
from registry_lib import dump_json, load_registry
from route import FakeClient, route

client = FakeClient("complexe\n")
choix = route(load_registry(Path("models.yaml")), role="dev", story="Réviser ce travail",
              classifier="llm", client=client, pane=6)
print(dump_json({cle: choix[cle] for cle in (
    "model", "level", "tier", "family", "classification", "heuristic_level", "reason", "warnings", "herdr_cmd"
)}), end="")
print(f"Prompts capturés par FakeClient : {len(client.prompts)}")
PY
```

stdout :

```text
{
  "model": "gemini-4-argon",
  "level": "complexe",
  "tier": "premium",
  "family": "google",
  "classification": "llm",
  "heuristic_level": "standard",
  "reason": "Classifieur LLM : réponse d'un seul mot validée → complexe. Classe complexe → préférence premium. Rôle dev, niveau souhaité premium; niveau retenu premium, puis coût minimal dans ce niveau (égalité tranchée par ID). Coût estimé : 41 crédits par tâche de référence.",
  "warnings": [
    "Disponibilité du compte non vérifiée; fournir --available après connexion au poste de travail."
  ],
  "herdr_cmd": "herdr agent start dev --kind copilot --pane 6 -- --model gemini-4-argon"
}
Prompts capturés par FakeClient : 1
```

stderr :

```text
(vide)
```

Code de sortie observé : **0**.

## Échec simulé du client LLM → repli heuristique

Entrée :

```bash
python3 - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, "scripts")
from registry_lib import dump_json, load_registry
from route import FakeClient, route

choix = route(load_registry(Path("models.yaml")), role="dev", story="Sécurité de l’auth",
              classifier="llm", client=FakeClient(error=TimeoutError("Délai simulé")), pane=7)
print(dump_json({cle: choix[cle] for cle in (
    "model", "level", "tier", "classification", "reason", "warnings", "herdr_cmd"
)}), end="")
PY
```

stdout :

```text
{
  "model": "claude-opus-4.8",
  "level": "critique",
  "tier": "frontier",
  "classification": "heuristic",
  "reason": "Classifieur LLM indisponible (TimeoutError); repli heuristique → critique. Mots-clés : auth, securite → critique. Signal le plus exigeant retenu : critique. Classe critique → préférence frontier. Rôle dev, niveau souhaité frontier; niveau retenu frontier, puis coût minimal dans ce niveau (égalité tranchée par ID). Coût estimé : 105 crédits par tâche de référence.",
  "warnings": [
    "Classifieur LLM indisponible (TimeoutError); repli heuristique → critique.",
    "Disponibilité du compte non vérifiée; fournir --available après connexion au poste de travail."
  ],
  "herdr_cmd": "herdr agent start dev --kind copilot --pane 7 -- --model claude-opus-4.8"
}
```

stderr :

```text
(vide)
```

Code de sortie observé : **0**.

## Sync d’un nouveau modèle simulé → niveau provisoire accepté et annoncé

Entrée :

```bash
python3 - <<'PY'
import copy
import sys
from pathlib import Path
sys.path.insert(0, "scripts")
from registry_lib import TABLE_FILES, dump_json, load_registry
from route import route
from sync_registry import build_registry, load_tables

# Donnée de test simulée en mémoire; aucun modèle ni tarif réel n’est ajouté au dépôt.
tables = load_tables({nom: (Path("upstream") / nom).read_text(encoding="utf-8") for nom in TABLE_FILES})
ligne = copy.deepcopy(next(ligne for ligne in tables["models-and-pricing.yml"]
                           if ligne.get("tier", "Default") == "Default"))
ligne.update(model="Modele nouveau POC", provider="openai", category="Powerful", release_status="GA",
             input="1", cached_input="0.1", output="2")
tables["models-and-pricing.yml"].append(ligne)
tables["model-supported-clients.yml"].append({"name": "Modele nouveau POC", "cli": True})
registre, rapport = build_registry(tables, load_registry(Path("models.yaml")), "2026-10-30")
modele = next(modele for modele in registre["models"] if modele["display_name"] == "Modele nouveau POC")
choix = route(registre, role="dev", story="Refactor multi-modules", available=[modele["id"]], pane=8)
print(dump_json({"nouveaux": rapport["new"], "provisoires": rapport["provisional"],
                 "tier_note": modele["tier_note"], "choix": {cle: choix[cle] for cle in (
                     "model", "level", "tier", "tier_provisoire", "cost_index", "reason", "warnings", "herdr_cmd"
                 )}}), end="")
PY
```

stdout :

```text
{
  "nouveaux": [
    "Modele nouveau POC"
  ],
  "provisoires": [
    "Modele nouveau POC"
  ],
  "tier_note": "Niveau déduit de la catégorie et du prix; à valider.",
  "choix": {
    "model": "modele-nouveau-poc",
    "level": "complexe",
    "tier": "premium",
    "tier_provisoire": true,
    "cost_index": 15.0,
    "reason": "Mots-clés : multi-modules, refactor → complexe. Signal le plus exigeant retenu : complexe. Classe complexe → préférence premium. Rôle dev, niveau souhaité premium; niveau retenu premium, puis coût minimal dans ce niveau (égalité tranchée par ID). Coût estimé : 15 crédits par tâche de référence. Niveau premium provisoire, déduit de la catégorie et du prix : à valider.",
    "warnings": [
      "Niveau premium provisoire, déduit de la catégorie et du prix : à valider."
    ],
    "herdr_cmd": "herdr agent start dev --kind copilot --pane 8 -- --model modele-nouveau-poc"
  }
}
```

stderr :

```text
(vide)
```

Code de sortie observé : **0**.

## Catalogue live inaccessible → code 4 sans sélection hors ligne

Entrée :

```bash
python3 scripts/route.py --role dev --available live --copilot-cli /absent/copilot-cmr --json
```

stdout :

```text
{
  "error": "Catalogue Copilot live inaccessible. Vérifier la connexion, la licence et le CLI sur le poste de travail.",
  "exit_code": 4
}
```

stderr :

```text
(vide)
```

Code de sortie observé : **4**.

## Refresh sans CLI → sync locale seule, dans un registre temporaire

Entrée :

```bash
python3 - <<'PY'
import os
import subprocess
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory(prefix="preuve-refresh-cmr-") as dossier:
    resultat = subprocess.run(["bash", "scripts/refresh.sh", "--upstream-dir", "upstream",
                               "--registry", str(Path(dossier) / "models.yaml"), "--json"],
                              env={**os.environ, "COPILOT_CLI": "/absent/copilot-cmr"})
    raise SystemExit(resultat.returncode)
PY
```

stdout :

```text
{
  "new": [
    "GPT-5.3-Codex",
    "GPT-5.6 Luna",
    "GPT-5.6 Sol",
    "GPT-5.6 Terra",
    "GPT-6 Astra",
    "GPT-6 Luna",
    "GPT-6 Sol",
    "GPT-6.1 Terra",
    "Claude Haiku 4.5",
    "Claude Haiku 5.5",
    "Claude Sonnet 4.6",
    "Claude Opus 4.8",
    "Claude Opus 5",
    "Claude Opus 5.5",
    "Claude Sonnet 5",
    "Claude Sonnet 5.5",
    "Claude Opus 4.8 (fast mode) (preview)",
    "Claude Fable 5",
    "Claude Fable 5.1",
    "Gemini 3.8 Flash",
    "Gemini 4 Argon",
    "Grok 4.5",
    "Grok 4.6",
    "Grok 4.7",
    "MAI-Code-1.1-Flash",
    "Kimi K3"
  ],
  "removed": [],
  "provisional": [
    "GPT-5.3-Codex",
    "GPT-5.6 Luna",
    "GPT-5.6 Sol",
    "GPT-5.6 Terra",
    "GPT-6 Astra",
    "GPT-6 Luna",
    "GPT-6 Sol",
    "GPT-6.1 Terra",
    "Claude Haiku 4.5",
    "Claude Haiku 5.5",
    "Claude Sonnet 4.6",
    "Claude Opus 4.8",
    "Claude Opus 5",
    "Claude Opus 5.5",
    "Claude Sonnet 5",
    "Claude Sonnet 5.5",
    "Claude Opus 4.8 (fast mode) (preview)",
    "Claude Fable 5",
    "Claude Fable 5.1",
    "Gemini 3.8 Flash",
    "Gemini 4 Argon",
    "Grok 4.5",
    "Grok 4.6",
    "Grok 4.7",
    "MAI-Code-1.1-Flash",
    "Kimi K3"
  ],
  "excluded_non_cli": [
    "GPT-5.4 nano",
    "GPT-6.1 Sol",
    "Claude Sonnet 4"
  ],
  "unmatched_cli": [],
  "ambiguous_cli": [],
  "id_changes": [],
  "models": 26,
  "mode": "local",
  "checked_at": "2026-10-31T01:25:30.169798+00:00"
}
```

stderr :

```text
Copilot CLI absent; synchronisation des tarifs seulement.
```

Code de sortie observé : **0**.

## Exemple Bash et cibles Make

Les 15 blocs Bash de README, du guide et de l’intégration ont été analysés avec `bash -n`. GNU Make est absent de cet environnement; `make route-demo` retourne 127. Les trois commandes de sa recette sont exécutées directement ci-dessous; la cible `test` utilise exactement la suite finale et `refresh` appelle le script éprouvé plus haut.

## Commande 1 de route-demo

Entrée :

```bash
python3 scripts/route.py --role doc --story 'Corriger une typo dans la doc' --files 1 --pane 1
```

stdout :

```text
trivial → economy : claude-haiku-5.5 (anthropic)
Portée mesurée : 1 fichier(s), nombre de lignes inconnu → trivial. Mots-clés : doc, typo → trivial. Signal le plus exigeant retenu : trivial. Classe trivial → préférence economy. Rôle doc plafonné à standard; préférence economy. Rôle doc, niveau souhaité economy; niveau retenu economy, puis coût minimal dans ce niveau (égalité tranchée par ID). Coût estimé : 2.1 crédits par tâche de référence. Bornes du rôle respectées : economy à standard.
À vérifier : Disponibilité du compte non vérifiée; fournir --available après connexion au poste de travail.
herdr agent start doc --kind copilot --pane 1 -- --model claude-haiku-5.5
```

stderr :

```text
(vide)
```

Code de sortie observé : **0**.

## Commande 2 de route-demo

Entrée :

```bash
python3 scripts/route.py --role dev --story 'Refactor multi-modules' --diff-stats '12 files changed, 340 insertions(+), 80 deletions(-)' --pane 2
```

stdout :

```text
complexe → premium : gemini-4-argon (google)
Portée mesurée : 12 fichier(s), 420 ligne(s) modifiée(s) → complexe. Mots-clés : multi-modules, refactor → complexe. Signal le plus exigeant retenu : complexe. Classe complexe → préférence premium. Rôle dev, niveau souhaité premium; niveau retenu premium, puis coût minimal dans ce niveau (égalité tranchée par ID). Coût estimé : 41 crédits par tâche de référence.
À vérifier : Disponibilité du compte non vérifiée; fournir --available après connexion au poste de travail.
herdr agent start dev --kind copilot --pane 2 -- --model gemini-4-argon
```

stderr :

```text
(vide)
```

Code de sortie observé : **0**.

## Commande 3 de route-demo

Entrée :

```bash
python3 scripts/route.py --role e2e-validator --story 'Valider la feature' --dev-model claude-sonnet-5.5 --pane 3
```

stdout :

```text
standard → premium : gemini-4-argon (google)
Aucun signal décisif; travail courant → standard. Signal le plus exigeant retenu : standard. Classe standard → préférence standard. Validation e2e non triviale : minimum premium; préférence premium. Rôle e2e-validator, niveau souhaité premium; niveau retenu premium, puis coût minimal dans ce niveau (égalité tranchée par ID). Coût estimé : 41 crédits par tâche de référence. Famille google différente de celle du dev (anthropic). Bornes du rôle respectées : premium à frontier.
À vérifier : Disponibilité du compte non vérifiée; fournir --available après connexion au poste de travail.
herdr agent start e2e-validator --kind copilot --pane 3 -- --model gemini-4-argon
```

stderr :

```text
(vide)
```

Code de sortie observé : **0**.

## Orchestrateur Bash exécuté avec Herdr simulé

Le bloc Bash exact de `docs/herdr-integration.md` a été exécuté avec `CMR_STORY_FILE` pointant vers « Refactor multi-modules », `CMR_CATALOGUE` vers une liste de test `["gemini-4-argon", "gpt-6-sol", "claude-opus-5.5"]`, les panneaux 1/2/3 et un exécutable temporaire `herdr` qui journalise ses arguments. Aucun Herdr réel n’a été lancé.

stdout :

```text
dev : gemini-4-argon (google)
Herdr SIMULÉ : ["agent", "start", "mission-dev", "--kind", "copilot", "--pane", "1", "--", "--model", "gemini-4-argon"]
e2e-validator : gpt-6-sol (openai)
Herdr SIMULÉ : ["agent", "start", "mission-e2e-validator", "--kind", "copilot", "--pane", "2", "--", "--model", "gpt-6-sol"]
reviewer : gpt-6-sol (openai)
Herdr SIMULÉ : ["agent", "start", "mission-reviewer", "--kind", "copilot", "--pane", "3", "--", "--model", "gpt-6-sol"]
```

stderr :

```text
(vide)
```

Code de sortie observé : **0**; trois appels au simulateur.

Même bloc avec le catalogue de test réduit à `["gpt-6-sol"]` :

stdout :

```text
(vide)
```

stderr :

```text
{
  "error": "Aucun modèle CLI admissible d'une famille différente de openai. La contrainte de famille ne peut pas être relâchée.",
  "exit_code": 3
}
```

Code de sortie observé : **3**; aucun appel au simulateur, car le validateur ne peut pas changer de famille.

## Suite complète finale, y compris les 47 tests d’origine

Entrée :

```bash
python3 -m unittest discover -s tests
```

stdout :

```text
(vide)
```

stderr :

```text
............................................................................
----------------------------------------------------------------------
Ran 76 tests in 3.317s

OK
```

Code de sortie observé : **0**.

## Portée de la validation

Le routage et le serveur ont été exécutés localement. Les tests couvrent aussi `ping`, `reload`, la conservation du registre après un rechargement invalide, les notifications, les erreurs de protocole, les quatre niveaux, les fichiers de signaux, le quoting, le budget, les familles, le secours sans PyYAML, le catalogue live simulé et les trois voies de refresh. Les appels de classification à un vrai Copilot, `/models`, `models.list` du compte et les lancements dans Herdr restent à valider sur le poste de travail. Aucun cron ni fichier de login n’a été installé, aucun registre de production n’a été resynchronisé pendant ces preuves et aucun commit/push n’a été fait.
