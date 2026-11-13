#!/usr/bin/env python3
"""Print remaining-quota data for Claude and Codex subscriptions as JSON.

Usage: fetch.py <usage.json>
  {"accounts": [
    {"label": "Claude", "kind": "claude", "dir": "~/.claude"},
    {"label": "Codex",  "kind": "codex",  "home": "~/.codex", "on": "<hc machine>", "color": "#10a37f"}
  ]}
`dir` is a Claude config dir, `home` a CODEX_HOME; `on` reads Codex on another herdr-core machine;
`color` overrides the bar colour. Without the file: one Claude account in $CLAUDE_CONFIG_DIR or ~/.claude.

Output: {"at": <unix>, "accounts": [{"label", "kind", "color", "bars": [{"name", "used", "resets"}], "error"}]}
How each source works: README.md.
"""
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# Runs where the Codex login lives; prints the account/rateLimits/read result.
CODEX = r"""
import json, os, select, subprocess, sys
env = dict(os.environ, CODEX_HOME=os.path.expanduser(sys.argv[1]))
env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + env.get("PATH", "")
p = subprocess.Popen(["codex", "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     stderr=subprocess.DEVNULL, text=True, env=env)
def send(o):
    p.stdin.write(json.dumps(o) + "\n"); p.stdin.flush()
send({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "herdr-usage", "version": "1"}}})
send({"method": "initialized"})
send({"id": 2, "method": "account/rateLimits/read", "params": {"excludeResetCreditDetails": True}})
out = {"error": {"message": "timeout"}}
while select.select([p.stdout], [], [], 20)[0]:
    line = p.stdout.readline()
    if not line: break
    m = json.loads(line)
    if m.get("id") == 2: out = m; break
p.kill()
print(json.dumps(out))
"""


def window(minutes):
    if not minutes:
        return ""
    if minutes % 1440 == 0:
        return f"{minutes // 1440}d"
    if minutes % 60 == 0:
        return f"{minutes // 60}h"
    return f"{minutes}m"


def claude(acct):
    path = os.path.abspath(os.path.expanduser(acct["dir"]))
    suffix = hashlib.sha256(path.encode()).hexdigest()[:8]
    secret = None
    for service in (f"Claude Code-credentials-{suffix}", "Claude Code-credentials"):
        r = subprocess.run(["security", "find-generic-password", "-s", service, "-w"],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            secret = r.stdout
            break
    if secret is None:
        raise RuntimeError("not logged in")
    token = json.loads(secret)["claudeAiOauth"]["accessToken"]
    req = urllib.request.Request(
        "https://api.anthropic.com/api/oauth/usage",
        headers={"Authorization": f"Bearer {token}", "anthropic-beta": "oauth-2025-04-20",
                 "User-Agent": "herdr-usage"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        raise RuntimeError("login expired" if e.code == 401 else f"http {e.code}")
    def ts(iso):
        return datetime.fromisoformat(iso).timestamp() if iso else None

    bars = []
    # `limits` is the newer shape and the only place model-scoped weekly limits (Fable) appear.
    for lim in data.get("limits") or []:
        model = ((lim.get("scope") or {}).get("model") or {}).get("display_name")
        name = {"session": "5h", "weekly_all": "7d"}.get(lim.get("kind")) or model
        if name and lim.get("percent") is not None:
            bars.append({"name": name, "used": lim["percent"], "resets": ts(lim.get("resets_at"))})
    if not bars:
        for key, name in (("five_hour", "5h"), ("seven_day", "7d")):
            w = data.get(key)
            if w and w.get("utilization") is not None:
                bars.append({"name": name, "used": w["utilization"], "resets": ts(w.get("resets_at"))})
    extra = data.get("extra_usage")
    if not bars and extra and extra.get("utilization") is not None:
        bars.append({"name": "mo", "used": extra["utilization"], "resets": None})
    return bars


def codex(acct):
    home = acct.get("home", "~/.codex")
    if acct.get("on"):
        # hc exec forwards no stdin, so the script travels as base64.
        b64 = base64.b64encode(CODEX.encode()).decode()
        cmd = ["hc", "exec", "--on", acct["on"], "--", "python3", "-c",
               f"import base64;exec(base64.b64decode('{b64}'))", home]
    else:
        cmd = [sys.executable, "-c", CODEX, home]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError((r.stderr.strip().splitlines() or ["unreachable"])[-1][:60])
    msg = json.loads(r.stdout.strip().splitlines()[-1])
    if "error" in msg:
        raise RuntimeError(msg["error"].get("message", "error")[:60])
    limits = msg["result"]["rateLimits"]
    bars = []
    for key in ("primary", "secondary"):
        w = limits.get(key)
        if w:
            bars.append({"name": window(w.get("windowDurationMins")), "used": w["usedPercent"],
                         "resets": w.get("resetsAt")})
    return bars


def read(acct):
    out = {"label": acct.get("label", acct["kind"]), "kind": acct["kind"], "color": acct.get("color"),
           "bars": [], "error": None}
    try:
        out["bars"] = {"claude": claude, "codex": codex}[acct["kind"]](acct)
    except Exception as e:  # one account failing must not hide the others
        out["error"] = str(e) or type(e).__name__
    return out


def main():
    try:
        accounts = json.load(open(sys.argv[1]))["accounts"]
    except (OSError, IndexError):
        accounts = [{"label": "Claude", "kind": "claude", "dir": os.environ.get("CLAUDE_CONFIG_DIR", "~/.claude")}]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(read, accounts))
    print(json.dumps({"at": int(time.time()), "accounts": results}))


if __name__ == "__main__":
    main()
