"""Mobile-friendly web UI — a thin HTTP layer over AuraSession. Stdlib only
(no Flask). Voice on the web/mobile uses the browser's built-in speech APIs,
so no Python audio deps are needed.

Multi-user: you log in with a name. An existing name opens that person's
setup (their JD, resume, memory, flashcards, live conversation); a new name
creates a fresh one. Every API call after login carries the user slug, and
each user gets their own AuraSession + lock, so sessions run in parallel
without touching each other.

Run:  python interview_agent.py --web   then open http://localhost:8765
"""

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import coding, flashcards
from .session import AuraSession, SetupError
from .users import MAX_UPLOAD_BYTES, UserStore

STATIC_DIR = Path(__file__).parent / "static"
PORT = 8765

_registry_lock = threading.Lock()
_sessions: dict[str, dict] = {}   # slug -> per-user state


def _entry(slug: str) -> dict:
    """Per-user state: the session, its lock, and the visible history."""
    with _registry_lock:
        return _sessions.setdefault(slug, {
            "session": None, "started": False, "reply0": "",
            "coding": None, "history": [], "lock": threading.Lock(),
        })


def _reset_entry(slug: str) -> None:
    with _registry_lock:
        _sessions.pop(slug, None)


def _remember(entry: dict, role: str, text: str) -> None:
    if text:
        entry["history"].append({"role": role, "text": text})


def _login(body: dict) -> dict:
    name = (body.get("name") or "").strip()
    try:
        user = UserStore(name)
    except ValueError as e:
        return {"error": str(e)}
    existing = user.exists
    user.create()
    return {"ok": True, "user": user.slug, "display_name": user.display_name,
            "existing": existing, "has_jd": user.has_jd,
            "has_resume": user.has_resume}


def _upload(user: UserStore, body: dict) -> dict:
    kind = body.get("kind", "")
    filename = body.get("filename", "")
    try:
        data = base64.b64decode(body.get("data_b64", ""), validate=True)
    except Exception:
        return {"error": "bad upload encoding"}
    try:
        chars = user.save_document(kind, filename, data)
    except (RuntimeError, ValueError) as e:
        return {"error": str(e)}
    # New documents change the brief — drop any live session so the next
    # start is grounded in them. Memory/flashcards persist on disk.
    _reset_entry(user.slug)
    label = "Job description" if kind == "jd" else "Resume"
    return {"ok": True, "kind": kind, "chars": chars,
            "has_jd": user.has_jd, "has_resume": user.has_resume,
            "note": f"{label} saved ({chars} chars extracted)."}


def handle_api(path: str, body: dict) -> dict:
    if path == "/api/login":
        return _login(body)

    try:
        user = UserStore(body.get("user") or "")
    except ValueError:
        return {"error": "not logged in", "need_login": True}
    if not user.exists:
        return {"error": "unknown user — log in again", "need_login": True}

    if path == "/api/setup/upload":
        return _upload(user, body)

    entry = _entry(user.slug)
    with entry["lock"]:   # one model call at a time per user
        return _handle_session_api(path, body, user, entry)


def _handle_session_api(path: str, body: dict, user: UserStore,
                        entry: dict) -> dict:
    if path == "/api/start":
        if entry["session"] is None:
            try:
                entry["session"] = AuraSession(user)
            except SetupError as e:
                return {"error": str(e), "need_setup": True}
        s = entry["session"]
        if not entry["started"]:
            entry["reply0"] = s.start()
            entry["started"] = True
            _remember(entry, "ai", entry["reply0"])
            return {"reply": entry["reply0"], "mode": s.mode,
                    "due": len(flashcards.due_cards(s.deck)),
                    "user": user.slug, "display_name": user.display_name}
        # reconnect (page reload): replay the conversation so far
        return {"history": entry["history"], "mode": s.mode,
                "due": len(flashcards.due_cards(s.deck)),
                "user": user.slug, "display_name": user.display_name}

    s = entry["session"]
    if s is None or not entry["started"]:
        return {"error": "session not started — reload the page",
                "need_setup": not user.has_jd}

    if path == "/api/message":
        text = body.get("text", "")
        _remember(entry, "me", text)
        reply = s.send(text)
        _remember(entry, "ai", reply)
        cont = s.maybe_compact()
        if cont:
            _remember(entry, "ai", cont)
        return {"reply": reply, "extra": [cont] if cont else [], "mode": s.mode}

    if path == "/api/command":
        cmd = body.get("cmd", "")
        if cmd == "debrief":
            reply, summary = s.debrief()
            _remember(entry, "ai", reply)
            return {"reply": reply, "extra": [summary] if summary else [], "mode": s.mode}
        if cmd in ("behavioral", "mock", "design"):
            reply = s.switch_mode(cmd)
            _remember(entry, "ai", reply)
            return {"reply": reply, "extra": [], "mode": s.mode}
        if cmd == "end":
            reply = s.end_round()
            _remember(entry, "ai", reply)
            return {"reply": reply, "extra": [], "mode": s.mode}
        if cmd == "quit":
            summary = s.end()
            _reset_entry(user.slug)
            return {"reply": "Session saved. See you next time — you've got this.",
                    "extra": [summary] if summary else [], "mode": s.mode}
        return {"error": f"unknown command {cmd}"}

    if path == "/api/code/start":
        setup = coding.setup_round(s.thread, user.workspace_dir)
        if setup is None:
            return {"error": "couldn't set up a coding problem — try again"}
        data, pdir = setup
        entry["coding"] = (data, pdir)
        return {"title": data.get("title", ""), "statement": data["statement"],
                "stub": data.get("stub", "")}

    if path == "/api/code/submit":
        if not entry["coding"]:
            return {"error": "no coding round in progress"}
        data, pdir = entry["coding"]
        review = coding.review_round(data, pdir, s.thread,
                                     code=body.get("code", ""))
        entry["coding"] = None
        _remember(entry, "ai", review)
        return {"reply": review, "mode": s.mode}

    if path == "/api/review/next":
        due = flashcards.due_cards(s.deck)
        if not due:
            return {"done": True}
        c = due[0]
        return {"done": False, "front": c["front"], "back": c["back"],
                "skill": c.get("skill", ""), "remaining": len(due)}

    if path == "/api/review/grade":
        due = flashcards.due_cards(s.deck)
        if due:
            flashcards.grade_card(s.deck, due[0], int(body.get("quality", 3)),
                                  user.deck_file)
        return {"ok": True}

    return {"error": "not found"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet
        pass

    def _send(self, code: int, content: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html = (STATIC_DIR / "index.html").read_bytes()
            self._send(200, html, "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if not self.path.startswith("/api/"):
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_UPLOAD_BYTES * 2:   # b64 inflation headroom
            self._send(200, json.dumps(
                {"error": "request too large"}).encode(), "application/json")
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            body = {}
        try:
            result = handle_api(self.path, body)
        except Exception as e:  # surface backend errors to the UI
            result = {"error": str(e)}
        self._send(200, json.dumps(result).encode(), "application/json")


def serve(port: int = PORT) -> None:
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"\nAura web UI running:  http://localhost:{port}")
    print("Each person logs in with their name and uploads their own JD/CV.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down…")
