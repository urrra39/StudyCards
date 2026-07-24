"""LLM extraction: document chunk -> candidate flashcards.

EXTRACTION PROMPT DESIGN
------------------------
The prompt encodes four deliberate constraints:

1. **Concept-level, not trivia.** The model is told to test understanding
   ("why/how/what happens if") and explicitly banned from surface facts like
   dates, counts, or author names — those produce cards that are memorable
   without being meaningful.
2. **One concept per card + a `concept` label.** Naming the concept forces
   the model to decompose the chunk; multi-concept questions are the main
   source of un-gradeable reviews ("half right" has no SM-2 rating).
3. **Self-contained questions.** Cards are reviewed weeks later without the
   document, so deictic references ("in this section", "the author") are
   banned in the prompt.
4. **Strict JSON array output.** We instruct "JSON only, no markdown fences"
   but still defensively strip fences in the parser — models regress on
   formatting instructions often enough that parsing must not depend on
   perfect compliance.

The LLM call is isolated behind ``CompletionFn`` (str -> str) so the pipeline
is testable with a stub and provider-agnostic (Anthropic or OpenAI adapters
both satisfy it).
"""
from __future__ import annotations

import json
import re
from typing import Callable, List, Optional

from src.extraction.schema import Flashcard

# str prompt in, str completion out. Both provider adapters satisfy this.
CompletionFn = Callable[[str], str]

MAX_CARDS_PER_CHUNK = 8

EXTRACTION_PROMPT_TEMPLATE = """\
You are an expert tutor creating spaced-repetition flashcards from study material.

Extract at most {max_cards} flashcards from the text below. Rules:

1. CONCEPT-LEVEL ONLY: each card must test understanding of an idea, mechanism,
   relationship, or definition. Do NOT create cards about incidental facts
   (dates, page numbers, author names, section titles).
2. ONE concept per card. Never combine two ideas into one question.
3. SELF-CONTAINED: the question must make sense to someone who does not have
   the document. Never write "according to the text", "in this section",
   "the author", or similar.
4. NO REDUNDANCY: if two candidate cards test the same idea from slightly
   different angles, keep only the better one.
5. Answers must be correct, complete, and concise (1-3 sentences).
6. If the text contains no card-worthy concepts (e.g. a references list),
   return an empty array.

Respond with ONLY a JSON array, no markdown fences, no commentary:
[{{"concept": "short concept name", "question": "...", "answer": "..."}}]

TEXT:
{chunk_text}
"""


class ExtractionParseError(ValueError):
    """Raised when the LLM response cannot be parsed into cards."""


def build_extraction_prompt(chunk_text: str, max_cards: int = MAX_CARDS_PER_CHUNK) -> str:
    """Render the extraction prompt for one chunk."""
    return EXTRACTION_PROMPT_TEMPLATE.format(max_cards=max_cards, chunk_text=chunk_text)


def parse_cards_response(raw: str, source_chunk: Optional[int] = None) -> List[Flashcard]:
    """Parse an LLM response into Flashcards, tolerating minor format drift.

    Tolerated deviations: markdown code fences, leading/trailing prose around
    the array. Structural problems (not an array, missing fields) raise
    ExtractionParseError so the caller can decide to retry or skip the chunk.
    """
    text = raw.strip()
    # Strip ```json ... ``` fences if the model added them despite instructions.
    text = re.sub(r"^```(?:json)?\s*|```\s*$", "", text, flags=re.MULTILINE).strip()
    # If prose surrounds the array, isolate the outermost [...] span.
    if not text.startswith("["):
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end == -1 or end < start:
            raise ExtractionParseError(f"No JSON array found in response: {raw[:200]!r}")
        text = text[start : end + 1]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExtractionParseError(f"Invalid JSON in response: {exc}") from exc
    if not isinstance(data, list):
        raise ExtractionParseError(f"Expected JSON array, got {type(data).__name__}")

    cards: List[Flashcard] = []
    for item in data:
        if not isinstance(item, dict):
            continue  # skip malformed entries rather than losing the whole chunk
        question = str(item.get("question", "")).strip()
        answer = str(item.get("answer", "")).strip()
        concept = str(item.get("concept", "")).strip()
        if question and answer:
            cards.append(
                Flashcard(
                    question=question,
                    answer=answer,
                    concept=concept or question[:60],
                    source_chunk=source_chunk,
                )
            )
    return cards


def extract_cards_from_chunk(
    chunk_text: str,
    chunk_index: int,
    complete: CompletionFn,
    max_cards: int = MAX_CARDS_PER_CHUNK,
) -> List[Flashcard]:
    """Run extraction for one chunk. Parse errors return [] (skip the chunk)
    instead of failing the whole document — one bad completion should not
    cost the user the other 40 chunks."""
    prompt = build_extraction_prompt(chunk_text, max_cards=max_cards)
    raw = complete(prompt)
    try:
        return parse_cards_response(raw, source_chunk=chunk_index)
    except ExtractionParseError:
        return []
