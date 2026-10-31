"""Teste la découverte avec un CLI simulé, sans authentification externe."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ListingTests(unittest.TestCase):
    def run_listing(self, mode, *args):
        with tempfile.TemporaryDirectory() as folder:
            # Le lanceur permet d'utiliser le même interpréteur Python que les tests.
            cli = Path(folder) / "copilot-simule"
            cli.write_text(f'#!{sys.executable}\nexec(compile(open({str(ROOT / "tests/fixtures/fake_copilot.py")!r}).read(), "cli-simule", "exec"))\n')
            cli.chmod(0o755)
            log = Path(folder) / "requêtes.txt"
            output = Path(folder) / "catalogue.json"
            output.write_text('{"ancien": true}', encoding="utf-8")
            result = subprocess.run([sys.executable, str(ROOT / "scripts/list_copilot_models.py"),
                                     "--cli", str(cli), "--timeout", "0.3", "--output", str(output), *args],
                                    env={**os.environ, "CMR_FAKE_MODE": mode, "CMR_FAKE_LOG": str(log)},
                                    capture_output=True, text=True, timeout=10)
            return result, json.loads(output.read_text()), log.read_text() if log.exists() else ""

    def test_rpc_et_notifications(self):
        result, output, log = self.run_listing("success")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output["models"][0]["id"], "gpt-6-sol")
        self.assertEqual(output["source"], "models.list")
        self.assertNotIn("session.create", log)

    def test_non_authentifie_ne_demande_pas_la_liste(self):
        result, output, log = self.run_listing("unauthenticated")
        self.assertEqual(result.returncode, 4)
        self.assertIn("copilot login", result.stderr)
        self.assertNotIn("models.list", log)
        self.assertEqual(output, {"ancien": True})

    def test_compte_sans_modeles_message_licence(self):
        result, output, _ = self.run_listing("no_license")
        self.assertEqual(result.returncode, 4)
        self.assertIn("licence", result.stderr)
        self.assertEqual(output, {"ancien": True})

    def test_ancien_protocole_et_repli_ping(self):
        result, output, log = self.run_listing("legacy")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output["protocol_version"], 2)
        self.assertIn("ping", log)

    def test_delai_et_protocole_futur(self):
        for mode in ("timeout", "future"):
            result, output, _ = self.run_listing(mode)
            self.assertEqual(result.returncode, 4)
            self.assertEqual(output, {"ancien": True})

    def test_catalogue_integre_ne_demande_pas_auth_ou_api(self):
        result, output, log = self.run_listing("unauthenticated", "--built-in")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output["source"], "models.getBuiltInCatalog")
        self.assertNotIn("auth.getStatus", log)
        self.assertNotIn("models.list", log)


if __name__ == "__main__":
    unittest.main()
