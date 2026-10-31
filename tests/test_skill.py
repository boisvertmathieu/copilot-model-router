"""Exercise the installed skill wrapper with local CLI binaries and no account."""

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_selection import model

ROOT = Path(__file__).resolve().parents[1]


class HerdrRouteSkillTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.project = self.directory / "calling project"
        self.project.mkdir()
        self.router_home = self.directory / "router checkout"
        self.router_home.symlink_to(ROOT, target_is_directory=True)
        installed = self.directory / "installed skills" / "herdr-model-router"
        shutil.copytree(ROOT / "skills/herdr-model-router", installed)
        self.wrapper = installed / "herdr-model-router.sh"
        self.bin = self.directory / "bin"
        self.bin.mkdir()
        self.herdr_log = self.directory / "herdr.jsonl"
        self.copilot_log = self.directory / "copilot.jsonl"
        self.env = {**os.environ, "COPILOT_MODEL_ROUTER_HOME": str(self.router_home),
                    "COPILOT_HOME": str(self.directory / "copilot-config"),
                    "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
                    "CMR_SKILL_HERDR_LOG": str(self.herdr_log),
                    "CMR_SKILL_COPILOT_LOG": str(self.copilot_log)}
        self.env.setdefault("UV_CACHE_DIR", str(self.directory / "uv-cache"))
        self.registry = self.directory / "registry.json"
        self.catalog = self.directory / "catalog.json"
        self.write_registry("chosen-model")
        self.write_binary("copilot", """
import json, os, sys
with open(os.environ["CMR_SKILL_COPILOT_LOG"], "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
if "--headless" in sys.argv or os.environ.get("CMR_SKILL_FAIL_CLASSIFIER"):
    print("Simulated Copilot failure", file=sys.stderr)
    sys.exit(9)
print(json.dumps({"level": "standard", "reason": "Routine task",
                  "preferred_model": os.environ["CMR_SKILL_PREFERRED"]}))
""")
        self.write_binary("herdr", """
import json, os, sys
with open(os.environ["CMR_SKILL_HERDR_LOG"], "a") as log:
    log.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd()}) + "\\n")
""")

    def write_binary(self, name, source):
        path = self.bin / name
        path.write_text(f"#!{sys.executable}\n" + source, encoding="utf-8")
        path.chmod(0o755)

    def write_registry(self, preferred):
        entries = [model("classifier-model", "openai", "economy", 1),
                   model("cheaper-model", "google", "standard", 5),
                   model(preferred, "anthropic", "standard", 8)]
        self.registry.write_text(json.dumps({"models": entries}), encoding="utf-8")
        self.catalog.write_text(json.dumps([entry["id"] for entry in entries]), encoding="utf-8")
        self.env["CMR_SKILL_PREFERRED"] = preferred

    def run_wrapper(self, *args):
        return subprocess.run(
            ["sh", str(self.wrapper), "--registry", str(self.registry), "--role", "dev",
             "--story", "Add a list filter", "--available", str(self.catalog),
             "--classifier", "llm", "--pane", "3", "--name", "dev-filter", *args],
            cwd=self.project, env=self.env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=20)

    def assert_launch(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        choice = json.loads(result.stdout)
        calls = [json.loads(line) for line in self.herdr_log.read_text().splitlines()]
        self.assertEqual(calls, [{"argv": ["agent", "start", "dev-filter", "--kind", "copilot",
                                           "--pane", "3", "--", "--model", choice["model"]],
                                 "cwd": str(self.project)}])
        self.assertEqual(["herdr", *calls[0]["argv"]], shlex.split(choice["herdr_command"]))
        return choice

    def test_nominal_launch_uses_json_model_and_preserves_command(self):
        result = self.run_wrapper()
        choice = self.assert_launch(result)
        self.assertEqual(choice["decision_source"], "llm")
        self.assertEqual(choice["model"], "chosen-model")
        self.assertNotIn("Heuristic fallback", result.stderr)
        calls = [json.loads(line) for line in self.copilot_log.read_text().splitlines()]
        self.assertEqual(len(calls), 1)
        self.assertIn("--no-ask-user", calls[0])

    def test_command_quoting_is_preserved(self):
        self.write_registry("chosen'model")
        choice = self.assert_launch(self.run_wrapper())
        self.assertEqual(choice["model"], "chosen'model")

    def test_all_router_errors_stop_launch_and_report_code_error_and_action(self):
        cases = [(("--pane", "0"), 1, "Fix input/registry"),
                 (("--max-cost", "0"), 2, "Report the impossible budget"),
                 (("--role", "reviewer"), 3, "Supply the actual dev model/family"),
                 (("--available", "live"), 4, "Restore Copilot login/license/CLI access"),
                 (("--role", "unknown"), 5, "Use a supported role")]
        for args, code, action in cases:
            with self.subTest(code=code):
                result = self.run_wrapper(*args)
                self.assertEqual(result.returncode, code, result.stdout + result.stderr)
                error = json.loads(result.stdout)
                self.assertEqual(error["exit_code"], code)
                notices = [line for line in result.stderr.splitlines() if line.startswith("Router exit")]
                self.assertEqual(len(notices), 1, result.stderr)
                self.assertIn(f"Router exit {code}:", notices[0])
                self.assertIn(json.dumps(error["error"], ensure_ascii=False), notices[0])
                self.assertIn(action, notices[0])
                self.assertFalse(self.herdr_log.exists())

    def test_heuristic_fallback_prints_notice_and_launches(self):
        self.env["CMR_SKILL_FAIL_CLASSIFIER"] = "1"
        result = self.run_wrapper()
        choice = self.assert_launch(result)
        self.assertEqual(choice["decision_source"], "heuristic")
        notices = [line for line in result.stderr.splitlines() if line.startswith("Heuristic fallback:")]
        self.assertEqual(len(notices), 1, result.stderr)

    def test_missing_or_invalid_router_home_launches_nothing(self):
        for home in (None, "", str(self.directory), str(self.directory / "missing")):
            with self.subTest(home=home):
                self.env.pop("COPILOT_MODEL_ROUTER_HOME", None)
                if home is not None:
                    self.env["COPILOT_MODEL_ROUTER_HOME"] = home
                result = self.run_wrapper()
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("COPILOT_MODEL_ROUTER_HOME", result.stderr)
                self.assertIn("scripts/route.py", result.stderr)
                self.assertIn("nothing launched", result.stderr)
                self.assertFalse(self.herdr_log.exists())
                self.assertFalse(self.copilot_log.exists())


if __name__ == "__main__":
    unittest.main()
