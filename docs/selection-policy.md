# Politique de sélection

Le fournisseur d'origine est appelé `family` dans ce dépôt : `anthropic`, `openai`, `google`, `xai`, `microsoft`, `moonshot_ai`, ou tout autre `provider` ajouté aux tables officielles. Les catégories `economy`, `standard`, `premium`, `frontier` sont une convention locale, distincte des paliers de tarification GitHub.

## Ordre de décision

1. Garder les modèles au support CLI documenté, non retirés et disponibles. Une valeur `available: null` signifie « compte non vérifié »; elle est admissible seulement faute de constat contraire. Un `--available` fourni devient le constat courant et remplace celui sauvegardé dans le registre.
2. Exiger GA sans aperçu. `--allow-preview` permet un aperçu; une politique `disabled` ou `unconfigured`, un type non conversationnel ou un `model_picker_enabled: false` reste bloquant. Le nom officiel contenant `preview` suffit à exclure un modèle, même si la table annonce GA.
3. Pour `e2e-validator` et `reviewer`, résoudre la famille du dev, puis enlever **toute** cette famille. Un autre Claude ne suffit pas si le dev utilise Claude. La famille vient du `provider` officiel; le `vendor` de l'API peut nommer un hébergeur différent.
4. Appliquer le plafond de `cost_index`, s'il y en a un. La comparaison utilise `Decimal`, sans tolérance qui permettrait de dépasser le budget. L'égalité exacte au plafond est permise.
5. Retenir le meilleur niveau inférieur ou égal à la préférence. Dans ce niveau, choisir le coût le plus bas; en cas d'égalité, trier par ID pour rendre le résultat reproductible.
6. Si le niveau souhaité manque, descendre au meilleur niveau restant. S'il ne reste **aucun** niveau inférieur ou égal, relâcher cette préférence et choisir le plus petit niveau supérieur disponible, puis le moins cher. La sortie porte alors `fallback: relaxed_level` et explique le choix.

**Les filtres de budget et de famille ne sont jamais relâchés**, même au dernier repli. Le support CLI, les retraits, les interdictions du catalogue et le refus des aperçus ne le sont pas non plus.

Une famille manquante, inconnue ou contradictoire pour les deux rôles indépendants donne le code 3. `--dev-model` doit correspondre à un ID ou à un alias connu. Pour un modèle externe, `--dev-family` explicite peut fournir son fournisseur, à condition qu'il existe dans le registre. Si les deux options sont connues et se contredisent, la sélection échoue.

## Niveaux et préférences

Le niveau vient d'un **score de capacité fondé sur les métadonnées GitHub synchronisées, pas sur des benchmarks**. Le prix, le `cost_index` et les multiplicateurs annuels n'entrent jamais dans ce score. Une baisse de prix seule ne change donc aucun niveau. Le prix sert au filtre de budget, puis au départage dans le niveau retenu.

`capability_score()` et `assign_model_tiers()` dans `registry_lib.py` servent à tous les modèles à chaque sync, y compris aux nouveaux. Les poids sont définis dans `CAPABILITY_POLICY` et copiés sous `policy` dans le registre pour rendre la décision vérifiable; modifier cette copie ne configure pas le calcul. Le registre conserve les textes sous `github_comparison`, les indices de contexte sous `github_context`, le score et ses composantes sous `capability`, puis l'origine du niveau final sous `tier_source`.

| Signal GitHub | Points |
| --- | ---: |
| Catégorie `Lightweight` / `Versatile` / `Powerful` | Base de 10 / 35 / 65 |
| `deep reasoning` ou `sophisticated reasoning` dans `task_area` ou `excels_at` | +18 |
| Sinon, `complex` dans ces mêmes textes | +10 |
| `long-horizon` ou `long-running`, avec trait d'union ou espace | +12 |
| `multistep`, `multi-step`, vérification, `validation`, `confirmation` ou `tests edge cases` en anglais | +6 |
| `fast`, `faster`, `quick`, `simple`, `repetitive` ou `lightweight` dans ces textes | −8 |
| Fenêtre explicite ou limite du tarif Default d'au moins 200 000 jetons | +2 |
| Présence d'un palier `Long context` | +2 |
| Statut officiel `GA` / autre statut | +2 / −2 |
| Chaque génération suivante présente dans la même lignée | +4, maximum +12 |

Chaque ligne de bonus/malus est appliquée une seule fois, même si le mot se répète dans les deux textes. Les indices « raisonnement profond » et « complexité » sont exclusifs. Les autres composantes s'additionnent; le total est borné à zéro. Les poids sont des hypothèses locales : les textes éditoriaux indiquent une orientation, la génération présume une progression, le contexte apporte un petit indice et GA un indice de maturité. Ils ne prouvent aucune supériorité mesurée.

Les champs de fenêtre reconnus sont `context_window`, `context_window_tokens` et `max_context_tokens` lorsqu'ils sont présents dans les tables, avec nombre de jetons ou suffixe K/M. Les tables livrées fournissent surtout des **seuils tarifaires** (`≤ 272K`, par exemple) et des paliers long contexte. Ces seuils sont conservés comme tels; ils ne sont pas présentés comme la fenêtre maximale du modèle. Aucune valeur de prix n'est lue pour cette composante.

| Score brut | Niveau calculé |
| --- | --- |
| 0 à 29 | `economy` |
| 30 à 59 | `standard` |
| 60 à 84 | `premium` |
| 85 ou plus | `frontier` |

La lignée combine le fournisseur `family` et la gamme extraite du nom officiel : Claude Opus, Sonnet, Haiku et Fable sont distincts; GPT Sol, Terra, Luna, Astra et Codex aussi. Les formats Gemini, Grok, MAI-Code et Kimi K sont reconnus. Les versions sont comparées comme des suites d'entiers : `4.8 < 5 < 5.5 < 5.10`, `5.0 = 5`, et `GPT-5.6 Sol < GPT-6 Sol`. Les mentions `fast`, `fast mode` et `preview` du nom ne créent aucune nouvelle génération. Le bonus compte les versions distinctes présentes, de la plus ancienne à la plus récente, avec les archives; il ne compare pas les numéros de gammes différentes.

**Après le scoring, un passage de monotonie impose le même niveau aux variantes d'une même version et un niveau jamais inférieur pour une version plus récente de la même lignée.** Le plancher est le meilleur niveau final des générations précédentes. Le score brut et `capability.tier_scored` restent visibles; `tier_source: monotonicity` explique une hausse. Le prix plus bas d'une nouvelle génération ne peut jamais causer une rétrogradation.

Exemples du registre livré : Opus 4.8 obtient `65 + 18 + 2 = 85`; Opus 5.5 obtient `65 + 12 + 6 + 2 + 8 = 93`. Les deux sont `frontier` sans override; entre eux, le sélecteur préfère Opus 5.5 à **82 crédits** plutôt qu'Opus 4.8 à **105 crédits**. GPT-6 Sol a un score brut de 81, puis monte à `frontier` par monotonie avec GPT-5.6 Sol. La [preuve complète](tiering-proof.md) montre les 26 modèles avant/après.

Si le comparatif est absent **ou** la lignée ne peut pas être extraite, le score utilise seulement la base de catégorie : `economy`, `standard` ou `premium`. Le modèle porte `tier_provisoire: true` et une note « à valider ». La monotonie peut encore relever ce niveau prudent lorsqu'une génération antérieure reconnue impose un plancher. Un prix élevé ne fournit jamais le signal manquant. Une catégorie inconnue arrête la sync pour faire réviser la politique.

| Rôle | Préférence par défaut |
| --- | --- |
| `doc` | `economy` |
| `test` | `standard` |
| `dev`, `e2e-validator`, `reviewer` | `premium` |
| `planner` | `frontier` |

`--level`, `--max-cost` et `--budget-profile` sont exclusifs. `--max-cost` garde la préférence propre au rôle et impose un plafond. Les profils livrés définissent à la fois une préférence et un plafond par tâche de référence :

| Profil | Niveau | Plafond en crédits |
| --- | --- | ---: |
| `economy` | `economy` | 5 |
| `standard` | `standard` | 35 |
| `premium` | `premium` | 100 |
| `frontier` | `frontier` | 250 |

Les profils, les préférences et les seuils de score sont des choix de ce dépôt, pas des offres GitHub. Un profil peut être ajouté sous `budget_profiles`, par exemple `petite-mission: {level: standard, max_cost: 25}`. Sans plafond explicite, la sélection n'impose pas de budget financier.

## Formule et portée du budget

La tâche de référence totalise 200 000 jetons d'entrée **sur plusieurs appels**, 50 % lus d'un cache déjà créé, et 20 000 jetons de sortie. Chaque appel est supposé rester dans le tarif `Default` du modèle. Le total d'entrée d'une mission n'est pas assimilé à la taille d'un seul prompt : c'est particulièrement pertinent pour Haiku 5.5, dont le seuil Default est de 100 000 jetons par entrée.

Pour les prix `I`, `C`, `O` en USD par million de jetons :

```text
coût_USD = 0,1 × I + 0,1 × C + 0,02 × O
cost_index = coût_USD / 0,01
```

Exemple tiré du YAML officiel pour GPT-5.3-Codex : `I = 1,75`, `C = 0,175`, `O = 14`. Résultat : `0,4725 USD`, soit **47,25 crédits**. Les [tables officielles](https://raw.githubusercontent.com/github/docs/main/data/tables/copilot/models-and-pricing.yml) constituent la source des prix; aucune valeur manquante n'est remplacée par zéro.

Le scénario suppose zéro écriture de cache. Le prix `cache_write` officiel est conservé, avec `null` quand il n'est pas fourni ou ne s'applique pas. Ce `null` n'est pas une affirmation de gratuité. Le coût des écritures, les tarifs long contexte, les variations de volume, les changements de promotion et les frais autres que ces jetons sortent de l'estimation. Pour une facture réelle, suivre la consommation et configurer le plafond de session du CLI.

Les tarifs courants de Gemini sont promotionnels : la documentation annonce ceux de Gemini 3.8 Flash jusqu'au 31 décembre 2026 et ceux de Gemini 4 Argon jusqu'au 1er décembre 2026. Aucun prix futur n'est inventé. Synchroniser avant de réutiliser ces estimations après ces dates. Voir les [notes tarifaires officielles](https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing#footnotes).

`legacy_multiplier` conserve seulement les valeurs des anciens plans annuels Pro/Pro+ provenant d'[annual-subscriber-model-multipliers.yml](https://raw.githubusercontent.com/github/docs/main/data/tables/copilot/annual-subscriber-model-multipliers.yml). Il ne multiplie ni les prix USD ni le `cost_index`.

## Disponibilité et identifiants

`--available` accepte un fichier JSON ou texte, `@chemin`, ou des ID séparés par virgules/espaces. Une liste vide signifie qu'aucun modèle n'est disponible. Les ID inconnus sans prix officiel correspondant sont signalés et exclus.

Le rapprochement essaie l'ID canonique, puis les alias, puis le nom affiché normalisé. Les notes Markdown et les espaces sont normalisés; les variantes de modèle ne sont pas fusionnées. Un nom correspondant à plusieurs ID est ambigu et exclu jusqu'à l'ajout d'un ID/alias manuel. Un alias ne peut pas contourner une interdiction explicite de l'ID canonique.

Une correspondance importée peut corriger un slug supposé. L'ancien ID est conservé comme alias; `id_verified: true` signifie alors « ID observé dans le catalogue fourni ». Ça ne prouve pas qu'une inférence a réussi. Le catalogue intégré hors ligne est refusé comme disponibilité, puisqu'il peut contenir des modèles sans droit d'accès ou sans support CLI documenté.

La livraison garde `available: null` partout. Les 25 ID marqués vérifiés le sont par `models.getBuiltInCatalog` du CLI 1.0.105, avec une preuve sous `id_source`. Le seul ID encore supposé est `gpt-6.1-terra`.

## Synchronisation et champs manuels

La sync télécharge les quatre tables officielles avant toute écriture. Elle ne retient qu'un tarif `Default` par modèle; une entrée sans champ `tier` est traitée comme le tarif unique Default. Elle retire les notes Markdown pour croiser les noms, puis garde seulement `cli: true`. Au premier passage, elle signale 26 nouveaux modèles et trois exclusions; aux passages suivants, elle signale seulement les nouveaux changements.

Les modèles retirés des tarifs ou du support CLI restent archivés avec `retired: true`, `cli: false`, `available: false` et une date de retrait. Leur ancien prix reste visible pour l'historique et ne participe jamais à la sélection. Leurs métadonnées de capacité conservées participent encore au plancher de leur lignée, sans les rendre admissibles.

Les champs suivants sont conservés : `id`, `id_verified`, `id_source`, `aliases`, `notes`, les autres champs personnels, `tier_override`, `manual_capabilities`, `role_defaults` et `budget_profiles`. Utiliser **`tier_override`** pour personnaliser un niveau et **`manual_capabilities`** pour ajouter des tags. Les champs dérivés `tier` et `capabilities` sont recalculés à chaque sync. Les tarifs, le fournisseur officiel, le statut et le support CLI appartiennent aux sources et sont actualisés.

`tier_override` accepte `economy`, `standard`, `premium` ou `frontier` et prévaut sur le score automatique après resynchronisation. Par exemple, ajouter `tier_override: premium` à une entrée dans `models.yaml`, puis exécuter `python3 scripts/sync_registry.py --upstream-dir upstream`. Ne pas modifier seulement `tier`, qui sera recalculé. Un override s'applique aussi aux variantes de cette même version pour conserver leur capacité commune. Deux overrides incompatibles sur ces variantes, ou un override plus bas que le plancher d'une génération antérieure, font échouer la sync **avant toute écriture** avec une erreur de monotonie. Ajuster les overrides de la lignée de façon cohérente; le calcul n'écrase jamais silencieusement un override.

Le caractère provisoire dépend des signaux, pas de l'âge de l'entrée. Il est recalculé à chaque sync : il reste si les données manquent, puis disparaît lorsqu'un comparatif et une lignée reconnus deviennent disponibles, ou avec un override explicite sur le modèle. Un ancien `tier` seul ne confirme pas sa capacité. Les choix acceptent un niveau provisoire en l'annonçant dans `reason` et `warnings`; voir le [guide du routeur](router.md#nouveaux-modèles-et-niveau-provisoire).

`capabilities` contient des tags de tâches en français dérivés de `model-comparison.yml`; ce ne sont pas des limites ou des fonctions testées. La structure technique importée du CLI est conservée séparément sous `runtime`, y compris ses données de facturation. Elle ne remplace jamais les tarifs officiels du calcul.

Sans `--from-cli-models`, le dernier constat de disponibilité importé reste en place, avec sa date; il n'est pas rafraîchi par un téléchargement de documentation. Pour un lancement, fournir un catalogue récent à `--available`.

La sync génère `models.json` avec l'empreinte du YAML. Si PyYAML est absent, le sélecteur vérifie cette empreinte avant d'utiliser le secours; un YAML modifié exige donc une nouvelle sync. On peut aussi passer explicitement `--registry chemin/models.json`. La sync elle-même exige PyYAML.

## Sorties et erreurs

| Code | Sens |
| ---: | --- |
| 0 | Sélection réussie, sync réussie ou catalogue obtenu. |
| 1 | Configuration/fichier invalide, sync impossible, ou aucun candidat pour un rôle ordinaire. |
| 2 | Aucun candidat admissible dans le plafond de référence; également erreur de syntaxe standard d'`argparse`. |
| 3 | Famille indépendante impossible à établir ou à obtenir pour e2e/reviewer. |
| 4 | Découverte Copilot impossible : CLI absent, authentification, accès, catalogue vide ou protocole. |

Si aucune autre famille n'est admissible **avant** le filtre de coût, la sortie est 3. S'il existe une autre famille, mais aucun candidat sous le plafond, elle est 2. La sortie JSON d'échec de sélection contient `error` et `exit_code`; elle ne contient aucune commande à lancer.

En cas de succès, le JSON contient `id`, `family`, `tier`, `cost_index`, `reason`, `fallback`, `warnings`, `herdr_command` et `herdr_argv`. Le tableau `herdr_argv` permet d'éviter l'interprétation par un shell. Le sélecteur affiche une commande d'exemple et ne lance aucun processus Herdr.
