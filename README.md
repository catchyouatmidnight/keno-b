# Keno backend

A self-hosted personal assistant with a local LLM, persistent personal data, and a browser test console. Android will connect to this API later. Version 0.2.0 is a single-owner assistant backend with local Laya routing, document analysis and vision, not an autonomous PC agent.

## Start on a Linux server

Requires Docker Engine with Compose v2, Python 3 for the optional model download, and Linux x86-64 or ARM64. An 8 GB machine is the initial target, not a measured performance guarantee. Leave approximately 12 GB of disk space for images, model files, and backups. CPU speed matters; one response runs at a time.

```bash
git clone https://github.com/catchyouatmidnight/keno-b.git
cd keno-b
bash scripts/setup.sh --download-model
docker compose up -d --build
```

Check `docker compose port gateway 8080` and `curl http://127.0.0.1:8080/health` to verify the published web port. On upgrades, run `docker compose up -d --force-recreate` so the gateway is created and the obsolete backend port mapping is removed.

Open **http://localhost:8080**. Copy `KENO_API_KEY` from your local `.env` into the page’s access-key field. The page includes chat, memories, your profile, personality settings, backup download, and an API reference. The key stays in tab memory and is cleared on refresh/disconnect.

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

Laya is the actual local multilingual decision checkpoint from [NandhaKishorM/laya](https://github.com/NandhaKishorM/laya). It evaluates three typed choices in one request: quick/deep thinking, text/vision evidence, and focused/overview document selection. The latest user request, a bounded recent-chat excerpt and attachment metadata are the decision input. Document contents are processed locally by Qwen. Laya never generates the user-facing answer. There is no thinking button or API override.

Low chosen-answer confidence (below 0.65) or a truncated long request gets deeper thinking. Images and textless PDFs require vision even when the router selects text. A failed or invalid router response produces HTTP 503 rather than silently substituting another engine. Inspect `context.route` for choices, confidence, routing time and the effective mode. These are zero-shot decisions and need evaluation on your own requests; probabilities are not a guarantee of correctness.

Thinking is capped at 384 generated tokens and consumes extra time. The API reserves this in addition to the requested answer limit. llama.cpp separates reasoning into its reasoning field; Keno reads and saves only answer content. Choosing a smaller model can reduce inference time, but adding Laya does not guarantee lower end-to-end latency.

Use the file picker in Chat and select up to four stored attachments per request. Supported files: PDF, DOCX, UTF-8 TXT/MD/CSV, PNG/JPG/WebP. Each file is limited to 8 MB, PDFs to 100 pages, extracted text to 200,000 characters, each chat to eight files, and total raw/extracted attachment storage to 128 MB. Files are stored inside SQLite and included in backups. Deleting a chat deletes its attachments; explicit memories remain.

The server extracts document text locally and retrieves at most six 1,000-character excerpts using Unicode keyword overlap, or evenly spaced excerpts when Laya chooses an overview. This is lexical retrieval, not semantic embeddings or an exhaustive whole-document review. Up to two images/PDF pages are included for vision, resized to fit a 1,120-pixel side and capped at 1,024 image tokens each in llama.cpp. Ask for a specific page (`page 7` / `halaman 7`) when needed. Scanned PDFs default to their first two pages; extracting every scanned page with OCR is not implemented. Detailed charts, tiny text, long documents and reasoning still need accuracy checks.

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

Set `stream:true` and use `curl -N` for SSE. Events are `context`, `timing`, `delta`, `done`, and `error`. Only `done` confirms a persisted answer. `finish_reason:length` means the response reached its output limit. The console warns when this happens. Select a longer output for website/code generation: 512, 1,024, 2,048, or 3,072 tokens. The API defaults to 512 and permits up to 3,072 through `max_tokens`; larger outputs leave less room for profile and history within the 8,192-token default context. If the remaining mandatory prompt does not fit, the API returns 422 rather than silently discarding your profile. Stream failures use an `error` event after HTTP headers have been sent. Non-streaming failures use HTTP 502/503.

Clients should supply a unique `request_id` per message and reuse it when retrying that message. Completed requests replay the saved answer without running inference again; using the ID with different text or a different conversation returns 409. Failed turns are retryable. One generation runs at a time; concurrent chat requests return 409 with `Retry-After`, rather than growing a RAM-consuming queue. The backend must run with **one Uvicorn worker / one replica**. A restart marks unfinished turns failed. Partial streamed answers are not retained as completed history.

## How personal continuity works

The system combines the assistant identity, your profile, selected memories, and recent completed turns with each new message. Profile and identity are always included. Up to eight active memories are selected using pinned priority and local Unicode keyword overlap; no embedding model or external search service is required. Expired memories are excluded. Recent history is limited to twelve turns and trimmed by the model’s tokenizer to fit the configured context, reserving output tokens. If necessary, memories are also trimmed; `context.memory_keys` reports exactly which ones were included. Older turns remain in the database but are not automatically retrieved across chats in this first version.

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

PUT it to `/api/v1/memories/preferred_language`. Expiry must be an ISO timestamp with timezone. A source conversation can be attached when saving a fact. Deleting a chat preserves explicit memories but clears their source reference. Deleting a memory does not erase historical chat messages that mention it; remove those conversations separately if needed.

Memory saving remains explicit in v0.2.0. Saying “remember this” in chat does not silently write a fact; the assistant is instructed to direct you to the memory editor. Automatic suggestions, summarization of older conversations, semantic retrieval, and fine-tuning are later features. No model can guarantee identical wording or reliable reasoning merely because memories are supplied.

## Privacy

The backend, Qwen model and Laya router share a Docker network marked `internal:true`; none is attached to an external-egress network. A small Nginx gateway joins that private network and a separate bridge network so Docker can publish the web port reliably. Only the gateway port is published; the backend and raw model API are not exposed directly. The gateway forwards requests only to the backend, has no analytics or provider integrations, and has no mounted database/model files. It does have a bridge network with external connectivity; runtime egress isolation applies to the backend, Qwen and Laya, not to the gateway. The backend accepts only the local `llm` / `laya` services or loopback as its model/router URLs, ignores HTTP proxy environment variables, and never calls an external LLM provider. There are no analytics, remote fonts, external UI scripts, or automatic cloud backups. Personal prompts are not written to access logs; llama logs only generic output and errors by default, so startup failures remain visible without enabling info/debug prompt logging.

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

Updating code and running `docker compose up -d --build` preserves your data. Schema version checks reject newer databases rather than silently downgrading. Training is not required or implemented in this release. A future adapter-training workflow will be a separate opt-in operation.

## Change the model

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
```

Tests use a deterministic simulated llama.cpp and Laya services to verify auth, fresh installs, cross-chat memory corrections, retries, failure handling, context limits, consistent backups, and restart recovery. They do not measure Qwen’s intelligence, real CPU latency, or Docker egress behavior. A full model startup must be verified on the target server. See `docs/verification.md` for the implementation’s validation record and an actual-model acceptance checklist.

The source project is intentionally backend-first. Android, voice, browser/desktop tools, automatic memory extraction, and model training are not implemented yet.

## Response latency

The console reports time until the first visible word and total server time. Saved response context includes `context_prepare_seconds` (Laya routing, document selection/rendering, template formatting/tokenization and trimming), `model_first_token_seconds` (generation call until first content token), `first_token_seconds` (server request start until first content token), and `total_seconds`. The browser's first-word measurement also includes tunnel/network latency. First-word timings include waiting for hidden reasoning when Laya enables it; raw reasoning text is neither displayed nor stored. `context.route.seconds` measures the routing call separately. Old/replayed turns retain their original timing metadata.

The system prompt has no changing clock timestamp, allowing a stable prefix to be reused by the model runtime when its cache is available. Profile/personality changes and selected memories still legitimately change context. This is a cache opportunity, not a measured speedup guarantee. The assistant is not automatically given the current date/time; supply it in your question when needed. On this CPU-only deployment, compare short prompts in new and existing chats before switching models. Longer output limits address truncation, not initial-token latency.
