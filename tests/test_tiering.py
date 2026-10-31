"""Régressions du score GitHub, des lignées et du départage financier."""

import copy
import json
import subprocess
import sys
import unittest
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from registry_lib import LEVELS, TABLE_FILES, capability_score, load_registry, model_lineage
from select_model import SelectionError, select_model
from sync_registry import build_registry, load_tables


class TieringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = load_tables({name: (ROOT / "upstream" / name).read_text(encoding="utf-8")
                                 for name in TABLE_FILES})

    def build(self, tables=None, previous=None):
        return build_registry(tables or self.tables, previous, "2026-10-30")

    def assert_monotone(self, registry):
        groups = defaultdict(list)
        for model in registry["models"]:
            lineage = model_lineage(model["family"], model["display_name"])
            self.assertIsNotNone(lineage, model["id"])
            name, version = lineage
            groups[(model["family"], name)].append((version, LEVELS.index(model["tier"]), model["id"]))
        for models in groups.values():
            for older in models:
                for newer in models:
                    if older[0] <= newer[0]:
                        with self.subTest(older=older[2], newer=newer[2]):
                            self.assertLessEqual(older[1], newer[1])

    def test_monotonie_sur_tout_le_registre_livre_et_regenere(self):
        self.assert_monotone(load_registry(ROOT / "models.yaml"))
        registry, _ = self.build()
        self.assert_monotone(registry)

    def test_versions_numeriques_et_variantes_fast(self):
        opus = [model_lineage("anthropic", name) for name in
                ("Claude Opus 4.8", "Claude Opus 5", "Claude Opus 5.5", "Claude Opus 5.10")]
        self.assertEqual(opus, sorted(opus))
        self.assertEqual(opus[0], model_lineage("anthropic", "Claude Opus 4.8 (fast mode) (preview)"))
        self.assertEqual(opus[1], model_lineage("anthropic", "Claude Opus 5.0"))
        self.assertGreater(model_lineage("openai", "GPT-6 Sol"), model_lineage("openai", "GPT-5.6 Sol"))
        self.assertNotEqual(model_lineage("openai", "GPT-6 Sol")[0], model_lineage("openai", "GPT-6 Luna")[0])
        self.assertIsNone(model_lineage("inconnu", "GPT-6 Sol"))

    def test_opus_plus_recent_et_moins_cher_prefere_en_frontier(self):
        registry, _ = self.build()
        opus = {m["id"]: m for m in registry["models"] if m["id"] in ("claude-opus-4.8", "claude-opus-5.5")}
        self.assertEqual({m["tier"] for m in opus.values()}, {"frontier"})
        self.assertGreater(opus["claude-opus-5.5"]["capability"]["score"], opus["claude-opus-4.8"]["capability"]["score"])
        self.assertLess(opus["claude-opus-5.5"]["cost_index"], opus["claude-opus-4.8"]["cost_index"])
        self.assertNotIn("tier_override", opus["claude-opus-5.5"])
        choice = select_model(registry, role="dev", level="frontier", available=[{"id": key} for key in opus])
        self.assertEqual(choice["id"], "claude-opus-5.5")

    def test_prix_change_sans_changer_scores_ni_tiers(self):
        original, _ = self.build()
        tables = copy.deepcopy(self.tables)
        for row in tables["models-and-pricing.yml"]:
            for field in ("input", "cached_input", "output"):
                row[field] = "$0.001" if row["category"] == "Powerful" else "$999"
        changed, _ = self.build(tables, original)
        for before, after in zip(original["models"], changed["models"]):
            with self.subTest(model=before["id"]):
                self.assertEqual(before["tier"], after["tier"])
                self.assertEqual(before["capability"], after["capability"])
                self.assertNotEqual(before["cost_index"], after["cost_index"])

    def test_meilleur_tier_admissible_puis_prix_sur_tout_le_registre(self):
        registry, _ = self.build()
        for wanted in LEVELS:
            for cap in (3, 20, 45, 90, 250):
                with self.subTest(wanted=wanted, cap=cap):
                    candidates = [m for m in registry["models"] if not m["preview"]
                                  and m["cost_index"] <= cap and LEVELS.index(m["tier"]) <= LEVELS.index(wanted)]
                    if not candidates:
                        continue  # Le repli supérieur a ses propres tests historiques.
                    rank = max(LEVELS.index(m["tier"]) for m in candidates)
                    expected = min((m for m in candidates if LEVELS.index(m["tier"]) == rank),
                                   key=lambda m: (m["cost_index"], m["id"]))
                    actual = select_model(registry, role="dev", preferred_level=wanted, max_cost=cap)
                    self.assertEqual(actual["tier"], expected["tier"])
                    self.assertEqual(actual["cost_index"], expected["cost_index"])

    def test_budget_opus_exact_et_code_2_reel(self):
        registry, _ = self.build()
        available = [{"id": "claude-opus-4.8"}, {"id": "claude-opus-5.5"}]
        choice = select_model(registry, role="dev", preferred_level="frontier", max_cost="82", available=available)
        self.assertEqual(choice["id"], "claude-opus-5.5")
        with self.assertRaises(SelectionError) as caught:
            select_model(registry, role="dev", preferred_level="frontier", max_cost="81.999", available=available)
        self.assertEqual(caught.exception.code, 2)
        result = subprocess.run([sys.executable, str(ROOT / "scripts/select_model.py"), "--role", "dev",
                                 "--max-cost", "81.999", "--available", "claude-opus-4.8,claude-opus-5.5", "--json"],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(json.loads(result.stdout)["exit_code"], 2)

    def add_model(self, tables, name, category, comparison=None, **pricing):
        row = copy.deepcopy(tables["models-and-pricing.yml"][0])
        row.update(model=name, provider="openai", category=category, **pricing)
        tables["models-and-pricing.yml"].append(row)
        tables["model-supported-clients.yml"].append({"name": name, "cli": True})
        if comparison:
            tables["model-comparison.yml"].append({"name": name, **comparison})

    def test_nouvelle_generation_powerful_bon_marche_et_lightweight_cher(self):
        tables = copy.deepcopy(self.tables)
        self.add_model(tables, "GPT-6.2 Sol", "Powerful",
                       {"task_area": "Long-horizon autonomous coding", "excels_at": "Complex reasoning and verification"},
                       input="$0.10", cached_input="$0.01", output="$0.50")
        self.add_model(tables, "GPT-7 Luna", "Lightweight",
                       {"task_area": "Fast help with simple tasks", "excels_at": "Quick responses"},
                       input="$99", cached_input="$99", output="$99")
        registry, report = self.build(tables)
        models = {m["id"]: m for m in registry["models"]}
        powerful, light = models["gpt-6.2-sol"], models["gpt-7-luna"]
        self.assertEqual(powerful["tier"], "frontier")
        self.assertFalse(powerful["tier_provisoire"])
        self.assertLess(powerful["cost_index"], 3)
        self.assertEqual(light["tier"], "economy")
        self.assertGreater(light["cost_index"], 100)
        self.assertNotIn("GPT-6.2 Sol", report["provisional"])
        self.assertEqual(select_model(registry, role="planner")["id"], powerful["id"])

    def test_signaux_insuffisants_categorie_seule_et_avertissement(self):
        tables = copy.deepcopy(self.tables)
        self.add_model(tables, "GPT-7 Nova", "Powerful", input="$999")
        self.add_model(tables, "Modele inconnu", "Powerful",
                       {"task_area": "Deep reasoning", "excels_at": "Complex long-horizon verification"}, input="$0.01")
        registry, report = self.build(tables)
        for name in ("GPT-7 Nova", "Modele inconnu"):
            model = next(m for m in registry["models"] if m["display_name"] == name)
            self.assertEqual(model["tier"], "premium")
            self.assertEqual(model["capability"]["components"], {"category": 65})
            self.assertTrue(model["tier_provisoire"])
            self.assertIn(name, report["provisional"])
            choice = select_model(registry, role="dev", available=[{"id": model["id"]}])
            self.assertIn("à valider", " ".join(choice["warnings"]))

    def test_monotonie_apres_un_comparatif_plus_faible_ou_absent(self):
        tables = copy.deepcopy(self.tables)
        self.add_model(tables, "GPT-7 Sol", "Powerful", input="$0.01")
        registry, _ = self.build(tables)
        sol = next(m for m in registry["models"] if m["id"] == "gpt-7-sol")
        self.assertEqual(sol["capability"]["tier_scored"], "premium")
        self.assertEqual(sol["tier"], "frontier")
        self.assertEqual(sol["tier_source"], "monotonicity")
        self.assertTrue(sol["tier_provisoire"])
        self.assert_monotone(registry)

    def test_override_prioritaire_sur_score_et_conserve_aux_syncs(self):
        registry, _ = self.build()
        target = next(m for m in registry["models"] if m["id"] == "gpt-5.3-codex")
        target["tier_override"] = "economy"
        for _ in range(2):
            registry, _ = self.build(previous=registry)
            target = next(m for m in registry["models"] if m["id"] == "gpt-5.3-codex")
            self.assertEqual(target["capability"]["tier_scored"], "premium")
            self.assertEqual(target["tier"], "economy")
            self.assertEqual(target["tier_source"], "manual")

    def test_overrides_invalides_et_non_monotones_refuses(self):
        for override in ("invalide", "", None, "premium"):
            registry, _ = self.build()
            target = next(m for m in registry["models"] if m["id"] == "claude-opus-5.5")
            target["tier_override"] = override
            with self.subTest(override=override), self.assertRaisesRegex(ValueError, "tier_override"):
                self.build(previous=registry)

    def test_override_variante_fast_applique_a_la_meme_version(self):
        registry, _ = self.build()
        fast = next(m for m in registry["models"] if m["id"] == "claude-opus-4.8-fast")
        fast["tier_override"] = "premium"
        updated, _ = self.build(previous=registry)
        peers = [m for m in updated["models"] if m["display_name"].startswith("Claude Opus 4.8")]
        self.assertEqual({m["tier"] for m in peers}, {"premium"})
        self.assertEqual(len({m["capability"]["score"] for m in peers}), 1)
        self.assert_monotone(updated)

    def test_composantes_contexte_et_statut_sans_prix(self):
        registry, _ = self.build()
        sol = next(m for m in registry["models"] if m["id"] == "gpt-6-sol")
        self.assertEqual(sol["github_context"], {"default_limit_tokens": 272000, "long_context_tier": True})
        score, missing = capability_score(sol)
        self.assertFalse(missing)
        self.assertEqual(score["components"]["context_200k"], 2)
        self.assertEqual(score["components"]["long_context_tier"], 2)
        sol["release_status"] = "Public preview"
        preview, _ = capability_score(sol)
        self.assertLess(preview["score"], score["score"])

    def test_fenetre_explicite_lue_dans_les_metadonnees(self):
        tables = copy.deepcopy(self.tables)
        next(r for r in tables["model-comparison.yml"] if r["name"] == "GPT-5.3-Codex")["context_window"] = "1M"
        registry, _ = self.build(tables)
        model = next(m for m in registry["models"] if m["id"] == "gpt-5.3-codex")
        self.assertEqual(model["github_context"]["window_tokens"], 1_000_000)
        self.assertIn("context_200k", model["capability"]["components"])


if __name__ == "__main__":
    unittest.main()
