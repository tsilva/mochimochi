# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**mochi-mochi** is a Python CLI tool for managing Mochi flashcards via the Mochi API. It provides CRUD operations and AI-powered grading using OpenRouter's Gemini 2.5 Flash model.

## Documentation Philosophy

**This is a small, focused CLI tool (< 400 lines).** Keep all documentation consolidated in README.md and this file. Do not create additional .md files (summaries, migration guides, completion reports, etc.) unless explicitly requested by the user. Over-documentation creates maintenance burden for small projects.

## Development Commands

### Running the CLI
```bash
# Direct execution
python main.py <command>

# Or install and use entry point
uv sync
mochi-cards <command>
```

### Available Commands
```bash
python main.py list                          # List all cards in default deck
python main.py list --deck-name "Deck Name"  # List cards in specific deck
python main.py list --deck-id "deck_id"      # List cards by ID
python main.py grade --batch-size 20         # Grade cards using LLM
python main.py dump --output cards.md        # Export cards to markdown
python main.py decks                         # List all available decks
```

### Running Tests
```bash
# Install with dev dependencies
uv sync --extra dev

# Run all unit tests (skip integration tests)
pytest -m "not integration"

# Run all tests including integration tests (requires TEST_DECK_ID env var)
TEST_DECK_ID=your_deck_id pytest

# Run specific test class
pytest test_main.py::TestParseCard -v

# Run with coverage
pytest --cov=main --cov-report=term-missing
```

### Dependencies
```bash
# Install in development mode
uv sync --extra dev

# Runtime dependencies:
# - requests>=2.25.0
# - python-dotenv>=0.19.0

# Dev dependencies:
# - pytest>=7.0.0
# - pytest-mock>=3.10.0
```

## Configuration

The tool requires a `.env` file with:
```
MOCHI_API_KEY=your_mochi_api_key
OPENROUTER_API_KEY=your_openrouter_api_key  # Only for grading feature
```

## Architecture

### Single-File Structure
All code is in `main.py` - a single Python module (388 lines) with no subdirectories or packages.
Tests are in `test_main.py` using pytest framework.

### Error Handling Philosophy
**Fail fast.** The codebase intentionally avoids defensive error handling that swallows exceptions or provides defaults. Let exceptions propagate to the top rather than catching and continuing. This makes debugging easier and prevents silent failures.

### Core API Functions
- **`parse_card(content)`**: Utility to parse card content into (question, answer) tuple
- **`get_decks()`**: Fetch all decks from Mochi API
- **`get_cards(deck_id, limit=100)`**: Paginated card fetching
- **`create_card(deck_id, content, **kwargs)`**: Create new cards
- **`update_card(card_id, **kwargs)`**: Update existing cards
- **`delete_card(card_id)`**: Delete cards
- **`grade_cards_batch(cards_batch)`**: Grade multiple cards in a single LLM API call
- **`grade_all_cards(deck_id, batch_size=20)`**: Grade all cards in batches to minimize API costs
- **`dump_cards_to_markdown(deck_id, output_file)`**: Export cards to markdown format
- **`find_deck(decks, deck_name, deck_id)`**: Find deck by name (partial match) or ID

### Card Format
Cards use markdown with `---` separator:
```
Question text
---
Answer text
```

### LLM Grading System
- Uses OpenRouter API with Gemini 2.5 Flash model
- Batches multiple cards per API call (default: 20) to minimize costs
- Returns JSON-formatted grades with scores (0-10) and justifications

### Default Deck Behavior
By default, the CLI looks for a deck containing "AI/ML" in the name. Use `--deck-name` or `--deck-id` flags to specify different decks.

### Testing Architecture
- **Unit Tests**: Test utilities (parse_card, find_deck) and CLI parsing with mocks
- **Integration Tests**: Marked with `@pytest.mark.integration`, test live API operations
- **Mocking**: Uses `unittest.mock` and `pytest-mock` for external API calls
- **Fixtures**: Reusable test data (sample_decks, sample_cards) defined in test_main.py
- **Test Organization**: Tests grouped by functionality in classes (TestParseCard, TestFindDeck, TestCRUDOperations, etc.)

Integration tests require `TEST_DECK_ID` environment variable and are skipped by default.

## Entry Point
The package is configured in `pyproject.toml` with the entry point `mochi-cards` pointing to `main:main`.
