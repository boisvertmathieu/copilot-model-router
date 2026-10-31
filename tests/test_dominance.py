"""US4 : les générations dominées ne gagnent jamais une préférence de niveau."""

import copy
import itertools
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from registry_lib import LEVELS, ROLES, TABLE_FILES, load_registry
from route import TASK_LEVELS, route
from select_model import SelectionError, select_model
from sync_registry import build_registry, load_tables
from test_selection import model


class DominanceTests(unittest.TestCase):
    def test_qa_equal_price_grok_and_opus(self):
        registry = load_registry(ROOT / "models.yaml")
        result = route(registry, role="dev", story="Refactor multi-modules",
                       diff_stats="12 files changed, 340 insertions(+), 80 deletions(-)")
        self.assertEqual(result["model"], "grok-4.7")
        self.assertEqual(select_model(registry, role="dev", level="premium")["id"], "grok-4.7")
        self.assertEqual(select_model(registry, role="planner",
                                      available=["claude-opus-4.8", "claude-opus-5"])["id"], "claude-opus-5")

    def test_same_lineage_successor_overrides_target_at_equal_or_lower_cost(self):
        for cost in (36, 37, 38):
            registry = {"models": [model("grok-4.5", "xai", "standard", 37),
                                   model("grok-4.7", "xai", "premium", cost),
                                   model("fallback", "google", "economy", 1)]}
            for budget in (None, 36, 37, 38):
                expected = ("fallback" if budget is not None and budget < 37 else
                            "grok-4.7" if cost <= 37 else "grok-4.5")
                with self.subTest(cost=cost, budget=budget):
                    result = select_model(registry, role="test", max_cost=budget)
                    self.assertEqual(result["id"], expected)
                    routed = route(registry, role="test", story="Add a filter", max_cost=budget)
                    self.assertEqual(routed["model"], expected)
        actual = load_registry(ROOT / "models.yaml")
        self.assertEqual(select_model(actual, role="test", available=["grok-4.5", "grok-4.7"])["id"],
                         "grok-4.7")

    def test_cross_lineage_target_ceiling_kept_at_equal_price(self):
        standard = model("claude-sonnet-5.5", "anthropic", "standard", 37, capability={"score": 40})
        for premium in (model("claude-opus-5", "anthropic", "premium", 37, capability={"score": 80}),
                        model("grok-4.7", "xai", "premium", 37, capability={"score": 80})):
            for models in ([standard, premium], [premium, standard]):
                with self.subTest(premium=premium["id"], first=models[0]["id"]):
                    registry = {"models": models}
                    self.assertEqual(select_model(registry, role="test")["id"], standard["id"])
                    self.assertEqual(route(registry, role="test", story="Add a filter")["model"], standard["id"])

    def test_synced_equal_price_grok_successor_wins(self):
        tables = load_tables({name: (ROOT / "upstream" / name).read_text(encoding="utf-8")
                              for name in TABLE_FILES})
        new = copy.deepcopy(next(row for row in tables["models-and-pricing.yml"]
                                 if row["model"] == "Grok 4.7"))
        new["model"] = "Grok 4.8"
        tables["models-and-pricing.yml"].append(new)
        tables["model-supported-clients.yml"].append({"name": "Grok 4.8", "cli": True})
        catalog = ["grok-4.7", "grok-4.8"]
        registry, report = build_registry(tables, None, "2026-10-31", cli_payload=catalog)
        successor = next(model for model in registry["models"] if model["id"] == "grok-4.8")
        self.assertEqual(successor["tier"], "premium")
        self.assertTrue(successor["tier_provisoire"])
        self.assertEqual(successor["cost_index"], 37)
        self.assertEqual(report["unmatched_cli"], [])
        self.assertEqual(select_model(registry, role="test", available=catalog)["id"], "grok-4.8")
        self.assertEqual(route(registry, role="dev", available=catalog)["model"], "grok-4.8")

    def test_newer_dominates_all_roles_levels_and_budgets(self):
        tiers = [(older, newer) for older in LEVELS for newer in LEVELS
                 if LEVELS.index(newer) >= LEVELS.index(older)]
        for role, level, (old_tier, new_tier), cost, budget in itertools.product(
                ROLES, LEVELS, tiers, (10, 20), (0, 9.99, 10, 19.99, 20, 100)):
            registry = {"models": [
                model("claude-opus-4.8", "anthropic", old_tier, 20),
                model("claude-opus-5.5", "anthropic", new_tier, cost),
                model("fallback", "google", "economy", 1),
            ]}
            with self.subTest(role=role, level=level, tiers=(old_tier, new_tier), cost=cost, budget=budget):
                try:
                    result = select_model(registry, role=role, preferred_level=level,
                                          max_cost=budget, dev_family="google")
                except SelectionError as exc:
                    self.assertIn(exc.code, (2, 3))
                    self.assertLess(budget, cost)
                else:
                    self.assertNotEqual(result["id"], "claude-opus-4.8")
                    self.assertLessEqual(result["cost_index"], budget)

    def test_router_dominance_respects_role_bounds(self):
        registry = {"models": [model("claude-opus-4.8", "anthropic", "standard", 20),
                               model("claude-opus-5.5", "anthropic", "premium", 20),
                               model("dev-google", "google", "standard", 20, available=False)]}
        for role, level, budget in itertools.product(ROLES, TASK_LEVELS, (20, 100)):
            with self.subTest(role=role, level=level, budget=budget), patch("route.heuristic_classify", return_value={
                    "level": level, "reasons": ["Niveau simulé."], "warnings": [], "signals": {}}):
                result = route(registry, role=role, max_cost=budget, dev_model="dev-google")
                self.assertEqual(result["model"], "claude-opus-4.8" if role == "doc" else "claude-opus-5.5")

    def test_sync_unknown_org_model_auto_tier_then_dominates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "models.yaml"
            catalog = Path(directory) / "catalog.json"
            entries = ["claude-opus-5.5", {"id": "claude-opus-6", "name": "Claude Opus 6", "cost_index": 80}]
            catalog.write_text(json.dumps(entries), encoding="utf-8")
            for _ in range(2):
                synced = subprocess.run([sys.executable, str(ROOT / "scripts/sync_registry.py"),
                                         "--upstream-dir", str(ROOT / "upstream"), "--registry", str(path),
                                         "--from-cli-models", str(catalog), "--json"],
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(synced.returncode, 0, synced.stderr)
                registry = load_registry(path)
                new = next(model for model in registry["models"] if model["id"] == "claude-opus-6")
                self.assertEqual(new["tier"], "frontier")
                self.assertTrue(new["tier_provisoire"])
                for story in ("typo", "Ajouter un filtre", "Refactor", "CVE"):
                    result = route(registry, role="dev", story=story, max_cost=82, available=str(catalog))
                    self.assertEqual(result["model"], "claude-opus-6")


if __name__ == "__main__":
    unittest.main()
