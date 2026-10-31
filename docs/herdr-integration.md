# Intégration Herdr sous WSL

Herdr doit recevoir le choix de modèle au lancement de chaque équipier. Le sélecteur retourne un ID et une commande; il ne modifie pas le modèle global du CLI.

La forme de transmission des arguments natifs est confirmée par l'[historique officiel Herdr](https://github.com/herdrdev/herdr/blob/master/CHANGELOG.md#075---2026-07-21). Le CLI inspecté accepte `--model`; son aide confirme aussi `--context default` et `--max-ai-credits`. Aucun lancement Herdr n'a été effectué dans cet environnement.

## Commandes directes

Les panneaux doivent déjà exister et être prêts à recevoir un processus. Les noms d'agents doivent être libres dans la session Herdr. Remplacer les variables par les ID de panneaux du poste de travail.

```bash
# Exemple de forme : dev Anthropic, validation OpenAI, revue Google.
herdr agent start dev --kind copilot --pane "$PANE_DEV" -- \
  --model claude-opus-5.5 --context default

herdr agent start e2e-validator --kind copilot --pane "$PANE_E2E" -- \
  --model gpt-6-sol --context default

herdr agent start reviewer --kind copilot --pane "$PANE_REVIEW" -- \
  --model gemini-4-argon --context default
```

Les ID ci-dessus illustrent la syntaxe; le catalogue du compte doit autoriser les choix. Le séparateur `--` est essentiel : ce qui suit est transmis à `copilot`.

Pour les autres rôles :

```bash
python3 scripts/select_model.py --role test --level standard --available copilot-models.local.json
python3 scripts/select_model.py --role doc --max-cost 5 --available copilot-models.local.json
python3 scripts/select_model.py --role planner --budget-profile frontier --available copilot-models.local.json
```

## Sélectionner l'équipe avant de la lancer

Dans le dossier de ce dépôt, commencer par actualiser le catalogue et les tarifs :

```bash
python3 scripts/list_copilot_models.py --output copilot-models.local.json
python3 scripts/sync_registry.py --from-cli-models copilot-models.local.json
```

L'exemple Python suivant utilise `PANE_DEV`, `PANE_E2E` et `PANE_REVIEW` déjà définies dans l'environnement WSL. Il choisit les trois modèles avant le premier démarrage, vérifie les codes de sortie, puis transmet des tableaux d'arguments à Herdr. Le budget de 100 crédits s'applique à la tâche de référence de chaque rôle; le CLI reçoit séparément un plafond de session.

```python
import json
import os
import subprocess
import sys
from pathlib import Path

racine = Path.cwd()
catalogue = racine / "copilot-models.local.json"
panneaux = {
    "dev": os.environ["PANE_DEV"],
    "e2e-validator": os.environ["PANE_E2E"],
    "reviewer": os.environ["PANE_REVIEW"],
}
if len(set(panneaux.values())) != len(panneaux):
    raise SystemExit("Chaque équipier doit avoir son propre panneau.")

def choisir(role, famille_dev=None):
    arguments = [sys.executable, str(racine / "scripts/select_model.py"),
                 "--role", role, "--max-cost", "100",
                 "--available", str(catalogue), "--json"]
    if famille_dev:
        arguments += ["--dev-family", famille_dev]
    resultat = subprocess.run(arguments, capture_output=True, text=True)
    if resultat.returncode:
        print(resultat.stdout or resultat.stderr, file=sys.stderr)
        raise SystemExit(resultat.returncode)
    choix = json.loads(resultat.stdout)
    if choix["available"] is not True or not choix["id_verified"]:
        raise SystemExit("Confirmer l'identifiant et la disponibilité avant le lancement.")
    return choix

equipe = {"dev": choisir("dev")}
famille_dev = equipe["dev"]["family"]
for role in ("e2e-validator", "reviewer"):
    equipe[role] = choisir(role, famille_dev)

# Toutes les contraintes de sélection ont réussi avant le premier lancement.
for role, choix in equipe.items():
    print(f"{role} : {choix['id']} — {choix['reason']}")
    arguments = [panneaux[role] if valeur == "<pane>" else valeur
                 for valeur in choix["herdr_argv"]]
    arguments += ["--context", "default", "--max-ai-credits", "100"]
    subprocess.run(arguments, check=True)
```

Le niveau reste celui par défaut du rôle avec `--max-cost`. Une autre famille n'est exigée que par rapport au dev : le validateur et le réviseur peuvent utiliser le même fournisseur entre eux. Si l'équipe exige aussi une séparation entre ces deux rôles, cette règle doit être ajoutée explicitement à l'orchestrateur.

La vérification préalable des modèles évite un lancement partiel causé par la sélection. Une erreur Herdr pendant le démarrage peut quand même laisser les agents déjà lancés en place; inspecter leur état avant de réessayer et utiliser de nouveaux noms au besoin.

## Coût réel et routeurs automatiques

`--max-cost 100` limite l'estimation du sélecteur. `--max-ai-credits 100`, disponible dans le CLI 1.0.105, borne la consommation de la session selon les mécanismes du CLI. Ce sont deux contrôles distincts. Dans une session interactive, `/limits set max-ai-credits 100` est une autre façon de configurer cette limite. Vérifier les options avec `copilot --help` et `copilot help limits` sur la version installée.

`--context default` rend explicite l'hypothèse de tarif utilisée ici; un long contexte ou des écritures de cache changent le calcul. Un plafond peut interrompre une tâche si la session consomme plus que prévu.

Éviter de remplacer l'ID concret par un routeur `auto` ou `fusion` pour les rôles soumis à la séparation des fournisseurs : la famille finalement choisie ne serait plus établie à l'avance. Le CLI 1.0.105 inspecté documente `auto` et `--auto-tier`; `fusion` mentionné dans le brief reste à confirmer sur la version du poste de travail.

## Échec de sélection

Avec `--json`, lire le code du processus avant d'accéder à `id`. Un code **2** signifie qu'aucun candidat ne respecte le budget; un code **3** signifie que la séparation des fournisseurs ne peut pas être établie. Le JSON contient la raison et aucune commande de lancement.

Ne pas substituer le modèle du dev dans un bloc de récupération d'erreur. Il faut rendre accessible une autre famille, revoir le budget avec l'utilisateur ou suspendre ce lancement. Un échec de découverte donne le code **4** : régler la connexion, le CLI ou la licence avant de reprendre.
