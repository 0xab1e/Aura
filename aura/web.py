"""Mobile-friendly web UI — a thin HTTP layer over the same AuraSession the
CLI uses. Stdlib only (no Flask). Voice on the web/mobile uses the browser's
built-in speech APIs, so no Python audio deps are needed.

Run:  python interview_agent.py --web   then open http://localhost:8765
(on your phone: http://<your-computer-ip>:8765 on the same wifi)
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import flashcards
from .session import AuraSession

STATIC_DIR = Path(__file__).parent / "static"
PORT = 8765

_lock = threading.Lock()
_state: dict = {"session": None, "started": False, "coding": None}


def _session() -> AuraSession:
    return _state["session"]


def handle_api(path: str, body: dict) -> dict:
    s = _session()
    if path == "/api/start":
        if not _state["started"]:
            _state["reply0"] = s.start()
            _state["started"] = True
        return {"reply": _state["reply0"], "mode": s.mode,
                "due": len(flashcards.due_cards(s.deck))}

    if path == "/api/message":
        reply = s.send(body.get("text", ""))
        cont = s.maybe_compact()
        return {"reply": reply, "extra": [cont] if cont else [], "mode": s.mode}

    if path == "/api/command":
        cmd = body.get("cmd", "")
        if cmd == "debrief":
            reply, summary = s.debrief()
            return {"reply": reply, "extra": [summary] if summary else [], "mode": s.mode}
        if cmd in ("behavioral", "mock", "design"):
            return {"reply": s.switch_mode(cmd), "extra": [], "mode": s.mode}
        if cmd == "end":
            return {"reply": s.end_round(), "extra": [], "mode": s.mode}
        if cmd == "quit":
            summary = s.end()
            return {"reply": "Session saved. See you next time — you've got this.",
                    "extra": [summary] if summary else [], "mode": s.mode}
        return {"error": f"unknown command {cmd}"}

    if path == "/api/code/start":
        from . import coding
        setup = coding.setup_round()
        if setup is None:
            return {"error": "couldn't set up a coding problem — try again"}
        data, pdir = setup
        _state["coding"] = (data, pdir)
        return {"title": data.get("title", ""), "statement": data["statement"],
                "stub": data.get("stub", "")}

    if path == "/api/code/submit":
        from . import coding
        if not _state["coding"]:
            return {"error": "no coding round in progress"}
        data, pdir = _state["coding"]
        review = coding.review_round(data, pdir, code=body.get("code", ""))
        _state["coding"] = None
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
            flashcards.grade_card(s.deck, due[0], int(body.get("quality", 3)))
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
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            body = {}
        try:
            with _lock:  # one model call at a time; session is single-user
                result = handle_api(self.path, body)
        except Exception as e:  # surface backend errors to the UI
            result = {"error": str(e)}
        self._send(200, json.dumps(result).encode(), "application/json")


def serve(jd_path: str, resume_path: str | None, fresh: bool,
          port: int = PORT) -> None:
    _state["session"] = AuraSession(jd_path, resume_path, fresh)
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"\nAura web UI running:  http://localhost:{port}")
    print("On your phone (same wifi): http://<this-computer's-ip>:%d\n" % port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSaving session before exit…")
        if _state["started"]:
            _session().end()
