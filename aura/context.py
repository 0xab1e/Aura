"""Context-window management for the long-running Codex session.

The Codex session accumulates every turn. To keep long mentoring sessions
from overflowing the model's context, we track an approximate budget and,
when it's exceeded, "compact": ask the live session for a handoff summary,
then reseed a brand-new Codex session with the mentor brief + that summary.
The user experiences one uninterrupted conversation.
"""

from .backend import codex_turn

# ~4 chars/token; budget well under typical context limits to leave headroom
MAX_CHARS = 120_000
MAX_TURNS = 60

HANDOFF_PROMPT = """\
[SYSTEM TASK — this session is being compacted. Write a handoff note for the
mentor who continues this exact conversation. Include, concisely:
1. Your full current mental model of the candidate: every skill probed/taught,
   its status (strong/shaky/taught/untested), and key evidence.
2. What you taught this session and what still needs re-verification (and what
   angle you'd use to re-check it).
3. The current thread: what was just being discussed and what your next
   question or teaching point was going to be.
Plain text, no preamble. This note is the only memory the next mentor gets.]"""

CONTINUATION_NOTE = """
HANDOFF FROM YOUR EARLIER SELF (the session continues seamlessly — the candidate
must not notice any reset; do NOT greet them again or restart):
---
{handoff}
---
Pick up the conversation exactly where the handoff says it left off: continue
with the next question or teaching point mid-flow, as if nothing happened.
"""


class ContextTracker:
    def __init__(self, max_chars: int = MAX_CHARS, max_turns: int = MAX_TURNS):
        self.max_chars = max_chars
        self.max_turns = max_turns
        self.chars = 0
        self.turns = 0

    def add(self, user_text: str, reply_text: str) -> None:
        self.chars += len(user_text) + len(reply_text)
        self.turns += 1

    def needs_compact(self) -> bool:
        return self.chars >= self.max_chars or self.turns >= self.max_turns

    def reset(self, seed_chars: int = 0) -> None:
        self.chars = seed_chars
        self.turns = 0


def compact_session(base_brief: str) -> str:
    """Summarize the live session and reseed a fresh one.

    base_brief: the full mentor brief (JD + resume + operating instructions)
    minus the 'greet them' opener — the continuation note overrides that.
    Returns the new session's first reply (usually the mid-flow continuation).
    """
    handoff = codex_turn(HANDOFF_PROMPT, first=False)
    seed = base_brief + CONTINUATION_NOTE.format(handoff=handoff)
    return codex_turn(seed, first=True)
