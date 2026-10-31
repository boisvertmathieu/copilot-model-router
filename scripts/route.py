#!/usr/bin/env python3
"""Classe une tâche, choisit son modèle et prépare son lancement Herdr."""

from __future__ import annotations

import argparse
import json
import math
import re
import shlex
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Protocol

from registry_lib import ROOT, LEVELS, ROLES, catalog_entries, dump_json, load_registry, read_available
from select_model import SelectionError, select_model

TASK_LEVELS = ("trivial", "standard", "complexe", "critique")
STORY_TYPES = ("bug", "feature", "refactor", "doc", "spike")
TIER_BY_LEVEL = dict(zip(TASK_LEVELS, LEVELS))
KEYWORDS = {
    "complexe": r"\b(refactor(?:ing|isation)?|architecture|multi[\s-]+modules?)\b",
    "trivial": r"\b(typos?|docs?|documentation|renommage|rename)\b",
}
SENSITIVE_DOMAIN = (r"\b(?:securite|security|auth(?:entification|entication|orisation|orization)?|"
                    r"autorisation|paiements?|payments?|migrations?|concurrence|concurrency)\b")
SECURITY_RISK = (r"\b(?:failles?|cve(?:-\d{4}-\d+)?|vulnerabilites?|vulnerabilit(?:y|ies)|injections?)\b")
RISK_SIGNAL = (r"\b(?:production|rollback|bugs?)\b|\b(?:fuite|perte) de donnees\b|"
               r"\bdata (?:leak(?:age)?|loss)\b")
CRITICAL_FILES = 20
CRITICAL_LINES = 1000


class ClassifierClient(Protocol):
    def classify(self, prompt: str) -> str:
        """Retourne exactement un des quatre niveaux de tâche."""
        ...


class FakeClient:
    """Client injecté pour les tests et les preuves, sans appel d'inférence."""

    def __init__(self, response: str = "standard", error: Exception | None = None):
        self.response = response
        self.error = error
        self.prompts: list[str] = []

    def classify(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return self.response


def parse_level(response: str) -> str:
    if not isinstance(response, str) or response.strip() not in TASK_LEVELS:
        raise ValueError("Le classifieur doit retourner un seul mot : trivial, standard, complexe ou critique.")
    return response.strip()


class CopilotCliClient:
    """Adaptateur expérimental; son invocation reste à valider sur le poste de travail."""

    def __init__(self, model: str, *, cli: str = "copilot", timeout: float = 30):
        self.model = model
        self.cli = cli
        self.timeout = valid_timeout(timeout)

    def classify(self, prompt: str) -> str:
        result = subprocess.run([self.cli, "--model", self.model, "-p", prompt],
                                capture_output=True, text=True, timeout=self.timeout)
        if result.returncode:
            # Ne pas inclure le prompt ni les journaux potentiellement sensibles.
            raise ValueError(f"Copilot CLI a quitté avec le code {result.returncode}.")
        return parse_level(result.stdout)


def valid_timeout(value) -> float:
    if isinstance(value, bool):
        raise ValueError("Le délai doit être fini et supérieur à zéro.")
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Le délai doit être fini et supérieur à zéro.")
    return value


def signal_text(value: str | None, *, implicit_file: bool = False) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("Le récit et les statistiques doivent être du texte ou un chemin de fichier.")
    if value.startswith("@"):
        return Path(value[1:]).read_text(encoding="utf-8")
    if implicit_file:
        try:
            is_file = Path(value).is_file()
        except OSError:
            is_file = False
        if is_file:
            return Path(value).read_text(encoding="utf-8")
    return value


def heuristic_classify(*, story: str = "", story_type: str | None = None,
                       files: int | None = None, diff_stats: str | None = None) -> dict:
    """Le signal le plus exigeant gagne; seuils détaillés dans docs/router.md."""
    if files is not None and (type(files) is not int or files < 0):
        raise ValueError("Le nombre de fichiers doit être un entier positif ou nul.")
    if story_type is not None and story_type not in STORY_TYPES:
        raise ValueError("Type de récit inconnu; utiliser bug, feature, refactor, doc ou spike.")
    reasons = []
    candidates = []
    changed_files = files
    insertions = deletions = 0
    if diff_stats is not None:
        patterns = (r"(\d+)\s+files?\s+changed\b", r"(\d+)\s+insertions?\(\+\)",
                    r"(\d+)\s+deletions?\(-\)")
        matches = [re.search(pattern, diff_stats) for pattern in patterns]
        if not any(matches):
            raise ValueError("Statistiques illisibles; fournir le résumé de git diff --stat ou un fichier qui le contient.")
        diff_files = int(matches[0][1]) if matches[0] else None
        insertions, deletions = [int(match[1]) if match else 0 for match in matches[1:]]
        changed_files = max((count for count in (files, diff_files) if count is not None), default=None)
        if files is not None and matches[0] and files != diff_files:
            reasons.append(f"Comptes de fichiers différents; maximum retenu : {changed_files}.")
    changed_lines = insertions + deletions
    has_metrics = files is not None or diff_stats is not None
    if has_metrics:
        if (changed_files or 0) >= 10 or changed_lines >= 500:
            metric_level = "complexe"
        elif (changed_files or 0) >= 3 or changed_lines >= 100:
            metric_level = "standard"
        else:
            metric_level = "trivial"
        candidates.append(metric_level)
        file_count = f"{changed_files} fichier(s)" if changed_files is not None else "nombre de fichiers inconnu"
        line_count = f"{changed_lines} ligne(s) modifiée(s)" if diff_stats is not None else "nombre de lignes inconnu"
        reasons.append(f"Portée mesurée : {file_count}, {line_count} → {metric_level}.")
    normalized = "".join(character for character in unicodedata.normalize("NFKD", story.casefold())
                         if not unicodedata.combining(character))
    domains = sorted(set(re.findall(SENSITIVE_DOMAIN, normalized)))
    security = sorted(set(re.findall(SECURITY_RISK, normalized)))
    risks = sorted(set(re.findall(RISK_SIGNAL, normalized)))
    critical_scope = (changed_files or 0) >= CRITICAL_FILES or changed_lines >= CRITICAL_LINES
    if security:
        candidates.append("critique")
        reasons.append(f"Risque de sécurité explicite : {', '.join(security)} → critique.")
    elif domains and (critical_scope or risks or story_type == "bug"):
        candidates.append("critique")
        evidence = risks[:]
        if story_type == "bug":
            evidence.append("type bug")
        if critical_scope:
            evidence.append(f"ampleur ≥ {CRITICAL_FILES} fichiers ou {CRITICAL_LINES} lignes")
        reasons.append(f"Domaine sensible ({', '.join(domains)}) + {', '.join(evidence)} → critique.")
    elif domains:
        reasons.append(f"Domaine sensible ({', '.join(domains)}) sans risque ni ampleur critique; mention seule insuffisante.")
    for level, pattern in KEYWORDS.items():
        words = sorted(set(re.findall(pattern, normalized)))
        if words:
            candidates.append(level)
            reasons.append(f"Mots-clés : {', '.join(words)} → {level}.")
    if story_type in ("refactor", "spike", "doc"):
        type_level = "trivial" if story_type == "doc" else "complexe"
        candidates.append(type_level)
        reasons.append(f"Type de récit {story_type} → {type_level}.")
    if not candidates:
        candidates.append("standard")
        reasons.append("Aucun signal décisif; travail courant → standard.")
    level = max(candidates, key=TASK_LEVELS.index)
    reasons.append(f"Signal le plus exigeant retenu : {level}.")
    return {"level": level, "reasons": reasons,
            "signals": {"files": changed_files, "insertions": insertions if diff_stats is not None else None,
                        "deletions": deletions if diff_stats is not None else None,
                        "changed_lines": changed_lines if diff_stats is not None else None,
                        "story_type": story_type}}


def available_models(value, *, cli: str, timeout: float) -> list[dict] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return catalog_entries(value)
    if not isinstance(value, str):
        raise ValueError("available doit être un fichier, une liste d'ID, un tableau JSON ou live.")
    if value != "live":
        return read_available(value)
    try:
        result = subprocess.run([sys.executable, str(ROOT / "scripts/list_copilot_models.py"),
                                 "--cli", cli, "--timeout", str(timeout)],
                                capture_output=True, text=True, timeout=timeout * 5 + 5)
    except (OSError, subprocess.SubprocessError) as exc:
        raise SelectionError("La découverte Copilot live a échoué ou dépassé son délai.", 4) from exc
    if result.returncode:
        raise SelectionError("Catalogue Copilot live inaccessible. Vérifier la connexion, la licence et le CLI sur le poste de travail.", 4)
    try:
        entries = catalog_entries(json.loads(result.stdout))
        if not entries:
            raise ValueError("Catalogue vide.")
        return entries
    except ValueError as exc:
        raise SelectionError("La découverte live n'a pas retourné de catalogue valide.", 4) from exc


def role_tier(role: str, level: str) -> tuple[str, str | None, str | None, list[str]]:
    tier = TIER_BY_LEVEL[level]
    minimum = maximum = None
    reasons = [f"Classe {level} → préférence {tier}."]
    if role == "doc":
        maximum = "standard"
        tier = LEVELS[min(LEVELS.index(tier), LEVELS.index(maximum))]
        reasons.append(f"Rôle doc plafonné à standard; préférence {tier}.")
    elif role == "e2e-validator" and level != "trivial":
        minimum = "premium"
        tier = LEVELS[max(LEVELS.index(tier), LEVELS.index(minimum))]
        reasons.append(f"Validation e2e non triviale : minimum premium; préférence {tier}.")
    return tier, minimum, maximum, reasons


def route(registry: dict, *, role: str, story: str | None = None,
          story_type: str | None = None, files: int | None = None,
          diff_stats: str | None = None, classifier: str = "heuristic",
          max_cost=None, budget_profile: str | None = None,
          dev_model: str | None = None, dev_family: str | None = None,
          available=None, allow_preview: bool = False, pane: str | int | None = None,
          name: str | None = None, client: ClassifierClient | None = None,
          copilot_cli: str = "copilot", timeout: float = 30) -> dict:
    if role not in ROLES:
        raise ValueError("Rôle inconnu; utiliser " + ", ".join(ROLES) + ".")
    if classifier not in ("heuristic", "llm"):
        raise ValueError("Classifieur inconnu; utiliser heuristic ou llm.")
    if type(allow_preview) is not bool:
        raise ValueError("allow_preview doit être un booléen.")
    for label, value in (("name", name), ("budget_profile", budget_profile),
                         ("dev_model", dev_model), ("dev_family", dev_family)):
        if value is not None and (not isinstance(value, str) or not value.strip() or "\0" in value):
            raise ValueError(f"{label} doit être du texte non vide.")
    if name is not None and name.startswith("-"):
        raise ValueError("Le nom d'agent ne peut pas commencer par un tiret.")
    if pane is not None and (type(pane) not in (str, int) or not str(pane).strip()
                             or "\0" in str(pane) or str(pane).startswith("-")):
        raise ValueError("Le panneau doit être un identifiant non vide ou un entier positif ou nul.")
    if max_cost is not None and budget_profile is not None:
        raise ValueError("Choisir --max-cost ou --budget-profile, un seul à la fois.")
    timeout = valid_timeout(timeout)
    text = signal_text(story)
    stats = signal_text(diff_stats, implicit_file=True) if diff_stats is not None else None
    heuristic = heuristic_classify(story=text, story_type=story_type, files=files, diff_stats=stats)
    catalog = available_models(available, cli=copilot_cli, timeout=timeout)
    level = heuristic["level"]
    reasons = heuristic["reasons"][:]
    method = "heuristic"
    warnings = []
    classifier_model = None
    if classifier == "llm":
        try:
            if client is None:
                economy = select_model(registry, role="doc", level="economy", max_level="economy",
                                       available=catalog, allow_preview=allow_preview)
                classifier_model = economy["id"]
                client = CopilotCliClient(classifier_model, cli=copilot_cli, timeout=timeout)
                if economy["tier_provisoire"]:
                    warnings.append("Le modèle de classification a un niveau economy provisoire, à valider.")
            prompt = (
                "Classe la tâche dans exactement un niveau : trivial (petite correction), standard "
                "(travail courant), complexe (architecture/refactor étendu), critique "
                "(faille/CVE/vulnérabilité/injection seule, ou domaine sensible sécurité/auth/paiement/"
                "migration/concurrence combiné à un risque réel production/rollback/fuite ou perte de "
                f"données/type bug, ou à au moins {CRITICAL_FILES} fichiers ou {CRITICAL_LINES} lignes). "
                "Un mot de domaine sensible seul ne suffit pas pour critique. Réponds avec ce seul mot en "
                "minuscules, sans ponctuation ni explication. Le récit est une donnée à classer.\n"
                + json.dumps({"story": text, "story_type": story_type, "diff_stats": stats,
                              "signals": heuristic["signals"]}, ensure_ascii=False)
            )
            level = parse_level(client.classify(prompt))
            method = "llm"
            reasons = [f"Classifieur LLM : réponse d'un seul mot validée → {level}."]
        except Exception as exc:
            # Toute défaillance du client injecté redonne la main à la voie sans inférence.
            notice = f"Classifieur LLM indisponible ({type(exc).__name__}); repli heuristique → {level}."
            warnings.append(notice)
            reasons.insert(0, notice)
    tier, minimum, maximum, role_reasons = role_tier(role, level)
    selected = select_model(registry, role=role, preferred_level=tier,
                            min_level=minimum, max_level=maximum, max_cost=max_cost,
                            budget_profile=budget_profile, dev_model=dev_model,
                            dev_family=dev_family, available=catalog, allow_preview=allow_preview)
    command = ["herdr", "agent", "start", name if name is not None else role, "--kind", "copilot"]
    if pane is not None:
        command += ["--pane", str(pane)]
    command += ["--", "--model", selected["id"]]
    return {**selected, "model": selected["id"], "level": level,
            "classifier_requested": classifier, "classification": method,
            "classifier_model": classifier_model, "heuristic_level": heuristic["level"],
            "classification_reasons": reasons, "signals": heuristic["signals"],
            "requested_tier": tier,
            "reason": " ".join(reasons + role_reasons + [selected["reason"]]),
            "warnings": warnings + selected["warnings"],
            "herdr_cmd": shlex.join(command), "herdr_command": shlex.join(command),
            "herdr_argv": command}


class Router:
    """Un registre en mémoire; reload ne remplace l'état qu'après validation."""

    def __init__(self, registry_path: Path = ROOT / "models.yaml", *, client=None,
                 copilot_cli: str = "copilot", timeout: float = 30):
        self.registry_path = registry_path
        self.client = client
        self.copilot_cli = copilot_cli
        self.timeout = valid_timeout(timeout)
        self.registry = load_registry(registry_path)

    def reload(self) -> dict:
        updated = load_registry(self.registry_path)
        self.registry = updated
        return {"status": "rechargé", "models": len(updated["models"])}

    def route(self, **params) -> dict:
        return route(self.registry, client=self.client, copilot_cli=self.copilot_cli,
                     timeout=self.timeout, **params)


ROUTE_PARAMS = {
    "role", "story", "story_type", "files", "diff_stats", "classifier", "max_cost",
    "budget_profile", "dev_model", "dev_family", "available", "allow_preview", "pane", "name",
}


def rpc_error(identifier, code: int, message: str, *, exit_code=None) -> dict:
    error = {"code": code, "message": message}
    if exit_code is not None:
        error["data"] = {"exit_code": exit_code}
    return {"jsonrpc": "2.0", "id": identifier, "error": error}


def handle_request(router: Router, request) -> dict | None:
    if (not isinstance(request, dict) or request.get("jsonrpc") != "2.0"
            or not isinstance(request.get("method"), str)):
        return rpc_error(None, -32600, "Requête JSON-RPC 2.0 invalide.")
    identifier = request.get("id")
    if (identifier is not None and (type(identifier) not in (str, int, float)
                                    or (type(identifier) is float and not math.isfinite(identifier)))):
        return rpc_error(None, -32600, "Identifiant de requête invalide.")
    notification = "id" not in request
    method = request["method"]
    params = request.get("params", {})
    if not isinstance(params, dict):
        reply = rpc_error(identifier, -32602, "Les paramètres doivent être un objet JSON.")
    elif method not in ("route", "ping", "reload"):
        reply = rpc_error(identifier, -32601, "Méthode inconnue.")
    elif (method == "route" and ("role" not in params or params.keys() - ROUTE_PARAMS)
          or method != "route" and params):
        reply = rpc_error(identifier, -32602, "Paramètres manquants ou inconnus pour cette méthode.")
    else:
        try:
            if method == "route":
                result = router.route(**params)
            elif method == "reload":
                result = router.reload()
            else:
                result = {"status": "ok", "models": len(router.registry["models"])}
            reply = {"jsonrpc": "2.0", "id": identifier, "result": result}
        except SelectionError as exc:
            reply = rpc_error(identifier, -32000, str(exc), exit_code=exc.code)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            reply = (rpc_error(identifier, -32000, str(exc), exit_code=1) if method == "reload"
                     else rpc_error(identifier, -32602, str(exc)))
    return None if notification else reply


def reject_constant(value):
    raise ValueError(f"Constante JSON invalide : {value}.")


def serve(router: Router) -> int:
    for line in sys.stdin:
        try:
            request = json.loads(line, parse_constant=reject_constant)
        except ValueError:
            reply = rpc_error(None, -32700, "JSON illisible; fournir une requête par ligne.")
        else:
            reply = handle_request(router, request)
        if reply is not None:
            print(json.dumps(reply, ensure_ascii=False, allow_nan=False), flush=True)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=ROOT / "models.yaml", help="Registre YAML ou JSON.")
    parser.add_argument("--serve", action="store_true", help="Servir JSON-RPC 2.0 sur stdio, une requête par ligne.")
    parser.add_argument("--role", choices=ROLES, help="Rôle de l'équipier, requis hors mode serveur.")
    parser.add_argument("--story", help="Récit en texte ou @fichier UTF-8.")
    parser.add_argument("--story-type", choices=STORY_TYPES, help="Type de travail.")
    parser.add_argument("--files", type=int, help="Nombre de fichiers touchés.")
    parser.add_argument("--diff-stats", help="Résumé git diff --stat, fichier ou @fichier.")
    parser.add_argument("--classifier", choices=("heuristic", "llm"), default="heuristic", help="Heuristique sans inférence par défaut.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--max-cost", help="Plafond de crédits par tâche de référence.")
    mode.add_argument("--budget-profile", help="Profil financier du registre; la classe garde la préférence de niveau.")
    parser.add_argument("--dev-model", help="Modèle du dev pour la séparation des familles.")
    parser.add_argument("--dev-family", help="Fournisseur du dev, requis pour validation/revue si son ID est inconnu.")
    parser.add_argument("--available", help="Catalogue, @fichier, liste d'ID ou live.")
    parser.add_argument("--allow-preview", action="store_true", help="Permettre les modèles en aperçu.")
    parser.add_argument("--pane", help="Identifiant du panneau Herdr.")
    parser.add_argument("--name", help="Nom de l'agent Herdr; rôle par défaut.")
    parser.add_argument("--copilot-cli", default="copilot", help="Exécutable pour la classification LLM et le catalogue live.")
    parser.add_argument("--timeout", type=float, default=30, help="Délai Copilot par opération, en secondes.")
    parser.add_argument("--json", action="store_true", help="Produire un objet JSON pour l'orchestrateur.")
    args = parser.parse_args(argv)
    if not args.serve and args.role is None:
        parser.error("--role est requis hors mode --serve.")
    try:
        router = Router(args.registry, copilot_cli=args.copilot_cli, timeout=args.timeout)
        if args.serve:
            return serve(router)
        params = {key: getattr(args, key) for key in ROUTE_PARAMS}
        result = router.route(**params)
    except (SelectionError, ValueError, OSError, KeyError, TypeError) as exc:
        code = exc.code if isinstance(exc, SelectionError) else 1
        if args.json and not args.serve:
            print(dump_json({"error": str(exc), "exit_code": code}), end="")
        else:
            print(f"Routage impossible : {exc}", file=sys.stderr)
        return code
    if args.json:
        print(dump_json(result), end="")
    else:
        print(f"{result['level']} → {result['tier']} : {result['model']} ({result['family']})")
        print(result["reason"])
        for warning in result["warnings"]:
            print(f"À vérifier : {warning}")
        print(result["herdr_cmd"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
