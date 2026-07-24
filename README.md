# StudyCards

Document-to-flashcard generator with SM-2 spaced repetition.

Upload a PDF or text file, get concept-level Q&A flashcards extracted by an LLM,
and review them on a schedule computed by a faithful implementation of the
SuperMemo SM-2 algorithm — with an evaluation harness that measures the schedule
against a fixed-interval baseline on synthetic forgetting curves.

> Work in progress. Full README (architecture, setup, evaluation results) lands in Phase 7.

## Layout

```
src/
  ingestion/    PDF/text loading and chunking
  extraction/   LLM Q&A card extraction (Anthropic API)
  scheduler/    SM-2 implementation
  data/         SQLite persistence (cards + review history)
  evaluation/   forgetting-curve simulation, SM-2 vs. baseline
  app/          Streamlit demo
tests/          pytest suite
docs/           design decisions, evaluation results
```

## License

MIT
