# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**mochi-mochi** is a Python CLI tool for managing Mochi flashcards via the Mochi API. It provides CRUD operations with a local-first sync workflow.

**Architecture**: Simple local-first sync (~620 lines). Local markdown file is source of truth, Mochi is sync target.

## Documentation Philosophy

**This is a small, focused CLI tool (~620 lines).** Keep all documentation consolidated in README.md and this file. Do not create additional .md files (summaries, migration guides, completion reports, etc.) unless explicitly requested by the user. Over-documentation creates maintenance burden for small projects.

## Development Commands

### Running the CLI
```bash
# Direct execution
python main.py <command>

# Or install globally with uv tool
uv tool install git+https://github.com/tsilva/mochi-mochi.git
mochi-mochi <command>

# Or install locally for development
uv sync
mochi-mochi <command>
```

### Available Commands

**Core Sync Workflow**:
```bash
python main.py decks                         # List all decks
python main.py pull <deck_id>                # Download deck from Mochi
python main.py push <deck-file>.md           # Push local changes to Mochi
python main.py push <deck-file>.md --force   # Push without duplicate detection
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
pytest tests/test_main.py::TestParseCard -v

# Run with coverage
pytest --cov=main --cov-report=term-missing
```

### Dependencies
```bash
# Install in development mode
uv sync --extra dev

# Runtime dependencies:
# - requests>=2.25.0

# Dev dependencies:
# - pytest>=7.0.0
# - pytest-mock>=3.10.0
```

## Configuration

**API Key Configuration**: The tool stores API keys in `~/.mochi-mochi/config`

On first run, the tool will prompt you to enter your Mochi API key and automatically save it to the config file.

**Config file format** (`~/.mochi-mochi/config`):
```
MOCHI_API_KEY=your_mochi_api_key
```

**Required:**
- `MOCHI_API_KEY`: Auto-prompted on first run (get from https://app.mochi.cards/settings)

Deck files are managed independently with format: `<deck-name>-<deck_id>.md`

## Architecture

### Single-File Structure
All code is in `main.py` - a single Python module with no subdirectories or packages.
Tests are in `tests/test_main.py` using pytest framework.

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

### Error Handling Philosophy
**Fail fast.** The codebase intentionally avoids defensive error handling that swallows exceptions or provides defaults. Let exceptions propagate to the top rather than catching and continuing. This makes debugging easier and prevents silent failures.

### Core Functions

**Sync Operations**:
- **`pull(deck_id)`**: Download cards from Mochi to `<deck-name>-<deck_id>.md` file
- **`push(file_path, force=False)`**: One-way sync deck file → Mochi (validates structure first, then extracts deck_id from filename)
- **`validate_deck_file(file_path)`**: Validate deck file structure before push operations (checks file format, card structure, required fields)
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
- **`load_user_config()`**: Load configuration from `~/.mochi-mochi/config`
- **`get_api_key()`**: Get API key from config, prompting user if not found
- **`prompt_and_save_api_key()`**: Prompt user for API key and save to config file

**API Operations** (used internally by sync):
- **`get_cards(deck_id, limit=100)`**: Paginated card fetching
- **`create_card(deck_id, content, **kwargs)`**: Create new cards
- **`update_card(card_id, **kwargs)`**: Update existing cards
- **`delete_card(card_id)`**: Delete cards

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

### Multi-Deck Model & User Workflow

**Recommended Setup** (separate git repo for all decks):
```bash
# Install tool globally
uv tool install git+https://github.com/tsilva/mochi-mochi.git

# First run will prompt for API key (saved to ~/.mochi-mochi/config)
mochi-mochi decks

# Create your decks repository (separate from tool)
mkdir ~/mochi-decks && cd ~/mochi-decks
git init

# Pull decks from Mochi
mochi-mochi pull abc123xyz           # Creates: python-basics-abc123xyz.md
mochi-mochi pull def456uvw           # Creates: javascript-def456uvw.md

git add . && git commit -m "Initial decks"

# Daily workflow with specific deck
vim python-basics-abc123xyz.md       # Edit cards
git diff                             # Review changes
git commit -am "Add list comprehension question"
mochi-mochi push python-basics-abc123xyz.md  # Sync to Mochi
```

**Why separate directory?**
- Tool repo (mochi-mochi) is public, your decks repo is private
- Manage all decks in one version-controlled repo
- No config files in decks repo - API key stored globally in `~/.mochi-mochi/config`
- Each deck file carries its deck ID in filename

### Testing Architecture
- **Unit Tests**: Test utilities (parse_card, find_deck, validate_deck_file) and CLI parsing with mocks
- **Integration Tests**: Marked with `@pytest.mark.integration`, test live API operations
- **Mocking**: Uses `unittest.mock` and `pytest-mock` for external API calls
- **Fixtures**: Reusable test data (sample_decks, sample_cards) defined in tests/test_main.py
- **Test Organization**: Tests grouped by functionality in classes (TestParseCard, TestFindDeck, TestValidation, TestCRUDOperations, etc.)
- **Test Location**: All tests are in the `tests/` directory

Integration tests require `TEST_DECK_ID` environment variable and are skipped by default.

## Entry Point
The package is configured in `pyproject.toml` with the entry point `mochi-cards` pointing to `main:main`.
