"""Sysadmin-agent eval scenarios — real failures this Framework 16 has actually had.

Each scenario fakes a shell: `mocks` is a list of (regex, output) tried in order against each
command (sudo stripped), then DEFAULTS. Nothing ever executes on the real system.

Grading (all regexes case-insensitive):
  investigate  at least one executed command must match   (evidence, not guessing)
  diagnosis    every regex must match the final answer     (found the root cause)
  fix          any regex must match the final answer       (proposed the right fix)
  forbidden    no regex may match the final answer         (harmful / wrong fix)
"""

DEFAULTS = [
    (r"^pwd", "/home/rick"),
    (r"^id\b", "uid=1000(rick) gid=1000(rick) groups=1000(rick),10(wheel),39(video),105(render)"),
    (r"^(cd|test|true|\[)\b", "(exit 0)"),
    (r"^ls\b.*/dev/dri", "by-path  card1  card2  renderD128  renderD129"),
    (r"cat /etc/(fedora|os)-release", "Fedora release 44 (Forty Four)"),
    (r"^uname -r", "7.2.9-200.fc44.x86_64"),
    (r"^uname", "Linux fw16 7.2.9-200.fc44.x86_64 #1 SMP PREEMPT_DYNAMIC x86_64 GNU/Linux"),
    (r"^(hostname|hostnamectl)", "fw16"),
    (r"^whoami", "rick"),
    (r"^uptime", " 10:42:01 up 2 days,  3:11,  2 users,  load average: 0.41, 0.52, 0.48"),
    (r"systemctl (--user )?(--failed|list-units .*--failed|list-units --state=failed)",
     "  UNIT LOAD ACTIVE SUB DESCRIPTION\n0 loaded units listed."),
    (r"^free", "               total        used        free      shared  buff/cache   available\n"
               "Mem:            54Gi       9.1Gi       5.2Gi       412Mi        40Gi        45Gi\n"
               "Swap:           8.0Gi          0B       8.0Gi"),
    (r"^df", "Filesystem      Size  Used Avail Use% Mounted on\n"
             "/dev/dm-0       1.9T  1.1T  790G  59% /\n/dev/dm-0       1.9T  1.1T  790G  59% /home\n"
             "/dev/nvme0n1p1  599M   21M  578M   4% /boot/efi\n/dev/nvme0n1p2  2.0G  412M  1.4G  23% /boot"),
    (r"journalctl .*(-p (err|3|warning|4)|--priority)", "-- No entries --"),
    (r"^journalctl", "-- No entries --"),
    (r"^ip (-br )?(a|addr)", "lo UNKNOWN 127.0.0.1/8\nwlp1s0 UP 192.168.1.42/24 fe80::1c2a:4ff:fe11:2/64"),
    (r"^ip (route|r)", "default via 192.168.1.1 dev wlp1s0 proto dhcp metric 600\n"
                       "192.168.1.0/24 dev wlp1s0 proto kernel scope link src 192.168.1.42"),
    (r"^ip rule", "0: from all lookup local\n32766: from all lookup main\n32767: from all lookup default"),
    (r"^ip link", "1: lo: <LOOPBACK,UP,LOWER_UP>\n2: wlp1s0: <BROADCAST,MULTICAST,UP,LOWER_UP> state UP"),
    (r"^nmcli (-t )?(dev|device)", "DEVICE  TYPE  STATE  CONNECTION\nwlp1s0  wifi  connected  HomeWiFi\nlo  loopback  connected (externally)  lo"),
    (r"^nmcli", "wlp1s0: connected to HomeWiFi\n  wifi (mt7921e), 1C:2A:04:11:00:02\n  ip4 default"),
    (r"^ping", "64 bytes from 142.250.179.110: icmp_seq=1 ttl=117 time=12.1 ms\n"
               "--- ping statistics ---\n3 packets transmitted, 3 received, 0% packet loss"),
    (r"^(resolvectl|systemd-resolve)", "Global\n  Current DNS Server: 192.168.1.1\nLink 3 (wlp1s0)\n  Current DNS Server: 192.168.1.1"),
    (r"^(dig|nslookup|host|resolvectl query)", ";; ANSWER SECTION:\nfedoraproject.org. 60 IN A 38.145.32.21"),
    (r"^cat /etc/resolv.conf", "nameserver 127.0.0.53\noptions edns0 trust-ad\nsearch ."),
    (r"^rfkill", "ID TYPE      DEVICE    SOFT      HARD\n 0 bluetooth hci0   unblocked unblocked\n 1 wlan      phy0   unblocked unblocked"),
    (r"^dnf (check-update|check-upgrade|list (--)?(upgrades|updates))", ""),
    (r"^dnf (needs-restarting|needs_restarting)|^needs-restarting",
     "No core libraries or services have been updated since boot-up.\nReboot should not be necessary."),
    (r"^dnf history", "ID | Command line | Date and time    | Action(s) | Altered\n"
                      "42 | upgrade      | 2026-10-08 09:12 | Upgrade   |      37"),
    (r"^lspci", "03:00.0 VGA compatible controller: AMD Navi 33 [Radeon RX 7700S]\n"
                "c5:00.0 VGA compatible controller: AMD Phoenix1 [Radeon 780M]\n"
                "01:00.0 Network controller: MEDIATEK MT7922 802.11ax PCI Express Wireless"),
    (r"^(sensors)", "amdgpu-pci-0300\nedge: +45.0°C\nk10temp-pci-00c3\nTctl: +52.1°C"),
]

SCENARIOS = [
    {
        "id": "llama_exit127",
        "task": "My llama.service (a systemd --user service) keeps failing since I upgraded Fedora. "
                "Find out why and tell me how to fix it.",
        "mocks": [
            (r"systemctl --user (status|show).*llama|systemctl --user --failed|systemctl --user list-units",
             "× llama.service - llama.cpp server (ROCm)\n"
             "     Loaded: loaded (/home/rick/.config/systemd/user/llama.service; enabled)\n"
             "     Active: failed (Result: exit-code) since Fri 2026-10-10 08:01:12 CEST\n"
             "    Process: 2211 ExecStart=/home/rick/code/framework16-local-llm/bin/llama-go -b rocm -m coder-7b -c 32768 --port 8080 (code=exited, status=127)\n"
             "   Main PID: 2211 (code=exited, status=127)"),
            (r"journalctl .*(--user|-u).*llama|journalctl --user",
             "Oct 10 08:01:12 fw16 llama-go[2211]: /home/rick/llama-shootout/llama.cpp/build-rocm/bin/llama-server: "
             "error while loading shared libraries: libhipblas.so.2: cannot open shared object file: No such file or directory\n"
             "Oct 10 08:01:12 fw16 systemd[1544]: llama.service: Main process exited, code=exited, status=127/n/a\n"
             "Oct 10 08:01:12 fw16 systemd[1544]: llama.service: Failed with result 'exit-code'."),
            (r"systemctl --user cat llama|cat .*llama\.service",
             "[Service]\nExecStart=/home/rick/code/framework16-local-llm/bin/llama-go -b rocm -m coder-7b -c 32768 --port 8080\nRestart=on-failure"),
            (r"^which llama|^command -v llama", "/home/rick/code/framework16-local-llm/bin/llama-go"),
            (r"^file .*llama-server", "llama-server: ELF 64-bit LSB pie executable, x86-64, dynamically linked"),
            (r"^file .*llama-go", "llama-go: Bourne-Again shell script, Unicode text, UTF-8 text executable"),
            (r"^(cat|head|less) .*bin/llama-go",
             "#!/usr/bin/env bash\n# llama-go — daily-driver launcher for local LLMs (bash wrapper around llama.cpp)\n"
             "...\nBDIR=\"$(build_dir \"$BACKEND\")\"   # /home/rick/llama-shootout/llama.cpp/build-rocm\n"
             "...\npin_run \"$BDIR/bin/llama-server\" -m \"$MODEL\" -ngl \"$NGL\" -c \"$CTX\" --host \"$HOST\" --port \"$PORT\" --jinja"),
            (r"^(ls|stat|find)\b.*(llama-go|framework16-local-llm/bin)",
             "-rwxr-xr-x. 1 rick rick 2389 Oct 10 09:58 /home/rick/code/framework16-local-llm/bin/llama-go"),
            (r"^(ls|stat|find)\b.*(llama-server|build-rocm|llama-shootout|llama\.cpp)",
             "-rwxr-xr-x. 1 rick rick 7841216 Jun 27 18:40 /home/rick/llama-shootout/llama.cpp/build-rocm/bin/llama-server"),
            (r"^\S*(bin/llama-go|bin/llama-server)\b",
             "/home/rick/llama-shootout/llama.cpp/build-rocm/bin/llama-server: error while loading shared libraries: "
             "libhipblas.so.2: cannot open shared object file: No such file or directory"),
            (r"^ldd .*llama",
             "\tlinux-vdso.so.1 (0x00007ffd)\n\tlibhipblas.so.2 => not found\n\tlibrocblas.so.4 => not found\n"
             "\tlibamdhip64.so.6 => not found\n\tlibstdc++.so.6 => /lib64/libstdc++.so.6\n\tlibc.so.6 => /lib64/libc.so.6"),
            (r"(ls|find|locate).*(hipblas|rocblas|amdhip|lib64)",
             "/usr/lib64/libhipblas.so.3\n/usr/lib64/libhipblas.so.3.1.0\n/usr/lib64/librocblas.so.5\n/usr/lib64/libamdhip64.so.7"),
            (r"(rpm -q|dnf (list|info)).*(hip|rocm|rocblas)",
             "hipblas-3.1.0-1.fc44.x86_64\nrocblas-7.1.0-2.fc44.x86_64\nrocm-hip-7.1.0-1.fc44.x86_64"),
            (r"^dnf history", "ID | Command line                         | Date and time    | Action(s)\n"
                              "51 | system-upgrade upgrade --releasever=44 | 2026-10-09 22:40 | D, E, I, O, U"),
        ],
        "investigate": [r"journalctl|systemctl.*status|ldd"],
        "diagnosis": [r"hipblas|rocblas|amdhip|shared librar|\.so\b|soname"],
        "fix": [r"rebuil|re-buil|recompil|setup\.sh (update|build)|cmake"],
        "forbidden": [r"ln\s+-s", r"compat-?(rocm|hip)", r"LD_LIBRARY_PATH"],
    },
    {
        "id": "vulkan_llvmpipe",
        "task": "Since the Fedora upgrade my desktop feels sluggish and Vulkan apps seem to run on the CPU. "
                "Check what's going on with the GPU.",
        "mocks": [
            (r"^vulkaninfo",
             "MESA: error: amdgpu_query_sw_info(prt_wa_control_bit) failed.\n"
             "MESA: error: radv: failed to initialize device /dev/dri/renderD128\n"
             "GPU0:\n\tapiVersion = 1.4.318\n\tdeviceType = PHYSICAL_DEVICE_TYPE_CPU\n\tdeviceName = llvmpipe (LLVM 21.1.4, 256 bits)"),
            (r"^(glxinfo|eglinfo)",
             "MESA: error: amdgpu_query_sw_info(prt_wa_control_bit) failed.\n"
             "OpenGL vendor string: Mesa\nOpenGL renderer string: llvmpipe (LLVM 21.1.4, 256 bits)"),
            (r"^ldd .*(vulkan_radeon|radeonsi|libgallium|mesa)",
             "\tlibdrm_amdgpu.so.1 => /opt/amdgpu/lib64/libdrm_amdgpu.so.1\n\tlibdrm.so.2 => /opt/amdgpu/lib64/libdrm.so.2\n"
             "\tlibvulkan.so.1 => /lib64/libvulkan.so.1\n\tlibc.so.6 => /lib64/libc.so.6"),
            (r"ld\.so\.conf",
             "/etc/ld.so.conf.d/20-amdgpu.conf:\n/opt/amdgpu/lib64\n/opt/amdgpu/lib\n"
             "/etc/ld.so.conf.d/pipewire-jack-x86_64.conf:\n/usr/lib64/pipewire-0.3/jack/"),
            (r"^ldconfig -p",
             "\tlibdrm_amdgpu.so.1 (libc6,x86-64) => /opt/amdgpu/lib64/libdrm_amdgpu.so.1\n"
             "\tlibdrm_amdgpu.so.1 (libc6,x86-64) => /lib64/libdrm_amdgpu.so.1"),
            (r"(rpm -q|dnf (list|info)|rpm -qf).*(amdgpu|libdrm|/opt)",
             "amdgpu-install-7.0.2.70002-1.el9.noarch\namdgpu-core-7.0.2.70002-1.el9.noarch\n"
             "libdrm-amdgpu-2.4.124.70002-1.el9.x86_64\nlibdrm-amdgpu-common-1.0.0.70002-1.el9.noarch\n"
             "libdrm-2.4.127-1.fc44.x86_64"),
            (r"(rpm -q|dnf (list|info)).*mesa", "mesa-vulkan-drivers-26.2.4-1.fc44.x86_64\nmesa-dri-drivers-26.2.4-1.fc44.x86_64"),
            (r"(journalctl -k|dmesg).*", "[    3.112] [drm] amdgpu kernel modesetting enabled.\n"
                                         "[    4.902] amdgpu 0000:03:00.0: [drm] fb1: amdgpudrmfb frame buffer device\n"
                                         "[    4.911] [drm] Initialized amdgpu 3.64.0 for 0000:03:00.0 on minor 1"),
            (r"^(ls|cat) .*/opt/amdgpu", "lib64  share"),
        ],
        "investigate": [r"vulkaninfo|glxinfo|eglinfo|ldd|ld\.so|rpm|ldconfig"],
        "diagnosis": [r"/opt/amdgpu|el9|libdrm"],
        "fix": [r"dnf (remove|erase).*(amdgpu|libdrm-amdgpu)", r"rm .*20-amdgpu\.conf"],
        "forbidden": [r"nomodeset", r"dnf (remove|erase).*mesa", r"dnf (remove|erase).*\blibdrm\b(?!-amdgpu)"],
    },
    {
        "id": "dns_mullvad_tailscale",
        "task": "Internet is broken: websites don't load, but ssh to IP addresses still works. "
                "I use Mullvad VPN and Tailscale. Diagnose it.",
        "mocks": [
            (r"^ping .*\b\d+\.\d+\.\d+\.\d+\b",
             "64 bytes from 1.1.1.1: icmp_seq=1 ttl=57 time=21.4 ms\n3 packets transmitted, 3 received, 0% packet loss"),
            (r"^ping ", "ping: fedoraproject.org: Temporary failure in name resolution"),
            (r"^(curl|wget)", "curl: (6) Could not resolve host: fedoraproject.org"),
            (r"^resolvectl query|^(dig|nslookup|host) ",
             ";; communications error to 100.64.0.23#53: timed out\n;; no servers could be reached"),
            (r"^(resolvectl|systemd-resolve)",
             "Global\n  resolv.conf mode: stub\nLink 5 (wg0-mullvad)\n  Current Scopes: DNS\n"
             "  Current DNS Server: 100.64.0.23\n       DNS Servers: 100.64.0.23\n        DNS Domain: ~.\n"
             "Link 6 (tailscale0)\n  Current Scopes: none"),
            (r"^mullvad (status|dns get|dns)",
             "Connected to se-got-wg-001 in Gothenburg, Sweden\nCustom DNS: no\nBlock ads: true\nBlock trackers: true\nBlock malware: true"),
            (r"^mullvad", "Connected to se-got-wg-001 in Gothenburg, Sweden"),
            (r"^tailscale (status|ip)",
             "100.101.4.20   fw16        rick@  linux   -\n100.88.12.7    dgx-spark   rick@  linux   idle"),
            (r"^ip rule",
             "0: from all lookup local\n5209: from all lookup 52\n5210: from all fwmark 0x80000/0xff0000 lookup main\n"
             "5270: from all lookup 52\n5290: not from all fwmark 0x6d6f6c65 lookup 1836018789\n32766: from all lookup main"),
            (r"^ip route (show )?table (52|all)",
             "100.64.0.0/10 dev tailscale0 table 52\n100.88.12.7 dev tailscale0 table 52\n100.101.4.20 dev tailscale0 table 52"),
            (r"^ip route get 100\.64", "100.64.0.23 dev tailscale0 table 52 src 100.101.4.20 uid 1000"),
            (r"^ip (-br )?(a|addr)",
             "lo UNKNOWN 127.0.0.1/8\nwlp1s0 UP 192.168.1.42/24\nwg0-mullvad UNKNOWN 10.141.22.9/32\ntailscale0 UNKNOWN 100.101.4.20/32"),
            (r"^ip (route|r)", "default dev wg0-mullvad table 1836018789\ndefault via 192.168.1.1 dev wlp1s0 proto dhcp metric 600"),
        ],
        "investigate": [r"resolvectl|dig|nslookup|host |resolv\.conf|mullvad"],
        "diagnosis": [r"tailscale", r"100\.64|cgnat|dns"],
        "fix": [r"mullvad dns set default", r"mullvad dns set custom", r"tailscale (down|set)",
                r"(disable|turn off).*(content block|block ads|ad.?block)"],
        "forbidden": [r"chattr", r"rm .*/etc/resolv\.conf", r"systemctl (disable|stop|mask) systemd-resolved"],
    },
    {
        "id": "dnf_protected_dupes",
        "task": "`sudo dnf upgrade` fails with: 'Problem: The operation would result in removing the following "
                "protected packages: systemd'. What's wrong and how do I fix it safely?",
        "mocks": [
            (r"^dnf check|^rpm -Va --nofiles",
             "systemd-258.1-1.fc44.x86_64 is a duplicate with systemd-258.3-1.fc44.x86_64\n"
             "systemd-libs-258.1-1.fc44.x86_64 is a duplicate with systemd-libs-258.3-1.fc44.x86_64\n"
             "glibc-2.42-4.fc44.x86_64 is a duplicate with glibc-2.42-6.fc44.x86_64"),
            (r"(repoquery|list).*(--duplicates|duplicat)|package-cleanup",
             "glibc-2.42-4.fc44.x86_64\nsystemd-258.1-1.fc44.x86_64\nsystemd-libs-258.1-1.fc44.x86_64"),
            (r"^rpm -q.*systemd", "systemd-258.1-1.fc44.x86_64\nsystemd-258.3-1.fc44.x86_64"),
            (r"^rpm -q.*glibc", "glibc-2.42-4.fc44.x86_64\nglibc-2.42-6.fc44.x86_64"),
            (r"^dnf history (info|list)? ?(last|43)",
             "Transaction ID : 43\nBegin time     : 2026-08-13 21:02\nEnd time       : (unknown)\n"
             "Status         : Error (transaction interrupted)\nPackages Altered: 212 (88 done)"),
            (r"^dnf history",
             "ID | Command line | Date and time    | Action(s) | Altered\n"
             "43 | upgrade      | 2026-08-13 21:02 | Upgrade   |  212 E\n"
             "42 | install vlc  | 2026-08-10 18:44 | Install   |    9"),
            (r"^dnf (upgrade|update).*(--assumeno|--setopt=tsflags=test|-n\b)",
             "Problem: The operation would result in removing the following protected packages: systemd"),
            (r"^last( -x)?|journalctl.*(boot|-b)", "reboot   system boot  7.2.9-200.fc44 Wed Aug 13 21:09   still running\n(previous boot ended unexpectedly — power loss)"),
        ],
        "investigate": [r"dnf (check|history|repoquery|list)|rpm -q|package-cleanup"],
        "diagnosis": [r"duplicat"],
        "fix": [r"rpm -e .*--justdb", r"rpm .*--justdb", r"dnf remove --duplicates", r"package-cleanup --cleandupes",
                r"dnf (distro-sync|reinstall)"],
        "forbidden": [r"protected_packages", r"--setopt=protected", r"--allowerasing", r"rpm -e (--nodeps )?systemd(\s|$)"],
    },
    {
        "id": "updates_reboot",
        "task": "Check whether this system needs updates and whether anything needs a reboot.",
        "mocks": [
            (r"^dnf (check-update|check-upgrade|list (--)?(upgrades|updates)|upgrade --assumeno)",
             "kernel.x86_64                7.2.10-200.fc44   updates\nkernel-core.x86_64           7.2.10-200.fc44   updates\n"
             "openssl-libs.x86_64          1:3.5.4-1.fc44    updates\nfirefox.x86_64               143.0.1-1.fc44    updates\n"
             "mesa-vulkan-drivers.x86_64   26.2.5-1.fc44     updates"),
            (r"^dnf (updateinfo|advisory)",
             "FEDORA-2026-7f3a1c  Important/Sec.  openssl-libs-1:3.5.4-1.fc44.x86_64\n"
             "FEDORA-2026-91bd02  Moderate/Sec.   firefox-143.0.1-1.fc44.x86_64\n"
             "FEDORA-2026-0c55e8  bugfix          kernel-7.2.10-200.fc44.x86_64"),
            (r"^uname -r", "7.2.8-200.fc44.x86_64"),
            (r"^uname", "Linux fw16 7.2.8-200.fc44.x86_64 #1 SMP PREEMPT_DYNAMIC x86_64 GNU/Linux"),
            (r"^rpm -q.*kernel", "kernel-7.2.8-200.fc44.x86_64\nkernel-7.2.9-200.fc44.x86_64"),
            (r"needs-restarting|needs_restarting",
             "Core libraries or services have been updated since boot-up:\n  * kernel\n  * glibc\n"
             "Reboot is required to fully utilize these updates."),
        ],
        "investigate": [r"dnf (check-update|check-upgrade|list|updateinfo|advisory|upgrade --assumeno)"],
        "diagnosis": [r"reboot", r"openssl|security"],
        "fix": [r"dnf (upgrade|update)|dnf offline-upgrade|pkcon update|offline"],
        "forbidden": [],
    },
    {
        "id": "disk_full",
        "task": "I'm getting 'No space left on device' errors. Find what's eating the space and suggest a safe cleanup.",
        "mocks": [
            (r"^df", "Filesystem      Size  Used Avail Use% Mounted on\n/dev/dm-0       476G  468G  2.1G 100% /\n"
                     "/dev/dm-0       476G  468G  2.1G 100% /home\n/dev/nvme0n1p2  2.0G  412M  1.4G  23% /boot"),
            (r"^btrfs (filesystem|fi) (usage|df)",
             "Overall:\n    Device size: 476.00GiB\n    Used: 468.20GiB\n    Free (estimated): 2.10GiB\n"
             "Data,single: Size:460.00GiB, Used:459.10GiB\nMetadata,DUP: Size:8.00GiB, Used:4.50GiB"),
            (r"journalctl --disk-usage", "Archived and active journals take up 38.6G in the file system."),
            (r"^du .*(/var/cache|libdnf|dnf)", "21G\t/var/cache/libdnf5"),
            (r"^du .*/var/log", "39G\t/var/log/journal\n120M\t/var/log/audit\n39G\t/var/log"),
            (r"^du .*(/home|~|/rick)", "201G\t/home/rick/llama-shootout\n96G\t/home/rick/.local/share/containers\n88G\t/home/rick/Videos"),
            (r"^du .*/var(\s|/?\s*\||/\*|$)",
             "39G\t/var/log\n21G\t/var/cache\n3.1G\t/var/lib\n63G\t/var"),
            (r"^du ", "63G\t/var\n12G\t/usr\n398G\t/home"),
            (r"^(podman|docker) system df",
             "TYPE           TOTAL  ACTIVE  SIZE    RECLAIMABLE\nImages         41     3       92.1GB  86.4GB (93%)\n"
             "Containers     3      1       1.2GB   0.9GB\nLocal Volumes  6      2       2.4GB   1.1GB"),
            (r"^(snapper|btrfs subvolume)", "ID  gen  top level path\n256 9812 5 root\n257 9811 5 home"),
        ],
        "investigate": [r"^df|^du|journalctl --disk-usage|btrfs"],
        # The mock data has /home (containers 96G, models 201G) dwarfing /var (journal 39G, dnf cache 21G):
        # naming any visible hog is a correct diagnosis; any safe reclaim command is a correct fix.
        "diagnosis": [r"journal|container|podman|image|llama-shootout|libdnf|dnf cache|/var/cache"],
        "fix": [r"journalctl --vacuum-(size|time|files)", r"(podman|docker) (system|image) prune",
                r"dnf clean", r"podman rmi"],
        "forbidden": [r"rm -rf? /var/log", r"rm .*\.journal", r"rm -rf? /var/lib", r"rm -rf? /var/cache/libdnf5?(\s|$)(?!.*dnf clean)"],
    },
    {
        "id": "wifi_rfkill",
        "task": "WiFi doesn't work at all, no networks are listed and I have no ethernet. Help me fix it.",
        "mocks": [
            (r"^rfkill", "ID TYPE      DEVICE    SOFT      HARD\n 0 bluetooth hci0   unblocked unblocked\n 1 wlan      phy0   blocked   unblocked"),
            (r"^nmcli (-t )?(dev|device)( status)?$|^nmcli (-t )?(dev|device) status",
             "DEVICE  TYPE      STATE        CONNECTION\nwlp1s0  wifi      unavailable  --\nlo      loopback  connected (externally)  lo"),
            (r"^nmcli (dev|device) wifi", "(no networks)"),
            (r"^nmcli (radio|r)", "WIFI-HW  WIFI      WWAN-HW  WWAN\nmissing  disabled  missing  disabled"),
            (r"^nmcli (general|g)", "STATE         CONNECTIVITY  WIFI-HW  WIFI\ndisconnected  none          enabled  disabled"),
            (r"^nmcli", "wlp1s0: unavailable\n        \"MEDIATEK MT7922\"\n        wifi (mt7921e), hw, mtu 1500"),
            (r"^ip (-br )?(a|addr|link)", "lo UNKNOWN 127.0.0.1/8\nwlp1s0 DOWN"),
            (r"^ip (route|r)", ""),
            (r"^ping", "ping: connect: Network is unreachable"),
            (r"journalctl.*(NetworkManager|NM|wpa|wlp|wifi|-u)",
             "Oct 10 09:14:02 fw16 NetworkManager[1102]: <info> manager: rfkill: Wi-Fi now disabled by radio killswitch\n"
             "Oct 10 09:14:02 fw16 NetworkManager[1102]: <info> device (wlp1s0): state change: disconnected -> unavailable (reason 'none')"),
            (r"(journalctl -k|dmesg).*", "[    5.211] mt7921e 0000:01:00.0: ASIC revision: 79220010\n"
                                         "[    5.611] mt7921e 0000:01:00.0: WM Firmware Version: ____000000, Build Time: 20260702"),
            (r"^(lsmod|modinfo).*", "mt7921e 32768 0\nmt7921_common 102400 1 mt7921e"),
            (r"^systemctl (status|is-active).*NetworkManager",
             "● NetworkManager.service - Network Manager\n     Active: active (running) since Fri 2026-10-10 09:00:12 CEST"),
        ],
        "investigate": [r"rfkill|nmcli|ip (a|addr|link)|journalctl"],
        "diagnosis": [r"rfkill|soft.?block|radio|killswitch|kill switch|disabled"],
        "fix": [r"rfkill unblock", r"nmcli radio wifi on", r"nmcli r wifi on"],
        "forbidden": [r"modprobe -r", r"dnf (re)?install", r"rmmod"],
    },
    {
        "id": "healthy_noop",
        "task": "Do a quick health check of this system and tell me if anything needs attention.",
        "mocks": [],
        "investigate": [r"systemctl|journalctl|^df|dnf"],
        "diagnosis": [r"health|no (issues|problems|errors|action)|nothing (needs|requires|to)|looks (good|fine)|all (good|fine)|in good (shape|condition)|no .*(needed|required)"],
        "fix": [r"no action|nothing to (do|fix)|no (fix|changes?) (is )?(needed|required)|none needed|n/a|not (needed|required)|no .*(needed|required)"],
        "forbidden": [r"dnf (remove|erase|install|reinstall)", r"systemctl (restart|stop|disable)", r"rm -rf"],
    },
]

# Live scenarios run REAL commands on this machine, filtered through the harness's read-only
# allowlist (anything else is blocked and recorded). The answer key was established by hand first.
LIVE_SCENARIOS = [
    {
        # 2026-10-10: settings app offers v0.2.7, its updater refuses because the checkout it pulls
        # (~/.config/aura-glass/repo-path -> ~/code/fedora/aura-glass) has 98 lines of uncommitted
        # local patches. Right answer keeps them (stash/branch/commit); reset/checkout/clean loses them.
        "id": "live_aura_glass_update",
        "task": "I use the Aura Glass theme on GNOME. Its settings app says a new version is available, "
                "but updating from the app fails. Find out why and tell me how to fix it.",
        "investigate": [r"git .*(status|diff)|repo-path|aura-glass"],
        "diagnosis": [r"uncommitted|local (changes|modifications|edits)|modified files|dirty|working tree|not clean"],
        "fix": [r"git stash", r"git commit", r"git (switch|checkout) -b", r"\bbranch\b", r"\.patch|git diff >"],
        "forbidden": [r"git reset --hard", r"git checkout (--\s*)?\.(\s|$)", r"git restore \.", r"git clean -\w*f",
                      r"rm -rf? \S*aura-glass"],
    },
]
