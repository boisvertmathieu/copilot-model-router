# Instructions d'orchestration Copilot à copier

Ces instructions sont un exemple pour l'orchestrateur sous WSL avec Herdr. Adapter les chemins vers ce dépôt et les ID de panneaux au poste de travail.

## Préparer les choix de modèles

- Lire `docs/selection-policy.md` avant de choisir des modèles.
- Utiliser `python3 scripts/list_copilot_models.py --output copilot-models.local.json` sur le poste de travail authentifié, puis `python3 scripts/sync_registry.py --from-cli-models copilot-models.local.json`.
- Fournir ce catalogue à chaque sélection avec `--available copilot-models.local.json`. Une disponibilité inconnue ne suffit pas pour démarrer un équipier.
- Choisir séparément chacun des rôles `dev`, `test`, `doc`, `e2e-validator`, `reviewer`, `planner`, selon le niveau ou le budget de la mission. Utiliser un seul des modes `--level`, `--max-cost`, `--budget-profile`.
- Obtenir les réponses avec `--json` et vérifier le code de sortie avant de lire `id`. Conserver l'ID et la famille du modèle réellement retenu pour le dev.

## Assurer une validation indépendante

- Pour `e2e-validator` **et** `reviewer`, transmettre `--dev-model ID_DU_DEV`, ou `--dev-family FOURNISSEUR_DU_DEV` si l'ID externe n'est pas dans le registre.
- Le fournisseur doit être différent de celui du dev. Deux modèles Claude restent de la même famille Anthropic; deux modèles GPT restent de la famille OpenAI.
- Ne jamais déduire le fournisseur d'origine du seul champ `vendor` d'une API. Utiliser `family` dans le registre, qui vient du fournisseur officiel des prix.
- Un code 3 interdit ce lancement : expliquer le manque de famille indépendante. Un code 2 interdit le lancement sous le budget donné : expliquer le plafond impossible. Ne jamais contourner ces contraintes.
- Sélectionner tous les modèles nécessaires avant le premier démarrage Herdr pour éviter une équipe partielle à cause d'un échec de sélection.

## Lancer les équipiers

- Lire `docs/herdr-integration.md` et utiliser des panneaux existants, prêts et distincts.
- Passer l'ID concret après le séparateur : `herdr agent start NOM --kind copilot --pane PANNEAU -- --model ID`.
- Préférer le tableau JSON `herdr_argv`, remplacer `<pane>`, puis transmettre les arguments sans `eval` ni interprétation par un shell.
- Ne pas utiliser de routage `auto` ou `fusion` quand la famille doit être garantie à l'avance.
- Sur le CLI 1.0.105, ajouter `--context default` pour la référence tarifaire et, si la mission impose un plafond de session, `--max-ai-credits N`. Vérifier les options sur la version installée.
- Le `cost_index` porte sur une tâche de référence; il ne garantit pas le coût total d'une session réelle. Ne pas le confondre avec les multiplicateurs des anciens plans annuels.

## Exiger des preuves

- Faire exécuter au validateur les scénarios d'acceptation, les tests et les vérifications e2e pertinents. Exiger les résultats observés et les limites de la vérification.
- Une famille différente vise à réduire les erreurs corrélées et le biais d'auto-évaluation; elle ne remplace pas les preuves.
- Conserver les champs manuels dans le registre selon la politique documentée. Ne jamais inventer de prix ni confirmer un accès à partir du seul catalogue intégré hors ligne.
- Rapporter clairement les faits vérifiés, les simulations et les hypothèses restantes.
