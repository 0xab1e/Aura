#!/usr/bin/env python3
"""
Aura – AI Interview Prep Agent
Run: python interview_agent.py [path/to/job_description.md]
"""

import sys
import os
import json
import textwrap
from pathlib import Path
import anthropic

# ── Config ─────────────────────────────────────────────────────────────────
MODEL = "claude-opus-4-8"
JD_FILE = "job_description.md"
WIDTH = 88  # terminal wrap width

client = anthropic.Anthropic()

# ── Helpers ─────────────────────────────────────────────────────────────────

def wrap(text: str, indent: str = "") -> str:
    lines = text.split("\n")
    wrapped = []
    for line in lines:
        if line.strip() == "":
            wrapped.append("")
        else:
            wrapped.extend(
                textwrap.wrap(line, width=WIDTH - len(indent),
                              initial_indent=indent, subsequent_indent=indent)
            )
    return "\n".join(wrapped)


def print_divider(char: str = "─", label: str = "") -> None:
    if label:
        side = (WIDTH - len(label) - 2) // 2
        print(f"\n{char * side} {label} {char * (WIDTH - side - len(label) - 2)}\n")
    else:
        print(f"\n{char * WIDTH}\n")


def stream_response(messages: list, system: str) -> str:
    """Stream a response and return the full text."""
    full_text = ""
    print()
    with client.messages.stream(
        model=MODEL,
        max_tokens=4096,
        system=system,
        messages=messages,
        thinking={"type": "enabled", "budget_tokens": 8000},
    ) as stream:
        for event in stream:
            if hasattr(event, "type"):
                if event.type == "content_block_start":
                    pass
                elif event.type == "content_block_delta":
                    delta = event.delta
                    if hasattr(delta, "text"):
                        print(delta.text, end="", flush=True)
                        full_text += delta.text
    print()
    return full_text


def get_input(prompt: str) -> str:
    print(f"\n{prompt}")
    print("(Type your answer. Press Enter twice when done, or type 'quit' to exit)\n")
    lines = []
    blank_count = 0
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.lower() == "quit":
            print("\nExiting interview session. Good luck! 🎯\n")
            sys.exit(0)
        if line == "":
            blank_count += 1
            if blank_count >= 2:
                break
            lines.append(line)
        else:
            blank_count = 0
            lines.append(line)
    # strip trailing blank lines
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


# ── System prompts ───────────────────────────────────────────────────────────

SYSTEM_PLANNER = """\
You are an expert technical recruiter and senior engineer with 15+ years of experience
conducting and preparing candidates for interviews at top tech companies.

Your task: Given a job description, design a structured interview prep plan.

Output a JSON object with:
{
  "role_summary": "one-sentence summary of the role",
  "core_skills": ["skill1", "skill2", ...],   // 5-8 key skills to test
  "question_bank": [
    {
      "id": 1,
      "skill": "skill name",
      "question": "the interview question",
      "difficulty": "easy|medium|hard",
      "key_points": ["point1", "point2", ...]  // 3-5 things a good answer covers
    },
    ...  // 8-12 questions total, mix of difficulty
  ]
}

Output ONLY valid JSON. No markdown, no explanation."""


SYSTEM_INTERVIEWER = """\
You are Aura, a warm but rigorous AI interview coach and technical mentor.

You conduct mock interviews, evaluate answers honestly, identify gaps in knowledge,
and teach those gaps in a clear, engaging way — like a senior engineer mentoring
a friend.

Tone: conversational, encouraging, direct. No corporate speak.
When teaching: use analogies, examples, step-by-step explanations.
When evaluating: be specific — point to exactly what was missing or wrong."""


# ── Core agent logic ─────────────────────────────────────────────────────────

def load_job_description(path: str) -> str:
    p = Path(path)
    if not p.exists():
        print(f"[ERROR] File not found: {path}")
        sys.exit(1)
    text = p.read_text().strip()
    if not text or "Paste your target job description" in text:
        print("[ERROR] job_description.md contains only placeholder text.")
        print("Please paste your actual job description into job_description.md and run again.")
        sys.exit(1)
    return text


def build_interview_plan(jd: str) -> dict:
    print_divider("═", "Analyzing Job Description")
    print(wrap("Reading the JD and building your personalized interview plan…"))

    messages = [{"role": "user", "content": f"Job Description:\n\n{jd}"}]
    raw = ""
    with client.messages.stream(
        model=MODEL,
        max_tokens=2048,
        system=SYSTEM_PLANNER,
        messages=messages,
        thinking={"type": "enabled", "budget_tokens": 4000},
    ) as stream:
        for event in stream:
            if (hasattr(event, "type") and event.type == "content_block_delta"
                    and hasattr(event.delta, "text")):
                raw += event.delta.text

    # extract JSON — sometimes the model wraps it in ```
    raw = raw.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:])
    if raw.endswith("```"):
        raw = "\n".join(raw.split("\n")[:-1])
    return json.loads(raw.strip())


def evaluate_answer(
    question_obj: dict,
    user_answer: str,
    conversation: list,
    jd_summary: str,
) -> tuple[str, list[str]]:
    """Return (feedback_text, gaps_list)."""

    eval_prompt = f"""\
The candidate just answered this interview question:

**Question:** {question_obj['question']}
**Skill being tested:** {question_obj['skill']}
**Difficulty:** {question_obj['difficulty']}
**Key points a strong answer should cover:** {json.dumps(question_obj['key_points'])}

**Candidate's answer:**
{user_answer}

Evaluate the answer. Structure your response in three parts:

### What you got right
(Be specific and genuine — don't just say "good job")

### What was missing or could be stronger
(Be direct and specific. List the exact concepts, details, or depth that were absent.)

### Knowledge gaps to address
(A JSON array on its own line at the end, like: GAPS: ["gap1", "gap2"])
If the answer was complete and strong, output: GAPS: []

Keep the evaluation concise but substantive."""

    conversation.append({"role": "user", "content": eval_prompt})
    feedback = stream_response(conversation, SYSTEM_INTERVIEWER)
    conversation.append({"role": "assistant", "content": feedback})

    # parse gaps from the GAPS: [...] line
    gaps: list[str] = []
    for line in feedback.split("\n"):
        line = line.strip()
        if line.startswith("GAPS:"):
            try:
                gaps = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                pass
            break

    return feedback, gaps


def teach_gap(gap: str, context: str, conversation: list) -> None:
    teach_prompt = f"""\
The candidate has a gap in: **{gap}**

Context (role they're preparing for): {context}

Teach this concept now. Be the best teacher they've ever had:
- Start with the core intuition / why it matters
- Build up with a clear explanation
- Use a concrete example or analogy
- End with 1-2 key takeaways they should remember for the interview

Then ask them a quick follow-up question to check understanding."""

    conversation.append({"role": "user", "content": teach_prompt})
    lesson = stream_response(conversation, SYSTEM_INTERVIEWER)
    conversation.append({"role": "assistant", "content": lesson})

    # Get their follow-up answer
    answer = get_input("Your answer to the follow-up:")
    if answer.strip():
        followup_prompt = f"The candidate answered the follow-up: {answer}\n\nGive brief feedback (2-3 sentences max), then confirm whether the concept is now clear."
        conversation.append({"role": "user", "content": followup_prompt})
        reply = stream_response(conversation, SYSTEM_INTERVIEWER)
        conversation.append({"role": "assistant", "content": reply})


def final_debrief(results: list, plan: dict, conversation: list) -> None:
    print_divider("═", "Interview Debrief")

    summary_data = []
    for r in results:
        summary_data.append({
            "question": r["question"]["question"],
            "skill": r["question"]["skill"],
            "gaps": r["gaps"],
            "answered": bool(r["answer"].strip()),
        })

    debrief_prompt = f"""\
The mock interview is complete. Here's what happened:

{json.dumps(summary_data, indent=2)}

Give a comprehensive debrief:

## Overall Assessment
(Honest 2-3 sentence summary of where they stand)

## Strongest Areas
(What they demonstrated well)

## Priority Gaps to Fix Before the Interview
(Ranked by importance. For each gap, give a specific resource or study strategy)

## 7-Day Study Plan
(A day-by-day plan to close the key gaps and be ready for this interview)

## Final Encouragement
(Something genuine and motivating)"""

    conversation.append({"role": "user", "content": debrief_prompt})
    debrief = stream_response(conversation, SYSTEM_INTERVIEWER)
    conversation.append({"role": "assistant", "content": debrief})


# ── Main session loop ─────────────────────────────────────────────────────────

def run_session(jd_path: str) -> None:
    print_divider("═", "AURA – AI Interview Prep Agent")
    print(wrap("Welcome! I'm Aura, your personal interview coach."))
    print(wrap("I'll run a mock interview, evaluate your answers, teach you what you're missing,"))
    print(wrap("and build you a study plan. Let's get you ready.\n"))

    jd = load_job_description(jd_path)
    plan = build_interview_plan(jd)

    role_summary = plan.get("role_summary", "the target role")
    core_skills = plan.get("core_skills", [])
    questions = plan.get("question_bank", [])

    print_divider()
    print(wrap(f"Role: {role_summary}"))
    print(wrap(f"Core skills I'll test: {', '.join(core_skills)}"))
    print(wrap(f"Questions in this session: {len(questions)}"))
    print()
    input("Press Enter to start the mock interview…")

    conversation: list = []
    results: list = []

    # Opening message from Aura
    conversation.append({
        "role": "user",
        "content": f"Start the mock interview for this role: {role_summary}. Greet the candidate and ask the first question: {questions[0]['question']}",
    })
    opening = stream_response(conversation, SYSTEM_INTERVIEWER)
    conversation.append({"role": "assistant", "content": opening})

    for i, q_obj in enumerate(questions):
        print_divider("─", f"Question {i + 1} of {len(questions)}")

        if i == 0:
            # question was already asked in opening
            answer = get_input("Your answer:")
        else:
            # ask the next question naturally
            transition_prompt = f"Transition naturally to the next question and ask it: {q_obj['question']}"
            conversation.append({"role": "user", "content": transition_prompt})
            q_text = stream_response(conversation, SYSTEM_INTERVIEWER)
            conversation.append({"role": "assistant", "content": q_text})
            answer = get_input("Your answer:")

        print_divider("─", "Evaluation")
        feedback, gaps = evaluate_answer(q_obj, answer, conversation, role_summary)
        results.append({"question": q_obj, "answer": answer, "gaps": gaps})

        if gaps:
            print_divider("─", "Closing the Gaps")
            print(wrap(f"I found {len(gaps)} gap(s) to address: {', '.join(gaps)}"))
            for gap in gaps:
                print_divider("·" * 1, f"Teaching: {gap}")
                teach_gap(gap, role_summary, conversation)

        if i < len(questions) - 1:
            cont = input("\nReady for the next question? (Enter / 'skip' to end early): ").strip().lower()
            if cont == "skip":
                break

    final_debrief(results, plan, conversation)
    print_divider("═")
    print(wrap("Session complete. Good luck with your interview! 💪"))
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    jd_path = sys.argv[1] if len(sys.argv) > 1 else JD_FILE
    run_session(jd_path)
