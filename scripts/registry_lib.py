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
        if not isinstance(model.get("family"), str) or not model["family"]:
            raise ValueError(f"Famille manquante pour {model['id']}.")
        decimal_number(model.get("cost_index"), f"Coût de {model['id']}")
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


def entry_selectable(entry: dict) -> bool:
    """Une interdiction explicite du catalogue n'est jamais ignorée."""
    policy = entry.get("policy") or {}
    capabilities = entry.get("capabilities") or {}
    if not isinstance(policy, dict) or not isinstance(capabilities, dict):
        raise ValueError("Politique ou capacités de modèle invalides.")
    return (
        entry.get("available") is not False
        and policy.get("state", "enabled") == "enabled"
        and entry.get("model_picker_enabled") is not False
        and capabilities.get("type", "chat") == "chat"
    )


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


def derived_tier(category: str, cost: float) -> str:
    """Convention locale : la catégorie prime, puis le prix distingue frontier."""
    if category == "Lightweight":
        return "economy"
    if category == "Versatile":
        return "standard"
    if category == "Powerful":
        return "frontier" if cost >= 100 else "premium"
    raise ValueError(f"Catégorie GitHub inconnue : {category}. Mise à jour de politique requise.")


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
