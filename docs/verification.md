# Verification record

Backend version: 0.3.0.

Thinking-budget regression: quick choices reserve/send 0 tokens, uncertain deep choices reserve/send 96, and confident deep choices reserve/send 384. Tested against the simulated model; actual latency and answer quality require deployment evaluation.

## Completed in the development workspace

- Twenty-seven integration cases pass with deterministic simulated Qwen and Laya services: fresh installation/auth, persistent profile after restart, corrected and expired memories across chats, SSE persistence and idempotent replay, failed/incomplete streams, retries, context limits, request-size limits, consistent backups, restart recovery, busy-slot handling, cancellation cleanup, opt-in CLI restoration, automatic quick/deep routing, low-confidence quick/deep choices, two-question plain-chat routing without assistant-output contamination, hidden-reasoning timing without storing its contents, router failure cleanup, local PDF/DOCX extraction, an 11-page vague-request regression that samples pages 1/3/5/7/9/11 instead of only early pages, conversation-scoped file references, image/page payloads, upload bounds, and backups containing attachments, and schema-1 backup migration preserving personal state.
- Additional native-tool transport checks cover staged memory save/correction/forget, idempotent replay, failed-stream/cancellation rollback, explicit-only settings, exact-current-message evidence validation, decimal arithmetic and code rejection, all 11 extracted PDF pages and authenticated previews, unselected-file rejection, compact history/retrieval and cascade deletion, schema-2 migration, disabled-by-default live lookups, current-request-only outbound inputs, unknown tool rejection and two-round bounds. Optional lookup tests verify authentication, fixed provider destinations, query-only payloads, snippet filtering and malformed provider responses.
- Console Markdown and reconnect checks pass with `node tests/test_console.js`: headings, emphasis, code blocks, tables and safe links render through DOM nodes; raw HTML/scripts/images do not execute/load; the saved access key reconnects and disconnect clears it. These are simulated DOM tests.
- Console authentication flows pass under simulated DOM/fetch/browser-storage objects: save after valid authentication, reconnect on reload, disconnect/forget, clear rejected keys, retain keys during server outages, and remain usable when persistent storage is blocked. This is not a real-browser interaction test.
- Python modules compile, browser JavaScript passes Node syntax checking, and shell scripts pass `bash -n`.
- Compose YAML parses; model API has no published host port and backend, Qwen and Laya use only the internal network; only the gateway publishes a port.
- OpenAPI schema and Postman collection parse as JSON.
- Backend test dependencies are pinned. Native extraction/rendering tests use Pillow 12.3.0 and PDFium 5.3.0. The separate Laya runtime dependencies are pinned but its image has not been built here.

## Not verified in this workspace

Docker is not installed here, so the images were not built or started here. The actual Qwen and Laya checkpoints were not downloaded or benchmarked. No actual Laya route accuracy, native Qwen tool-selection accuracy, checkpoint startup, vision quality or latency has been verified. Optional live Docker services and real external provider requests have not been started here. Official llama.cpp b11146 source confirms /apply-template uses the same OpenAI chat parser including tools; this does not replace a real checkpoint acceptance test. The browser binary was unavailable and its installation download failed, so visual layout and browser interaction checks were not completed. Static assets are served by the tested API, but this is not a substitute for browser testing. No claim of measured 8 GB fit, model reliability, or production readiness is made.

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

## Tool-profile acceptance

1. Back up before upgrading; schema 3 requires a pre-upgrade backup to roll back to 0.2. Rebuild the backend and hard-refresh the console once. Existing key persistence should reconnect.
2. Introduce yourself, inspect Tools activity and Memories, then start a new chat and ask your name. Correct it and verify the same key updates. Ask to forget it. Evaluate actual model choices in Indonesian and English; transport mocks do not prove extraction quality.
3. Disable automatic memory, make an introduction and verify no save; explicitly ask to remember and verify it can save. Stop a tool-assisted reply before completion and confirm staged facts do not persist.
4. Ask a calculation, inspect the tool trace and result. A greeting should route to none and skip the planner. Compare timings.sh before/after; planner calls add overhead.
5. Upload an 11-page known PDF. Request an overview, check coverage/shortening in actual results, open source page 11, and ask a targeted late-page question. Scanned pages still require bounded vision; full OCR is absent.
6. Create a long chat, verify recent turns <=4 and relevant older retrieval where words match. Compact notes are incomplete excerpts. Verify backup/restore transfers them.
7. Keep live settings off and confirm no lookup calls. Optionally run enable-live.sh, enable weather, ask for weather in an explicit city, and inspect matched location/forecast timestamp. Enable search, request a public phrase and inspect links. Test missing service/provider errors and disable settings again.
8. Inspect the final network configuration: inference services internal only, lookup bridging only when the live profile is started, search on edge only, no additional host ports. Check total RAM with optional services running.
