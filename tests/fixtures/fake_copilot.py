#!/usr/bin/env python3
"""Faux CLI local pour tester le protocole; aucune connexion réseau."""

import json
import os
import sys
import time

mode = os.environ.get("CMR_FAKE_MODE", "success")


def send(payload):
    data = json.dumps(payload).encode()
    sys.stdout.buffer.write(f"Content-Length: {len(data)}\r\n\r\n".encode() + data)
    sys.stdout.buffer.flush()


while True:
    line = sys.stdin.buffer.readline()
    if not line:
        break
    length = int(line.split(b":", 1)[1])
    while sys.stdin.buffer.readline() not in (b"\r\n", b"\n", b""):
        pass
    message = json.loads(sys.stdin.buffer.read(length))
    if "method" not in message:
        continue
    method = message["method"]
    if os.environ.get("CMR_FAKE_LOG"):
        with open(os.environ["CMR_FAKE_LOG"], "a", encoding="utf-8") as log:
            log.write(method + "\n")
    if mode == "timeout":
        time.sleep(5)
    if method == "connect" and mode == "legacy":
        send({"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601}})
        continue
    if method in ("connect", "ping"):
        result = {"protocolVersion": 9 if mode == "future" else (2 if mode == "legacy" else 3)}
        send({"jsonrpc": "2.0", "method": "notification.sans_effet", "params": {}})
    elif method == "auth.getStatus":
        result = {"isAuthenticated": mode != "unauthenticated"}
    elif method == "models.list":
        send({"jsonrpc": "2.0", "id": "requete-serveur", "method": "outil.interdit", "params": {}})
        result = {"models": [] if mode == "no_license" else [{"id": "gpt-6-sol", "name": "GPT-6 Sol"}]}
    elif method == "models.getBuiltInCatalog":
        result = {"models": [{"id": "integre-sans-licence"}]}
    else:
        result = {}
    send({"jsonrpc": "2.0", "id": message["id"], "result": result})
