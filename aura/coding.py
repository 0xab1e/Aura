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
{
  "title": "<short slug, e.g. rate-limiter>",
  "language": "python",
  "statement": "<full problem statement: requirements, examples, constraints>",
  "stub": "<starter code with the function signature(s) to implement>",
  "test_code": "<python code that imports/exercises the solution and prints PASS/FAIL per case; assume it runs in the same directory as solution.py>"
}
Pick difficulty appropriate to the role and the candidate's demonstrated level.
Output ONLY the JSON.]"""

REVIEW_PROMPT = """\
[SYSTEM TASK — the candidate finished the coding round "{title}".

Their solution:
```python
{code}
```

Run output (tests + their code):
```
{output}
```

Now, back in your natural mentor voice, review it with them: what's good, what's
wrong or missing (correctness, edge cases, complexity, style), what an interviewer
would push on. If it failed, teach the fix. Then continue the session naturally.]"""


def setup_round(thread: CodexThread,
                workspace: Path) -> tuple[dict, Path] | None:
    """Ask the session for a problem; write stub + statement to a workspace dir."""
    reply = thread.turn(PROBLEM_PROMPT)
    data = extract_json(reply)
    if not isinstance(data, dict) or "statement" not in data:
        return None
    workspace.mkdir(parents=True, exist_ok=True)
    n = len(list(workspace.glob("problem_*"))) + 1
    pdir = workspace / f"problem_{n}_{data.get('title', 'challenge')}"
    pdir.mkdir(parents=True, exist_ok=True)
    stub = data.get("stub", "# your solution here\n")
    (pdir / "solution.py").write_text(f'"""\n{data["statement"]}\n"""\n\n{stub}\n')
    (pdir / "PROBLEM.md").write_text(
        f"# {data.get('title', 'Coding round')}\n\n{data['statement']}\n")
    return data, pdir


def review_round(data: dict, pdir: Path, thread: CodexThread,
                 code: str | None = None) -> str:
    """Run the solution (+ agent tests) and get the in-conversation review.
    If `code` is given (web UI), it's written to solution.py first."""
    solution = pdir / "solution.py"
    if code is not None:
        solution.write_text(code)
    code_text = solution.read_text()
    output = _run_solution(pdir, data.get("test_code", ""))
    review = thread.turn(
        REVIEW_PROMPT.format(title=data.get("title", ""),
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
    print(f"\nOpen this file in your editor and write your solution:\n  {pdir / 'solution.py'}")
    cmd = input("\nType 'done' when finished (or 'skip' to bail): ").strip().lower()
    while cmd not in ("done", "skip"):
        cmd = input("Type 'done' or 'skip': ").strip().lower()
    if cmd == "skip":
        return None

    review = review_round(data, pdir, thread)
    return review


def _run_solution(pdir: Path, test_code: str) -> str:
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
