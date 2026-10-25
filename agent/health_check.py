#!/usr/bin/env python3
"""Daily read-only health check for the Framework 16. Run by fw16-health.timer (./setup.sh agent).

Facts are collected by fixed read-only commands — the model never runs anything here. Gemma (the local
llama.service) only summarises them against agent/RUNBOOK.md. If the model is unreachable, the raw
facts are still reported. Output: ~/.local/state/fw16-sysadmin/health-<date>.md + OPEN.md, the standing
list of open issues with their age. A daily "ATTENTION" popup got ignored (13 of 16 days, 304 updates piled
up), so it only notifies when an issue is new, open 3 days, then weekly while it stays open.
"""
from __future__ import annotations

import datetime
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
    ("Pending Flatpak updates", "flatpak remote-ls --updates --columns=origin | grep -vcx fedora"),  # fedora = OCI remote, always listed
    ("Pending security advisories", "dnf updateinfo list --security -q --cacheonly | head -n 20"),
    ("Reboot needed", "dnf needs-restarting -r 2>&1 | tail -n 3"),
    ("Running vs newest installed kernel", "echo running $(uname -r); rpm -q kernel --last | head -n 1"),
    ("Disk usage", "df -h --output=target,size,used,avail,pcent / /home /boot /boot/efi"),
    ("Last snapshots", "snapper -c root list 2>&1 | tail -n 3"),
    ("Local LLM service", "systemctl --user is-active llama-proxy.socket"),  # llama.service itself runs on demand
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


JOURNAL_MIN = 10  # ponytail: errors/24h from one source before it counts; one-off errors stay in the report only
HARMLESS = (  # journal errors the runbook already explains — never an open issue (they still show in the report)
    "Ignoring duplicate name",  # RUNBOOK #10: two packages provide one D-Bus name; every dnf run reloads dbus
    "NAME_CONFLICT: new_policy_object(): 'docker-forwarding'",  # RUNBOOK #7
)


def journal_sources() -> dict[str, int]:
    out = run("journalctl -p err --since -24h -q -o json --output-fields=SYSLOG_IDENTIFIER,_COMM,MESSAGE")
    counts: dict[str, int] = {}
    for line in out.splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if any(h in str(e.get("MESSAGE", "")) for h in HARMLESS):
            continue
        src = e.get("SYSLOG_IDENTIFIER") or e.get("_COMM") or "?"
        counts[src] = counts.get(src, 0) + 1
    return counts


def find_issues(out: dict[str, str], journal: dict[str, int]) -> dict[str, str]:
    """Stable key -> one-line detail. Keys must not change day to day (no counts in them), or age resets."""
    issues = {}
    for title in ("Failed system units", "Failed user units"):
        for line in out[title].splitlines():
            if line != "(none)" and line.split():
                issues[f"failed:{line.split()[0]}"] = f"{title[:-1].lower()}: {line.split()[0]} — systemctl status {line.split()[0]}"
    for src, n in journal.items():
        if n >= JOURNAL_MIN:
            issues[f"journal:{src}"] = f"{n} errors in 24h from {src} — journalctl -p err --since -24h -t {src}"
    rpm, flat = out["Pending updates"].strip(), out["Pending Flatpak updates"].strip()
    if rpm.isdigit() and int(rpm):
        sec = "" if out["Pending security advisories"] == "(none)" else ", incl. security advisories"
        issues["updates:rpm"] = f"{rpm} RPM updates pending{sec} — sudo dnf upgrade"
    if flat.isdigit() and int(flat):
        issues["updates:flatpak"] = f"{flat} Flatpak updates pending — flatpak update -y"
    if "Reboot is required" in out["Reboot needed"]:
        issues["reboot"] = "reboot needed for installed updates"
    for line in out["Disk usage"].splitlines()[1:]:
        cols = line.split()
        if len(cols) == 5 and cols[4].rstrip("%").isdigit() and int(cols[4].rstrip("%")) >= 90:
            issues[f"disk:{cols[0]}"] = f"{cols[0]} is {cols[4]} full ({cols[3]} left) — fw16-du {cols[0]}"
    if out["Local LLM service"] != "active":
        issues["llama"] = "local model socket not active — systemctl --user status llama-proxy.socket"
    return issues


def track(state: dict, issues: dict[str, str], today: datetime.date) -> tuple[dict, list[str]]:
    """New state + the keys worth a notification today: new, open 3 days, then every 7 days."""
    new_state, due = {}, []
    for key, detail in issues.items():
        old = state.get(key)
        if old is None:
            new_state[key] = {"first": today.isoformat(), "notified": today.isoformat(), "reminders": 0, "detail": detail}
            due.append(key)
            continue
        since = (today - datetime.date.fromisoformat(old["notified"])).days
        remind = since >= (3 if old["reminders"] == 0 else 7)
        new_state[key] = {**old, "detail": detail,
                          "notified": today.isoformat() if remind else old["notified"],
                          "reminders": old["reminders"] + remind}
        if remind:
            due.append(key)
    return new_state, due


def open_md(state: dict, today: datetime.date, report: Path) -> str:
    rows = sorted(state.items(), key=lambda kv: kv[1]["first"])
    lines = [f"# Open issues — {today.isoformat()}", "", f"Latest report: {report}", ""]
    for _, v in rows:
        lines.append(f"- [{(today - datetime.date.fromisoformat(v['first'])).days}d] {v['detail']}")
    return "\n".join(lines if rows else lines + ["Nothing open."]) + "\n"


def main() -> None:
    out = {title: run(cmd) for title, cmd in CHECKS}
    facts = "\n\n".join(f"## {title}\n$ {cmd}\n{out[title]}" for title, cmd in CHECKS)
    summary = summarise(facts)
    headline = (summary.splitlines()[0] if summary else "STATUS: model unreachable — raw facts in the report")
    STATE.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today()
    report = STATE / f"health-{today.isoformat()}.md"
    report.write_text(f"# Health check {time.strftime('%Y-%m-%d %H:%M')}\n\n"
                      f"{summary or headline}\n\n---\n\n{facts}\n")
    state_file = STATE / "open.json"
    old = json.loads(state_file.read_text()) if state_file.exists() else {}
    state, due = track(old, find_issues(out, journal_sources()), today)
    state_file.write_text(json.dumps(state, indent=1))
    (STATE / "OPEN.md").write_text(open_md(state, today, report))
    if due:
        body = "\n".join(f"{'NEW' if k not in old else str((today - datetime.date.fromisoformat(state[k]['first'])).days) + 'd'}: "
                         f"{state[k]['detail'].split(' — ')[0]}" for k in due)
        subprocess.run(["notify-send", "-u", "critical", "-a", "fw16 sysadmin",
                        f"{len(state)} open issue(s)", f"{body}\n\n{STATE / 'OPEN.md'}"], check=False)
    print(STATE / "OPEN.md")


if __name__ == "__main__":
    main()
