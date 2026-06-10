#!/usr/bin/env python3
"""
Aura – AI Interview Mentor (powered by your Codex subscription)

A continuous, natural interview-prep conversation. Aura interviews you,
spots gaps as they appear, teaches them on the spot, and quietly re-verifies
later that the lesson stuck — like a real mentor would.

Requirements:
  - Codex CLI installed and logged in with your ChatGPT/Codex subscription:
      npm install -g @openai/codex   (or: brew install codex)
      codex login
  - A job description in job_description.md (or pass a path as an argument)

Run:
  python interview_agent.py [path/to/job_description.md]
"""

import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

JD_FILE = "job_description.md"
WIDTH = 88
SESSION_LOG = Path(".aura_session.md")  # local transcript so you can review later

MENTOR_BRIEF = """\
You are Aura, an elite interview mentor — a senior engineer who has run hundreds of
interviews and now prepares a candidate (the user) for a specific role.

THE JOB DESCRIPTION you are preparing them for:
---
{jd}
---

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

5. HONEST AND WARM. Be direct about weak answers — specifics, not platitudes. Be
   genuinely encouraging about strong ones. No corporate filler.

6. WHEN THE CANDIDATE SAYS "debrief" or asks how they're doing overall, give them
   your current mental model: strong areas, open gaps, what to study, and how ready
   they are for this interview. Then continue the session if they want.

Start now: greet them briefly (2-3 sentences), and open with a natural first question
grounded in the most important skill in the JD. Keep every turn focused and
conversational — this should feel like a great human mentor, not a test engine.
"""


# ── terminal helpers ─────────────────────────────────────────────────────────

def wrap(text: str) -> str:
    out = []
    for line in text.split("\n"):
        out.extend(textwrap.wrap(line, WIDTH) if line.strip() else [""])
    return "\n".join(out)


def say(text: str) -> None:
    print("\n" + wrap(text) + "\n")


def get_input() -> str:
    print("You ▸ (Enter twice to send, 'quit' to exit, 'debrief' for a progress check)")
    lines, blanks = [], 0
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip().lower() == "quit":
            return "quit"
        if line == "":
            blanks += 1
            if blanks >= 2 and lines:
                break
        else:
            blanks = 0
            lines.append(line)
    return "\n".join(lines).strip()


# ── Codex backend ────────────────────────────────────────────────────────────

def check_codex() -> None:
    if shutil.which("codex") is None:
        print("ERROR: Codex CLI not found.")
        print("Install it and log in with your subscription:")
        print("  npm install -g @openai/codex   (or: brew install codex)")
        print("  codex login")
        sys.exit(1)


def codex_turn(prompt: str, first: bool) -> str:
    """Send one turn to Codex. The Codex session itself holds the conversation
    history (we resume the same session every turn), so the dialogue is truly
    continuous rather than replayed."""
    base = ["codex", "exec", "--json", "--skip-git-repo-check",
            "--sandbox", "read-only"]
    cmd = base + [prompt] if first else \
        ["codex", "exec", "resume", "--last", "--json",
         "--skip-git-repo-check", "--sandbox", "read-only", prompt]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "codex exec failed")

    # codex --json emits JSONL events; the reply is the last agent_message
    reply = ""
    for line in proc.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = event.get("item") or event.get("msg") or {}
        if item.get("type") in ("agent_message", "agent_message_delta") or \
           item.get("item_type") == "agent_message":
            reply = item.get("text") or item.get("message") or reply
    if not reply:
        # fallback: non-JSON output (older codex versions print plain text)
        reply = proc.stdout.strip()
    return reply


# ── session ──────────────────────────────────────────────────────────────────

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


def log(role: str, text: str) -> None:
    with SESSION_LOG.open("a") as f:
        f.write(f"\n**{role}:**\n\n{text}\n")


def main() -> None:
    check_codex()
    jd_path = sys.argv[1] if len(sys.argv) > 1 else JD_FILE
    jd = load_jd(jd_path)

    print("═" * WIDTH)
    print("  AURA — your interview mentor  (backend: Codex)")
    print("═" * WIDTH)
    print(wrap("One continuous conversation. Aura will interview you, teach what "
               "you're missing, and quietly re-check it stuck. Say 'debrief' any "
               "time for a readiness report; 'quit' to end."))

    SESSION_LOG.write_text("# Aura session transcript\n")

    say("Connecting to your mentor…")
    reply = codex_turn(MENTOR_BRIEF.format(jd=jd), first=True)
    say(f"Aura ▸ {reply}")
    log("Aura", reply)

    while True:
        user = get_input()
        if user == "quit":
            say("Aura ▸ Ending here. Your transcript is in .aura_session.md — "
                "review the gaps we covered. You've got this.")
            break
        if not user:
            continue
        log("You", user)
        try:
            reply = codex_turn(user, first=False)
        except RuntimeError as e:
            say(f"[connection hiccup: {e}] — try sending that again.")
            continue
        say(f"Aura ▸ {reply}")
        log("Aura", reply)


if __name__ == "__main__":
    main()
