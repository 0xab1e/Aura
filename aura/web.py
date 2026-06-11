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

from datetime import date as _date

from . import coding, curriculum, flashcards, memory, schedule
from .session import AuraSession, SetupError, load_jd, load_resume
from .users import MAX_UPLOAD_BYTES, UserStore

PROFILE_SAVE_EVERY = 6   # mentor turns between background profile saves

STATIC_DIR = Path(__file__).parent / "static"
PORT = 8765

_registry_lock = threading.Lock()
_sessions: dict[str, dict] = {}   # slug -> per-user state


def _entry(slug: str) -> dict:
    """Per-user state: the session, its lock, and the visible history."""
    with _registry_lock:
        return _sessions.setdefault(slug, {
            "session": None, "started": False, "reply0": "",
            "coding": None, "history": [], "episode": None,
            "turns": 0, "hydrated": False, "lock": threading.Lock(),
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
    _clear_live(user)
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


def _live_file(user: UserStore):
    return user.dir / "live.json"


def _save_live(user: UserStore, entry: dict) -> None:
    """Persist live conversation state (thread ids + visible history) so any
    device — and a server restart — resumes the same conversations."""
    data = {}
    s = entry.get("session")
    if s is not None and entry["started"]:
        data["mentor"] = {"thread_id": s.thread.thread_id, "mode": s.mode,
                          "history": entry["history"][-200:],
                          "turns": entry["turns"],
                          "ctx": {"chars": s.ctx.chars, "turns": s.ctx.turns}}
    ep = entry.get("episode")
    if ep is not None:
        data["episode"] = {"thread_id": ep["session"].thread.thread_id,
                           "ch": ep["ch"], "ep": ep["ep"],
                           "mode": ep.get("mode", "quiz"),
                           "history": ep.get("history", [])[-200:]}
    c = entry.get("coding")
    if c is not None:
        data["coding"] = {"data": c[0], "pdir": str(c[1])}
    try:
        _live_file(user).write_text(json.dumps(data))
    except OSError:
        pass


def _clear_live(user: UserStore) -> None:
    try:
        _live_file(user).unlink()
    except (FileNotFoundError, OSError):
        pass


def _hydrate(user: UserStore, entry: dict) -> None:
    """After a server restart, rebuild this user's live sessions from disk.
    Codex stores the actual conversations; we resume them by thread id."""
    if entry["hydrated"]:
        return
    entry["hydrated"] = True
    f = _live_file(user)
    if not f.exists():
        return
    try:
        data = json.loads(f.read_text())
    except (json.JSONDecodeError, OSError):
        return
    m = data.get("mentor")
    if m and m.get("thread_id") and entry["session"] is None:
        log_snapshot = (user.session_log.read_text()
                        if user.session_log.exists() else None)
        try:
            s = AuraSession(user, repo_fallback=False)
        except SetupError:
            s = None
        if s is not None:
            if log_snapshot is not None:   # keep the transcript mid-session
                user.session_log.write_text(log_snapshot)
            s.thread.thread_id = m["thread_id"]
            s.mode = m.get("mode", "mentor")
            ctx = m.get("ctx", {})
            s.ctx.chars = ctx.get("chars", 0)
            s.ctx.turns = ctx.get("turns", 0)
            entry["session"] = s
            entry["started"] = True
            entry["history"] = m.get("history", [])
            entry["turns"] = m.get("turns", 0)
    e = data.get("episode")
    if e and e.get("thread_id") and entry.get("episode") is None:
        cur = curriculum.load_curriculum(user)
        try:
            chapter = cur["chapters"][e["ch"]]
            episode = chapter["episodes"][e["ep"]]
            jd, resume = _user_docs(user)
        except (TypeError, KeyError, IndexError, SetupError):
            return
        es = curriculum.EpisodeSession(user, jd, resume, chapter, episode)
        es.thread.thread_id = e["thread_id"]
        entry["episode"] = {"session": es, "ch": e["ch"], "ep": e["ep"],
                            "mode": e.get("mode", "quiz"),
                            "history": e.get("history", [])}
    c = data.get("coding")
    if c and entry.get("coding") is None and Path(c.get("pdir", "")).exists():
        entry["coding"] = (c["data"], Path(c["pdir"]))


def _handle_session_api(path: str, body: dict, user: UserStore,
                        entry: dict) -> dict:
    _hydrate(user, entry)

    if path == "/api/start":
        if entry["session"] is None:
            try:
                entry["session"] = AuraSession(user, repo_fallback=False)
            except SetupError as e:
                return {"error": str(e), "need_setup": True}
        s = entry["session"]
        if not entry["started"]:
            entry["reply0"] = s.start()
            entry["started"] = True
            _remember(entry, "ai", entry["reply0"])
            _save_live(user, entry)
            return {"reply": entry["reply0"], "mode": s.mode,
                    "due": len(flashcards.due_cards(s.deck)),
                    "user": user.slug, "display_name": user.display_name}
        # reconnect (page reload): replay the conversation so far
        return {"history": entry["history"], "mode": s.mode,
                "due": len(flashcards.due_cards(s.deck)),
                "user": user.slug, "display_name": user.display_name}

    if path.startswith("/api/learn/"):
        return _handle_learn(path, body, user, entry)

    if path.startswith("/api/interviews") or path == "/api/schedule/check":
        return _handle_interviews(path, body, user)

    # ── session-independent: dashboard status + flashcard review ────────
    if path == "/api/status":
        deck = flashcards.load_deck(user.deck_file)
        cur = curriculum.load_curriculum(user)
        plan = None
        if cur:
            eps = [e for c in cur["chapters"] for e in c["episodes"]]
            plan = {"total": len(eps),
                    "done": sum(1 for e in eps if e["status"] == "done")}
        live_ep = entry.get("episode")
        live_code = entry.get("coding")
        s = entry.get("session")
        return {"has_jd": user.has_jd, "has_resume": user.has_resume,
                "due": len(flashcards.due_cards(deck)),
                "started": entry["started"], "plan": plan,
                "mode": s.mode if s else "mentor",
                "episode_live": live_ep is not None,
                "episode": ({"chapter": live_ep["ch"], "episode": live_ep["ep"],
                             "title": live_ep["session"].episode["title"]}
                            if live_ep else None),
                "coding": (live_code[0].get("title", "Coding round")
                           if live_code else None),
                "display_name": user.display_name,
                "interviews": [{"id": i["id"], "label": i["label"],
                                "date": i["date"]}
                               for i in schedule.load_interviews(user)]}

    if path == "/api/review/next":
        deck = flashcards.load_deck(user.deck_file)
        due = flashcards.due_cards(deck)
        if not due:
            return {"done": True, "total": len(deck)}
        c = due[0]
        return {"done": False, "front": c["front"], "back": c["back"],
                "skill": c.get("skill", ""), "remaining": len(due)}

    if path == "/api/review/grade":
        deck = flashcards.load_deck(user.deck_file)
        due = flashcards.due_cards(deck)
        if due:
            quality = int(body.get("quality", 3))
            card = due[0]
            flashcards.grade_card(deck, card, quality, user.deck_file)
            _grade_to_profile(user, card.get("skill", ""), quality)
        return {"ok": True}

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
        # keep the shared skill profile fresh so episodes, schedules, and
        # flashcards see what the chat just taught — not only at quit time
        entry["turns"] += 1
        if entry["turns"] % PROFILE_SAVE_EVERY == 0:
            threading.Thread(target=_checkpoint_profile, args=(entry,),
                             daemon=True).start()
        _save_live(user, entry)
        return {"reply": reply, "extra": [cont] if cont else [], "mode": s.mode}

    if path == "/api/command":
        cmd = body.get("cmd", "")
        if cmd == "debrief":
            reply, summary = s.debrief()
            _remember(entry, "ai", reply)
            _save_live(user, entry)
            return {"reply": reply, "extra": [summary] if summary else [], "mode": s.mode}
        if cmd in ("behavioral", "mock", "design"):
            reply = s.switch_mode(cmd)
            _remember(entry, "ai", reply)
            _save_live(user, entry)
            return {"reply": reply, "extra": [], "mode": s.mode}
        if cmd == "end":
            reply = s.end_round()
            _remember(entry, "ai", reply)
            _save_live(user, entry)
            return {"reply": reply, "extra": [], "mode": s.mode}
        if cmd == "quit":
            summary = s.end()
            _reset_entry(user.slug)
            _clear_live(user)
            return {"reply": "Session saved. See you next time — you've got this.",
                    "extra": [summary] if summary else [], "mode": s.mode}
        return {"error": f"unknown command {cmd}"}

    if path == "/api/code/start":
        setup = coding.setup_round(s.thread, user.workspace_dir)
        if setup is None:
            return {"error": "couldn't set up a coding problem — try again"}
        data, pdir = setup
        entry["coding"] = (data, pdir)
        _save_live(user, entry)
        return {"title": data.get("title", ""), "statement": data["statement"],
                "stub": data.get("stub", "")}

    if path == "/api/code/current":
        if not entry["coding"]:
            return {"pending": False}
        data, pdir = entry["coding"]
        solution = pdir / "solution.py"
        return {"pending": True, "title": data.get("title", ""),
                "statement": data["statement"],
                "code": solution.read_text() if solution.exists() else
                        data.get("stub", "")}

    if path == "/api/code/save":
        if not entry["coding"]:
            return {"error": "no coding round in progress"}
        _, pdir = entry["coding"]
        (pdir / "solution.py").write_text(body.get("code", ""))
        return {"ok": True}

    if path == "/api/code/submit":
        if not entry["coding"]:
            return {"error": "no coding round in progress"}
        data, pdir = entry["coding"]
        review = coding.review_round(data, pdir, s.thread,
                                     code=body.get("code", ""))
        entry["coding"] = None
        _remember(entry, "ai", review)
        _save_live(user, entry)
        return {"reply": review, "mode": s.mode}

    return {"error": "not found"}


def _grade_to_profile(user: UserStore, skill: str, quality: int) -> None:
    """Flashcard self-ratings feed the shared skill profile: a blank on a
    card marks its skill shaky everywhere; an easy recall marks it strong."""
    if not skill or quality == 3:   # 3 = hard-but-recalled, no signal shift
        return
    profile = memory.load_profile(user.profile_file)
    prev = profile["skills"].get(skill, {})
    profile["skills"][skill] = {
        "status": "shaky" if quality < 3 else "strong",
        "notes": (prev.get("notes") or "").split(" | flashcard")[0] +
                 f" | flashcard recall {'failed' if quality < 3 else 'easy'}",
        "last_checked": _date.today().isoformat(),
    }
    memory.save_profile(profile, user.profile_file)


def _today(body: dict) -> str:
    t = body.get("today", "")
    return t if isinstance(t, str) and len(t) == 10 else _date.today().isoformat()


def _handle_interviews(path: str, body: dict, user: UserStore) -> dict:
    """Interview registry + per-interview day-by-day sub-schedules."""
    if path == "/api/interviews":
        return {"interviews": schedule.load_interviews(user)}

    if path == "/api/interviews/add":
        label = (body.get("label") or "").strip() or "Interview"
        date = (body.get("date") or "").strip()
        focus = (body.get("focus") or "").strip()
        today = _today(body)
        if not date or len(date) != 10 or date <= today:
            return {"error": "pick an interview date that's in the future"}
        try:
            jd, resume = _user_docs(user)
        except SetupError as e:
            return {"error": str(e), "need_setup": True}
        cur = curriculum.load_curriculum(user)
        if cur is None:   # the schedule plans around episodes, so build them
            profile = memory.load_profile(user.profile_file)
            try:
                cur = curriculum.generate_curriculum(user, jd, resume, profile)
            except RuntimeError as e:
                return {"error": str(e)}
        try:
            iv = schedule.add_interview(user, label, date, focus, today,
                                        jd, resume, cur)
        except RuntimeError as e:
            return {"error": str(e)}
        return {"ok": True, "interview": iv}

    if path == "/api/interviews/delete":
        schedule.delete_interview(user, body.get("id", ""))
        return {"ok": True}

    if path == "/api/interviews/redo":
        try:
            jd, resume = _user_docs(user)
        except SetupError as e:
            return {"error": str(e), "need_setup": True}
        cur = curriculum.load_curriculum(user)
        if cur is None:
            return {"error": "no study plan yet — add the interview again"}
        try:
            iv = schedule.regenerate(user, body.get("id", ""), _today(body),
                                     jd, resume, cur)
        except RuntimeError as e:
            return {"error": str(e)}
        if iv is None:
            return {"error": "unknown interview"}
        return {"ok": True, "interview": iv}

    if path == "/api/schedule/check":
        ok = schedule.check_item(user, body.get("id", ""),
                                 body.get("date", ""),
                                 int(body.get("index", -1)),
                                 bool(body.get("done", True)))
        return {"ok": ok}

    return {"error": "not found"}


def _checkpoint_profile(entry: dict) -> None:
    """Background save of the mentor session's skill map (one model call)."""
    with entry["lock"]:
        s = entry.get("session")
        if s is None:
            return
        try:
            memory.update_profile_from_session(s.profile, s.thread,
                                               s.user.profile_file)
        except Exception:
            pass


def _user_docs(user: UserStore) -> tuple[str, str]:
    """The user's own JD/resume only — never the repo-root fallbacks."""
    jd = load_jd(user, None, repo_fallback=False)
    resume = load_resume(user, None, repo_fallback=False)
    return jd, resume


def _handle_learn(path: str, body: dict, user: UserStore,
                  entry: dict) -> dict:
    """Topic-by-topic mode. Independent of the continuous chat session —
    episodes run on their own Codex threads but share the user's skill
    profile and flashcard deck."""
    if path == "/api/learn/plan":
        cur = None if body.get("regenerate") else curriculum.load_curriculum(user)
        if cur is None and (body.get("build") or body.get("regenerate")):
            try:
                jd, resume = _user_docs(user)
            except SetupError as e:
                return {"error": str(e), "need_setup": True}
            profile = memory.load_profile(user.profile_file)
            try:
                cur = curriculum.generate_curriculum(user, jd, resume, profile)
            except RuntimeError as e:
                return {"error": str(e)}
        return {"plan": cur}   # plan may be null -> client offers to build it

    if path == "/api/learn/start":
        try:
            ch_i, ep_i = int(body.get("chapter")), int(body.get("episode"))
        except (TypeError, ValueError):
            return {"error": "bad episode reference"}
        live = entry.get("episode")
        # same lesson already in progress (other device / page reload):
        # resume the SAME conversation, don't start a parallel one
        if live and live["ch"] == ch_i and live["ep"] == ep_i:
            return {"resumed": True, "history": live.get("history", []),
                    "mode": live.get("mode", "quiz"),
                    "chapter": live["session"].chapter["title"],
                    "episode": live["session"].episode["title"]}
        # a different lesson is live: make the user decide, don't silently
        # abandon it
        if live and not body.get("force"):
            return {"need_force": True,
                    "live_title": live["session"].episode["title"]}
        cur = curriculum.load_curriculum(user)
        if cur is None or ch_i < 0 or ep_i < 0:
            return {"error": "no topic plan yet — open Topics first"}
        try:
            chapter = cur["chapters"][ch_i]
            episode = chapter["episodes"][ep_i]
        except (KeyError, IndexError):
            return {"error": "unknown episode — refresh the topic list"}
        try:
            jd, resume = _user_docs(user)
        except SetupError as e:
            return {"error": str(e), "need_setup": True}
        es = curriculum.EpisodeSession(user, jd, resume, chapter, episode)
        reply = es.start()
        entry["episode"] = {"session": es, "ch": ch_i, "ep": ep_i,
                            "mode": "quiz",
                            "history": [{"role": "ai", "text": reply}]}
        curriculum.mark_episode(user, ch_i, ep_i, "in_progress")
        _save_live(user, entry)
        return {"reply": reply, "chapter": chapter["title"],
                "episode": episode["title"]}

    ep = entry.get("episode")
    if not ep:
        return {"error": "no episode in progress — pick a topic first"}

    if path == "/api/learn/message":
        text = body.get("text", "")
        reply = ep["session"].send(text)
        ep["history"].append({"role": "me", "text": text})
        ep["history"].append({"role": "ai", "text": reply})
        _save_live(user, entry)
        return {"reply": reply}

    if path == "/api/learn/mode":
        mode = body.get("mode", "")
        if mode not in ("learn", "quiz"):
            return {"error": "mode must be learn or quiz"}
        reply = ep["session"].set_mode(mode)
        ep["mode"] = mode
        marker = ("— 🎓 learn mode: Aura teaches, no test questions —"
                  if mode == "learn" else
                  "— 🎯 quiz mode: Aura tests what you've learned —")
        ep["history"].append({"role": "sys", "text": marker})
        ep["history"].append({"role": "ai", "text": reply})
        _save_live(user, entry)
        return {"reply": reply, "mode": mode, "marker": marker}

    if path == "/api/learn/finish":
        result = ep["session"].finish()
        curriculum.mark_episode(user, ep["ch"], ep["ep"], "done",
                                result.get("mastery"))
        entry["episode"] = None
        _save_live(user, entry)
        return result

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
