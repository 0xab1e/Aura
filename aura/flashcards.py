"""Flashcards with SM-2 spaced repetition. Fully local — no LLM needed to
review, so you can drill cards even offline. Cards are harvested from the
live session whenever the profile is saved (debrief / quit / compaction).
Each user has their own deck file."""

import json
from datetime import date, timedelta
from pathlib import Path

HARVEST_PROMPT = """\
[SYSTEM TASK — flashcard harvest, the candidate will not see this.
For each concept you TAUGHT or corrected this session, output a flashcard.
JSON array only:
[{"front": "<question testing the concept>", "back": "<concise ideal answer>",
  "skill": "<skill area>"}]
Only concepts actually taught/corrected this session, max 8 cards, [] if none.
Output ONLY the JSON array.]"""


def load_deck(deck_file: Path) -> list[dict]:
    if deck_file.exists():
        try:
            return json.loads(deck_file.read_text())
        except json.JSONDecodeError:
            pass
    return []


def save_deck(deck: list[dict], deck_file: Path) -> None:
    deck_file.parent.mkdir(parents=True, exist_ok=True)
    deck_file.write_text(json.dumps(deck, indent=2))


def add_cards(deck: list[dict], new_cards: list[dict], deck_file: Path) -> int:
    """Add harvested cards, skipping near-duplicates. Returns count added."""
    fronts = {c["front"].strip().lower() for c in deck}
    added = 0
    for c in new_cards:
        if not isinstance(c, dict) or not c.get("front") or not c.get("back"):
            continue
        key = c["front"].strip().lower()
        if key in fronts:
            continue
        fronts.add(key)
        deck.append({
            "front": c["front"], "back": c["back"],
            "skill": c.get("skill", ""),
            "ef": 2.5, "interval": 0, "reps": 0,
            "due": date.today().isoformat(),
        })
        added += 1
    if added:
        save_deck(deck, deck_file)
    return added


def due_cards(deck: list[dict]) -> list[dict]:
    today = date.today().isoformat()
    return [c for c in deck if c["due"] <= today]


def grade_card(deck: list[dict], card: dict, quality: int,
               deck_file: Path) -> None:
    """SM-2: quality 0-5 (0=blank, 3=hard recall, 5=perfect)."""
    quality = max(0, min(5, quality))
    if quality >= 3:
        if card["reps"] == 0:
            card["interval"] = 1
        elif card["reps"] == 1:
            card["interval"] = 6
        else:
            card["interval"] = round(card["interval"] * card["ef"])
        card["reps"] += 1
    else:
        card["reps"] = 0
        card["interval"] = 1
    card["ef"] = max(1.3, card["ef"] + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    card["due"] = (date.today() + timedelta(days=card["interval"])).isoformat()
    save_deck(deck, deck_file)
