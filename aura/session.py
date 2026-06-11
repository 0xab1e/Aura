"""AuraSession — the single conversation engine shared by the CLI and the
web UI. All features (memory, compaction, rounds, flashcard harvesting,
reports) live here so every frontend behaves identically.

Each session belongs to one UserStore (login name) and owns its own
CodexThread, so any number of candidates can prep concurrently, each with
their own JD, resume, and history."""

from pathlib import Path

from . import flashcards, memory, reports, rounds
from .backend import CodexThread
from .backend import extract_json
from .context import ContextTracker, compact_session
from .users import UserStore

JD_FILE = "job_description.md"

MENTOR_BRIEF = """\
You are Aura, an elite interview mentor — a senior engineer who has run hundreds of
interviews and now prepares a candidate (the user) for a specific role.

THE JOB DESCRIPTION you are preparing them for:
---
{jd}
---
{resume_section}{memory_section}
HOW YOU OPERATE — this is one continuous, natural conversation, not a scripted quiz:

1. CONTINUOUS LEARNING LOOP. You silently maintain a mental model of the candidate:
   which skills from the JD they've demonstrated, which are shaky, which are untested.
   Every reply they give updates this model.

2. NATURAL FLOW. Never announce "Question 3 of 10" or "Evaluation:". Talk like a
   human mentor: react to what they said, follow up on interesting threads, dig
   deeper when an answer is shallow, move on when it's solid. One question or one
   teaching point at a time — never a wall of questions.

3. TEACH IN THE MOMENT. When an answer reveals a gap, don't just note it — teach it
   right there: the core intuition, a concrete example, what to say in the real
   interview. Then weave on naturally.

4. CONTINUOUS VERIFICATION. After teaching something, don't immediately quiz them on
   it. Instead, a few exchanges later, circle back from a different angle to check it
   actually stuck. If it didn't, teach it differently. Also re-probe shaky areas from
   earlier in the session.

5. SPECIAL ROUNDS. The app can switch into focused rounds — coding (hands-on, you
   review code + run output), behavioral (STAR stories), mock (realistic simulation),
   and system design. When one would be valuable, suggest it: tell the candidate to
   use the matching command/button (code, behavioral, mock, design). Mode switches
   arrive as [MODE SWITCH] system messages.

6. HONEST AND WARM. Be direct about weak answers — specifics, not platitudes. Be
   genuinely encouraging about strong ones. No corporate filler.

7. WHEN THE CANDIDATE SAYS "debrief" or asks how they're doing overall, give them
   your current mental model: strong areas, open gaps, what to study, and how ready
   they are for this interview. Then continue the session if they want.

Start now: greet them briefly (2-3 sentences), and open with a natural first question
grounded in the most important skill in the JD{memory_hint}. Keep every turn focused
and conversational — this should feel like a great human mentor, not a test engine.
"""

RESUME_SECTION = """
THE CANDIDATE'S RESUME:
---
{resume}
---
Use it: tailor questions to their claimed experience, probe specific projects and
claims on the resume (interviewers will), and flag gaps between the resume and the
JD's requirements.
"""

DEBRIEF_MSG = ("debrief — give me your current honest read: strong areas, "
               "open gaps, what to study, how ready I am.")


class SetupError(Exception):
    """The user's setup is incomplete (e.g. no JD yet) — recoverable."""


def load_jd(user: UserStore, jd_path: str | None,
            repo_fallback: bool = True) -> str:
    """The user's uploaded JD wins. An explicit path or the repo-root
    job_description.md are CLI-only fallbacks — the web UI must never leak
    one person's documents to another."""
    candidates = ([Path(jd_path)] if jd_path else
                  [user.jd_file] + ([Path(JD_FILE)] if repo_fallback else []))
    for p in candidates:
        if not p.exists():
            continue
        text = p.read_text().strip()
        if text and "Paste your target job description" not in text:
            return text
        if text:
            raise SetupError(f"{p} still contains placeholder text — "
                             "replace it with the real job description.")
    raise SetupError("No job description yet — upload one (PDF or text) "
                     "to start your prep.")


def load_resume(user: UserStore, resume_path: str | None,
                repo_fallback: bool = True) -> str:
    candidates = ([Path(resume_path)] if resume_path else
                  [user.resume_file] +
                  ([Path("resume.md")] if repo_fallback else []))
    for p in candidates:
        if not p.exists():
            if resume_path:
                print(f"WARNING: resume file {p} not found — continuing without it.")
            continue
        if p.suffix.lower() == ".pdf":
            try:
                from pypdf import PdfReader
                return "\n".join(page.extract_text() or ""
                                 for page in PdfReader(p).pages)
            except ImportError:
                print("WARNING: PDF resume needs `pip install pypdf` — "
                      "continuing without it.")
                return ""
        return p.read_text().strip()
    return ""


class AuraSession:
    """One continuous mentoring conversation with mode switches, memory,
    flashcard harvesting, and automatic context compaction."""

    def __init__(self, user: UserStore, jd_path: str | None = None,
                 resume_path: str | None = None, fresh: bool = False,
                 repo_fallback: bool = True):
        self.user = user
        user.create()
        self.thread = CodexThread()
        self.jd = load_jd(user, jd_path, repo_fallback)
        self.resume = load_resume(user, resume_path, repo_fallback)
        self.profile = ({"skills": {}, "sessions": []} if fresh
                        else memory.load_profile(user.profile_file))
        self.deck = flashcards.load_deck(user.deck_file)
        self.mode = "mentor"       # mentor | behavioral | mock | design
        self.ctx = ContextTracker()
        memory_section = memory.profile_brief(self.profile)
        self._returning = bool(memory_section)
        self._sections = dict(
            resume_section=RESUME_SECTION.format(resume=self.resume) if self.resume else "",
            memory_section=memory_section,
        )
        self.user.session_log.write_text(
            f"# Aura session transcript — {user.display_name}\n")

    # ── lifecycle ────────────────────────────────────────────────────────

    def start(self) -> str:
        brief = MENTOR_BRIEF.format(
            jd=self.jd, memory_hint=(
                " — or, since you know this candidate already, pick up where "
                "you left off and start by re-verifying something you taught "
                "last time" if self._returning else ""),
            **self._sections)
        reply = self.thread.turn(brief, first=True)
        self.ctx.add(brief, reply)
        self._log("Aura", reply)
        return reply

    def send(self, text: str) -> str:
        """One normal conversation turn (also used for debrief text)."""
        self._log("You", text)
        reply = self.thread.turn(text)
        self.ctx.add(text, reply)
        self._log("Aura", reply)
        return reply

    def maybe_compact(self) -> str | None:
        """Call after each turn. Returns the continuation reply if a compact
        happened, else None. Failures degrade to the current session."""
        if not self.ctx.needs_compact():
            return None
        try:
            self.save_progress()
            base = MENTOR_BRIEF.format(jd=self.jd, memory_hint="", **self._sections)
            cont = compact_session(base, self.thread)
            self.ctx.reset(seed_chars=len(base) + len(cont))
            if cont:
                self._log("Aura", cont)
            return cont or None
        except RuntimeError:
            return None

    def save_progress(self) -> int:
        """Persist profile + harvest flashcards. Returns # new cards."""
        memory.update_profile_from_session(self.profile, self.thread,
                                           self.user.profile_file)
        try:
            reply = self.thread.turn(flashcards.HARVEST_PROMPT)
        except RuntimeError:
            return 0
        cards = extract_json(reply)
        if isinstance(cards, list):
            return flashcards.add_cards(self.deck, cards, self.user.deck_file)
        return 0

    def debrief(self) -> tuple[str, str | None]:
        reply = self.send(DEBRIEF_MSG)
        summary = reports.generate_report(self.thread, self.user.reports_dir,
                                          self.user.scores_file)
        self.save_progress()
        return reply, summary

    def end(self) -> str | None:
        self.save_progress()
        return reports.generate_report(self.thread, self.user.reports_dir,
                                       self.user.scores_file)

    # ── rounds ───────────────────────────────────────────────────────────

    def switch_mode(self, mode: str) -> str:
        """Enter behavioral/mock/design — or back to mentor via end_round()."""
        reply = self.thread.turn(rounds.MODE_PROMPTS[mode])
        self.ctx.add(rounds.MODE_PROMPTS[mode], reply)
        self.mode = mode
        self._log("Aura", f"[{mode} round]\n{reply}")
        return reply

    def end_round(self) -> str:
        mode, self.mode = self.mode, "mentor"
        if mode == "mentor":
            return "(no round in progress)"
        prompt = rounds.END_PROMPTS[mode]
        reply = self.thread.turn(prompt)
        self.ctx.add(prompt, reply)
        if mode == "behavioral":
            rounds.save_stories(rounds.extract_stories(reply),
                                self.user.stories_file)
        self._log("Aura", f"[end {mode} round]\n{reply}")
        return reply

    # ── misc ─────────────────────────────────────────────────────────────

    def _log(self, role: str, text: str) -> None:
        with self.user.session_log.open("a") as f:
            f.write(f"\n**{role}:**\n\n{text}\n")
