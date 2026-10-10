#!/usr/bin/env bash
# One-time, root: snapper snapshots of / before and after every dnf transaction — the sysadmin agent's
# safety net. Idempotent. Run: sudo agent/install-snapshots.sh
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "needs root: sudo $0" >&2; exit 1; }
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

dnf install -y snapper libdnf5-plugin-actions
# /home is its own btrfs subvolume, so this covers the OS, not your files.
snapper list-configs | grep -q '^root ' || snapper -c root create-config /
# dnf pre/post pairs only — no hourly timeline snapshots eating the disk.
snapper -c root set-config TIMELINE_CREATE=no NUMBER_CLEANUP=yes NUMBER_LIMIT=20 NUMBER_LIMIT_IMPORTANT=10
install -D -m 0644 "$HERE/snapper.actions" /etc/dnf/libdnf5-plugins/actions.d/snapper.actions
systemctl enable --now snapper-cleanup.timer
snapper -c root create -d "baseline (install-snapshots.sh)"
snapper -c root list | tail -3
echo "done — every dnf transaction now gets a pre/post snapshot pair"
