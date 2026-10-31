# Routing and selection policy

Use `uv run python scripts/route.py --role ROLE --story TEXT --available FILE --json`.
`--story @FILE` reads UTF-8. Optional inputs are `--story-type bug|feature|refactor|doc|spike`,
`--files N`, `--diff-stats TEXT|FILE|@FILE`, `--pane PANE` (default `1`) and `--name NAME` (defaults to the role).
Roles are `dev`, `test`, `doc`, `e2e-validator`, `reviewer`, `planner`.
The router never launches Herdr. Each invocation reads the registry anew.
Panes must be positive integers. Names match `[A-Za-z0-9._-]{1,64}` and cannot start with a hyphen.
Invalid panes or names return exit 1 with a JSON error.

## Task classification

The default heuristic combines signals and keeps the highest level:

| Signal | Level |
| --- | --- |
| Typo, doc, rename; `doc` story type | `trivial` |
| Ordinary work, no decisive signal | `standard` |
| Refactor, architecture, multiple modules; `refactor`/`spike` story type | `complexe` |
| Explicit vulnerability, CVE or security injection | `critique` |
| Sensitive domain plus production/rollback/bug/data-loss risk, bug story type, or critical scope | `critique` |

Sensitive domains include security, auth, payments, migrations and concurrency. A domain mention alone
is insufficient. Dependency injection alone is a design pattern, not a security risk.
Scope is trivial below 3 files/100 changed lines, standard below 10 files/500 lines, otherwise complex.
Critical scope means at least 20 files or 1,000 changed lines, combined with a sensitive domain.
`--diff-stats` accepts short summaries (`14 files, 620 insertions`), full `git diff --stat` output,
French summaries (`12 fichiers modifiés, 340 insertions`) and singular summaries (`1 file changed`).
Insertions plus deletions give changed lines. When file counts disagree, the larger count wins.
Partial parsing, negative counts clamped to zero and conflicting file counts produce stderr warnings.
Unreadable statistics produce a stderr warning and are ignored.

`--classifier llm` selects an available economy-tier model, then makes exactly one non-interactive
`copilot --model ID -p PROMPT` call with closed stdin and all built-in tools excluded. The shared
classifier/judge helper also denies `shell`, `write`, `read`, `url`, `memory`, and passes
`--no-ask-user --disable-builtin-mcps --no-custom-instructions -s`, following the
[Copilot CLI reference](https://docs.github.com/en/copilot/reference/cli-command-reference).
There are no retries. If no economy model is available, the cheapest available admissible model
classifies the task, with a stderr warning.
`--timeout SECONDS` defaults to 30, must be positive and finite, and kills the entire inference
process group on expiry. The prompt includes the task,
role, budget and compact available model entries (`id`, `family`, `tier`, `cost`). The response must
be one strict JSON object with `level`, a nonempty `reason`, and optionally `preferred_model`.
Unknown fields, duplicate keys, surrounding prose, invalid types and unknown levels are rejected.
A timeout, CLI failure or malformed response triggers a stderr warning,
heuristic classification and `decision_source: "heuristic"`. A successful final selection still exits 0.
A valid response sets `decision_source: "llm"`; Python vets any suggested model before honoring it.

## Hard constraints, then preference

The task levels `trivial`, `standard`, `complexe`, `critique` prefer the model tiers
`economy`, `standard`, `premium`, `frontier`. Doc has a hard maximum of standard;
nontrivial e2e validation has a hard minimum of premium. Reviewer has no extra tier bound.
For both e2e validation and review, pass `--dev-model ID` so Python excludes the dev's entire
provider family. For an unknown external ID, `--dev-family PROVIDER` must identify a family in
the registry. Conflicting model/family inputs fail. Runtime `vendor` is an intermediary, not a provider.

Selection applies these steps:

1. Apply the current catalog, CLI support, retirement, policy and preview constraints. Models must
   have a known reference cost and provider. `--allow-preview` permits previews but never disabled
   policies, hidden picker entries or non-chat models.
2. Apply role bounds, independent provider and budget. `--max-cost` and `--budget-profile` are
   exclusive. Profiles supply their `max_cost`; the task keeps its tier preference.
3. Find candidates in the highest tier at or below the preference. If none is at or below the
   preference, use the lowest eligible higher tier.
4. Replace dominated candidates with admissible newer generations in the same provider and lineage
   whose tier is at least as high and cost at most as large, even above the preferred tier. This
   exception applies only within a lineage: a standard model still beats an unrelated premium
   model at the same price. An old standard model cannot beat its equally cheap premium successor.
5. Honor an LLM suggestion if it passes the hard constraints, substituting its admissible dominant
   successor when present. A suggestion cannot exceed the target tier through an unrelated lineage
   when a model at or below the target is admissible. Otherwise record its rejection in `reasons`
   and use Python's choice.
6. Without a valid suggestion, choose minimum cost from the candidates and their replacements.
   Break equal prices by highest capability score, then latest numeric generation, then ID.
   `fallback` records `lower_tier` or `relaxed_level` where applicable.

Budget, provider independence and role bounds are never relaxed. If the newer model is unavailable,
prohibited, over budget or outside a role bound, it cannot disqualify an otherwise eligible older model.

## Org catalog and synchronization

`--available` accepts a JSON/text file, `@FILE`, an ID list separated by commas/spaces, or `live`.
An empty list permits no model. It replaces the registry's saved availability and runtime policy.
Matching uses canonical ID, aliases, then an unambiguous display name. The returned ID is always
in the supplied catalog; canonical restrictions cannot be bypassed by an alias.
Overriding a saved unavailable status warns `registre périmé, relancer la sync` on stderr.
An ID absent from the registry remains non-admissible and requires sync.
Without `--available`, the saved snapshot applies; `available: null` means unverified and warns.
The bundled registry has unverified account availability. Use a current org catalog for launches.

`uv run python scripts/sync_registry.py --from-cli-models copilot-models.local.json` downloads
four public GitHub documentation tables and imports the org catalog. Org presence overrides the
docs' `cli` support flag. Documented models absent from the org are unavailable. Model listing
uses Copilot's `models.list`; its offline built-in catalog is rejected as proof of account access.
For an offline refresh, add `--upstream-dir upstream`. `scripts/refresh.sh` attempts the account
catalog and then syncs; if discovery fails it warns and refreshes metadata only, retaining
the previous availability snapshot. A failed discovery does not verify current access.

All models receive tiers automatically from the existing metadata score. Category bases are
10/35/65 for Lightweight/Versatile/Powerful; reasoning, task descriptions, context, maturity and
generation add signals. Thresholds are 0/30/60/85. Prices never affect tiers. Numeric versions
are compared within a provider and lineage, with equal tiers for variants and nondecreasing tiers
across generations. `CAPABILITY_POLICY` in `scripts/registry_lib.py` defines the scoring weights.
These are metadata estimates, not benchmark results.

Missing comparison/lineage metadata sets `tier_provisoire: true`, with a warning on selection.
An org-only new generation uses its lineage's category (otherwise a conservative Lightweight base),
then the same scoring and monotonicity rules. Org-only models can supply `cost_index` in reference
credits, or `pricing` with USD/million-token `input`, `cached_input`, `output`. A missing price inherits
the price of the direct predecessor in the same provider and lineage, even if that predecessor is
currently unavailable. The decision sets `prix_suppose: true`, identifies `pricing_predecessor`,
and warns on stderr and in `reasons`. It never skips a generation to find a cheaper price or uses
another lineage. If no predecessor price can be resolved, `pricing_missing` excludes the model and
asks for its price in `models.yaml`. An explicit base-registry price always wins, including over
the local overlay and catalog pricing. A newer generation
that dominates its predecessor is selected automatically, even with a provisional tier.

Sync preserves `id`, aliases, notes, `tier_override`, `manual_capabilities`, role defaults and budget
profiles. Use `tier_override`, not the derived `tier`, for a manual adjustment; conflicting overrides
across variants or generations fail before writing. Removed models remain archived. Sync normally
writes the gitignored sibling `models.local.json`; router and eval read it first. Neither a catalog
import nor `eval/run_eval.py --refresh` changes tracked registries or upstream snapshots by default.
Remove the local file to use the bundled registry. `--write-registry` explicitly regenerates the
base YAML and matching JSON with a YAML hash, plus snapshots for a network refresh.
The JSON fallback refuses a stale hash if PyYAML is absent.
PyYAML is installed by `uv sync`.

## Cost and output

For prices I (input), C (cached input), O (output) in USD/million tokens:
`cost_index = (0.1 × I + 0.1 × C + 0.02 × O) / 0.01`.
This reference task totals 200,000 input tokens (half cached) and 20,000 output tokens across calls
at Default pricing, with no cache creation. It estimates reference credits, not a session cap or bill.
`legacy_multiplier` is historical data and never enters this formula. Budget comparisons use Decimal.
Bundled profiles cap reference credits at 5/35/100/250 for economy/standard/premium/frontier.

stdout is always one JSON object. Success includes `model`, `tier`, `level`, `reasons`,
`decision_source`, `cost_index`, `warnings`, and a shell-quoted `herdr_command` with `--pane`
(default `1`). `herdr_argv` contains the same command as tokens. Diagnostics go to stderr.
Failures contain `error`, `hint`, `exit_code`, `decision_source: null` and no launch command.
Unknown roles return exit `5`; budget failures return `2`. See the [README](../README.md)
for exit codes and [integration](integration.md) for the orchestrator block and complete example.
