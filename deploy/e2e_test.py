#!/usr/bin/env python3
"""End-to-end test of multi-user Aura against the live HTTPS endpoint."""
import base64
import json
import urllib.request

BASE = "https://aura.34.93.196.79.sslip.io"


def post(path, body):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.loads(r.read())


def make_pdf(text: str) -> bytes:
    """Minimal valid one-page PDF with the given text (Helvetica)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" +
        stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n").encode()
    return out


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


# 1. new user logs in
r = post("/api/login", {"name": "E2E Alice"})
assert r.get("ok") and not r["existing"] and not r["has_jd"], r
alice = r["user"]
print(f"1. login new user -> slug '{alice}', fresh setup: OK")

# 2. she uploads a JD as a real PDF
jd_pdf = make_pdf("Hiring: Senior Python Backend Engineer. "
                  "Needs REST APIs, PostgreSQL, Docker, AWS.")
r = post("/api/setup/upload", {"user": alice, "kind": "jd",
                               "filename": "jd.pdf", "data_b64": b64(jd_pdf)})
assert r.get("ok") and r["has_jd"] and r["chars"] > 30, r
print(f"2. JD uploaded as PDF, {r['chars']} chars extracted: OK")

# 3. and a CV as plain text
r = post("/api/setup/upload", {"user": alice, "kind": "resume",
                               "filename": "cv.txt",
                               "data_b64": b64(b"6 years Python, Django, K8s.")})
assert r.get("ok") and r["has_resume"], r
print("3. CV uploaded: OK")

# 4. her session starts grounded in HER docs (real Codex call)
r = post("/api/start", {"user": alice})
assert r.get("reply"), r
print(f"4. session started, mentor opener: {r['reply'][:120]}…")

# 5. logging in with the same name again finds her setup
r = post("/api/login", {"name": "e2e ALICE"})
assert r["existing"] and r["has_jd"] and r["has_resume"], r
print("5. re-login with same name -> existing setup found: OK")

# 6. reconnect replays her conversation, doesn't restart it
r = post("/api/start", {"user": alice})
assert r.get("history") and len(r["history"]) >= 1, r
print(f"6. reconnect replays history ({len(r['history'])} messages): OK")

# 7. a different new user is isolated: no JD, no session, must set up
r = post("/api/login", {"name": "E2E Bob"})
assert r.get("ok") and not r["existing"] and not r["has_jd"], r
bob = r["user"]
r = post("/api/start", {"user": bob})
assert r.get("need_setup"), r
print("7. second user is isolated and asked for his own JD: OK")

print("\nALL E2E TESTS PASS")
