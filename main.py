import os
import json
import math
import time
import statistics
import asyncio

import aiohttp
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


def percentile(data, p: float):
    """Return the p-th percentile of a list of numbers (0-100)."""
    if not data:
        return None
    data_sorted = sorted(data)
    k = (len(data_sorted) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return data_sorted[int(k)]
    d0 = data_sorted[f] * (c - k)
    d1 = data_sorted[c] * (k - f)
    return d0 + d1


async def make_single_request(
    session: aiohttp.ClientSession,
    url: str,
    method: str,
    headers: dict | None,
    index: int,
):
    """
    Send a single JSON-RPC request and return a result dict:
    {index, latency_ms, success, status_code}
    """
    # Build payload
    payload: dict = {
        "jsonrpc": "2.0",
        "id": index,
        "method": method,
        "params": [],
    }

    # For eth_getBlockByNumber we benchmark "latest"
    if method == "eth_getBlockByNumber":
        payload["params"] = ["latest", False]

    start = time.perf_counter()
    success = False
    status_code: int | None = None

    try:
        async with session.post(url, json=payload, headers=headers or {}, timeout=15) as resp:
            status_code = resp.status
            elapsed = time.perf_counter() - start
            latency_ms = elapsed * 1000.0

            if resp.status == 200:
                try:
                    data = await resp.json()
                    if "error" not in data:
                        success = True
                except Exception:
                    # JSON parse error, count as failure
                    success = False
    except Exception:
        elapsed = time.perf_counter() - start
        latency_ms = elapsed * 1000.0
        success = False

    return {
        "index": index,
        "latency_ms": latency_ms,
        "success": success,
        "status_code": status_code,
    }


async def run_benchmark_async(
    url: str,
    method: str,
    headers: dict | None,
    rps: int,
    duration_seconds: int,
):
    """
    Asynchronous RPS-based benchmark:
    - total_requests = rps * duration
    - fire up to `rps` requests per second in batches
    """
    total_requests = rps * duration_seconds
    results: list[dict] = []

    start_time = time.perf_counter()
    end_time = start_time + duration_seconds
    sent = 0

    async with aiohttp.ClientSession() as session:
        # Loop in 1-second batches
        while time.perf_counter() < end_time and sent < total_requests:
            batch_start = time.perf_counter()
            tasks = []

            # Prepare up to `rps` requests for this second
            for _ in range(rps):
                if sent >= total_requests:
                    break
                idx = sent + 1
                tasks.append(
                    make_single_request(
                        session=session,
                        url=url,
                        method=method,
                        headers=headers,
                        index=idx,
                    )
                )
                sent += 1

            if tasks:
                batch_results = await asyncio.gather(*tasks)
                results.extend(batch_results)

            # Keep roughly 1-second pacing per batch
            elapsed = time.perf_counter() - batch_start
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)

    latencies = [r["latency_ms"] for r in results]
    successes = [r for r in results if r["success"]]
    errors = [r for r in results if not r["success"]]

    summary: dict = {}
    if latencies:
        summary = {
            "total_requests": len(results),
            "total_success": len(successes),
            "total_errors": len(errors),
            "error_rate": (len(errors) / len(results)) * 100.0,
            "latency_min_ms": min(latencies),
            "latency_max_ms": max(latencies),
            "latency_avg_ms": statistics.mean(latencies),
            "latency_p90_ms": percentile(latencies, 90),
            "latency_p95_ms": percentile(latencies, 95),
            "latency_p99_ms": percentile(latencies, 99),
        }

    return summary, results


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "summary": None,
            "results": [],
            "form_values": {
                "url": "",
                "method": "eth_blockNumber",
                "headers": "",
                "rps": 5,
                "duration": 10,
            },
        },
    )


@app.post("/run")
async def run_json(
    url: str = Form(...),
    method: str = Form(...),
    headers: str = Form(""),
    rps: int = Form(...),
    duration: int = Form(...),
):
    headers_dict: dict | None = None
    if headers.strip():
        try:
            headers_dict = json.loads(headers)
            if not isinstance(headers_dict, dict):
                headers_dict = None
        except json.JSONDecodeError:
            headers_dict = None

    summary, results = await run_benchmark_async(
        url=url,
        method=method,
        headers=headers_dict,
        rps=rps,
        duration_seconds=duration,
    )

    return JSONResponse({"summary": summary, "results": results})
