"""Propriétés, invariants, juges et sorties de la suite d'évaluation."""

import contextlib
import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval import run_eval as ev


class EvalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ev.load_registry(ROOT / "models.yaml")
        cls.cases = ev.load_cases(ROOT / "eval/cases.yaml")

    def case(self, identifier="dev-filtre-commandes"):
        return copy.deepcopy(next(case for case in self.cases if case["id"] == identifier))

    def model(self, identifier):
        return next(model for model in self.registry["models"] if model["id"] == identifier)

    def cli(self, directory):
        cli = Path(directory) / "copilot-juge-simule"
        fixture = ROOT / "tests/fixtures/fake_judge.py"
        cli.write_text(f"#!{sys.executable}\nexec(compile(open({str(fixture)!r}).read(), 'juge-simule', 'exec'))\n", encoding="utf-8")
        cli.chmod(0o755)
        return str(cli)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "eval/run_eval.py"), *args],
                              cwd="/tmp", capture_output=True, text=True, timeout=15)

    def test_corpus_complet_et_attentes_sans_id_fixe(self):
        self.assertGreaterEqual(len(self.cases), 100)
        self.assertEqual({case["inputs"]["role"] for case in self.cases}, set(ev.ROLES))
        self.assertEqual({case["expect_exit"] for case in self.cases}, {0, 2, 3, 4})
        self.assertEqual({case["expect"].get("tier") for case in self.cases
                          if isinstance(case["expect"].get("tier"), str)}, set(ev.LEVELS))
        for case in self.cases:
            self.assertLessEqual(case["expect"].keys(), ev.EXPECT_KEYS)

    def test_chargement_refuse_cas_vides_dupliques_et_propriete_inconnue(self):
        cases = [self.case()]
        invalid = [None, [], {"schema_version": 2, "cases": cases}, {"schema_version": 1, "cases": []},
                   {"schema_version": 1, "cases": cases * 2}]
        modifications = [({"expect": {"model": "id-fige"}}), {"expect_exit": True},
                         {"expect": {"tier": ["frontier", "economy"]}}, {"expect": {"level": []}},
                         {"expect": {"cost_range": [30, 2]}}, {"expect": {"max_cost": "nan"}},
                         {"expect": {"family_not": []}}, {"expect": {"tier_provisoire": "oui"}},
                         {"expect": {"warning_contains": 3}}, {"expect": {}}, {"extra": "inconnu"},
                         {"simulate_model": {"model": "Incomplet"}}, {"simulate_live_failure": False},
                         {"expect_exit": 3, "expect": {"tier": "premium"}}]
        for change in modifications:
            case = self.case()
            case.update(change)
            invalid.append({"schema_version": 1, "cases": [case]})
        for change in ({"role": "inconnu"}, {"classifier": "llm"}, {"available": "live"}, {"story": "@mission.txt"}):
            case = self.case()
            case["inputs"].update(change)
            invalid.append({"schema_version": 1, "cases": [case]})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.yaml"
            for payload in invalid:
                with self.subTest(payload=payload):
                    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        ev.load_cases(path)
            path.write_text("cases: [", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "YAML"):
                ev.load_cases(path)

    def test_tous_les_cas_et_invariants_rejoues_par_la_vraie_fonction(self):
        before = copy.deepcopy(self.registry)
        report = ev.evaluate(self.cases, self.registry, judge=ev.FakeJudge())
        self.assertTrue(report["passed"], [r for r in report["results"] if not r["passed"]])
        self.assertEqual(report["summary"]["passed"], len(self.cases))
        self.assertEqual(report["summary"]["judge"]["mean_score"], 1)
        self.assertEqual(report["invariant_failures"], [])
        self.assertEqual(self.registry, before)
        self.assertEqual(report["drift"]["status"], "SAUTÉ")

    def test_verification_proprietes_independante(self):
        case = self.case()
        decision = ev.run_case(case, self.registry)["decision"]
        case["expect"] = {"level": ["trivial", "standard"], "tier": ["economy", "premium"],
                          "family_not": "anthropic", "max_cost": 30, "cost_range": [1, 30],
                          "tier_provisoire": False}
        self.assertEqual(ev.check_properties(case, decision), [])
        case["expect"] = {"level": "critique", "tier": "frontier", "family_not": decision["family"],
                          "max_cost": 1, "cost_range": [100, 200], "tier_provisoire": True,
                          "warning_contains": "Avertissement absent"}
        self.assertEqual(len(ev.check_properties(case, decision)), 7)
        self.assertTrue(ev.check_properties(case, {"exit_code": 2, "error": "Budget"}))
        refusal = self.case("budget-zero-impossible")
        self.assertEqual(ev.check_properties(refusal, {"exit_code": 2}), [])
        self.assertTrue(ev.check_properties(refusal, decision))

    def test_invariants_detectent_budget_famille_tier_et_available_sans_faire_confiance_decision(self):
        case = self.case("e2e-inscription")
        inputs = {**case["inputs"], "max_cost": 40}
        decision = ev.run_case(case, self.registry)["decision"]
        decision.update(model="hors-catalogue", family="anthropic", dev_family="faux", cost_index=1000, tier="economy")
        failures = ev.decision_invariants(self.registry, inputs, decision, [{"id": "gpt-6-sol"}])
        for text in ("Budget dépassé", "hors available", "entrée unique", "indépendante", "incohérente", "sous premium"):
            self.assertTrue(any(text in failure for failure in failures), failures)
        doc = self.case("doc-installation")
        decision = ev.run_case(doc, self.registry)["decision"]
        decision["tier"] = "frontier"
        self.assertTrue(any("doc dépasse" in failure for failure in ev.decision_invariants(self.registry, doc["inputs"], decision, None)))

    def test_invariant_budget_profil_utilise_plafond_du_registre(self):
        case = self.case("budget-profil-economy")
        decision = ev.run_case(case, self.registry)["decision"]
        decision.update(cost_index=6, max_cost=999999)
        failures = ev.decision_invariants(self.registry, case["inputs"], decision, None)
        self.assertTrue(any("Budget dépassé" in failure for failure in failures))

    def test_monotonie_violations_et_variantes_fast(self):
        self.assertEqual(ev.registry_invariants(self.registry), [])
        registry = copy.deepcopy(self.registry)
        next(m for m in registry["models"] if m["id"] == "claude-opus-5.5")["tier"] = "economy"
        self.assertTrue(any("Monotonie" in item for item in ev.registry_invariants(registry)))
        report = ev.evaluate([self.case()], registry)
        self.assertFalse(report["passed"])
        registry = copy.deepcopy(self.registry)
        next(m for m in registry["models"] if m["id"] == "claude-opus-4.8-fast")["tier"] = "economy"
        self.assertTrue(ev.registry_invariants(registry))

    def test_catalogue_global_intersection_et_politiques(self):
        case = self.case("available-repli-inferieur")
        result = ev.run_case(case, self.registry, [{"id": "gpt-6.1-terra"}, {"id": "gpt-6-sol"}])
        self.assertTrue(result["passed"])
        self.assertEqual(result["decision"]["model"], "gpt-6.1-terra")
        excluded = ev.run_case(case, self.registry, [{"id": "gpt-6-sol"}])
        self.assertFalse(excluded["passed"])
        self.assertNotEqual(excluded["exit_code"], 0)
        global_catalog = [{"id": "gpt-6-sol"}, {"id": "gpt-6.1-terra"}]
        result = ev.run_case(self.case("available-politique-desactivee"), self.registry, global_catalog)
        self.assertTrue(result["passed"])
        self.assertEqual(result["decision"]["tier"], "standard")
        global_catalog[1]["policy"] = {"state": "disabled"}
        self.assertFalse(ev.run_case(self.case("available-politique-desactivee"), self.registry, global_catalog)["passed"])

    def test_intersection_resout_id_reel_par_nom(self):
        model = self.model("gpt-6.1-terra")
        catalogue = [{"id": "id-observe", "name": model["display_name"]}]
        case = self.case("available-doc-repli")
        result = ev.run_case(case, self.registry, catalogue)
        self.assertTrue(result["passed"], result["failures"])
        self.assertEqual(result["decision"]["model"], "id-observe")

    def test_nouveau_modele_passe_par_sync_et_registre_temporaire(self):
        case = self.case("nouveau-modele-provisoire")
        with tempfile.TemporaryDirectory() as directory:
            updated = ev.simulated_registry(self.registry, case["simulate_model"], Path(directory))
            self.assertTrue((Path(directory) / "registry.json").exists())
        added = next(m for m in updated["models"] if m["id"] == "gpt-7-nova")
        self.assertTrue(added["tier_provisoire"])
        self.assertEqual(added["tier_source"], "category_only")
        self.assertEqual(added["capability"]["components"], {"category": 65})
        self.assertEqual(ev.registry_invariants(updated), [])
        result = ev.run_case(case, self.registry)
        self.assertTrue(result["passed"])
        self.assertEqual(result["catalog_scope"], "simulation isolée")

    def test_catalogue_global_ne_permet_jamais_de_choisir_un_modele_fictif(self):
        catalogue = [{"id": model["id"]} for model in self.registry["models"]]
        ids = {entry["id"] for entry in catalogue}
        report = ev.evaluate(self.cases, self.registry, available=catalogue, judge=ev.FakeJudge())
        self.assertTrue(report["passed"])
        self.assertEqual(report["summary"]["skipped"], 2)
        self.assertEqual(report["summary"]["total"], len(self.cases) - 2)
        self.assertEqual(report["summary"]["judge"]["count"], len(self.cases) - 2)
        for result in report["results"]:
            if result["skipped"]:
                self.assertIsNone(result["decision"])
                self.assertIsNone(result["passed"])
            elif result["exit_code"] == 0:
                self.assertIn(result["decision"]["model"], ids)
        self.assertIn("## Scénarios sautés", ev.render_report(report))
        report = ev.evaluate([self.case("nouveau-modele-provisoire")], self.registry, available=catalogue)
        self.assertFalse(report["passed"])
        self.assertIn("Aucun cas exécuté", report["operational_errors"][0])

    def test_code_4_simule_ne_contacte_pas_copilot_reel(self):
        result = ev.run_case(self.case("live-panne-simulee"), self.registry)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["exit_code"], 4)

    def test_fake_judge_ecart_tier_et_refus(self):
        case = self.case()
        judge = ev.FakeJudge()
        for tier, score in (("standard", 1), ("economy", 2 / 3), ("frontier", 1 / 3)):
            with self.subTest(tier=tier):
                verdict = judge.judge(case, {"exit_code": 0, "tier": tier})
                self.assertAlmostEqual(verdict["score"], score)
        self.assertEqual(judge.judge(case, {"exit_code": 2})["score"], 0)
        self.assertEqual(judge.judge(self.case("budget-zero-impossible"), {"exit_code": 2})["score"], 1)
        doc_case = self.case("doc-cve")
        del doc_case["expect"]["tier"]
        self.assertEqual(judge.judge(doc_case, {"exit_code": 0, "tier": "standard"})["score"], 1)

    def test_seuil_moyen_independant_des_proprietes(self):
        class ScoreJudge:
            def __init__(self, score):
                self.score = score

            def judge(self, case, decision):
                return {"score": self.score, "justification": "Score fixé pour éprouver le seuil."}

        for score, passed in ((0.84, False), (0.85, True), (1, True)):
            with self.subTest(score=score):
                report = ev.evaluate([self.case()], self.registry, judge=ScoreJudge(score))
                self.assertEqual(report["summary"]["failed"], 0)
                self.assertEqual(report["passed"], passed)
                self.assertEqual(report["exit_code"], 0 if passed else 1)
                self.assertAlmostEqual(report["by_role"]["dev"]["judge"]["mean_score"], score)
        for threshold in (float("nan"), float("inf"), -0.1, 1.1, True):
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                ev.evaluate([self.case()], self.registry, threshold=threshold)
        report = ev.evaluate(self.cases[:10], self.registry, judge=ScoreJudge(0.85))
        self.assertTrue(report["passed"])

    def test_erreur_juge_comptee_zero_et_poursuite_des_cas(self):
        class BrokenJudge:
            def judge(self, case, decision):
                raise RuntimeError("Panne simulée")

        report = ev.evaluate(self.cases[:2], self.registry, judge=BrokenJudge(), threshold=0)
        self.assertEqual(report["summary"]["judge"], {"count": 2, "mean_score": 0, "success_rate": 0, "errors": 2})
        self.assertFalse(report["passed"])
        self.assertEqual(report["summary"]["passed"], 2)
        self.assertIn("Panne simulée", ev.render_report(report))

    def test_copilot_juge_vrai_subprocess_json_brut_bloc_et_diagnostics(self):
        case = self.case()
        decision = ev.run_case(case, self.registry)["decision"]
        with tempfile.TemporaryDirectory() as directory:
            cli = self.cli(directory)
            for mode in ("valid", "fenced", "progress"):
                with self.subTest(mode=mode):
                    verdict = ev.CopilotJudge(mode, cli=cli, timeout=2).judge(case, decision)
                    self.assertEqual(verdict["score"], 0.9)
                    self.assertIn("francophone", verdict["justification"])

    def test_copilot_juge_parsing_refuse_ambigu_et_invalides(self):
        case = self.case()
        decision = ev.run_case(case, self.registry)["decision"]
        with tempfile.TemporaryDirectory() as directory:
            cli = self.cli(directory)
            for mode in ("invalid", "ambiguous", "boolean", "nan", "duplicate", "error"):
                with self.subTest(mode=mode), self.assertRaises(ev.JudgeError):
                    ev.CopilotJudge(mode, cli=cli, timeout=2).judge(case, decision)
        for output in ('{"score": -1, "justification": "x"}', '{"score": 1.1, "justification": "x"}',
                       '{"score": "0.9", "justification": "x"}', '{"score": 0.9, "justification": " "}',
                       '{"score": 0.9, "justification": "x", "extra": 1}', '{}', '[]'):
            with self.subTest(output=output), self.assertRaises(ev.JudgeError):
                ev.parse_judgment(output)

    def test_copilot_juge_timeout_et_executable_absent(self):
        case = self.case()
        decision = ev.run_case(case, self.registry)["decision"]
        with tempfile.TemporaryDirectory() as directory:
            cli = self.cli(directory)
            with self.assertRaisesRegex(ev.JudgeError, "Délai"):
                ev.CopilotJudge("timeout", cli=cli, timeout=0.1).judge(case, decision)
            with self.assertRaisesRegex(ev.JudgeError, "impossible"):
                ev.CopilotJudge("absent", cli=str(Path(directory) / "absent")).judge(case, decision)
            report = ev.evaluate([case], self.registry, judge=ev.CopilotJudge("timeout", cli=cli, timeout=0.1))
            self.assertEqual(report["summary"]["judge"]["errors"], 1)
            self.assertFalse(report["passed"])

    def test_derive_nouveau_modele_org_sans_tier(self):
        entries = [{"id": model["id"]} for model in self.registry["models"]]
        report = ev.check_drift(self.registry, entries + [{"id": "modele-org-nouveau"}])
        self.assertEqual(report["status"], "ÉCHEC")
        self.assertEqual(report["unregistered"], ["modele-org-nouveau"])
        self.assertEqual(report["missing"], [])
        self.assertIn("lancer refresh", report["reason"])
        registry = copy.deepcopy(self.registry)
        registry["models"][0].pop("tier")
        self.assertIn(entries[0]["id"], ev.check_drift(registry, entries)["unregistered"])

    def test_derive_modele_retire_du_catalogue_et_ignore_archives_registre(self):
        entries = [{"id": model["id"]} for model in self.registry["models"]]
        report = ev.check_drift(self.registry, entries[1:])
        self.assertEqual(report["status"], "ÉCHEC")
        self.assertEqual(report["missing"], [entries[0]["id"]])
        registry = copy.deepcopy(self.registry)
        registry["models"][0]["retired"] = True
        self.assertEqual(ev.check_drift(registry, entries[1:])["status"], "OK")

    def test_derive_sautee_sans_live_et_alias_rapproches(self):
        self.assertEqual(ev.check_drift(self.registry)["status"], "SAUTÉ")
        entries = [{"id": model["id"]} for model in self.registry["models"]]
        entries[0] = {"id": "id-reel", "name": self.registry["models"][0]["display_name"]}
        self.assertEqual(ev.check_drift(self.registry, entries)["status"], "OK")
        self.assertEqual(ev.check_drift(self.registry, [])["status"], "ÉCHEC")

    def test_filtres_role_id_et_aucun_resultat(self):
        self.assertTrue(all(case["inputs"]["role"] == "doc" for case in ev.filter_cases(self.cases, "role/doc")))
        self.assertEqual(len(ev.filter_cases(self.cases, "id/budget-zero")), 1)
        self.assertEqual(len(ev.filter_cases(self.cases, "famille-")), 4)
        with self.assertRaisesRegex(ValueError, "Aucun cas"):
            ev.evaluate([], self.registry)

    def test_rapport_json_et_markdown_avec_commandes_depuis_autre_repertoire(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "rapport.md"
            result = self.run_cli("--filter", "role/doc", "--judge", "--fake-judge", "--json", "--report", str(report_path))
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            report = json.loads(result.stdout)
            expected_ids = {case["id"] for case in self.cases if case["inputs"]["role"] == "doc"}
            self.assertEqual({result["id"] for result in report["results"]}, expected_ids)
            self.assertEqual(report["summary"]["total"], len(expected_ids))
            self.assertEqual(report["by_role"]["doc"]["success_rate"], 1)
            self.assertEqual(report["judge_name"], "FakeJudge")
            self.assertIn("**SAUTÉ**", report_path.read_text(encoding="utf-8"))
            self.assertIn("## Par tier", report_path.read_text(encoding="utf-8"))
            self.assertNotIn("NaN", result.stdout)

    def test_options_available_registry_cases_et_json_de_derive(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            registry_path = directory / "models.json"
            registry_path.write_text(ev.dump_json(self.registry), encoding="utf-8")
            cases_path = directory / "cases.yaml"
            cases_path.write_text(yaml.safe_dump({"schema_version": 1, "cases": [self.case()]}), encoding="utf-8")
            catalogue = directory / "org.json"
            entries = [{"id": model["id"]} for model in self.registry["models"]]
            for added, expected in (([], 0), ([{"id": "nouveau-org"}], 1)):
                catalogue.write_text(json.dumps({"source": "models.list", "models": entries + added}), encoding="utf-8")
                result = self.run_cli("--cases", str(cases_path), "--registry", str(registry_path),
                                      "--available", str(catalogue), "--json", "--report", str(directory / "report.md"))
                report = json.loads(result.stdout)
                self.assertEqual(result.returncode, expected, report)
                self.assertEqual(report["summary"]["failed"], 0)
                self.assertEqual(report["drift"]["status"], "OK" if expected == 0 else "ÉCHEC")
            catalogue.write_text(json.dumps(entries[1:]), encoding="utf-8")
            result = self.run_cli("--filter", "id/dev-filtre-commandes", "--live-catalog", str(catalogue),
                                  "--json", "--report", str(directory / "simule.md"))
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)["drift"]["missing"], [entries[0]["id"]])

    def test_json_sur_erreur_live_et_filtre_vide(self):
        with tempfile.TemporaryDirectory() as directory:
            for args, code, text in ((["--available", "live", "--copilot-cli", str(Path(directory) / "absent")], 4, "Copilot"),
                                     (["--filter", "id/aucun-resultat"], 1, "Aucun cas"),
                                     (["--threshold", "nan"], 1, "threshold")):
                result = self.run_cli(*args, "--json", "--report", str(Path(directory) / "report.md"))
                self.assertEqual(result.returncode, code, result.stderr + result.stdout)
                report = json.loads(result.stdout)
                self.assertFalse(report["passed"])
                self.assertIn(text, " ".join(report["operational_errors"]))

    def test_cli_copilot_exige_modele_et_rejette_modes_concurrents(self):
        for args in (("--copilot",), ("--judge-model", "un-modele"), ("--copilot", "--fake-judge")):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)

    def test_cli_juge_simule_et_code_non_nul_sous_seuil(self):
        with tempfile.TemporaryDirectory() as directory:
            cli = self.cli(directory)
            for threshold, code in (("0.85", 0), ("0.95", 1)):
                result = self.run_cli("--filter", "id/dev-filtre-commandes", "--judge", "--copilot", "--judge-model", "valid",
                                      "--copilot-cli", cli, "--threshold", threshold, "--json", "--report", str(Path(directory) / "report.md"))
                report = json.loads(result.stdout)
                self.assertEqual(result.returncode, code, result.stderr + result.stdout)
                self.assertEqual(report["summary"]["judge"]["mean_score"], 0.9)
                self.assertEqual(report["summary"]["failed"], 0)

    def test_refresh_reutilise_script_et_capture_sortie(self):
        completed = subprocess.CompletedProcess([], 0, "Registre synchronisé\n", "Catalogue indisponible\n")
        with patch.object(ev.subprocess, "run", return_value=completed) as run:
            result = ev.refresh_registry(ROOT / "models.yaml", "copilot-test", 2)
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["bash", str(ROOT / "scripts/refresh.sh"), "--registry", str(ROOT / "models.yaml")])
        self.assertEqual(kwargs["env"]["COPILOT_CLI"], "copilot-test")
        self.assertEqual(kwargs["env"]["PYTHON"], sys.executable)
        self.assertEqual(result["stdout"], "Registre synchronisé")
        with patch.object(ev.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "Erreur")):
            with self.assertRaisesRegex(ValueError, "refresh a échoué"):
                ev.refresh_registry(ROOT / "models.yaml", "copilot-test", 2)

    def test_main_refresh_precede_chargement_et_ne_pollue_pas_json(self):
        order = []

        def refresh(*args):
            order.append("refresh")
            return {"stdout": "OK", "stderr": ""}

        def load(*args):
            order.append("load")
            return self.registry

        with tempfile.TemporaryDirectory() as directory, patch.object(ev, "refresh_registry", side_effect=refresh), \
                patch.object(ev, "load_registry", side_effect=load), contextlib.redirect_stdout(io.StringIO()) as output:
            code = ev.main(["--refresh", "--filter", "id/dev-filtre-commandes", "--json", "--report", str(Path(directory) / "report.md")])
        self.assertEqual(code, 0)
        self.assertEqual(order, ["refresh", "load"])
        self.assertEqual(json.loads(output.getvalue())["refresh"]["stdout"], "OK")


if __name__ == "__main__":
    unittest.main()
