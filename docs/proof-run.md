# Preuve d'exécution

Exécuté le 2026-10-30 20:31 (heure locale) sur la box de développement, contre models.yaml tel que commité. **Pas testé contre une org Copilot réelle** (aucune licence Copilot ici).

## 1. Dev economy

```console
$ python3 scripts/select_model.py --role dev --level economy
claude-haiku-5.5
Rôle dev, niveau souhaité economy; niveau retenu economy, puis coût minimal dans ce niveau (égalité tranchée par ID). Coût estimé : 2.1 crédits par tâche de référence.
À vérifier : Disponibilité du compte non vérifiée; fournir --available après connexion au poste de travail.
herdr agent start dev --kind copilot --pane '<pane>' -- --model claude-haiku-5.5
# code de sortie: 0
```

## 2. Dev frontier

```console
$ python3 scripts/select_model.py --role dev --level frontier
claude-opus-4.8
Rôle dev, niveau souhaité frontier; niveau retenu frontier, puis coût minimal dans ce niveau (égalité tranchée par ID). Coût estimé : 105 crédits par tâche de référence.
À vérifier : Disponibilité du compte non vérifiée; fournir --available après connexion au poste de travail.
herdr agent start dev --kind copilot --pane '<pane>' -- --model claude-opus-4.8
# code de sortie: 0
```

## 3. Validateur e2e quand le dev = Sonnet 5.5 (doit changer de famille)

```console
$ python3 scripts/select_model.py --role e2e-validator --dev-model claude-sonnet-5.5
gemini-4-argon
Rôle e2e-validator, niveau souhaité premium; niveau retenu premium, puis coût minimal dans ce niveau (égalité tranchée par ID). Coût estimé : 41 crédits par tâche de référence. Famille google différente de celle du dev (anthropic).
À vérifier : Disponibilité du compte non vérifiée; fournir --available après connexion au poste de travail.
herdr agent start e2e-validator --kind copilot --pane '<pane>' -- --model gemini-4-argon
# code de sortie: 0
```

## 4. Validateur e2e quand le dev = GPT-6 Sol

```console
$ python3 scripts/select_model.py --role e2e-validator --dev-model gpt-6-sol --level premium
gemini-4-argon
Rôle e2e-validator, niveau souhaité premium; niveau retenu premium, puis coût minimal dans ce niveau (égalité tranchée par ID). Coût estimé : 41 crédits par tâche de référence. Famille google différente de celle du dev (openai).
À vérifier : Disponibilité du compte non vérifiée; fournir --available après connexion au poste de travail.
herdr agent start e2e-validator --kind copilot --pane '<pane>' -- --model gemini-4-argon
# code de sortie: 0
```

## 5. Budget serré

Plafond explicite de 5 crédits par tâche de référence (le plafond et --level sont mutuellement exclusifs par conception) :

```console
$ python3 scripts/select_model.py --role dev --max-cost 5
claude-haiku-5.5
Rôle dev, niveau souhaité premium; niveau retenu economy, puis coût minimal dans ce niveau (égalité tranchée par ID). Repli vers un niveau inférieur : aucun candidat admissible au niveau souhaité. Coût estimé : 2.1 crédits par tâche de référence. Plafond respecté : 5 crédits.
À vérifier : Disponibilité du compte non vérifiée; fournir --available après connexion au poste de travail.
herdr agent start dev --kind copilot --pane '<pane>' -- --model claude-haiku-5.5
# code de sortie: 0
```

Profil de budget « economy » défini dans models.yaml :

```console
$ python3 scripts/select_model.py --role dev --budget-profile economy
claude-haiku-5.5
Rôle dev, niveau souhaité economy; niveau retenu economy, puis coût minimal dans ce niveau (égalité tranchée par ID). Coût estimé : 2.1 crédits par tâche de référence. Plafond respecté : 5 crédits.
À vérifier : Disponibilité du compte non vérifiée; fournir --available après connexion au poste de travail.
herdr agent start dev --kind copilot --pane '<pane>' -- --model claude-haiku-5.5
# code de sortie: 0
```

Budget impossible (doit échouer, code 2) :

```console
$ python3 scripts/select_model.py --role dev --max-cost 1
Sélection impossible : Aucun modèle admissible ne respecte le plafond de 1 crédits par tâche de référence. Le budget ne peut pas être dépassé.
# code de sortie: 2
```


## 6. Modèle idéal indisponible dans l'org (fallback)

```console
$ python3 scripts/select_model.py --role dev --level premium --available claude-sonnet-5.5,gpt-6-luna,claude-haiku-5.5
claude-sonnet-5.5
Rôle dev, niveau souhaité premium; niveau retenu standard, puis coût minimal dans ce niveau (égalité tranchée par ID). Repli vers un niveau inférieur : aucun candidat admissible au niveau souhaité. Coût estimé : 41 crédits par tâche de référence.
herdr agent start dev --kind copilot --pane '<pane>' -- --model claude-sonnet-5.5
# code de sortie: 0
```

## 7. Aucune autre famille disponible pour le validateur (doit échouer, code 3)

```console
$ python3 scripts/select_model.py --role e2e-validator --dev-family anthropic --available claude-sonnet-5.5,claude-haiku-5.5
Sélection impossible : Aucun modèle CLI admissible d'une famille différente de anthropic. La contrainte de famille ne peut pas être relâchée.
# code de sortie: 3
```

## 8. Sortie JSON pour l'orchestrateur

```console
$ python3 scripts/select_model.py --role test --level standard --json
{
  "id": "gemini-3.8-flash",
  "display_name": "Gemini 3.8 Flash",
  "family": "google",
  "tier": "standard",
  "requested_level": "standard",
  "role": "test",
  "cost_index": 15.75,
  "max_cost": null,
  "budget_profile": null,
  "dev_family": null,
  "id_verified": true,
  "available": null,
  "reason": "Rôle test, niveau souhaité standard; niveau retenu standard, puis coût minimal dans ce niveau (égalité tranchée par ID). Coût estimé : 15.75 crédits par tâche de référence.",
  "fallback": "none",
  "warnings": [
    "Disponibilité du compte non vérifiée; fournir --available après connexion au poste de travail."
  ],
  "herdr_command": "herdr agent start test --kind copilot --pane '<pane>' -- --model gemini-3.8-flash",
  "herdr_argv": [
    "herdr",
    "agent",
    "start",
    "test",
    "--kind",
    "copilot",
    "--pane",
    "<pane>",
    "--",
    "--model",
    "gemini-3.8-flash"
  ]
}
# code de sortie: 0
```

## 9. Tests unitaires

```console
$ python3 -m unittest discover -s tests -v
test_ancien_protocole_et_repli_ping (test_listing.ListingTests.test_ancien_protocole_et_repli_ping) ... ok
test_catalogue_integre_ne_demande_pas_auth_ou_api (test_listing.ListingTests.test_catalogue_integre_ne_demande_pas_auth_ou_api) ... ok
test_compte_sans_modeles_message_licence (test_listing.ListingTests.test_compte_sans_modeles_message_licence) ... ok
test_delai_et_protocole_futur (test_listing.ListingTests.test_delai_et_protocole_futur) ... ok
test_non_authentifie_ne_demande_pas_la_liste (test_listing.ListingTests.test_non_authentifie_ne_demande_pas_la_liste) ... ok
test_rpc_et_notifications (test_listing.ListingTests.test_rpc_et_notifications) ... ok
test_codes_de_sortie_reels (test_selection.IntegrationSelectionTests.test_codes_de_sortie_reels) ... ok
test_formats_de_disponibilite (test_selection.IntegrationSelectionTests.test_formats_de_disponibilite) ... ok
test_integrite_du_registre_livre (test_selection.IntegrationSelectionTests.test_integrite_du_registre_livre) ... ok
test_json_perime_refuse_sans_pyyaml (test_selection.IntegrationSelectionTests.test_json_perime_refuse_sans_pyyaml) ... ok
test_longue_liste_d_ids_sans_erreur_de_chemin (test_selection.IntegrationSelectionTests.test_longue_liste_d_ids_sans_erreur_de_chemin) ... ok
test_secours_sans_pyyaml (test_selection.IntegrationSelectionTests.test_secours_sans_pyyaml) ... ok
test_yaml_invalide_refuse_sans_traceback (test_selection.IntegrationSelectionTests.test_yaml_invalide_refuse_sans_traceback) ... ok
test_absence_sous_budget_code_2 (test_selection.SelectionTests.test_absence_sous_budget_code_2) ... ok
test_alias_ne_contourne_pas_politique_canonique (test_selection.SelectionTests.test_alias_ne_contourne_pas_politique_canonique) ... ok
test_apercu_et_politiques (test_selection.SelectionTests.test_apercu_et_politiques) ... ok
test_budget_inviolable_sur_grille_de_plafonds (test_selection.SelectionTests.test_budget_inviolable_sur_grille_de_plafonds) ... ok
test_budget_respecte_et_repli_inferieur (test_selection.SelectionTests.test_budget_respecte_et_repli_inferieur) ... ok
test_budgets_invalides_refuses (test_selection.SelectionTests.test_budgets_invalides_refuses) ... ok
test_catalogue_frais_remplace_ancien_constat (test_selection.SelectionTests.test_catalogue_frais_remplace_ancien_constat) ... ok
test_catalogue_refuse_indisponibles_et_non_chat (test_selection.SelectionTests.test_catalogue_refuse_indisponibles_et_non_chat) ... ok
test_cli_ga_et_retraits_obligatoires (test_selection.SelectionTests.test_cli_ga_et_retraits_obligatoires) ... ok
test_dev_inconnu_accepte_famille_explicite_connue (test_selection.SelectionTests.test_dev_inconnu_accepte_famille_explicite_connue) ... ok
test_e2e_et_reviewer_changent_de_famille (test_selection.SelectionTests.test_e2e_et_reviewer_changent_de_famille) ... ok
test_famille_jamais_relachee (test_selection.SelectionTests.test_famille_jamais_relachee) ... ok
test_famille_manquante_inconnue_et_contradictoire (test_selection.SelectionTests.test_famille_manquante_inconnue_et_contradictoire) ... ok
test_id_reel_par_nom_et_famille_dev_resolue (test_selection.SelectionTests.test_id_reel_par_nom_et_famille_dev_resolue) ... ok
test_meilleur_niveau_avant_prix (test_selection.SelectionTests.test_meilleur_niveau_avant_prix) ... ok
test_modele_ideal_indisponible (test_selection.SelectionTests.test_modele_ideal_indisponible) ... ok
test_moins_cher_dans_le_niveau (test_selection.SelectionTests.test_moins_cher_dans_le_niveau) ... ok
test_profils_et_defauts_par_role (test_selection.SelectionTests.test_profils_et_defauts_par_role) ... ok
test_relachement_niveau_seulement (test_selection.SelectionTests.test_relachement_niveau_seulement) ... ok
test_sortie_ne_modifie_pas_registre_et_commande_sans_shell (test_selection.SelectionTests.test_sortie_ne_modifie_pas_registre_et_commande_sans_shell) ... ok
test_vide_et_modele_sans_prix_ne_deviennent_pas_disponibles (test_selection.SelectionTests.test_vide_et_modele_sans_prix_ne_deviennent_pas_disponibles) ... ok
test_catalogues_invalides_et_integres_refuses (test_sync.SyncTests.test_catalogues_invalides_et_integres_refuses) ... ok
test_champs_de_catalogue_invalides_refuses (test_sync.SyncTests.test_champs_de_catalogue_invalides_refuses) ... ok
test_champs_manuels_conserves_prix_actualises (test_sync.SyncTests.test_champs_manuels_conserves_prix_actualises) ... ok
test_import_ambigu_exclu (test_sync.SyncTests.test_import_ambigu_exclu) ... ok
test_import_cli_reel_politique_et_id_corrige (test_sync.SyncTests.test_import_cli_reel_politique_et_id_corrige) ... ok
test_intersection_cli_et_notes_markdown (test_sync.SyncTests.test_intersection_cli_et_notes_markdown) ... ok
test_multiplicateurs_legacy_distincts (test_sync.SyncTests.test_multiplicateurs_legacy_distincts) ... ok
test_nouveaux_et_retraits_conserves_comme_archives (test_sync.SyncTests.test_nouveaux_et_retraits_conserves_comme_archives) ... ok
test_preview_malgre_ga (test_sync.SyncTests.test_preview_malgre_ga) ... ok
test_prix_manquant_ne_devient_pas_zero (test_sync.SyncTests.test_prix_manquant_ne_devient_pas_zero) ... ok
test_sync_locale_cli_et_parite_yaml_json (test_sync.SyncTests.test_sync_locale_cli_et_parite_yaml_json) ... ok
test_vrais_prix_default_et_calculs (test_sync.SyncTests.test_vrais_prix_default_et_calculs) ... ok
test_yaml_officiel_invalide_signale (test_sync.SyncTests.test_yaml_officiel_invalide_signale) ... ok

----------------------------------------------------------------------
Ran 47 tests in 1.422s

OK
```
