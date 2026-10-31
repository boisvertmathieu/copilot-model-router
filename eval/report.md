# Évaluation du routeur

Généré le 2026-10-31T02:20:05.886036+00:00.

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
