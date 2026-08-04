process INTERPRET {
    tag "${report.baseName}"
    label "process_gpu"
    resourceLimits cpus: 4, memory: 24.GB, time: '1h'
    //container 'ghcr.io/fertiglab/llmize:latest'
    container 'ghcr.io/fertiglab/llmize:sha-f2ae922'
    publishDir params.outdir, mode: 'copy'

    input:
    path report

    output:
    path "*_interpretation_*.md", emit: interpretation

    script:
    def home = workflow.containerEngine ? '/opt/llmize' : "${projectDir}"
    def boot = workflow.containerEngine ? "export LLMIZE_MODEL='${params.model}'\n    bash ${home}/docker/boot_ollama.sh" : ''
    def ollama_models_escaped = params.ollama_models_dir ? params.ollama_models_dir.toString().replace("'", "'\"'\"'") : null
    def ollama_models_export = ollama_models_escaped ? "export OLLAMA_MODELS='${ollama_models_escaped}'" : 'export OLLAMA_MODELS="\$PWD/ollama/models"'
    def think_flag   = "${params.think}".toBoolean()        ? '--think' : '--no-think'
    def review_flag  = "${params.review}".toBoolean()       ? "--review --review-passes ${params.review_passes}" : ''
    def whole_flag   = "${params.whole_report}".toBoolean() ? '--whole-report' : ''
    def synth_flag   = "${params.synthesis}".toBoolean()    ? '' : '--no-synthesis'
    def prompt_escaped = params.prompt ? params.prompt.toString().replace("'", "'\"'\"'") : ''
    def prompt_flag  = params.prompt ? "--prompt '${prompt_escaped}'" : ''
    def temp_flag    = params.temperature != null ? "--temperature ${params.temperature}" : ''
    def seed_flag    = params.seed        != null ? "--seed ${params.seed}" : ''
    def top_p_flag   = params.top_p       != null ? "--top_p ${params.top_p}" : ''
    def top_k_flag   = params.top_k       != null ? "--top_k ${params.top_k}" : ''
    def numpred_flag = params.num_predict != null ? "--num_predict ${params.num_predict}" : ''
    """
    export HOME="\$PWD"
    export XDG_CACHE_HOME="\$PWD/.cache"
    ${ollama_models_export}
    mkdir -p "\$OLLAMA_MODELS" "\$XDG_CACHE_HOME"

    ${boot}

    STAMP=\$(date +%Y%m%d_%H%M%S)
    python3 ${home}/pipeline.py \\
        --input '${report}' \\
        --model '${params.model}' \\
        --num_ctx ${params.num_ctx} \\
        --work-dir . \\
        ${think_flag} ${review_flag} ${whole_flag} ${synth_flag} \\
        ${prompt_flag} ${temp_flag} ${seed_flag} ${top_p_flag} ${top_k_flag} ${numpred_flag} \\
        --output "${report.baseName}_interpretation_\${STAMP}.md"
    """
}

workflow {
    if( !params.input )
        error "Provide --input <multiqc_data.json>"

    ch_input = channel.fromPath(params.input, checkIfExists: true)

    INTERPRET(ch_input)
}
