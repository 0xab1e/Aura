"""Readiness reports + score trend across sessions."""

import csv
from datetime import datetime
from pathlib import Path

from .backend import codex_turn, extract_json

REPORTS_DIR = Path(".aura") / "reports"
SCORES_FILE = Path(".aura") / "scores.csv"

REPORT_PROMPT = """\
[SYSTEM TASK — generate a readiness report for the candidate. Output JSON only:
{
  "overall_score": <0-100, honest readiness for THIS role's interview>,
  "skill_scores": {"<skill>": <0-100>},
  "strengths": ["..."],
  "priority_gaps": ["<ranked, most important first, each with a one-line study tip>"],
  "study_plan": ["<day-by-day or step-by-step plan to close the gaps>"],
  "verdict": "<2-3 sentence honest bottom line>"
}
Output ONLY the JSON.]"""


def generate_report() -> str | None:
    """Ask the live session for a structured report; write it to disk.
    Returns a short printable summary, or None on failure."""
    try:
        reply = codex_turn(REPORT_PROMPT, first=False)
    except RuntimeError:
        return None
    data = extract_json(reply)
    if not isinstance(data, dict) or "overall_score" not in data:
        return None

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = REPORTS_DIR / f"report_{stamp}.md"

    lines = [f"# Readiness report — {stamp}",
             f"\n**Overall readiness: {data['overall_score']}/100**",
             f"\n> {data.get('verdict', '')}",
             "\n## Skill scores"]
    for skill, score in (data.get("skill_scores") or {}).items():
        lines.append(f"- {skill}: {score}/100")
    lines.append("\n## Strengths")
    lines += [f"- {s}" for s in data.get("strengths", [])]
    lines.append("\n## Priority gaps")
    lines += [f"{i + 1}. {g}" for i, g in enumerate(data.get("priority_gaps", []))]
    lines.append("\n## Study plan")
    lines += [f"- {s}" for s in data.get("study_plan", [])]
    path.write_text("\n".join(lines) + "\n")

    _append_score(stamp, data["overall_score"])
    trend = score_trend()
    summary = (f"Readiness: {data['overall_score']}/100. "
               f"Report saved to {path}.")
    if trend:
        summary += f" Trend: {trend}"
    return summary


def _append_score(stamp: str, score) -> None:
    new = not SCORES_FILE.exists()
    with SCORES_FILE.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "overall_score"])
        w.writerow([stamp, score])


def score_trend() -> str:
    if not SCORES_FILE.exists():
        return ""
    with SCORES_FILE.open() as f:
        rows = list(csv.DictReader(f))
    if len(rows) < 2:
        return ""
    scores = [r["overall_score"] for r in rows]
    return " → ".join(scores) + f" over {len(scores)} sessions"
