# Keno backend

A self-hosted personal assistant with a local LLM, persistent personal data, and a browser test console. Android will connect to this API later. Version 0.3.2 includes bounded tool calling, automatic memory, broader document coverage, compact history, Markdown answers, and optional live lookups. Android comes later.

## Start on a Linux server

Requires Docker Engine with Compose v2, Python 3 for the optional model download, and Linux x86-64 or ARM64. An 8 GB machine is the initial target, not a measured performance guarantee. Leave approximately 12 GB of disk space for images, model files, and backups. CPU speed matters; one response runs at a time.

```bash
git clone https://github.com/catchyouatmidnight/keno-b.git
cd keno-b
bash scripts/setup.sh --download-model
docker compose up -d --build
```

Check `docker compose port gateway 8080` and `curl http://127.0.0.1:8080/health` to verify the published web port. On upgrades, run `docker compose up -d --force-recreate` so the gateway is created and the obsolete backend port mapping is removed.

Open **http://localhost:8080**. Copy `KENO_API_KEY` from your local `.env` into the page’s access-key field. The page includes chat, memories, your profile, personality settings, backup download, and an API reference. After a successful connection, the key is saved in this browser’s local storage for this site address, and the page reconnects automatically on reload. Use **Disconnect & forget key** to remove it. A rejected key is also removed; temporary server outages retain it. If browser storage is blocked, the page reports that the key can only be used in the current tab. The server key remains in `.env`; no key is embedded in the published assets.

Setup preserves existing `.env` and `data/`. On a genuinely new installation, the profile, memories, and history are empty; the assistant is named Keno. The pretrained base model still has general knowledge. No personal facts are embedded in the repository. No retraining runs during setup or normal chat.

The backend may be ready before Qwen finishes loading. Check the status badge, `GET /api/v1/status`, or:

```bash
docker compose ps
docker compose logs --tail=80 llm
docker compose logs --tail=80 backend
```

If `llm` restarts, its error log should now explain why. A GPU warning is not fatal for the CPU image. Check that the configured GGUF exists in `models/` (the default Qwen 2B file is approximately 1.28 GB, with a separate 668 MB vision projector), and inspect the last exit state:

```bash
ls -lh models/
docker inspect keno-llm-1 --format 'ExitCode={{.State.ExitCode}} OOMKilled={{.State.OOMKilled}} Error={{.State.Error}}'
```

For missing default assets, run `python3 scripts/download-model.py --vision --laya`, then `docker compose up -d --force-recreate llm`. Exit code 1 alone does not identify the cause; use the error log. The pinned runtime uses `--reasoning auto`; Laya makes the decision per request. `--offline` prevents runtime model downloads. Laya has offline Hugging Face/Transformers flags and reads only its mounted checkpoint.

### Access a remote server from your computer

The default port binds only to server loopback. Use an SSH tunnel, then open localhost on your computer:

```bash
ssh -L 8080:127.0.0.1:8080 YOUR_USER@YOUR_SERVER
```

For later Android access, put the backend behind a TLS reverse proxy or a private encrypted connection. Set `BIND_ADDRESS` to the appropriate private interface only if needed, and retain bearer authentication. This package does not provision public TLS or an Android pairing system. Plain HTTP on a public interface exposes personal content and credentials in transit.

## Upgrade an existing Keno installation

The previous 4B `.env` is preserved by setup. Explicitly switch to this analysis profile, download its assets, then rebuild the changed services:

```bash
cd ~/keno-b
git pull origin main
python3 scripts/download-model.py --model 2b --vision --laya
python3 scripts/enable-analysis.py
docker compose up -d --build --force-recreate
docker compose ps
docker compose logs --tail=80 laya llm backend
```

`enable-analysis.py` updates only the model, matching projector and context size. It preserves the access key, port (including `PORT=18081`), bind address and personal data. The existing 4B GGUF is not deleted. The database migrates from schema 1 to schema 2 on startup; older backups can still be restored and migrated. A v0.1 backend cannot read the newer schema, so export a pre-upgrade backup if you need to return to v0.1.

Refresh the console with Ctrl+F5. Your existing SSH tunnel remains valid. For this VPS's loopback port 18081, an example is:

```bash
ssh -N -o ExitOnForwardFailure=yes -L 19081:127.0.0.1:18081 ubuntu@51.79.240.119
```

Open `http://127.0.0.1:19081`. The new status badge checks both model and router readiness.

## Automatic decisions and attachments

Laya is the actual local multilingual decision checkpoint from [NandhaKishorM/laya](https://github.com/NandhaKishorM/laya). For plain chat it first evaluates only two choices: quick/deep effort and answer-only versus tool action. If an action is needed, a second local request selects the tool family; answer-only turns skip family classification entirely. An answer-only decision disables tool planning; no family confidence is invented for a decision that was not requested. This binary check is also made by Laya, not a keyword router. Advice uses one local request with two heads. Action turns use two local requests with three heads in total, which can increase their routing overhead. `question_count` counts all heads and `call_count` counts local router requests; compare both on the VPS before claiming a speedup. With attachments it uses four choices: effort, family, text/vision evidence, and focused/overview document selection; the answer-only gate is not used for file requests. The latest user request, up to 600 characters from two earlier user requests, and attachment metadata are the decision input. Earlier assistant outputs are excluded from routing; Qwen still receives the normal conversation history. Document contents are processed locally by Qwen. Laya never generates the user-facing answer. There is no thinking button or API override.

Laya selects effort; the backend uses a latency policy that enables deep thinking only when the chosen deep answer has confidence at least 0.65. Lower-confidence decisions use quick mode, with the raw decision and `effort_policy=uncertain_quick` retained for inspection. A truncated long request still gets deeper thinking. Routine device instructions are described to Laya as quick general advice with no tool action; mentioning a device in a question is not a memory declaration. Images and textless PDFs require vision even when the router selects text. A failed or invalid router response produces HTTP 503 rather than silently substituting another engine. Inspect `context.route` for choices, confidence, routing time and the effective mode. These are zero-shot decisions and need evaluation on your own requests; probabilities are not a guarantee of correctness.

Thinking consumes extra time. Quick mode uses zero hidden-thinking tokens; truncated requests use a 96-token cap; confident deep decisions use a 384-token cap. Confidence is a routing heuristic, not a validated guarantee; defaulting uncertain requests to quick can reduce reasoning quality on difficult tasks. Uncertainty includes confidence below 0.65 or a truncated routing request. The API reserves the selected cap in addition to the requested answer limit and sends that same cap to llama.cpp. The shorter cap can shorten analysis, so evaluate answer quality on your actual tasks. llama.cpp separates reasoning into its reasoning field; Keno reads and saves only answer content. Choosing a smaller model can reduce inference time, but adding Laya does not guarantee lower end-to-end latency.

Use the file picker in Chat and select up to four stored attachments per request. Supported files: PDF, DOCX, UTF-8 TXT/MD/CSV, PNG/JPG/WebP. Each file is limited to 8 MB, PDFs to 100 pages, extracted text to 200,000 characters, each chat to eight files, and total raw/extracted attachment storage to 128 MB. Files are stored inside SQLite and included in backups. Deleting a chat deletes its attachments and compact notes; saved memories remain.

The server extracts document text locally and retrieves at most six 1,000-character excerpts using Unicode keyword overlap after removing common English/Indonesian query words, or evenly spaced excerpts when Laya chooses an overview or there are no informative matches. The attachment prompt identifies supplied excerpts/images as locally available file contents, asks for filename/page citations, and separates document claims from recommendations. Document tools can then search, read up to four requested pages, or build an overview representing every page with extracted text within a shared 12,000-character budget. Longer page text is shortened and missing/scanned pages are reported. This is lexical retrieval and bounded page coverage; semantic embeddings and exhaustive whole-document review are not implemented. Source buttons open an authenticated local page preview. Up to two images/PDF pages are included for vision, resized to fit a 1,120-pixel side and capped at 1,024 image tokens each in llama.cpp. Ask for a specific page (`page 7` / `halaman 7`) when needed. Scanned PDFs default to their first two pages; extracting every scanned page with OCR is not implemented. Detailed charts, tiny text, long documents and reasoning still need accuracy checks.

Response context lists `document_sources`, `visual_sources` and selected attachment IDs; the console shows filenames/pages. Evidence may be trimmed further to fit the context. Image token counts use a conservative reserve rather than the text tokenizer; the model server enforces the actual image limit. If your request itself does not fit, the API returns 422.

For API uploads, POST this JSON to `/api/v1/attachments`:

```json
{"conversation_id":"YOUR_CONVERSATION_ID","name":"report.pdf","data_base64":"BASE64_FILE_BYTES"}
```

Pass the returned IDs as `attachment_ids` in `/api/v1/chat`. An empty list means no files. Omitting the field selects the latest four files in that conversation. Attachments from another conversation are rejected; external image URLs are not accepted. Reuse the same selected IDs when retrying the same request ID.

## API / Postman

All `/api/v1/*` routes require `Authorization: Bearer YOUR_KEY`. `/health` exposes only backend liveness and version. Download the OpenAPI JSON from the browser’s API tab and import it into Postman, or import `docs/keno.postman_collection.json` and set `base_url` and `api_key` locally. Do not share an environment containing your real key.

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/health` | Backend liveness (not model readiness) |
| GET | `/api/v1/status` | Model readiness, busy state, and configuration |
| GET / PUT | `/api/v1/tools/settings` | Automatic memory / opt-in weather and search |
| GET | `/api/v1/attachments/{id}/pages/{page}` | Authenticated local source preview |
| GET / PUT | `/api/v1/profile` | Read/replace personal profile |
| GET / PUT | `/api/v1/identity` | Read/replace personality |
| GET | `/api/v1/memories?q=...&limit=100` | Search active memories |
| PUT / DELETE | `/api/v1/memories/{key}` | Save/correct or remove a memory |
| POST / GET | `/api/v1/conversations` | Create/list chats |
| GET / DELETE | `/api/v1/conversations/{id}` | Read/delete a chat |
| POST | `/api/v1/chat` | JSON response or SSE stream, automatic thinking |
| POST | `/api/v1/attachments` | Upload a file as base64 JSON |
| GET | `/api/v1/conversations/{id}/attachments` | List file metadata |
| DELETE | `/api/v1/attachments/{id}` | Delete a stored attachment |
| GET | `/api/v1/backup` | Download a consistent SQLite snapshot |
| GET | `/api/v1/openapi.json` | Machine-readable API schema |

Example workflow (use your own key):

```bash
export KENO_KEY='YOUR_KEY'
curl http://localhost:8080/api/v1/conversations \
  -H "Authorization: Bearer $KENO_KEY" -H 'Content-Type: application/json' \
  -d '{"title":"First chat"}'
```

Copy the returned `id` into the next request:

```bash
curl http://localhost:8080/api/v1/chat \
  -H "Authorization: Bearer $KENO_KEY" -H 'Content-Type: application/json' \
  -d '{"conversation_id":"YOUR_CONVERSATION_ID","message":"Hello!","request_id":"first-message-001","stream":false}'
```

Set `stream:true` and use `curl -N` for SSE. Events are `context`, `tool`, `timing`, `delta`, `done`, and `error`. Tool events contain the allowlisted name, index and status, never hidden reasoning. Only `done` confirms a persisted answer. `finish_reason:length` means the response reached its output limit. The console warns when this happens. Select a longer output for website/code generation: 512, 1,024, 2,048, or 3,072 tokens. The API defaults to 512 and permits up to 3,072 through `max_tokens`; larger outputs leave less room for profile and history within the 8,192-token default context. If the remaining mandatory prompt does not fit, the API returns 422 rather than silently discarding your profile. Stream failures use an `error` event after HTTP headers have been sent. Non-streaming failures use HTTP 502/503.

Clients should supply a unique `request_id` per message and reuse it when retrying that message. Completed requests replay the saved answer without running inference again; using the ID with different text or a different conversation returns 409. Failed turns are retryable. One generation runs at a time; concurrent chat requests return 409 with `Retry-After`, rather than growing a RAM-consuming queue. The backend must run with **one Uvicorn worker / one replica**. A restart marks unfinished turns failed. Partial streamed answers are not retained as completed history.

## How personal continuity works

The system combines the assistant identity, your profile, selected memories, and recent completed turns with each new message. Profile and identity are always included. Up to eight active memories are selected using pinned priority and local Unicode keyword overlap after removing common query words. The `user.name` memory is retrieved only when relevant instead of being inserted into every unrelated prompt; other pinned preferences remain available. A misplaced English 'Your name is …' preamble in an earlier unrelated answer is omitted from model context when followed by more answer text; the stored transcript is unchanged. Actual name questions retain their answers and cross-chat name recall. No embedding model or external search service is required. Expired memories are excluded. Recent history is limited to four completed turns, plus compact extractive notes from up to ten preceding turns and up to two lexically relevant excerpts from the last 200 older turns in the same chat. These incomplete notes are excerpts, not a generated summary, and need no extra model call. All context is trimmed by the model tokenizer, reserving answer/thinking tokens. If necessary, memories are also trimmed; `context.memory_keys` reports exactly which ones were included. Older full turns remain in SQLite. Cross-chat continuity uses saved memories and profile rather than searching every conversation.

Use **About you** for stable background and global preferences. Use **Memories** for lasting facts, projects, and dated decisions. Reusing the same memory key replaces its old value. Example:

```json
{
  "key": "preferred_language",
  "content": "I prefer Indonesian for casual conversation.",
  "category": "preference",
  "pinned": true,
  "source_conversation_id": null,
  "expires_at": null
}
```

PUT it to `/api/v1/memories/preferred_language`. Expiry must be an ISO timestamp with timezone. A source conversation can be attached when saving a fact. Deleting a chat preserves saved memories but clears their source reference. Deleting a memory does not erase historical chat messages that mention it; remove those conversations separately if needed.

Automatic memory is enabled by default in Tools. Laya selects a tool family; Qwen chooses allowlisted calls and quotes a lasting fact directly from your current message. An explicit follow-up such as “save” or “remember that” may quote one of the last four completed user messages in the same chat. Case/whitespace-insensitive matching preserves the original source text. Memory-save turns acknowledge the staged result directly, and failed tool traces include a safe validation reason. Assistant text, other chats, and earlier requests not to save are excluded. Corrections should reuse its existing key, and deletion requires an explicit request. Writes commit in the same SQLite transaction as a completed answer; cancelled/failed answers leave memories untouched. A length-limited answer is still completed and can commit its staged writes. Inspect or correct facts in Memories: quote validation prevents invented evidence, but the model can still misclassify a real user statement. Disable automatic memory to allow writes only for explicit save/forget requests. Canonical name/language facts are pinned. No model can guarantee identical wording or reliable reasoning merely because memories are supplied.

## Tools and optional live information

Laya chooses `none`, `memory`, `documents`, `calculator`, `live`, or `multiple`; Qwen uses native llama.cpp tool calls for that family. There are at most two planning rounds and four calls per request, with strict argument validation. The final answer streams after the tool phase. Ordinary chats routed to `none` skip planning. Tool requests add model inference and can take longer on CPU; `tool_seconds` separates this overhead from answer timing. Memory/document results and web snippets are treated as reference data, not instructions. The calculator accepts bounded numeric arithmetic, never Python execution or shell commands.

Weather and web search are **off by default**. Simple current-weather questions use a backend answer guard: disabled lookup settings return an explanation, missing/invalid cities ask for a city, unavailable lookups report failure, and successful results are rendered directly from returned temperature/location/time fields. These replies cannot fall through to invented model weather JSON. Broader conceptual/document questions retain the normal model answer path. If you want them, start the optional services:

```bash
bash scripts/enable-live.sh
```

Then connect to the console, open **Tools**, enable the desired lookup, and save. The script creates a local random SearXNG secret and starts `lookup` and `search`; it does not turn on the user settings. Disable the checkboxes to stop calls, or stop optional services with `docker compose --profile live stop lookup search`.

Weather sends only a city verbatim from the current request to Open-Meteo geocoding, then the matched coordinates to its forecast API. Confirm the returned location when a city name is ambiguous. Search sends only a verbatim search phrase from the current request to self-hosted SearXNG, whose configured search engines receive it. Providers receive that query and ordinary connection metadata, not the full prompt, memories, profile, or files. If you include private text in a search request, that chosen phrase can leave the server. The backend rejects queries supplied only by a profile, memory or attachment. Search returns up to five snippets and links; it does not fetch or verify linked pages. Clicking external source links opens those websites in your browser. Weather data is a model estimate, not a local sensor reading.

The lookup service alone bridges private and egress networks. Search has egress access and no database/model mounts or published port. Backend/Qwen/Laya remain private. SearXNG's optional image defaults to the official `latest`; set `SEARXNG_IMAGE` to your tested digest for reproducibility. Optional lookup/search memory ceilings are 192 MB/512 MB; measure total RAM on the target server.

## Privacy

The backend, Qwen model and Laya router share a Docker network marked `internal:true`; none is attached to an external-egress network. An optional lookup service is the only application path for explicitly enabled weather/search. A small Nginx gateway joins that private network and a separate bridge network so Docker can publish the web port reliably. Only the gateway port is published; the backend and raw model API are not exposed directly. The gateway forwards requests only to the backend, has no analytics, and has no mounted database/model files. It does have a bridge network with external connectivity; runtime egress isolation applies to the backend, Qwen and Laya, not to the gateway. The backend accepts only the local `llm` / `laya` services or loopback as its model/router URLs, ignores HTTP proxy environment variables, and never calls an external LLM provider. There are no analytics, remote fonts, external UI scripts, or automatic cloud backups. Personal prompts are not written to access logs; llama logs only generic output and errors by default, so startup failures remain visible without enabling info/debug prompt logging.

Initial Git/image/package/model downloads contact their respective hosts and reveal ordinary network metadata such as IP address. They do not upload your profile, memories, or chat contents. The setup downloader pins model revisions and verifies GGUF SHA256 and Laya snapshot LFS SHA256 / Git blob hashes. Existing verified models can be imported for offline installation.

The SQLite database and downloaded backups contain plaintext personal data. Use disk encryption on the server if needed, and protect backups. The API key is in `.env`, is not included in data backups, and can be rotated by changing it and recreating the backend. Docker administrators and the server owner can access the data. Network isolation does not protect against a compromised host or privileged container configuration changes.

## Portable installation, backup, and restore

Code, model weights, and personal data are separate:

- `models/`: Qwen GGUF, matching vision projector, and `laya/` checkpoint, mounted read-only.
- `data/`: SQLite database and local restore rollback snapshots.
- `.env`: installation-specific access key and runtime settings.
- `backups/`: optional exported personal-data snapshots.

Build once. Restart without rebuilding:

```bash
docker compose up -d --no-build
```

Export your already-built images to avoid building or downloading images on another compatible server:

```bash
docker save -o keno-images.tar keno-backend:local keno-laya:local ghcr.io/ggml-org/llama.cpp:server-b11146 nginx:1.28-alpine
```

Copy the repository files, the entire `models/` directory, and the image archive to the new server. Then:

```bash
docker load -i keno-images.tar
bash scripts/setup.sh
docker compose up -d --no-build
```

This starts **fresh** unless you explicitly restore a backup. The destination CPU architecture must match the exported images. You can also reuse an image you publish to your own registry by setting `KENO_IMAGE`. This repository does not yet publish prebuilt backend images automatically.

Create a backup from the page or:

```bash
bash scripts/backup.sh
```

Restore only your own trusted backup. The script stops the backend, saves a rollback snapshot inside `data/` if there is an existing database, validates the input, then atomically replaces the database. The explicit flag is required:

```bash
bash scripts/restore.sh /absolute/path/to/keno-backup.sqlite3 --replace
```

If validation fails, the backend stays stopped; existing data is preserved. Fix the backup problem or run `docker compose up -d backend` to continue with the old database. The new server keeps its own API key. Backup files contain no model weights; transfer/download models separately. Clones develop independent histories; synchronization is not implemented.

Back up before an upgrade:

```bash
bash scripts/backup.sh
git pull origin main
docker compose up -d --build backend
```

Version 0.3 automatically migrates schema 1/2 to 3 while preserving personal data. Rolling back to older code requires restoring the pre-upgrade backup; older code rejects schema 3. Updating code and running `docker compose up -d --build` preserves your data. Schema version checks reject newer databases rather than silently downgrading. Training is not required or implemented in this release. A future adapter-training workflow will be a separate opt-in operation.

## Change the model

### Try Qwen3 1.7B (text only)

This opt-in profile uses Unsloth's `Qwen3-1.7B-Q4_K_M.gguf`, approximately 1.11 GB, at file revision `bd59ef4`. Download and activation both verify SHA256 `b139949c5bd74937ad8ed8c8cf3d9ffb1e99c866c823204dc42c0d91fa181897`. Existing model files and personal data are preserved. It disables the vision projector, sets context to 4096, and retains your CPU threads, API key, port and Laya's automatic thinking/tool decisions. No manual thinking toggle is added. Its latency and answer/tool quality have not been benchmarked on your server.

```bash
bash scripts/backup.sh
python3 scripts/download-model.py --model 1.7b
python3 scripts/enable-fast.py --model 1.7b
docker compose up -d --no-deps --force-recreate llm backend
```

After an application update, rebuild the backend separately with `docker compose up -d --build --no-deps --force-recreate backend`. The model switch itself does not require a rebuild. Fresh installations also need `bash scripts/setup.sh` and the downloader's `--laya` option.

Check `docker compose ps` and `docker compose logs --tail=60 llm`; wait for the model to be healthy before chatting. Use `bash scripts/timings.sh` to compare complete responses. A smaller model does not guarantee a speed improvement; the first request after recreation has a cold prompt cache. A fair comparison must use matching context, threads, prompts, history and tool routing.

Rollback to the previously installed 2B vision profile:

```bash
python3 scripts/enable-analysis.py
docker compose up -d --no-deps --force-recreate llm backend
```

### Try Qwen3 0.6B

This opt-in text profile downloads Unsloth's Qwen3-0.6B Q4_K_M GGUF (approximately 397 MB), pinned to revision `f2d6f9ca53a254cc379437c49e4b2eb447f779df` and verified by SHA256. It keeps the existing Laya router and automatic thinking decisions, uses a 4096-token context, and disables the vision projector. Speed and answer/tool quality must be measured on your server; the smaller model is not a promised latency fix.

```bash
python3 scripts/download-model.py --model 0.6b
python3 scripts/enable-fast.py
docker compose up -d --no-deps --force-recreate llm backend
```

For a fresh installation, run `bash scripts/setup.sh` and include `--laya` in the download command. Existing chats, memories, profile, credentials, port, CPU threads, and previous model files are preserved. The switch script verifies the downloaded model again before changing `.env` and removes duplicate entries for the settings it changes. Text, DOCX, and PDFs with extracted text remain usable; images, scanned PDF pages, and visual chart interpretation require switching back to vision. Smaller context can mean less attachment/history content fits, while full stored history remains in SQLite.

Return to the installed 2B vision profile with:

```bash
python3 scripts/enable-analysis.py
docker compose up -d --no-deps --force-recreate llm backend
```

Set `LLM_LOG_VERBOSITY=3` in `.env` and recreate `llm` to expose informational processing timings for a controlled benchmark; the default remains `1`. Test a new chat with “hello”, then the same document and memory requests used with 2B. Compare `bash scripts/timings.sh` and the model's `prompt eval time` / `eval time` logs. The first request after restarting has a cold prompt cache.

### Other compatible models

Put a compatible chat GGUF in `models/`, update `MODEL_FILE` in `.env`, and recreate services:

```bash
docker compose up -d --force-recreate
```

Your profile, personality, and history remain intact. This adapter specifically expects llama.cpp’s `/apply-template`, `/tokenize`, and streaming chat endpoints; it is not a generic remote-provider connector. The configured runtime includes Qwen chat templates and delegates thinking to Laya. Other model families must be tested with their own template and sampling settings. A vision model needs its matching `MMPROJ_FILE`; do not reuse the Qwen 2B projector with the previous 4B model.

Start with `CONTEXT_SIZE=8192`, `CPU_THREADS=4`, and `LLM_MEMORY_LIMIT=6g` on an 8 GB machine. Backend memory is capped at 768 MB; the gateway at 64 MB, and Laya at 3 GB (a ceiling, not a reservation). The CPU-only Laya image uses PyTorch 2.8.0, Transformers 4.57.1 and Laya 0.3.26. A model-loading OOM requires a smaller model or more RAM; increasing context also increases resource use. Reduce thread count on small CPUs. Check `docker stats` on your actual server before treating these defaults as a sizing guarantee.

## Development and verification

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
node tests/test_console.js
```

Tests use a deterministic simulated llama.cpp and Laya services to verify auth, fresh installs, cross-chat memory corrections, retries, failure handling, context limits, consistent backups, and restart recovery. They do not measure Qwen’s intelligence, real CPU latency, or Docker egress behavior. A full model startup must be verified on the target server. See `docs/verification.md` for the implementation’s validation record and an actual-model acceptance checklist.

The source project is intentionally backend-first. Android, voice, browser/desktop control, semantic embeddings, OCR across scanned documents, and model training are not implemented yet.

## Response latency

The response prompt asks Qwen to start with the first useful step or fact, without restating the question, announcing a list of steps, or adding stock openings/sign-offs. A bounded output filter also removes an English `To … follow these steps:` first line from how-to answers when its topic repeats words in the current question and substantive answer text follows. It buffers at most 512 characters of a possible opening, then releases the answer; ordinary openings stream immediately. Different conditions, quoted/code requests, file responses, and incomplete intro-only answers are preserved. The same cleaned answer is streamed and saved, with `repeated_opening_removed` in metadata. No additional inference call is used, but generating and hiding a preamble still costs time before the first visible word. This is a narrow style rule, not factual verification or universal language cleanup.

Advice-only turns use one streaming chat request with no tool schema or planner. `context.route.tool_policy=answer_only` and an empty `available_tools` list identify this path; `tool_need` and, on action turns, the tool-family decision are printed by `scripts/timings.sh`. Laya must classify your real requests correctly for this optimization to apply; mock tests verify the gate and streaming behavior, not real-model classification accuracy.

If the native tool planner returns a complete plain-language answer without calling a tool, Keno reuses it instead of discarding it and generating a second answer. The planner itself honors the effective thinking mode and reasoning budget, so complete deep answers can also be reused. Explicit save/weather acknowledgements still pass through server-state guards first. Incomplete/empty planner responses, JSON/fenced planner output, and turns that executed tools retain the final generation pass. Non-streaming planner reasoning duration is unknown and reported as null for deep planner answers; no fabricated token timings are supplied. Planner responses are non-streaming: their answers become visible when the planner call completes, and individual model token timings are unavailable. `answer_source=tool_planner` identifies this reuse. `tool_model_seconds` measures planner inference round trips, `tool_execution_seconds` measures actual tool calls, and `tool_planning_rounds` counts planner calls; `tool_seconds` remains total tool-phase time. These fields do not measure internal model prefill separately. A controlled VPS comparison is still required to establish a speedup.

Ordinary conversation uses a shorter system prompt that explicitly distinguishes the user from the assistant. Tool-specific guidance is included only for the tools Laya makes available on that turn; document evidence rules remain enabled for attached files. This reduces unrelated instructions but does not establish real-model accuracy or a measured latency improvement. Explicit firsthand save requests receive a server-grounded acknowledgement: without a staged successful memory write, Keno reports that nothing was saved instead of generating an unsupported promise of future recall. Laya routing and validated tool calls still control all writes.

The console reports time until the first visible word and total server time. Saved response context includes `context_prepare_seconds` (Laya routing, document selection/rendering, template formatting/tokenization and trimming), `model_first_token_seconds` (generation call until first visible answer text after opening cleanup), `first_token_seconds` (server request start until first visible answer text), and `total_seconds`. Additional timing fields are `model_first_delta_seconds` (generation call until the first nonempty answer or reasoning delta), `model_first_reasoning_seconds` (first reasoning delta, absent when none is observed), and `hidden_reasoning_seconds` (observed interval from first reasoning delta until first raw answer content, zero when no reasoning was observed; excludes opening cleanup buffering). These streaming observations include network/buffering effects; they are not exact internal prefill or reasoning measurements. The browser's first-word measurement also includes tunnel/network latency. First-word timings include waiting for hidden reasoning when Laya enables it; raw reasoning text is neither displayed nor stored. `context.route.seconds` measures the routing call separately; `tool_seconds` measures tool planning/execution. First-word and total times include both. Old/replayed turns retain their original timing metadata. Run `bash scripts/timings.sh` to print timing and effort metadata for the three latest completed responses without exposing messages, files, memories or API keys.

The system prompt has no changing clock timestamp, allowing a stable prefix to be reused by the model runtime when its cache is available. Profile/personality changes and selected memories still legitimately change context. This is a cache opportunity, not a measured speedup guarantee. The assistant is not automatically given the current date/time; supply it in your question when needed. On this CPU-only deployment, compare short prompts in new and existing chats before switching models. Longer output limits address truncation, not initial-token latency.


### Reliability checks and relevant context

Personal `user.*` facts are included only when relevant; pinned preferences and legacy non-personal pinned settings remain available. Profile fields live in retrieved reference data after the stable system/history prefix rather than in the system prompt. Name and background fields are selected for relevant questions; preferences remain applicable across replies. Short bounded follow-ups such as “which is?” and “tell me more” use the preceding user request for retrieval. A name follow-up immediately after “who made you?” can use verified name evidence without another tool-planner call. This does not infer who created the underlying Qwen model.

A streaming filter removes only exact generic closing sentences at a line boundary after substantive text, including “Let me know if you need further assistance.” It preserves specific requests for information, standalone sentences, quotes/code requests, and attached-file answers. `stock_closing_removed` reports removal. Profile relevance and style filters do not certify factual accuracy: device instructions still need evidence, current information needs an enabled successful lookup, and no external lookup is enabled automatically by this update.

Run `bash scripts/evaluate.sh` while the server is otherwise idle. It starts a temporary loopback-only backend in the existing container with a separate temporary database and the real local Laya/LLM services. It exercises greeting, advice routing/style, calculator, memory saving, cross-chat recall, and follow-up context, reports replies and latency, then shuts down the temporary backend and deletes its database. It does not alter production chats or memories. The isolated backend starts with default settings; existing custom identity/profile settings are not copied. Evaluation inference shares the model and changes its cache, so do not treat these mixed prompts as a controlled speed benchmark. Pass/fail checks are bounded smoke checks; review menu paths and general factual quality yourself. Local automated tests use mocked inference, not the VPS models.


Explicit firsthand save commands (`Remember that my …`, `Save that I …`) and bare follow-up saves take precedence over Laya's answer-only classification, without changing its recorded raw decision. They use the memory tool route; firsthand saves require `memory_save` with validated verbatim evidence. Exact name-save commands retain the direct staged save path. Negative save/deletion requests and uploaded-file messages are excluded from this override. Unrecognized facts still require model tool argument generation and can fail honestly. A bounded name question with no evidence now returns an unknown-name acknowledgement rather than asking the model to guess.

Live evaluation now reports effective tool policy, available tools and tool events. Calculator checks require successful tool execution rather than accepting a correct answer alone. Follow-up checks require the marker in the reply and reject explicit denials of conversation access, in addition to checking context selection. These stronger checks can fail even when the earlier smoke checks passed.
