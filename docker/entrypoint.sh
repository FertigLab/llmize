#!/usr/bin/env bash
# Image ENTRYPOINT for plain `docker run`: boot Ollama, then run the given command.
# (Nextflow overrides the entrypoint, so its process script calls boot_ollama.sh itself.)
set -euo pipefail

source /opt/llmize/docker/boot_ollama.sh

# Default to the env preflight if no command was given.
if [ "$#" -eq 0 ]; then
    exec python3 /opt/llmize/pipeline.py --check
fi
exec "$@"
