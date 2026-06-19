"""Interview-date–driven study schedules.

The user registers one or more interviews (label + date + optional focus,
e.g. "phone screen — DSA heavy" or "onsite system design"). For each one,
Aura generates a day-by-day sub-schedule from today to the interview:
which episodes to take (prioritizing what the shared skill profile says
the candidate does NOT yet know), when to drill flashcards, and when to
run mock/behavioral/design rounds. Episode items link back to the
curriculum, so finishing a lesson anywhere ticks it off everywhere.

Stored per user in .aura/users/<name>/interviews.json."""

import json
import re
import time
from pathlib import Path

from . import memory
from .backend import CodexThread, extract_json
from .users import UserStore

SCHEDULE_PROMPT = """\
[SYSTEM TASK — build a day-by-day interview study schedule.

TODAY'S DATE: {today}
THE INTERVIEW: "{label}" on {date}{focus_line}

THE JOB DESCRIPTION:
---
{jd}
---
THE CANDIDATE'S RESUME:
---
{resume}
---
{memory}
AVAILABLE STUDY EPISODES (reference them by their exact id):
{episodes}

Create a daily plan covering every date from {today} through {last_day}
(the day before the interview), tailored to what THIS interview will test.
Rules:
- PRIORITIZE GAPS: schedule episodes for skills the candidate is shaky on,
  untested on, or scored low on. Skip or de-prioritize what they're already
  strong at — at most a light refresher near the end.
- Respect the interview's focus when given; pull in the episodes most
  relevant to it first.
- Each day: 2-4 items, roughly 60-90 minutes total. Item types:
    "episode"    — one of the episode ids above (the main learning unit)
    "coding"     — a hands-on coding exercise in the app; use this when the
                   interview includes implementation tasks or code evaluation
    "flashcards" — review due cards (5-10 min, most days)
    "mock" | "behavioral" | "design" — practice rounds; put a full mock in
                   the last 2-3 days, behavioral/design where relevant
    "chat"       — a free mentor conversation on a stated theme
- The final day before the interview: light review and confidence building
  only — no new heavy topics.
- If the runway is short, cut low-priority topics rather than cramming.
Output JSON only:
{{"days": [{{"date": "YYYY-MM-DD", "theme": "<one line for the day>",
   "items": [{{"type": "episode", "ref": "ch0.ep1", "title": "<title>",
               "why": "<one line: why this, for this interview>"}},
              {{"type": "flashcards", "title": "Review due cards",
               "why": "<one line>"}}]}}]}}
Use ONLY dates in the range. Output ONLY the JSON.]"""


def interviews_file(user: UserStore) -> Path:
    return user.dir / "interviews.json"


def load_interviews(user: UserStore) -> list[dict]:
    f = interviews_file(user)
    if f.exists():
        try:
            return json.loads(f.read_text()).get("interviews", [])
        except json.JSONDecodeError:
            pass
    return []


def save_interviews(user: UserStore, interviews: list[dict]) -> None:
    interviews_file(user).write_text(
        json.dumps({"interviews": interviews}, indent=2))


def _episode_lines(curriculum: dict) -> str:
    lines = []
    for ci, ch in enumerate(curriculum["chapters"]):
        for ei, ep in enumerate(ch["episodes"]):
            state = ep["status"]
            if ep.get("score") is not None:
                state += f" {ep['score']}/100"
            lines.append(f"ch{ci}.ep{ei} [{state}] {ch['title']} — "
                         f"{ep['title']}: {ep.get('focus', '')}")
    return "\n".join(lines)


def _valid_ref(ref: str, curriculum: dict) -> bool:
    m = re.fullmatch(r"ch(\d+)\.ep(\d+)", ref or "")
    if not m:
        return False
    ci, ei = int(m.group(1)), int(m.group(2))
    try:
        curriculum["chapters"][ci]["episodes"][ei]
        return True
    except (IndexError, KeyError):
        return False


def generate_schedule(user: UserStore, label: str, date: str, focus: str,
                      today: str, jd: str, resume: str,
                      curriculum: dict) -> list[dict]:
    """One Codex call on a throwaway thread → validated day list."""
    from datetime import date as d, timedelta
    last_day = (d.fromisoformat(date) - timedelta(days=1)).isoformat()
    if last_day < today:
        last_day = today
    profile = memory.load_profile(user.profile_file)
    prompt = SCHEDULE_PROMPT.format(
        today=today, label=label, date=date,
        focus_line=(f"\nWHAT THIS INTERVIEW FOCUSES ON: {focus}" if focus else ""),
        jd=jd, resume=resume or "(no resume provided)",
        memory=memory.profile_brief(profile),
        episodes=_episode_lines(curriculum), last_day=last_day)
    reply = CodexThread().turn(prompt, first=True)
    data = extract_json(reply)
    if not isinstance(data, dict) or not isinstance(data.get("days"), list):
        raise RuntimeError("couldn't build the schedule — try again")
    days = []
    for day in data["days"]:
        if not isinstance(day, dict) or not day.get("date"):
            continue
        if not (today <= day["date"] <= last_day):
            continue
        items = []
        for it in day.get("items", []):
            if not isinstance(it, dict) or not it.get("type"):
                continue
            if it["type"] == "episode" and not _valid_ref(it.get("ref"), curriculum):
                continue
            items.append({"type": it["type"], "ref": it.get("ref"),
                          "title": it.get("title", it["type"]),
                          "why": it.get("why", ""), "done": False})
        if items:
            days.append({"date": day["date"],
                         "theme": day.get("theme", ""), "items": items})
    if not days:
        raise RuntimeError("couldn't build the schedule — try again")
    days.sort(key=lambda x: x["date"])
    return days


def add_interview(user: UserStore, label: str, date: str, focus: str,
                  today: str, jd: str, resume: str,
                  curriculum: dict) -> dict:
    interviews = load_interviews(user)
    interview = {"id": f"iv{int(time.time() * 1000)}",
                 "label": label, "date": date, "focus": focus,
                 "schedule": generate_schedule(user, label, date, focus,
                                               today, jd, resume, curriculum)}
    interviews.append(interview)
    interviews.sort(key=lambda i: i["date"])
    save_interviews(user, interviews)
    return interview


def delete_interview(user: UserStore, iv_id: str) -> None:
    interviews = [i for i in load_interviews(user) if i["id"] != iv_id]
    save_interviews(user, interviews)


def regenerate(user: UserStore, iv_id: str, today: str, jd: str,
               resume: str, curriculum: dict) -> dict | None:
    interviews = load_interviews(user)
    for iv in interviews:
        if iv["id"] == iv_id:
            iv["schedule"] = generate_schedule(
                user, iv["label"], iv["date"], iv.get("focus", ""),
                today, jd, resume, curriculum)
            save_interviews(user, interviews)
            return iv
    return None


def check_item(user: UserStore, iv_id: str, date: str, index: int,
               done: bool) -> bool:
    interviews = load_interviews(user)
    for iv in interviews:
        if iv["id"] != iv_id:
            continue
        for day in iv["schedule"]:
            if day["date"] == date and 0 <= index < len(day["items"]):
                day["items"][index]["done"] = done
                save_interviews(user, interviews)
                return True
    return False
