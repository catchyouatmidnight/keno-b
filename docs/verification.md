# Verification record

Backend version: 0.1.0.

## Completed in the development workspace

- Ten integration cases pass with a deterministic simulated local model: fresh installation/auth, persistent profile after restart, corrected and expired memories across chats, SSE persistence and idempotent replay, failed/incomplete streams, retries, context limits, request-size limits, consistent backups, restart recovery, busy-slot handling, cancellation cleanup, and opt-in CLI restoration.
- Python modules compile, browser JavaScript passes Node syntax checking, and shell scripts pass `bash -n`.
- Compose YAML parses; model API has no published host port and both services use the internal network.
- OpenAPI schema and Postman collection parse as JSON.
- Dependency versions are pinned to the environment used for the integration checks.

## Not verified in this workspace

Docker is not installed here, so the images were not built or started here. The actual Qwen model was not downloaded or benchmarked. The browser binary was unavailable and its installation download failed, so visual layout and browser interaction checks were not completed. Static assets are served by the tested API, but this is not a substitute for browser testing. No claim of measured 8 GB fit, model reliability, or production readiness is made.

## Target-server acceptance

1. Run setup and `docker compose up -d --build`; check both services stay running.
2. Open the HTML console, connect with your local access key, and wait for “Model ready”.
3. Save a profile and a pinned memory. Open a new chat and ask about that fact; verify `context.memory_keys` includes it.
4. Correct the memory using its existing key. Start a new chat and confirm the model applies the correction.
5. Send a long answer request, stop it, and retry. Verify the slot becomes available and incomplete responses are not completed history.
6. Restart services and confirm the profile, memories, and conversations remain.
7. Export a backup, restore it to a separate test installation, and confirm personal state transfers while the access key remains installation-specific.
8. Check `docker stats`; adjust model/context sizing if memory is tight.
9. Verify the browser works at desktop and phone widths, the API routes work in Postman, and disconnect clears displayed personal data.
10. Inspect runtime networking on the host: neither container should have an external-egress network. Run any network-isolation probes without real personal data. Installation downloads require internet; chat does not.

Use realistic Indonesian/English questions to evaluate the actual model. Deterministic transport tests establish backend behavior, not intelligence or accuracy.
