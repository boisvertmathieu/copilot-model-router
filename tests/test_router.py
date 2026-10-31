"""Vérifie le routage sans compte Copilot ni lancement Herdr."""

import copy
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from registry_lib import load_registry
from route import CopilotCliClient, FakeClient, heuristic_classify, main, route
from select_model import SelectionError
from test_selection import model


def sample_registry():
    return {"models": [
        model("claude-dev", "anthropic", "premium", 40),
        model("autre-premium", "openai", "premium", 50),
        model("autre-standard", "google", "standard", 20),
        model("autre-economy", "openai", "economy", 2.1),
        model("autre-frontier", "google", "frontier", 150),
    ], "budget_profiles": {"petit": {"level": "economy", "max_cost": 25},
                            "large": {"level": "frontier", "max_cost": 200}}}


def fake_copilot(folder):
    cli = Path(folder) / "copilot-simule"
    cli.write_text(f'#!{sys.executable}\nexec(compile(open({str(ROOT / "tests/fixtures/fake_copilot.py")!r}).read(), "cli-simule", "exec"))\n',
                   encoding="utf-8")
    cli.chmod(0o755)
    return cli


class HeuristicTests(unittest.TestCase):
    def test_quatre_niveaux(self):
        cases = [({"story": "Corriger une typo dans la doc", "files": 1}, "trivial"),
                 ({"story": "Ajouter un filtre", "story_type": "feature"}, "standard"),
                 ({"story": "Refactor multi-modules", "files": 12}, "complexe"),
                 ({"story": "Corriger une faille dans l'auth"}, "critique")]
        for params, expected in cases:
            with self.subTest(params=params):
                result = heuristic_classify(**params)
                self.assertEqual(result["level"], expected)
                self.assertTrue(result["reasons"])

    def test_domaines_sensibles_seuls_insuffisants_et_accents(self):
        for word in ("SÉCURITÉ", "auth", "authentification", "autorisation", "paiement", "migration", "concurrence"):
            with self.subTest(word=word):
                self.assertEqual(heuristic_classify(story=f"Typo dans la doc {word}", files=1)["level"], "trivial")
                self.assertEqual(heuristic_classify(story=word)["level"], "standard")
        self.assertEqual(heuristic_classify(story="Redessiner la mise en page")["level"], "standard")

    def test_vrais_signaux_de_securite_critiques_seuls(self):
        for word in ("faille", "CVE-2026-12345", "VULNÉRABILITÉ", "vulnérabilités", "injection SQL", "vulnerability"):
            with self.subTest(word=word):
                self.assertEqual(heuristic_classify(story=word, files=1)["level"], "critique")

    def test_injection_de_dependances_sans_faux_risque_de_securite(self):
        for text in ("Ajouter l’injection de dépendances", "Configurer des injections de dépendances",
                     "Utiliser dependency injection", "Configurer dependency-injection"):
            with self.subTest(text=text):
                self.assertEqual(heuristic_classify(story=text, files=4)["level"], "standard")
        mixed = "Refactor de l’injection de dépendances et correction d’une injection SQL"
        self.assertEqual(heuristic_classify(story=mixed, files=4)["level"], "critique")

    def test_domaine_plus_risque_ou_type_bug(self):
        for risk in ("production", "rollback", "fuite de données", "perte de données", "data loss", "bug"):
            with self.subTest(risk=risk):
                self.assertEqual(heuristic_classify(story=f"paiement {risk}")["level"], "critique")
                self.assertNotEqual(heuristic_classify(story=risk)["level"], "critique")
        self.assertEqual(heuristic_classify(story="auth", story_type="bug")["level"], "critique")
        self.assertEqual(heuristic_classify(story="auth", story_type="feature")["level"], "standard")
        self.assertEqual(heuristic_classify(story_type="bug")["level"], "standard")

    def test_seuils_critiques_combines_au_domaine(self):
        for files, expected in ((19, "complexe"), (20, "critique")):
            with self.subTest(files=files):
                self.assertEqual(heuristic_classify(story="migration", files=files)["level"], expected)
        for lines, expected in ((999, "complexe"), (1000, "critique")):
            with self.subTest(lines=lines):
                self.assertEqual(heuristic_classify(story="paiement", diff_stats=f"{lines} deletions(-)")["level"], expected)
        self.assertEqual(heuristic_classify(story="Ajouter un filtre", files=20)["level"], "complexe")

    def test_refactor_paiement_du_brief_reste_complexe(self):
        for stats in (None, "14 files changed, 620 insertions(+), 210 deletions(-)"):
            with self.subTest(stats=stats):
                result = heuristic_classify(story="refactor paiement", diff_stats=stats)
                self.assertEqual(result["level"], "complexe")
                self.assertIn("mention seule insuffisante", " ".join(result["reasons"]))

    def test_seuils_de_portee(self):
        for files, expected in ((0, "trivial"), (2, "trivial"), (3, "standard"), (9, "standard"), (10, "complexe")):
            with self.subTest(files=files):
                self.assertEqual(heuristic_classify(files=files)["level"], expected)
        for lines, expected in ((99, "trivial"), (100, "standard"), (499, "standard"), (500, "complexe")):
            with self.subTest(lines=lines):
                stats = f"1 file changed, {lines} insertions(+)"
                self.assertEqual(heuristic_classify(diff_stats=stats)["level"], expected)

    def test_types_et_priorite(self):
        for story_type, expected in (("doc", "trivial"), ("bug", "standard"), ("feature", "standard"),
                                     ("spike", "complexe"), ("refactor", "complexe")):
            self.assertEqual(heuristic_classify(story_type=story_type)["level"], expected)
        self.assertEqual(heuristic_classify(story_type="doc", files=12)["level"], "complexe")
        self.assertEqual(heuristic_classify(story="architecture", files=1)["level"], "complexe")

    def test_diff_singulier_suppressions_et_comptes_differents(self):
        result = heuristic_classify(diff_stats="1 file changed, 1 insertion(+), 500 deletions(-)", files=12)
        self.assertEqual(result["level"], "complexe")
        self.assertEqual(result["signals"]["changed_lines"], 501)
        self.assertEqual(result["signals"]["files"], 12)
        self.assertIn("maximum", " ".join(result["reasons"]))
        partial = heuristic_classify(diff_stats="500 insertions(+)")
        self.assertEqual(partial["level"], "complexe")
        self.assertIsNone(partial["signals"]["files"])
        self.assertIn("nombre de fichiers inconnu", " ".join(partial["reasons"]))

    def test_signaux_invalides(self):
        for params in ({"files": -1}, {"files": True}, {"files": 1.2},
                       {"story_type": "inconnu"}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                heuristic_classify(**params)

    def test_diff_stats_formats(self):
        for stats, files, lines in (
            ("14 files, 620 insertions", 14, 620),
            ("12 files changed, 340 insertions(+), 80 deletions(-)", 12, 420),
            ("1 file changed", 1, 0),
            (" src/a.py | 340 ++++\n src/b.py | 80 ----\n 2 files changed, 340 insertions(+), 80 deletions(-)\n", 2, 420),
        ):
            with self.subTest(stats=stats):
                result = heuristic_classify(diff_stats=stats)
                self.assertEqual(result["signals"]["files"], files)
                self.assertEqual(result["signals"]["changed_lines"], lines)
                self.assertEqual(result["warnings"], [])

    def test_unreadable_diff_ignored(self):
        result = heuristic_classify(story="Ajouter un filtre", diff_stats="statistiques brisées")
        self.assertEqual(result["level"], "standard")
        self.assertIsNone(result["signals"]["changed_lines"])
        self.assertTrue(result["warnings"])


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.registry = sample_registry()

    def test_classe_et_tier_distincts_avec_budget(self):
        result = route(self.registry, role="dev", story="Refactor", max_cost="20")
        self.assertEqual((result["level"], result["requested_tier"], result["tier"]),
                         ("complexe", "premium", "standard"))
        self.assertEqual(result["fallback"], "lower_tier")
        self.assertLessEqual(result["cost_index"], 20)

    def test_profil_impose_le_budget_et_garde_la_classe(self):
        result = route(self.registry, role="dev", story="Refactor", budget_profile="petit")
        self.assertEqual(result["requested_tier"], "premium")
        self.assertEqual(result["tier"], "standard")
        self.assertEqual(result["max_cost"], 25)
        result = route(self.registry, role="dev", story="Ajouter un filtre", budget_profile="large")
        self.assertEqual(result["tier"], "standard")

    def test_doc_plafonnee_meme_en_repli(self):
        result = route(self.registry, role="doc", story="Doc de vulnérabilité de sécurité")
        self.assertEqual((result["level"], result["tier"]), ("critique", "standard"))
        with self.assertRaises(SelectionError):
            route(self.registry, role="doc", available="autre-frontier")

    def test_e2e_minimum_et_exception_triviale(self):
        result = route(self.registry, role="e2e-validator", dev_model="claude-dev")
        self.assertEqual(result["tier"], "premium")
        self.assertEqual(result["family"], "openai")
        trivial = route(self.registry, role="e2e-validator", dev_family="anthropic", files=1)
        self.assertEqual(trivial["tier"], "economy")
        with self.assertRaises(SelectionError) as caught:
            route(self.registry, role="e2e-validator", dev_model="claude-dev", max_cost=25)
        self.assertEqual(caught.exception.code, 2)

    def test_famille_et_budget_non_relaches(self):
        for role in ("e2e-validator", "reviewer"):
            with self.subTest(role=role), self.assertRaises(SelectionError) as caught:
                route(self.registry, role=role, dev_model="claude-dev", available="claude-dev")
            self.assertEqual(caught.exception.code, 3)
        with self.assertRaises(SelectionError) as caught:
            route(self.registry, role="dev", max_cost="2.0999")
        self.assertEqual(caught.exception.code, 2)

    def test_herdr_cmd_quoting_et_options(self):
        name = "dev de l'équipe; echo 'test'"
        before = copy.deepcopy(self.registry)
        result = route(self.registry, role="dev", name=name, pane="%3")
        expected = ["herdr", "agent", "start", name, "--kind", "copilot", "--pane", "%3",
                    "--", "--model", result["model"]]
        self.assertEqual(shlex.split(result["herdr_cmd"]), expected)
        self.assertEqual(result["herdr_argv"], expected)
        self.assertEqual(self.registry, before)
        no_pane = route(self.registry, role="doc")
        self.assertEqual(no_pane["herdr_argv"][6:8], ["--pane", "1"])
        self.assertEqual(no_pane["herdr_argv"][3], "doc")

    def test_fake_llm_et_heuristique_sans_client(self):
        fake = FakeClient('{"level":"critique","reason":"Risque élevé."}\n')
        result = route(self.registry, role="dev", story="Une petite tâche", classifier="llm", client=fake)
        self.assertEqual((result["level"], result["tier"], result["classification"]),
                         ("critique", "frontier", "llm"))
        self.assertIn("Une petite tâche", fake.prompts[0])
        unused = FakeClient(error=AssertionError("Ce client ne doit pas être appelé"))
        result = route(self.registry, role="doc", story="typo", client=unused)
        self.assertEqual(result["level"], "trivial")
        self.assertEqual(unused.prompts, [])

    def test_llm_echec_et_parsing_strict_redonnent_heuristique(self):
        clients = [FakeClient(error=TimeoutError("Délai simulé"))]
        clients += [FakeClient(value) for value in ("", "Critique", "complexe. conseil", '"complexe"', "standard\ntrivial", None)]
        for client in clients:
            with self.subTest(response=client.response):
                result = route(self.registry, role="dev", story="migration en production", classifier="llm", client=client)
                self.assertEqual((result["level"], result["classification"]), ("critique", "heuristic"))
                self.assertIn("repli heuristique", " ".join(result["warnings"]))

    def test_adaptateur_choisit_economy_et_passe_des_arguments(self):
        completed = subprocess.CompletedProcess([], 0, '{"level":"complexe","reason":"Portée étendue."}\n', "")
        with patch("route.subprocess.run", return_value=completed) as run:
            result = route(self.registry, role="dev", classifier="llm", copilot_cli="copilot-simule", timeout=2)
        self.assertEqual(result["classifier_model"], "autre-economy")
        self.assertEqual(result["tier"], "premium")
        args, kwargs = run.call_args
        run.assert_called_once()
        self.assertEqual(args[0][:4], ["copilot-simule", "--model", "autre-economy", "-p"])
        self.assertEqual(kwargs["timeout"], 2)
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        self.assertIn("--allow-all-tools", args[0])
        self.assertNotIn("shell", kwargs)

    def test_adaptateur_refus_delai_cli_absent_et_aucun_economy(self):
        failures = [FileNotFoundError(), subprocess.TimeoutExpired("copilot", 1)]
        for failure in failures:
            with patch("route.subprocess.run", side_effect=failure):
                result = route(self.registry, role="dev", story="architecture", classifier="llm")
            self.assertEqual(result["classification"], "heuristic")
        for code, output in ((1, "complexe"), (0, "Voici : complexe")):
            with patch("route.subprocess.run", return_value=subprocess.CompletedProcess([], code, output, "")):
                result = route(self.registry, role="dev", story="architecture", classifier="llm")
            self.assertEqual(result["classification"], "heuristic")
        with patch("route.subprocess.run") as run:
            result = route(self.registry, role="dev", classifier="llm", available="autre-premium")
        run.assert_not_called()
        self.assertEqual(result["classification"], "heuristic")

    def test_tier_provisoire_accepte_et_signale(self):
        self.registry["models"][3]["tier_provisoire"] = True
        result = route(self.registry, role="doc", story="typo")
        self.assertTrue(result["tier_provisoire"])
        self.assertIn("à valider", result["reason"])
        self.assertIn("provisoire", " ".join(result["warnings"]))


class LlmGuardrailTests(unittest.TestCase):
    def setUp(self):
        self.registry = sample_registry()

    def classify(self, preferred=None, **params):
        response = {"level": "standard", "reason": "Travail courant."}
        if preferred is not None:
            response["preferred_model"] = preferred
        self.client = FakeClient(json.dumps(response))
        return route(self.registry, classifier="llm", client=self.client,
                     **{"role": "dev", **params})

    def assert_rejected(self, result, preferred, reason):
        self.assertNotEqual(result["model"], preferred)
        self.assertEqual(result["decision_source"], "llm")
        self.assertIn(reason, " ".join(result["reasons"]))
        self.assertEqual(len(self.client.prompts), 1)

    def test_llm_prompt_contains_compact_available_models(self):
        result = self.classify(available="autre-economy,autre-standard")
        payload = json.loads(self.client.prompts[0].split("\n", 1)[1])
        self.assertEqual(payload["models"], [
            {"id": "autre-standard", "family": "google", "tier": "standard", "cost": 20},
            {"id": "autre-economy", "family": "openai", "tier": "economy", "cost": 2.1},
        ])
        self.assertEqual(result["classifier_model"], "autre-economy")
        self.assertEqual(result["decision_source"], "llm")

    def test_llm_valid_preference_is_honored(self):
        self.registry["models"].append(model("standard-suggere", "xai", "standard", 25))
        result = self.classify("standard-suggere")
        self.assertEqual(result["model"], "standard-suggere")
        self.assertIn("validée", " ".join(result["reasons"]))

    def test_llm_cross_lineage_ceiling_kept(self):
        self.registry["models"][1]["cost_index"] = 20
        result = self.classify("autre-premium", role="test")
        self.assert_rejected(result, "autre-premium", "plafond de niveau")
        self.assertEqual(result["model"], "autre-standard")

    def test_llm_unknown_preference_rejected(self):
        self.assert_rejected(self.classify("inconnu"), "inconnu", "hors catalogue")

    def test_llm_unavailable_preference_rejected(self):
        result = self.classify("claude-dev", available="autre-standard,autre-economy")
        self.assert_rejected(result, "claude-dev", "indisponible")
        self.assertIn(result["model"], ("autre-standard", "autre-economy"))

    def test_llm_same_dev_family_rejected_for_both_roles(self):
        for role in ("reviewer", "e2e-validator"):
            with self.subTest(role=role):
                result = self.classify("claude-dev", role=role, dev_model="claude-dev")
                self.assert_rejected(result, "claude-dev", "même famille")
                self.assertNotEqual(result["family"], "anthropic")

    def test_llm_over_budget_preference_rejected(self):
        for budget in ({"max_cost": 25}, {"budget_profile": "petit"}):
            with self.subTest(budget=budget):
                result = self.classify("autre-premium", **budget)
                self.assert_rejected(result, "autre-premium", "budget dépassé")
                self.assertLessEqual(result["cost_index"], 25)

    def test_llm_dominated_preference_rejected(self):
        self.registry["models"] += [
            model("claude-opus-4.8", "anthropic", "standard", 30, display_name="Claude Opus 4.8"),
            model("claude-opus-5.5", "anthropic", "premium", 30, display_name="Claude Opus 5.5"),
        ]
        result = self.classify("claude-opus-4.8")
        self.assert_rejected(result, "claude-opus-4.8", "génération dominée")
        self.assertEqual(result["model"], "claude-opus-5.5")

    def test_llm_same_lineage_successor_can_exceed_ceiling(self):
        self.registry["models"] += [model("grok-4.5", "xai", "standard", 30),
                                    model("grok-4.7", "xai", "premium", 30)]
        result = self.classify("grok-4.7", role="test")
        self.assertEqual(result["model"], "grok-4.7")
        self.assertIn("validée", " ".join(result["reasons"]))

    def test_llm_preference_kept_when_successor_violates_constraints(self):
        self.registry["models"] += [
            model("grok-4.5", "xai", "standard", 30),
            model("grok-4.7", "xai", "premium", 30),
        ]
        for fields, params in (({"available": False}, {}),
                               ({"cost_index": 31}, {"max_cost": 30}),
                               ({"runtime": {"policy": {"state": "disabled"}}}, {})):
            registry = copy.deepcopy(self.registry)
            self.registry["models"][-1].update(fields)
            with self.subTest(fields=fields):
                result = self.classify("grok-4.5", **params)
                self.assertEqual(result["model"], "grok-4.5")
                self.assertIn("validée", " ".join(result["reasons"]))
            self.registry = registry

    def test_llm_role_bounds_reject_preference(self):
        for preferred, params in (("autre-frontier", {"role": "doc"}),
                                  ("autre-economy", {"role": "e2e-validator", "dev_model": "claude-dev"})):
            with self.subTest(params=params):
                self.assert_rejected(self.classify(preferred, **params), preferred, "hors bornes")

    def test_llm_nonconforming_json_falls_back(self):
        for response in ("garbage", "standard", "```json\n{}\n```", "[]", "{}",
                         '{"level":"standard"}', '{"level":"unknown","reason":"x"}',
                         '{"level":"standard","reason":" "}',
                         '{"level":"standard","reason":"x","preferred_model":null}',
                         '{"level":"standard","reason":"x","extra":1}',
                         '{"level":"standard","level":"critique","reason":"x"}',
                         '{"level":"standard","reason":NaN}',
                         '{"level":"standard","reason":"x"} trailing'):
            with self.subTest(response=response):
                client = FakeClient(response)
                result = route(self.registry, role="dev", story="Refactor", classifier="llm", client=client)
                self.assertEqual((result["level"], result["decision_source"]), ("complexe", "heuristic"))
                self.assertEqual(len(client.prompts), 1)
                self.assertTrue(result["warnings"])

    def test_llm_failure_and_timeout_fall_back_once(self):
        for error in (RuntimeError("Échec"), TimeoutError(), subprocess.TimeoutExpired("copilot", 30)):
            with self.subTest(error=error):
                client = FakeClient(error=error)
                result = route(self.registry, role="dev", classifier="llm", client=client)
                self.assertEqual(result["decision_source"], "heuristic")
                self.assertTrue(result["warnings"])
                self.assertEqual(len(client.prompts), 1)

    def test_llm_fallback_warns_on_stderr_and_exits_zero(self):
        import contextlib
        import io
        for client in (FakeClient("garbage"), FakeClient(error=TimeoutError()), FakeClient(error=RuntimeError())):
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch("route.load_registry", return_value=self.registry), \
                 patch("route.CopilotCliClient", return_value=client), \
                 contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["--role", "dev", "--classifier", "llm", "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stdout.getvalue())["decision_source"], "heuristic")
            self.assertIn("repli heuristique", stderr.getvalue())


class RouterCliTests(unittest.TestCase):
    def run_route(self, *args, env=None, no_yaml=False):
        return subprocess.run([sys.executable, *(["-S"] if no_yaml else []),
                               str(ROOT / "scripts/route.py"), *args, "--json"],
                              cwd="/tmp", capture_output=True, text=True, timeout=15, env=env)

    def test_codes_budget_et_famille(self):
        for args, expected in ((("--role", "dev", "--max-cost", "0"), 2),
                               (("--role", "e2e-validator", "--dev-model", "claude-sonnet-5.5",
                                 "--available", "claude-sonnet-5.5"), 3)):
            result = self.run_route(*args)
            self.assertEqual(result.returncode, expected, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["exit_code"], expected)
            self.assertNotIn("herdr_cmd", payload)

    def test_cli_errors_are_one_json_object_with_hint(self):
        for args in ((), ("--role", "unknown"), ("--role", "dev", "--files", "abc"),
                     ("--role", "dev", "--files", "-1"), ("--role", "dev", "--timeout", "nan"),
                     ("--role", "dev", "--max-cost", "2", "--budget-profile", "economy"),
                     ("--role", "doc", "--available", ""),
                     ("--role", "doc", "--registry", "/tmp/cmr-missing-registry.yaml"),
                     ("--role", "doc", "--story", "@/tmp/cmr-missing-story.txt")):
            with self.subTest(args=args):
                result = self.run_route(*args)
                self.assertNotEqual(result.returncode, 0)
                payload = json.loads(result.stdout)
                self.assertEqual(set(payload), {"error", "hint", "exit_code", "decision_source"})
                self.assertTrue(payload["hint"])
                self.assertIsNone(payload["decision_source"])
                self.assertEqual(payload["exit_code"], result.returncode)
                self.assertNotIn("Traceback", result.stderr)

    def test_unknown_role_json_exit_5(self):
        result = self.run_route("--role", "unknown", "--story", "x")
        self.assertEqual(result.returncode, 5)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["exit_code"], 5)
        self.assertIn("Rôle inconnu", payload["error"])
        self.assertTrue(payload["hint"])
        self.assertEqual(result.stderr, "")

    def test_default_pane_json_contract(self):
        result = self.run_route("--role", "dev", "--story", "Refactor multi-modules",
                                "--diff-stats", "12 files changed, 340 insertions(+), 80 deletions(-)")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["model"], "grok-4.7")
        self.assertEqual(payload["decision_source"], "heuristic")
        self.assertEqual(payload["herdr_command"],
                         "herdr agent start dev --kind copilot --pane 1 -- --model grok-4.7")

    def test_removed_serve_mode_returns_json_error(self):
        result = self.run_route("--role", "dev", "--serve")
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertIn("--serve", payload["error"])
        self.assertTrue(payload["hint"])

    def test_all_roles_json_contract_and_exact_herdr_command(self):
        with tempfile.TemporaryDirectory() as folder:
            story = Path(folder) / "story.txt"
            story.write_text("Ajouter un filtre", encoding="utf-8")
            for role in ("dev", "test", "doc", "e2e-validator", "reviewer", "planner"):
                args = ["--role", role, "--story", "@" + str(story), "--pane", "3", "--name", role,
                        "--available", "gpt-6-luna,gemini-4-argon,claude-sonnet-5.5"]
                if role in ("reviewer", "e2e-validator"):
                    args += ["--dev-model", "claude-sonnet-5.5"]
                with self.subTest(role=role):
                    result = self.run_route(*args)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    payload = json.loads(result.stdout)
                    self.assertTrue({"model", "tier", "level", "reasons", "decision_source", "herdr_command"} <= payload.keys())
                    self.assertEqual(payload["decision_source"], "heuristic")
                    self.assertTrue(payload["reasons"])
                    self.assertEqual(payload["herdr_command"],
                                     f"herdr agent start {role} --kind copilot --pane 3 -- --model {payload['model']}")

    def test_json_without_flag_and_warnings_on_stderr(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/route.py"), "--role", "doc"],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0)
        self.assertIn("model", json.loads(result.stdout))
        self.assertIn("Avertissement", result.stderr)

    def test_unreadable_diff_warns_and_continues(self):
        for stats in ("statistiques brisées", "@/tmp/cmr-missing-diff.txt"):
            with self.subTest(stats=stats):
                result = self.run_route("--role", "dev", "--story", "Ajouter un filtre", "--diff-stats", stats)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(json.loads(result.stdout)["level"], "standard")
                self.assertIn("diff illisibles", result.stderr)

    def test_short_diff_summary_and_unreadable_file(self):
        result = self.run_route("--role", "dev", "--diff-stats", "14 files, 620 insertions")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual((payload["level"], payload["signals"]["files"], payload["signals"]["changed_lines"]),
                         ("complexe", 14, 620))
        with tempfile.TemporaryDirectory() as folder:
            stats = Path(folder) / "diff.txt"
            stats.write_bytes(b"\xff\xfe")
            result = self.run_route("--role", "dev", "--diff-stats", "@" + str(stats))
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("diff illisibles", result.stderr)
            self.assertEqual(json.loads(result.stdout)["level"], "standard")

    def test_malformed_runtime_is_json_error(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "registry.json"
            registry = sample_registry()
            for runtime in ([], "invalid", {"policy": []}, {"capabilities": "chat"}):
                registry["models"][0]["runtime"] = runtime
                path.write_text(json.dumps(registry), encoding="utf-8")
                with self.subTest(runtime=runtime):
                    result = self.run_route("--role", "doc", "--registry", str(path))
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("hint", json.loads(result.stdout))
                    self.assertNotIn("Traceback", result.stderr)

    def test_story_et_diff_en_fichiers(self):
        with tempfile.TemporaryDirectory() as folder:
            story = Path(folder) / "récit de tâche.txt"
            stats = Path(folder) / "diff.txt"
            story.write_text("Refactor multi-modules", encoding="utf-8")
            stats.write_text("12 files changed, 340 insertions(+), 80 deletions(-)\n", encoding="utf-8")
            for stats_arg in (str(stats), "@" + str(stats)):
                result = self.run_route("--role", "dev", "--story", "@" + str(story), "--diff-stats", stats_arg)
                self.assertEqual(result.returncode, 0, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual((payload["level"], payload["tier"]), ("complexe", "premium"))
                self.assertEqual(payload["signals"]["changed_lines"], 420)

    def test_sans_pyyaml_et_depuis_autre_dossier(self):
        normal = self.run_route("--role", "doc", "--story-type", "doc")
        fallback = self.run_route("--role", "doc", "--story-type", "doc", no_yaml=True)
        self.assertEqual(fallback.returncode, 0, fallback.stderr)
        self.assertEqual(json.loads(normal.stdout), json.loads(fallback.stdout))

    def test_available_fichier_et_liste(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "catalogue.json"
            path.write_text(json.dumps(["gpt-6-luna"]), encoding="utf-8")
            for value in (str(path), "@" + str(path), "gpt-6-luna,claude-sonnet-5.5"):
                result = self.run_route("--role", "doc", "--story", "typo", "--available", value)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["model"], "gpt-6-luna")

    def test_live_simule_et_echec_code_4(self):
        with tempfile.TemporaryDirectory() as folder:
            cli = fake_copilot(folder)
            for mode, expected in (("success", 0), ("no_license", 4)):
                result = self.run_route("--role", "dev", "--available", "live", "--copilot-cli", str(cli),
                                        env={**os.environ, "CMR_FAKE_MODE": mode})
                self.assertEqual(result.returncode, expected, result.stderr)
                payload = json.loads(result.stdout)
                if expected == 0:
                    self.assertEqual(payload["model"], "gpt-6-sol")
                    self.assertTrue(payload["available"])
                else:
                    self.assertEqual(payload["exit_code"], 4)


class RefreshTests(unittest.TestCase):
    def test_refresh_absent_echec_et_succes_catalogue(self):
        with tempfile.TemporaryDirectory() as folder:
            cli = fake_copilot(folder)
            for mode in ("absent", "no_license", "success"):
                path = Path(folder) / f"{mode}.yaml"
                executable = str(Path(folder) / "absent") if mode == "absent" else str(cli)
                result = subprocess.run(["bash", str(ROOT / "scripts/refresh.sh"),
                                         "--upstream-dir", str(ROOT / "upstream"), "--registry", str(path), "--json"],
                                        env={**os.environ, "COPILOT_CLI": executable, "CMR_FAKE_MODE": mode, "PYTHON": sys.executable},
                                        capture_output=True, text=True, timeout=15, cwd="/tmp")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["mode"], "local")
                registry = load_registry(path)
                selected = next(item for item in registry["models"] if item["id"] == "gpt-6-sol")
                self.assertIs(selected["available"], True if mode == "success" else None)


if __name__ == "__main__":
    unittest.main()
