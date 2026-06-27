#!/usr/bin/env bash
# setup.sh — bootstrap the Framework 16 local-LLM stack (Fedora).
# Subcommands (default: all):
#   ./setup.sh deps              install ROCm + Vulkan + build dependencies (needs sudo)
#   ./setup.sh build [backend]   clone llama.cpp + build rocm and/or vulkan (default both)
#   ./setup.sh model <key>       download a catalog model (3b|7b|14b)
#   ./setup.sh service [opts]    install + enable the systemd --user service
#   ./setup.sh all               deps -> build -> model 7b -> service   (one-shot)
#   ./setup.sh doctor            verify hardware + toolchain
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/bin/_common.sh"

# ---- deps (Fedora) ----------------------------------------------------------
cmd_deps(){
  command -v dnf >/dev/null || die "non-Fedora system: install ROCm 6.x, Vulkan/RADV, glslc, spirv-tools, cmake/ninja manually, then run: ./setup.sh build"
  say "installing dependencies (sudo — fingerprint/password prompt expected)"
  # *-devel for rocblas/hipblas collide with the AMD el9 repo (which installs to /opt/rocm
  # and breaks dnf); glob-pin to .fc43 so only the Fedora-native packages are eligible.
  sudo dnf install -y \
    git cmake ninja-build gcc gcc-c++ \
    rocminfo rocm-hip-devel hipcc rocblas hipblas \
    'rocblas-devel-*.fc43*' 'hipblas-devel-*.fc43*' \
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

# ---- model download ---------------------------------------------------------
cmd_model(){
  local key="${1:?usage: ./setup.sh model <3b|7b|14b>}" rec fn url
  rec="$(catalog_lookup "$key")" || die "unknown model key '$key'"
  fn="${rec%%|*}"; url="$(echo "$rec" | cut -d'|' -f2)"
  mkdir -p "$MODELS_DIR"
  if [ -f "$MODELS_DIR/$fn" ]; then say "$fn already present"; return; fi
  say "downloading $fn"
  curl -fL --retry 3 -o "$MODELS_DIR/$fn" "$url"
}

# ---- systemd --user service -------------------------------------------------
cmd_service(){
  local BACKEND=rocm MODEL=7b CTX=16384 PORT=8080
  while [ $# -gt 0 ]; do case "$1" in
    -b) BACKEND="$2"; shift 2;; -m) MODEL="$2"; shift 2;;
    -c) CTX="$2"; shift 2;; -p) PORT="$2"; shift 2;; *) shift;;
  esac; done
  [ -x "$(build_dir "$BACKEND")/bin/llama-server" ] || die "build $BACKEND first: ./setup.sh build $BACKEND"
  [ -f "$(model_path "$MODEL")" ] || die "model $MODEL not downloaded: ./setup.sh model $MODEL"
  local unitdir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"; mkdir -p "$unitdir"
  say "installing $unitdir/llama.service ($BACKEND, $MODEL, ctx=$CTX, :$PORT)"
  sed -e "s|@LLAMAGO@|$REPO_DIR/bin/llama-go|g" -e "s|@BACKEND@|$BACKEND|g" \
      -e "s|@MODEL@|$MODEL|g" -e "s|@CTX@|$CTX|g" -e "s|@PORT@|$PORT|g" \
      "$REPO_DIR/systemd/llama.service.in" > "$unitdir/llama.service"
  systemctl --user daemon-reload
  systemctl --user enable --now llama.service
  say "service started — http://127.0.0.1:$PORT  (enable boot-without-login: sudo loginctl enable-linger $USER)"
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
  echo -n "rocm build: "; [ -x "$BUILD_ROCM/bin/llama-server" ] && echo ok || echo missing
  echo -n "vulkan build: "; [ -x "$BUILD_VULKAN/bin/llama-server" ] && echo ok || echo missing
  echo -n "service: "; systemctl --user is-active llama.service 2>/dev/null || echo inactive
}

case "${1:-all}" in
  deps)    cmd_deps;;
  build)   shift; cmd_build "${1:-both}";;
  model)   shift; cmd_model "$@";;
  service) shift; cmd_service "$@";;
  doctor)  cmd_doctor;;
  all)     cmd_deps; cmd_build both; cmd_model 7b; cmd_service;;
  *) die "unknown subcommand '$1' (deps|build|model|service|all|doctor)";;
esac
