# EVM Node RPC Benchmark

FastAPI app that fires controlled bursts of JSON-RPC calls (currently
`eth_blockNumber` or `eth_getBlockByNumber`) so you can benchmark public or
private Ethereum-compatible nodes from a browser.

## Features
- Adjustable requests-per-second (RPS) and duration controls from the UI
- Optional custom headers for authenticated endpoints
- Latency summary with min/max/avg plus p90/p95/p99 percentiles
- Simple timer feedback while tests are running

## Quick start

```bash
cd /Users/krissemmy/personal/evm-node-rpc-benchmark
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Then open `http://127.0.0.1:8000` and plug in the RPC URL you want to test.

## Usage tips
- Use `eth_blockNumber` for a cheap availability probe; switch to
  `eth_getBlockByNumber` to add response payload load.
- Keep `duration` ≤ 60s; the UI drops requests in 1-second batches at the RPS
  you chose (5/10/15 by default).
- Provide headers as a JSON object, e.g.
  `{"Authorization": "Bearer ...", "x-api-key": "..."}`.
- Results are not persisted—copy them out after each run if you need history.

## Troubleshooting
- `Errors > 0` with HTTP 401/403 → your RPC endpoint likely needs headers.
- Many timeouts → lower the RPS or check network routing/firewalls.
- Nothing loads → ensure the server is running (check `uvicorn` logs).