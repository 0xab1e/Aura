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
HOW THIS EPISODE RUNS:
1. Open with ONE quick probing question on this exact topic to gauge their
   level (one or two sentences of intro, no long greeting).
2. Based on each answer: teach what's missing right there, then a few turns
   later check it stuck from a new angle; if they're strong, go deeper instead.
   Alternate teaching and testing for the whole episode.
3. STAY ON THIS TOPIC. If the conversation drifts, gently pull it back.
4. Keep every turn short and conversational — one question or one teaching
   point at a time.
Start now."""

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
