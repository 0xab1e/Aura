"""Codex CLI backend — the only LLM dependency. Uses the user's
ChatGPT/Codex subscription via `codex exec`; each turn resumes the same
Codex session so the conversation history lives server-side."""

import json
import shutil
import subprocess
import sys


def check_codex() -> None:
    if shutil.which("codex") is None:
        print("ERROR: Codex CLI not found.")
        print("Install it and log in with your subscription:")
        print("  npm install -g @openai/codex   (or: brew install codex)")
        print("  codex login")
        sys.exit(1)


def codex_turn(prompt: str, first: bool) -> str:
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


def extract_json(text: str):
    """Parse JSON from a model reply that may be wrapped in ``` fences or prose."""
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        for part in parts[1:]:
            candidate = part.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # last resort: find the outermost braces
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return None
