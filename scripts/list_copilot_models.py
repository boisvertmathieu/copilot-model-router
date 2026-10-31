#!/usr/bin/env python3
"""Lit models.list par le même protocole JSON-RPC que le SDK Copilot."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

from registry_lib import catalog_entries, dump_json, write_atomic


class RpcError(Exception):
    def __init__(self, code):
        # Le texte brut du serveur pourrait contenir des renseignements d'authentification.
        super().__init__(f"Requête RPC refusée (code {code}).")
        self.code = code


class LocalRpc:
    """Transport stdio cadré par Content-Length; aucun prompt ou outil n'est lancé."""

    def __init__(self, process, timeout):
        self.process = process
        self.timeout = timeout
        self.request_id = 0

    async def send(self, message):
        data = json.dumps(message, ensure_ascii=False).encode("utf-8")
        self.process.stdin.write(f"Content-Length: {len(data)}\r\n\r\n".encode("ascii") + data)
        await self.process.stdin.drain()

    async def receive(self):
        headers = {}
        while True:
            line = await self.process.stdout.readline()
            if not line:
                raise ValueError("Le CLI a fermé sa sortie avant de répondre.")
            if line in (b"\r\n", b"\n"):
                break
            name, sep, value = line.decode("ascii").partition(":")
            if not sep:
                raise ValueError("Cadrage JSON-RPC invalide reçu du CLI.")
            headers[name.casefold()] = value.strip()
        length = int(headers.get("content-length", "0"))
        if not 0 < length <= 20_000_000:
            raise ValueError("Longueur JSON-RPC absente ou hors limite.")
        return json.loads(await self.process.stdout.readexactly(length))

    async def request(self, method, params=None):
        self.request_id += 1
        request_id = self.request_id

        async def exchange():
            await self.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
            while True:
                message = await self.receive()
                if "method" in message:
                    if "id" in message:
                        # Refuse toute demande inattendue; cette commande ne sert qu'au catalogue.
                        await self.send({"jsonrpc": "2.0", "id": message["id"],
                                         "error": {"code": -32601, "message": "Méthode non prise en charge."}})
                    continue
                if message.get("id") != request_id:
                    continue
                if "error" in message:
                    raise RpcError(message["error"].get("code"))
                return message.get("result")

        return await asyncio.wait_for(exchange(), timeout=self.timeout)


async def fetch_models(cli: str, timeout: float, built_in=False) -> dict:
    command = [cli, "--headless", "--stdio", "--no-auto-update", "--log-level", "error"]
    if built_in:
        command.append("--no-auto-login")
    process = await asyncio.create_subprocess_exec(*command, stdin=asyncio.subprocess.PIPE,
                                                   stdout=asyncio.subprocess.PIPE,
                                                   stderr=asyncio.subprocess.DEVNULL)
    try:
        rpc = LocalRpc(process, timeout)
        try:
            handshake = await rpc.request("connect")
        except RpcError as exc:
            if exc.code != -32601:
                raise
            handshake = await rpc.request("ping")
        version = handshake.get("protocolVersion") if isinstance(handshake, dict) else None
        if version not in (2, 3):
            raise ValueError(f"Version de protocole non prise en charge : {version}; adapter le script au SDK courant.")
        method = "models.getBuiltInCatalog" if built_in else "models.list"
        if not built_in:
            status = await rpc.request("auth.getStatus")
            if not status or status.get("isAuthenticated") is not True:
                raise PermissionError("Aucune authentification Copilot. Lancez « copilot login » sur le poste de travail avec accès Copilot.")
        payload = await rpc.request(method)
        if built_in:
            if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
                raise ValueError("Réponse du catalogue intégré invalide.")
            entries = payload["models"]
        else:
            entries = catalog_entries(payload)
            if not entries:
                raise PermissionError(
                    "Aucun modèle accessible. Le CLI peut reconnaître un compte GitHub sans accès Copilot. "
                    "Vérifiez « copilot login », la licence et les politiques de l'organisation sur le poste de travail.")
        return {"source": method, "fetched_at": datetime.now(timezone.utc).isoformat(),
                "protocol_version": version, "models": entries}
    finally:
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except asyncio.TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                await process.wait()
        if process.stdin:
            process.stdin.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", default="copilot", help="Exécutable Copilot installé localement.")
    parser.add_argument("--timeout", type=float, default=30, help="Délai maximal par requête, en secondes.")
    parser.add_argument("--output", type=Path, help="Écrire le JSON seulement en cas de succès.")
    parser.add_argument("--built-in", action="store_true", help="Catalogue intégré hors ligne; ne prouve aucun accès au compte.")
    args = parser.parse_args(argv)
    try:
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("Le délai doit être fini et supérieur à zéro.")
        result = asyncio.run(fetch_models(args.cli, args.timeout, args.built_in))
        text = dump_json(result)
        if args.output:
            write_atomic(args.output, text)
            print(f"Catalogue écrit dans {args.output} ({len(result['models'])} ID).", file=sys.stderr)
        else:
            print(text, end="")
        return 0
    except FileNotFoundError:
        print("Copilot CLI introuvable. Installez-le sur le poste de travail, puis lancez « copilot login ».", file=sys.stderr)
    except PermissionError as exc:
        print(str(exc), file=sys.stderr)
    except (RpcError, OSError, ValueError, asyncio.TimeoutError, asyncio.IncompleteReadError) as exc:
        detail = "Délai de réponse dépassé." if isinstance(exc, asyncio.TimeoutError) else str(exc)
        print(f"Liste Copilot inaccessible : {detail} Vérifiez la version du CLI, la connexion et l'accès Copilot.", file=sys.stderr)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
