# _common.sh — shared config + helpers for the Framework 16 local-LLM stack.
# Sourced by llama-go, llama-bench-shootout, and setup.sh. Not executable on its own.
#
# Path model (all overridable via env or ~/.config/fw16-llm/config):
#   FW16_HOME   : where llama.cpp source + builds live   (default ~/.local/share/fw16-llm)
#   MODELS_DIR  : where .gguf model files live           (default $FW16_HOME/models)
#   GFX         : discrete-GPU arch target               (default gfx1102 = RX 7700S)

# repo root = parent of this file's dir
_COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$_COMMON_DIR")"

# user config file (optional) overrides defaults
[ -f "${XDG_CONFIG_HOME:-$HOME/.config}/fw16-llm/config" ] && \
  . "${XDG_CONFIG_HOME:-$HOME/.config}/fw16-llm/config"

FW16_HOME="${FW16_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/fw16-llm}"
MODELS_DIR="${MODELS_DIR:-$FW16_HOME/models}"
LLAMA_SRC="${LLAMA_SRC:-$FW16_HOME/llama.cpp}"
BUILD_ROCM="$LLAMA_SRC/build-rocm"
BUILD_VULKAN="$LLAMA_SRC/build-vulkan"
GFX="${GFX:-gfx1102}"
CATALOG="$REPO_DIR/config/models.conf"

die(){ echo "error: $*" >&2; exit 1; }
say(){ printf '\033[1;36m==>\033[0m %s\n' "$*"; }

# build dir for a backend name
build_dir(){ case "$1" in rocm) echo "$BUILD_ROCM";; vulkan) echo "$BUILD_VULKAN";; *) die "unknown backend $1";; esac; }

# resolve a catalog key (3b|7b|14b) -> echoes "filename|url|ngl|note"
catalog_lookup(){
  local key="$1" line
  line="$(grep -E "^${key}\|" "$CATALOG" 2>/dev/null | head -1)" || true
  [ -n "$line" ] && echo "${line#*|}" || return 1
}

# absolute path to a model by catalog key (or pass a literal path through)
model_path(){
  local key="$1"
  if [ -f "$key" ]; then echo "$key"; return; fi
  local rec; rec="$(catalog_lookup "$key")" || die "no catalog entry '$key' (try: 3b 7b 14b, or a .gguf path)"
  echo "$MODELS_DIR/${rec%%|*}"
}
model_ngl(){ local rec; rec="$(catalog_lookup "$1")" && { rec="${rec#*|}"; rec="${rec#*|}"; echo "${rec%%|*}"; } || echo 99; }

# ROCm: HIP ordinal of the discrete GPU (its position among gfx agents in rocminfo)
hip_idx(){
  local i; i="$(rocminfo 2>/dev/null | grep -oE 'gfx[0-9]+' | grep -n "^${GFX}$" | head -1 | cut -d: -f1)"
  [ -n "$i" ] && echo $((i-1)) || echo 0
}
# Vulkan: device id (VulkanN) of the discrete GPU, matched by NAVI33; falls back to highest index
vk_dev(){
  local bin="$1" d
  d="$( "$bin" --list-devices 2>/dev/null | grep -i 'NAVI33' | grep -oE 'Vulkan[0-9]+' | head -1)"
  [ -n "$d" ] && echo "$d" || echo "Vulkan1"
}

# ensure a backend's binary (llama-server|llama-cli|llama-bench) exists; build if missing
ensure_binary(){
  local backend="$1" tool="$2" bdir; bdir="$(build_dir "$backend")"
  [ -x "$bdir/bin/$tool" ] && return 0
  [ -d "$LLAMA_SRC" ] || die "llama.cpp not found at $LLAMA_SRC — run setup.sh first"
  say "building $tool ($backend) — first use, one-time"
  if [ ! -e "$bdir/CMakeCache.txt" ]; then
    if [ "$backend" = rocm ]; then
      HIP_PATH="$(hipconfig -R)" HIPCXX="$(hipconfig -l)/clang" \
      cmake -S "$LLAMA_SRC" -B "$bdir" -DGGML_HIP=ON -DAMDGPU_TARGETS="$GFX" \
        -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF -DCMAKE_PREFIX_PATH=/usr >/dev/null
    else
      cmake -S "$LLAMA_SRC" -B "$bdir" -DGGML_VULKAN=ON \
        -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF >/dev/null
    fi
  fi
  cmake --build "$bdir" --target "$tool" -j "$(nproc)"
}
