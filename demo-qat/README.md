# Intel Xeon 6 QAT Demo
### QuickAssist Technology — Real-Time Compression Benchmark

![Docker](https://img.shields.io/badge/Docker-required-blue?logo=docker)
![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green?logo=fastapi)
![Grafana](https://img.shields.io/badge/Grafana-10.4-orange?logo=grafana)
![Prometheus](https://img.shields.io/badge/Prometheus-2.51-red?logo=prometheus)

A full-stack interactive benchmark demonstrating the performance impact of **Intel QuickAssist Technology (QAT)** — the hardware compression and crypto offload engine built into Intel Xeon 6 processors. This demo shows side-by-side: software-based compression vs. QAT-accelerated compression, with live metrics streaming to both the browser UI and Grafana dashboards.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Customer Browser                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │            Intel QAT Demo UI (port 8000)                 │   │
│  │  Live Chart  |  Throughput Gauges  |  Speedup Results   │   │
│  └────────────────────────┬────────────────────────────────┘   │
│                            │ WebSocket                           │
└────────────────────────────┼────────────────────────────────────┘
                             │
              ┌──────────────▼──────────────┐
              │    FastAPI Backend           │
              │    (Python 3.11, port 8000) │
              └──────┬───────────┬──────────┘
                     │           │
         ┌───────────▼───┐   ┌───▼──────────────────┐
         │ Software Path │   │  Accelerated Path     │
         │ Python gzip   │   │  Intel ISA-L (isal)   │
         │ (CPU-bound)   │   │  + QAT HW offload     │
         └───────────────┘   └──────────────────────┘
                     │
              ┌──────▼──────────────┐
              │  Prometheus Client  │
              │  (port 8001)        │
              └──────┬──────────────┘
                     │
          ┌──────────▼────────────────┐
          │    Prometheus             │
          │    (port 9090, 2s scrape) │
          └──────────┬────────────────┘
                     │
          ┌──────────▼────────────────┐
          │    Grafana                │
          │    (port 3000)            │
          │    Pre-built dashboard    │
          └───────────────────────────┘
```

---

## Quick Start

```bash
# 1. Clone and enter the demo directory
git clone <repo>
cd demo-qat

# 2. Build and launch the full stack
make run

# 3. Open the demo in your browser
open http://localhost:8000

# 4. Open the Grafana dashboard
make dashboard
# Login: admin / intel2024
```

That's it. Hit **▶ RUN BENCHMARK** in the UI and watch the comparison unfold in real time.

---

## What You'll See

### Demo UI (http://localhost:8000)

1. **Status bar** — Shows whether real QAT hardware is detected or simulation mode is active
2. **Control panel** — Adjust benchmark duration (10–60s) and chunk size (1–25 MB)
3. **Side-by-side panels** — Software Path vs. QAT Accelerated, each showing:
   - Throughput (MB/s) — live updating
   - CPU Utilization (%) — live updating
   - Compression Ratio
   - P99 Latency (ms)
4. **Live chart** — Real-time line chart showing both modes on the same axis
5. **Animated diagram** — Data particles flowing through CPU vs. QAT chip
6. **Results section** (after benchmark) — Big speedup number, comparison table, cores freed, Grafana link
7. **Confetti** — Fires automatically when speedup exceeds 10x 🎉

### Grafana Dashboard (http://localhost:3000)

The pre-provisioned **"Intel Xeon 6 QAT — Compression Benchmark"** dashboard includes:

| Row | Content |
|-----|---------|
| **Row 1** | Software Throughput stat, QAT Throughput stat (blue), Speedup Ratio gauge, CPU Saved stat |
| **Row 2** | Throughput time series (both modes), CPU Utilization time series (both modes) |
| **Row 3** | P99 Latency bar gauge, Compression Ratio stat, Cores Freed stat |
| **Row 4** | Speedup ratio time series (full run history) |

---

## Expected Results

These numbers represent a **typical Intel Xeon 6** server with QAT hardware enabled, compressing 10 MB chunks of realistic log data (JSON-format, ~3:1 compressible):

| Metric | Software (Python gzip) | QAT Accelerated | Improvement |
|--------|----------------------|-----------------|-------------|
| **Throughput** | ~150 MB/s | ~4,800 MB/s | **~32x** |
| **CPU Utilization** | ~92% | ~5–8% | **~15x less** |
| **P99 Latency** | ~80 ms | ~2.5 ms | **~32x** |
| **Compression Ratio** | 3.2:1 | 3.2:1 | Same (lossless) |
| **Cores Freed (64-core)** | — | ~56 cores | — |

> **Note:** In simulation mode (`QAT_SIMULATE=1`), the demo uses Intel ISA-L (genuinely ~5–10x faster than Python gzip on CPU) and applies an additional multiplier to simulate full hardware QAT throughput. Real results on Xeon 6 with QAT hardware may vary based on data type, core count, and workload parallelism.

---

## Running Without QAT Hardware

By default, the demo runs with `QAT_SIMULATE=1` (set in `docker-compose.yml`). This means:

- **Intel ISA-L** (`isal` library) is used for the accelerated path — this is genuinely faster than Python's gzip
- A **hardware simulation multiplier** is applied to model real QAT throughput (~30–40x software baseline)
- The CPU utilization drop is also simulated to reflect hardware offload behavior

This mode is ideal for **pre-sales demos** on any hardware — no Xeon 6 required to show the story.

---

## Running With Real QAT Hardware

If you're running on an actual Intel Xeon 6 platform with QAT enabled:

```bash
# 1. Load the QAT kernel modules
sudo modprobe qat_4xxx
sudo modprobe usdm_drv

# 2. Verify QAT is detected
lsmod | grep qat

# 3. Disable simulation mode in docker-compose.yml
# Remove or set: QAT_SIMULATE=0

# 4. Rebuild and launch
make clean && make run
```

The backend will auto-detect the QAT module and use the hardware path. The `QAT_AVAILABLE` flag in `/api/status` will show `true` and the UI badge will turn green.

For full QAT setup on Xeon 6, refer to the [Intel QAT Software for Linux](https://www.intel.com/content/www/us/en/developer/articles/guide/intel-quickassist-technology-software-for-linux-getting-started-guide.html) guide.

---

## Business Impact / TCO Narrative

### The Problem
Storage-heavy workloads — log pipelines, database backups, object storage, Kafka — spend 20–40% of CPU cycles doing gzip compression. That's capacity being consumed by a function that isn't your application.

### The QAT Answer
Intel Xeon 6 has a hardware QAT engine built directly into the die. It handles compression and cryptographic operations at wire speed — without consuming CPU cores.

### The Math (64-core Xeon 6 server, $8,000/server)

| | Software-only | With QAT |
|---|---|---|
| Target: 10 GB/s compression | 4 servers needed | 1 server needed |
| 3-year CapEx | $32,000 | $8,000 |
| 3-year Power (250W × $0.10/kWh) | ~$2,600 | ~$650 |
| **Total 3-year TCO** | **~$34,600** | **~$8,650** |
| **Savings** | | **~$25,950 (75%)** |

And those 3 freed servers can run more application workload — increasing revenue capacity, not just cutting cost.

---

## Grafana Dashboard Guide

1. Open `http://localhost:3000`
2. Login: `admin` / `intel2024` (or browse anonymously as Viewer)
3. The QAT dashboard loads automatically as the home dashboard
4. Run a benchmark from the UI — metrics appear in Grafana within 2 seconds
5. Use the time picker to zoom in on your benchmark window
6. The **Speedup Ratio gauge** in Row 1 is your headline number — this is what to show customers

---

## Troubleshooting

**Backend won't start**
```bash
make logs  # Check for Python import errors
make status  # Check if API is responding
```

**Port conflicts**
Edit `docker-compose.yml` and change the host-side ports (left side of `:`).

**Grafana shows "No data"**
- Wait 10–15 seconds after running a benchmark (Prometheus scrape interval is 2s, but metrics need a run)
- Check `http://localhost:9090/targets` — the `qat-demo-backend` target should be UP

**ISA-L not available**
The Dockerfile compiles ISA-L during build. If `isal` import fails, the accelerated path falls back to `zlib`. Check build logs with `docker compose build --no-cache`.

**QAT not detected on real hardware**
Check `lsmod | grep qat` and ensure the `qat_4xxx` (or appropriate variant) driver is loaded before starting the container.

---

## Links

- [Intel QAT Documentation](https://www.intel.com/content/www/us/en/developer/articles/guide/intel-quickassist-technology-software-for-linux-getting-started-guide.html)
- [Intel ISA-L (isa-l) GitHub](https://github.com/intel/isa-l)
- [Intel ISA-L Python bindings (isal)](https://github.com/pycompression/python-isal)
- [Intel Extension for PyTorch (IPEX)](https://github.com/intel/intel-extension-for-pytorch)
- [Intel OpenVINO](https://github.com/openvinotoolkit/openvino)
- [Intel Xeon 6 Platform Overview](https://www.intel.com/content/www/us/en/products/details/processors/xeon/xeon6.html)

---

*Built with [OpenClaw](https://openclaw.ai) | Powered by Intel Xeon 6*
