#!/usr/bin/env python3
"""health_check issue tracking: stable keys, notify on new / 3 days / weekly, resolved issues drop out."""
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
from health_check import find_issues, track  # noqa: E402

OK = {"Failed system units": "(none)", "Failed user units": "(none)", "Pending updates": "0",
      "Pending Flatpak updates": "0", "Pending security advisories": "(none)",
      "Reboot needed": "Reboot should not be necessary.",
      "Disk usage": "Mounted on Size Used Avail Use%\n/ 1.9T 1.0T 674G 61%", "Local LLM service": "active"}

assert find_issues(OK, {"kernel": 2}) == {}, "healthy box, one-off errors -> nothing open"

bad = {**OK, "Pending updates": "304", "Pending security advisories": "FEDORA-2026-1 Critical/Sec. x",
       "Failed user units": "foo.service loaded failed failed Foo",
       "Disk usage": "Mounted on Size Used Avail Use%\n/ 1.9T 1.8T 40G 98%", "Local LLM service": "inactive"}
issues = find_issues(bad, {"hp": 40})
assert set(issues) == {"updates:rpm", "failed:foo.service", "disk:/", "journal:hp", "llama"}, issues
assert "security" in issues["updates:rpm"]

d = datetime.date(2026, 10, 1)
day = lambda n: d + datetime.timedelta(days=n)  # noqa: E731
s, due = track({}, issues, d)
assert sorted(due) == sorted(issues), "everything is new on day 0"
for n, expect in [(1, []), (2, []), (3, ["journal:hp"]), (4, []), (9, []), (10, ["journal:hp"])]:
    s, due = track(s, {"journal:hp": "x"}, day(n))
    assert due == expect, (n, due)
assert s["journal:hp"]["first"] == d.isoformat(), "age survives detail/count changes"
assert set(s) == {"journal:hp"}, "resolved issues drop out"
s, due = track(s, {}, day(11))
assert s == {} and due == []
print("ok: health issue tracking")
