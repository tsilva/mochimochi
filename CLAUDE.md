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
python main.py pull                          # Download from Mochi (initialization/reset)
python main.py push                          # Push local changes to Mochi
python main.py push --force                  # Push without duplicate detection
```

**Local Operations**:
```bash
python main.py grade --batch-size 20         # Grade cards in local file using LLM
git status                                   # See what changed locally
git diff mochi_cards.md                      # Review specific changes
```

**Discovery** (doesn't require DECK_ID):
```bash
python main.py decks                         # List all decks (only needs API_KEY)
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
DECK_ID=your_deck_id
OPENROUTER_API_KEY=your_openrouter_api_key  # Only for grading feature
```

All operations work on the single deck specified by `DECK_ID`.

## Architecture

### Single-File Structure
All code is in `main.py` - a single Python module with no subdirectories or packages.
Tests are in `test_main.py` using pytest framework.

### Local-First Workflow

The tool operates on a **local-first model** where your local `mochi_cards.md` is the source of truth:

1. **Local Working Copy**: `mochi_cards.md` - your editable deck file (source of truth)
2. **Version Control**: Use git in your own directory to track changes
3. **Workflow**: `pull` (once) → edit locally → commit → `push` to sync

**Benefits**:
- Simple one-way sync: local → remote
- No hidden state directories (`.mochi_sync/` removed)
- Use git for version control and change tracking
- Duplicate detection prevents card duplication
- Works offline for local operations

**Key Commands**:
- `pull`: Downloads from Mochi (initialization or reset)
- `push`: Syncs local changes to Mochi (creates/updates/deletes to match local)
- `git status/diff`: See what changed locally
- `grade`: LLM-based card grading (works offline)

### Error Handling Philosophy
**Fail fast.** The codebase intentionally avoids defensive error handling that swallows exceptions or provides defaults. Let exceptions propagate to the top rather than catching and continuing. This makes debugging easier and prevents silent failures.

### Core Functions

**Sync Operations**:
- **`pull(deck_id)`**: Download cards from Mochi to local file (initialization/reset)
- **`push(deck_id, force=False)`**: One-way sync local → Mochi (create/update/delete to match local)

**Utility Functions**:
- **`parse_card(content)`**: Parse card content into (question, answer) tuple
- **`content_hash(question, answer)`**: Generate hash for duplicate detection
- **`parse_markdown_cards(markdown_text)`**: Parse markdown file into card dicts with metadata
- **`format_card_to_markdown(card)`**: Format card dict to markdown with frontmatter
- **`ensure_sync_dir()`**: Create .mochi_sync directory and update .gitignore
- **`get_decks()`**: Fetch all decks from Mochi API
- **`find_deck(decks, deck_name, deck_id)`**: Find deck by name (partial match) or ID

**Local Operations**:
- **`grade_local_cards(batch_size=20)`**: Grade cards from local file using LLM

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

### Single Deck Model & User Workflow
The CLI operates on a single deck specified by `DECK_ID` in `.env`.

**Recommended Setup** (separate from tool repo):
```bash
# Create your own private cards directory
mkdir ~/my-flashcards && cd ~/my-flashcards
echo "MOCHI_API_KEY=..." > .env
echo "DECK_ID=..." >> .env
git init

# Initialize from Mochi
mochi-cards pull
git add . && git commit -m "Initial cards"

# Daily workflow
vim mochi_cards.md                   # Edit cards
git diff                             # Review changes
git commit -am "Add Python questions"
mochi-cards push                     # Sync to Mochi
```

**Why separate directory?**
- Tool repo is public, your cards are private
- You control version history with your own git repo
- Easy backup/restore

### Testing Architecture
- **Unit Tests**: Test utilities (parse_card, find_deck) and CLI parsing with mocks
- **Integration Tests**: Marked with `@pytest.mark.integration`, test live API operations
- **Mocking**: Uses `unittest.mock` and `pytest-mock` for external API calls
- **Fixtures**: Reusable test data (sample_decks, sample_cards) defined in test_main.py
- **Test Organization**: Tests grouped by functionality in classes (TestParseCard, TestFindDeck, TestCRUDOperations, etc.)

Integration tests require `TEST_DECK_ID` environment variable and are skipped by default.

## Entry Point
The package is configured in `pyproject.toml` with the entry point `mochi-cards` pointing to `main:main`.
