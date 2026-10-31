# Instructions d'orchestration Copilot à copier

Ces instructions sont un exemple pour un orchestrateur multi-agents sous WSL avec Herdr. Adapter les chemins vers ce dépôt et les ID de panneaux au poste de travail.

## Préparer les choix de modèles

- Lire `docs/router.md` et `docs/selection-policy.md` avant de choisir des modèles.
- Utiliser `python3 scripts/list_copilot_models.py --output copilot-models.local.json` sur le poste de travail authentifié, puis `python3 scripts/sync_registry.py --from-cli-models copilot-models.local.json`.
- Fournir ce catalogue à chaque routage avec `--available copilot-models.local.json`. Le routeur accepte aussi `--available live`, dont tout échec donne le code 4. Une disponibilité inconnue ne suffit pas pour démarrer un équipier.
- Avant chaque équipier, appeler `python3 scripts/route.py --role ROLE --story @mission.txt --available copilot-models.local.json --pane PANNEAU --json`. Ajouter `--story-type`, `--files` ou `--diff-stats` lorsque ces signaux sont connus; `--name` permet un nom unique par mission.
- Router séparément chacun des rôles `dev`, `test`, `doc`, `e2e-validator`, `reviewer`, `planner`. La classification heuristique par défaut ne fait aucune inférence. `trivial/standard/complexe/critique` donnent `economy/standard/premium/frontier`, avec un plafond standard pour doc et un minimum premium pour e2e sauf si trivial.
- Un domaine sensible seul (`auth`, `paiement`, `migration`, etc.) ne justifie pas critique. Exiger ce domaine avec un risque (`production`, `rollback`, fuite/perte de données, `bug` ou type bug) ou avec au moins 20 fichiers/1 000 lignes modifiées. Une faille, une CVE, une vulnérabilité ou une injection suffit seule. « refactor paiement » avec 14 fichiers et 830 lignes reste complexe.
- Le niveau d'un modèle vient du score commun de métadonnées GitHub et de la monotonie des générations dans sa lignée, jamais de son prix. Ce score ne constitue pas des benchmarks. Filtrer le budget, puis choisir le meilleur niveau inférieur ou égal au niveau demandé et le moins cher de ce niveau; les replis permis sont décrits dans la politique. Une nouvelle génération moins chère ne doit pas être rétrogradée pour ce motif.
- Utiliser `--max-cost` ou `--budget-profile`, un seul à la fois. Dans le routeur, un profil fournit son plafond financier; la classification garde la préférence de niveau. Le sélecteur direct reste disponible pour imposer un `--level`, avec ses trois modes historiques exclusifs.
- Obtenir les réponses avec `--json` et vérifier le code de sortie avant de lire `model`. Conserver `model` et `family` du choix réellement retenu pour le dev. Vérifier `available: true`, `id_verified: true`, les replis et les avertissements avant Herdr.
- Pour une équipe entière, on peut garder `python3 scripts/route.py --serve` ouvert : une requête JSON-RPC 2.0 par ligne, méthodes `route`, `ping`, `reload`, paramètres en snake_case. Le registre reste en mémoire; envoyer `reload` après une synchronisation. Les erreurs métier sont sous `error.data.exit_code`.
- `bash scripts/refresh.sh` (ou `make refresh`) importe le catalogue si accessible, sinon synchronise les tarifs seulement. Ce repli ne confirme aucun accès au compte. Les exemples de garde quotidienne WSL et de cron sont dans `docs/router.md`.

## Assurer une validation indépendante

- Pour `e2e-validator` **et** `reviewer`, transmettre `--dev-model ID_DU_DEV`, ou `--dev-family FOURNISSEUR_DU_DEV` si l'ID externe n'est pas dans le registre.
- Le fournisseur doit être différent de celui du dev. Deux modèles Claude restent de la même famille Anthropic; deux modèles GPT restent de la famille OpenAI.
- Ne jamais déduire le fournisseur d'origine du seul champ `vendor` d'une API. Utiliser `family` dans le registre, qui vient du fournisseur officiel des prix.
- Un code 3 interdit ce lancement : expliquer le manque de famille indépendante. Un code 2 interdit le lancement sous le budget donné : expliquer le plafond impossible. Un code 4 interdit un lancement fondé sur le catalogue live : vérifier le CLI, la connexion et la licence. Ne jamais contourner ces contraintes.
- Sélectionner tous les modèles nécessaires avant le premier démarrage Herdr pour éviter une équipe partielle à cause d'un échec de sélection.

## Lancer les équipiers

- Lire `docs/herdr-integration.md` et utiliser des panneaux existants, prêts et distincts.
- Passer l'ID concret après le séparateur : `herdr agent start NOM --kind copilot --pane PANNEAU -- --model ID`.
- Passer `--pane` au routeur, puis utiliser le tableau JSON `herdr_argv`, ou lire `herdr_cmd` avec Python et `shlex.split()` comme dans l'exemple Bash. Transmettre les arguments sans `eval` ni interprétation par un shell. Avec le sélecteur direct historique seulement, remplacer son espace réservé `<pane>`.
- Ne pas utiliser de routage `auto` ou `fusion` quand la famille doit être garantie à l'avance.
- Sur le CLI 1.0.105, ajouter `--context default` pour la référence tarifaire et, si la mission impose un plafond de session, `--max-ai-credits N`. Vérifier les options sur la version installée.
- Le `cost_index` porte sur une tâche de référence; il ne garantit pas le coût total d'une session réelle. Ne pas le confondre avec les multiplicateurs des anciens plans annuels.

## Exiger des preuves

- Faire exécuter au validateur les scénarios d'acceptation, les tests et les vérifications e2e pertinents. Exiger les résultats observés et les limites de la vérification.
- Une famille différente vise à réduire les erreurs corrélées et le biais d'auto-évaluation; elle ne remplace pas les preuves.
- Conserver les champs manuels dans le registre selon la politique documentée. Ne jamais inventer de prix ni confirmer un accès à partir du seul catalogue intégré hors ligne.
- Un modèle sans comparatif ou à lignée inconnue reçoit le niveau prudent de sa catégorie, sous réserve du plancher de monotonie, avec `tier_provisoire: true` et une note « à valider ». Le routeur l'accepte et l'annonce dans `reason`/`warnings`. Le marqueur est recalculé à la sync et disparaît si les signaux deviennent suffisants ou avec un override explicite sur le modèle.
- `tier_override: economy|standard|premium|frontier` dans `models.yaml` prévaut sur le score après resynchronisation; ne pas modifier seulement `tier`. Les variantes d'une même version partagent leur niveau. Un conflit d'overrides entre variantes ou avec le plancher d'une génération antérieure fait échouer la sync avant écriture : corriger les overrides de la lignée de façon cohérente. Opus 5.5 atteint `frontier` sans override.
- `--classifier llm` utilise un client injecté ou l'adaptateur expérimental `copilot --model ID_ECONOMY -p PROMPT`. Un seul mot de classe est accepté; toute défaillance revient à l'heuristique. Ici, seuls `FakeClient` et le CLI simulé sont vérifiés. Aucune organisation Copilot ni Herdr n'est accessible : la classification réelle, `/models` et le catalogue live restent à valider sur le poste de travail.
- Lancer `python3 -m unittest discover -s tests -v` et lire `docs/tiering-proof.md` pour les scénarios avant/après du correctif et les 26 niveaux; `docs/router-proof.md` conserve les preuves historiques du routeur.
- Lire le [guide d’évaluation](../eval/README.md), puis lancer `uv run python eval/run_eval.py` et `uv run python eval/run_eval.py --judge --fake-judge` (ou `python3` dans l’environnement installé). Les 104 cas francophone attendent des propriétés, jamais un ID choisi. Consulter [le rapport](../eval/report.md) et [les preuves](../eval/proof.md); garder les attentes justifiées lorsqu’un cas révèle un bug du routeur. L’injection de dépendances est un patron de conception; elle ne suffit pas à signaler un risque de sécurité, alors qu’une injection SQL reste critique.
- Sur le poste de travail, actualiser le registre puis lancer `uv run python eval/run_eval.py --available live`. Une dérive (nouveau modèle org sans tier ou modèle actif du registre absent de l’org) exige un refresh et une revue du registre. Sans capture live, le statut SAUTÉ ne confirme aucun accès. Le juge réel est facultatif : `uv run python eval/run_eval.py --judge --copilot --judge-model ID_MODELE_ECO`; moyenne minimale 0,85, toute erreur de juge bloquante. Le juge Copilot réel et /models live n’ont pas été testés ici.
- Rapporter clairement les faits vérifiés, les simulations et les hypothèses restantes.
