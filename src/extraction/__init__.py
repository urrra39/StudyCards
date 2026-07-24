"""LLM-based Q&A card extraction from document chunks."""
from src.extraction.extractor import (
    CompletionFn,
    ExtractionParseError,
    build_extraction_prompt,
    extract_cards_from_chunk,
    parse_cards_response,
)
from src.extraction.filtering import dedup_cards, filter_cards, passes_quality
from src.extraction.model_discovery import (
    DEFAULT_ANTHROPIC_MODELS,
    DEFAULT_OPENAI_MODELS,
    ModelList,
    discover_models,
    fetch_anthropic_models,
    fetch_openai_models,
)
from src.extraction.pipeline import extract_flashcards
from src.extraction.providers import make_completion_fn
from src.extraction.schema import Flashcard

__all__ = [
    "CompletionFn",
    "ExtractionParseError",
    "Flashcard",
    "ModelList",
    "DEFAULT_ANTHROPIC_MODELS",
    "DEFAULT_OPENAI_MODELS",
    "build_extraction_prompt",
    "dedup_cards",
    "discover_models",
    "extract_cards_from_chunk",
    "extract_flashcards",
    "fetch_anthropic_models",
    "fetch_openai_models",
    "filter_cards",
    "make_completion_fn",
    "parse_cards_response",
    "passes_quality",
]
