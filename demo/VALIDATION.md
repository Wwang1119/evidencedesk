# Observed live validation — November 10, 2026

All results below used real Nebius Token Factory and Tavily calls. The model was `Qwen/Qwen3-235B-A22B-Instruct-2507`. No fixture, cached application answer or alternative inference provider supplied these results. Search providers may use their own caches.

## Connectivity and offline checks

- Nebius: generated a schema-valid JSON response through the application's provider adapter.
- Tavily: real Search passed; a separate real Extract check returned substantive official documentation.
- 36 offline tests passed, including rejection of fabricated quotes, unsupported claims, private DNS answers, unsafe redirects and malicious public-DNS responses. Tests also check IP pinning with HTTP Host/TLS SNI, native Tavily domain filters, strict model output requests and credential-free exports.

## Three-question evaluation

Run started at `2026-11-10T10:39:35Z`. Durations are actual wall-clock seconds; partial means gaps or retrieval/validation warnings remain.

| Question | Result | Claims published / withheld | Sources retrieved / cited | Time | Model tokens |
| --- | --- | --- | --- | --- | --- |
| RAG literature review | Partial | 7 / 1 | 5 / 4 | 99.81 s | 26,104 |
| Spaced retrieval for students | Partial | 7 / 1 | 4 / 2 | 79.49 s | 20,604 |
| Fictional QuasarLeaf-9000 premise | Insufficient evidence | 0 / 0 | 5 / 0 | 49.59 s | 24,931 |

Each run made three logical Tavily searches, two extraction calls and three or four Nebius calls. Token totals and timings are observations from this run, not performance promises. Local audit JSON contains service request IDs, source checks and claim-to-quote mappings; it is kept outside Git.

## Browser walkthrough

A separate focused question asked how Lewis et al.'s original RAG paper combines parametric and non-parametric memory, and what its evidence supports. The actual UI run took **44.07 s**, published **7 claims** citing **one original paper**, withheld **1 claim**, and kept **1 uncovered question facet** visible. The numbered citation opened the [actual paper on arXiv](https://arxiv.org/pdf/2005.11401), not a generated URL.

A second actual UI run challenged the fictional premise. It took **35.8 s**, published **0 claims**, and displayed insufficient evidence. The walkthrough uses captured browser frames with synthesized English narration and shortened waiting periods. Its playback duration is not the research latency.

## Manual checks and remaining limitations

- Spot-checked the original-paper architecture claim against the authors' [abstract](https://arxiv.org/abs/2005.11401) and PDF. Also inspected its retrieved passage and context in the evidence panel. The source identifies the sequence-to-sequence parametric component and a Wikipedia vector index accessed by a neural retriever.
- The broader RAG question still cited vendor commentary for some recent architecture trends. Those passages should be read as source reports, not independent experimental confirmation.
- The student-learning run retrieved a 2007 primary experiment and a 2022 secondary research summary for a question asking about recent primary research. That does not satisfy the requested recency/primary-source coverage. Its partial result and gaps should prompt further research; successful execution is not a quality pass.
- Some sources were blocked or returned insufficient extracted text. The application excluded them; it did not substitute a prewritten answer.
- Earlier real runs exposed a synthetic-proxy DNS issue and an invalid reviewer output. These failures prompted public-IP pinning with a narrowly scoped public-DNS fallback and strict JSON Schema output. Earlier failures are not counted as successful runs.
- This is a small functional evaluation and a manual spot check, not an exhaustive review, an accuracy score, a representative benchmark or a guarantee that every model-approved statement is correct. The synthesizer and reviewer share the configured model.

Credentials, billing details and university inbox contents are excluded from public artifacts.
