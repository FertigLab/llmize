#!/usr/bin/env bash
# Start the in-container Ollama server and pull the model. nohup + disown let the
# server survive this script exiting so later commands in the task can reach it.
# Honours LLMIZE_MODEL (default gemma4) and OLLAMA_HOST (default 127.0.0.1:11434).
set -euo pipefail

MODEL="${LLMIZE_MODEL:-gemma4}"
ENDPOINT="http://${OLLAMA_HOST:-127.0.0.1:11434}"

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

# Skip the pull when the model is already present (baked in or volume-cached) so the
# image works offline; 'ollama pull' would otherwise contact the registry regardless.
if ollama list 2>/dev/null | grep -qF "${MODEL}"; then
    echo "[boot] model '${MODEL}' already present; skipping pull (offline-safe)."
else
    echo "[boot] pulling model '${MODEL}' (runtime pull; needs network)..."
    ollama pull "${MODEL}"
fi
echo "[boot] ready."
