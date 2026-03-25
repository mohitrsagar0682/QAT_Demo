"""
metrics_exporter.py — Prometheus metrics exporter for the QAT demo.

Exposes standard gauges and counters for both software and accelerated benchmark paths.
Starts an HTTP metrics server on port 8001.
"""

import logging
import threading

from prometheus_client import Counter, Gauge, start_http_server

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prometheus metric definitions
# ---------------------------------------------------------------------------

# Throughput gauge — labelled by mode: "software" | "accelerated"
qat_throughput = Gauge(
    "qat_demo_throughput_mbps",
    "Compression throughput in MB/s",
    ["mode"],
)

# CPU utilization gauge — labelled by mode
qat_cpu = Gauge(
    "qat_demo_cpu_utilization_pct",
    "CPU utilization percentage during benchmark",
    ["mode"],
)

# P99 latency gauge — labelled by mode
qat_latency_p99 = Gauge(
    "qat_demo_latency_p99_ms",
    "P99 compression operation latency in milliseconds",
    ["mode"],
)

# Compression ratio — labelled by mode
qat_compression_ratio = Gauge(
    "qat_demo_compression_ratio",
    "Compression ratio achieved (uncompressed / compressed size)",
    ["mode"],
)

# Speedup ratio — no label (ratio between accelerated and software)
qat_speedup_ratio = Gauge(
    "qat_demo_speedup_ratio",
    "Throughput speedup of accelerated path vs software path",
)

# Total benchmark runs counter — labelled by mode
qat_run_count = Counter(
    "qat_demo_run_count_total",
    "Total number of completed benchmark runs",
    ["mode"],
)


class MetricsExporter:
    """
    Manages Prometheus metric updates for the QAT demo backend.

    Usage:
        exporter = MetricsExporter()
        exporter.start_server(port=8001)
        exporter.update_metrics(summary_dict)
        exporter.compute_speedup(sw_summary, accel_summary)
    """

    def __init__(self) -> None:
        self._server_started = False
        self._lock = threading.Lock()
        self._sw_summary: dict | None = None
        self._accel_summary: dict | None = None

    def start_server(self, port: int = 8001) -> None:
        """Start the Prometheus HTTP metrics server (idempotent — safe to call multiple times)."""
        with self._lock:
            if self._server_started:
                logger.debug("Prometheus metrics server already running on port %d.", port)
                return
            try:
                start_http_server(port)
                self._server_started = True
                logger.info("Prometheus metrics server started on port %d.", port)
            except OSError as exc:
                # Port already bound (e.g. hot reload) — log and continue
                logger.warning("Could not bind metrics server on port %d: %s", port, exc)
                self._server_started = True  # Treat as running

    def update_metrics(self, summary: dict) -> None:
        """
        Update Prometheus gauges from a completed benchmark summary dict.

        Expected keys in summary:
            mode, avg_throughput_mbps, avg_cpu_percent, p99_latency_ms,
            compression_ratio
        """
        mode = summary.get("mode", "unknown")
        throughput = summary.get("avg_throughput_mbps", 0.0)
        cpu = summary.get("avg_cpu_percent", 0.0)
        latency_p99 = summary.get("p99_latency_ms", 0.0)
        ratio = summary.get("compression_ratio", 1.0)

        qat_throughput.labels(mode=mode).set(throughput)
        qat_cpu.labels(mode=mode).set(cpu)
        qat_latency_p99.labels(mode=mode).set(latency_p99)
        qat_compression_ratio.labels(mode=mode).set(ratio)
        qat_run_count.labels(mode=mode).inc()

        logger.debug(
            "Updated metrics for mode=%s: throughput=%.2f MB/s, cpu=%.1f%%, p99=%.2f ms",
            mode,
            throughput,
            cpu,
            latency_p99,
        )

        # Cache summary for speedup computation
        if mode == "software":
            self._sw_summary = summary
        elif mode == "accelerated":
            self._accel_summary = summary

        # Auto-compute speedup if both are available
        if self._sw_summary and self._accel_summary:
            self.compute_speedup(self._sw_summary, self._accel_summary)

    def compute_speedup(self, sw_summary: dict, accel_summary: dict) -> float:
        """
        Compute the throughput speedup ratio (accelerated / software) and update gauge.

        Args:
            sw_summary: Summary dict from software benchmark.
            accel_summary: Summary dict from accelerated benchmark.

        Returns:
            Speedup ratio as a float.
        """
        sw_tp = sw_summary.get("avg_throughput_mbps", 1.0) or 1.0
        accel_tp = accel_summary.get("avg_throughput_mbps", 1.0)
        speedup = accel_tp / sw_tp if sw_tp > 0 else 0.0

        qat_speedup_ratio.set(speedup)
        logger.info(
            "Speedup ratio computed: %.2fx (software=%.2f MB/s, accelerated=%.2f MB/s)",
            speedup,
            sw_tp,
            accel_tp,
        )
        return speedup

    def update_live_metric(self, metric: dict) -> None:
        """
        Update gauges from a per-second streaming metric dict (for live dashboard refresh).

        Expected keys: mode, throughput_mbps, cpu_percent, latency_ms, compression_ratio
        """
        mode = metric.get("mode", "unknown")
        qat_throughput.labels(mode=mode).set(metric.get("throughput_mbps", 0.0))
        qat_cpu.labels(mode=mode).set(metric.get("cpu_percent", 0.0))
        qat_latency_p99.labels(mode=mode).set(metric.get("latency_ms", 0.0))
        qat_compression_ratio.labels(mode=mode).set(metric.get("compression_ratio", 1.0))
