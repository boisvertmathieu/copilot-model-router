# Preuves d’exécution de la suite d’évaluation

Capturées le 2026-10-31T02:19:24.308322+00:00 dans `/workspace/cmr`.

Les sorties ci-dessous proviennent des commandes exécutées, avec leur code de sortie observé. Les catalogues org sont **simulés**, sans appel au compte Copilot. Le juge Copilot réel et /models live n’ont pas été testés ici. Les tests CopilotJudge utilisent un faux exécutable, y compris pour le timeout. L’invocation de `--refresh` est testée avec subprocess simulé; aucune nouvelle sync réseau n’a été effectuée.

## Faux positif trouvé avant correction

Le premier passage `python3 eval/run_eval.py --json` a laissé la sortie dans `/tmp/cmr-eval-first.json`. Voici les champs capturés pertinents. Les attentes des deux cas sont restées identiques après le correctif du routeur.

```json
{
  "exit_code": 1,
  "summary": {
    "total": 104,
    "passed": 102,
    "failed": 2,
    "success_rate": 0.9807692307692307
  },
  "failures": [
    {
      "id": "injection-dependances",
      "failures": [
        "Classe attendue ['standard'], obtenue critique.",
        "Tier attendu standard, obtenu frontier."
      ]
    },
    {
      "id": "dependency-injection",
      "failures": [
        "Classe attendue ['complexe'], obtenue critique.",
        "Tier attendu premium, obtenu frontier."
      ]
    }
  ]
}
```

## Préparer les catalogues simulés

Les trois fichiers suivants ont été générés à partir des ID CLI actifs de `models.json`. Le champ `source` active l’audit de dérive; `simulation: true` précise leur provenance fictive.

```python
import json
from pathlib import Path
directory = Path('/tmp/cmr-eval-proof')
directory.mkdir(exist_ok=True)
registry = json.loads(Path('models.json').read_text(encoding='utf-8'))
entries = [{'id': m['id']} for m in registry['models'] if m.get('cli') and not m.get('retired')]
snapshots = {
    'org-complete-simulee': entries,
    'org-nouveau-simulee': entries + [{'id': 'nouveau-modele-org'}],
    'org-retrait-simulee': entries[1:],
}
for name, models in snapshots.items():
    (directory / (name + '.json')).write_text(
        json.dumps({'source': 'models.list', 'simulation': True, 'models': models}), encoding='utf-8')
```

Le modèle omis dans le troisième catalogue est `claude-fable-5`.

## Mode déterministe

```bash
python3 eval/run_eval.py --report /tmp/cmr-eval-proof/deterministe.md
```

Code de sortie observé : **0**.

```text
# Évaluation du routeur

Généré le 2026-10-31T02:19:15.492727+00:00.

Résultat : **RÉUSSI** — 104/104 cas conformes (100.0%).

Les codes de refus attendus comptent comme des succès. Les tiers ci-dessous sont les tiers choisis; « aucun » regroupe les refus et les scénarios sautés. Les modèles fictifs sont testés hors ligne; leurs scénarios sont sautés avec un catalogue global.

## Par rôle

| Groupe | Cas exécutés | Réussis | Sautés | Taux |
| --- | ---: | ---: | ---: | ---: |
| dev | 32 | 32 | 0 | 100.0% |
| test | 15 | 15 | 0 | 100.0% |
| doc | 15 | 15 | 0 | 100.0% |
| e2e-validator | 14 | 14 | 0 | 100.0% |
| reviewer | 16 | 16 | 0 | 100.0% |
| planner | 12 | 12 | 0 | 100.0% |

## Par tier

| Groupe | Cas exécutés | Réussis | Sautés | Taux |
| --- | ---: | ---: | ---: | ---: |
| economy | 25 | 25 | 0 | 100.0% |
| standard | 29 | 29 | 0 | 100.0% |
| premium | 23 | 23 | 0 | 100.0% |
| frontier | 19 | 19 | 0 | 100.0% |
| aucun | 8 | 8 | 0 | 100.0% |

## Pertinence du juge

SAUTÉ — aucun juge demandé.

## Invariants globaux

Aucune violation : monotonie des lignées, budget, indépendance des familles, bornes par rôle et disponibilité.

## Dérive du catalogue

**SAUTÉ** — Aucune liste live ou capture models.list fournie.

- Modèles org sans tier associé : aucun.
- Modèles du registre absents de l'org : aucun.

## Échecs et explications

Aucun échec de cas ni erreur de juge.

Les violations du registre et la dérive sont détaillées ci-dessus. Un catalogue d'organisation plus restreint peut rendre certaines attentes impossibles; inspecter les contraintes avant de modifier un cas.
Rapport : /tmp/cmr-eval-proof/deterministe.md
```

## Mode déterministe avec FakeJudge — rapport livré

```bash
python3 eval/run_eval.py --judge --fake-judge
```

Code de sortie observé : **0**.

```text
# Évaluation du routeur

Généré le 2026-10-31T02:19:15.870298+00:00.

Résultat : **RÉUSSI** — 104/104 cas conformes (100.0%).

Les codes de refus attendus comptent comme des succès. Les tiers ci-dessous sont les tiers choisis; « aucun » regroupe les refus et les scénarios sautés. Les modèles fictifs sont testés hors ligne; leurs scénarios sont sautés avec un catalogue global.

## Par rôle

| Groupe | Cas exécutés | Réussis | Sautés | Taux |
| --- | ---: | ---: | ---: | ---: |
| dev | 32 | 32 | 0 | 100.0% |
| test | 15 | 15 | 0 | 100.0% |
| doc | 15 | 15 | 0 | 100.0% |
| e2e-validator | 14 | 14 | 0 | 100.0% |
| reviewer | 16 | 16 | 0 | 100.0% |
| planner | 12 | 12 | 0 | 100.0% |

## Par tier

| Groupe | Cas exécutés | Réussis | Sautés | Taux |
| --- | ---: | ---: | ---: | ---: |
| economy | 25 | 25 | 0 | 100.0% |
| standard | 29 | 29 | 0 | 100.0% |
| premium | 23 | 23 | 0 | 100.0% |
| frontier | 19 | 19 | 0 | 100.0% |
| aucun | 8 | 8 | 0 | 100.0% |

## Pertinence du juge

Juge : **FakeJudge**. Seuil global : **0.85**.

Score moyen : **1.000**; succès individuels au seuil : **100.0%**; erreurs : **0**.

| Groupe | Score moyen | Succès au seuil | Erreurs |
| --- | ---: | ---: | ---: |
| dev | 1.000 | 100.0% | 0 |
| test | 1.000 | 100.0% | 0 |
| doc | 1.000 | 100.0% | 0 |
| e2e-validator | 1.000 | 100.0% | 0 |
| reviewer | 1.000 | 100.0% | 0 |
| planner | 1.000 | 100.0% | 0 |
| economy | 1.000 | 100.0% | 0 |
| standard | 1.000 | 100.0% | 0 |
| premium | 1.000 | 100.0% | 0 |
| frontier | 1.000 | 100.0% | 0 |
| aucun | 1.000 | 100.0% | 0 |

FakeJudge mesure l'écart aux attentes déclarées; son score ne valide pas la qualité réelle d'un modèle. Le juge Copilot réel et /models live n'ont pas été testés ici.

## Invariants globaux

Aucune violation : monotonie des lignées, budget, indépendance des familles, bornes par rôle et disponibilité.

## Dérive du catalogue

**SAUTÉ** — Aucune liste live ou capture models.list fournie.

- Modèles org sans tier associé : aucun.
- Modèles du registre absents de l'org : aucun.

## Échecs et explications

Aucun échec de cas ni erreur de juge.

Les violations du registre et la dérive sont détaillées ci-dessus. Un catalogue d'organisation plus restreint peut rendre certaines attentes impossibles; inspecter les contraintes avant de modifier un cas.
Rapport : /workspace/cmr/eval/report.md
```

## Catalogue org simulé complet : garde OK

```bash
python3 eval/run_eval.py --available /tmp/cmr-eval-proof/org-complete-simulee.json --report /tmp/cmr-eval-proof/org-complete-simulee.md
```

Code de sortie observé : **0**.

```text
# Évaluation du routeur

Généré le 2026-10-31T02:19:16.177544+00:00.

Résultat : **RÉUSSI** — 102/102 cas conformes (100.0%).

Les codes de refus attendus comptent comme des succès. Les tiers ci-dessous sont les tiers choisis; « aucun » regroupe les refus et les scénarios sautés. Les modèles fictifs sont testés hors ligne; leurs scénarios sont sautés avec un catalogue global.

## Par rôle

| Groupe | Cas exécutés | Réussis | Sautés | Taux |
| --- | ---: | ---: | ---: | ---: |
| dev | 31 | 31 | 1 | 100.0% |
| test | 14 | 14 | 1 | 100.0% |
| doc | 15 | 15 | 0 | 100.0% |
| e2e-validator | 14 | 14 | 0 | 100.0% |
| reviewer | 16 | 16 | 0 | 100.0% |
| planner | 12 | 12 | 0 | 100.0% |

## Par tier

| Groupe | Cas exécutés | Réussis | Sautés | Taux |
| --- | ---: | ---: | ---: | ---: |
| economy | 25 | 25 | 0 | 100.0% |
| standard | 28 | 28 | 0 | 100.0% |
| premium | 22 | 22 | 0 | 100.0% |
| frontier | 19 | 19 | 0 | 100.0% |
| aucun | 8 | 8 | 2 | 100.0% |

## Scénarios sautés

2 scénario(s) exclu(s) des taux et des scores :

- nouveau-modele-provisoire : Ce scénario ajoute un modèle fictif; le rejouer sans --available pour tester son registre temporaire.
- nouveau-modele-lignee-inconnue : Ce scénario ajoute un modèle fictif; le rejouer sans --available pour tester son registre temporaire.

## Pertinence du juge

SAUTÉ — aucun juge demandé.

## Invariants globaux

Aucune violation : monotonie des lignées, budget, indépendance des familles, bornes par rôle et disponibilité.

## Dérive du catalogue

**OK** — Chaque modèle de l'organisation a un tier; tous les modèles CLI actifs sont présents.

- Modèles org sans tier associé : aucun.
- Modèles du registre absents de l'org : aucun.

## Échecs et explications

Aucun échec de cas ni erreur de juge.

Les violations du registre et la dérive sont détaillées ci-dessus. Un catalogue d'organisation plus restreint peut rendre certaines attentes impossibles; inspecter les contraintes avant de modifier un cas.
Rapport : /tmp/cmr-eval-proof/org-complete-simulee.md
```

## Nouveau modèle org simulé sans tier : échec attendu

```bash
python3 eval/run_eval.py --available /tmp/cmr-eval-proof/org-nouveau-simulee.json --report /tmp/cmr-eval-proof/org-nouveau-simulee.md
```

Code de sortie observé : **1**.

```text
# Évaluation du routeur

Généré le 2026-10-31T02:19:16.498635+00:00.

Résultat : **ÉCHEC** — 102/102 cas conformes (100.0%).

Les codes de refus attendus comptent comme des succès. Les tiers ci-dessous sont les tiers choisis; « aucun » regroupe les refus et les scénarios sautés. Les modèles fictifs sont testés hors ligne; leurs scénarios sont sautés avec un catalogue global.

## Par rôle

| Groupe | Cas exécutés | Réussis | Sautés | Taux |
| --- | ---: | ---: | ---: | ---: |
| dev | 31 | 31 | 1 | 100.0% |
| test | 14 | 14 | 1 | 100.0% |
| doc | 15 | 15 | 0 | 100.0% |
| e2e-validator | 14 | 14 | 0 | 100.0% |
| reviewer | 16 | 16 | 0 | 100.0% |
| planner | 12 | 12 | 0 | 100.0% |

## Par tier

| Groupe | Cas exécutés | Réussis | Sautés | Taux |
| --- | ---: | ---: | ---: | ---: |
| economy | 25 | 25 | 0 | 100.0% |
| standard | 28 | 28 | 0 | 100.0% |
| premium | 22 | 22 | 0 | 100.0% |
| frontier | 19 | 19 | 0 | 100.0% |
| aucun | 8 | 8 | 2 | 100.0% |

## Scénarios sautés

2 scénario(s) exclu(s) des taux et des scores :

- nouveau-modele-provisoire : Ce scénario ajoute un modèle fictif; le rejouer sans --available pour tester son registre temporaire.
- nouveau-modele-lignee-inconnue : Ce scénario ajoute un modèle fictif; le rejouer sans --available pour tester son registre temporaire.

## Pertinence du juge

SAUTÉ — aucun juge demandé.

## Invariants globaux

Aucune violation : monotonie des lignées, budget, indépendance des familles, bornes par rôle et disponibilité.

## Dérive du catalogue

**ÉCHEC** — Dérive détectée : lancer refresh (bash scripts/refresh.sh), puis revoir les niveaux.

- Modèles org sans tier associé : nouveau-modele-org.
- Modèles du registre absents de l'org : aucun.

## Échecs et explications

Aucun échec de cas ni erreur de juge.

Les violations du registre et la dérive sont détaillées ci-dessus. Un catalogue d'organisation plus restreint peut rendre certaines attentes impossibles; inspecter les contraintes avant de modifier un cas.
Rapport : /tmp/cmr-eval-proof/org-nouveau-simulee.md
```

## Modèle absent de l’org simulée : échec attendu

```bash
python3 eval/run_eval.py --available /tmp/cmr-eval-proof/org-retrait-simulee.json --report /tmp/cmr-eval-proof/org-retrait-simulee.md
```

Code de sortie observé : **1**.

```text
# Évaluation du routeur

Généré le 2026-10-31T02:19:16.808307+00:00.

Résultat : **ÉCHEC** — 102/102 cas conformes (100.0%).

Les codes de refus attendus comptent comme des succès. Les tiers ci-dessous sont les tiers choisis; « aucun » regroupe les refus et les scénarios sautés. Les modèles fictifs sont testés hors ligne; leurs scénarios sont sautés avec un catalogue global.

## Par rôle

| Groupe | Cas exécutés | Réussis | Sautés | Taux |
| --- | ---: | ---: | ---: | ---: |
| dev | 31 | 31 | 1 | 100.0% |
| test | 14 | 14 | 1 | 100.0% |
| doc | 15 | 15 | 0 | 100.0% |
| e2e-validator | 14 | 14 | 0 | 100.0% |
| reviewer | 16 | 16 | 0 | 100.0% |
| planner | 12 | 12 | 0 | 100.0% |

## Par tier

| Groupe | Cas exécutés | Réussis | Sautés | Taux |
| --- | ---: | ---: | ---: | ---: |
| economy | 25 | 25 | 0 | 100.0% |
| standard | 28 | 28 | 0 | 100.0% |
| premium | 22 | 22 | 0 | 100.0% |
| frontier | 19 | 19 | 0 | 100.0% |
| aucun | 8 | 8 | 2 | 100.0% |

## Scénarios sautés

2 scénario(s) exclu(s) des taux et des scores :

- nouveau-modele-provisoire : Ce scénario ajoute un modèle fictif; le rejouer sans --available pour tester son registre temporaire.
- nouveau-modele-lignee-inconnue : Ce scénario ajoute un modèle fictif; le rejouer sans --available pour tester son registre temporaire.

## Pertinence du juge

SAUTÉ — aucun juge demandé.

## Invariants globaux

Aucune violation : monotonie des lignées, budget, indépendance des familles, bornes par rôle et disponibilité.

## Dérive du catalogue

**ÉCHEC** — Dérive détectée : lancer refresh (bash scripts/refresh.sh), puis revoir les niveaux.

- Modèles org sans tier associé : aucun.
- Modèles du registre absents de l'org : claude-fable-5.

## Échecs et explications

Aucun échec de cas ni erreur de juge.

Les violations du registre et la dérive sont détaillées ci-dessus. Un catalogue d'organisation plus restreint peut rendre certaines attentes impossibles; inspecter les contraintes avant de modifier un cas.
Rapport : /tmp/cmr-eval-proof/org-retrait-simulee.md
```

## Parcours uv

```bash
uv run python eval/run_eval.py --report /tmp/cmr-eval-proof/uv.md
```

Code de sortie observé : **0**.

Dans ce bac à sable, `UV_CACHE_DIR=/tmp/cmr-uv-cache` et `UV_LINK_MODE=copy` placent le cache dans le répertoire autorisé; aucune dépendance supplémentaire.

```text
# Évaluation du routeur

Généré le 2026-10-31T02:19:17.191493+00:00.

Résultat : **RÉUSSI** — 104/104 cas conformes (100.0%).

Les codes de refus attendus comptent comme des succès. Les tiers ci-dessous sont les tiers choisis; « aucun » regroupe les refus et les scénarios sautés. Les modèles fictifs sont testés hors ligne; leurs scénarios sont sautés avec un catalogue global.

## Par rôle

| Groupe | Cas exécutés | Réussis | Sautés | Taux |
| --- | ---: | ---: | ---: | ---: |
| dev | 32 | 32 | 0 | 100.0% |
| test | 15 | 15 | 0 | 100.0% |
| doc | 15 | 15 | 0 | 100.0% |
| e2e-validator | 14 | 14 | 0 | 100.0% |
| reviewer | 16 | 16 | 0 | 100.0% |
| planner | 12 | 12 | 0 | 100.0% |

## Par tier

| Groupe | Cas exécutés | Réussis | Sautés | Taux |
| --- | ---: | ---: | ---: | ---: |
| economy | 25 | 25 | 0 | 100.0% |
| standard | 29 | 29 | 0 | 100.0% |
| premium | 23 | 23 | 0 | 100.0% |
| frontier | 19 | 19 | 0 | 100.0% |
| aucun | 8 | 8 | 0 | 100.0% |

## Pertinence du juge

SAUTÉ — aucun juge demandé.

## Invariants globaux

Aucune violation : monotonie des lignées, budget, indépendance des familles, bornes par rôle et disponibilité.

## Dérive du catalogue

**SAUTÉ** — Aucune liste live ou capture models.list fournie.

- Modèles org sans tier associé : aucun.
- Modèles du registre absents de l'org : aucun.

## Échecs et explications

Aucun échec de cas ni erreur de juge.

Les violations du registre et la dérive sont détaillées ci-dessus. Un catalogue d'organisation plus restreint peut rendre certaines attentes impossibles; inspecter les contraintes avant de modifier un cas.
Rapport : /tmp/cmr-eval-proof/uv.md
```

## Suite unittest complète

```bash
python3 -m unittest discover -s tests
```

Code de sortie observé : **0**.

```text
............................................................................................................................
----------------------------------------------------------------------
Ran 124 tests in 6.640s

OK
```

## Sortie JSON

```bash
python3 eval/run_eval.py --judge --fake-judge --json --report /tmp/cmr-eval-proof/json.md
```

Code de sortie observé : **0**. Extrait structuré de stdout; la sortie complète a été capturée dans `/tmp/cmr-eval-proof/rapport-complet.json`.

```json
{
  "passed": true,
  "exit_code": 0,
  "judge_name": "FakeJudge",
  "threshold": 0.85,
  "summary": {
    "total": 104,
    "passed": 104,
    "failed": 0,
    "skipped": 0,
    "success_rate": 1.0,
    "judge": {
      "count": 104,
      "mean_score": 1.0,
      "success_rate": 1.0,
      "errors": 0
    }
  },
  "drift": {
    "status": "SAUTÉ",
    "reason": "Aucune liste live ou capture models.list fournie.",
    "unregistered": [],
    "missing": []
  }
}
```

## Artefacts et limites

`eval/report.md` est le fichier écrit par la commande FakeJudge ci-dessus, avec 104/104 cas conformes et un score moyen de 1,000. Les rapports des essais de dérive restent dans `/tmp`; ils n’écrasent pas ce rapport livré. Les deux registres de modèles futurs sont temporaires et leurs prix sont fictifs. Le contrôle de dérive est SAUTÉ lors du passage hors ligne, puis vérifié avec les trois captures simulées.

Empreintes des registres livrés, restés identiques à HEAD :

| Fichier | SHA-256 |
| --- | --- |
| models.yaml | `fbd80816f597b457b0dfea8a5497c6c6cd7caea05c450cf5cd28ab9f8146e412` |
| models.json | `eeb7f1609d1b339c91bf49f077225185e5a86e4fe6ba10329f791c54477c482d` |

Aucun commit ni push effectué.
