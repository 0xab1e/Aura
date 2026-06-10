"""Persistent candidate profile — Aura's memory across sessions.

Stored in .aura/profile.json:
{
  "skills": {"<skill>": {"status": "strong|shaky|taught|untested",
                          "last_checked": "ISO date", "notes": "..."}},
  "sessions": [{"date": "...", "summary": "..."}]
}
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from .backend import codex_turn, extract_json

AURA_DIR = Path(".aura")
PROFILE_FILE = AURA_DIR / "profile.json"

PROFILE_UPDATE_PROMPT = """\
[SYSTEM TASK — not part of the interview; the candidate will not see this.]
Summarize your current mental model of the candidate as JSON only, no prose:
{
  "skills": {"<skill name>": {"status": "strong|shaky|taught|untested", "notes": "<one line>"}},
  "session_summary": "<2-3 sentence summary of this session: what was covered, taught, and still open>"
}
Include every skill you probed or taught this session. Output ONLY the JSON."""


def load_profile() -> dict:
    if PROFILE_FILE.exists():
        try:
            return json.loads(PROFILE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return {"skills": {}, "sessions": []}


def save_profile(profile: dict) -> None:
    AURA_DIR.mkdir(exist_ok=True)
    PROFILE_FILE.write_text(json.dumps(profile, indent=2))


def profile_brief(profile: dict) -> str:
    """Render the stored profile as a section for the mentor brief."""
    if not profile["skills"] and not profile["sessions"]:
        return ""
    lines = ["\nWHAT YOU ALREADY KNOW ABOUT THIS CANDIDATE (from previous sessions):"]
    for skill, info in profile["skills"].items():
        lines.append(f"- {skill}: {info.get('status', '?')}"
                     f" (last checked {info.get('last_checked', 'unknown')})"
                     f" — {info.get('notes', '')}")
    for s in profile["sessions"][-3:]:
        lines.append(f"- Session {s['date']}: {s['summary']}")
    lines.append(
        "\nUSE THIS MEMORY: resume where you left off. Early in this session, "
        "re-verify items marked 'taught' or 'shaky' from a NEW angle (spaced "
        "repetition) — if something was taught more than a day ago, check it "
        "stuck. Don't repeat questions the candidate already answered strongly; "
        "go deeper or move to untested skills instead.")
    return "\n".join(lines) + "\n"


def update_profile_from_session(profile: dict) -> dict:
    """Ask the live Codex session for its skill map and merge it in."""
    try:
        reply = codex_turn(PROFILE_UPDATE_PROMPT, first=False)
    except RuntimeError:
        return profile
    data = extract_json(reply)
    if not isinstance(data, dict):
        return profile
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for skill, info in (data.get("skills") or {}).items():
        if not isinstance(info, dict):
            continue
        profile["skills"][skill] = {
            "status": info.get("status", "untested"),
            "notes": info.get("notes", ""),
            "last_checked": today,
        }
    if data.get("session_summary"):
        profile["sessions"].append(
            {"date": today, "summary": data["session_summary"]})
    save_profile(profile)
    return profile
