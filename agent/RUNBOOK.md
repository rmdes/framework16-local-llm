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
  `flatpak remote-ls --updates --columns=origin | grep -vcx fedora` → number of Flatpak updates. The `fedora`
  remote is OCI (oci+https://registry.fedoraproject.org): remote-ls ALWAYS lists its refs as updatable even when
  they are current — ignore them. `flatpak update` saying "Nothing to update" is the final word.
  `fwupdmgr get-updates` → firmware ("No updates available" refers to firmware ONLY)
  Report each count separately. Any number above 0 means updates are waiting.
- Fix, one source at a time: RPMs `sudo dnf upgrade -y` (snapper snapshots it automatically). It takes 15-60 min:
  ALWAYS call the shell tool with timeout 3600000 — the default 120000 kills dnf mid-run (an interrupted
  transaction leaves duplicate packages, see #4). Long silence during install = SELinux relabel, normal.
  Flatpaks also get timeout 1800000.
  Flatpaks `flatpak update -y` (no sudo, NOT snapshotted — roll back one app with `flatpak update --commit=<old> <app>`);
  firmware `fwupdmgr update` (rick runs it himself — needs a reboot).
- After applying, run the same count again and report what is actually left — never claim "all N applied" unseen.
- Success = dnf's last line `Complete!` and the recount is 0. `[RPM] file /lib/modules/<old kernel>/…: remove failed:
  No such file or directory` lines are the OLD kernel's already-missing dirs being cleaned up — harmless, not a failure.
  `dnf history list` prints NEWEST FIRST: pipe it through head, never tail. New kernel installed →
  tell rick a reboot is needed (`dnf needs-restarting -r`).
- A cancelled GNOME Software offline update ("Pending offline transaction has been invalidated") is harmless; just apply as above.

## 7. firewalld logs `ERROR: NAME_CONFLICT: new_policy_object(): 'docker-forwarding'`
- Cause: harmless. docker-ce creates the `docker-forwarding` policy in firewalld's RUNTIME config. When docker
  restarts while firewalld keeps running, docker asks to create it again → firewalld logs the conflict, docker
  logs "Firewalld: docker zone already exists, returning" and carries on.
- Check: the error's timestamp is seconds after `journalctl -u docker` shows "Starting docker.service";
  `firewall-cmd --get-policies` lists docker-forwarding; containers have network.
- Fix: none — "No action needed".
- Never: `firewall-cmd --reload` or `systemctl restart firewalld` while docker runs (wipes docker's runtime rules →
  containers lose networking until docker restarts), `docker network prune`, or deleting the policy.

## 8. udev: `75-davincipanel.rules:2 Failed to resolve group 'resolve', ignoring: Unknown group`
- Cause: DaVinci Resolve's installer (`/opt/resolve`) dropped `/usr/lib/udev/rules.d/75-davincipanel.rules`
  (not owned by any rpm). Line 2 is `KERNEL=="hidraw*", SUBSYSTEM=="hidraw", MODE="0777", GROUP="resolve"`
  — it has NO vendor match, so it targets EVERY hidraw device. Because the group is missing, udev drops the
  line: `ls -l /dev/hidraw*` shows 0600 root, i.e. the warning is currently protecting you.
- Check: `cat` the rule, `getent group resolve` (empty), `rpm -qf` (not owned), `ls -l /dev/hidraw*`.
- Fix (rick runs it, root): override with a same-named file in /etc, limited to Blackmagic's vendor id 1edb:
  `printf '%s\n' 'SUBSYSTEM=="usb", ATTRS{idVendor}=="1edb", TAG+="uaccess"' 'KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{idVendor}=="1edb", TAG+="uaccess"' | sudo tee /etc/udev/rules.d/75-davincipanel.rules`
  then `sudo udevadm control --reload && sudo udevadm trigger`.
- Never: create the `resolve` group or swap in another group (activates MODE=0777 on all HID devices — keyboards,
  fingerprint reader), or edit the file in /usr/lib (installer overwrites it).
