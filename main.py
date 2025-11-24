from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
# from fastapi.staticfiles import StaticFiles

import requests
import time
import statistics
import math
import json
import os

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


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


def run_benchmark(
    url: str,
    method: str,
    headers: dict | None,
    rps: int,
    duration_seconds: int,
):
    """
    Very simple RPS-based benchmark:
    - total_requests = rps * duration
    - send requests one by one
    - sleep to roughly maintain RPS
    """
    total_requests = rps * duration_seconds
    interval = 1.0 / rps

    results = []  # list of dicts: {index, latency_ms, success, status_code}

    for i in range(total_requests):
        payload = {
            "jsonrpc": "2.0",
            "id": i,
            "method": method,
            "params": [],
        }

        # For eth_getBlockByNumber we benchmark "latest"
        if method == "eth_getBlockByNumber":
            payload["params"] = ["latest", False]

        start = time.perf_counter()
        success = False
        status_code = None

        try:
            resp = requests.post(url, json=payload, headers=headers or {}, timeout=10)
            status_code = resp.status_code
            elapsed = time.perf_counter() - start
            latency_ms = elapsed * 1000.0

            if resp.status_code == 200:
                data = resp.json()
                if "error" not in data:
                    success = True
        except Exception:
            elapsed = time.perf_counter() - start
            latency_ms = elapsed * 1000.0
            success = False

        results.append(
            {
                "index": i + 1,
                "latency_ms": latency_ms,
                "success": success,
                "status_code": status_code,
            }
        )

        # Sleep to roughly match RPS
        sleep_for = interval - (time.perf_counter() - start)
        if sleep_for > 0:
            time.sleep(sleep_for)

    latencies = [r["latency_ms"] for r in results]
    successes = [r for r in results if r["success"]]
    errors = [r for r in results if not r["success"]]

    summary = {}
    if latencies:
        summary = {
            "total_requests": len(results),
            "total_success": len(successes),
            "total_errors": len(errors),
            "error_rate": (len(errors) / len(results)) * 100.0,
            "latency_min_ms": min(latencies),
            "latency_max_ms": max(latencies),
            "latency_avg_ms": statistics.mean(latencies),
            "latency_p50_ms": percentile(latencies, 50),
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


@app.post("/run", response_class=HTMLResponse)
async def run(
    request: Request,
    url: str = Form(...),
    method: str = Form(...),
    headers: str = Form(""),
    rps: int = Form(...),
    duration: int = Form(...),
):
    # Parse headers if given as JSON, otherwise ignore
    headers_dict: dict | None = None
    if headers.strip():
        try:
            headers_dict = json.loads(headers)
            if not isinstance(headers_dict, dict):
                headers_dict = None
        except json.JSONDecodeError:
            headers_dict = None

    summary, results = run_benchmark(
        url=url,
        method=method,
        headers=headers_dict,
        rps=rps,
        duration_seconds=duration,
    )

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "summary": summary,
            "results": results,
            "form_values": {
                "url": url,
                "method": method,
                "headers": headers,
                "rps": rps,
                "duration": duration,
            },
        },
    )
