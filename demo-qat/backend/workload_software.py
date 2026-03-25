"""
workload_software.py — Software-path compression benchmark using Python's built-in gzip.

This module generates realistic compressible data and measures throughput, compression ratio,
CPU utilization, and latency using pure CPU-based gzip compression.
"""

import gzip
import io
import json
import logging
import statistics
import time
import uuid
from datetime import datetime, timezone
from typing import Generator

import psutil

logger = logging.getLogger(__name__)

LOG_LEVELS = ["DEBUG", "INFO", "INFO", "INFO", "WARNING", "ERROR"]
LOG_MESSAGES = [
    "Request processed successfully",
    "Cache miss, fetching from database",
    "User authentication completed",
    "Connection pool size: 42/128",
    "Disk usage at 67%% on volume /data",
    "Slow query detected: 340ms for SELECT",
    "Batch job completed: 10000 records processed",
    "Health check passed for service mesh node",
    "Rate limit triggered for client 10.0.1.55",
    "Checkpoint written to WAL position 0x3FA2",
]


def _generate_compressible_data(chunk_size_mb: int) -> bytes:
    """
    Generate realistic compressible data: JSON log lines repeated to fill chunk_size_mb MB.
    JSON logs are highly compressible (typically 3-6x ratio with gzip level 6).
    """
    target_bytes = chunk_size_mb * 1024 * 1024

    # Build a single log line template
    lines = []
    for i in range(500):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": LOG_LEVELS[i % len(LOG_LEVELS)],
            "service": f"svc-{i % 12:02d}",
            "host": f"node-{i % 8:03d}.datacenter.example.com",
            "trace_id": str(uuid.uuid4()),
            "span_id": str(uuid.uuid4())[:8],
            "message": LOG_MESSAGES[i % len(LOG_MESSAGES)],
            "latency_us": 120 + (i * 7) % 9800,
            "status_code": [200, 200, 200, 200, 201, 204, 400, 404, 500][i % 9],
            "bytes_sent": 1024 + (i * 137) % 65536,
            "user_id": f"usr_{i % 1000:04d}",
            "region": ["us-east-1", "eu-west-1", "ap-south-1"][i % 3],
        }
        lines.append(json.dumps(log_entry))

    # Build repeating block
    block = "\n".join(lines) + "\n"
    block_bytes = block.encode("utf-8")

    # Repeat to fill target size
    repeats = (target_bytes // len(block_bytes)) + 1
    data = (block_bytes * repeats)[:target_bytes]
    return data


def run_software_benchmark(
    duration_seconds: int = 30,
    chunk_size_mb: int = 10,
) -> Generator[dict, None, dict]:
    """
    Run a software-path gzip compression benchmark.

    Yields per-second metric dicts, then returns a final summary dict.

    Args:
        duration_seconds: How long to run the benchmark.
        chunk_size_mb: Size of each compression chunk in MB.

    Yields:
        dict with keys: elapsed, throughput_mbps, compression_ratio, cpu_percent,
                        latency_ms, mode
    """
    logger.info(
        "Starting software benchmark: duration=%ds, chunk=%dMB",
        duration_seconds,
        chunk_size_mb,
    )

    # Pre-generate data once; re-use across iterations for consistent measurement
    data = _generate_compressible_data(chunk_size_mb)
    data_size_mb = len(data) / (1024 * 1024)

    # Warm up CPU percent tracking (first call always returns 0.0)
    psutil.cpu_percent(interval=None)

    start_time = time.monotonic()
    deadline = start_time + duration_seconds

    # Per-second accumulation
    window_start = start_time
    window_bytes = 0
    window_latencies: list[float] = []

    # Overall accumulators
    all_latencies: list[float] = []
    all_throughputs: list[float] = []
    all_cpus: list[float] = []
    total_bytes = 0

    # Track last compression ratio seen
    last_ratio = 1.0

    next_report = start_time + 1.0

    while True:
        now = time.monotonic()
        if now >= deadline:
            break

        # --- Compress ---
        t0 = time.monotonic()
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=6) as gz:
            gz.write(data)
        compressed = buf.getvalue()
        t1 = time.monotonic()

        # --- Decompress to verify ---
        buf2 = io.BytesIO(compressed)
        with gzip.GzipFile(fileobj=buf2, mode="rb") as gz:
            _ = gz.read()

        op_ms = (t1 - t0) * 1000.0
        window_latencies.append(op_ms)
        all_latencies.append(op_ms)
        window_bytes += len(data)
        total_bytes += len(data)
        last_ratio = len(data) / len(compressed) if compressed else 1.0

        # --- Report every second ---
        now = time.monotonic()
        if now >= next_report:
            elapsed = now - start_time
            window_secs = now - window_start
            throughput = (window_bytes / (1024 * 1024)) / window_secs if window_secs > 0 else 0.0
            cpu = psutil.cpu_percent(interval=None)

            all_throughputs.append(throughput)
            all_cpus.append(cpu)

            metric = {
                "elapsed": round(elapsed, 2),
                "throughput_mbps": round(throughput, 2),
                "compression_ratio": round(last_ratio, 3),
                "cpu_percent": round(cpu, 1),
                "latency_ms": round(statistics.median(window_latencies), 2),
                "mode": "software",
            }
            yield metric

            # Reset window
            window_start = now
            window_bytes = 0
            window_latencies = []
            next_report = now + 1.0

    # Build final summary
    summary = {
        "total_data_mb": round(total_bytes / (1024 * 1024), 2),
        "avg_throughput_mbps": round(statistics.mean(all_throughputs) if all_throughputs else 0.0, 2),
        "avg_cpu_percent": round(statistics.mean(all_cpus) if all_cpus else 0.0, 1),
        "compression_ratio": round(last_ratio, 3),
        "p50_latency_ms": round(statistics.median(all_latencies) if all_latencies else 0.0, 2),
        "p99_latency_ms": round(
            sorted(all_latencies)[int(len(all_latencies) * 0.99)] if all_latencies else 0.0, 2
        ),
        "mode": "software",
    }
    logger.info("Software benchmark complete: %s", summary)
    return summary
