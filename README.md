# Framework 16 Local LLM Stack

Fast, well-tuned local LLM inference on a **Framework 16** laptop with the **AMD Radeon RX 7700S** (8 GB) discrete GPU — on Fedora, with no cloud and no NVIDIA.

If your machine matches the spec below, `./setup.sh` gets you a running, GPU-accelerated, OpenAI-compatible endpoint at `http://127.0.0.1:8080` in one command.

## Why this exists

"Can a laptop with no real GPU run local AI?" turned out to be the wrong question for this hardware — the Framework 16 dGPU module is a **real 8 GB RDNA3 card (gfx1102)**, in the same tier as a desktop RX 7600. The hard part isn't capability, it's getting ROCm to build and pin correctly on Fedora. This repo encodes the solution, measured on the actual hardware.

## Target hardware

| Component | Spec |
|---|---|
| Laptop | Framework 16 |
| CPU | AMD Ryzen 9 7940HS (8C/16T, AVX-512) |
| dGPU | **Radeon RX 7700S** — Navi 33, **gfx1102**, 8 GB VRAM |
| iGPU | Radeon 780M (gfx1103) — present, not used for inference here |
| RAM | 32–64 GB recommended |
| OS | Fedora 43 (ROCm 6.4.x, Mesa RADV) |

> The XDNA **1** NPU in the 7040-series has no Linux LLM runtime — inference is GPU + CPU only.

## Quickstart

```bash
git clone <this-repo> framework16-local-llm && cd framework16-local-llm
./setup.sh            # deps + build (ROCm & Vulkan) + download 7B + install service
# → http://127.0.0.1:8080  (web UI in a browser, OpenAI API at /v1)
```

Or step by step: `./setup.sh deps`, `./setup.sh build`, `./setup.sh model 7b`, `./setup.sh service`. Run `./setup.sh doctor` anytime to verify the stack.

## Two backends — pick by workload

Measured on the RX 7700S, Qwen2.5-7B Q4_K_M, full offload:

| Backend | Prompt processing (pp512) | Token generation (tg128) | Best for |
|---|---:|---:|---|
| **ROCm** | **1140 t/s** | 45 t/s | Long context / RAG / large prompts (prefill-bound) |
| **Vulkan** | 853 t/s | **54 t/s** | Interactive chat (decode-bound), zero-maintenance |

Neither is universally faster — ROCm wins prefill by ~33%, Vulkan wins decode by ~20%. The always-on service runs **ROCm** (long-context strength); `llama-go` with no args gives you **Vulkan** for snappy chat.

## Model capacity (8 GB VRAM)

| Model | Fits VRAM? | pp512 | tg128 | Use |
|---|:--:|---:|---:|---|
| **3B** Q4 | ✅ full | 2352 t/s | 80 t/s | Agentic, autocomplete, tool-calling |
| **7B** Q4 | ✅ full | 1140 t/s | 45 t/s | **Default daily driver** |
| **14B** Q4 | ⚠️ partial (44/48 layers) | 482 t/s | 17 t/s | Max quality, slower |

7B is the sweet spot. 14B (8.37 GiB) overflows 8 GB and runs partially on CPU — usable for quality-first single queries, not rapid chat. See [docs/BENCHMARKS.md](docs/BENCHMARKS.md).

## Usage

```bash
bin/llama-go                      # Vulkan chat server (default)
bin/llama-go -b rocm -c 32768     # ROCm, long context
bin/llama-go --chat               # interactive terminal chat
bin/llama-go -m 3b --prompt "hi"  # one-shot with the 3B model
bin/llama-bench-shootout 3b 7b 14b  # re-run the size sweep

systemctl --user {status,restart,stop} llama   # manage the service
```

## Layout

```
setup.sh                 one-shot installer (deps|build|model|service|doctor)
bin/llama-go             daily-driver launcher (backend + model + pinning)
bin/llama-bench-shootout ROCm-vs-Vulkan benchmark
bin/_common.sh           shared config, paths, GPU pinning, model catalog
config/models.conf       model catalog with measured ngl recommendations
systemd/llama.service.in service template
docs/                    BENCHMARKS.md, HARDWARE.md
```

Paths are overridable via `~/.config/fw16-llm/config` (`FW16_HOME`, `MODELS_DIR`, `GFX`). License: MIT.
