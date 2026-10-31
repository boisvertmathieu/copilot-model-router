#!/usr/bin/env python3
"""Choisit un modèle Copilot par rôle, niveau ou plafond en AI credits."""

from __future__ import annotations

import argparse
import copy
import shlex
import sys
from pathlib import Path

from registry_lib import (
    ROOT, LEVELS, ROLES, ROLE_LEVELS, decimal_number, dump_json,
    entry_selectable, load_registry, matching_entries, read_available,
)


class SelectionError(Exception):
    """Erreur prévisible avec un code utilisable par l'orchestrateur."""

    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


def resolve_dev_family(models: list[dict], role: str,
                       dev_family: str | None, dev_model: str | None) -> str | None:
    if role not in ("e2e-validator", "reviewer"):
        return None
    known_families = {model["family"] for model in models}
    if dev_family and dev_family not in known_families:
        raise SelectionError(f"Famille du dev inconnue : {dev_family}. Utilisez le fournisseur du registre.", 3)
    found = [model for model in models if dev_model and
             dev_model in {model["id"], *model.get("aliases", [])}]
    families = {model["family"] for model in found}
    if len(families) > 1:
        raise SelectionError("L'identifiant du dev correspond à plusieurs familles; corrigez le registre.", 3)
    inferred = next(iter(families), None)
    if inferred and dev_family and inferred != dev_family:
        raise SelectionError("--dev-model et --dev-family désignent des fournisseurs différents.", 3)
    family = inferred or dev_family
    if not family:
        raise SelectionError(
            "La famille du dev est obligatoire pour ce rôle. Fournissez --dev-family ou un --dev-model connu.", 3)
    return family


def select_model(registry: dict, *, role: str, level: str | None = None,
                 max_cost=None, budget_profile: str | None = None,
                 dev_family: str | None = None, dev_model: str | None = None,
                 available: list[dict] | None = None, allow_preview=False,
                 preferred_level: str | None = None, min_level: str | None = None,
                 max_level: str | None = None) -> dict:
    """L'API permet au routeur de fournir sa préférence et ses bornes par rôle.

    Les trois modes publics restent exclusifs. preferred_level remplace seulement
    la préférence des défauts/profils; le plafond financier reste intact.
    """
    if role not in ROLES:
        raise SelectionError(f"Rôle inconnu : {role}.")
    if sum(value is not None for value in (level, max_cost, budget_profile)) > 1:
        raise SelectionError("Choisissez un seul mode : --level, --max-cost ou --budget-profile.")
    wanted = level or registry.get("role_defaults", {}).get(role, ROLE_LEVELS[role])
    cap = decimal_number(max_cost, "Le plafond") if max_cost is not None else None
    if budget_profile is not None:
        profile = registry.get("budget_profiles", {}).get(budget_profile)
        if not isinstance(profile, dict) or "max_cost" not in profile:
            raise SelectionError(f"Profil de budget inconnu ou invalide : {budget_profile}.")
        wanted = profile.get("level", wanted)
        cap = decimal_number(profile["max_cost"], "Le plafond du profil")
    if preferred_level is not None:
        wanted = preferred_level
    if wanted not in LEVELS:
        raise SelectionError(f"Niveau demandé invalide : {wanted}.")
    rank = {name: i for i, name in enumerate(LEVELS)}
    if any(bound is not None and bound not in LEVELS for bound in (min_level, max_level)):
        raise SelectionError("Borne de niveau invalide.")
    if min_level and max_level and rank[min_level] > rank[max_level]:
        raise SelectionError("Le niveau minimal dépasse le niveau maximal.")
    models = copy.deepcopy(registry["models"])
    warnings = []
    # Un catalogue récent fourni à cette invocation remplace l'ancien constat disponible.
    if available is not None:
        known = set()
        for model in models:
            matches = matching_entries(model, available)
            entry = matches[0] if len(matches) == 1 else None
            model["available"] = bool(entry and entry_selectable(entry))
            if len(matches) > 1:
                warnings.append(f"Correspondance ambiguë exclue : {model['display_name']}.")
            if entry:
                known.add(entry["id"])
                if entry["id"] != model["id"]:
                    model["aliases"] = list(set(model.get("aliases", []) + [model["id"]]))
                    model["id"] = entry["id"]
                model["id_verified"] = True
                model["runtime"] = entry
        unknown = sorted(entry["id"] for entry in available if entry["id"] not in known)
        if unknown:
            warnings.append("ID sans tarif CLI associé, exclus : " + ", ".join(unknown) + ".")
    family = resolve_dev_family(models, role, dev_family, dev_model)
    eligible = [model for model in models
                if model.get("cli") is True and not model.get("retired")
                and model.get("available") is not False
                and (min_level is None or rank[model["tier"]] >= rank[min_level])
                and (max_level is None or rank[model["tier"]] <= rank[max_level])
                and entry_selectable(model.get("runtime", {}))
                and (allow_preview or (model.get("release_status") == "GA"
                     and not model.get("preview") and not model.get("runtime", {}).get("preview")))]
    if family:
        eligible = [model for model in eligible if model["family"] != family]
        if not eligible:
            raise SelectionError(
                f"Aucun modèle CLI admissible d'une famille différente de {family}. "
                "La contrainte de famille ne peut pas être relâchée.", 3)
    if not eligible:
        raise SelectionError("Aucun modèle CLI admissible dans la disponibilité fournie et le statut permis.")
    if cap is not None:
        eligible = [model for model in eligible if decimal_number(model["cost_index"]) <= cap]
        if not eligible:
            raise SelectionError(
                f"Aucun modèle admissible ne respecte le plafond de {cap} crédits par tâche de référence. "
                "Le budget ne peut pas être dépassé.", 2)
    within_level = [model for model in eligible if rank[model["tier"]] <= rank[wanted]]
    fallback = "none"
    if within_level:
        chosen_rank = max(rank[model["tier"]] for model in within_level)
        pool = [model for model in within_level if rank[model["tier"]] == chosen_rank]
        if chosen_rank < rank[wanted]:
            fallback = "lower_tier"
    else:
        # Seule la préférence de niveau est souple; les filtres de coût et de famille restent en place.
        chosen_rank = min(rank[model["tier"]] for model in eligible)
        pool = [model for model in eligible if rank[model["tier"]] == chosen_rank]
        fallback = "relaxed_level"
    chosen = min(pool, key=lambda model: (decimal_number(model["cost_index"]), model["id"]))
    reasons = [f"Rôle {role}, niveau souhaité {wanted}; niveau retenu {chosen['tier']}, "
               "puis coût minimal dans ce niveau (égalité tranchée par ID)."]
    if fallback == "lower_tier":
        reasons.append("Repli vers un niveau inférieur : aucun candidat admissible au niveau souhaité.")
    elif fallback == "relaxed_level":
        reasons.append("Préférence de niveau relâchée : aucun candidat admissible au niveau souhaité ou plus bas.")
    reasons.append(f"Coût estimé : {chosen['cost_index']:g} crédits par tâche de référence.")
    if cap is not None:
        reasons.append(f"Plafond respecté : {cap} crédits.")
    if family:
        reasons.append(f"Famille {chosen['family']} différente de celle du dev ({family}).")
    if min_level or max_level:
        reasons.append(f"Bornes du rôle respectées : {min_level or 'economy'} à {max_level or 'frontier'}.")
    if chosen.get("tier_provisoire"):
        notice = (f"Niveau {chosen['tier']} provisoire : "
                  + chosen.get("tier_note", "métadonnées GitHub insuffisantes; à valider."))
        reasons.append(notice)
        warnings.append(notice)
    if chosen.get("available") is None:
        warnings.append("Disponibilité du compte non vérifiée; fournir --available après connexion au poste de travail.")
    if not chosen.get("id_verified"):
        warnings.append("Identifiant CLI supposé; le confirmer avec models.list avant de lancer Herdr.")
    if chosen.get("preview") or chosen.get("runtime", {}).get("preview") or chosen.get("release_status") != "GA":
        warnings.append("Modèle en aperçu autorisé explicitement par --allow-preview.")
    command = ["herdr", "agent", "start", role, "--kind", "copilot", "--pane", "<pane>",
               "--", "--model", chosen["id"]]
    return {
        "id": chosen["id"], "display_name": chosen["display_name"], "family": chosen["family"],
        "tier": chosen["tier"], "requested_level": wanted, "role": role,
        "tier_provisoire": bool(chosen.get("tier_provisoire")),
        "cost_index": chosen["cost_index"], "max_cost": float(cap) if cap is not None else None,
        "budget_profile": budget_profile, "dev_family": family,
        "id_verified": chosen.get("id_verified", False), "available": chosen.get("available"),
        "reason": " ".join(reasons), "fallback": fallback, "warnings": warnings,
        "herdr_command": shlex.join(command), "herdr_argv": command,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=ROOT / "models.yaml", help="Registre YAML ou JSON.")
    parser.add_argument("--role", choices=ROLES, required=True, help="Rôle de l'équipier.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--level", choices=LEVELS, help="Préférence de niveau.")
    mode.add_argument("--max-cost", help="Plafond de crédits par tâche de référence.")
    mode.add_argument("--budget-profile", help="Profil défini dans le registre.")
    parser.add_argument("--dev-family", help="Fournisseur du modèle du dev, obligatoire pour la validation/revue.")
    parser.add_argument("--dev-model", help="Identifiant connu du modèle du dev; permet d'en déduire la famille.")
    parser.add_argument("--available", help="Fichier JSON/texte ou liste d'ID séparés par virgule.")
    parser.add_argument("--allow-preview", action="store_true", help="Permettre les modèles en aperçu.")
    parser.add_argument("--json", action="store_true", help="Sortie JSON destinée à l'orchestrateur.")
    args = parser.parse_args(argv)
    try:
        registry = load_registry(args.registry)
        available = read_available(args.available) if args.available is not None else None
        result = select_model(registry, role=args.role, level=args.level, max_cost=args.max_cost,
                              budget_profile=args.budget_profile, dev_family=args.dev_family,
                              dev_model=args.dev_model, available=available, allow_preview=args.allow_preview)
    except (SelectionError, ValueError, OSError, KeyError, TypeError) as exc:
        code = exc.code if isinstance(exc, SelectionError) else 1
        if args.json:
            print(dump_json({"error": str(exc), "exit_code": code}), end="")
        else:
            print(f"Sélection impossible : {exc}", file=sys.stderr)
        return code
    if args.json:
        print(dump_json(result), end="")
    else:
        print(result["id"])
        print(result["reason"])
        for warning in result["warnings"]:
            print(f"À vérifier : {warning}")
        print(result["herdr_command"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
