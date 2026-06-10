#!/usr/bin/env python3
"""
Aura – AI Interview Mentor (powered by your Codex subscription)

One continuous, natural conversation: Aura interviews you, teaches gaps the
moment they appear, and circles back later to verify the lesson stuck. It
remembers you across sessions, can run live coding rounds, tailor itself to
your resume, and track your readiness score over time.

Run:
  python interview_agent.py [path/to/jd.md] [--voice] [--resume resume.pdf] [--fresh]

In-session commands:  debrief  |  code  |  quit
"""

import argparse
import sys
import textwrap
from pathlib import Path

from aura.backend import check_codex, codex_turn
from aura import memory, reports
from aura.coding import run_coding_round

JD_FILE = "job_description.md"
WIDTH = 88
SESSION_LOG = Path(".aura_session.md")

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

5. CODING ROUNDS. The CLI can run hands-on coding rounds: the candidate solves a
   problem in a real file and you review the code and its run output. When you think
   a coding exercise would be valuable (the role is technical and they've warmed up),
   suggest it — tell them to type 'code' to start one. You'll receive system tasks
   to set the problem and review the result.

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


# ── terminal helpers ─────────────────────────────────────────────────────────

def wrap(text: str) -> str:
    out = []
    for line in text.split("\n"):
        out.extend(textwrap.wrap(line, WIDTH) if line.strip() else [""])
    return "\n".join(out)


def say(text: str, voice: bool = False) -> str:
    print("\n" + wrap(text) + "\n")
    if voice:
        from aura.voice import speak
        speak(text)
    return text


def get_input(voice: bool = False) -> str:
    if voice:
        from aura.voice import listen
        print("You ▸ (voice mode — or type 't' + Enter to type this answer,"
              " 'debrief'/'code'/'quit' also work)")
        first = input().strip()
        if first.lower() in ("debrief", "code", "quit"):
            return first.lower()
        if first.lower() != "t" and first != "":
            return first  # they typed an answer directly
        if first.lower() != "t":
            transcript = listen()
            if transcript:
                print(f'  heard: "{transcript}"')
                if input("  Send this? (Enter = yes / type to replace): ").strip() == "":
                    return transcript
        # fall through to typed input
    print("You ▸ (Enter twice to send | 'debrief' = progress check | 'code' = coding round | 'quit')")
    lines, blanks = [], 0
    while True:
        try:
            line = input()
        except EOFError:
            break
        stripped = line.strip().lower()
        if stripped in ("quit", "debrief", "code") and not lines:
            return stripped
        if line == "":
            blanks += 1
            if blanks >= 2 and lines:
                break
        else:
            blanks = 0
            lines.append(line)
    return "\n".join(lines).strip()


# ── inputs ───────────────────────────────────────────────────────────────────

def load_jd(path: str) -> str:
    p = Path(path)
    if not p.exists():
        print(f"ERROR: {path} not found. Put your job description there and rerun.")
        sys.exit(1)
    text = p.read_text().strip()
    if not text or "Paste your target job description" in text:
        print("ERROR: job_description.md still contains placeholder text — paste your real JD.")
        sys.exit(1)
    return text


def load_resume(path: str | None) -> str:
    if path is None:
        default = Path("resume.md")
        if not default.exists():
            return ""
        path = str(default)
    p = Path(path)
    if not p.exists():
        print(f"WARNING: resume file {path} not found — continuing without it.")
        return ""
    if p.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
            return "\n".join(page.extract_text() or "" for page in PdfReader(p).pages)
        except ImportError:
            print("WARNING: PDF resume needs `pip install pypdf` — continuing without it.")
            return ""
    return p.read_text().strip()


def log(role: str, text: str) -> None:
    with SESSION_LOG.open("a") as f:
        f.write(f"\n**{role}:**\n\n{text}\n")


# ── session ──────────────────────────────────────────────────────────────────

def end_of_session(profile: dict) -> None:
    print(wrap("Saving your profile and generating a readiness report…"))
    memory.update_profile_from_session(profile)
    summary = reports.generate_report()
    if summary:
        print("\n" + wrap(summary))
    print("\n" + wrap("Transcript: .aura_session.md — see you next session. You've got this."))


def main() -> None:
    parser = argparse.ArgumentParser(description="Aura – AI interview mentor")
    parser.add_argument("jd", nargs="?", default=JD_FILE, help="job description file")
    parser.add_argument("--voice", action="store_true", help="speak answers / hear questions")
    parser.add_argument("--resume", help="resume file (md/txt/pdf); defaults to resume.md if present")
    parser.add_argument("--fresh", action="store_true", help="ignore stored memory this session")
    args = parser.parse_args()

    check_codex()
    jd = load_jd(args.jd)
    resume = load_resume(args.resume)

    voice = False
    if args.voice:
        from aura.voice import voice_available
        voice, hint = voice_available()
        if not voice:
            print(hint)

    profile = {"skills": {}, "sessions": []} if args.fresh else memory.load_profile()
    memory_section = memory.profile_brief(profile)
    returning = bool(memory_section)

    print("═" * WIDTH)
    print("  AURA — your interview mentor  (backend: Codex)")
    print("═" * WIDTH)
    print(wrap("Commands any time: 'debrief' (readiness report), 'code' (coding round), 'quit'."))

    SESSION_LOG.write_text("# Aura session transcript\n")

    brief = MENTOR_BRIEF.format(
        jd=jd,
        resume_section=RESUME_SECTION.format(resume=resume) if resume else "",
        memory_section=memory_section,
        memory_hint=(" — or, since you know this candidate already, pick up where "
                     "you left off and start by re-verifying something you taught "
                     "last time" if returning else ""),
    )

    say("Connecting to your mentor…")
    reply = codex_turn(brief, first=True)
    say(f"Aura ▸ {reply}", voice)
    log("Aura", reply)

    while True:
        user = get_input(voice)
        if not user:
            continue

        if user == "quit":
            end_of_session(profile)
            break

        if user == "code":
            review = run_coding_round()
            if review:
                say(f"Aura ▸ {review}", voice)
                log("Aura", f"[coding round review]\n{review}")
            continue

        log("You", user)
        if user == "debrief":
            user = ("debrief — give me your current honest read: strong areas, "
                    "open gaps, what to study, how ready I am.")

        try:
            reply = codex_turn(user, first=False)
        except RuntimeError as e:
            say(f"[connection hiccup: {e}] — try sending that again.")
            continue
        say(f"Aura ▸ {reply}", voice)
        log("Aura", reply)

        if user.startswith("debrief"):
            summary = reports.generate_report()
            if summary:
                print(wrap(summary))
            memory.update_profile_from_session(profile)


if __name__ == "__main__":
    main()
