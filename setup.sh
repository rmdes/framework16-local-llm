#!/usr/bin/env bash
# setup.sh — bootstrap the Framework 16 local-LLM stack (Fedora).
# Subcommands (default: all):
#   ./setup.sh deps              install ROCm + Vulkan + build dependencies (needs sudo)
#   ./setup.sh build [backend]   clone llama.cpp + build rocm and/or vulkan (default both)
#   ./setup.sh update            pull latest llama.cpp + clean-rebuild both backends (+ restart service)
#   ./setup.sh model <key>       download a catalog model (3b|7b|coder-7b|14b)
#   ./setup.sh service [opts]    install + enable the systemd --user service
#   ./setup.sh agent             install the opencode Sysadmin agent (agent/opencode-sysadmin.md + RUNBOOK.md)
#   ./setup.sh all               deps -> build -> model coder-7b -> service   (one-shot)
#   ./setup.sh doctor            verify hardware + toolchain
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/bin/_common.sh"

# ---- deps (Fedora) ----------------------------------------------------------
cmd_deps(){
  command -v dnf >/dev/null || die "non-Fedora system: install ROCm 6.4+ (7.x on Fedora 44+), Vulkan/RADV, glslc, spirv-tools, cmake/ninja manually, then run: ./setup.sh build"
  say "installing dependencies (sudo — fingerprint/password prompt expected)"
  # *-devel for rocblas/hipblas collide with the AMD el9 repo (which installs to /opt/rocm
  # and breaks dnf); glob-pin to the running release (.fcNN) so only Fedora-native packages
  # are eligible. Never hardcode NN — a stale pin matches nothing after a release upgrade.
  local fc; fc="fc$(rpm -E %fedora)"
  sudo dnf install -y \
    git cmake ninja-build gcc gcc-c++ \
    rocminfo rocm-hip-devel hipcc rocblas hipblas \
    "rocblas-devel-*.$fc*" "hipblas-devel-*.$fc*" \
    vulkan-loader vulkan-loader-devel vulkan-headers mesa-vulkan-drivers \
    glslc glslang spirv-headers-devel spirv-tools-devel \
    || die "dnf failed — resolve AMD-repo conflicts first (see docs/HARDWARE.md)"
  # compute access for the current user
  sudo usermod -a -G render,video "$USER" 2>/dev/null || true
}

# ---- build ------------------------------------------------------------------
cmd_build(){
  local which="${1:-both}"
  command -v cmake >/dev/null || die "build tools missing — run ./setup.sh deps first"
  [ -d "$LLAMA_SRC" ] || { say "cloning llama.cpp -> $LLAMA_SRC"; mkdir -p "$FW16_HOME"; git clone --depth 1 https://github.com/ggml-org/llama.cpp "$LLAMA_SRC"; }
  case "$which" in
    rocm|both)  ensure_binary rocm   llama-server; ensure_binary rocm   llama-cli; ensure_binary rocm   llama-bench;;
  esac
  case "$which" in
    vulkan|both) ensure_binary vulkan llama-server; ensure_binary vulkan llama-cli; ensure_binary vulkan llama-bench;;
  esac
  say "build complete"
}

# ---- update llama.cpp -------------------------------------------------------
# Pull upstream and rebuild both backends from EMPTY build dirs. Clean is deliberate: after a
# Fedora upgrade a reused CMakeCache still points at the old toolchain (ROCm sonames, GCC N's
# libgomp.so) and the relink fails or produces a dead binary.
cmd_update(){
  [ -d "$LLAMA_SRC/.git" ] || die "no llama.cpp checkout at $LLAMA_SRC — run ./setup.sh build first"
  local before; before="$(git -C "$LLAMA_SRC" rev-parse --short HEAD)"
  git -C "$LLAMA_SRC" pull --ff-only
  say "llama.cpp $before -> $(git -C "$LLAMA_SRC" rev-parse --short HEAD); rebuilding clean"
  systemctl --user stop llama.service 2>/dev/null || true   # on demand: the next request loads the new binary
  rm -rf "$BUILD_ROCM" "$BUILD_VULKAN"
  cmd_build both
  say "done — re-measure with: bin/llama-bench-shootout 7b"
}

# ---- model download ---------------------------------------------------------
cmd_model(){
  local key="${1:?usage: ./setup.sh model <3b|7b|coder-7b|14b>}" rec fn url
  rec="$(catalog_lookup "$key")" || die "unknown model key '$key'"
  fn="${rec%%|*}"; url="$(echo "$rec" | cut -d'|' -f2)"
  mkdir -p "$MODELS_DIR"
  if [ -f "$MODELS_DIR/$fn" ]; then say "$fn already present"; return; fi
  say "downloading $fn"
  curl -fL --retry 3 -o "$MODELS_DIR/$fn" "$url"
}

# ---- systemd --user service -------------------------------------------------
cmd_service(){
  local BACKEND=rocm MODEL=coder-7b CTX=32768 PORT=8080   # 32k: agentic clients (opencode) need headroom or they compaction-loop
  while [ $# -gt 0 ]; do case "$1" in
    -b) BACKEND="$2"; shift 2;; -m) MODEL="$2"; shift 2;;
    -c) CTX="$2"; shift 2;; -p) PORT="$2"; shift 2;; *) shift;;
  esac; done
  [ -x "$(build_dir "$BACKEND")/bin/llama-server" ] || die "build $BACKEND first: ./setup.sh build $BACKEND"
  [ -f "$(model_path "$MODEL")" ] || die "model $MODEL not downloaded: ./setup.sh model $MODEL"
  local unitdir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user" u; mkdir -p "$unitdir"
  # On demand: llama-proxy.socket owns :PORT, the first connection starts llama.service on PORT+10000,
  # and the proxy exits after IDLE without a connection, which stops the model (StopWhenUnneeded).
  local BACKPORT=$((PORT + 10000)) IDLE="${LLAMA_IDLE:-15min}"
  say "installing on-demand llama.service ($BACKEND, $MODEL, ctx=$CTX) behind :$PORT, idle stop after $IDLE"
  systemctl --user disable --now llama.service 2>/dev/null || true   # was always-on (WantedBy=default.target)
  for u in llama.service llama-proxy.socket llama-proxy.service; do
    sed -e "s|@LLAMAGO@|$REPO_DIR/bin/llama-go|g" -e "s|@BACKEND@|$BACKEND|g" -e "s|@MODEL@|$MODEL|g" \
        -e "s|@CTX@|$CTX|g" -e "s|@PORT@|$PORT|g" -e "s|@BACKPORT@|$BACKPORT|g" -e "s|@IDLE@|$IDLE|g" \
        "$REPO_DIR/systemd/$u.in" > "$unitdir/$u"
  done
  systemctl --user daemon-reload
  systemctl --user enable --now llama-proxy.socket
  say "listening on http://127.0.0.1:$PORT — model loads on first request (enable boot-without-login: sudo loginctl enable-linger $USER)"
}

# ---- opencode sysadmin agent ----------------------------------------------
# The installed file is generated: permissions + rules from agent/opencode-sysadmin.md, knowledge from
# agent/RUNBOOK.md. Re-run after editing either (every new incident -> RUNBOOK entry -> ./setup.sh agent).
cmd_agent(){
  local dir="${XDG_CONFIG_HOME:-$HOME/.config}/opencode/agent" out
  out="$dir/Sysadmin.md"
  [ -d "$dir" ] || die "no opencode agent dir at $dir — install opencode first"
  { cat "$REPO_DIR/agent/opencode-sysadmin.md"; echo; cat "$REPO_DIR/agent/RUNBOOK.md"; } > "$out"
  mkdir -p "$HOME/.local/bin" && ln -sf "$REPO_DIR/agent/fw16-du" "$HOME/.local/bin/fw16-du"
  say "installed $out (model llama-local/gemma4-e4b — serve it with: ./setup.sh service -b vulkan -m gemma4-e4b)"
  # Daily read-only health check: fixed commands collect facts, the local model only summarises them.
  local unitdir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"; mkdir -p "$unitdir"
  cat > "$unitdir/fw16-health.service" <<UNIT
[Unit]
Description=fw16 read-only health check (summarised by the local model)

[Service]
Type=oneshot
StandardInput=null
ExecStart=/usr/bin/python3 $REPO_DIR/agent/health_check.py
UNIT
  cat > "$unitdir/fw16-health.timer" <<UNIT
[Unit]
Description=Daily fw16 health check

[Timer]
OnCalendar=*-*-* 10:00
Persistent=true
RandomizedDelaySec=10m

[Install]
WantedBy=timers.target
UNIT
  # Weekly Docker cleanup: keep the 2 newest rmdes/* builds, cap BuildKit cache (~2 builds). Worst case: full rebuild.
  cat > "$unitdir/fw16-docker-prune.service" <<UNIT
[Unit]
Description=fw16 weekly Docker prune (keep last 2 builds)

[Service]
Type=oneshot
StandardInput=null
Nice=19
IOSchedulingClass=idle
ExecStart=$REPO_DIR/agent/docker-prune
UNIT
  cat > "$unitdir/fw16-docker-prune.timer" <<UNIT
[Unit]
Description=Weekly fw16 Docker prune

[Timer]
OnCalendar=weekly
Persistent=true
RandomizedDelaySec=1h

[Install]
WantedBy=timers.target
UNIT
  systemctl --user daemon-reload
  systemctl --user enable --now fw16-health.timer fw16-docker-prune.timer
  say "weekly docker prune enabled (dry run: DRY_RUN=1 agent/docker-prune)"
  say "daily health check enabled (reports: ~/.local/state/fw16-sysadmin/) — run now: systemctl --user start fw16-health"
}

# ---- doctor -----------------------------------------------------------------
cmd_doctor(){
  echo "FW16_HOME : $FW16_HOME"; echo "MODELS_DIR: $MODELS_DIR"; echo "GFX target: $GFX"
  # Capture-then-match (not `| grep -q`): under `set -o pipefail`, grep -q closes the pipe
  # early and the producer dies with SIGPIPE(141), which pipefail would report as failure.
  local rocm_out vk_out
  rocm_out="$(rocminfo 2>/dev/null || true)"
  echo -n "discrete GPU ($GFX) visible to ROCm: "; case "$rocm_out" in *"$GFX"*) echo yes;; *) echo "NO (check amdgpu/ROCm)";; esac
  vk_out="$(vulkaninfo 2>/dev/null || true)"
  echo -n "Vulkan RADV NAVI33: "; case "$vk_out" in *[Nn][Aa][Vv][Ii]33*) echo yes;; *) echo "NO";; esac
  # Leftover AMD el9 packages (amdgpu-install) put an old libdrm_amdgpu in /opt/amdgpu via
  # ld.so.conf; a newer Fedora Mesa then fails to init (RADV/radeonsi) and Vulkan + the whole
  # desktop silently fall back to llvmpipe (CPU).
  local radv; radv="$(ldd /usr/lib64/libvulkan_radeon.so 2>/dev/null || true)"
  echo -n "Mesa uses Fedora libdrm: "; case "$radv" in
    */opt/amdgpu/*) echo "NO — el9 libdrm shadowing Mesa; fix: sudo dnf remove amdgpu-install amdgpu-core libdrm-amdgpu libdrm-amdgpu-common && sudo ldconfig, then re-login";;
    *) echo yes;; esac
  local b bin; for b in rocm vulkan; do
    bin="$(build_dir "$b")/bin/llama-server"
    echo -n "$b build: "
    if [ ! -x "$bin" ]; then echo missing
    elif binary_broken "$bin"; then echo "BROKEN (missing libs after upgrade) — rebuilt automatically on next llama-go, or: ./setup.sh build $b"
    else echo ok; fi
  done
  echo -n "endpoint socket: "; systemctl --user is-active llama-proxy.socket 2>/dev/null || echo inactive
  echo -n "model (on demand): "; systemctl --user is-active llama.service 2>/dev/null || echo inactive
}

case "${1:-all}" in
  deps)    cmd_deps;;
  build)   shift; cmd_build "${1:-both}";;
  update)  cmd_update;;
  model)   shift; cmd_model "$@";;
  service) shift; cmd_service "$@";;
  agent)   cmd_agent;;
  doctor)  cmd_doctor;;
  all)     cmd_deps; cmd_build both; cmd_model coder-7b; cmd_service;;
  *) die "unknown subcommand '$1' (deps|build|update|model|service|agent|all|doctor)";;
esac
