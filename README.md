# Aura — AI Interview Mentor

A continuous, natural interview-prep conversation powered by **your ChatGPT/Codex
subscription** — no API key, no per-token billing. Aura reads the job description
(and optionally your resume), interviews you like a human mentor, teaches gaps the
moment they appear, quietly re-verifies later that the lesson stuck, remembers you
across sessions, runs coding / behavioral / mock / system-design rounds, drills you
with spaced-repetition flashcards, and tracks your readiness score over time.

Works as a terminal CLI **and** as a mobile-friendly web app served from your
machine.

---

## Requirements

| What | Why | Install |
|------|-----|---------|
| Python 3.10+ | runs the agent | usually preinstalled |
| Codex CLI (logged in) | the LLM backend, via your ChatGPT subscription | `npm install -g @openai/codex` (or `brew install codex`), then `codex login` |
| Python packages | **none required** — optional extras only (CLI voice, PDF resume) | `pip install -r requirements.txt` |

## Setup

```bash
# 1. One-time backend setup
npm install -g @openai/codex      # or: brew install codex
codex login                       # signs in with your ChatGPT subscription

# 2. Clone and enter the repo, then add your target job description
#    (open job_description.md, delete the placeholder, paste the real JD)

# 3. (Optional) add your resume as resume.md — or keep a PDF and use --resume

# 4. (Optional) extras for CLI voice mode / PDF resumes
pip install -r requirements.txt
```

## Run

```bash
python interview_agent.py                          # CLI
python interview_agent.py --web                    # mobile-friendly web UI
python interview_agent.py --resume resume.pdf      # tailor to your resume
python interview_agent.py --voice                  # CLI voice mode
python interview_agent.py --fresh                  # ignore stored memory
python interview_agent.py path/to/other_jd.md      # different role
python interview_agent.py --web --port 9000        # custom web port
```

### Mobile-friendly web UI

```bash
python interview_agent.py --web        # open http://localhost:8765
```

On your phone (same wifi): `http://<your-computer-ip>:8765`
(find your IP with `ipconfig` on Windows or `ifconfig`/`ip addr` on Mac/Linux).

Responsive chat UI with command chips, a bottom-sheet code editor for coding
rounds, a flashcard review sheet, and **browser-native voice** — 🎙 dictate
answers, 🔊 hear Aura's replies — no Python audio packages needed.

### In-session commands (CLI) / chips (web)

| Command        | What it does |
|----------------|--------------|
| `review`       | Drill due flashcards (SM-2 spaced repetition, works offline) |
| `code`         | Coding round — solve in a real file/editor, Aura runs and reviews it |
| `behavioral`   | STAR-method behavioral round; polished stories saved to `.aura/stories.md` |
| `mock`         | Realistic mock interview: no hints, real pressure, full debrief at `end` |
| `design`       | System-design round with interviewer-style probing |
| `end`          | Finish the current round and return to mentoring (with debrief) |
| `debrief`      | Honest readiness report: strengths, gaps, study plan, score + trend |
| `voice`/`text` | Toggle CLI voice mode mid-session |
| `quit`         | End session: saves profile, flashcards, and a readiness report |

## Features

- **Continuous mentoring loop** — no scripted question bank; Aura adapts each turn,
  teaches in the moment, and circles back later from new angles to verify learning.
- **Persistent memory** — `.aura/profile.json` tracks every skill (strong / shaky /
  taught / untested). New sessions resume where you left off and re-verify older
  lessons.
- **Flashcards with spaced repetition** — every concept Aura teaches becomes a card
  (harvested automatically); SM-2 scheduling decides what's due each day. Fully
  offline — you can review without the backend.
- **Coding rounds** — problems written to `.aura/workspace/`, solved in your own
  editor (or the web UI's code sheet), executed with the agent's tests, reviewed
  in-conversation.
- **Behavioral, mock & design rounds** — layered onto the *same* conversation (no
  separate flows): STAR coaching, pressure simulation with withheld feedback, and
  architecture probing — `end` returns seamlessly to mentoring.
- **Resume-aware** — questions probe your actual claimed experience and flag
  resume-vs-JD gaps.
- **Readiness reports** — saved to `.aura/reports/`, with a score trend across
  sessions (e.g. `54 → 71 over 3 sessions`).
- **Never overflows context** — long sessions are automatically compacted: Aura
  writes itself a handoff note, the profile is saved, and a fresh model session
  continues mid-flow. You won't notice the seam.

## CLI voice mode (optional)

```bash
pip install -r requirements.txt     # installs edge-tts, faster-whisper, sounddevice, numpy
python interview_agent.py --voice
```

Aura's replies are spoken aloud (edge-tts) and you answer by mic (local Whisper,
push-to-talk: Enter to start/stop, transcript confirmed before sending). You can
always still type, and `voice`/`text` toggle mid-session. If any dependency is
missing it falls back to text mode with a hint. *(The web UI doesn't need any of
this — it uses the browser's built-in speech APIs.)*

## Project layout

```
interview_agent.py        # CLI entry point (also launches the web UI with --web)
job_description.md        # paste your target JD here
requirements.txt          # optional extras (core needs nothing)
aura/
  session.py              # AuraSession — the conversation engine (shared by CLI & web)
  backend.py              # Codex CLI wrapper (codex exec / resume)
  context.py              # context budget + automatic session compaction
  memory.py               # persistent skill profile across sessions
  flashcards.py           # SM-2 spaced-repetition deck
  rounds.py               # behavioral / mock / design mode prompts + story bank
  coding.py               # coding rounds: problem setup, run, review
  reports.py              # readiness reports + score trend
  voice.py                # optional CLI voice I/O
  web.py                  # stdlib HTTP server for the web UI
  static/index.html       # responsive mobile-first chat UI
```

### Your data (all local, all gitignored)

```
.aura/profile.json        # skill memory across sessions
.aura/flashcards.json     # spaced-repetition deck
.aura/stories.md          # polished STAR story bank
.aura/reports/            # readiness reports
.aura/scores.csv          # readiness score history
.aura/workspace/          # coding round problems & solutions
.aura_session.md          # transcript of the latest session
```

## Troubleshooting

- **`ERROR: Codex CLI not found`** — install it (`npm install -g @openai/codex`)
  and make sure `codex` is on your PATH, then `codex login`.
- **`job_description.md still contains placeholder text`** — open the file and
  replace the example JD with your real one.
- **Phone can't reach the web UI** — both devices must be on the same network;
  check your firewall allows the port (default 8765).
- **Voice input not working in the browser** — use Chrome or Safari;
  SpeechRecognition isn't available in all browsers.
- **Replies feel slow** — each turn is a real model call through the Codex CLI;
  this is normal. The web UI shows "Aura is thinking…" while a turn runs.
