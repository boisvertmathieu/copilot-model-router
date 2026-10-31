# Évaluer le routeur pas à pas

La suite rejoue **104 récits Jira synthétiques en français francophone** avec la fonction
`route()` de [scripts/route.py](../scripts/route.py), dans le processus Python.
Elle importe le sélecteur et les utilitaires existants; les modèles simulés sont
construits par la vraie synchronisation dans un registre temporaire.
Python **3.10+** et **PyYAML** sont les seules dépendances. Aucun appel d’inférence
n’est fait dans le mode par défaut ou avec FakeJudge. Aucun agent Herdr n’est démarré.

## 1. Démarrage rapide avec uv, sans Copilot

Depuis la racine du dépôt, avec `uv` installé :

```bash
uv run python eval/run_eval.py
```

`uv` lit `pyproject.toml`, prépare `.venv` et installe PyYAML. L’exécution affiche les
taux par rôle et par tier, puis écrit [report.md](report.md). Le code de sortie
est **0** si toutes les propriétés et les invariants passent. Les refus attendus
(budget impossible, famille impossible, découverte inaccessible) comptent comme
des succès. Sans catalogue live, la dérive affiche **SAUTÉ** et ne bloque pas.

Pour ajouter le juge reproductible de CI :

```bash
uv run python eval/run_eval.py --judge --fake-judge
uv run python -m unittest discover -s tests
```

`--judge` seul choisit aussi FakeJudge. `--fake-judge` seul l’active également.
Le [rapport livré](report.md) provient du passage réel combinant vérification
déterministe et FakeJudge; [proof.md](proof.md) contient les sorties capturées.

## 2. Même parcours avec Python classique

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 eval/run_eval.py
python3 eval/run_eval.py --judge --fake-judge
python3 -m unittest discover -s tests
```

Sous Windows, activer `.venv\Scripts\activate` à la place. La synchronisation
`scripts/refresh.sh` exige Bash, disponible sous WSL. Les commandes d’évaluation
sans `--refresh` sont en Python.

## 3. Vérifier les modèles de l’organisation

Sur le poste de travail authentifié avec les droits Copilot :

```bash
copilot login
uv run bash scripts/refresh.sh
uv run python eval/run_eval.py --available live
```

L’équivalent classique utilise `PYTHON=python3 bash scripts/refresh.sh`, puis
`python3 eval/run_eval.py --available live`. On peut regrouper les deux étapes :

```bash
uv run python eval/run_eval.py --refresh --available live
```

`--refresh` lance le script existant avec le registre YAML demandé (la sync ne
réécrit pas directement un registre JSON). Ce script peut
actualiser les tarifs sans catalogue si Copilot est inaccessible; l’étape
`--available live` exige ensuite une découverte réussie et retourne **4** sinon.
`--copilot-cli CHEMIN` et `--timeout SECONDES` règlent la découverte et le juge.

Pour conserver une capture réutilisable :

```bash
uv run python scripts/list_copilot_models.py --output copilot-models.local.json
uv run python eval/run_eval.py --available copilot-models.local.json
```

Une capture JSON marquée `source: models.list` active aussi le contrôle de dérive.
Il échoue si un modèle de l’organisation n’a pas de tier associé ou si un modèle
CLI actif du registre manque à l’organisation. Les alias et les noms sont
rapprochés par les utilitaires du registre; les entrées retirées du registre sont
exclues. Une politique désactivée indique encore la présence dans le catalogue,
mais elle interdit la sélection. L’erreur demande de **lancer refresh**, puis de
revoir les modèles et les tiers du registre choisi.

Une simple liste d’ID ou un fichier sans provenance `models.list` contraint la
sélection mais ne prouve pas un catalogue org complet : la dérive reste **SAUTÉ**.
`--live-catalog FICHIER` fournit explicitement une capture pour l’audit, y compris
une liste simulée pour tester la garde. Cette option n’ajoute aucun modèle disponible
à la sélection. Exemple reproductible d’une dérive simulée :

```bash
python3 - <<'PY'
import json
from pathlib import Path
registry = json.loads(Path('models.json').read_text(encoding='utf-8'))
ids = [m['id'] for m in registry['models'] if m.get('cli') and not m.get('retired')]
Path('/tmp/cmr-org-simulee.json').write_text(json.dumps(ids[1:] + ['nouveau-modele-org']), encoding='utf-8')
PY
uv run python eval/run_eval.py --live-catalog /tmp/cmr-org-simulee.json --report /tmp/cmr-derive.md
# Échec attendu (code 1) : un nouveau modèle sans tier et un modèle absent.
```

La disponibilité globale s’applique aux cas ordinaires et est intersectée avec
la restriction `available` de chaque scénario. Les politiques restrictives sont
conservées. Un catalogue org trop restreint peut donc faire échouer une attente de
tier ou rendre un budget impossible; le rapport explique le résultat obtenu.
Les deux cas `simulate_model` emploient un registre temporaire et un catalogue
fictif lors des passages **sans `--available`**. Avec un catalogue global, ils
sont explicitement **sautés**, exclus des taux et des scores : un modèle fictif
ne peut pas contourner la disponibilité réelle. Les 102 autres cas restent
exécutés. Le rapport et les champs JSON `skipped`, `skip_reason` et `catalog_scope`
identifient ces scénarios. Un filtre qui ne laisse que des cas sautés échoue.
Le cas de panne live utilise un exécutable absent dans un répertoire temporaire;
il ne sélectionne aucun modèle et reste exécuté dans les deux modes.

## 4. Demander une appréciation au juge Copilot

Choisir un ID économique réellement présent dans le catalogue, puis remplacer
`ID_MODELE_ECO` dans cette commande :

```bash
uv run python eval/run_eval.py --judge --copilot --judge-model ID_MODELE_ECO
# Avec les disponibilités réelles et un seuil explicite :
uv run python eval/run_eval.py --available live --judge --copilot \
  --judge-model ID_MODELE_ECO --threshold 0.85 --timeout 30
```

En Python classique, remplacer `uv run python` par `python3`.
CopilotJudge appelle `copilot --model ID -p PROMPT` une fois par cas et demande
exactement `{"score": 0.0, "justification": "..."}`. L’interface commune est
`judge(case, decision) -> {score, justification}`. Un JSON brut, un bloc Markdown
ou un objet précédé de diagnostics est accepté; plusieurs verdicts, clés
dupliquées, scores non finis/hors bornes et justifications vides sont refusés.
Une erreur d’exécutable, de parsing ou de délai compte **0**, est rapportée et
n’empêche pas l’évaluation des cas suivants.

**Le juge Copilot réel et /models live n’ont pas été testés ici.** Les tests
emploient un faux exécutable, sans connexion ni licence. La pertinence réelle
des choix et la qualité effective des modèles restent à mesurer avec le compte.

## 5. Lire le rapport, les seuils et le JSON

Le rapport présente les propriétés globales, les six rôles, les quatre tiers,
les refus (« aucun »), les éventuels scénarios sautés, la pertinence facultative,
les invariants et la dérive.
Les tiers des tableaux sont ceux **choisis**, après budget et contraintes de rôle.
Une ligne sans cas affiche « — ». Chaque échec nomme son cas et la propriété violée.

- **Déterministe** : 100 % des cas doivent passer; une seule violation échoue.
- **Invariants** : les versions d’une lignée ne régressent pas en tier; les variantes
  d’une même génération partagent leur tier. Le budget, la famille indépendante,
  les bornes doc/e2e et le catalogue transmis au routeur sont vérifiés séparément.
- **Juge** : score moyen global au moins **0,85** par défaut. Le taux de succès du
  juge est la proportion de scores individuels au moins au seuil; c’est un diagnostic.
  Un score individuel faible n’échoue pas seul si la moyenne passe. Toute erreur
  de juge fait échouer le passage, même si la moyenne reste supérieure au seuil.
- **FakeJudge** : score `1 - distance_en_tiers / 3`, distance zéro dans la plage
  attendue. Un refus attendu vaut 1, un code inattendu vaut 0. Ce score vérifie le
  mécanisme de CI; il ne mesure pas la qualité sémantique des modèles.
- **Dérive** : OK ou SAUTÉ permet de passer; ÉCHEC bloque.

Le script retourne **0** au succès, **1** pour une évaluation ou configuration en
échec, **4** pour une découverte live inaccessible. Une erreur de syntaxe CLI
retourne **2** via argparse. Ces codes du runner sont distincts des `expect_exit`
du routeur dans les cas (0, 2, 3, 4).

```bash
uv run python eval/run_eval.py --judge --fake-judge --json > /tmp/cmr-eval.json
uv run python eval/run_eval.py --filter role/reviewer --report /tmp/revue.md
uv run python eval/run_eval.py --filter id/budget --json --report /tmp/budgets.md
uv run python eval/run_eval.py --cases eval/cases.yaml --registry models.json
uv run python eval/run_eval.py --available gpt-6-sol,claude-opus-5.5 --report /tmp/catalogue.md
```

Sans préfixe, `--filter` accepte un rôle ou un fragment d’ID. Un filtre vide de
résultats échoue. Les valeurs par défaut de `--cases`, `--registry` et `--report`
sont relatives au dépôt; un chemin explicite est relatif au répertoire courant.
`--json` garde stdout lisible par une machine et écrit quand même le rapport Markdown.
Le JSON contient `summary`, `by_role`, `by_tier`, `results` (décisions et erreurs),
`invariant_failures`, `drift`, `threshold`, `passed` et `exit_code`.

## 6. Ajouter un cas

Ajouter une entrée dans [cases.yaml](cases.yaml), avec un ID unique et un récit
réaliste. Décrire le comportement attendu avant d’observer le résultat :

```yaml
- id: test-filtre-etablissement
  inputs:
    role: test
    story: "QA-701 — Couvrir le filtre par établissement et la pagination."
    files: 4
    diff_stats: "4 files changed, 130 insertions(+), 20 deletions(-)"
    max_cost: 35
  expect_exit: 0
  expect:
    level: standard
    tier: [economy, standard]
    max_cost: 35
    cost_range: [1, 35]
```

`level` accepte une classe ou une liste de classes; `tier` accepte un tier ou
`[min, max]` inclusif. Les autres propriétés possibles sont `family_not` (un
fournisseur ou une liste), `tier_provisoire` et `warning_contains`. Un validateur
ou reviewer exige `dev_model` ou `dev_family`. Un refus attendu utilise
`expect_exit: 2|3|4` et `expect: {}`. Ne jamais attendre un ID choisi; les ID sont
permis uniquement comme entrées de disponibilité ou comme modèle du dev.

Pour un nouveau modèle, reprendre `simulate_model` des deux cas existants : ses
métadonnées synthétiques sont injectées dans les tables locales, puis passées à
`sync_registry.build_registry` et à `load_registry` via un fichier temporaire.
Le marqueur provisoire est ainsi calculé par la politique réelle. Les valeurs
de prix de ces modèles sont fictives. Les fichiers `models.yaml/json` du dépôt
restent intacts pendant les évaluations sans `--refresh`.

Rejouer le cas avec `--filter id/IDENTIFIANT`, puis toute la suite et les tests.
Si le résultat contredit une attente justifiée, examiner le routeur et corriger
le problème; ne pas élargir une attente pour cacher une régression.

## Bugs trouvés

Le premier passage a produit **102/104** succès. Les cas
`injection-dependances` et `dependency-injection` attendaient respectivement
`standard/standard` et `complexe/premium`. Le routeur les classait tous deux
`critique/frontier` parce que le mot « injection » était traité comme un risque
de sécurité sans tenir compte du patron de conception.

Le correctif dans `scripts/route.py` retire seulement les expressions françaises
« injection de dépendances » et anglaises « dependency injection » du texte analysé
pour les risques de sécurité. Les signaux de portée restent évalués, et une injection
SQL dans le même récit reste critique. Les attentes des deux cas ont été conservées.
Un test de régression vérifie les variantes françaises/anglaises et le récit mixte.
Le passage après correction réussit **104/104**; voir [proof.md](proof.md).
