"""Outils communs du registre; aucune requête d'inférence n'est envoyée."""

from __future__ import annotations

import hashlib
import json
import math
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LEVELS = ("economy", "standard", "premium", "frontier")
ROLES = ("dev", "test", "doc", "e2e-validator", "reviewer", "planner")
ROLE_LEVELS = {
    "dev": "premium", "test": "standard", "doc": "economy",
    "e2e-validator": "premium", "reviewer": "premium", "planner": "frontier",
}
REFERENCE_TASK = {
    "input_tokens": 200_000,
    "output_tokens": 20_000,
    "cached_input_ratio": 0.5,
    "usd_per_credit": 0.01,
    "pricing_tier": "Default",
    "cache_write_tokens": 0,
    "description": (
        "Total sur plusieurs appels au tarif Default : 100 000 jetons d'entrée "
        "ordinaires, 100 000 déjà en cache, 20 000 de sortie; aucune création de cache."
    ),
}
TABLE_FILES = (
    "models-and-pricing.yml", "model-supported-clients.yml",
    "model-comparison.yml", "annual-subscriber-model-multipliers.yml",
)
TABLE_BASE = "https://raw.githubusercontent.com/github/docs/main/data/tables/copilot/"
CAPABILITY_POLICY = {
    "scoring_version": 1,
    "category_scores": {"Lightweight": 10, "Versatile": 35, "Powerful": 65},
    "tier_thresholds": {"economy": 0, "standard": 30, "premium": 60, "frontier": 85},
    "weights": {"deep_reasoning": 18, "complex": 10, "long_horizon": 12,
                "validation": 6, "simple_or_fast": -8, "context_200k": 2,
                "long_context_tier": 2, "ga": 2, "preview": -2,
                "generation_step": 4, "generation_max": 12},
    "description": (
        "Score de métadonnées GitHub, pas des benchmarks; aucun prix dans le niveau. "
        "Catégorie seule si le comparatif ou la lignée manque; monotonie par lignée "
        "après scoring, puis coût minimal dans le meilleur niveau admissible."
    ),
}


def decimal_number(value: Any, label: str = "Valeur") -> Decimal:
    """Refuse les nombres non finis et négatifs, même dans des fichiers modifiés."""
    try:
        if isinstance(value, bool):
            raise ValueError
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or not math.isfinite(float(result)):
            raise ValueError
        return result
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{label} doit être un nombre fini, positif ou nul.") from exc


def clean_name(name: str) -> str:
    """Enlève seulement les notes Markdown et les espaces superflus."""
    return re.sub(r"\s+", " ", re.sub(r"\[\^[^\]]+\]", "", name)).strip()


def name_key(name: str) -> str:
    return clean_name(name).casefold()


def probable_id(name: str) -> str:
    """Produit une hypothèse d'identifiant, jamais une preuve de disponibilité."""
    name = clean_name(name).casefold().replace("(fast mode)", "fast")
    name = name.replace("(preview)", "")
    return re.sub(r"[^a-z0-9.]+", "-", name).strip("-")


def load_registry(path: Path) -> dict:
    """Le JSON de secours doit correspondre exactement au YAML courant."""
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        try:
            import yaml
        except ImportError:
            fallback = path.with_suffix(".json")
            if not fallback.is_file():
                raise ValueError("PyYAML est absent et le registre JSON de secours est introuvable.")
            data = json.loads(fallback.read_text(encoding="utf-8"))
            digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
            if digest and data.get("_yaml_sha256") != digest:
                raise ValueError("Le JSON de secours est périmé. Régénérez-le avec sync_registry.py.")
        else:
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
            except yaml.YAMLError as exc:
                raise ValueError("Le registre YAML est invalide.") from exc
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        raise ValueError("Le registre doit contenir une liste « models ».")
    ids = set()
    for model in data["models"]:
        if not isinstance(model, dict) or not isinstance(model.get("id"), str) or not model["id"]:
            raise ValueError("Chaque modèle doit avoir un identifiant non vide.")
        if model["id"] in ids:
            raise ValueError(f"Identifiant en double : {model['id']}.")
        ids.add(model["id"])
        if model.get("tier") not in LEVELS:
            raise ValueError(f"Niveau invalide pour {model['id']}.")
        if "tier_override" in model and model["tier_override"] not in LEVELS:
            raise ValueError(f"tier_override invalide pour {model['id']}.")
        if not isinstance(model.get("family"), str) or not model["family"]:
            raise ValueError(f"Famille manquante pour {model['id']}.")
        if not (model.get("cost_index") is None and model.get("pricing_missing") is True):
            decimal_number(model.get("cost_index"), f"Coût de {model['id']}")
        entry_selectable(model.get("runtime"))
    return data


def catalog_entries(payload: Any) -> list[dict]:
    """Accepte SDK, RPC, API HTTP et listes d'identifiants explicites."""
    if isinstance(payload, dict):
        if payload.get("source") == "models.getBuiltInCatalog":
            raise ValueError("Le catalogue intégré ne prouve aucun accès au compte. Utilisez models.list.")
        if "error" in payload:
            raise ValueError("Le fichier contient une erreur, pas un catalogue de modèles.")
        if "result" in payload:
            return catalog_entries(payload["result"])
        if "models" in payload:
            return catalog_entries(payload["models"])
        if "data" in payload:
            return catalog_entries(payload["data"])
        raise ValueError("Format de catalogue inconnu : liste, models, data ou result attendu.")
    if not isinstance(payload, list):
        raise ValueError("Le catalogue doit contenir une liste.")
    result = []
    seen = set()
    for item in payload:
        entry = {"id": item} if isinstance(item, str) else item
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"].strip():
            raise ValueError("Chaque entrée de catalogue doit avoir un identifiant texte non vide.")
        if any(character.isspace() for character in entry["id"]):
            raise ValueError("Un identifiant de catalogue ne peut pas contenir d'espace.")
        for field in ("policy", "capabilities", "billing"):
            if entry.get(field) is not None and not isinstance(entry[field], dict):
                raise ValueError(f"Le champ de catalogue {field} doit être un objet.")
        if entry.get("name") is not None and not isinstance(entry["name"], str):
            raise ValueError("Le nom d'un modèle doit être du texte.")
        if entry["id"] in seen:
            raise ValueError(f"Identifiant de catalogue en double : {entry['id']}.")
        seen.add(entry["id"])
        result.append(entry)
    return result


def entry_selectable(entry: dict | None) -> bool:
    """Une interdiction explicite du catalogue n'est jamais ignorée."""
    if entry is None:
        entry = {}
    if not isinstance(entry, dict):
        raise ValueError("Les métadonnées runtime doivent être un objet.")
    policy = entry.get("policy")
    capabilities = entry.get("capabilities")
    policy = {} if policy is None else policy
    capabilities = {} if capabilities is None else capabilities
    if not isinstance(policy, dict) or not isinstance(capabilities, dict):
        raise ValueError("Politique ou capacités de modèle invalides.")
    return (
        entry.get("available") is not False
        and policy.get("state", "enabled") == "enabled"
        and entry.get("model_picker_enabled") is not False
        and capabilities.get("type", "chat") == "chat"
    )


def dominates(newer: dict, older: dict) -> bool:
    """Une génération plus récente, au moins aussi capable, à coût égal ou moindre."""
    if newer["family"] != older["family"]:
        return False
    new_lineage = model_lineage(newer["family"], newer["display_name"])
    old_lineage = model_lineage(older["family"], older["display_name"])
    return bool(new_lineage and old_lineage
                and new_lineage[0] == old_lineage[0] and new_lineage[1] > old_lineage[1]
                and LEVELS.index(newer["tier"]) >= LEVELS.index(older["tier"])
                and decimal_number(newer["cost_index"]) <= decimal_number(older["cost_index"]))


def read_available(value: str) -> list[dict]:
    """Un chemin peut être préfixé par @; sinon, accepte des ID séparés par virgule."""
    path = Path(value.removeprefix("@"))
    try:
        is_file = path.is_file()
    except OSError:
        # Une longue liste d'ID n'est pas nécessairement un nom de fichier valide.
        is_file = False
    if is_file:
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            return []
        if content.startswith(("[", "{")):
            return catalog_entries(json.loads(content))
        return catalog_entries(content.replace(",", " ").split())
    if value.lstrip().startswith(("[", "{")):
        return catalog_entries(json.loads(value))
    if value.startswith("@") or "/" in value or value.endswith((".json", ".txt", ".yaml", ".yml")):
        raise ValueError(f"Fichier de disponibilité introuvable : {value}.")
    return catalog_entries(value.replace(",", " ").split())


def matching_entries(model: dict, entries: list[dict]) -> list[dict]:
    """Privilégie l'ID exact; un nom ne suffit que s'il est non ambigu."""
    ids = {model["id"], *model.get("aliases", [])}
    exact = [entry for entry in entries if entry["id"] in ids]
    if exact:
        # Si le catalogue connaît l'ID canonique, un alias ne contourne pas sa politique.
        canonical = [entry for entry in exact if entry["id"] == model["id"]]
        return canonical or exact
    return [entry for entry in entries if entry.get("name") and
            name_key(entry["name"]) == name_key(model["display_name"])]


def reference_cost(prices: dict) -> float:
    """Calcule en décimal : (0,1 entrée + 0,1 cache + 0,02 sortie) × 100."""
    cost = (
        Decimal("0.1") * decimal_number(prices["input"])
        + Decimal("0.1") * decimal_number(prices["cached_input"])
        + Decimal("0.02") * decimal_number(prices["output"])
    ) * 100
    return float(cost)


def derived_tier(score: int) -> str:
    """Transforme le score de capacité en niveau; le prix n'est jamais un signal."""
    return max((tier for tier in LEVELS
                if score >= CAPABILITY_POLICY["tier_thresholds"][tier]), key=LEVELS.index)


def model_lineage(family: str, name: str) -> tuple[str, tuple[int, ...]] | None:
    """Lignées distinctes par fournisseur et gamme; versions numériques, sans fast."""
    name = clean_name(name).casefold()
    name = re.sub(r"\(preview\)|\(?\bfast(?: mode)?\b\)?", "", name)
    name = name.strip(" -")
    version = r"(?P<version>\d+(?:\.\d+)*)"
    suffix = r"(?:[\s-]+(?P<lineage>[a-z]+))?"
    patterns = {
        "anthropic": (rf"claude[\s-]+(?P<lineage>[a-z]+)[\s-]+{version}", "claude"),
        "openai": (rf"gpt[\s-]+{version}{suffix}", "gpt"),
        "google": (rf"gemini[\s-]+{version}{suffix}", "gemini"),
        "xai": (rf"grok[\s-]+{version}{suffix}", "grok"),
        "microsoft": (rf"mai[\s-]+code[\s-]+{version}{suffix}", "mai-code"),
        "moonshot_ai": (rf"kimi[\s-]+k{version}", "kimi-k"),
    }
    if family not in patterns:
        return None
    pattern, prefix = patterns[family]
    match = re.fullmatch(pattern, name)
    if not match:
        return None
    parts = tuple(map(int, match["version"].split(".")))
    # 5 et 5.0 représentent la même génération, mais 5.10 vient après 5.9.
    while len(parts) > 1 and parts[-1] == 0:
        parts = parts[:-1]
    lineage = match.groupdict().get("lineage")
    return prefix + ("-" + lineage if lineage else ""), parts


def capability_score(model: dict, *, generation: int = 0) -> tuple[dict, list[str]]:
    """Heuristique éditoriale reproductible à partir des métadonnées synchronisées."""
    category = model.get("github_category")
    if category not in CAPABILITY_POLICY["category_scores"]:
        raise ValueError(f"Catégorie GitHub inconnue : {category}. Mise à jour de politique requise.")
    lineage = model_lineage(model["family"], model["display_name"])
    comparison = model.get("github_comparison", {})
    missing = []
    if not any(comparison.get(field) for field in ("task_area", "excels_at")):
        missing.append("comparatif absent")
    if lineage is None:
        missing.append("lignée inconnue")
    components = {"category": CAPABILITY_POLICY["category_scores"][category]}
    if not missing:
        text = " ".join(str(comparison.get(field, "")) for field in ("task_area", "excels_at")).casefold()
        weights = CAPABILITY_POLICY["weights"]
        if re.search(r"\b(?:deep|sophisticated) reasoning\b", text):
            components["deep_reasoning"] = weights["deep_reasoning"]
        elif re.search(r"\bcomplex\b", text):
            components["complex"] = weights["complex"]
        if re.search(r"\blong[- ](?:horizon|running)\b", text):
            components["long_horizon"] = weights["long_horizon"]
        if re.search(r"\b(?:multi[- ]?step|verif\w*|validation|confirmation)\b|\btests? edge cases\b", text):
            components["validation"] = weights["validation"]
        if re.search(r"\b(?:fast|faster|quick|simple|repetitive|lightweight)\b", text):
            components["simple_or_fast"] = weights["simple_or_fast"]
        context = model.get("github_context", {})
        if max(context.get("window_tokens", 0), context.get("default_limit_tokens", 0)) >= 200_000:
            components["context_200k"] = weights["context_200k"]
        if context.get("long_context_tier"):
            components["long_context_tier"] = weights["long_context_tier"]
        status = "ga" if model.get("release_status") == "GA" else "preview"
        components[status] = weights[status]
        components["generation"] = min(generation * weights["generation_step"], weights["generation_max"])
    score = max(0, sum(components.values()))
    return {"score": score, "components": components,
            "lineage": lineage[0] if lineage else None,
            "version": ".".join(map(str, lineage[1])) if lineage else None,
            "tier_scored": derived_tier(score)}, missing


def assign_model_tiers(models: list[dict]) -> None:
    """Score commun aux nouveaux/anciens modèles, puis monotonie des versions.

    Un override prévaut sur le score. Un override contradictoire avec la monotonie
    est une erreur de configuration, jamais une exception silencieuse à la règle.
    """
    groups = {}
    for model in models:
        parsed = model_lineage(model["family"], model["display_name"])
        if parsed:
            lineage, version = parsed
            groups.setdefault((model["family"], lineage), {}).setdefault(version, []).append(model)
    generations = {id(model): generation
                   for versions in groups.values()
                   for generation, version in enumerate(sorted(versions))
                   for model in versions[version]}
    for model in models:
        override = model.get("tier_override")
        if "tier_override" in model and override not in LEVELS:
            raise ValueError(f"tier_override invalide pour {model['id']} : {override}.")
        details, missing = capability_score(model, generation=generations.get(id(model), 0))
        model["capability"] = details
        model["tier"] = override or details["tier_scored"]
        model["tier_source"] = "manual" if override else "category_only" if missing else "score"
        model["tier_provisoire"] = bool(missing and not override)
        model.pop("tier_note", None)
        if model["tier_provisoire"]:
            model["tier_note"] = "Catégorie seule (" + ", ".join(missing) + "); à valider, sous réserve de monotonie."
    for versions in groups.values():
        floor = 0
        for version in sorted(versions):
            peers = versions[version]
            overrides = {model["tier_override"] for model in peers if "tier_override" in model}
            if len(overrides) > 1:
                raise ValueError(f"tier_override contradictoires pour les variantes de {peers[0]['display_name']}.")
            if overrides:
                rank = LEVELS.index(next(iter(overrides)))
                if rank < floor:
                    raise ValueError(f"tier_override de {peers[0]['display_name']} viole la monotonie de sa lignée.")
            else:
                rank = max(floor, *(LEVELS.index(model["tier"]) for model in peers))
            for model in peers:
                if model["tier"] != LEVELS[rank]:
                    model["tier_source"] = "lineage_override" if overrides else "monotonicity"
                model["tier"] = LEVELS[rank]
            floor = rank


def dump_json(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    except (TypeError, ValueError) as exc:
        raise ValueError("Les données contiennent une valeur non compatible avec le format JSON.") from exc


def write_atomic(path: Path, text: str) -> None:
    """Évite de remplacer un fichier valide par une écriture incomplète."""
    import os
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as out:
            name = out.name
            out.write(text)
        os.replace(name, path)
    finally:
        if name and Path(name).exists():
            Path(name).unlink()
