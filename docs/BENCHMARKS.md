# Benchmarks

All measured on a Framework 16 — Ryzen 9 7940HS, Radeon RX 7700S (gfx1102, 8 GB), Fedora 43,
llama.cpp commit `0ed235ea2`, Qwen2.5-Instruct **Q4_K_M**, via `llama-bench` (`-r 3`), pinned to the dGPU.

## Backend shootout (7B, full offload)

| Test | ROCm | Vulkan | Winner |
|---|---:|---:|---|
| pp512  (prompt processing) | 1133.9 t/s | 852.9 t/s | ROCm +33% |
| pp4096 (long prompt)       | 1020.5 t/s | 758.6 t/s | ROCm +35% |
| tg128  (token generation)  | 44.4 t/s   | 53.8 t/s   | Vulkan +21% |

Takeaways:
- ROCm's prefill lead is **stable ~33–35%** across prompt sizes — it does not runaway-widen.
- It pays off in **absolute time-to-first-token**: prefilling 4096 tokens ≈ 4.0 s (ROCm) vs 5.4 s (Vulkan), ~1.4 s saved, and that saving grows with prompt length.
- Decode (`tg128`) is unaffected by prompt size; Vulkan stays ~20% ahead.

## Model size sweep (ROCm)

| Model | File | Fits 8 GB? | ngl | pp512 | tg128 |
|---|---:|:--:|--:|---:|---:|
| Qwen2.5-3B  | 1.79 GiB | ✅ full | 99 | 2352 t/s | 80.5 t/s |
| Qwen2.5-7B  | 4.36 GiB | ✅ full | 99 | 1140 t/s | 44.8 t/s |
| Qwen2.5-14B | 8.37 GiB | ⚠️ partial | 44 | 482 t/s | 17.2 t/s |
| Qwen2.5-14B | 8.37 GiB | (CPU only) | 0 | 260 t/s | 6.3 t/s |

14B partial-offload sensitivity (layers on GPU → decode): `ngl 44 → 17.2`, `40 → 15.3`, `36 → 12.9`, `0 → 6.3` t/s.

## Reproduce

```bash
bin/llama-bench-shootout 7b           # backend shootout on 7B
bin/llama-bench-shootout 3b 7b 14b    # full size sweep
PP=512,4096 bin/llama-bench-shootout 7b
```

Comfort reference: reading speed ≈ 8–10 t/s, so 3B/7B feel instant and 14B (17 t/s) is comfortable for non-realtime work; 14B on CPU (6 t/s) is batch-only.
