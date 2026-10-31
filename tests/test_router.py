"""Vérifie le routage sans compte Copilot ni lancement Herdr."""

import copy
import json
import os
import selectors
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
from route import CopilotCliClient, FakeClient, heuristic_classify, route
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
                       {"diff_stats": "statistiques brisées"}, {"story_type": "inconnu"}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                heuristic_classify(**params)


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
        name = "dev de utilisateur; echo 'test'"
        before = copy.deepcopy(self.registry)
        result = route(self.registry, role="dev", name=name, pane="%3")
        expected = ["herdr", "agent", "start", name, "--kind", "copilot", "--pane", "%3",
                    "--", "--model", result["model"]]
        self.assertEqual(shlex.split(result["herdr_cmd"]), expected)
        self.assertEqual(result["herdr_argv"], expected)
        self.assertEqual(self.registry, before)
        no_pane = route(self.registry, role="doc")
        self.assertNotIn("--pane", no_pane["herdr_argv"])
        self.assertEqual(no_pane["herdr_argv"][3], "doc")

    def test_fake_llm_et_heuristique_sans_client(self):
        fake = FakeClient("critique\n")
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
        completed = subprocess.CompletedProcess([], 0, "complexe\n", "")
        with patch("route.subprocess.run", return_value=completed) as run:
            result = route(self.registry, role="dev", classifier="llm", copilot_cli="copilot-simule", timeout=2)
        self.assertEqual(result["classifier_model"], "autre-economy")
        self.assertEqual(result["tier"], "premium")
        args, kwargs = run.call_args
        self.assertEqual(args[0][:4], ["copilot-simule", "--model", "autre-economy", "-p"])
        self.assertEqual(kwargs["timeout"], 2)
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


class RouterServerTests(unittest.TestCase):
    def test_plusieurs_requetes_erreurs_et_notifications(self):
        requests = ["{json brisé}",
                    {"jsonrpc": "2.0", "id": 1, "method": "ping"},
                    {"jsonrpc": "2.0", "id": 2, "method": "route", "params": {"role": "doc", "story": "typo", "pane": 1}},
                    {"jsonrpc": "2.0", "id": 3, "method": "route", "params": {"role": "dev", "max_cost": 0}},
                    {"jsonrpc": "2.0", "id": 4, "method": "route", "params": {"role": "e2e-validator"}},
                    {"jsonrpc": "2.0", "id": 5, "method": "inconnue"},
                    {"jsonrpc": "2.0", "id": 6, "method": "route", "params": {"role": "dev", "files": "deux"}},
                    {"jsonrpc": "2.0", "method": "ping"},
                    {"jsonrpc": "2.0", "id": 7, "method": "reload"},
                    {"jsonrpc": "2.0", "id": 8, "method": "route", "params": {"role": "dev", "available": ["gpt-6-luna"]}}]
        content = "\n".join(item if isinstance(item, str) else json.dumps(item) for item in requests) + "\n"
        result = subprocess.run([sys.executable, str(ROOT / "scripts/route.py"), "--serve"],
                                input=content, capture_output=True, text=True, timeout=10, cwd="/tmp")
        self.assertEqual(result.returncode, 0, result.stderr)
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(replies), 9)
        self.assertEqual(replies[0]["error"]["code"], -32700)
        self.assertEqual(replies[1]["result"]["status"], "ok")
        self.assertEqual(replies[2]["result"]["level"], "trivial")
        self.assertEqual(replies[3]["error"]["data"]["exit_code"], 2)
        self.assertEqual(replies[4]["error"]["data"]["exit_code"], 3)
        self.assertEqual(replies[5]["error"]["code"], -32601)
        self.assertEqual(replies[6]["error"]["code"], -32602)
        self.assertEqual(replies[7]["result"]["status"], "rechargé")
        self.assertEqual(replies[8]["result"]["model"], "gpt-6-luna")
        self.assertEqual(result.stderr, "")

    def test_registre_charge_une_fois_reload_et_echec_atomique(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "models.json"
            registry = sample_registry()
            path.write_text(json.dumps(registry), encoding="utf-8")
            process = subprocess.Popen([sys.executable, str(ROOT / "scripts/route.py"), "--serve", "--registry", str(path)],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            def request(method, params=None):
                process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}) + "\n")
                process.stdin.flush()
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    self.assertTrue(selector.select(timeout=5), "Le serveur ne répond pas.")
                return json.loads(process.stdout.readline())
            try:
                first = request("route", {"role": "doc", "story": "typo"})["result"]["model"]
                registry["models"][3]["id"] = "economy-nouveau"
                path.write_text(json.dumps(registry), encoding="utf-8")
                self.assertEqual(request("route", {"role": "doc", "story": "typo"})["result"]["model"], first)
                self.assertIn("result", request("reload"))
                self.assertEqual(request("route", {"role": "doc", "story": "typo"})["result"]["model"], "economy-nouveau")
                path.write_text("{registre brisé", encoding="utf-8")
                self.assertEqual(request("reload")["error"]["data"]["exit_code"], 1)
                self.assertEqual(request("route", {"role": "doc", "story": "typo"})["result"]["model"], "economy-nouveau")
            finally:
                process.stdin.close()
                process.wait(timeout=5)
                process.stdout.close()
                process.stderr.close()

    def test_requetes_invalides_ne_ferment_pas_le_serveur(self):
        requests = [[], {"jsonrpc": "1.0", "method": "ping", "id": 1},
                    {"jsonrpc": "2.0", "id": True, "method": "ping"},
                    {"jsonrpc": "2.0", "id": 2, "method": "route", "params": []},
                    {"jsonrpc": "2.0", "id": 3, "method": "route", "params": {"role": "dev", "surprise": 1}},
                    {"jsonrpc": "2.0", "id": 4, "method": "ping"}]
        result = subprocess.run([sys.executable, str(ROOT / "scripts/route.py"), "--serve"],
                                input="\n".join(map(json.dumps, requests)) + "\n", capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        replies = list(map(json.loads, result.stdout.splitlines()))
        self.assertEqual([item["error"]["code"] for item in replies[:-1]], [-32600, -32600, -32600, -32602, -32602])
        self.assertIn("result", replies[-1])


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
