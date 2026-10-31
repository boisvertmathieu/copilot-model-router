"""Vérifie les vrais fichiers upstream et la conservation des réglages."""

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from registry_lib import TABLE_FILES, catalog_entries, reference_cost
from sync_registry import build_registry, load_tables


class SyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contents = {name: (ROOT / "upstream" / name).read_text(encoding="utf-8") for name in TABLE_FILES}
        cls.tables = load_tables(cls.contents)

    def build(self, previous=None, payload=None, tables=None):
        return build_registry(tables or self.tables, previous, "2026-10-30", payload)

    def test_intersection_cli_et_notes_markdown(self):
        registry, report = self.build()
        names = {model["display_name"] for model in registry["models"]}
        self.assertEqual(len(names), 26)
        self.assertIn("Gemini 4 Argon", names)
        self.assertIn("Gemini 3.8 Flash", names)
        self.assertNotIn("GPT-5.4 nano", names)
        self.assertNotIn("GPT-6.1 Sol", names)
        self.assertNotIn("Claude Sonnet 4", names)
        self.assertEqual(len(report["excluded_non_cli"]), 3)

    def test_vrais_prix_default_et_calculs(self):
        registry, _ = self.build()
        models = {model["id"]: model for model in registry["models"]}
        self.assertEqual(models["gpt-5.3-codex"]["pricing"]["cached_input"], 0.175)
        self.assertEqual(models["gpt-5.3-codex"]["cost_index"], 47.25)
        self.assertEqual(models["gpt-6-luna"]["pricing"]["input"], 0.1)
        self.assertEqual(models["gpt-6-luna"]["pricing"]["cache_write"], 0.125)
        self.assertEqual(models["gpt-6-luna"]["cost_index"], 2.1)
        self.assertEqual(models["gemini-4-argon"]["cost_index"], 41)
        self.assertIsNone(models["gemini-4-argon"]["pricing"]["cache_write"])
        for model in registry["models"]:
            self.assertEqual(model["cost_index"], reference_cost(model["pricing"]))
            self.assertEqual(model["pricing"]["tier"], "Default")

    def test_multiplicateurs_legacy_distincts(self):
        registry, _ = self.build()
        models = {model["id"]: model for model in registry["models"]}
        self.assertEqual(models["claude-opus-4.8"]["legacy_multiplier"], 27)
        self.assertEqual(models["claude-opus-4.8"]["cost_index"], 105)
        self.assertIsNone(models["claude-opus-5"]["legacy_multiplier"])

    def test_preview_malgre_ga(self):
        registry, _ = self.build()
        fast = next(model for model in registry["models"] if "fast mode" in model["display_name"])
        self.assertEqual(fast["release_status"], "GA")
        self.assertTrue(fast["preview"])

    def test_champs_manuels_conserves_prix_actualises(self):
        registry, _ = self.build()
        first = registry["models"][0]
        first.update(id="id-manuel", id_verified=True, id_source="Preuve manuelle",
                     notes="Conserver cette note.", tier_override="premium", manual_capabilities=["revue"])
        first["pricing"]["input"] = 999
        registry["budget_profiles"]["sur-mesure"] = {"level": "standard", "max_cost": 18}
        registry["role_defaults"]["dev"] = "standard"
        updated, _ = self.build(registry)
        kept = next(model for model in updated["models"] if model["id"] == "id-manuel")
        self.assertTrue(kept["id_verified"])
        self.assertEqual(kept["notes"], "Conserver cette note.")
        self.assertEqual(kept["tier"], "premium")
        self.assertIn("revue", kept["capabilities"])
        self.assertNotEqual(kept["pricing"]["input"], 999)
        self.assertIn("sur-mesure", updated["budget_profiles"])
        self.assertEqual(updated["role_defaults"]["dev"], "standard")

    def test_nouveaux_et_retraits_conserves_comme_archives(self):
        registry, first_report = self.build()
        self.assertEqual(len(first_report["new"]), 26)
        tables = copy.deepcopy(self.tables)
        tables["model-supported-clients.yml"] = [row for row in tables["model-supported-clients.yml"]
                                                  if row["name"] != "Grok 4.7"]
        updated, report = self.build(registry, tables=tables)
        removed = next(model for model in updated["models"] if model["id"] == "grok-4.7")
        self.assertTrue(removed["retired"])
        self.assertFalse(removed["cli"])
        self.assertFalse(removed["available"])
        self.assertEqual(report["removed"], ["Grok 4.7"])
        _, second_report = self.build(updated, tables=tables)
        self.assertEqual(second_report["removed"], [])

    def test_nouveau_modele_provisoire_persistant_et_validation_manuelle(self):
        registry, _ = self.build()
        tables = copy.deepcopy(self.tables)
        pricing = copy.deepcopy(tables["models-and-pricing.yml"][0])
        pricing.update(model="Modèle nouveau", provider="openai", category="Lightweight", release_status="GA")
        tables["models-and-pricing.yml"].append(pricing)
        tables["model-supported-clients.yml"].append({"name": "Modèle nouveau", "cli": True})
        updated, report = self.build(registry, tables=tables)
        new = next(model for model in updated["models"] if model["display_name"] == "Modèle nouveau")
        self.assertEqual(new["tier"], "economy")
        self.assertTrue(new["tier_provisoire"])
        self.assertIn("à valider", new["tier_note"])
        self.assertEqual(report["new"], ["Modèle nouveau"])
        self.assertIn("Modèle nouveau", report["provisional"])
        from route import route
        choice = route(updated, role="doc", story="typo", available=[{"id": new["id"]}])
        self.assertEqual(choice["model"], new["id"])
        self.assertTrue(choice["tier_provisoire"])
        self.assertIn("à valider", choice["reason"])
        repeated, _ = self.build(updated, tables=tables)
        new = next(model for model in repeated["models"] if model["display_name"] == "Modèle nouveau")
        self.assertTrue(new["tier_provisoire"])
        new["tier_override"] = "standard"
        validated, report = self.build(repeated, tables=tables)
        new = next(model for model in validated["models"] if model["display_name"] == "Modèle nouveau")
        self.assertFalse(new["tier_provisoire"])
        self.assertEqual(new["tier"], "standard")
        self.assertNotIn("tier_note", new)
        self.assertNotIn("Modèle nouveau", report["provisional"])

    def test_niveau_connu_non_marque_provisoire(self):
        registry, _ = self.build()
        for model in registry["models"]:
            model.pop("tier_provisoire", None)
        updated, report = self.build(registry)
        self.assertFalse(any(model.get("tier_provisoire") for model in updated["models"]))
        self.assertEqual(report["provisional"], [])

    def test_tiers_deduits_des_metadonnees_suffisantes(self):
        registry, _ = self.build()
        models = {model["id"]: model for model in registry["models"]}
        for identifier, tier in (("claude-haiku-5.5", "economy"), ("claude-sonnet-5.5", "standard"),
                                 ("gemini-4-argon", "premium"), ("claude-opus-5", "frontier")):
            with self.subTest(identifier=identifier):
                self.assertEqual(models[identifier]["tier"], tier)
                self.assertFalse(models[identifier]["tier_provisoire"])
                self.assertIn("score", models[identifier]["capability"])

    def test_import_cli_reel_politique_et_id_corrige(self):
        payload = {"source": "models.list", "models": [
            {"id": "id-cli-corrige", "name": "Kimi K3", "policy": {"state": "enabled"}},
            {"id": "gpt-6-sol", "vendor": "Azure OpenAI", "policy": {"state": "disabled"}},
            {"id": "grok-4.7", "model_picker_enabled": False},
            {"id": "sans-tarif"},
        ]}
        registry, report = self.build(payload=payload)
        models = {model["id"]: model for model in registry["models"]}
        self.assertTrue(models["id-cli-corrige"]["available"])
        self.assertTrue(models["id-cli-corrige"]["id_verified"])
        self.assertIn("kimi-k3", models["id-cli-corrige"]["aliases"])
        self.assertFalse(models["gpt-6-sol"]["available"])
        self.assertEqual(models["gpt-6-sol"]["family"], "openai")
        self.assertFalse(models["grok-4.7"]["available"])
        self.assertFalse(models["claude-opus-5"]["available"])
        self.assertEqual(report["unmatched_cli"], [])
        self.assertEqual(report["pricing_missing"], ["sans-tarif"])

    def test_import_ambigu_exclu(self):
        registry, report = self.build(payload=[{"id": "kimi-a", "name": "Kimi K3"},
                                                {"id": "kimi-b", "name": "Kimi K3"}])
        kimi = next(model for model in registry["models"] if model["id"] == "kimi-k3")
        self.assertFalse(kimi["available"])
        self.assertEqual(report["ambiguous_cli"], ["Kimi K3"])

    def test_org_catalog_overrides_documented_cli_support(self):
        from route import route
        for entry in ("gpt-6.1-sol", "gpt-5.4-nano", {"id": "org-sol", "name": "GPT-6.1 Sol"}):
            with self.subTest(entry=entry):
                registry, report = self.build(payload=[entry])
                identifier = entry if isinstance(entry, str) else entry["id"]
                selected = next(model for model in registry["models"] if model["id"] == identifier)
                self.assertTrue(selected["cli"])
                self.assertTrue(selected["available"])
                self.assertNotIn(selected["display_name"], report["excluded_non_cli"])
                self.assertNotIn(identifier, report["unmatched_cli"])
                self.assertEqual(route(registry, role="dev")["model"], identifier)
                self.assertEqual(route(registry, role="dev", available=[entry])["model"], identifier)

    def test_documented_models_absent_from_org_are_never_chosen(self):
        from route import route
        registry, _ = self.build(payload=["gpt-6-luna"])
        for role in ("dev", "test", "doc", "planner", "reviewer"):
            with self.subTest(role=role):
                result = route(registry, role=role, dev_family="anthropic", story="CVE")
                self.assertEqual(result["model"], "gpt-6-luna")

    def test_unknown_org_model_inherits_direct_predecessor_price_and_provisional_tier(self):
        from route import route
        entries = ["gpt-6-sol", {"id": "gpt-7-sol", "name": "GPT-7 Sol"}]
        registry, report = self.build(payload=entries)
        new = next(model for model in registry["models"] if model["id"] == "gpt-7-sol")
        self.assertTrue(new["tier_provisoire"])
        self.assertEqual(new["tier"], "frontier")
        predecessor = next(model for model in registry["models"] if model["id"] == "gpt-6-sol")
        self.assertEqual(new["cost_index"], predecessor["cost_index"])
        self.assertTrue(new["prix_suppose"])
        self.assertEqual(new["pricing_predecessor"], predecessor["id"])
        self.assertEqual(report["unmatched_cli"], [])
        self.assertNotIn(new["id"], report["pricing_missing"])
        self.assertIn(new["id"], report["pricing_assumed"])
        self.assertEqual(route(registry, role="dev")["model"], "gpt-7-sol")
        entries[1]["cost_index"] = 40
        updated, _ = self.build(registry, payload=entries)
        self.assertEqual(route(updated, role="dev")["model"], "gpt-7-sol")

    def test_org_only_models_added_with_provisional_tiers_and_known_costs(self):
        from route import route
        entries = ["grok-4.7", "claude-opus-5.5",
                   {"id": "grok-4.8", "cost_index": 37},
                   {"id": "claude-opus-6", "cost_index": 80}]
        registry = None
        for _ in range(2):
            registry, report = self.build(registry, payload=entries)
            models = {model["id"]: model for model in registry["models"]}
            self.assertEqual(report["unmatched_cli"], [])
            self.assertEqual(report["pricing_missing"], [])
            for identifier, tier in (("grok-4.8", "premium"), ("claude-opus-6", "frontier")):
                with self.subTest(identifier=identifier):
                    self.assertTrue(models[identifier]["cli"])
                    self.assertTrue(models[identifier]["available"])
                    self.assertTrue(models[identifier]["tier_provisoire"])
                    self.assertEqual(models[identifier]["tier"], tier)
            self.assertEqual(route(registry, role="dev", available="grok-4.7,grok-4.8")["model"], "grok-4.8")
            self.assertEqual(route(registry, role="planner", available="claude-opus-5.5,claude-opus-6")["model"],
                             "claude-opus-6")

    def test_catalogues_invalides_et_integres_refuses(self):
        for payload in ({"error": "Non authentifié"}, {"source": "models.getBuiltInCatalog", "models": []},
                        {"inconnu": []}, [{"id": "a"}, {"id": "a"}], [{"name": "Sans ID"}]):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                catalog_entries(payload)

    def test_champs_de_catalogue_invalides_refuses(self):
        for entry in ({"id": "avec espace"}, {"id": "a", "policy": "enabled"},
                      {"id": "a", "capabilities": []}, {"id": "a", "name": 12}):
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                catalog_entries([entry])

    def test_yaml_officiel_invalide_signale(self):
        contents = dict(self.contents)
        contents["models-and-pricing.yml"] = "model: ["
        with self.assertRaisesRegex(ValueError, "YAML officiel invalide"):
            load_tables(contents)

    def test_prix_manquant_ne_devient_pas_zero(self):
        tables = copy.deepcopy(self.tables)
        tables["models-and-pricing.yml"][0]["input"] = None
        registry, report = self.build(tables=tables)
        missing = next(model for model in registry["models"]
                       if model["display_name"] == tables["models-and-pricing.yml"][0]["model"])
        self.assertIsNone(missing["cost_index"])
        self.assertTrue(missing["pricing_missing"])
        self.assertIn(missing["id"], report["pricing_missing"])

    def test_sync_locale_cli_et_parite_yaml_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "models.yaml"
            result = subprocess.run([sys.executable, str(ROOT / "scripts/sync_registry.py"),
                                     "--upstream-dir", str(ROOT / "upstream"), "--registry", str(path),
                                     "--write-registry", "--json"],
                                    capture_output=True, text=True, cwd="/tmp")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["mode"], "local")
            import yaml
            yaml_data = yaml.safe_load(path.read_text(encoding="utf-8"))
            json_data = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(json_data.pop("_yaml_sha256"), hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(yaml_data, json_data)


if __name__ == "__main__":
    unittest.main()
