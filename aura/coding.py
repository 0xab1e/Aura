"""Coding rounds: the mentor sets a problem, the candidate solves it in a
real file in their own editor, we run it and feed code + output back into
the conversation for review."""

import subprocess
import sys
import textwrap
from pathlib import Path

from .backend import codex_turn, extract_json

WORKSPACE = Path(".aura") / "workspace"
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


def run_coding_round() -> str | None:
    """Run one full coding round. Returns the mentor's review text, or None if aborted."""
    reply = codex_turn(PROBLEM_PROMPT, first=False)
    data = extract_json(reply)
    if not isinstance(data, dict) or "statement" not in data:
        print("(couldn't set up a coding problem — continuing the conversation)")
        return None

    n = len(list(WORKSPACE.glob("problem_*"))) + 1
    pdir = WORKSPACE / f"problem_{n}_{data.get('title', 'challenge')}"
    pdir.mkdir(parents=True, exist_ok=True)
    solution = pdir / "solution.py"

    statement = data["statement"]
    stub = data.get("stub", "# your solution here\n")
    solution.write_text(f'"""\n{statement}\n"""\n\n{stub}\n')
    (pdir / "PROBLEM.md").write_text(f"# {data.get('title', 'Coding round')}\n\n{statement}\n")

    print("\n" + "─" * 60)
    print("CODING ROUND")
    print("─" * 60)
    print(textwrap.fill(statement, 88))
    print(f"\nOpen this file in your editor and write your solution:\n  {solution}")
    cmd = input("\nType 'done' when finished (or 'skip' to bail): ").strip().lower()
    while cmd not in ("done", "skip"):
        cmd = input("Type 'done' or 'skip': ").strip().lower()
    if cmd == "skip":
        return None

    code = solution.read_text()
    output = _run_solution(pdir, data.get("test_code", ""))
    print("\nRun output:\n" + textwrap.indent(output[:2000], "  "))

    return codex_turn(
        REVIEW_PROMPT.format(title=data.get("title", ""), code=code, output=output[:4000]),
        first=False)


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
