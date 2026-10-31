"""Appels d'inférence Copilot sans outils, avec un délai pour tout le groupe."""

from __future__ import annotations

import os
import signal
import subprocess

# https://docs.github.com/en/copilot/reference/cli-command-reference
# --excluded-tools retire tous les outils intégrés documentés; --deny-tool couvre
# shell/write/read/url/memory et ses refus priment toujours sur les autorisations.
# --no-ask-user, --disable-builtin-mcps, --no-custom-instructions et -s gardent
# ces appels non interactifs et indépendants des instructions du dépôt.
COPILOT_NO_TOOLS_ARGS = (
    "--excluded-tools",
    "bash,powershell,list_bash,read_bash,stop_bash,write_bash,"
    "list_powershell,read_powershell,stop_powershell,write_powershell,"
    "apply_patch,create,edit,view,list_agents,read_agent,task,write_agent,"
    "ask_user,glob,grep,rg,skill,web_fetch",
    "--deny-tool", "shell,write,read,url,memory",
    "--no-ask-user", "--disable-builtin-mcps", "--no-custom-instructions", "-s",
)


def run_copilot(model: str, prompt: str, *, cli: str = "copilot", timeout: float = 30):
    command = [cli, "--model", model, "-p", prompt, *COPILOT_NO_TOOLS_ARGS]
    with subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, start_new_session=True) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            raise
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
