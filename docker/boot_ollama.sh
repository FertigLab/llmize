#!/usr/bin/env bash
# Start the in-container Ollama server, wait for it, and pull the model.
#
# Reusable so both the image ENTRYPOINT (docker run) and the Nextflow process
# script can call it. The server is started with nohup + disown so it survives
# this script exiting and is reachable by later commands in the same task.
#
# Honours:
#   LLMIZE_MODEL  - model tag to pull/run (default: gemma4)
#   OLLAMA_HOST   - server/client endpoint (default: 127.0.0.1:11434)
set -euo pipefail

MODEL="${LLMIZE_MODEL:-gemma4}"
ENDPOINT="http://${OLLAMA_HOST:-127.0.0.1:11434}"

# Start the server only if one isn't already answering.
if ! curl -sf "${ENDPOINT}/api/tags" >/dev/null 2>&1; then
    echo "[boot] starting 'ollama serve'..."
    nohup ollama serve >/tmp/ollama.log 2>&1 &
    disown || true
fi

echo "[boot] waiting for Ollama at ${ENDPOINT} ..."
for i in $(seq 1 60); do
    if curl -sf "${ENDPOINT}/api/tags" >/dev/null 2>&1; then
        break
    fi
    sleep 1
    if [ "$i" -eq 60 ]; then
        echo "[boot] ERROR: Ollama did not become ready in 60s" >&2
        cat /tmp/ollama.log >&2 || true
        exit 1
    fi
done

# Skip the pull if the model is already present (baked into the image, or cached
# on a mounted volume). This is what makes an offline / air-gapped image work:
# 'ollama pull' would otherwise contact the registry even for an existing model.
if ollama list 2>/dev/null | grep -qF "${MODEL}"; then
    echo "[boot] model '${MODEL}' already present; skipping pull (offline-safe)."
else
    echo "[boot] pulling model '${MODEL}' (runtime pull; needs network)..."
    ollama pull "${MODEL}"
fi
echo "[boot] ready."
