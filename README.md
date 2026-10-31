# Un modèle Copilot par rôle dans Herdr

L'orchestrateur de utilisateur lance ses équipiers avec GitHub Copilot CLI dans Herdr, sous WSL. Ce dépôt choisit un modèle selon le rôle, le niveau souhaité ou un plafond de coût. Le validateur e2e **et** le réviseur doivent utiliser un fournisseur différent de celui du dev.

Le registre contient **26 modèles** issus du croisement des tarifs officiels et du support CLI. La synchronisation réseau a été exécutée; 25 ID ont aussi été repérés dans le catalogue intégré du CLI 1.0.105. L'accès au compte reste inconnu pour tous les modèles; `gpt-6.1-terra` garde `id_verified: false`.

Les [constats de recherche](docs/reverse-engineering.md) distinguent les sources vérifiées, la simulation HTTP locale et les hypothèses. Aucun catalogue de compte Copilot réel n'a été obtenu sur cette machine sans licence.

## Démarrage

Python **3.10 ou plus récent**. PyYAML sert à la synchronisation; le sélecteur peut utiliser `models.json` si PyYAML est absent.

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v

# Synchronisation avec les quatre tables officielles, par le réseau.
python3 scripts/sync_registry.py

# Choix fondé sur les tarifs publics, avant connexion au compte.
python3 scripts/select_model.py --role dev --level premium
python3 scripts/select_model.py --role doc --max-cost 5 --json
python3 scripts/select_model.py --role e2e-validator --dev-family anthropic --budget-profile premium --json
```

Sans `--available`, une disponibilité inconnue reste admissible et la sortie le signale. Ça permet de planifier hors ligne; l'orchestrateur doit fournir le catalogue réel avant de lancer les équipiers.

Les trois modes `--level`, `--max-cost` et `--budget-profile` sont mutuellement exclusifs. Sans mode explicite, les préférences sont : doc `economy`, test `standard`, dev/e2e/reviewer `premium`, planner `frontier`.

## Sur le poste de travail avec accès Copilot

```bash
copilot login

# Écrit le fichier seulement si le CLI retourne un catalogue non vide.
python3 scripts/list_copilot_models.py --output copilot-models.local.json

# Met à jour les prix et rapproche les ID, politiques et disponibilités du compte.
python3 scripts/sync_registry.py --from-cli-models copilot-models.local.json

python3 scripts/select_model.py --role dev --level premium \
  --available copilot-models.local.json --json

# Exemple : reprendre l'ID réellement retenu pour le dev.
python3 scripts/select_model.py --role e2e-validator --dev-model claude-opus-5 \
  --max-cost 100 --available copilot-models.local.json --json
```

Le script de découverte utilise directement le protocole RPC du SDK; aucune dépendance Node ou SDK Python n'est nécessaire. Il ne crée aucune session et n'envoie aucun prompt. Une authentification GitHub sans licence ou sans modèles accessibles peut quand même échouer : le code de sortie **4** explique alors quoi vérifier.

Un catalogue JSON du SDK (`models`), de l'API (`data`), une réponse RPC (`result.models`), une liste JSON d'ID ou un fichier texte d'ID conviennent à `--available`. Une liste en ligne convient aussi :

```bash
python3 scripts/select_model.py --role reviewer --dev-family anthropic \
  --available gpt-6-sol,gemini-4-argon,claude-opus-5 --json
```

## Instructions pour GitHub Copilot

L'agent orchestrateur sur le poste de travail peut suivre ces étapes et copier [`.github/copilot-instructions.md`](.github/copilot-instructions.md) dans son dépôt de travail.

1. Lire la [politique de sélection](docs/selection-policy.md) et actualiser le registre. Obtenir un catalogue avec `list_copilot_models.py`; si l'accès échoue, corriger la connexion ou la licence avant tout lancement.
2. Choisir le modèle du dev avec le niveau ou le profil demandé, `--available` et `--json`. Vérifier le code de sortie, conserver `id` et `family` dans l'état de la mission.
3. Choisir chaque autre rôle séparément. Pour `e2e-validator` et `reviewer`, fournir l'ID du dev à `--dev-model`, ou son fournisseur officiel à `--dev-family`.
4. Sur un code **2** ou **3**, interrompre ce lancement et rapporter la raison. Ne jamais contourner le plafond ou reprendre le fournisseur du dev pour débloquer une validation.
5. Démarrer dans des panneaux Herdr existants avec `herdr agent start ... --kind copilot --pane ... -- --model ID`. Utiliser `herdr_argv` comme tableau d'arguments, en remplaçant `<pane>`. Les [exemples d'intégration](docs/herdr-integration.md) montrent un lancement vérifié avant exécution.
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
| `scripts/sync_registry.py` | Prix, catégories, ajouts/retraits et rapprochement du catalogue réel. |
| `scripts/list_copilot_models.py` | Découverte locale par RPC, avec diagnostic de connexion. |
| `docs/evidence/` | Versions, empreintes, catalogue intégré et expérience HTTP simulée. |
| `tests/` | Tests unitaires et essais de commandes avec un CLI simulé. |

Pour rejouer la synchronisation sans réseau :

```bash
python3 scripts/sync_registry.py --upstream-dir upstream
```

La livraison a été vérifiée avec **47 tests réussis**, y compris les codes 2/3, les replis, l'import des tables réelles, le protocole RPC simulé et le fonctionnement sans PyYAML. Le [rapport de validation](docs/evidence/validation.json) consigne la synchronisation réseau et les vérifications. Aucun lancement Herdr, commit ou push n'a été effectué. Les limites restantes sont le droit réel aux modèles, l'ID `gpt-6.1-terra` et le routage HTTP du compte; voir le [rapport de recherche](docs/reverse-engineering.md).
