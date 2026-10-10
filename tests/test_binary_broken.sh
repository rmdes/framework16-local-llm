#!/usr/bin/env bash
# test_binary_broken.sh — binary_broken must flag a binary whose shared lib vanished
# (what a Fedora ROCm soname bump does to llama-server) and pass a healthy one.
# Needs gcc. Run: tests/test_binary_broken.sh
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/bin/_common.sh"

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
echo 'int f(void){return 0;}' > "$tmp/l.c"
echo 'int f(void);int main(void){return f();}' > "$tmp/m.c"
gcc -shared -fPIC -o "$tmp/libgone.so" "$tmp/l.c"
gcc -o "$tmp/app" "$tmp/m.c" -L"$tmp" -lgone -Wl,-rpath,"$tmp"

if binary_broken "$tmp/app"; then echo "FAIL: healthy binary flagged"; exit 1; fi
rm "$tmp/libgone.so"
binary_broken "$tmp/app" || { echo "FAIL: missing-lib binary not flagged"; exit 1; }
echo "ok: binary_broken"
