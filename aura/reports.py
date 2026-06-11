"""Readiness reports + score trend across sessions, per user."""

import csv
from datetime import datetime
from pathlib import Path

from .backend import CodexThread, extract_json

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


def generate_report(thread: CodexThread, reports_dir: Path,
                    scores_file: Path) -> str | None:
    """Ask the live session for a structured report; write it to disk.
    Returns a short printable summary, or None on failure."""
    try:
        reply = thread.turn(REPORT_PROMPT)
    except RuntimeError:
        return None
    data = extract_json(reply)
    if not isinstance(data, dict) or "overall_score" not in data:
        return None

    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = reports_dir / f"report_{stamp}.md"

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

    _append_score(stamp, data["overall_score"], scores_file)
    trend = score_trend(scores_file)
    summary = (f"Readiness: {data['overall_score']}/100. "
               f"Report saved to {path}.")
    if trend:
        summary += f" Trend: {trend}"
    return summary


def _append_score(stamp: str, score, scores_file: Path) -> None:
    new = not scores_file.exists()
    scores_file.parent.mkdir(parents=True, exist_ok=True)
    with scores_file.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "overall_score"])
        w.writerow([stamp, score])


def score_trend(scores_file: Path) -> str:
    if not scores_file.exists():
        return ""
    with scores_file.open() as f:
        rows = list(csv.DictReader(f))
    if len(rows) < 2:
        return ""
    scores = [r["overall_score"] for r in rows]
    return " → ".join(scores) + f" over {len(scores)} sessions"
