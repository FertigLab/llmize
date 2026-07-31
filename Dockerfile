# Ollama runtime + the llmize Python pipeline in one image.
FROM ollama/ollama:latest

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-pip curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/llmize

ARG INSTALL_ENRICH=false
RUN python3 -m pip install --no-cache-dir --break-system-packages "ollama>=0.5" \
 && if [ "$INSTALL_ENRICH" = "true" ]; then \
        python3 -m pip install --no-cache-dir --break-system-packages tooluniverse "PyYAML>=6" ; \
    fi

# TEST_MODEL is baked in for offline runs; LLMIZE_MODEL is the runtime default.
# Set BAKE_MODEL=true to also bake LLMIZE_MODEL for air-gapped use.
ARG TEST_MODEL=smollm2:135m
ARG LLMIZE_MODEL=gemma4
ENV LLMIZE_MODEL=${LLMIZE_MODEL}
ARG BAKE_MODEL=false
RUN if [ -n "$TEST_MODEL" ] || [ "$BAKE_MODEL" = "true" ]; then \
        ollama serve & srv=$! ; \
        until curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; do sleep 1; done ; \
        if [ -n "$TEST_MODEL" ]; then ollama pull "$TEST_MODEL" ; fi ; \
        if [ "$BAKE_MODEL" = "true" ]; then ollama pull "$LLMIZE_MODEL" ; fi ; \
        kill $srv ; \
    fi

COPY . .
RUN mkdir -p /opt/llmize/data && chmod -R a+rwX /opt/llmize/data \
 && chmod +x docker/boot_ollama.sh docker/entrypoint.sh

ENTRYPOINT ["/opt/llmize/docker/entrypoint.sh"]
CMD ["python3", "pipeline.py", "--check"]
