# CLAUDE.md — Framework 16 Local LLM Stack

Guidance for Claude Code (or any agent) working in this repo.

## What this is

A thin, measured packaging of llama.cpp for the Framework 16 + Radeon RX 7700S (gfx1102, 8 GB). It is **shell + config**, plus one stdlib-Python eval harness (`eval/`) — no application code. The value is in the *correct ROCm-on-Fedora build recipe* and the *hardware-measured defaults*, not in abstraction.

## Architecture (one source of truth each)

- `bin/_common.sh` — sourced by everything. Owns: path resolution (`FW16_HOME`, `MODELS_DIR`, `LLAMA_SRC`, build dirs), GPU pinning (`hip_idx`, `vk_dev`), model-catalog lookup, and `ensure_binary` (the canonical build recipe). **Change build flags or pinning here, nowhere else.**
- `bin/llama-go` — launcher. Maps workload → backend/model, then pins and runs `llama-server`/`llama-cli`.
- `bin/llama-vulkan-mode` — convenience wrapper: stop ROCm service → run Vulkan on `:8081` → restore the service on exit (trap, NOT exec'd so the trap survives). For opencode's on-demand `llama-vulkan` provider.
- `bin/llama-bench-shootout` — benchmark harness.
- `config/models.conf` — the model catalog: `key|filename|url|ngl|note`. `ngl` values are **measured**, not guessed.
- `systemd/llama.service.in` — `@PLACEHOLDER@` template; `setup.sh service` substitutes absolute paths.
- `setup.sh` — orchestrator (`deps|build|update|model|service|all|doctor`).
- `eval/` — sysadmin-agent model eval (`sysadmin_eval.py`, scenarios, `report.py`, allowlist self-check). Results: `docs/AGENT_EVAL.md`.
- `agent/RUNBOOK.md` — this machine's known failure modes, fed to the local sysadmin agent. Every new incident → an entry → `./setup.sh agent`.
- `agent/opencode-sysadmin.md` — the opencode Sysadmin agent: permission rules + rules prompt. `./setup.sh agent` installs it (+ runbook appended), the daily `fw16-health.timer` (`agent/health_check.py`) and the weekly `fw16-docker-prune.timer` (`agent/docker-prune`: keep the 2 newest `rmdes/*` builds, BuildKit cache capped at 10GB — Cloudron builds once filled 1.3T).
- `agent/install-snapshots.sh` + `snapper.actions` — root, one-time: snapper pre/post snapshots around every dnf5 transaction.

## Hard-won facts — do not regress these

- **Discrete GPU is `gfx1102`** (RX 7700S, renderD128). The iGPU is `gfx1103` (780M) and is the rocBLAS problem-child — always target/pin the dGPU.
- **Fedora ROCm build needs `rocm-hip-devel`** for the `libamdhip64.so` linker symlink + HIP cmake config. Without it: `ld.lld: error: unable to find library -lamdhip64`.
- **Do NOT force `hipcc` as the C/C++ compiler.** Use `HIP_PATH=$(hipconfig -R)` (=/usr) and `HIPCXX=$(hipconfig -l)/clang`. Forcing hipcc makes cmake's trivial compiler test fail.
- **`rocblas-devel`/`hipblas-devel` collide with the AMD el9 repo** (installs to `/opt/rocm`, breaks `dnf`). Always glob-pin to the running `.fc$(rpm -E %fedora)` — never a hardcoded release; see `cmd_deps` in setup.sh.
- **Fedora upgrades bump ROCm sonames** (F44: ROCm 7.1, `libhipblas.so.3`). A stale binary still *exists* but exits 127. `ensure_binary` checks `ldd` (`binary_broken`) and rebuilds from a clean build dir — a reused CMakeCache relinks the old libs.
- **After any Fedora upgrade or llama.cpp pull, rebuild from EMPTY build dirs** (`./setup.sh update`). Stale CMakeCaches pin the old toolchain: F44 broke both on ROCm sonames *and* on GCC 15's `libgomp.so`. `binary_broken` only catches the first.
- **`llama-cli` is chat-only upstream (verified at `1623d8ce4`, 2026-10).** `-cnv`/`-no-cnv` are gone; one-shot is `-st -p "…"`. The old non-chat tool is `llama-completion`. Check `--help` for flags `llama-go` passes after every bump.
- **Never install the AMD el9 `amdgpu-install` stack on Fedora.** Its `libdrm-amdgpu` lands in `/opt/amdgpu` (ld.so.conf) and breaks newer Fedora Mesa → Vulkan + desktop on llvmpipe. Fedora ships all of ROCm natively; `doctor` checks for this.
- **Vulkan build needs** `spirv-headers-devel spirv-tools-devel glslang glslc` (build-time shader compile), beyond just `glslc`.
- **`pkill -f llama-server` self-matches** an agent shell whose command line contains the string. Use `pkill -x llama-server`.
- **14B Q4 (8.37 GiB) does not fit 8 GB.** `-ngl 99` → "failed to load model". Catalog pins it to `ngl 44` (partial offload).
- **Sysadmin agent model = Gemma 4 E4B, thinking ON, + `agent/RUNBOOK.md`** (eval 2026-10-10: 19/27, 12/12 on known incidents, 1 unsafe run). Thinking OFF makes it skip investigation. No model reasons through unfamiliar setups — escalate.
- **The eval's live mode runs model-chosen shell (`shell=True`) behind `READ_ONLY`.** Any change to the allowlist needs a bypass case in `eval/test_live_allowlist.py` (git `-c`/`--output`, `env CMD`, `sed w/e`, `find -exec`…).
- **opencode bash permissions match each command's text INCLUDING its redirect** (`cat x > f` vs `cat *` → allowed). Hence the trailing `"*>*": deny`. Unfixable gap: `{ cmd; } > f` / `( cmd ) > f` (redirect sits on the group). Last match wins: `"*": ask` first, denies last. `tests/test_sysadmin_permissions.py` ports the matcher — run it after any rule change.
- **`opencode run` hangs at `init` when stdin is an open pipe** (agent shells, scripts). Always `< /dev/null`.
- **This is dnf5**: `python3-dnf-plugin-snapper` is dnf4-only; snapshots go through `libdnf5-plugin-actions` + an actions file.
- **`/var/lib/docker` must be its own btrfs subvolume** (inode 256). Inside root, every snapper snapshot pins all docker layers + build cache — a 742G prune freed 0 bytes. The reflink migration in `install-snapshots.sh` took ~55 min for 35M build-cache files; prune the cache first if it ever has to run again.
- **Fake-shell output must never imply absence.** Unknown commands return an explicit "no data" — an empty string reads as "file missing" and sent models down false paths.

## Backend choice (measured, not preference)

ROCm wins prompt-processing ~30%; token-generation is near-parity (Vulkan +4% as of llama.cpp 2026-10 — it was +20% in June, so re-measure after every bump). Service = Vulkan running `gemma4-e4b` for the sysadmin agent (2026-10-10; coding moved to the DGX Spark). `llama-go` default = ROCm too (2026-10); Vulkan still wins decode on small models (3B +21%), so the gap is size-dependent. Don't flatten this into "X is faster" — it is workload-dependent.

## Conventions

- Bash with `set -euo pipefail`; helpers/config live in `_common.sh`, sourced via `BASH_SOURCE` dir.
- Keep models and builds **out of git** (see `.gitignore`); they live under `FW16_HOME`.
- New models: add a measured row to `config/models.conf` (run `llama-bench-shootout <key>` first to set `ngl`).
- Re-verify any hardware claim (`rocminfo`, `vulkaninfo`, `--list-devices`) before changing defaults.

## Verify a change

```bash
./setup.sh doctor                 # hardware + toolchain + libdrm + build health + service state
tests/test_binary_broken.sh       # stale-binary detection (needs gcc)
eval/test_live_allowlist.py       # eval security boundary + grader
tests/test_sysadmin_permissions.py  # opencode Sysadmin rules: read-only allowed, changes held
bin/llama-go --prompt "ping"      # end-to-end generation
systemctl --user status llama
```
