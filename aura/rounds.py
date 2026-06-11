"""Round modes layered on the SAME live conversation: behavioral (STAR),
mock interview (pressure, no teaching), and system design. Each mode is a
prompt injection into the running session, so context, memory, and flow
are unaffected — 'end' returns to normal mentoring."""

from pathlib import Path

MODE_PROMPTS = {
    "behavioral": """\
[MODE SWITCH — behavioral round. Until told the round is over, act as a
behavioral interviewer for this role. Ask "tell me about a time..." questions
grounded in the candidate's resume and the JD's soft requirements. After each
answer: briefly score its STAR structure (Situation, Task, Action, Result —
what was present, what was missing), help them tighten the story into a
strong version, then ask the next one. One question at a time. Stay warm but
honest. Acknowledge the switch in one short line and ask the first question.]""",

    "mock": """\
[MODE SWITCH — full mock interview simulation. Until told the round is over,
you are a REAL interviewer for this role, not a mentor: do NOT teach, do NOT
give hints or feedback, do NOT reveal whether answers were good. Be
professionally neutral. Ask follow-ups that apply realistic pressure, probe
vague claims, interrupt rambling answers by moving on. Keep your turns short
like a real interviewer. Open the way a real interview opens (brief intro,
first question). Save ALL evaluation for the debrief when the round ends.]""",

    "design": """\
[MODE SWITCH — system design round. Until told the round is over, run a
design interview appropriate to this role. Give one design prompt, then probe
like a real interviewer: requirements clarification, scaling, data model,
failure modes, trade-offs, "what if traffic grows 10x". One probe at a time;
let the candidate drive the design. When they're clearly stuck, give a small
nudge, not the answer. Acknowledge the switch briefly and give the prompt.]""",
}

END_PROMPTS = {
    "behavioral": """\
[MODE SWITCH — the behavioral round is over; return to normal mentoring.
First give honest feedback on their stories and STAR structure overall.
Then output the candidate's best stories, polished into strong STAR form,
inside a fenced block exactly like:
```stories
### <story title>
**S/T:** ...
**A:** ...
**R:** ...
```
Then continue the session naturally.]""",

    "mock": """\
[MODE SWITCH — the mock interview is over; return to mentor mode. Now give
the full debrief you withheld: how they actually did, answer by answer —
what a real interviewer would have scored well, what would have raised flags,
hire/no-hire signal and why. Be specific and honest. Teach the biggest gap
revealed, then continue the session naturally.]""",

    "design": """\
[MODE SWITCH — the design round is over; return to mentor mode. Debrief the
design: what was solid, what a real interviewer would have pushed back on,
the trade-offs they missed. Teach the most important missing concept, then
continue the session naturally.]""",
}


def extract_stories(reply: str) -> str:
    """Pull the ```stories fenced block out of a behavioral-round debrief."""
    if "```stories" not in reply:
        return ""
    return reply.split("```stories", 1)[1].split("```", 1)[0].strip()


def save_stories(stories: str, stories_file: Path) -> None:
    if not stories:
        return
    stories_file.parent.mkdir(parents=True, exist_ok=True)
    with stories_file.open("a") as f:
        f.write("\n" + stories + "\n")
