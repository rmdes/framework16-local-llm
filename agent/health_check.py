#!/usr/bin/env python3
"""Daily read-only health check for the Framework 16. Run by fw16-health.timer (./setup.sh agent).

Facts are collected by fixed read-only commands — the model never runs anything here. Gemma (the local
llama.service) only summarises them against agent/RUNBOOK.md. If the model is unreachable, the raw
facts are still reported. Output: a desktop notification + ~/.local/state/fw16-sysadmin/health-<date>.md
"""
from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = Path.home() / ".local/state/fw16-sysadmin"
API = "http://127.0.0.1:8080/v1/chat/completions"

CHECKS = [  # (title, command) — every one read-only
    ("Failed system units", "systemctl --failed --no-legend --plain"),
    ("Failed user units", "systemctl --user --failed --no-legend --plain"),
    ("Errors in the journal (last 24h, newest 30)", "journalctl -p err --since -24h --no-pager -q -o short | tail -n 30"),
    ("Pending updates", "dnf check-update -q --cacheonly | grep -c '\\.' || true"),
    ("Pending security advisories", "dnf updateinfo list --security -q --cacheonly | head -n 20"),
    ("Reboot needed", "dnf needs-restarting -r 2>&1 | tail -n 3"),
    ("Running vs newest installed kernel", "echo running $(uname -r); rpm -q kernel --last | head -n 1"),
    ("Disk usage", "df -h --output=target,size,used,avail,pcent / /home /boot /boot/efi"),
    ("Last snapshots", "snapper -c root list 2>&1 | tail -n 3"),
    ("Local LLM service", "systemctl --user is-active llama.service"),
]

PROMPT = """You are the health-check summariser for rick's Fedora laptop. Below are the outputs of fixed
read-only checks. Using ONLY these facts (and the runbook for known failure patterns), write:
STATUS: one line, starting with OK, ATTENTION or PROBLEM.
Then at most 5 bullets, most important first: what needs attention and the exact command to look further
or fix it. If everything is fine, say so in one bullet. Never invent facts that are not in the outputs."""


def run(cmd: str) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
        return (r.stdout + r.stderr).strip() or "(none)"
    except subprocess.TimeoutExpired:
        return "(timed out)"


def summarise(facts: str) -> str | None:
    body = {"messages": [{"role": "system", "content": PROMPT + "\n\n" + (HERE / "RUNBOOK.md").read_text()},
                         {"role": "user", "content": facts}],
            "temperature": 0.3, "max_tokens": 3000, "chat_template_kwargs": {"enable_thinking": True}}
    req = urllib.request.Request(API, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return (json.load(r)["choices"][0]["message"].get("content") or "").strip() or None
    except OSError:
        return None


def main() -> None:
    facts = "\n\n".join(f"## {title}\n$ {cmd}\n{run(cmd)}" for title, cmd in CHECKS)
    summary = summarise(facts)
    headline = (summary.splitlines()[0] if summary else "STATUS: model unreachable — raw facts in the report")
    STATE.mkdir(parents=True, exist_ok=True)
    report = STATE / f"health-{time.strftime('%Y-%m-%d')}.md"
    report.write_text(f"# Health check {time.strftime('%Y-%m-%d %H:%M')}\n\n"
                      f"{summary or headline}\n\n---\n\n{facts}\n")
    urgency = "critical" if "PROBLEM" in headline else "normal"
    subprocess.run(["notify-send", "-u", urgency, "-a", "fw16 sysadmin", headline.replace("STATUS: ", ""),
                    f"Report: {report}"], check=False)
    print(report)


if __name__ == "__main__":
    main()
