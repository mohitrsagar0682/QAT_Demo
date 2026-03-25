"""
main.py — FastAPI backend for the Intel Xeon 6 QAT Compression Demo.

Endpoints:
  GET  /                → serve frontend index.html
  GET  /api/status      → QAT/ISA-L status
  POST /api/benchmark   → synchronous benchmark run
  WS   /ws/benchmark    → streaming per-second metrics
  GET  /static/*        → static frontend assets
"""

import asyncio
import json
import logging
import os
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from metrics_exporter import MetricsExporter
from workload_accelerated import QAT_AVAILABLE, QAT_SIMULATE, ISAL_AVAILABLE
from workload_software import run_software_benchmark
from workload_accelerated import run_accelerated_benchmark

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("qat-demo")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = pathlib.Path(__file__).parent
FRONTEND_DIR = BASE_DIR / ".." / "frontend"
FRONTEND_DIR = FRONTEND_DIR.resolve()

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------
exporter: MetricsExporter | None = None


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global exporter
    exporter = MetricsExporter()
    exporter.start_server(port=8001)
    logger.info("QAT Demo backend started. Frontend: %s", FRONTEND_DIR)
    logger.info("QAT_AVAILABLE=%s, QAT_SIMULATE=%s, ISAL_AVAILABLE=%s",
                QAT_AVAILABLE, QAT_SIMULATE, ISAL_AVAILABLE)
    yield
    logger.info("QAT Demo backend shutting down.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Intel Xeon 6 QAT Demo",
    description="Real-time compression benchmark: software vs. QAT-accelerated path.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount frontend static files
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
    logger.info("Mounted frontend static files from %s", FRONTEND_DIR)
else:
    logger.warning("Frontend directory not found at %s — /static not mounted.", FRONTEND_DIR)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class BenchmarkRequest(BaseModel):
    mode: str = Field(default="both", pattern="^(software|accelerated|both)$")
    duration: int = Field(default=30, ge=5, le=300)
    chunk_size_mb: int = Field(default=10, ge=1, le=100)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/")
async def serve_index():
    """Serve the frontend single-page application."""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path), media_type="text/html")
    return JSONResponse(
        {"error": "Frontend not found. Mount the frontend volume correctly."},
        status_code=404,
    )


@app.get("/api/status")
async def get_status():
    """Return current QAT and ISA-L availability status."""
    isal_version = "unavailable"
    if ISAL_AVAILABLE:
        try:
            import isal
            isal_version = getattr(isal, "__version__", "unknown")
        except Exception:
            isal_version = "loaded"

    return {
        "status": "ready",
        "qat_available": QAT_AVAILABLE,
        "qat_hardware": bool(os.environ.get("QAT_SIMULATE", "0") == "0" and QAT_AVAILABLE),
        "qat_simulated": QAT_SIMULATE,
        "isal_available": ISAL_AVAILABLE,
        "isal_version": isal_version,
    }


@app.post("/api/benchmark")
async def run_benchmark_api(req: BenchmarkRequest):
    """
    Run benchmark synchronously and return full summary.
    For streaming results, use the WebSocket endpoint instead.
    """
    global exporter
    results = {}

    try:
        if req.mode in ("software", "both"):
            sw_gen = run_software_benchmark(req.duration, req.chunk_size_mb)
            sw_metrics = []
            try:
                while True:
                    m = next(sw_gen)
                    sw_metrics.append(m)
            except StopIteration as e:
                sw_summary = e.value
            if exporter:
                exporter.update_metrics(sw_summary)
            results["software"] = sw_summary

        if req.mode in ("accelerated", "both"):
            accel_gen = run_accelerated_benchmark(req.duration, req.chunk_size_mb)
            accel_metrics = []
            try:
                while True:
                    m = next(accel_gen)
                    accel_metrics.append(m)
            except StopIteration as e:
                accel_summary = e.value
            if exporter:
                exporter.update_metrics(accel_summary)
            results["accelerated"] = accel_summary

        if req.mode == "both" and exporter:
            speedup = exporter.compute_speedup(results["software"], results["accelerated"])
            results["speedup"] = round(speedup, 2)

        return results

    except Exception as exc:
        logger.error("Benchmark error: %s", exc, exc_info=True)
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.websocket("/ws/benchmark")
async def websocket_benchmark(websocket: WebSocket):
    """
    WebSocket endpoint for live benchmark streaming.

    Client sends:
        {"mode": "both", "duration": 30, "chunk_size_mb": 10}

    Server sends per-second metric dicts, then:
        {"type": "complete", "summary": {...}}

    For "both" mode, between phases:
        {"type": "mode_switch", "next_mode": "accelerated"}
    """
    await websocket.accept()
    logger.info("WebSocket client connected from %s", websocket.client)
    global exporter

    try:
        # Receive config from client
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
        config = json.loads(raw)
        mode = config.get("mode", "both")
        duration = max(5, min(300, int(config.get("duration", 30))))
        chunk_size_mb = max(1, min(100, int(config.get("chunk_size_mb", 10))))

        logger.info("WS benchmark: mode=%s, duration=%ds, chunk=%dMB", mode, duration, chunk_size_mb)

        sw_summary = None
        accel_summary = None

        # --- Software phase ---
        if mode in ("software", "both"):
            await websocket.send_text(json.dumps({
                "type": "phase_start",
                "phase": "software",
                "message": "Running software compression benchmark...",
            }))

            sw_gen = run_software_benchmark(duration, chunk_size_mb)
            try:
                while True:
                    # Run one generator step in thread pool to avoid blocking event loop
                    metric = await asyncio.get_event_loop().run_in_executor(
                        None, _next_or_done, sw_gen
                    )
                    if metric is None:
                        break
                    if isinstance(metric, dict) and metric.get("_summary"):
                        sw_summary = metric["_summary"]
                        break
                    # Live metrics update
                    if exporter:
                        exporter.update_live_metric(metric)
                    await websocket.send_text(json.dumps(metric))
                    await asyncio.sleep(0)  # yield to event loop
            except WebSocketDisconnect:
                logger.info("WS client disconnected during software phase.")
                return

        # --- Mode switch ---
        if mode == "both":
            if sw_summary and exporter:
                exporter.update_metrics(sw_summary)
            await websocket.send_text(json.dumps({
                "type": "mode_switch",
                "next_mode": "accelerated",
                "message": "Now running QAT accelerated path...",
                "sw_summary": sw_summary,
            }))

        # --- Accelerated phase ---
        if mode in ("accelerated", "both"):
            if mode == "accelerated":
                await websocket.send_text(json.dumps({
                    "type": "phase_start",
                    "phase": "accelerated",
                    "message": "Running QAT accelerated benchmark...",
                }))

            accel_gen = run_accelerated_benchmark(duration, chunk_size_mb)
            try:
                while True:
                    metric = await asyncio.get_event_loop().run_in_executor(
                        None, _next_or_done, accel_gen
                    )
                    if metric is None:
                        break
                    if isinstance(metric, dict) and metric.get("_summary"):
                        accel_summary = metric["_summary"]
                        break
                    if exporter:
                        exporter.update_live_metric(metric)
                    await websocket.send_text(json.dumps(metric))
                    await asyncio.sleep(0)
            except WebSocketDisconnect:
                logger.info("WS client disconnected during accelerated phase.")
                return

        # --- Final summary ---
        final_result: dict = {}
        if sw_summary:
            if exporter:
                exporter.update_metrics(sw_summary)
            final_result["software"] = sw_summary
        if accel_summary:
            if exporter:
                exporter.update_metrics(accel_summary)
            final_result["accelerated"] = accel_summary

        speedup = None
        if sw_summary and accel_summary and exporter:
            speedup = exporter.compute_speedup(sw_summary, accel_summary)
            final_result["speedup"] = round(speedup, 2)
        elif sw_summary and accel_summary:
            sw_tp = sw_summary.get("avg_throughput_mbps", 1.0) or 1.0
            accel_tp = accel_summary.get("avg_throughput_mbps", 1.0)
            speedup = accel_tp / sw_tp
            final_result["speedup"] = round(speedup, 2)

        await websocket.send_text(json.dumps({
            "type": "complete",
            "summary": final_result,
        }))
        logger.info("WS benchmark complete. speedup=%.2fx", speedup or 0)

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected.")
    except asyncio.TimeoutError:
        logger.warning("WebSocket config receive timed out.")
        await websocket.close(code=1008)
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON from WS client: %s", exc)
        await websocket.send_text(json.dumps({"type": "error", "message": "Invalid JSON config."}))
        await websocket.close(code=1003)
    except Exception as exc:
        logger.error("WebSocket error: %s", exc, exc_info=True)
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
        except Exception:
            pass


def _next_or_done(gen):
    """
    Advance a generator by one step.
    Returns the yielded value, or {"_summary": value} when StopIteration is raised.
    Returns None on any other exception.
    """
    try:
        return next(gen)
    except StopIteration as e:
        return {"_summary": e.value}
    except Exception as exc:
        logger.error("Generator error: %s", exc)
        return None
