# Preuve du correctif de tiering

Exécutions locales réelles; synchronisation du registre à `2026-10-31T01:56:51.433693+00:00` (UTC), depuis les quatre tables livrées dans `upstream/`. Aucun benchmark, compte Copilot, appel d'inférence ni lancement Herdr n'est utilisé. Les listes `--available` ci-dessous sont des données de simulation explicites; elles ne prouvent aucun droit d'accès au compte.

## Même commande avant et après

```bash
python3 scripts/route.py --role dev --story "refactor paiement" --diff-stats "14 files changed, 620 insertions(+), 210 deletions(-)"
```

Avant : copie intégrale de `/workspace/before.txt`. Avant de modifier le code et le registre, cette commande a aussi été rejouée : sortie et code identiques à cette copie, octet pour octet.

```text
critique → frontier : claude-opus-4.8 (anthropic)
Portée mesurée : 14 fichier(s), 830 ligne(s) modifiée(s) → complexe. Mots-clés : paiement → critique. Mots-clés : refactor → complexe. Signal le plus exigeant retenu : critique. Classe critique → préférence frontier. Rôle dev, niveau souhaité frontier; niveau retenu frontier, puis coût minimal dans ce niveau (égalité tranchée par ID). Coût estimé : 105 crédits par tâche de référence.
À vérifier : Disponibilité du compte non vérifiée; fournir --available après connexion au poste de travail.
herdr agent start dev --kind copilot -- --model claude-opus-4.8
code 0
```

Après : même commande et mêmes arguments, exécutés avec le nouveau registre. Le seuil complexe reste 10 fichiers ou 500 lignes; le seuil critique sur un domaine sensible est 20 fichiers ou 1 000 lignes, ou un vrai signal de risque. La mention « paiement » et les 14 fichiers/830 lignes ne suffisent donc plus pour critique.

```text
complexe → premium : grok-4.6 (xai)
Portée mesurée : 14 fichier(s), 830 ligne(s) modifiée(s) → complexe. Domaine sensible (paiement) sans risque ni ampleur critique; mention seule insuffisante. Mots-clés : refactor → complexe. Signal le plus exigeant retenu : complexe. Classe complexe → préférence premium. Rôle dev, niveau souhaité premium; niveau retenu premium, puis coût minimal dans ce niveau (égalité tranchée par ID). Coût estimé : 37 crédits par tâche de référence.
À vérifier : Disponibilité du compte non vérifiée; fournir --available après connexion au poste de travail.
herdr agent start dev --kind copilot -- --model grok-4.6
code 0
```

## Signal de sécurité réellement critique

```bash
python3 scripts/route.py --role dev --story "corriger une faille d'injection SQL dans l'auth"
```

```text
critique → frontier : gpt-6-sol (openai)
Risque de sécurité explicite : faille, injection → critique. Signal le plus exigeant retenu : critique. Classe critique → préférence frontier. Rôle dev, niveau souhaité frontier; niveau retenu frontier, puis coût minimal dans ce niveau (égalité tranchée par ID). Coût estimé : 42 crédits par tâche de référence.
À vérifier : Disponibilité du compte non vérifiée; fournir --available après connexion au poste de travail.
herdr agent start dev --kind copilot -- --model gpt-6-sol
code 0
```

La faille et l'injection suffisent sans statistiques. GPT-6 Sol est ici le frontier admissible le moins cher du registre complet (42 crédits). Cette sélection respecte le niveau, puis le prix.

## Opus plus récent, plus capable selon le score et moins cher

```bash
python3 scripts/select_model.py --role dev --level frontier --available claude-opus-4.8,claude-opus-5.5
```

```text
claude-opus-5.5
Rôle dev, niveau souhaité frontier; niveau retenu frontier, puis coût minimal dans ce niveau (égalité tranchée par ID). Coût estimé : 82 crédits par tâche de référence.
herdr agent start dev --kind copilot --pane '<pane>' -- --model claude-opus-5.5
code 0
```

Opus 4.8 : score 85, frontier, 105 crédits. Opus 5.5 : score 93, frontier, 82 crédits. Aucun des deux ne porte de `tier_override`. Le score utilise les métadonnées GitHub, pas des résultats de benchmarks : il ne prétend pas mesurer la qualité réelle. Le même niveau rend maintenant possible le départage par prix en faveur de 5.5.

## Budget : égalité permise, dépassement refusé

```bash
python3 scripts/route.py --role dev --story "corriger une faille d'injection SQL dans l'auth" --available claude-opus-4.8,claude-opus-5.5 --max-cost 82
```

```text
critique → frontier : claude-opus-5.5 (anthropic)
Risque de sécurité explicite : faille, injection → critique. Signal le plus exigeant retenu : critique. Classe critique → préférence frontier. Rôle dev, niveau souhaité frontier; niveau retenu frontier, puis coût minimal dans ce niveau (égalité tranchée par ID). Coût estimé : 82 crédits par tâche de référence. Plafond respecté : 82 crédits.
herdr agent start dev --kind copilot -- --model claude-opus-5.5
code 0
```

```bash
python3 scripts/route.py --role dev --story "corriger une faille d'injection SQL dans l'auth" --available claude-opus-4.8,claude-opus-5.5 --max-cost 81.999 --json
```

```text
{
  "error": "Aucun modèle admissible ne respecte le plafond de 81.999 crédits par tâche de référence. Le budget ne peut pas être dépassé.",
  "exit_code": 2
}
code 2
```

Le code 2 interdit le lancement; aucune commande Herdr n'est renvoyée. Les tests vérifient aussi le code réel du sélecteur direct, les profils, les replis et l'indépendance des fournisseurs.

## Synchronisation et intégrité

```bash
python3 scripts/sync_registry.py --upstream-dir upstream --json
```

```text
{
  "new": [],
  "removed": [],
  "provisional": [],
  "excluded_non_cli": [
    "GPT-5.4 nano",
    "GPT-6.1 Sol",
    "Claude Sonnet 4"
  ],
  "unmatched_cli": [],
  "ambiguous_cli": [],
  "id_changes": [],
  "models": 26,
  "mode": "local",
  "checked_at": "2026-10-31T01:56:51.433693+00:00"
}
code 0
```

Comparaison réelle avec les copies des deux registres prises avant modification :

```text
26 modèles; champs manuels, préférences et profils conservés; YAML/JSON et empreinte concordants; sync répétée identique; aucun tier_override.
```

Les ID, preuves d'ID, alias, constats de disponibilité, champs manuels présents, préférences par rôle et profils sont conservés. Le JSON contient la bonne empreinte SHA-256 du YAML. La répétition du calcul sur les mêmes tables donne exactement le même registre, sans ajout/retrait ni niveau provisoire pour les 26 modèles dont les signaux sont suffisants. Les quatre fichiers upstream n'ont pas été modifiés.

## Tiers des 26 modèles avant et après

Prix inchangés, en crédits par tâche de référence. Le score est brut, avant le passage de monotonie; la colonne origine explique le niveau final. Les variantes fast partagent le niveau de leur version.

| ID | Avant | Score | Après | Origine | Coût |
| --- | --- | ---: | --- | --- | ---: |
| `claude-fable-5` | frontier | 85 | frontier | score | 210 |
| `claude-fable-5.1` | frontier | 93 | frontier | score | 202.5 |
| `claude-haiku-4.5` | standard | 29 | economy | score | 21 |
| `claude-haiku-5.5` | economy | 10 | economy | score | 2.1 |
| `claude-opus-4.8` | frontier | 85 | frontier | score | 105 |
| `claude-opus-4.8-fast` | frontier | 85 | frontier | score | 210 |
| `claude-opus-5` | frontier | 89 | frontier | score | 105 |
| `claude-opus-5.5` | premium | 93 | frontier | score | 82 |
| `claude-sonnet-4.6` | standard | 55 | standard | score | 63 |
| `claude-sonnet-5` | standard | 59 | standard | score | 42 |
| `claude-sonnet-5.5` | standard | 45 | standard | score | 41 |
| `gemini-3.8-flash` | standard | 29 | economy | score | 15.75 |
| `gemini-4-argon` | premium | 83 | premium | score | 41 |
| `mai-code-1.1-flash` | economy | 4 | economy | score | 4.6 |
| `kimi-k3` | premium | 73 | premium | score | 63 |
| `gpt-5.3-codex` | premium | 67 | premium | score | 47.25 |
| `gpt-5.6-luna` | economy | 8 | economy | score | 4.6 |
| `gpt-5.6-sol` | premium | 101 | frontier | score | 84 |
| `gpt-5.6-terra` | standard | 41 | standard | score | 46 |
| `gpt-6-astra` | frontier | 89 | frontier | score | 210 |
| `gpt-6-luna` | economy | 12 | economy | score | 2.1 |
| `gpt-6-sol` | premium | 81 | frontier | monotonicity | 42 |
| `gpt-6.1-terra` | standard | 45 | standard | score | 20.5 |
| `grok-4.5` | standard | 59 | standard | score | 37 |
| `grok-4.6` | standard | 63 | premium | score | 37 |
| `grok-4.7` | standard | 73 | premium | score | 37 |


GPT-6 Sol aurait un niveau premium sur son seul score brut de 81; le frontier de GPT-5.6 Sol impose le plancher frontier par monotonie. Le test sur tout le registre compare toutes les versions et toutes les variantes de chaque lignée. Les [poids et hypothèses](selection-policy.md#niveaux-et-préférences) décrivent les autres changements de niveau.

## Nouveaux modèles et réglages manuels

Les tests injectent un GPT-6.2 Sol Powerful à 2,1 crédits avec un comparatif de raisonnement/long horizon : il atteint frontier sans override et devient le choix du planner. Un GPT-7 Luna Lightweight à 2 178 crédits reste economy. La variation de tous les prix sur les 26 modèles ne change aucun score ni aucun niveau.

Un Powerful sans comparatif, ou avec un comparatif mais une lignée inconnue, reste premium provisoire sur la seule catégorie. La sortie annonce « à valider ». Un GPT-7 Sol sans comparatif reste provisoire mais reçoit le plancher frontier de sa lignée. Les tests couvrent la persistance du marqueur, l'override prioritaire, sa conservation, les variantes fast, le refus des overrides invalides ou non monotones, le contexte et le statut.

## Suite complète

Avant correction : 76 tests réussis. Les anciens tests qui exigeaient le prix pour frontier ou un mot de domaine isolé pour critique ont été adaptés en gardant leurs vérifications des catégories, accents, plafonds et replis. Après correction :

```bash
python3 -m unittest discover -s tests -v
```

```text
test_ancien_protocole_et_repli_ping (test_listing.ListingTests.test_ancien_protocole_et_repli_ping) ... ok
test_catalogue_integre_ne_demande_pas_auth_ou_api (test_listing.ListingTests.test_catalogue_integre_ne_demande_pas_auth_ou_api) ... ok
test_compte_sans_modeles_message_licence (test_listing.ListingTests.test_compte_sans_modeles_message_licence) ... ok
test_delai_et_protocole_futur (test_listing.ListingTests.test_delai_et_protocole_futur) ... ok
test_non_authentifie_ne_demande_pas_la_liste (test_listing.ListingTests.test_non_authentifie_ne_demande_pas_la_liste) ... ok
test_rpc_et_notifications (test_listing.ListingTests.test_rpc_et_notifications) ... ok
test_diff_singulier_suppressions_et_comptes_differents (test_router.HeuristicTests.test_diff_singulier_suppressions_et_comptes_differents) ... ok
test_domaine_plus_risque_ou_type_bug (test_router.HeuristicTests.test_domaine_plus_risque_ou_type_bug) ... ok
test_domaines_sensibles_seuls_insuffisants_et_accents (test_router.HeuristicTests.test_domaines_sensibles_seuls_insuffisants_et_accents) ... ok
test_quatre_niveaux (test_router.HeuristicTests.test_quatre_niveaux) ... ok
test_refactor_paiement_du_brief_reste_complexe (test_router.HeuristicTests.test_refactor_paiement_du_brief_reste_complexe) ... ok
test_seuils_critiques_combines_au_domaine (test_router.HeuristicTests.test_seuils_critiques_combines_au_domaine) ... ok
test_seuils_de_portee (test_router.HeuristicTests.test_seuils_de_portee) ... ok
test_signaux_invalides (test_router.HeuristicTests.test_signaux_invalides) ... ok
test_types_et_priorite (test_router.HeuristicTests.test_types_et_priorite) ... ok
test_vrais_signaux_de_securite_critiques_seuls (test_router.HeuristicTests.test_vrais_signaux_de_securite_critiques_seuls) ... ok
test_refresh_absent_echec_et_succes_catalogue (test_router.RefreshTests.test_refresh_absent_echec_et_succes_catalogue) ... ok
test_available_fichier_et_liste (test_router.RouterCliTests.test_available_fichier_et_liste) ... ok
test_codes_budget_et_famille (test_router.RouterCliTests.test_codes_budget_et_famille) ... ok
test_live_simule_et_echec_code_4 (test_router.RouterCliTests.test_live_simule_et_echec_code_4) ... ok
test_sans_pyyaml_et_depuis_autre_dossier (test_router.RouterCliTests.test_sans_pyyaml_et_depuis_autre_dossier) ... ok
test_story_et_diff_en_fichiers (test_router.RouterCliTests.test_story_et_diff_en_fichiers) ... ok
test_plusieurs_requetes_erreurs_et_notifications (test_router.RouterServerTests.test_plusieurs_requetes_erreurs_et_notifications) ... ok
test_registre_charge_une_fois_reload_et_echec_atomique (test_router.RouterServerTests.test_registre_charge_une_fois_reload_et_echec_atomique) ... ok
test_requetes_invalides_ne_ferment_pas_le_serveur (test_router.RouterServerTests.test_requetes_invalides_ne_ferment_pas_le_serveur) ... ok
test_adaptateur_choisit_economy_et_passe_des_arguments (test_router.RouterTests.test_adaptateur_choisit_economy_et_passe_des_arguments) ... ok
test_adaptateur_refus_delai_cli_absent_et_aucun_economy (test_router.RouterTests.test_adaptateur_refus_delai_cli_absent_et_aucun_economy) ... ok
test_classe_et_tier_distincts_avec_budget (test_router.RouterTests.test_classe_et_tier_distincts_avec_budget) ... ok
test_doc_plafonnee_meme_en_repli (test_router.RouterTests.test_doc_plafonnee_meme_en_repli) ... ok
test_e2e_minimum_et_exception_triviale (test_router.RouterTests.test_e2e_minimum_et_exception_triviale) ... ok
test_fake_llm_et_heuristique_sans_client (test_router.RouterTests.test_fake_llm_et_heuristique_sans_client) ... ok
test_famille_et_budget_non_relaches (test_router.RouterTests.test_famille_et_budget_non_relaches) ... ok
test_herdr_cmd_quoting_et_options (test_router.RouterTests.test_herdr_cmd_quoting_et_options) ... ok
test_llm_echec_et_parsing_strict_redonnent_heuristique (test_router.RouterTests.test_llm_echec_et_parsing_strict_redonnent_heuristique) ... ok
test_profil_impose_le_budget_et_garde_la_classe (test_router.RouterTests.test_profil_impose_le_budget_et_garde_la_classe) ... ok
test_tier_provisoire_accepte_et_signale (test_router.RouterTests.test_tier_provisoire_accepte_et_signale) ... ok
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
test_niveau_connu_non_marque_provisoire (test_sync.SyncTests.test_niveau_connu_non_marque_provisoire) ... ok
test_nouveau_modele_provisoire_persistant_et_validation_manuelle (test_sync.SyncTests.test_nouveau_modele_provisoire_persistant_et_validation_manuelle) ... ok
test_nouveaux_et_retraits_conserves_comme_archives (test_sync.SyncTests.test_nouveaux_et_retraits_conserves_comme_archives) ... ok
test_preview_malgre_ga (test_sync.SyncTests.test_preview_malgre_ga) ... ok
test_prix_manquant_ne_devient_pas_zero (test_sync.SyncTests.test_prix_manquant_ne_devient_pas_zero) ... ok
test_sync_locale_cli_et_parite_yaml_json (test_sync.SyncTests.test_sync_locale_cli_et_parite_yaml_json) ... ok
test_tiers_deduits_des_metadonnees_suffisantes (test_sync.SyncTests.test_tiers_deduits_des_metadonnees_suffisantes) ... ok
test_vrais_prix_default_et_calculs (test_sync.SyncTests.test_vrais_prix_default_et_calculs) ... ok
test_yaml_officiel_invalide_signale (test_sync.SyncTests.test_yaml_officiel_invalide_signale) ... ok
test_budget_opus_exact_et_code_2_reel (test_tiering.TieringTests.test_budget_opus_exact_et_code_2_reel) ... ok
test_composantes_contexte_et_statut_sans_prix (test_tiering.TieringTests.test_composantes_contexte_et_statut_sans_prix) ... ok
test_fenetre_explicite_lue_dans_les_metadonnees (test_tiering.TieringTests.test_fenetre_explicite_lue_dans_les_metadonnees) ... ok
test_meilleur_tier_admissible_puis_prix_sur_tout_le_registre (test_tiering.TieringTests.test_meilleur_tier_admissible_puis_prix_sur_tout_le_registre) ... ok
test_monotonie_apres_un_comparatif_plus_faible_ou_absent (test_tiering.TieringTests.test_monotonie_apres_un_comparatif_plus_faible_ou_absent) ... ok
test_monotonie_sur_tout_le_registre_livre_et_regenere (test_tiering.TieringTests.test_monotonie_sur_tout_le_registre_livre_et_regenere) ... ok
test_nouvelle_generation_powerful_bon_marche_et_lightweight_cher (test_tiering.TieringTests.test_nouvelle_generation_powerful_bon_marche_et_lightweight_cher) ... ok
test_opus_plus_recent_et_moins_cher_prefere_en_frontier (test_tiering.TieringTests.test_opus_plus_recent_et_moins_cher_prefere_en_frontier) ... ok
test_override_prioritaire_sur_score_et_conserve_aux_syncs (test_tiering.TieringTests.test_override_prioritaire_sur_score_et_conserve_aux_syncs) ... ok
test_override_variante_fast_applique_a_la_meme_version (test_tiering.TieringTests.test_override_variante_fast_applique_a_la_meme_version) ... ok
test_overrides_invalides_et_non_monotones_refuses (test_tiering.TieringTests.test_overrides_invalides_et_non_monotones_refuses) ... ok
test_prix_change_sans_changer_scores_ni_tiers (test_tiering.TieringTests.test_prix_change_sans_changer_scores_ni_tiers) ... ok
test_signaux_insuffisants_categorie_seule_et_avertissement (test_tiering.TieringTests.test_signaux_insuffisants_categorie_seule_et_avertissement) ... ok
test_versions_numeriques_et_variantes_fast (test_tiering.TieringTests.test_versions_numeriques_et_variantes_fast) ... ok

----------------------------------------------------------------------
Ran 94 tests in 3.915s

OK
code 0
```

Les essais restent locaux et les accès Copilot/Herdr réels restent à valider sur le poste de travail. Aucun commit ni push n'a été effectué.
