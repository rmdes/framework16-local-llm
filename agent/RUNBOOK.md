# Runbook — rick's Framework 16 (Fedora 44)

Known failure modes on THIS machine. They recur. Match symptoms against them first, but confirm
with evidence before concluding — a runbook entry is a hypothesis, not a diagnosis.

## Machine
- Framework 16, Ryzen 9 7940HS, RX 7700S dGPU (gfx1102, card1/renderD128) + 780M iGPU. btrfs on LUKS. GNOME + Hyprland.
- ROCm and Mesa come from Fedora's own repos. Local LLM stack: `~/code/framework16-local-llm`
  (llama.cpp builds under `~/llama-shootout/llama.cpp/build-{rocm,vulkan}`, `llama.service` is a systemd --user unit).
- VPN: Mullvad + Tailscale both installed.

## 1. A service/binary exits 127 after a Fedora upgrade
- Symptom: `status=127`, journal says `error while loading shared libraries: libXXX.so.N`.
- Check: `ldd <binary> | grep 'not found'`; `ls /usr/lib64/libXXX.so*` usually shows a NEWER soname (Fedora bumped ROCm: libhipblas .2→.3, rocblas .4→.5, amdhip64 .6→.7).
- Fix: rebuild against the new libraries. For llama.cpp: `cd ~/code/framework16-local-llm && ./setup.sh update` (clean rebuild + service restart).
- Never: symlink the old soname to the new one, or paper over it with LD_LIBRARY_PATH.

## 2. Desktop sluggish / Vulkan or OpenGL on `llvmpipe` (CPU)
- Cause seen here: AMD's EL9 `amdgpu-install` packages put an old `libdrm_amdgpu` in `/opt/amdgpu`
  via `/etc/ld.so.conf.d/20-amdgpu.conf`, shadowing Fedora's; newer Mesa fails to init (`amdgpu_query_sw_info ... failed`).
- Check: `ldd /usr/lib64/libvulkan_radeon.so | grep drm` points into `/opt/amdgpu`; `rpm -qa | grep -E 'amdgpu|el9'`.
- Fix: `sudo dnf remove amdgpu-install amdgpu-core libdrm-amdgpu libdrm-amdgpu-common && sudo ldconfig`, then log out/in.
- Never: nomodeset, removing Mesa or Fedora's libdrm.

## 3. DNS dead, raw IPs (ssh to an IP) still work — Mullvad + Tailscale
- Cause: Mullvad DNS content blocking hands out a resolver in 100.64.0.0/10 (e.g. 100.64.0.23).
  That is Tailscale's CGNAT range, so Tailscale's routing/netfilter swallows the DNS traffic.
- Check: `resolvectl status` shows a 100.64.x.x DNS server; `ip route get 100.64.0.23`; `mullvad dns get`; `tailscale status`.
- Fix: `mullvad dns set default` (blocking off → resolver moves to 10.64.0.1). Or take Tailscale down while on Mullvad.
- Never: hand-edit or chattr /etc/resolv.conf, or disable systemd-resolved.

## 4. `dnf upgrade` → "would result in removing the following protected packages: systemd"
- Cause: an INTERRUPTED earlier dnf transaction left old+new versions of many packages registered (duplicates).
  Nothing is wrong with systemd.
- Check: `dnf history` (a transaction with error/unfinished status), `dnf repoquery --installed --duplicates`, `dnf check`.
- Fix: remove only the OLD duplicates' rpmdb entries, then upgrade:
  `dnf repoquery --installed --duplicates --latest-limit=-1 --queryformat '%{name}-%{version}-%{release}.%{arch}\n' > stale.txt`
  then `sudo rpm -e --justdb --noscripts --nodeps $(cat stale.txt)` and `sudo dnf upgrade`.
- Never: override protected_packages, use --allowerasing, or remove systemd.

## 5. A dnf update sits silent for a long time on a `%post` scriptlet
- Usually a selinux-policy bump running a full restorecon relabel: ~50 min on this LUKS+btrfs disk. Not hung.
- Check: `ps -eo pid,stat,etimes,pcpu,args | grep -E 'rpm-tmp|fixfiles|restorecon'` — CPU time climbing = working.
- Never: Ctrl-C it. Interrupting a transaction is what causes #4.

## 6. "Are there updates?" / GNOME Software update failed or was cancelled
- GNOME Software updates THREE sources. Check EACH ONE IN ITS OWN COMMAND (never chain them — the
  outputs run together and one tool's "No updates available" gets misread as covering the others):
  `dnf check-update -q | grep -c '\.'` → number of RPM updates
  `flatpak remote-ls --updates | wc -l` → number of Flatpak updates (apps + runtimes)
  `fwupdmgr get-updates` → firmware ("No updates available" refers to firmware ONLY)
  Report each count separately. Any number above 0 means updates are waiting.
- Fix, one source at a time: RPMs `sudo dnf upgrade` (snapper snapshots it automatically);
  Flatpaks `flatpak update -y` (no sudo, NOT snapshotted — roll back one app with `flatpak update --commit=<old> <app>`);
  firmware `fwupdmgr update` (rick runs it himself — needs a reboot).
- A cancelled GNOME Software offline update ("Pending offline transaction has been invalidated") is harmless; just apply as above.
