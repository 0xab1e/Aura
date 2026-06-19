"""Topic-by-topic learning — an alternative to the continuous chat.

Aura builds a personalized curriculum (chapters → episodes) from the user's
JD + resume: core technical areas, a resume deep-dive, current-job stories,
behavioral prep, system design. Each episode is a focused teach-and-test
micro-session on ONE topic, run on its own Codex thread. Finishing an
episode scores it, updates the shared skill profile, and harvests
flashcards — so the continuous mentor knows what you learned here.

Stored per user in .aura/users/<name>/curriculum.json."""

import json
from datetime import datetime, timezone
from pathlib import Path

from . import flashcards, memory
from .backend import CodexThread, extract_json
from .users import UserStore

CURRICULUM_PROMPT = """\
[SYSTEM TASK — build a personalized interview-prep curriculum.

THE JOB DESCRIPTION:
---
{jd}
---
THE CANDIDATE'S RESUME:
---
{resume}
---
{memory}
Design a complete topic-by-topic prep plan for THIS candidate and THIS role.
Cover, as separate chapters:
- the core technical skill areas the JD will test (one chapter per major area)
- a resume deep-dive chapter (the specific projects and claims on their resume
  that an interviewer will probe)
- a current/most-recent job chapter (impact stories, hard problems,
  "why are you leaving", what they'd answer about day-to-day work)
- behavioral / soft-skill prep grounded in the JD's requirements
- system design, if the role calls for it
4-8 chapters, each with 2-5 tightly-scoped episodes (one focused topic each,
about 10-20 minutes of teach + test). Order chapters by interview importance.
Output JSON only:
{{"chapters": [{{"title": "<short chapter title>",
   "why": "<one line: why this matters for this interview>",
   "episodes": [{{"title": "<short episode title>",
                  "focus": "<one line: exactly what is taught and tested>"}}]}}]}}
Output ONLY the JSON.]"""

COVERAGE_PROMPT = """\
[SYSTEM TASK - inspect and extend an existing interview-prep curriculum.

THE NEW INTERVIEW:
"{label}" on {date}{focus_line}

THE JOB DESCRIPTION:
---
{jd}
---
THE CANDIDATE'S RESUME:
---
{resume}
---
{memory}
EXISTING CURRICULUM:
{existing}

Decide whether the existing curriculum actually covers what THIS new interview
will test. Do not match by title alone. Check the requested round format,
deliverables, and evaluation style.

If the interview asks for hands-on coding, implementation tasks, live coding,
writing functions, tests, debugging code, or code evaluation, the curriculum
must include practice episodes that explicitly make the candidate write,
review, test, and explain code. Theory-only episodes, concept review, and
"code review drill" episodes are not enough.

If important coverage is missing, add the smallest set of new chapters/episodes
needed. Prefer adding a focused chapter over rewriting existing chapters.
Each episode should be a teach-and-test unit, but for coding rounds its focus
must explicitly require implementation practice and evaluation criteria.

Output JSON only:
{{"needed": true|false,
 "reason": "<one concise sentence>",
 "chapters": [{{"title": "<short chapter title>",
               "why": "<why this is missing and needed>",
               "episodes": [{{"title": "<short episode title>",
                             "focus": "<exactly what is practiced/tested>"}}]}}]}}

If nothing is missing, output {{"needed": false, "reason": "...", "chapters": []}}.
Output ONLY the JSON.]"""

EPISODE_BRIEF = """\
You are Aura, an elite interview mentor running a FOCUSED micro-lesson —
one topic only, teach + test, nothing else.

EPISODE: {episode}   (chapter: {chapter})
FOCUS: {focus}

THE JOB DESCRIPTION (context for why this topic matters):
---
{jd}
---
{resume_section}{memory}
THIS EPISODE HAS TWO MODES, and you must move between them deliberately:

QUIZ MODE — how the episode starts. Ask ONE focused question on this exact
topic to find out what they actually know (one or two sentences of intro, no
long greeting). If an answer is solid, probe deeper or move to the next
aspect, staying in quiz mode.

THE MOMENT the candidate says "I don't know", half-guesses, or gets it
materially wrong: STOP QUIZZING. Do not press on like an interviewer, do not
stack another test question on top. Switch fully into learn mode.

LEARN MODE — you are now a patient teacher, not an interviewer:
- Break the concept into small pieces. Explain the first piece simply, with
  a concrete example relevant to this role.
- After each piece, check understanding with small, low-pressure guiding
  questions ("so if X happens, what would you expect Y to do?") — never
  gotcha questions, never grading language.
- Use their answers to locate the precise gap and fill it. Build up until
  they can explain the whole idea back to you in their own words.
- When they do, say you're switching back to quiz mode, then re-test the
  SAME concept from a NEW angle to confirm it stuck, and continue the
  episode in quiz mode.

THE APP MAY ALSO SEND EXPLICIT SWITCHES — [SWITCH TO LEARN MODE] or
[SWITCH TO QUIZ MODE] — when the candidate presses a button. Obey them
immediately and without commentary about the mechanism.

ALWAYS: stay on this episode's topic (pull drifts back gently), and keep
every turn short — one question or one teaching point at a time.
Start now, in quiz mode."""

EPISODE_MODE_PROMPTS = {
    "learn": """\
[SWITCH TO LEARN MODE — the candidate pressed the Learn button: they want to
be taught this, not tested on it. Stop quizzing now. Take the current concept
(or the one they last struggled with), break it into small pieces, and teach
it step by step with concrete examples — checking along the way with gentle
guiding questions, never test questions. Start teaching now.]""",
    "quiz": """\
[SWITCH TO QUIZ MODE — the candidate pressed the Quiz button: they feel ready
to be tested. Acknowledge in a few words, then test what was just covered
from a NEW angle, one question at a time, interview-style but supportive.
If a gap reappears, switch back to learn mode as the rules say.]""",
}

RESUME_SECTION = """
THE CANDIDATE'S RESUME (probe their actual claims where relevant):
---
{resume}
---
"""

EPISODE_END_PROMPT = """\
[SYSTEM TASK — the episode is over. Output JSON only:
{"mastery": <0-100 honest score for this topic right now>,
 "verdict": "<2-3 sentences: where they stand on this topic and the single most important thing to remember>",
 "skills": {"<skill>": {"status": "strong|shaky|taught|untested", "notes": "<one line>"}},
 "flashcards": [{"front": "<question>", "back": "<concise ideal answer>", "skill": "<skill area>"}]}
skills: only what was actually probed or taught this episode.
flashcards: max 5, only concepts actually taught. Output ONLY the JSON.]"""


def curriculum_file(user: UserStore) -> Path:
    return user.dir / "curriculum.json"


def load_curriculum(user: UserStore) -> dict | None:
    f = curriculum_file(user)
    if f.exists():
        try:
            return json.loads(f.read_text())
        except json.JSONDecodeError:
            pass
    return None


def save_curriculum(user: UserStore, cur: dict) -> None:
    curriculum_file(user).write_text(json.dumps(cur, indent=2))


def _curriculum_lines(cur: dict) -> str:
    lines = []
    for ci, ch in enumerate(cur.get("chapters", [])):
        lines.append(f"ch{ci}: {ch.get('title', '')} - {ch.get('why', '')}")
        for ei, ep in enumerate(ch.get("episodes", [])):
            lines.append(
                f"  ch{ci}.ep{ei}: {ep.get('title', '')} - "
                f"{ep.get('focus', '')}")
    return "\n".join(lines) or "(no existing curriculum)"


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def ensure_interview_coverage(user: UserStore, label: str, date: str,
                              focus: str, jd: str, resume: str,
                              profile: dict, cur: dict) -> dict:
    """Append missing curriculum coverage for a newly added interview."""
    prompt = COVERAGE_PROMPT.format(
        label=label, date=date,
        focus_line=(f"\nWHAT THIS INTERVIEW FOCUSES ON: {focus}" if focus else ""),
        jd=jd, resume=resume or "(no resume provided)",
        memory=memory.profile_brief(profile),
        existing=_curriculum_lines(cur))
    reply = CodexThread().turn(prompt, first=True)
    data = extract_json(reply)
    if not isinstance(data, dict) or not data.get("needed"):
        return cur

    existing_titles = {
        _norm(ep.get("title", ""))
        for ch in cur.get("chapters", [])
        for ep in ch.get("episodes", [])
    }
    added = 0
    for ch in data.get("chapters", []):
        if not isinstance(ch, dict) or not ch.get("title"):
            continue
        episodes = []
        for ep in ch.get("episodes", []):
            if not isinstance(ep, dict) or not ep.get("title"):
                continue
            key = _norm(ep["title"])
            if not key or key in existing_titles:
                continue
            existing_titles.add(key)
            episodes.append({"title": ep["title"], "focus": ep.get("focus", ""),
                             "status": "new", "score": None, "last": None})
        if episodes:
            cur.setdefault("chapters", []).append({
                "title": ch["title"],
                "why": ch.get("why", data.get("reason", "")),
                "episodes": episodes,
            })
            added += len(episodes)
    if added:
        cur["extended"] = datetime.now(timezone.utc).isoformat()
        save_curriculum(user, cur)
    return cur


def generate_curriculum(user: UserStore, jd: str, resume: str,
                        profile: dict) -> dict:
    """One Codex call on a throwaway thread → validated, trackable plan."""
    prompt = CURRICULUM_PROMPT.format(
        jd=jd, resume=resume or "(no resume provided)",
        memory=memory.profile_brief(profile))
    reply = CodexThread().turn(prompt, first=True)
    data = extract_json(reply)
    if not isinstance(data, dict) or not isinstance(data.get("chapters"), list):
        raise RuntimeError("couldn't build the topic plan — try again")
    chapters = []
    for ch in data["chapters"]:
        if not isinstance(ch, dict) or not ch.get("title"):
            continue
        episodes = [{"title": ep["title"], "focus": ep.get("focus", ""),
                     "status": "new", "score": None, "last": None}
                    for ep in ch.get("episodes", [])
                    if isinstance(ep, dict) and ep.get("title")]
        if episodes:
            chapters.append({"title": ch["title"], "why": ch.get("why", ""),
                             "episodes": episodes})
    if not chapters:
        raise RuntimeError("couldn't build the topic plan — try again")
    cur = {"generated": datetime.now(timezone.utc).isoformat(),
           "chapters": chapters}
    save_curriculum(user, cur)
    return cur


class EpisodeSession:
    """One focused teach-and-test conversation on a single episode topic,
    isolated on its own Codex thread."""

    def __init__(self, user: UserStore, jd: str, resume: str,
                 chapter: dict, episode: dict):
        self.user = user
        self.chapter = chapter
        self.episode = episode
        self.thread = CodexThread()
        self._jd = jd
        self._resume = resume

    def start(self) -> str:
        profile = memory.load_profile(self.user.profile_file)
        brief = EPISODE_BRIEF.format(
            episode=self.episode["title"], chapter=self.chapter["title"],
            focus=self.episode.get("focus", ""), jd=self._jd,
            resume_section=(RESUME_SECTION.format(resume=self._resume)
                            if self._resume else ""),
            memory=memory.profile_brief(profile))
        return self.thread.turn(brief, first=True)

    def send(self, text: str) -> str:
        return self.thread.turn(text)

    def set_mode(self, mode: str) -> str:
        """Explicit learn/quiz switch (the user pressed the button)."""
        return self.thread.turn(EPISODE_MODE_PROMPTS[mode])

    def finish(self) -> dict:
        """Score the episode; fold skills + flashcards into the user's
        shared memory. Returns {mastery, verdict, cards_added}."""
        reply = self.thread.turn(EPISODE_END_PROMPT)
        data = extract_json(reply)
        if not isinstance(data, dict):
            data = {}
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        profile = memory.load_profile(self.user.profile_file)
        for skill, info in (data.get("skills") or {}).items():
            if isinstance(info, dict):
                profile["skills"][skill] = {
                    "status": info.get("status", "taught"),
                    "notes": info.get("notes", ""),
                    "last_checked": today,
                }
        profile["sessions"].append({
            "date": today,
            "summary": (f"Episode '{self.episode['title']}' "
                        f"({self.chapter['title']}): "
                        f"{data.get('verdict', 'completed')}")})
        memory.save_profile(profile, self.user.profile_file)

        cards_added = 0
        cards = data.get("flashcards")
        if isinstance(cards, list) and cards:
            deck = flashcards.load_deck(self.user.deck_file)
            cards_added = flashcards.add_cards(deck, cards,
                                               self.user.deck_file)
        return {"mastery": data.get("mastery"),
                "verdict": data.get("verdict", ""),
                "cards_added": cards_added}


def mark_episode(user: UserStore, ch_i: int, ep_i: int, status: str,
                 score=None) -> None:
    cur = load_curriculum(user)
    try:
        ep = cur["chapters"][ch_i]["episodes"][ep_i]
    except (TypeError, KeyError, IndexError):
        return
    ep["status"] = status
    if score is not None:
        ep["score"] = score
    ep["last"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    save_curriculum(user, cur)
