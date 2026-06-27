# CLAUDE.md — Framework 16 Local LLM Stack

Guidance for Claude Code (or any agent) working in this repo.

## What this is

A thin, measured packaging of llama.cpp for the Framework 16 + Radeon RX 7700S (gfx1102, 8 GB). It is **shell + config only** — no application code. The value is in the *correct ROCm-on-Fedora build recipe* and the *hardware-measured defaults*, not in abstraction.

## Architecture (one source of truth each)

- `bin/_common.sh` — sourced by everything. Owns: path resolution (`FW16_HOME`, `MODELS_DIR`, `LLAMA_SRC`, build dirs), GPU pinning (`hip_idx`, `vk_dev`), model-catalog lookup, and `ensure_binary` (the canonical build recipe). **Change build flags or pinning here, nowhere else.**
- `bin/llama-go` — launcher. Maps workload → backend/model, then pins and runs `llama-server`/`llama-cli`.
- `bin/llama-vulkan-mode` — convenience wrapper: stop ROCm service → run Vulkan on `:8081` → restore the service on exit (trap, NOT exec'd so the trap survives). For opencode's on-demand `llama-vulkan` provider.
- `bin/llama-bench-shootout` — benchmark harness.
- `config/models.conf` — the model catalog: `key|filename|url|ngl|note`. `ngl` values are **measured**, not guessed.
- `systemd/llama.service.in` — `@PLACEHOLDER@` template; `setup.sh service` substitutes absolute paths.
- `setup.sh` — orchestrator (`deps|build|model|service|all|doctor`).

## Hard-won facts — do not regress these

- **Discrete GPU is `gfx1102`** (RX 7700S, renderD128). The iGPU is `gfx1103` (780M) and is the rocBLAS problem-child — always target/pin the dGPU.
- **Fedora ROCm build needs `rocm-hip-devel`** for the `libamdhip64.so` linker symlink + HIP cmake config. Without it: `ld.lld: error: unable to find library -lamdhip64`.
- **Do NOT force `hipcc` as the C/C++ compiler.** Use `HIP_PATH=$(hipconfig -R)` (=/usr) and `HIPCXX=$(hipconfig -l)/clang`. Forcing hipcc makes cmake's trivial compiler test fail.
- **`rocblas-devel`/`hipblas-devel` collide with the AMD el9 repo** (installs to `/opt/rocm`, breaks `dnf`). Always glob-pin to `.fc43` — see `cmd_deps` in setup.sh.
- **Vulkan build needs** `spirv-headers-devel spirv-tools-devel glslang glslc` (build-time shader compile), beyond just `glslc`.
- **`pkill -f llama-server` self-matches** an agent shell whose command line contains the string. Use `pkill -x llama-server`.
- **14B Q4 (8.37 GiB) does not fit 8 GB.** `-ngl 99` → "failed to load model". Catalog pins it to `ngl 44` (partial offload).

## Backend choice (measured, not preference)

ROCm wins prompt-processing ~33%; Vulkan wins token-generation ~20%. Service = ROCm (long-context). `llama-go` default = Vulkan (chat). Don't flatten this into "X is faster" — it is workload-dependent.

## Conventions

- Bash with `set -euo pipefail`; helpers/config live in `_common.sh`, sourced via `BASH_SOURCE` dir.
- Keep models and builds **out of git** (see `.gitignore`); they live under `FW16_HOME`.
- New models: add a measured row to `config/models.conf` (run `llama-bench-shootout <key>` first to set `ngl`).
- Re-verify any hardware claim (`rocminfo`, `vulkaninfo`, `--list-devices`) before changing defaults.

## Verify a change

```bash
./setup.sh doctor                 # hardware + toolchain + build + service state
bin/llama-go --prompt "ping"      # end-to-end generation
systemctl --user status llama
```
