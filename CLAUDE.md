# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**mochi-mochi** is a Python CLI tool for managing Mochi flashcards via the Mochi API. It provides CRUD operations and AI-powered grading using OpenRouter's Gemini 2.5 Flash model.

**Architecture**: Simple local-first sync (~675 lines). Local markdown file is source of truth, Mochi is sync target.

## Documentation Philosophy

**This is a small, focused CLI tool (~675 lines).** Keep all documentation consolidated in README.md and this file. Do not create additional .md files (summaries, migration guides, completion reports, etc.) unless explicitly requested by the user. Over-documentation creates maintenance burden for small projects.

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

**Core Sync Workflow**:
```bash
python main.py decks                         # List all decks
python main.py pull <deck_id>                # Download deck from Mochi
python main.py push <deck-file>.md           # Push local changes to Mochi
python main.py push <deck-file>.md --force   # Push without duplicate detection
```

**Local Operations**:
```bash
python main.py grade <deck-file>.md --batch-size 20  # Grade cards using LLM
git status                                   # See what changed locally
git diff <deck-file>.md                      # Review specific changes
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

Deck files are managed independently with format: `<deck-name>-<deck_id>.md`

## Architecture

### Single-File Structure
All code is in `main.py` - a single Python module with no subdirectories or packages.
Tests are in `test_main.py` using pytest framework.

### Local-First Multi-Deck Workflow

The tool operates on a **local-first model** with multiple deck support:

1. **Deck Files**: Each deck is `<deck-name>-<deck_id>.md` (source of truth)
2. **Version Control**: Use git to track all decks in one repo
3. **Workflow**: `pull <deck_id>` → edit locally → commit → `push <file>`

**File Format**: `<deck-name>-<deck_id>.md`
- Example: `python-basics-abc123xyz.md`
- Deck ID is extracted from filename for sync

**Benefits**:
- Manage multiple decks in one git repo
- Simple one-way sync: local → remote
- No hidden state directories
- No DECK_ID in .env - decoupled from storage
- Works offline for local operations

**Key Commands**:
- `pull <deck_id>`: Downloads from Mochi, creates `<name>-<deck_id>.md`
- `push <file>`: Syncs that deck file to Mochi
- `grade <file>`: LLM-based card grading

### Error Handling Philosophy
**Fail fast.** The codebase intentionally avoids defensive error handling that swallows exceptions or provides defaults. Let exceptions propagate to the top rather than catching and continuing. This makes debugging easier and prevents silent failures.

### Core Functions

**Sync Operations**:
- **`pull(deck_id)`**: Download cards from Mochi to `<deck-name>-<deck_id>.md` file
- **`push(file_path, force=False)`**: One-way sync deck file → Mochi (extracts deck_id from filename)
- **`get_deck(deck_id)`**: Fetch deck metadata (name, etc.)

**Utility Functions**:
- **`parse_card(content)`**: Parse card content into (question, answer) tuple
- **`content_hash(question, answer)`**: Generate hash for duplicate detection
- **`sanitize_filename(name)`**: Convert deck name to safe filename
- **`extract_deck_id_from_filename(file_path)`**: Extract deck ID from `<name>-<deck_id>.md` format
- **`parse_markdown_cards(markdown_text)`**: Parse markdown file into card dicts with metadata
- **`format_card_to_markdown(card)`**: Format card dict to markdown with frontmatter
- **`get_decks()`**: Fetch all decks from Mochi API
- **`get_deck(deck_id)`**: Fetch specific deck info
- **`find_deck(decks, deck_name, deck_id)`**: Find deck by name (partial match) or ID

**Local Operations**:
- **`grade_local_cards(file_path, batch_size=20)`**: Grade cards from deck file using LLM

**API Operations** (used internally by sync):
- **`get_cards(deck_id, limit=100)`**: Paginated card fetching
- **`create_card(deck_id, content, **kwargs)`**: Create new cards
- **`update_card(card_id, **kwargs)`**: Update existing cards
- **`delete_card(card_id)`**: Delete cards
- **`grade_cards_batch(cards_batch)`**: Grade multiple cards in a single LLM API call

### Card Format

**Internal API Format:**
Cards use markdown with `---` separator:
```
Question text
---
Answer text
```

**Local File Format** (`mochi_cards.md`):
Clean markdown with frontmatter for metadata (no header):
```markdown
---
card_id: abc123
tags: ["python", "basics"]
archived: false
---
Question text
---
Answer text
---
card_id: null
---
New question
---
New answer
```

**Frontmatter Fields**:
- `card_id`: Mochi card ID (or `null` for new cards)
- `tags`: JSON array of tags (optional)
- `archived`: Boolean flag for archived cards (optional, only included if `true`)

**Sync Behavior**:
- Cards with valid IDs → updated on `push`
- Cards with `card_id: null` → created as new cards on `push`
- Duplicate detection uses content hash (question + answer)

### LLM Grading System
- Uses OpenRouter API with Gemini 2.5 Flash model
- Batches multiple cards per API call (default: 20) to minimize costs
- Returns JSON-formatted grades with scores (0-10) and justifications

### Multi-Deck Model & User Workflow

**Recommended Setup** (separate git repo for all decks):
```bash
# Create your decks repository (separate from tool)
mkdir ~/mochi-decks && cd ~/mochi-decks
echo "MOCHI_API_KEY=..." > .env
echo "OPENROUTER_API_KEY=..." >> .env  # Optional, for grading
git init

# Pull decks from Mochi
mochi-cards decks                    # List available decks
mochi-cards pull abc123xyz           # Creates: python-basics-abc123xyz.md
mochi-cards pull def456uvw           # Creates: javascript-def456uvw.md

git add . && git commit -m "Initial decks"

# Daily workflow with specific deck
vim python-basics-abc123xyz.md       # Edit cards
git diff                             # Review changes
git commit -am "Add list comprehension question"
mochi-cards push python-basics-abc123xyz.md  # Sync to Mochi
```

**Why separate directory?**
- Tool repo (mochi-mochi) is public, your decks repo is private
- Manage all decks in one version-controlled repo
- No DECK_ID coupling in .env - each file carries its deck ID

### Testing Architecture
- **Unit Tests**: Test utilities (parse_card, find_deck) and CLI parsing with mocks
- **Integration Tests**: Marked with `@pytest.mark.integration`, test live API operations
- **Mocking**: Uses `unittest.mock` and `pytest-mock` for external API calls
- **Fixtures**: Reusable test data (sample_decks, sample_cards) defined in test_main.py
- **Test Organization**: Tests grouped by functionality in classes (TestParseCard, TestFindDeck, TestCRUDOperations, etc.)

Integration tests require `TEST_DECK_ID` environment variable and are skipped by default.

## Entry Point
The package is configured in `pyproject.toml` with the entry point `mochi-cards` pointing to `main:main`.
