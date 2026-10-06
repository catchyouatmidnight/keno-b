# Keno-B Lab

The Docker backend builds and serves the React application at `/`. The original console remains at `/legacy`. No separate frontend service is needed. React Router uses hash routes so the private gateway needs no routing changes.

## Upgrade

```sh
git pull origin main
docker compose up -d --build --no-deps --force-recreate backend
```

Reload the browser and connect under Settings. Access keys remain in the active tab only. Reloading requires reconnecting. Browser persistence contains theme and benchmark preferences; documents, prompts, credentials and results are not persisted there.

## Pages

Overview displays recorded metrics; Playground supports existing sessions, uploads, encrypted library fixtures, SSE, retries with the original failed request ID, and source previews. Documents shows imported file metadata and real retrieval scores. Benchmarks records cases, immutable configuration/case snapshots, results and separate human quality ratings on the backend. Runs provides filters, comparisons and exports. Runtime displays reported service state. Settings manages supported profile, identity, memories and UI preferences.

Backend durations may overlap. Missing data, null, zero and false remain distinct. No fabricated CPU, cache, queue or embedding health measurements are shown. Library contents are decrypted in server memory for model context and authenticated previews; environment-key encryption protects data at rest and does not prevent the server operator from decrypting it.

Benchmarks run sequentially from the active browser page. Leaving it aborts active requests and stops scheduling; recorded results remain. Existing chat attachment fixtures require their original session; encrypted library fixtures support fresh sessions. Citation checks validate labels only, not claim accuracy. Exports may contain private prompts and answers: review before sharing.

## Development and verification

```sh
cd web
npm install
npm test
npm run build
npx playwright install chromium
node tests/browser-smoke.mjs
```

The browser smoke test uses explicit API fixtures to verify UI contracts, not live model quality or speed. Python component checks cover backend lab persistence, context policies and document streaming. A real deployment should additionally verify authentication, encrypted imports, retrieval and live inference.

## Calendar and short follow-ups

Calendar countdowns use the server clock and Python date arithmetic without model planning or generation. A bare year means January 1 of that year; the response states the exact target and current date. Set `KENO_TIMEZONE=Asia/Jakarta` (or another IANA timezone) in `.env` and recreate the backend to use local calendar dates. The default is UTC. These read-only calculations need no internet. “Do that” and “do it” retain recent user context; calendar follow-ups resolve only the adjacent user request, never invented assistant facts.
