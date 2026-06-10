# Aura — AI Interview Mentor

A continuous, natural interview-prep conversation powered by **your ChatGPT/Codex
subscription** (no API key, no per-token billing). Aura interviews you for a
specific job, teaches gaps the moment they appear, quietly re-verifies later that
the lesson stuck, remembers you across sessions, runs live coding rounds, and
tracks your readiness score over time.

## Setup (one-time)

```bash
npm install -g @openai/codex     # or: brew install codex
codex login                      # signs in with your ChatGPT subscription
```

Paste your target job description into `job_description.md`.
Optionally drop your resume in `resume.md` (or pass `--resume resume.pdf`,
needs `pip install pypdf`).

## Run

```bash
python interview_agent.py                          # basic
python interview_agent.py --resume resume.pdf      # tailor to your resume
python interview_agent.py --voice                  # speak/hear (see below)
python interview_agent.py --fresh                  # ignore stored memory
python interview_agent.py path/to/other_jd.md      # different role
```

### In-session commands

| Command   | What it does |
|-----------|--------------|
| `debrief` | Honest readiness report: strengths, gaps, study plan, score + trend |
| `code`    | Live coding round — solve in a real file, Aura runs and reviews it |
| `voice`   | Switch to voice mode mid-session (if voice deps are installed) |
| `text`    | Switch back to typing mid-session |
| `quit`    | End session: saves your profile and a readiness report |

## Features

- **Continuous mentoring loop** — no scripted question bank; Aura adapts each turn,
  teaches in the moment, and circles back later from new angles to verify learning.
- **Persistent memory** — `.aura/profile.json` tracks every skill (strong / shaky /
  taught / untested). New sessions resume where you left off and re-verify older
  lessons (spaced repetition).
- **Coding rounds** — problems written to `.aura/workspace/`, solved in your own
  editor, executed with the agent's tests, reviewed in-conversation.
- **Resume-aware** — questions probe your actual claimed experience and flag
  resume-vs-JD gaps.
- **Readiness reports** — saved to `.aura/reports/`, with a score trend across
  sessions (e.g. `54 → 71 over 3 sessions`).
- **Never overflows context** — long sessions are automatically compacted: Aura
  writes itself a handoff note, the profile is saved, and a fresh model session
  continues mid-flow. You won't notice the seam.

## Voice mode (optional)

```bash
pip install edge-tts faster-whisper sounddevice numpy
```

Run with `--voice`: Aura's replies are spoken aloud (edge-tts) and you answer by
mic (local Whisper, push-to-talk: Enter to start/stop, transcript confirmed before
sending). You can always still type. If any dependency is missing it falls back to
text mode with a hint.

All personal data (`.aura/`, transcript, resume) is gitignored.
