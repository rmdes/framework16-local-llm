# Benchmarks

All measured on a Framework 16 — Ryzen 9 7940HS, Radeon RX 7700S (gfx1102, 8 GB),
Qwen2.5-Instruct **Q4_K_M**, via `llama-bench` (`-r 3`), pinned to the dGPU.

## Backend shootout (7B, full offload) — current

Fedora 44 (ROCm 7.1, Mesa 26.2.4 RADV, GCC 16), llama.cpp `1623d8ce4` (2026-10-10).

| Test | ROCm | Vulkan | Winner |
|---|---:|---:|---|
| pp512  (prompt processing) | 1301.6 t/s | 1000.5 t/s | ROCm +30% |
| pp4096 (long prompt)       | 1210.8 t/s | 911.0 t/s  | ROCm +33% |
| tg128  (token generation)  | 52.1 t/s   | 54.1 t/s   | Vulkan +4% |

Takeaways:
- ROCm's prefill lead is **stable ~30–33%** across prompt sizes.
- Time-to-first-token for 4096 tokens ≈ 3.4 s (ROCm) vs 4.5 s (Vulkan).
- **Decode is now near-parity** (Vulkan +4%, was +21%). ROCm is the better all-rounder; Vulkan remains
  the zero-maintenance fallback and the right pick only if you never send long prompts.

### What moved the numbers (same hardware, same model)

| Step | ROCm pp512 / pp4096 / tg128 | Vulkan pp512 / pp4096 / tg128 |
|---|---:|---:|
| F43 · ROCm 6.4 · llama.cpp `0ed235ea2` (2026-06) | 1133.9 / 1020.5 / 44.4 | 852.9 / 758.6 / 53.8 |
| F44 · ROCm 7.1 · Mesa 26.2 · same llama.cpp      | 1243.7 / 1141.7 / 46.5 | 1061.0 / 981.0 / 54.0 |
| F44 · llama.cpp `1623d8ce4` (2026-10)            | 1301.6 / 1210.8 / 52.1 | 1000.5 / 911.0 / 54.1 |

- **The OS upgrade alone** gave ROCm ~+10% prefill and Vulkan ~+25–30% prefill (Mesa).
- **The llama.cpp bump** gave ROCm +5–6% prefill and **+12% decode**, but cost Vulkan ~6–7% prefill.
  Decode on Vulkan was unchanged.

## Model size sweep — Fedora 44, llama.cpp `781dbc5ac` (2026-10-10)

| Model | File | Fits 8 GB? | ngl | ROCm pp512 | ROCm tg128 | Vulkan pp512 | Vulkan tg128 |
|---|---:|:--:|--:|---:|---:|---:|---:|
| Qwen2.5-3B  | 1.79 GiB | ✅ full | 99 | 2581 t/s | 86.6 t/s | 2089 t/s | **104.9 t/s** |
| Qwen2.5-7B¹ | 4.36 GiB | ✅ full | 99 | 1302 t/s | 52.1 t/s | 1000 t/s | 54.1 t/s |
| Qwen2.5-14B | 8.37 GiB | ⚠️ partial | 44 | 584 t/s | 18.9 t/s | 417 t/s | 19.2 t/s |

- ROCm leads prefill by 24–40% at every size.
- **Vulkan's decode lead depends on model size**: +21% on 3B, +4% on 7B, +2% on 14B (partial offload,
  so CPU-bound layers flatten the gap). For quick 3B chat, `llama-go -b vulkan -m 3b` is fastest.
- vs June (F43, `0ed235ea2`, ROCm only): 3B 2352 → 2581 / 80.5 → 86.6, 14B 482 → 584 / 17.2 → 18.9.

¹ 7B measured at `1623d8ce4` earlier the same day (see shootout above).

CPU-only 14B (June): 260 t/s pp512, 6.3 t/s tg128.

14B partial-offload sensitivity (June, ROCm; layers on GPU → decode): `ngl 44 → 17.2`, `40 → 15.3`, `36 → 12.9`, `0 → 6.3` t/s.

## Reproduce

```bash
bin/llama-bench-shootout 7b           # backend shootout on 7B
bin/llama-bench-shootout 3b 7b 14b    # full size sweep
PP=512,4096 bin/llama-bench-shootout 7b
```

Comfort reference: reading speed ≈ 8–10 t/s, so 3B/7B feel instant and 14B (17 t/s) is comfortable for non-realtime work; 14B on CPU (6 t/s) is batch-only.
