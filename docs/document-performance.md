# Streaming answers from Chat attachments

Document-only explanations, summaries and page questions use local extracted evidence directly in the streaming chat model. They do not ask the model to plan document tools before answering. Laya still chooses effort, text/vision and focused/broad scope. Requests routed to memory, calculation, live-data or mixed operations retain the tool planner.

Focused retrieval ranks matching passages and supplies at most three chunks within 2,600 extracted characters. It no longer forces unrelated cover pages into every answer. Broad summaries represent every extracted page within a 4,000-character text budget. Explicit PDF page requests select one to four pages and reject out-of-range pages. Excerpts carry filenames, page labels and truncation flags. The context-fitting pass can drop excerpts when the model context is too small; coverage metadata reports supplied and omitted pages. This is bounded evidence, not proof of a complete document review.

Document prompts skip older conversation retrieval. A short follow-up such as “tell me more” uses the previous user question for retrieval and one bounded recent exchange for context. A specific new question such as “tell me more about secure onboarding” retrieves its own topic without repeating unrelated earlier answers.

The first answer delta now reaches the browser during generation. Streaming removes waiting for the entire answer, but CPU prompt evaluation still takes time. Longer answers still take longer to finish. The encrypted Documents library has its own answer path; this change targets ordinary Chat attachments.

## Deploy and verify

```bash
cd ~/keno-b
git pull origin main
docker compose up -d --build --no-deps --force-recreate backend
```

Keep the LLM running to preserve its prefix cache. In Chat, select the PDF and ask a focused question. Then run:

```bash
bash scripts/timings.sh
```

Expected metadata: `document_answer_mode: direct_stream`, `answer_source: document_stream`, `tool_policy: document_evidence_answer`, `tool_planning_rounds: 0`, `tool_model_seconds: 0`. First-token timing should be measured during generation rather than only when the full answer is ready. Inspect the answer and source previews for factual correctness and relevant pages; routing/timing checks do not certify answer quality.

## Validation

`python tests/check_document_stream.py` runs the actual retrieval, context and generation functions with local fakes: focused retrieval, broad page coverage, explicit-page bounds, citation checks, planner bypass, deltas before final persistence and successful completion. API regression cases in `tests/test_backend.py` and `tests/test_tools.py` also check direct streaming and preserve mixed-tool isolation. Full API pytest requires the project's HTTP dependencies and pytest.
