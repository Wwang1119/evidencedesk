# EvidenceDesk demo recording

Status: both real API connectivity probes passed on November 10, 2026. Full research validation and recording are pending resolution of this workstation's synthetic proxy DNS addresses, which currently cause source reachability checks to reject documents. This file is a recording plan, not evidence of a completed video.

## Record a real 2–3 minute run

1. **0:00–0:20 — User and need.** Open the local UI. Explain: “EvidenceDesk helps university students start a coursework literature review with an evidence trail behind each published claim.” Show the configured-services indicator without opening `.env` or account settings.
2. **0:20–1:10 — Question to live evidence.** Choose the RAG literature-review question and click **Build research brief**. Show planning, live Tavily search, document extraction, Nebius synthesis and support review. If waiting is edited, label the cut explicitly. Do not imply a shortened video duration is the actual latency.
3. **1:10–1:50 — Verify a claim.** Read one finding, select its numbered citation, inspect the exact quote and surrounding context, then open the original source. Use the browser's find feature to locate the passage where possible. Check whether the evidence supports the whole claim.
4. **1:50–2:20 — Evidence gaps.** Run the fictional-premise question. Show abstention or evidence limits. If the result invents support, treat that as a defect to fix before recording the final video.
5. **2:20–2:45 — Reproduce.** Show the redacted research trace, model ID and tool calls, then the public README/run commands. Mention that model review can be wrong and the tool is intended to guide source reading.

Keep the video in English. Avoid credentials, inbox contents, university email addresses, personal browser tabs and unrelated notifications. Store raw recordings under ignored `demo/recordings/`; publish only the reviewed final file or release asset. A real-time demo may exceed three minutes depending on provider latency; make any cuts transparent.

## Before publication

- Both `doctor` API probes must pass using real keys.
- Run and inspect the three examples in `examples/questions.json`.
- Open cited original pages and manually check representative claims.
- Ensure the final video is available to judges without sign-in.
- Put the verified public video URL in the repository README and submission package.
