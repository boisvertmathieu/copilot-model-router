#!/usr/bin/env python3
"""Observe le transport du CLI sur un serveur local avec un jeton factice."""

import argparse
import asyncio
import contextlib
import json
import os
import sys
import tempfile
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from list_copilot_models import LocalRpc
from registry_lib import dump_json, write_atomic

# Ce texte est créé ici pour la simulation; il ne donne accès à aucun compte.
FAKE_TOKEN = "gho_FAUX_JETON_POUR_SERVEUR_LOCAL"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", required=True, help="Chemin du CLI Copilot à inspecter.")
    parser.add_argument("--cache-dir", type=Path, help="Cache temporaire déjà extrait, facultatif.")
    parser.add_argument("--output", type=Path, required=True, help="Fichier JSON de constat local.")
    args = parser.parse_args()
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            headers = dict(self.headers)
            if "authorization" in headers:
                headers["authorization"] = "Bearer <jeton-factice>"
            # Les identifiants aléatoires de la machine et de l'appel ne sont pas utiles à la preuve.
            for key in ("x-client-machine-id", "x-interaction-id", "host"):
                if key in headers:
                    headers[key] = "<valeur-locale-omise>"
            requests.append({"method": "GET", "path": self.path, "headers": headers})
            payload = {"data": [{
                "id": "gpt-6-sol", "name": "GPT-6 Sol", "vendor": "OpenAI",
                "model_picker_enabled": True, "policy": {"state": "enabled", "terms": ""},
                "capabilities": {"type": "chat", "supports": {}, "limits": {}},
            }]} if self.path.startswith("/models") else {}
            data = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_CONNECT(self):
            # Toute tentative HTTPS par le proxy local est refusée et consignée.
            requests.append({"method": "CONNECT", "path": self.path})
            self.send_error(502)

        def log_message(self, *args):
            pass

    with tempfile.TemporaryDirectory(prefix="cmr-sonde-") as folder:
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        # Une liste fermée évite d'hériter des jetons et des profils de l'utilisateur.
        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8",
            "XDG_CACHE_HOME": str(args.cache_dir or Path(folder) / "cache"),
            "COPILOT_HOME": str(Path(folder) / "profil"), "CMR_RESEARCH_TOKEN": FAKE_TOKEN,
            "COPILOT_API_URL": base, "COPILOT_DEBUG_GITHUB_API_URL": base,
            "HTTP_PROXY": base, "HTTPS_PROXY": base, "NO_PROXY": "127.0.0.1,localhost",
        }

        async def probe():
            process = await asyncio.create_subprocess_exec(
                args.cli, "--headless", "--stdio", "--no-auto-update", "--no-auto-login",
                "--auth-token-env", "CMR_RESEARCH_TOKEN", "--log-level", "error",
                "--disable-client-telemetry", env=environment,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL)
            try:
                rpc = LocalRpc(process, 15)
                connection = await rpc.request("connect")
                result = await rpc.request("models.list")
                return connection, len(result.get("models", []))
            finally:
                with contextlib.suppress(ProcessLookupError):
                    process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), 3)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()

        try:
            connection, count = asyncio.run(probe())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
    if not any(request["path"] == "/models" for request in requests):
        raise RuntimeError("Aucun appel /models observé sur le serveur local.")
    if any(request["method"] == "CONNECT" for request in requests):
        raise RuntimeError("Une tentative de connexion externe a été bloquée; inspecter le CLI avant de conclure.")
    write_atomic(args.output, dump_json({
        "source": "simulation_http_locale", "observed_at": datetime.now(timezone.utc).isoformat(),
        "cli_version": connection.get("version"), "protocol_version": connection.get("protocolVersion"),
        "response_is_synthetic": True, "rpc_model_count": count,
        "note": "Faux jeton et réponses simulées. Aucun catalogue de compte Copilot réel ni inférence.",
        "requests": requests,
    }))
    print(f"Observation locale écrite dans {args.output}.")


if __name__ == "__main__":
    main()
