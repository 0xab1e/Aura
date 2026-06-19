"""Coding rounds: the mentor sets a problem, the candidate solves it (in
their editor via the CLI, or in the web UI's code box), we run it and feed
code + output back into the conversation for review.

Split into setup / review halves so both the CLI (file + 'done') and the
web UI (textarea submit) can drive the same round. Problems live in the
user's own workspace directory."""

import subprocess
import sys
import textwrap
from pathlib import Path

from .backend import CodexThread, extract_json

RUN_TIMEOUT = 30  # seconds

PROBLEM_PROMPT = """\
[SYSTEM TASK — set up a coding round. The candidate asked for (or you decided on)
a hands-on coding exercise. Based on the job description and what you know about
the candidate so far, output JSON only:
{{
  "title": "<short slug, e.g. rate-limiter>",
  "language": "python|c",
  "statement": "<full problem statement: requirements, examples, constraints>",
  "stub": "<starter code with the function signature(s) to implement>",
  "test_code": "<test harness that imports/includes the solution and prints PASS/FAIL per case>"
}}
REQUESTED CODING FOCUS:
{topic}

If the requested focus is embedded C, firmware, registers, buffers, parsers,
ISR/task handoff, bit manipulation, or C code evaluation, use "language": "c".
For C rounds:
- stub must be valid C for solution.c, with function signatures to implement
- test_code must be a complete C file for run_tests.c
- run_tests.c should include "solution.c", call the functions, and print
  PASS/FAIL per case
For Python rounds, keep the existing solution.py pattern.
Pick difficulty appropriate to the role and the candidate's demonstrated level.
Output ONLY the JSON.]"""

REVIEW_PROMPT = """\
[SYSTEM TASK — the candidate finished the coding round "{title}".

Their solution:
```{language}
{code}
```

Run output (tests + their code):
```
{output}
```

Now, back in your natural mentor voice, review it with them: what's good, what's
wrong or missing (correctness, edge cases, complexity, style), what an interviewer
would push on. If it failed, teach the fix. Then continue the session naturally.]"""


def setup_round(thread: CodexThread, workspace: Path,
                topic: str = "") -> tuple[dict, Path] | None:
    """Ask the session for a problem; write stub + statement to a workspace dir."""
    reply = thread.turn(PROBLEM_PROMPT.format(
        topic=topic.strip() or "(no extra focus; choose a role-relevant task)"))
    data = extract_json(reply)
    if not isinstance(data, dict) or "statement" not in data:
        return None
    data["language"] = _language(data)
    workspace.mkdir(parents=True, exist_ok=True)
    n = len(list(workspace.glob("problem_*"))) + 1
    pdir = workspace / f"problem_{n}_{data.get('title', 'challenge')}"
    pdir.mkdir(parents=True, exist_ok=True)
    stub = data.get("stub", "# your solution here\n")
    solution = _solution_path(data, pdir)
    if data["language"] == "c":
        solution.write_text(f"/*\n{data['statement']}\n*/\n\n{stub}\n")
    else:
        solution.write_text(f'"""\n{data["statement"]}\n"""\n\n{stub}\n')
    (pdir / "PROBLEM.md").write_text(
        f"# {data.get('title', 'Coding round')}\n\n{data['statement']}\n")
    return data, pdir


def review_round(data: dict, pdir: Path, thread: CodexThread,
                 code: str | None = None) -> str:
    """Run the solution (+ agent tests) and get the in-conversation review.
    If `code` is given (web UI), it's written to the solution file first."""
    data["language"] = _language(data)
    solution = _solution_path(data, pdir)
    if code is not None:
        solution.write_text(code)
    code_text = solution.read_text()
    output = _run_solution(pdir, data)
    review = thread.turn(
        REVIEW_PROMPT.format(title=data.get("title", ""),
                             language=data["language"],
                             code=code_text, output=output[:4000]))
    return review


def run_coding_round(thread: CodexThread, workspace: Path) -> str | None:
    """CLI flow: solve in your own editor, type 'done'. Returns review or None."""
    setup = setup_round(thread, workspace)
    if setup is None:
        print("(couldn't set up a coding problem — continuing the conversation)")
        return None
    data, pdir = setup

    print("\n" + "─" * 60)
    print("CODING ROUND")
    print("─" * 60)
    print(textwrap.fill(data["statement"], 88))
    print(f"\nOpen this file in your editor and write your solution:\n  {_solution_path(data, pdir)}")
    cmd = input("\nType 'done' when finished (or 'skip' to bail): ").strip().lower()
    while cmd not in ("done", "skip"):
        cmd = input("Type 'done' or 'skip': ").strip().lower()
    if cmd == "skip":
        return None

    review = review_round(data, pdir, thread)
    return review


def _language(data: dict) -> str:
    lang = (data.get("language") or "python").strip().lower()
    return "c" if lang in ("c", "c11", "embedded c") else "python"


def _solution_path(data: dict, pdir: Path) -> Path:
    return pdir / ("solution.c" if _language(data) == "c" else "solution.py")


def _run_solution(pdir: Path, data: dict) -> str:
    if _language(data) == "c":
        return _run_c_solution(pdir, data.get("test_code", ""))
    return _run_python_solution(pdir, data.get("test_code", ""))


def _run_python_solution(pdir: Path, test_code: str) -> str:
    parts = []
    try:
        r = subprocess.run([sys.executable, "solution.py"], cwd=pdir,
                           capture_output=True, text=True, timeout=RUN_TIMEOUT)
        parts.append((r.stdout + r.stderr).strip() or "(no output)")
    except subprocess.TimeoutExpired:
        parts.append(f"(solution.py timed out after {RUN_TIMEOUT}s)")
    if test_code.strip():
        (pdir / "run_tests.py").write_text(test_code)
        try:
            r = subprocess.run([sys.executable, "run_tests.py"], cwd=pdir,
                               capture_output=True, text=True, timeout=RUN_TIMEOUT)
            parts.append("--- tests ---\n" + ((r.stdout + r.stderr).strip() or "(no output)"))
        except subprocess.TimeoutExpired:
            parts.append(f"(tests timed out after {RUN_TIMEOUT}s)")
    return "\n".join(parts)


def _run_c_solution(pdir: Path, test_code: str) -> str:
    if not test_code.strip():
        test_code = '#include "solution.c"\nint main(void) { return 0; }\n'
    (pdir / "run_tests.c").write_text(test_code)
    exe = pdir / ("run_tests.exe" if sys.platform.startswith("win") else "run_tests")
    try:
        r = subprocess.run(
            ["gcc", "-std=c11", "-Wall", "-Wextra", "-O0",
             "run_tests.c", "-o", str(exe)],
            cwd=pdir, capture_output=True, text=True, timeout=RUN_TIMEOUT)
    except FileNotFoundError:
        return "gcc not found; could not compile the C solution"
    except subprocess.TimeoutExpired:
        return f"(C compile timed out after {RUN_TIMEOUT}s)"
    if r.returncode != 0:
        return "--- compile failed ---\n" + (r.stdout + r.stderr).strip()
    try:
        r = subprocess.run([str(exe)], cwd=pdir, capture_output=True,
                           text=True, timeout=RUN_TIMEOUT)
        return "--- compile ok ---\n--- tests ---\n" + (
            (r.stdout + r.stderr).strip() or "(no output)")
    except subprocess.TimeoutExpired:
        return f"(C tests timed out after {RUN_TIMEOUT}s)"
