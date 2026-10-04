# Verification record

Backend version: 0.2.0.

Thinking-budget regression: quick choices reserve/send 0 tokens, uncertain deep choices reserve/send 96, and confident deep choices reserve/send 384. Tested against the simulated model; actual latency and answer quality require deployment evaluation.

## Completed in the development workspace

- Seventeen integration cases pass with deterministic simulated Qwen and Laya services: fresh installation/auth, persistent profile after restart, corrected and expired memories across chats, SSE persistence and idempotent replay, failed/incomplete streams, retries, context limits, request-size limits, consistent backups, restart recovery, busy-slot handling, cancellation cleanup, opt-in CLI restoration, automatic quick/deep routing, low-confidence quick/deep choices, single-question plain-chat routing without assistant-output contamination, hidden-reasoning timing without storing its contents, router failure cleanup, local PDF/DOCX extraction, an 11-page vague-request regression that samples pages 1/3/5/7/9/11 instead of only early pages, conversation-scoped file references, image/page payloads, upload bounds, and backups containing attachments, and schema-1 backup migration preserving personal state.
- Python modules compile, browser JavaScript passes Node syntax checking, and shell scripts pass `bash -n`.
- Compose YAML parses; model API has no published host port and backend, Qwen and Laya use only the internal network; only the gateway publishes a port.
- OpenAPI schema and Postman collection parse as JSON.
- Backend test dependencies are pinned. Native extraction/rendering tests use Pillow 12.3.0 and PDFium 5.3.0. The separate Laya runtime dependencies are pinned but its image has not been built here.

## Not verified in this workspace

Docker is not installed here, so the images were not built or started here. The actual Qwen and Laya checkpoints were not downloaded or benchmarked. No actual Laya route accuracy, checkpoint startup, vision quality or latency has been verified. The browser binary was unavailable and its installation download failed, so visual layout and browser interaction checks were not completed. Static assets are served by the tested API, but this is not a substitute for browser testing. No claim of measured 8 GB fit, model reliability, or production readiness is made.

## Target-server acceptance

1. Run setup and `docker compose up -d --build`; check all four services stay running.
2. Open the HTML console, connect with your local access key, and wait for “Model ready”.
3. Save a profile and a pinned memory. Open a new chat and ask about that fact; verify `context.memory_keys` includes it.
4. Correct the memory using its existing key. Start a new chat and confirm the model applies the correction.
5. Send a long answer request, stop it, and retry. Verify the slot becomes available and incomplete responses are not completed history.
6. Restart services and confirm the profile, memories, and conversations remain.
7. Export a backup, restore it to a separate test installation, and confirm personal state transfers while the access key remains installation-specific.
8. Check `docker stats`; adjust model/context sizing if memory is tight.
9. Verify the browser works at desktop and phone widths, the API routes work in Postman, and disconnect clears displayed personal data.
10. Inspect runtime networking on the host: backend, Qwen and Laya should have no external-egress network. Run any network-isolation probes without real personal data. Installation downloads require internet; chat does not.

Use realistic Indonesian/English questions to evaluate the actual model. Deterministic transport tests establish backend behavior, not intelligence or accuracy.

## Analysis-profile acceptance

- Compare a greeting with a multi-step comparison request. Inspect `context.route` to confirm the actual Laya engine is responding; evaluate its choices and confidence rather than assuming the mock test validates model accuracy.
- Upload a PDF with known text. Ask a targeted question, then an overview; check reported source pages and actual facts.
- Upload a known photo and a scanned page. Check that `visual_sources` identifies them and the answer describes the actual image. Ask for a specific PDF page.
- Monitor `docker stats` during Laya startup, routing and vision encoding. The 3 GB Laya ceiling allows loading overhead; it is not measured RAM use.
- Confirm a simple request disables thinking and a complex one enables it in the actual llama.cpp runtime, without a user toggle. Only final answer content should appear in the console/history.
- Export and validate a backup with attachments; restore it in a separate installation and re-query a stored file.
