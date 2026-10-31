#!/usr/bin/env python3
"""Synchronise les tables officielles sans écraser les réglages manuels."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from registry_lib import (
    ROOT, TABLE_FILES, TABLE_BASE, REFERENCE_TASK, ROLE_LEVELS,
    CAPABILITY_POLICY, assign_model_tiers, catalog_entries, clean_name, decimal_number, dump_json,
    entry_selectable, load_registry, matching_entries, model_lineage, name_key, probable_id,
    reference_cost, write_atomic,
)


def load_tables(contents: dict[str, str]) -> dict[str, list[dict]]:
    try:
        import yaml
    except ImportError as exc:
        raise ValueError("La synchronisation exige PyYAML : lancer uv sync.") from exc
    tables = {}
    for filename in TABLE_FILES:
        try:
            data = yaml.safe_load(contents[filename])
        except yaml.YAMLError as exc:
            raise ValueError(f"YAML officiel invalide : {filename}.") from exc
        if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
            raise ValueError(f"Table officielle invalide : {filename}.")
        tables[filename] = data
    return tables


def money(value, *, optional=False):
    if optional and (value is None or value == "Not applicable"):
        return None
    # Une valeur absente n'est jamais interprétée comme un prix nul.
    return float(decimal_number(str(value).removeprefix("$"), "Prix officiel"))


def capabilities_from_comparison(comparison: dict) -> list[str]:
    """Tags de tâches éditoriaux; aucune capacité technique n'est inventée."""
    area = " ".join(str(comparison.get(field, "")) for field in ("task_area", "excels_at")).casefold()
    tags = ["code"]
    if "agent" in area or "autonomous" in area:
        tags.append("agentique")
    if "reasoning" in area or "debugging" in area or "complex" in area:
        tags.append("raisonnement")
    if "fast" in area or "simple" in area or "repetitive" in area:
        tags.append("taches_simples")
    if "writing" in area or "knowledge" in area:
        tags.append("redaction")
    if "long-context" in area or "large" in area:
        tags.append("contexte_long")
    return tags


def context_from_metadata(rows: list[dict], comparison: dict, client: dict) -> dict:
    """Lit les limites explicites et les paliers; un seuil tarifaire n'est pas une fenêtre."""
    context = {}
    for row in [*rows, comparison, client]:
        for field in ("context_window", "context_window_tokens", "max_context_tokens"):
            value = row.get(field)
            if value is not None:
                match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([kKmM]?)\s*", str(value))
                if match:
                    tokens = int(float(match[1]) * {"": 1, "k": 1000, "m": 1_000_000}[match[2].lower()])
                    context["window_tokens"] = max(tokens, context.get("window_tokens", 0))
        if row.get("tier", "Default") == "Default":
            match = re.fullmatch(r"\s*(?:≤|<=)\s*(\d+(?:\.\d+)?)\s*([kKmM]?)\s*",
                                 str(row.get("threshold", "")))
            if match:
                context["default_limit_tokens"] = int(float(match[1]) * {"": 1, "k": 1000, "m": 1_000_000}[match[2].lower()])
        if row.get("tier", "").casefold() == "long context":
            context["long_context_tier"] = True
    return context


def build_registry(tables: dict, previous: dict | None, date: str,
                   cli_payload=None, mode="local") -> tuple[dict, dict]:
    previous = previous or {}
    entries = catalog_entries(cli_payload) if cli_payload is not None else None
    result = copy.deepcopy(previous)
    result.pop("_yaml_sha256", None)
    result["schema_version"] = 1
    result["updated_on"] = date
    result["reference_task"] = copy.deepcopy(REFERENCE_TASK)
    result.setdefault("role_defaults", copy.deepcopy(ROLE_LEVELS))
    result.setdefault("budget_profiles", {
        "economy": {"level": "economy", "max_cost": 5, "description": "Petites tâches, plafond de 5 crédits."},
        "standard": {"level": "standard", "max_cost": 35, "description": "Travail courant, plafond de 35 crédits."},
        "premium": {"level": "premium", "max_cost": 100, "description": "Développement soutenu, plafond de 100 crédits."},
        "frontier": {"level": "frontier", "max_cost": 250, "description": "Tâches exigeantes, plafond de 250 crédits."},
    })
    result.setdefault("policy", {}).pop("frontier_min_cost_index", None)
    result["policy"].update(copy.deepcopy(CAPABILITY_POLICY))
    clients = {name_key(row["name"]): row for row in tables["model-supported-clients.yml"]}
    comparisons = {name_key(row["name"]): row for row in tables["model-comparison.yml"]}
    legacy = {name_key(row["model"]): money(row["new_multiplier"])
              for row in tables["annual-subscriber-model-multipliers.yml"]}
    old = {name_key(row["display_name"]): row for row in previous.get("models", [])}
    default_rows = {}
    pricing_rows = {}
    for row in tables["models-and-pricing.yml"]:
        key = name_key(row["model"])
        pricing_rows.setdefault(key, []).append(row)
        if row.get("tier", "Default") != "Default":
            continue
        if key in default_rows:
            raise ValueError(f"Plusieurs tarifs Default pour {row['model']}.")
        default_rows[key] = row
    report = {"new": [], "removed": [], "provisional": [], "excluded_non_cli": [], "unmatched_cli": [],
              "pricing_missing": [], "ambiguous_cli": [], "id_changes": []}
    models = []
    current_keys = set()
    for key, row in default_rows.items():
        name = clean_name(row["model"])
        candidate = old.get(key, {"id": probable_id(name), "display_name": name})
        if clients.get(key, {}).get("cli") is not True and not (
                entries is not None and matching_entries(candidate, entries)):
            report["excluded_non_cli"].append(clean_name(row["model"]))
            continue
        current_keys.add(key)
        model = copy.deepcopy(old.get(key, {}))
        prices = {field: money(row[field]) for field in ("input", "output", "cached_input")}
        prices["cache_write"] = money(row.get("cache_write"), optional=True)
        cost = reference_cost(prices)
        comparison = comparisons.get(key, {})
        model.setdefault("id", probable_id(name))
        model.setdefault("id_verified", False)
        model.setdefault("id_source", "SUPPOSÉ : slug dérivé du nom officiel; à confirmer avec models.list.")
        model.setdefault("aliases", [])
        model.setdefault("available", None)
        if model.get("retired"):
            model["available"] = None
            model.pop("available_source", None)
            model.pop("retired_on", None)
        model.update({
            "display_name": name, "family": row["provider"], "cli": True, "retired": False,
            "release_status": row["release_status"],
            # Le statut brut est conservé; le nom peut annoncer un aperçu malgré GA.
            "preview": row["release_status"] != "GA" or "preview" in name.casefold(),
            "github_category": row["category"],
            "github_comparison": {field: comparison[field] for field in ("task_area", "excels_at") if field in comparison},
            "github_context": context_from_metadata(pricing_rows[key], comparison, clients.get(key, {})),
            "pricing": {"currency": "USD", "per_tokens": 1_000_000,
                        "tier": "Default", "threshold": row.get("threshold", "Not applicable"),
                        **prices},
            "cost_index": cost,
            "pricing_missing": False,
            "legacy_multiplier": legacy.get(key),
            "capabilities": sorted(set(capabilities_from_comparison(comparison)
                                       + model.get("manual_capabilities", []))),
            "capabilities_source": "Tags éditoriaux dérivés de model-comparison.yml, pas un test de capacités.",
            "source": {"date": date, "mode": mode, "pricing": TABLE_BASE + TABLE_FILES[0],
                       "clients": TABLE_BASE + TABLE_FILES[1],
                       "comparison": TABLE_BASE + TABLE_FILES[2],
                       "legacy": TABLE_BASE + TABLE_FILES[3]},
        })
        if key not in old:
            report["new"].append(name)
        models.append(model)
    for key, old_model in old.items():
        if key not in current_keys:
            model = copy.deepcopy(old_model)
            if entries is not None and matching_entries(model, entries):
                model.update(retired=False, cli=True)
            else:
                if not model.get("retired"):
                    report["removed"].append(model["display_name"])
                model.update(retired=True, cli=False, available=False)
                model["retired_on"] = model.get("retired_on", date)
            model.setdefault("github_comparison", {field: comparisons.get(key, {})[field]
                             for field in ("task_area", "excels_at") if field in comparisons.get(key, {})})
            models.append(model)
    if entries is not None:
        for entry in entries:
            if any(matching_entries(model, [entry]) for model in models):
                continue
            # Un ID arrivé avant la documentation reçoit tout de même un niveau.
            # Aucun tarif n'est inventé : sans coût connu, il reste non sélectionnable.
            name = entry.get("name") or entry["id"]
            family = entry.get("family") or entry.get("provider")
            if not isinstance(family, str) or not family:
                family = next((family for family in {m["family"] for m in models}
                               if model_lineage(family, name) or model_lineage(family, entry["id"])), "unknown")
            lineage = model_lineage(family, name) or model_lineage(family, entry["id"])
            peers = [model for model in models if model["family"] == family and lineage
                     and (model_lineage(family, model["display_name"]) or (None,))[0] == lineage[0]]
            category = entry.get("category") or (peers[-1]["github_category"] if peers else "Lightweight")
            prices = entry.get("pricing")
            cost = (float(decimal_number(entry["cost_index"])) if entry.get("cost_index") is not None
                    else reference_cost(prices) if isinstance(prices, dict) else None)
            model = {"id": entry["id"], "display_name": name, "family": family,
                     "aliases": [], "cli": True, "retired": False, "id_verified": True,
                     "id_source": "Catalogue importé; métadonnées GitHub absentes.",
                     "available": entry_selectable(entry), "preview": bool(entry.get("preview")),
                     "release_status": "Preview" if entry.get("preview") else "GA",
                     "github_category": category, "github_comparison": {},
                     "cost_index": cost, "pricing_missing": cost is None,
                     "source": {"date": date, "mode": "catalogue_importe"}}
            if prices is not None:
                model["pricing"] = prices
            models.append(model)
            report["new"].append(name)
    assign_model_tiers(models)
    report["provisional"] = [model["display_name"] for model in models
                             if model["tier_provisoire"] and not model.get("retired")]
    if cli_payload is not None:
        used = set()
        for model in models:
            matches = matching_entries(model, entries)
            if len(matches) > 1:
                report["ambiguous_cli"].append(model["display_name"])
            # En cas d'ambiguïté, on demande une correspondance manuelle d'ID.
            entry = matches[0] if len(matches) == 1 else None
            model["available"] = bool(entry and entry_selectable(entry))
            model["available_source"] = {"date": date, "method": "catalogue_importe",
                                         "catalog_source": cli_payload.get("source") if isinstance(cli_payload, dict) else None}
            if entry:
                model.update(cli=True, retired=False)
                if model.get("source", {}).get("mode") == "catalogue_importe":
                    if entry.get("cost_index") is not None:
                        model["cost_index"] = float(decimal_number(entry["cost_index"]))
                    elif isinstance(entry.get("pricing"), dict):
                        model["pricing"] = entry["pricing"]
                        model["cost_index"] = reference_cost(entry["pricing"])
                    model["pricing_missing"] = model.get("cost_index") is None
                used.add(entry["id"])
                if model.get("cost_index") is None:
                    report["pricing_missing"].append(entry["id"])
                if model["id"] != entry["id"]:
                    report["id_changes"].append({"old": model["id"], "new": entry["id"]})
                    model["aliases"] = sorted(set(model["aliases"] + [model["id"]]))
                    model["id"] = entry["id"]
                model["id_verified"] = True
                model["id_source"] = "VÉRIFIÉ : identifiant observé dans le catalogue importé, pas une inférence exécutée."
                model["runtime"] = {key: entry[key] for key in (
                    "vendor", "policy", "capabilities", "billing", "preview",
                    "model_picker_enabled", "supportedReasoningEfforts", "defaultReasoningEffort",
                ) if key in entry}
        report["unmatched_cli"] = sorted(entry["id"] for entry in entries if entry["id"] not in used)
    ids = [m["id"] for m in models]
    if len(ids) != len(set(ids)):
        raise ValueError("Le rapprochement produit des ID en double; corrigez les correspondances manuelles.")
    result["models"] = sorted(models, key=lambda m: (m["family"], m["display_name"].casefold()))
    return result, report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=ROOT / "models.yaml", help="Registre YAML à mettre à jour.")
    parser.add_argument("--upstream-dir", type=Path, help="Lire les quatre tables locales, sans réseau.")
    parser.add_argument("--snapshot-dir", type=Path, default=ROOT / "upstream", help="Copies des téléchargements officiels.")
    parser.add_argument("--from-cli-models", type=Path, help="Catalogue JSON réel de models.list ou de l'API.")
    parser.add_argument("--timeout", type=float, default=30, help="Délai réseau maximal par fichier, en secondes.")
    parser.add_argument("--json", action="store_true", help="Produire le rapport en JSON.")
    args = parser.parse_args(argv)
    try:
        if args.timeout <= 0 or not args.timeout < float("inf"):
            raise ValueError("Le délai doit être fini et supérieur à zéro.")
        if args.registry.suffix not in (".yaml", ".yml"):
            raise ValueError("--registry doit désigner un fichier YAML.")
        contents = {}
        for filename in TABLE_FILES:
            if args.upstream_dir:
                contents[filename] = (args.upstream_dir / filename).read_text(encoding="utf-8")
            else:
                request = Request(TABLE_BASE + filename, headers={"User-Agent": "cmr-registry/1", "Accept": "text/plain"})
                with urlopen(request, timeout=args.timeout) as response:
                    data = response.read(5_000_001)
                if len(data) > 5_000_000:
                    raise ValueError(f"Table officielle anormalement volumineuse : {filename}.")
                contents[filename] = data.decode("utf-8")
        tables = load_tables(contents)
        previous = load_registry(args.registry) if args.registry.exists() else None
        cli_payload = json.loads(args.from_cli_models.read_text(encoding="utf-8")) if args.from_cli_models else None
        now = datetime.now(timezone.utc)
        registry, report = build_registry(tables, previous, now.date().isoformat(), cli_payload,
                                           mode="local" if args.upstream_dir else "network")
        registry["sync"] = {
            "checked_at": now.isoformat(),
            "mode": "local" if args.upstream_dir else "network",
            "files": {name: {"url": TABLE_BASE + name, "sha256": hashlib.sha256(text.encode()).hexdigest()}
                      for name, text in contents.items()},
        }
        import yaml
        yaml_text = "# Registre généré; réglages manuels : voir docs/router.md.\n" + yaml.safe_dump(
            registry, allow_unicode=True, sort_keys=False, width=110)
        json_registry = {**registry, "_yaml_sha256": hashlib.sha256(yaml_text.encode()).hexdigest()}
        json_text = dump_json(json_registry)
        # Tous les téléchargements et rapprochements sont validés avant la première écriture.
        write_atomic(args.registry, yaml_text)
        write_atomic(args.registry.with_suffix(".json"), json_text)
        if not args.upstream_dir:
            for filename, content in contents.items():
                write_atomic(args.snapshot_dir / filename, content)
        report.update(models=len(registry["models"]), mode=registry["sync"]["mode"], checked_at=now.isoformat())
        if args.json:
            print(dump_json(report), end="")
        else:
            print(f"Registre synchronisé : {len(registry['models'])} modèles; source {report['mode']}.")
            for key, label in (("new", "Nouveaux"), ("removed", "Retirés du CLI"),
                               ("provisional", "Niveaux provisoires, à valider"),
                               ("excluded_non_cli", "Exclus, sans support CLI documenté"),
                               ("unmatched_cli", "ID importés sans correspondance unique"),
                               ("pricing_missing", "ID importés sans coût connu, exclus du routage"),
                               ("ambiguous_cli", "Correspondances ambiguës")):
                print(f"{label} : {', '.join(report[key]) or 'aucun'}.")
            if report["id_changes"]:
                print(f"Identifiants corrigés : {len(report['id_changes'])}.")
        return 0
    except (OSError, URLError, ValueError, KeyError, TypeError) as exc:
        print(f"Synchronisation impossible : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
