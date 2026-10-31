#!/usr/bin/env bash
# Rafraîchit les tarifs; importe le catalogue du compte seulement s'il est obtenu.
set -euo pipefail

racine=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
python_cmr=${PYTHON:-python3}
copilot_cmr=${COPILOT_CLI:-copilot}
catalogue_cmr=$(mktemp "${TMPDIR:-/tmp}/cmr-models.XXXXXX")
trap 'rm -f -- "$catalogue_cmr"' EXIT

options_catalogue=()
if command -v "$copilot_cmr" >/dev/null 2>&1; then
    if "$python_cmr" "$racine/scripts/list_copilot_models.py" \
        --cli "$copilot_cmr" --timeout "${CMR_COPILOT_TIMEOUT:-15}" --output "$catalogue_cmr"; then
        options_catalogue=(--from-cli-models "$catalogue_cmr")
    else
        echo "Catalogue Copilot inaccessible; synchronisation des tarifs seulement." >&2
    fi
else
    echo "Copilot CLI absent; synchronisation des tarifs seulement." >&2
fi

"$python_cmr" "$racine/scripts/sync_registry.py" "$@" "${options_catalogue[@]}"
