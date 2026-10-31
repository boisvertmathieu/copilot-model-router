# Routeur Copilot avant chaque équipier

`scripts/route.py` classe le travail, puis **importe `select_model()`** pour choisir le modèle. Il prépare une commande Herdr sans la lancer. Python 3.10+ suffit pour router avec le secours JSON; la synchronisation exige aussi PyYAML. GNU Make est facultatif pour les raccourcis.

```bash
python3 scripts/route.py --role doc --story "Corriger une typo dans la doc" --files 1 --pane 1
python3 scripts/route.py --role dev --story-type refactor \
  --diff-stats "12 files changed, 340 insertions(+), 80 deletions(-)" --pane 2 --json
python3 scripts/route.py --role e2e-validator --story "Valider la feature" \
  --dev-model claude-sonnet-5.5 --available copilot-models.local.json --pane 3 --json
```

Les [preuves exécutées](router-proof.md) montrent les sorties et les codes réels. L'[exemple d'orchestrateur Bash](herdr-integration.md#orchestrateur-bash-avec-le-routeur) choisit chaque équipier avant de démarrer l'équipe.

## Étage 1 : classification sans inférence

`--classifier heuristic` est le défaut. Sans `--available live`, cette voie ne lance pas Copilot et n'envoie aucun prompt. Les signaux sont combinés selon l'ordre **critique > complexe > standard > trivial**. Le signal le plus exigeant gagne; chaque règle déclenchée figure dans `classification_reasons` et `reason`.

| Signal | Classe proposée |
| --- | --- |
| Mots `sécurité`, `security`, `auth`, `authentification`, `authentication`, `autorisation`, `authorization`, `paiement`, `payment`, `migration`, `concurrence`, `concurrency` | `critique` |
| Mots `refactor`, `refactoring`, `refactorisation`, `architecture`, `multi-modules` (ou avec espace) | `complexe` |
| Au moins 10 fichiers **ou** 500 lignes ajoutées + supprimées | `complexe` |
| De 3 à 9 fichiers **ou** de 100 à 499 lignes modifiées, sans signal plus exigeant | `standard` |
| De 0 à 2 fichiers et moins de 100 lignes modifiées connues | `trivial` |
| Mots `typo`, `doc`, `documentation`, `renommage`, `rename` | `trivial` |
| `--story-type refactor` ou `spike` | `complexe` |
| `--story-type doc` | `trivial` |
| Aucun signal décisif, y compris `bug`/`feature` sans autre indice | `standard` |

Les mots sont comparés sans distinction de casse ou d'accents, avec des limites de mots; certaines formes au pluriel sont acceptées. Une mention de risque compte même dans « aucune migration » : cette heuristique simple ne comprend pas la négation. Elle classe la portée apparente, sans mesurer la difficulté réelle.

`--files N` accepte un entier positif ou nul. Sans diff, le nombre de lignes reste inconnu; le nombre de fichiers peut à lui seul proposer une classe. `--diff-stats` accepte le résumé anglais de `git diff --stat`, au singulier ou au pluriel, en texte ou dans un fichier UTF-8. Les ajouts et les suppressions s'additionnent. En cas de comptes de fichiers différents, le maximum de `--files` et du diff est retenu et expliqué. Un résumé illisible est une erreur de configuration.

```bash
git diff --stat > /tmp/cmr-diff.txt
python3 scripts/route.py --role dev --diff-stats /tmp/cmr-diff.txt \
  --story @mission.txt --story-type feature --json
```

`--story` est du texte, ou `@fichier`; un chemin sans `@` reste un récit. `--diff-stats` reconnaît aussi un chemin existant sans `@`. Une statistique ou un fichier absent n'est pas deviné.

## Classification LLM facultative

```bash
python3 scripts/route.py --role dev --story @mission.txt --classifier llm \
  --available copilot-models.local.json --timeout 20 --json
```

L'interface injectée est `classify(prompt: str) -> str`. Sans client injecté, le routeur demande au sélecteur un modèle **economy seulement**, admissible dans le catalogue fourni, et crée `CopilotCliClient`. L'adaptateur exécute un tableau d'arguments équivalent à :

```text
copilot --model ID_ECONOMY -p PROMPT
```

Le processus a un délai maximal (`--timeout`, 30 secondes par défaut), sans shell. Après retrait des espaces extérieurs, la réponse doit être exactement `trivial`, `standard`, `complexe` ou `critique`, en minuscules. JSON, explication, ponctuation et plusieurs mots sont refusés. La classe LLM acceptée remplace celle de l'heuristique; `heuristic_level` conserve l'autre résultat pour inspection.

Un CLI absent, un délai dépassé, une sortie non nulle, une réponse invalide ou l'absence de modèle economy entraîne un **repli heuristique**, signalé dans `reason` et `warnings`. Les contraintes du choix final sont ensuite appliquées normalement. Le budget de référence porte sur le modèle de l'équipier; il ne comptabilise pas l'inférence facultative de classification ni la facture réelle.

`FakeClient` permet une injection sans Copilot :

```python
import sys
from pathlib import Path
sys.path.insert(0, "scripts")
from registry_lib import load_registry
from route import FakeClient, route

choix = route(load_registry(Path("models.yaml")), role="dev", story="Réviser ce travail",
              classifier="llm", client=FakeClient("complexe"))
print(choix["level"], choix["model"])
```

**L'invocation de classification n'a pas été validée contre un vrai Copilot.** Ici, les essais utilisent des clients injectés et un CLI simulé. Le comportement de `-p`, la présentation des réponses et les modèles autorisés restent à valider sur le poste de travail.

## Étage 2 : niveaux, rôles et contraintes

| Classe de tâche (`level`) | Préférence du modèle (`requested_tier`) |
| --- | --- |
| `trivial` | `economy` |
| `standard` | `standard` |
| `complexe` | `premium` |
| `critique` | `frontier` |

Le rôle `doc` plafonne la préférence **et les candidats** à `standard`. Pour `e2e-validator`, toute classe sauf `trivial` impose au moins `premium`, même en repli. Une validation triviale peut utiliser `economy`. `reviewer` suit le mapping ordinaire; comme e2e, il doit toujours changer de famille par rapport au dev. Les autres rôles suivent le mapping sans borne supplémentaire.

Le routeur transmet ces préférences et bornes à l'API du sélecteur (`preferred_level`, `min_level`, `max_level`). Le sélecteur continue de gérer les statuts CLI/GA, les politiques, la disponibilité, les budgets, les familles et le tri. Sa CLI historique reste compatible : ses modes `--level`, `--max-cost` et `--budget-profile` restent exclusifs.

Pour le routeur, `--max-cost` et `--budget-profile` sont exclusifs. La classification donne toujours la préférence; un profil fournit son plafond `max_cost`, sans remplacer cette préférence par son champ `level`. Le repli du sélecteur peut abaisser le niveau retenu (`tier`) ou relâcher la préférence vers un niveau supérieur disponible, en respectant les bornes du rôle. **Le plafond de coût et la séparation des familles restent obligatoires.** Ainsi, un dev complexe sous 5 crédits peut retomber en economy; une validation e2e non triviale avec le même plafond échoue si aucun premium admissible ne respecte ce budget.

`--dev-model` résout l'ID ou un alias dans le registre. `--dev-family` donne explicitement le fournisseur officiel, notamment pour un modèle externe. Les deux options doivent être cohérentes. Pour e2e/reviewer, la famille manque ou aucun fournisseur différent n'est admissible : code **3**. Si une autre famille est admissible, mais aucun candidat ne respecte le plafond : code **2**. La [politique de sélection](selection-policy.md) détaille le coût de référence et l'ordre des filtres.

## Disponibilité et sortie

`--available` accepte les formats déjà pris en charge par le sélecteur : fichier JSON/texte, `@fichier`, liste d'ID séparés par virgules ou espaces. En plus, **`--available live` appelle `scripts/list_copilot_models.py`**, qui demande `models.list` par RPC. `--copilot-cli` permet de préciser l'exécutable. Un échec de découverte donne le code **4**, sans commande de lancement; le routeur ne revient pas à une disponibilité inconnue. Le catalogue intégré hors ligne ne prouve aucun droit d'accès.

Sans catalogue fourni, `available: null` reste admissible et génère un avertissement. Pour un lancement réel, fournir un catalogue récent et vérifier `available: true` et `id_verified: true`. Le chemin live est testé avec le CLI simulé seulement; l'accès de l'organisation, la liste interactive `/models` et `models.list` réel restent à valider sur le poste de travail.

La sortie lisible affiche classe, tier retenu, modèle, raisons, avertissements et commande. `--json` fournit entre autres :

| Champ | Sens |
| --- | --- |
| `model`, `id`, `family` | ID concret et fournisseur du modèle retenu. |
| `level`, `classification`, `heuristic_level` | Classe finale, méthode effective et classe heuristique. |
| `classification_reasons`, `signals` | Règles déclenchées et métriques interprétées. |
| `requested_tier`, `tier`, `fallback` | Préférence après ajustement du rôle, niveau retenu et repli du sélecteur. |
| `reason`, `warnings`, `tier_provisoire` | Explications et éléments à valider. |
| `herdr_cmd`, `herdr_command`, `herdr_argv` | Commande avec quoting `shlex` et tableau d'arguments équivalent. |

`--pane` ajoute `--pane IDENTIFIANT`. Sans cette option, aucun panneau fictif n'est ajouté. `--name` remplace le nom positionnel de l'agent, qui vaut le rôle par défaut : `herdr agent start NOM --kind copilot [--pane PANNEAU] -- --model ID`. Les panneaux doivent convenir à la session Herdr du poste de travail. Le routeur ne lance jamais Herdr.

Les échecs JSON de la CLI contiennent `error` et `exit_code`, sans `herdr_cmd`. Codes : **0** succès, **1** configuration/fichier invalide ou aucun candidat ordinaire, **2** budget impossible (aussi syntaxe `argparse`), **3** famille impossible, **4** découverte live impossible. Les erreurs de syntaxe d'arguments gardent la sortie standard d'`argparse` sur stderr.

## Serveur JSON-RPC 2.0 sur stdio

```bash
python3 scripts/route.py --serve --registry models.yaml
```

Le registre est chargé **une seule fois au démarrage**, puis reste en mémoire jusqu'à `reload`. Les seules options de configuration du serveur sont `--registry`, `--copilot-cli` et `--timeout`; les choix de chaque tâche passent dans `params`. Les chemins relatifs sont résolus depuis le dossier du serveur. Chaque requête et chaque réponse occupent une ligne JSON complète; aucune bannière n'est écrite sur stdout. Pas de cadrage `Content-Length`, pas de tableau de requêtes groupées. Le serveur traite les lignes dans l'ordre et se termine avec le code 0 à la fin de stdin.

Entrée, deux requêtes :

```jsonl
{"jsonrpc":"2.0","id":1,"method":"ping"}
{"jsonrpc":"2.0","id":2,"method":"route","params":{"role":"doc","story":"Corriger une typo","pane":1}}
```

Méthodes :

| Méthode | Paramètres | Résultat |
| --- | --- | --- |
| `ping` | Absents ou `{}` | `{"status":"ok","models":26}` pour le registre livré. |
| `route` | Objet, `role` obligatoire | Le même objet qu'une sélection CLI réussie. |
| `reload` | Absents ou `{}` | Recharge le même fichier; `{"status":"rechargé","models":N}`. En cas d'échec, l'ancien registre reste utilisable. |

Les clés de `params` pour `route` sont les options en **snake_case** : `role`, `story`, `story_type`, `files`, `diff_stats`, `classifier`, `max_cost`, `budget_profile`, `dev_model`, `dev_family`, `available`, `allow_preview`, `pane`, `name`. `files` est un entier, `allow_preview` un booléen; `pane` peut être un entier ou du texte. `available` accepte aussi un tableau JSON d'ID ou d'entrées de catalogue. Les clés inconnues sont refusées. Le classifieur et les autres défauts sont les mêmes que pour la CLI.

Une réponse reprend l'`id` avec `result` ou `error`. Les notifications valides, sans `id`, sont traitées sans réponse. Les erreurs de protocole utilisent `-32700` (JSON illisible), `-32600` (requête invalide), `-32601` (méthode inconnue), `-32602` (paramètres invalides). Les contraintes de sélection et les échecs de rechargement utilisent `-32000` avec `error.data.exit_code` pour conserver les codes métier, par exemple :

```json
{"jsonrpc":"2.0","id":3,"error":{"code":-32000,"message":"…","data":{"exit_code":2}}}
```

Une erreur de requête ne ferme pas le serveur. Après une synchronisation externe, envoyer `reload` avant le prochain choix. Un `available: "live"` rafraîchit le catalogue pour cette requête seulement et ne recharge pas les tarifs.

## Nouveaux modèles et niveau provisoire

À la synchronisation, un nouveau modèle sans niveau connu reçoit le niveau déduit de la catégorie et du prix : `Lightweight → economy`, `Versatile → standard`, `Powerful → premium` sous 100 crédits et `frontier` dès 100. Il reçoit `tier_provisoire: true` et `tier_note: "Niveau déduit de la catégorie et du prix; à valider."`. Le rapport de sync le liste sous `provisional`.

Le marqueur reste présent aux synchronisations suivantes. Le routeur accepte ce modèle, renvoie `tier_provisoire: true` et indique « à valider » dans `reason` et `warnings`. Après révision humaine, inscrire `tier_override: NIVEAU` dans le YAML, puis resynchroniser; cela enlève le marqueur et sa note. Les niveaux déjà connus restent compatibles. Un modèle sans prix officiel ou dont la catégorie est inconnue n'obtient pas de tarif inventé.

## Rafraîchissement automatique

```bash
bash scripts/refresh.sh
make refresh
make test
make route-demo

# Essai hors réseau dans un registre temporaire; le CLI est volontairement absent.
COPILOT_CLI=/absent/copilot bash scripts/refresh.sh \
  --upstream-dir upstream --registry /tmp/cmr-models.yaml --json
```

Le script cherche `copilot` (ou `COPILOT_CLI`). S'il obtient un catalogue non vide avec `list_copilot_models.py`, il appelle `sync_registry.py --from-cli-models FICHIER_TEMPORAIRE`, puis efface ce fichier. Si le CLI manque ou si sa découverte échoue, il annonce le repli et synchronise les tarifs seulement. Ce succès ne confirme aucun nouvel accès au compte; le dernier constat sauvegardé garde sa date. Un échec de sync donne un code non nul. Les arguments du script sont transmis à la sync; `PYTHON` choisit l'interpréteur et `CMR_COPILOT_TIMEOUT` le délai de découverte (15 secondes par défaut).

Pour Make, `PYTHON` et `REFRESH_ARGS` sont configurables : `make refresh REFRESH_ARGS='--upstream-dir upstream'`. La sync réseau est le défaut. Les tests utilisent des dossiers temporaires et les tables livrées.

Exemple de crontab WSL, avec des chemins à adapter et un environnement Python contenant PyYAML :

```cron
15 7 * * * PYTHON=/home/utilisateur/src/cmr/.venv/bin/python COPILOT_CLI=/home/utilisateur/.local/bin/copilot /bin/bash /home/utilisateur/src/cmr/scripts/refresh.sh >> /home/utilisateur/.cache/cmr-refresh.log 2>&1
```

Créer le dossier de journal au préalable. Cron doit fonctionner dans la distribution WSL, qui doit être démarrée à l'heure prévue. On peut plutôt ajouter ce bloc à `~/.bashrc` pour les ouvertures de shell interactif WSL, **avec une garde par jour** :

```bash
if [[ $- == *i* && -r /proc/sys/kernel/osrelease ]] &&
   [[ $(< /proc/sys/kernel/osrelease) == *[Mm]icrosoft* ]]; then
    cmr_repo="$HOME/src/cmr"  # À adapter.
    cmr_cache="${XDG_CACHE_HOME:-$HOME/.cache}/cmr"
    cmr_jour="$cmr_cache/refresh-$(date +%F)"
    if [[ -f "$cmr_repo/scripts/refresh.sh" ]] && mkdir -p -- "$cmr_cache"; then
        # mkdir est atomique : deux terminaux ouverts ensemble ne lancent pas deux syncs.
        if mkdir -- "$cmr_jour" 2>/dev/null; then
            (
                if ! PYTHON="$cmr_repo/.venv/bin/python" bash "$cmr_repo/scripts/refresh.sh" \
                    >> "$cmr_cache/refresh.log" 2>&1; then
                    rmdir -- "$cmr_jour"  # Un échec autorise une reprise au prochain shell.
                fi
            ) &
        fi
    fi
    unset cmr_repo cmr_cache cmr_jour
fi
```

Le travail se fait en arrière-plan. Le dossier daté bloque les autres lancements ce jour-là; en cas d'échec normal, il est retiré. Choisir cron ou le bloc au login pour éviter deux mécanismes indépendants. Aucun cron ni fichier personnel n'a été installé par cette mission.

Il n'y a ici ni organisation Copilot accessible ni Herdr. Les preuves locales couvrent le routage, les contraintes, les processus simulés et le protocole stdio; les lancements réels et les deux chemins Copilot expérimentaux attendent le poste de travail.
