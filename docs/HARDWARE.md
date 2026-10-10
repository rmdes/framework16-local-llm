# Hardware notes & troubleshooting

## Device map (this machine)

| Role | Marketing | Arch | DRI node | Use |
|---|---|---|---|---|
| dGPU | Radeon RX 7700S | **gfx1102** (Navi 33) | card1 / renderD128 | **inference target** |
| iGPU | Radeon 780M | gfx1103 (Phoenix) | card2 / renderD129 | display; rocBLAS problem-child, avoided |
| NPU | XDNA 1 | `aie2` / AIE-ML | — | no Linux LLM runtime |

Confirm with: `rocminfo | grep -E 'Name|gfx'`, `vulkaninfo | grep -i deviceName`, and
`for c in /sys/class/drm/card*/device; do lspci -s "$(basename $(readlink -f $c))"; done`.

## Why the NPU is unused

LLM inference on AMD NPUs under Linux (Lemonade + FastFlowLM) requires **XDNA 2** (Ryzen AI 300/400 series).
The 7040-series 7940HS has **XDNA 1** — unsupported. All acceleration here is the dGPU plus AVX-512 CPU fallback.

## Common build/run failures on Fedora

| Symptom | Cause | Fix |
|---|---|---|
| `ld.lld: error: unable to find library -lamdhip64` | unversioned `libamdhip64.so` symlink missing | install `rocm-hip-devel` |
| cmake "C compiler hipcc broken" | forcing `hipcc` as C/C++ compiler | use `HIP_PATH=$(hipconfig -R)`, `HIPCXX=$(hipconfig -l)/clang`; don't set `CMAKE_C_COMPILER=hipcc` |
| `Could not find SPIRV-Headers` (Vulkan) | shader toolchain incomplete | install `spirv-headers-devel spirv-tools-devel glslang` |
| `dnf` breaks after ROCm install | AMD el9 repo cross-grades into `/opt/rocm` | glob-pin devel packages to the running `.fcNN` (setup.sh does this via `rpm -E %fedora`) |
| service exits **127**: `libhipblas.so.2: cannot open shared object file` | Fedora upgrade bumped ROCm (F44: 6.4 → 7.1, `hipblas .so.2→.3`, `rocblas .4→.5`, `amdhip64 .6→.7`) | rebuild clean — `llama-go` now detects this and rebuilds automatically; or `./setup.sh build rocm`. Never symlink old sonames (ABI break) |
| Vulkan shows only `llvmpipe`; GNOME/Hyprland feel sluggish; `amdgpu_query_sw_info(...) failed` in logs | leftover AMD el9 `libdrm-amdgpu` in `/opt/amdgpu` (via `/etc/ld.so.conf.d/20-amdgpu.conf`) shadows Fedora libdrm; newer Mesa can't init the GPU | `sudo dnf remove amdgpu-install amdgpu-core libdrm-amdgpu libdrm-amdgpu-common && sudo ldconfig`, re-login. `./setup.sh doctor` flags it |
| 14B `failed to load model` at `-ngl 99` | 8.37 GiB > 8 GB VRAM | use `-ngl 44` (partial offload) |
| ROCm run uses CPU / wrong GPU | iGPU (gfx1103) picked or no offload | pin with `HIP_VISIBLE_DEVICES=$(hip_idx)`; verify `rocm-smi --showmeminfo vram` shows GPU[0] |

## Process management gotcha

`pkill -f llama-server` matches any command line containing that string — including your own shell.
Use `pkill -x llama-server` (exact process-name match) instead.

## ROCm vs Vulkan, in one line

ROCm = tuned rocBLAS GEMM → faster prefill (compute-bound). Vulkan = lighter RADV kernels → faster decode
(bandwidth-bound) and zero ROCm maintenance. Keep both built; choose per workload.
