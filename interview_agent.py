#!/usr/bin/env python3
"""
Aura – AI Interview Mentor (powered by your Codex subscription)

One continuous, natural conversation: Aura interviews you, teaches gaps the
moment they appear, and circles back later to verify the lesson stuck. It
remembers you across sessions, harvests flashcards from every lesson, runs
coding / behavioral / mock / system-design rounds, and tracks readiness.

Run:
  python interview_agent.py [jd.md] [--voice] [--resume resume.pdf] [--fresh]
  python interview_agent.py --web      # mobile-friendly UI at localhost:8765

In-session commands:
  review | code | behavioral | mock | design | end | debrief | voice | text | quit
"""

import argparse
import sys
import textwrap

from aura import flashcards
from aura.backend import check_codex
from aura.coding import run_coding_round
from aura.session import AuraSession, SetupError
from aura.users import UserStore

WIDTH = 88
COMMANDS = ("quit", "debrief", "code", "voice", "text",
            "review", "behavioral", "mock", "design", "end")


# ── terminal helpers ─────────────────────────────────────────────────────────

def wrap(text: str) -> str:
    out = []
    for line in text.split("\n"):
        out.extend(textwrap.wrap(line, WIDTH) if line.strip() else [""])
    return "\n".join(out)


def say(text: str, voice: bool = False) -> None:
    print("\n" + wrap(text) + "\n")
    if voice:
        from aura.voice import speak
        speak(text)


def get_input(voice: bool = False) -> str:
    if voice:
        from aura.voice import listen
        print("You ▸ (voice mode — Enter to speak, 't' + Enter to type | "
              "commands work too)")
        first = input().strip()
        if first.lower() in COMMANDS:
            return first.lower()
        if first.lower() != "t" and first != "":
            return first  # they typed an answer directly
        if first.lower() != "t":
            transcript = listen()
            if transcript:
                print(f'  heard: "{transcript}"')
                replace = input("  Send this? (Enter = yes / type to replace): ").strip()
                return replace if replace else transcript
            print("  (heard nothing — type your answer instead)")
        # fall through to typed input
    print("You ▸ (Enter twice to send | review, code, behavioral, mock, design, "
          "end, debrief, voice, text, quit)")
    lines, blanks = [], 0
    while True:
        try:
            line = input()
        except EOFError:
            break
        stripped = line.strip().lower()
        if stripped in COMMANDS and not lines:
            return stripped
        if line == "":
            blanks += 1
            if blanks >= 2 and lines:
                break
        else:
            blanks = 0
            lines.append(line)
    return "\n".join(lines).strip()


def review_cards(s: AuraSession) -> None:
    deck = s.deck
    due = flashcards.due_cards(deck)
    if not due:
        print(wrap("No flashcards due — come back after your next lesson."))
        return
    print(wrap(f"{len(due)} card(s) due. Grades: 0=blank, 3=hard, 4=good, 5=easy, q=stop."))
    for card in list(due):
        print("\n" + "─" * 40)
        if card.get("skill"):
            print(f"[{card['skill']}]")
        print(wrap("Q: " + card["front"]))
        input("(think, then press Enter to reveal) ")
        print(wrap("A: " + card["back"]))
        g = input("grade 0/3/4/5 (q to stop): ").strip().lower()
        if g == "q":
            break
        flashcards.grade_card(deck, card, int(g) if g in "0123455" and g else 3,
                              s.user.deck_file)
    print(wrap("Review saved."))


# ── main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Aura – AI interview mentor")
    parser.add_argument("jd", nargs="?", default=None,
                        help="job description file (default: your uploaded JD, "
                             "then job_description.md)")
    parser.add_argument("--user", default="default",
                        help="login name — each name has its own JD, resume, and memory")
    parser.add_argument("--voice", action="store_true", help="speak answers / hear questions")
    parser.add_argument("--resume", help="resume file (md/txt/pdf); defaults to your uploaded resume, then resume.md")
    parser.add_argument("--fresh", action="store_true", help="ignore stored memory this session")
    parser.add_argument("--web", action="store_true", help="serve the mobile-friendly web UI")
    parser.add_argument("--port", type=int, default=8765, help="web UI port")
    args = parser.parse_args()

    check_codex()

    if args.web:
        from aura.web import serve
        serve(args.port)
        return

    voice = False
    if args.voice:
        from aura.voice import voice_available
        voice, hint = voice_available()
        if not voice:
            print(hint)

    try:
        store = UserStore(args.user)
        s = AuraSession(store, args.jd, args.resume, args.fresh)
    except (ValueError, SetupError) as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print("═" * WIDTH)
    print("  AURA — your interview mentor  (backend: Codex)")
    print("═" * WIDTH)
    print(wrap("Rounds: 'code', 'behavioral', 'mock', 'design' ('end' to finish one). "
               "Also: 'review' (flashcards), 'debrief', 'voice'/'text', 'quit'."))

    due = flashcards.due_cards(s.deck)
    if due:
        print(wrap(f"\n🃏 {len(due)} flashcard(s) due from previous sessions — a quick "
                   "review locks in what you learned. Type 'review' any time."))

    say("Connecting to your mentor…")
    say(f"Aura ▸ {s.start()}", voice)

    while True:
        user = get_input(voice)
        if not user:
            continue

        if user == "quit":
            print(wrap("Saving your profile, flashcards, and readiness report…"))
            summary = s.end()
            if summary:
                print("\n" + wrap(summary))
            print("\n" + wrap(f"Transcript: {s.user.session_log} — see you next "
                              "session. You've got this."))
            break

        if user == "voice":
            from aura.voice import voice_available
            ok, hint = voice_available()
            voice = ok
            print(wrap("Voice mode ON." if ok else hint))
            continue
        if user == "text":
            voice = False
            print(wrap("Text mode ON."))
            continue

        if user == "review":
            review_cards(s)
            continue

        if user == "code":
            review = run_coding_round(s.thread, s.user.workspace_dir)
            if review:
                s.ctx.add("", review)
                say(f"Aura ▸ {review}", voice)
            continue

        if user in ("behavioral", "mock", "design"):
            say(f"Aura ▸ {s.switch_mode(user)}", voice)
            continue
        if user == "end":
            say(f"Aura ▸ {s.end_round()}", voice)
            continue

        try:
            if user == "debrief":
                reply, summary = s.debrief()
                say(f"Aura ▸ {reply}", voice)
                if summary:
                    print(wrap(summary))
            else:
                say(f"Aura ▸ {s.send(user)}", voice)
        except RuntimeError as e:
            say(f"[connection hiccup: {e}] — try sending that again.")
            continue

        cont = s.maybe_compact()
        if cont:
            say(f"Aura ▸ {cont}", voice)


if __name__ == "__main__":
    main()
