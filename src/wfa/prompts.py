"""Instructions sent to the LLM. Kept here, away from the UI: users see only the
words and counts that are shared, never these instructions."""

from __future__ import annotations

MAX_SENTENCES = 3
MAX_THEMES = 10
VERSION = 1  # bump when anything below changes, to invalidate cached answers

THEMES_SYSTEM = (
    "You are a literary analyst. You will be given only the most frequent words of a book "
    "(common function words removed) with how often each occurs. You are not told the title "
    "or author. Infer what the book is about and its main themes from the words alone."
)

THEMES_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": f"What the book is about and its main themes, in at most {MAX_SENTENCES} sentences.",
        },
        "themes": {
            "type": "array",
            "items": {"type": "string"},
            "description": f"Between 5 and {MAX_THEMES} short theme words or phrases.",
        },
    },
    "required": ["summary", "themes"],
}


def themes_user_message(words: list[tuple[str, int]]) -> str:
    listing = "\n".join(f"{word}: {count}" for word, count in words)
    return (
        f"The {len(words)} most frequent words in the book, with counts:\n\n{listing}\n\n"
        f"Reply in JSON with `summary` (at most {MAX_SENTENCES} sentences on what the book is about) "
        f"and `themes` (5 to {MAX_THEMES} short theme words or phrases)."
    )
