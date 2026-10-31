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
    catalog_entries, dominates, entry_selectable, load_registry, matching_entries, model_lineage, read_available,
    pricing_notice, resolve_model_prices,
)


class SelectionError(Exception):
    """Erreur prévisible avec un code utilisable par l'orchestrateur."""

    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)

    def print_help(self, file=None):
        print(dump_json({"help": self.format_help()}), end="", file=file)


def error_payload(exc: Exception) -> dict:
    code = exc.code if isinstance(exc, SelectionError) else 1
    hints = {
        1: "Vérifier les arguments (--help), les fichiers et le registre.",
        2: "Augmenter le budget ou fournir un catalogue avec un modèle admissible moins cher.",
        3: "Fournir --dev-model (ou --dev-family) et un modèle disponible d'une autre famille.",
        4: "Vérifier Copilot CLI, copilot login, la licence et le catalogue de l'organisation.",
        5: "Utiliser un rôle connu : " + ", ".join(ROLES) + ".",
    }
    return {"error": str(exc), "hint": hints[code], "exit_code": code, "decision_source": None}


def best_model(models: list[dict]) -> dict:
    """Coût minimal, puis capacité et génération décroissantes; ID en dernier."""
    def priority(model):
        lineage = model_lineage(model["family"], model["display_name"])
        return (-decimal_number(model["cost_index"]),
                decimal_number(model.get("capability", {}).get("score", 0)),
                lineage[1] if lineage else ())

    # Le tri stable garde l'ID croissant seulement si tous les signaux sont égaux.
    return max(sorted(models, key=lambda model: model["id"]), key=priority)


def catalog_models(registry: dict, available: list[dict] | None) -> tuple[list[dict], list[str]]:
    """Le catalogue fourni remplace le constat précédent et le support CLI documenté."""
    models = copy.deepcopy(registry["models"])
    resolve_model_prices(models)
    warnings = []
    if available is not None:
        available = catalog_entries(available)
        known = set()
        for model in models:
            matches = matching_entries(model, available)
            entry = matches[0] if len(matches) == 1 else None
            was_unavailable = (model.get("available") is False or not model.get("cli")
                               or model.get("retired") or not entry_selectable(model.get("runtime")))
            model["available"] = bool(entry and entry_selectable(entry))
            if len(matches) > 1:
                warnings.append(f"Correspondance ambiguë exclue : {model['display_name']}.")
            if entry:
                known.add(entry["id"])
                if entry_selectable(entry) and was_unavailable:
                    warnings.append(f"{entry['id']} : registre périmé, relancer la sync; --available fait foi.")
                if entry["id"] != model["id"]:
                    model["aliases"] = sorted(set(model.get("aliases", []) + [model["id"]]))
                    model["id"] = entry["id"]
                model.update(id_verified=True, cli=True, retired=False, runtime=entry)
        unknown = sorted(entry["id"] for entry in available if entry["id"] not in known)
        if unknown:
            warnings.append("ID absents du registre, non admissibles; lancer sync_registry : " + ", ".join(unknown) + ".")
    for model in models:
        entry_selectable(model.get("runtime"))
        model["runtime"] = model.get("runtime") or {}
    return models, warnings


def model_available(model: dict, allow_preview: bool) -> bool:
    return (model.get("cli") is True and not model.get("retired")
            and model.get("cost_index") is not None and model["family"] != "unknown"
            and model.get("available") is not False
            and entry_selectable(model["runtime"])
            and (allow_preview or (model.get("release_status") == "GA"
                 and not model.get("preview") and not model["runtime"].get("preview"))))


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
                 max_level: str | None = None, preferred_model: str | None = None) -> dict:
    """L'API permet au routeur de fournir sa préférence et ses bornes par rôle.

    Les trois modes publics restent exclusifs. preferred_level remplace seulement
    la préférence des défauts/profils; le plafond financier reste intact.
    """
    if role not in ROLES:
        raise SelectionError(f"Rôle inconnu : {role}.", 5)
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
    models, warnings = catalog_models(registry, available)
    missing_prices = [pricing_notice(model) for model in models
                      if model.get("pricing_missing") and model.get("available") is not False]
    warnings += missing_prices
    family = resolve_dev_family(models, role, dev_family, dev_model)

    def exclusions():
        details = []
        for model in models:
            reasons = []
            if model["family"] == "unknown":
                reasons.append("famille inconnue, définir family dans models.yaml")
            if model.get("cost_index") is None:
                reasons.append("pricing_missing, ajouter son prix dans models.yaml")
            if not model.get("cli"):
                reasons.append("CLI non pris en charge")
            if model.get("retired"):
                reasons.append("modèle retiré")
            if model.get("available") is False:
                reasons.append("indisponible")
            if not entry_selectable(model["runtime"]):
                reasons.append("politique ou capacités interdites")
            if not allow_preview and (model.get("release_status") != "GA"
                                      or model.get("preview") or model["runtime"].get("preview")):
                reasons.append("aperçu interdit")
            if max_level and rank[model["tier"]] > rank[max_level]:
                reasons.append("hors plafond du rôle")
            if min_level and rank[model["tier"]] < rank[min_level]:
                reasons.append("sous le niveau minimal du rôle")
            if cap is not None and model.get("cost_index") is not None and decimal_number(model["cost_index"]) > cap:
                reasons.append("hors budget")
            if family and model["family"] == family:
                reasons.append("même famille que le dev")
            if reasons:
                details.append(f"{model['id']}: " + ", ".join(reasons))
        return "Exclusions : " + "; ".join(details) + "."

    # Bornes absolues du rôle : un successeur doit passer ces filtres avant
    # de pouvoir dépasser la simple préférence de niveau « wanted ».
    eligible = [model for model in models
                if model_available(model, allow_preview)
                and (min_level is None or rank[model["tier"]] >= rank[min_level])
                and (max_level is None or rank[model["tier"]] <= rank[max_level])]
    if family:
        eligible = [model for model in eligible if model["family"] != family]
        if not eligible:
            raise SelectionError(
                f"Aucun modèle CLI admissible d'une famille différente de {family}. "
                "La contrainte de famille ne peut pas être relâchée. " + exclusions() + " " + " ".join(warnings), 3)
    if not eligible:
        raise SelectionError("Aucun modèle CLI admissible dans la disponibilité fournie et le statut permis. "
                             + exclusions() + " " + " ".join(warnings))
    if cap is not None:
        eligible = [model for model in eligible if decimal_number(model["cost_index"]) <= cap]
        if not eligible:
            raise SelectionError(
                f"Aucun modèle admissible ne respecte le plafond de {cap} crédits par tâche de référence. "
                "Le budget ne peut pas être dépassé. " + exclusions(), 2)
    within_level = [model for model in eligible if rank[model["tier"]] <= rank[wanted]]
    if within_level:
        chosen_rank = max(rank[model["tier"]] for model in within_level)
    else:
        # Seule la préférence de niveau est souple; les filtres de coût et de famille restent en place.
        chosen_rank = min(rank[model["tier"]] for model in eligible)
    target_pool = [model for model in eligible if rank[model["tier"]] == chosen_rank]
    dominated = {model["id"] for model in eligible
                 if any(dominates(other, model) for other in eligible)}
    survivors = [model for model in eligible if model["id"] not in dominated]
    # Seuls les successeurs de ces candidats peuvent dépasser le niveau visé.
    # Un autre modèle premium ne remplace pas un standard d'une lignée différente.
    pool = [model for model in survivors if model in target_pool
            or any(dominates(model, older) for older in target_pool)]
    chosen = best_model(pool)
    suggestion_reason = None
    suggested = None
    if preferred_model is not None:
        suggested = next((model for model in models if model["id"] == preferred_model), None)
        valid = next((model for model in eligible if model["id"] == preferred_model), None)
        above_ceiling = bool(valid and rank[valid["tier"]] > rank[wanted] and valid not in pool)
        if above_ceiling:
            valid = None
        if valid:
            successors = [model for model in survivors if dominates(model, valid)]
            chosen = best_model(successors) if successors else valid
            suggestion_reason = (
                f"Suggestion LLM {preferred_model} écartée : génération dominée; successeur {chosen['id']} retenu."
                if successors else f"Suggestion LLM {preferred_model} validée par les contraintes Python.")
        else:
            if suggested is None:
                rejection = "hors catalogue"
            elif not model_available(suggested, allow_preview):
                rejection = "indisponible ou statut interdit"
            elif family and suggested["family"] == family:
                rejection = "même famille que le dev"
            elif cap is not None and decimal_number(suggested["cost_index"]) > cap:
                rejection = "budget dépassé"
            elif above_ceiling:
                rejection = "plafond de niveau dépassé sans succession dans la même lignée"
            else:
                rejection = "hors bornes du rôle"
            suggestion_reason = f"Suggestion LLM {preferred_model} écartée : {rejection}; choix Python valide."
    fallback = ("lower_tier" if rank[chosen["tier"]] < rank[wanted] else
                "relaxed_level" if rank[chosen["tier"]] > rank[wanted] else "none")
    lineage_upgrade = any(dominates(chosen, older) for older in target_pool)
    if suggested and model_available(suggested, allow_preview):
        lineage_upgrade = lineage_upgrade or dominates(chosen, suggested)
    reasons = [f"Rôle {role}, niveau souhaité {wanted}; niveau retenu {chosen['tier']}.", *missing_prices]
    if chosen.get("prix_suppose"):
        notice = pricing_notice(chosen)
        reasons.append(notice)
        warnings.append(notice)
    if preferred_model != chosen["id"]:
        reasons.append("Choix Python par préférence de niveau et succession de lignée, puis coût minimal; "
                       "à coût égal : score de capacité, génération récente, puis ID.")
    if suggestion_reason:
        reasons.append(suggestion_reason)
    if dominated:
        reasons.append("Générations dominées exclues : " + ", ".join(sorted(dominated)) + ".")
    if lineage_upgrade:
        reasons.append("Successeur de même lignée prioritaire : niveau au moins égal, coût égal ou inférieur.")
    elif preferred_model == chosen["id"] and fallback != "none":
        reasons.append("Préférence de niveau ajustée pour la suggestion LLM validée.")
    elif fallback == "lower_tier":
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
    command = ["herdr", "agent", "start", role, "--kind", "copilot", "--pane", "1",
               "--", "--model", chosen["id"]]
    return {
        "id": chosen["id"], "model": chosen["id"], "display_name": chosen["display_name"], "family": chosen["family"],
        "tier": chosen["tier"], "requested_level": wanted, "role": role,
        "level": wanted, "decision_source": "heuristic",
        "tier_provisoire": bool(chosen.get("tier_provisoire")),
        "prix_suppose": bool(chosen.get("prix_suppose")),
        "pricing_predecessor": chosen.get("pricing_predecessor"),
        "cost_index": chosen["cost_index"], "max_cost": float(cap) if cap is not None else None,
        "budget_profile": budget_profile, "dev_family": family,
        "id_verified": chosen.get("id_verified", False), "available": chosen.get("available"),
        "reason": " ".join(reasons), "reasons": reasons, "fallback": fallback, "warnings": warnings,
        "herdr_command": shlex.join(command), "herdr_argv": command,
    }


def main(argv=None) -> int:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=ROOT / "models.yaml", help="Registre YAML ou JSON.")
    parser.add_argument("--role", required=True, help="Rôle de l'équipier : " + ", ".join(ROLES) + ".")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--level", choices=LEVELS, help="Préférence de niveau.")
    mode.add_argument("--max-cost", help="Plafond de crédits par tâche de référence.")
    mode.add_argument("--budget-profile", help="Profil défini dans le registre.")
    parser.add_argument("--dev-family", help="Fournisseur du modèle du dev, obligatoire pour la validation/revue.")
    parser.add_argument("--dev-model", help="Identifiant connu du modèle du dev; permet d'en déduire la famille.")
    parser.add_argument("--available", help="Fichier JSON/texte ou liste d'ID séparés par virgule.")
    parser.add_argument("--allow-preview", action="store_true", help="Permettre les modèles en aperçu.")
    parser.add_argument("--json", action="store_true", help="Compatibilité : la sortie est toujours un objet JSON.")
    try:
        args = parser.parse_args(argv)
        registry = load_registry(args.registry)
        available = read_available(args.available) if args.available is not None else None
        result = select_model(registry, role=args.role, level=args.level, max_cost=args.max_cost,
                              budget_profile=args.budget_profile, dev_family=args.dev_family,
                              dev_model=args.dev_model, available=available, allow_preview=args.allow_preview)
        output = dump_json(result)
    except Exception as exc:
        payload = error_payload(exc)
        print(dump_json(payload), end="")
        return payload["exit_code"]
    for warning in result["warnings"]:
        print(f"Avertissement : {warning}", file=sys.stderr)
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
