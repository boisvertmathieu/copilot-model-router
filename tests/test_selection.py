"""Vérifie les plafonds, l'indépendance des familles et les replis."""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from registry_lib import load_registry, read_available
from select_model import SelectionError, select_model


def model(identifier, family, tier, cost, **extra):
    return {"id": identifier, "display_name": identifier, "family": family,
            "tier": tier, "cost_index": cost, "cli": True, "retired": False,
            "release_status": "GA", "preview": False, "available": True,
            "id_verified": True, **extra}


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.registry = {"models": [
            model("dev-anthropic", "anthropic", "premium", 40),
            model("autre-premium", "openai", "premium", 50),
            model("autre-standard", "google", "standard", 20),
            model("autre-economy", "openai", "economy", 2.1),
            model("autre-frontier", "google", "frontier", 150),
        ]}

    def test_budget_respecte_et_repli_inferieur(self):
        result = select_model(self.registry, role="dev", max_cost="20")
        self.assertEqual(result["id"], "autre-standard")
        self.assertEqual(result["fallback"], "lower_tier")
        self.assertLessEqual(result["cost_index"], 20)

    def test_budget_inviolable_sur_grille_de_plafonds(self):
        for cap in ("0", "2.0999", "2.1", "19.99", "20", "39", "40", "50", "200"):
            for role in ("dev", "e2e-validator", "reviewer"):
                with self.subTest(cap=cap, role=role):
                    try:
                        result = select_model(self.registry, role=role, max_cost=cap, dev_family="anthropic")
                    except SelectionError as exc:
                        self.assertEqual(exc.code, 2)
                    else:
                        self.assertLessEqual(Decimal(str(result["cost_index"])), Decimal(cap))
                        if role != "dev":
                            self.assertNotEqual(result["family"], "anthropic")

    def test_meilleur_niveau_avant_prix(self):
        result = select_model(self.registry, role="dev", level="premium")
        self.assertEqual(result["id"], "dev-anthropic")

    def test_moins_cher_dans_le_niveau(self):
        self.registry["models"].append(model("premium-abordable", "xai", "premium", 35))
        self.assertEqual(select_model(self.registry, role="dev")["id"], "premium-abordable")

    def test_equal_price_prefers_capability_before_recency_and_id(self):
        registry = {"models": [
            model("a-recent", "anthropic", "premium", 37,
                  display_name="Claude Sonnet 5", capability={"score": 60}),
            model("z-capable", "xai", "premium", 37,
                  display_name="Grok 4.7", capability={"score": 80}),
        ]}
        self.assertEqual(select_model(registry, role="dev")["id"], "z-capable")

    def test_equal_score_prefers_numeric_recency_then_id(self):
        registry = {"models": [
            model("a-older", "anthropic", "premium", 37,
                  display_name="Claude Sonnet 4.9", capability={"score": 60}),
            model("z-newer", "anthropic", "premium", 37,
                  display_name="Claude Opus 4.10", capability={"score": 60}),
        ]}
        self.assertEqual(select_model(registry, role="dev")["id"], "z-newer")
        registry["models"][0]["display_name"] = "Claude Sonnet 4.10"
        for models in (registry["models"], list(reversed(registry["models"]))):
            self.assertEqual(select_model({"models": models}, role="dev")["id"], "a-older")

    def test_e2e_et_reviewer_changent_de_famille(self):
        for role in ("e2e-validator", "reviewer"):
            result = select_model(self.registry, role=role, dev_model="dev-anthropic")
            self.assertEqual(result["id"], "autre-premium")
            self.assertNotEqual(result["family"], "anthropic")

    def test_modele_ideal_indisponible(self):
        result = select_model(self.registry, role="dev", available=[{"id": "autre-standard"}])
        self.assertEqual(result["id"], "autre-standard")
        self.assertEqual(result["fallback"], "lower_tier")

    def test_famille_jamais_relachee(self):
        for role in ("e2e-validator", "reviewer"):
            with self.assertRaises(SelectionError) as caught:
                select_model(self.registry, role=role, dev_family="anthropic",
                             available=[{"id": "dev-anthropic"}])
            self.assertEqual(caught.exception.code, 3)

    def test_famille_manquante_inconnue_et_contradictoire(self):
        cases = ({}, {"dev_model": "inconnu"}, {"dev_family": "anthropik"},
                 {"dev_family": "google", "dev_model": "dev-anthropic"})
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(SelectionError) as caught:
                select_model(self.registry, role="e2e-validator", **kwargs)
            self.assertEqual(caught.exception.code, 3)

    def test_dev_inconnu_accepte_famille_explicite_connue(self):
        result = select_model(self.registry, role="reviewer", dev_model="modele-externe", dev_family="anthropic")
        self.assertNotEqual(result["family"], "anthropic")

    def test_absence_sous_budget_code_2(self):
        with self.assertRaises(SelectionError) as caught:
            select_model(self.registry, role="dev", max_cost="2")
        self.assertEqual(caught.exception.code, 2)

    def test_relachement_niveau_seulement(self):
        result = select_model(self.registry, role="doc", level="economy",
                              available=[{"id": "autre-standard"}])
        self.assertEqual(result["fallback"], "relaxed_level")
        self.assertEqual(result["tier"], "standard")
        with self.assertRaises(SelectionError) as caught:
            select_model(self.registry, role="doc", max_cost=5, available=[{"id": "autre-standard"}])
        self.assertEqual(caught.exception.code, 2)

    def test_profils_et_defauts_par_role(self):
        self.registry["budget_profiles"] = {"petit": {"max_cost": 25, "level": "standard"}}
        result = select_model(self.registry, role="dev", budget_profile="petit")
        self.assertEqual(result["id"], "autre-standard")
        self.assertEqual(select_model(self.registry, role="doc")["tier"], "economy")
        self.assertEqual(select_model(self.registry, role="planner")["tier"], "frontier")
        with self.assertRaises(SelectionError):
            select_model(self.registry, role="dev", budget_profile="absent")

    def test_budgets_invalides_refuses(self):
        for value in ("-1", "nan", "Infinity", "1e9999", "abc", True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                select_model(self.registry, role="dev", max_cost=value)

    def test_apercu_et_politiques(self):
        preview = self.registry["models"][0]
        preview["preview"] = True
        self.assertEqual(select_model(self.registry, role="dev")["id"], "autre-premium")
        self.assertEqual(select_model(self.registry, role="dev", allow_preview=True)["id"], "dev-anthropic")
        for state in ("disabled", "unconfigured"):
            preview["runtime"] = {"policy": {"state": state}}
            self.assertEqual(select_model(self.registry, role="dev", allow_preview=True)["id"], "autre-premium")

    def test_cli_ga_et_retraits_obligatoires(self):
        for field, value in (("cli", False), ("retired", True), ("release_status", "Public preview")):
            registry = copy.deepcopy(self.registry)
            registry["models"][0][field] = value
            self.assertEqual(select_model(registry, role="dev")["id"], "autre-premium")

    def test_catalogue_frais_remplace_ancien_constat(self):
        self.registry["models"][0].update(available=False, runtime={"policy": {"state": "disabled"}})
        result = select_model(self.registry, role="dev", available=[{"id": "dev-anthropic"}])
        self.assertEqual(result["id"], "dev-anthropic")

    def test_explicit_catalog_overrides_unsupported_cli(self):
        self.registry["models"][0].update(cli=False, retired=True, available=False)
        result = select_model(self.registry, role="dev", available=[{"id": "dev-anthropic"}])
        self.assertEqual(result["id"], "dev-anthropic")

    def test_null_runtime_is_treated_as_missing_metadata(self):
        self.registry["models"][0]["runtime"] = None
        self.assertEqual(select_model(self.registry, role="dev")["id"], "dev-anthropic")

    def test_catalogue_refuse_indisponibles_et_non_chat(self):
        for fields in ({"policy": {"state": "disabled"}}, {"model_picker_enabled": False},
                       {"capabilities": {"type": "embeddings"}}, {"available": False}):
            available = [{"id": "dev-anthropic", **fields}, {"id": "autre-standard"}]
            self.assertEqual(select_model(self.registry, role="dev", available=available)["id"], "autre-standard")

    def test_alias_ne_contourne_pas_politique_canonique(self):
        self.registry["models"][0]["aliases"] = ["alias-dev"]
        available = [{"id": "dev-anthropic", "policy": {"state": "disabled"}}, {"id": "alias-dev"},
                     {"id": "autre-standard"}]
        self.assertEqual(select_model(self.registry, role="dev", available=available)["id"], "autre-standard")

    def test_id_reel_par_nom_et_famille_dev_resolue(self):
        result = select_model(self.registry, role="e2e-validator", dev_model="id-reel",
                              available=[{"id": "id-reel", "name": "dev-anthropic"}, {"id": "autre-standard"}])
        self.assertEqual(result["dev_family"], "anthropic")
        self.assertEqual(result["id"], "autre-standard")

    def test_vide_et_modele_sans_prix_ne_deviennent_pas_disponibles(self):
        for available in ([], [{"id": "inconnu-sans-prix"}]):
            with self.assertRaises(SelectionError):
                select_model(self.registry, role="dev", available=available)

    def test_sortie_ne_modifie_pas_registre_et_commande_sans_shell(self):
        before = copy.deepcopy(self.registry)
        result = select_model(self.registry, role="dev")
        self.assertEqual(self.registry, before)
        self.assertEqual(result["herdr_argv"][-3:], ["--", "--model", result["id"]])


class IntegrationSelectionTests(unittest.TestCase):
    def run_select(self, *args, no_yaml=False):
        return subprocess.run([sys.executable, *(["-S"] if no_yaml else []),
                               str(ROOT / "scripts/select_model.py"), *args, "--json"],
                              capture_output=True, text=True, cwd="/tmp")

    def test_codes_de_sortie_reels(self):
        cap = self.run_select("--role", "dev", "--max-cost", "0")
        self.assertEqual(cap.returncode, 2)
        self.assertEqual(json.loads(cap.stdout)["exit_code"], 2)
        family = self.run_select("--role", "e2e-validator", "--dev-family", "anthropic",
                                  "--available", "claude-opus-5")
        self.assertEqual(family.returncode, 3)
        self.assertEqual(json.loads(family.stdout)["exit_code"], 3)

    def test_unknown_role_json_exit_5(self):
        result = self.run_select("--role", "unknown")
        self.assertEqual(result.returncode, 5)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["exit_code"], 5)
        self.assertTrue(payload["hint"])
        self.assertIsNone(payload["decision_source"])
        self.assertEqual(result.stderr, "")

    def test_cli_json_contract_default_pane_and_errors(self):
        result = self.run_select("--role", "test", "--available", "grok-4.5,grok-4.7")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["model"], "grok-4.7")
        self.assertEqual(payload["decision_source"], "heuristic")
        self.assertEqual(payload["herdr_command"],
                         "herdr agent start test --kind copilot --pane 1 -- --model grok-4.7")
        for args in ((), ("--role", "test", "--level", "invalid"),
                     ("--role", "test", "--available", ""),
                     ("--role", "test", "--max-cost", "0")):
            with self.subTest(args=args):
                result = self.run_select(*args)
                self.assertNotEqual(result.returncode, 0)
                payload = json.loads(result.stdout)
                self.assertTrue(payload["error"])
                self.assertTrue(payload["hint"])
                self.assertIn("decision_source", payload)

    def test_secours_sans_pyyaml(self):
        normal = self.run_select("--role", "doc")
        fallback = self.run_select("--role", "doc", no_yaml=True)
        self.assertEqual(fallback.returncode, 0, fallback.stderr)
        self.assertEqual(json.loads(fallback.stdout), json.loads(normal.stdout))

    def test_json_perime_refuse_sans_pyyaml(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "models.yaml"
            path.write_text("models: []\n", encoding="utf-8")
            path.with_suffix(".json").write_text('{"models": [], "_yaml_sha256": "ancien"}')
            result = self.run_select("--role", "doc", "--registry", str(path), no_yaml=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("périmé", result.stdout)

    def test_formats_de_disponibilite(self):
        for payload in (["gpt-6-sol"], {"models": [{"id": "gpt-6-sol"}]},
                        {"data": [{"id": "gpt-6-sol"}]},
                        {"result": {"models": [{"id": "gpt-6-sol"}]}}):
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "catalogue.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                self.assertEqual(read_available(str(path))[0]["id"], "gpt-6-sol")
        self.assertEqual(len(read_available("gpt-6-sol,claude-opus-5")), 2)
        self.assertEqual(read_available('["gpt-6-sol"]'), [{"id": "gpt-6-sol"}])
        with self.assertRaises(ValueError):
            read_available("@introuvable.json")

    def test_longue_liste_d_ids_sans_erreur_de_chemin(self):
        value = ",".join(f"modele-{i}" for i in range(100))
        self.assertEqual(len(read_available(value)), 100)

    def test_yaml_invalide_refuse_sans_traceback(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "models.yaml"
            path.write_text("models: [\n", encoding="utf-8")
            result = self.run_select("--role", "doc", "--registry", str(path))
            self.assertEqual(result.returncode, 1)
            self.assertIn("YAML est invalide", result.stdout)
            self.assertNotIn("Traceback", result.stderr)

    def test_integrite_du_registre_livre(self):
        registry = load_registry(ROOT / "models.yaml")
        self.assertEqual(len(registry["models"]), 26)
        self.assertTrue(all(model_["cli"] for model_ in registry["models"] if not model_.get("retired")))


if __name__ == "__main__":
    unittest.main()
