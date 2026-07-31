process INTERPRET {
    tag "${report.baseName}"
    container 'llmize:latest'
    publishDir params.outdir, mode: 'copy'

    input:
    path report

    output:
    path "*_interpretation_*.md", emit: interpretation

    script:
    def home = workflow.containerEngine ? '/opt/llmize' : "${projectDir}"
    def boot = workflow.containerEngine ? "export LLMIZE_MODEL='${params.model}'\n    bash ${home}/docker/boot_ollama.sh" : ''
    def think_flag   = "${params.think}".toBoolean()        ? '--think' : '--no-think'
    def enrich_flag  = "${params.enrich}".toBoolean()       ? '--enrich' : ''
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
    ${boot}
    STAMP=\$(date +%Y%m%d_%H%M%S)
    python3 ${home}/pipeline.py \\
        --input '${report}' \\
        --model '${params.model}' \\
        --num_ctx ${params.num_ctx} \\
        ${think_flag} ${enrich_flag} ${review_flag} ${whole_flag} ${synth_flag} \\
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
