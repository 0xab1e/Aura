#!/usr/bin/env python3
"""Run AFTER restarting the aura service: verifies live conversations
survive a server restart (hydrated from live.json + Codex thread ids)."""
import json
import urllib.request

BASE = "https://aura.34.93.196.79.sslip.io"


def post(path, body):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.loads(r.read())


r = post("/api/status", {"user": "e2e-alice"})
assert r["started"] is True, f"mentor session not hydrated: {r}"
r = post("/api/start", {"user": "e2e-alice"})
assert r.get("history"), f"no history replayed after restart: {r}"
print(f"RESTART RESUME OK — mentor history replayed "
      f"({len(r['history'])} messages) after service restart")
