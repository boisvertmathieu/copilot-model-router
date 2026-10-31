# Un modèle Copilot par rôle dans Herdr

L'orchestrateur de utilisateur lance ses équipiers avec GitHub Copilot CLI dans Herdr, sous WSL. Avant chaque équipier, le routeur classe la tâche (`trivial`, `standard`, `complexe`, `critique`), puis réutilise le sélecteur pour choisir un modèle selon le rôle, la disponibilité et le budget. Le validateur e2e **et** le réviseur doivent utiliser un fournisseur différent de celui du dev.

Le registre contient **26 modèles** issus du croisement des tarifs officiels et du support CLI. La synchronisation réseau a été exécutée; 25 ID ont aussi été repérés dans le catalogue intégré du CLI 1.0.105. L'accès au compte reste inconnu pour tous les modèles; `gpt-6.1-terra` garde `id_verified: false`.

Les [constats de recherche](docs/reverse-engineering.md) distinguent les sources vérifiées, la simulation HTTP locale et les hypothèses. Aucun catalogue de compte Copilot réel n'a été obtenu sur cette machine sans licence.

## Démarrage

Python **3.10 ou plus récent**. PyYAML sert à la synchronisation; le routeur et le sélecteur peuvent utiliser `models.json` si PyYAML est absent. GNU Make est facultatif pour les raccourcis.

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v

# Synchronisation avec les quatre tables officielles, par le réseau.
python3 scripts/sync_registry.py

# Routage heuristique sans inférence, avant chaque équipier.
python3 scripts/route.py --role doc --story "Corriger une typo dans la doc" --files 1 --pane 1
python3 scripts/route.py --role dev --story "Refactor multi-modules" \
  --diff-stats "12 files changed, 340 insertions(+), 80 deletions(-)" --pane 2 --json
python3 scripts/route.py --role e2e-validator --story "Valider la feature" \
  --dev-model claude-sonnet-5.5 --budget-profile premium --pane 3 --json

# Serveur persistant : JSON-RPC 2.0, une requête par ligne.
python3 scripts/route.py --serve
# Envoyer {"jsonrpc":"2.0","id":1,"method":"ping"}, puis Ctrl-D pour quitter.
```

Sans `--available`, une disponibilité inconnue reste admissible et la sortie le signale. Ça permet de planifier hors ligne; l'orchestrateur doit fournir le catalogue réel avant de lancer les équipiers.

Le [guide du routeur](docs/router.md) explique les seuils, les règles par rôle, le JSON et le protocole stdio. Le mapping est `trivial → economy`, `standard → standard`, `complexe → premium`, `critique → frontier`; doc est plafonné à standard et e2e exige au moins premium sauf pour une tâche triviale. `--max-cost` et `--budget-profile` sont exclusifs; le profil fournit son plafond tout en gardant la préférence issue de la classe. Un nouveau niveau déduit à la sync porte `tier_provisoire: true` et un avertissement « à valider ».

Le sélecteur direct reste disponible : `python3 scripts/select_model.py --role dev --level premium`. Pour cette CLI historique, `--level`, `--max-cost` et `--budget-profile` restent exclusifs et les préférences par défaut restent propres au rôle.

## Sur le poste de travail avec accès Copilot

```bash
copilot login

# Écrit le fichier seulement si le CLI retourne un catalogue non vide.
python3 scripts/list_copilot_models.py --output copilot-models.local.json

# Met à jour les prix et rapproche les ID, politiques et disponibilités du compte.
python3 scripts/sync_registry.py --from-cli-models copilot-models.local.json

python3 scripts/route.py --role dev --story @mission.txt \
  --available copilot-models.local.json --json

# Exemple : reprendre l'ID réellement retenu pour le dev.
python3 scripts/route.py --role e2e-validator --story @mission.txt --dev-model claude-opus-5 \
  --max-cost 100 --available copilot-models.local.json --json

# Variante : obtenir le catalogue courant au moment de router.
python3 scripts/route.py --role dev --story @mission.txt --available live --json
```

Préparer `mission.txt` avec le récit réel. `--story` accepte aussi du texte en ligne; `--diff-stats` accepte un résumé ou un fichier. Le classifieur facultatif `--classifier llm` choisit un modèle economy via le registre, puis utilise l'adaptateur expérimental `copilot --model ID -p PROMPT`; en cas d'échec, il revient à l'heuristique. **Cette classification et le catalogue live ne sont pas validés avec un vrai compte Copilot ici.** Les essais emploient `FakeClient` et un CLI simulé; la liste interactive `/models`, les droits de l'organisation et les lancements Herdr attendent le poste de travail.

Le script de découverte utilise directement le protocole RPC du SDK; aucune dépendance Node ou SDK Python n'est nécessaire. Il ne crée aucune session et n'envoie aucun prompt. Une authentification GitHub sans licence ou sans modèles accessibles peut quand même échouer : le code de sortie **4** explique alors quoi vérifier.

Un catalogue JSON du SDK (`models`), de l'API (`data`), une réponse RPC (`result.models`), une liste JSON d'ID ou un fichier texte d'ID conviennent à `--available`. Une liste en ligne convient aussi :

```bash
python3 scripts/route.py --role reviewer --dev-family anthropic \
  --available gpt-6-sol,gemini-4-argon,claude-opus-5 --json
```

Pour garder le registre à jour : `bash scripts/refresh.sh`, ou `make refresh`. Le script importe le catalogue s'il peut l'obtenir, sinon il synchronise les tarifs seulement. `make test` lance la suite et `make route-demo` montre trois choix sans démarrer Herdr. Les [exemples cron et login WSL](docs/router.md#rafraîchissement-automatique) incluent une garde quotidienne; le serveur doit recevoir `reload` après la mise à jour.

## Instructions pour GitHub Copilot

L'agent orchestrateur sur le poste de travail peut suivre ces étapes et copier [`.github/copilot-instructions.md`](.github/copilot-instructions.md) dans son dépôt de travail.

1. Lire le [guide du routeur](docs/router.md) et la [politique de sélection](docs/selection-policy.md), puis actualiser le registre. Obtenir un catalogue avec `list_copilot_models.py`; si l'accès échoue, corriger la connexion ou la licence avant tout lancement.
2. Appeler `route.py --role dev --story @mission.txt --available CATALOGUE --json` avec les signaux et le budget de la mission. Vérifier le code de sortie, conserver `model` et `family` dans l'état de la mission.
3. Appeler le routeur pour chaque autre rôle. Pour `e2e-validator` et `reviewer`, fournir l'ID du dev à `--dev-model`, ou son fournisseur officiel à `--dev-family`. Le serveur `--serve` évite de relire le registre entre les équipiers.
4. Sur un code **2**, **3** ou **4**, interrompre ce lancement et rapporter la raison. Ne jamais contourner le plafond, reprendre le fournisseur du dev pour débloquer une validation ou ignorer un échec live.
5. Fournir `--pane` et éventuellement `--name`, puis démarrer dans des panneaux Herdr existants avec `herdr agent start ... --kind copilot --pane ... -- --model ID`. Utiliser `herdr_argv`, ou lire `herdr_cmd` avec `shlex.split()` sans `eval`. Les [exemples d'intégration](docs/herdr-integration.md) vérifient toute l'équipe avant exécution.
6. Faire exécuter au validateur les scénarios d'acceptation et exiger des preuves de résultats. Le choix d'un autre fournisseur réduit le risque d'erreurs corrélées; il ne remplace pas les tests.

Deux modèles d'un même fournisseur peuvent partager des angles morts. Changer de fournisseur vise à réduire le biais d'auto-évaluation quand le dev est ensuite revu. Il s'agit d'une règle de conception de l'équipe, pas d'une garantie scientifique d'indépendance.

## Coût, fichiers et vérification

Le `cost_index` est une estimation en **GitHub AI Credits par tâche de référence** : 200 000 jetons d'entrée au total, dont la moitié déjà en cache, et 20 000 jetons de sortie, sur plusieurs appels au tarif `Default`. Les prix sont en USD par million de jetons; 1 crédit vaut 0,01 USD selon la [tarification officielle](https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing).

L'estimation exclut la création de cache et les tarifs long contexte. Ce n'est pas un plafond de facture réelle : le CLI peut consommer plus de jetons que la référence. Pour borner une session, le CLI 1.0.105 expose aussi `--max-ai-credits` et `/limits set max-ai-credits N`. Les multiplicateurs des anciens plans annuels sont conservés séparément et ne servent jamais à calculer ce coût.

| Fichier | Utilité |
| --- | --- |
| `models.yaml`, `models.json` | Registre lisible et copie de secours générée avec empreinte du YAML. |
| `upstream/` | Les quatre tables GitHub téléchargées, utilisables pour une sync hors ligne. |
| `scripts/select_model.py` | Filtrage, budget, indépendance des familles et commande Herdr. |
| `scripts/route.py` | Classification, ajustement par rôle, sélection importée et serveur stdio. |
| `scripts/sync_registry.py` | Prix, catégories, ajouts/retraits et rapprochement du catalogue réel. |
| `scripts/refresh.sh`, `Makefile` | Rafraîchissement avec repli, tests et démos du routeur. |
| `scripts/list_copilot_models.py` | Découverte locale par RPC, avec diagnostic de connexion. |
| `docs/evidence/` | Versions, empreintes, catalogue intégré et expérience HTTP simulée. |
| `tests/` | Tests unitaires et essais de commandes avec un CLI simulé. |

Pour rejouer la synchronisation sans réseau :

```bash
python3 scripts/sync_registry.py --upstream-dir upstream
```

La mission routeur est vérifiée avec **76 tests réussis**, dont les 47 tests d'origine. Les [preuves bout en bout](docs/router-proof.md) consignent les commandes, sorties et codes réels : classification, budgets/familles, serveur, faux client LLM et synchronisation provisoire. Le [rapport initial](docs/evidence/validation.json) conserve les preuves de la synchronisation réseau antérieure. Aucun lancement Herdr réel, commit ou push n'a été effectué. Les limites restantes comprennent l'accès réel aux modèles, la classification Copilot, l'ID `gpt-6.1-terra` et le routage HTTP du compte; voir le [rapport de recherche](docs/reverse-engineering.md).
