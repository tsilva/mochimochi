# mochi-mochi

A Python CLI tool for managing Mochi flashcards via the Mochi API with a local-first sync workflow. Edit your flashcards in markdown, grade them with AI, and sync changes to Mochi.

## Features

- 🔄 **Sync Workflow**: Pull cards to local markdown, edit, and push changes back
- 📝 **Local Editing**: Work with flashcards in `mochi_cards.md` with full version control support
- 🤖 **AI Grading**: Automatically grade flashcards using OpenRouter's Gemini 2.5 Flash LLM
- 🔍 **Duplicate Detection**: Prevent duplicate cards when pushing to remote
- 📋 **Status Tracking**: See local changes before pushing
- 🧪 **Test Suite**: Comprehensive pytest-based test suite with unit and integration tests

## Installation

### Using pip (from source)

1. Clone this repository:
   ```bash
   git clone <repository-url>
   cd mochi-mochi
   ```

2. Install the package:
   ```bash
   pip install -e .
   ```

   Or install directly:
   ```bash
   pip install .
   ```

After installation, the `mochi-cards` command will be available in your PATH.

### Requirements

- Python 3.8 or higher
- `requests>=2.25.0`
- `python-dotenv>=0.19.0`

## Configuration

Create a `.env` file in the project root with your API keys and deck ID:

```env
MOCHI_API_KEY=your_mochi_api_key_here
DECK_ID=your_deck_id_here
OPENROUTER_API_KEY=your_openrouter_api_key_here
```

**Required:**
- `MOCHI_API_KEY`: Your Mochi API key
- `DECK_ID`: The ID of the deck you want to work with

**Optional:**
- `OPENROUTER_API_KEY`: Only required if you want to use the AI grading feature

### Getting Configuration Values

- **Mochi API Key**: Obtain from your Mochi account settings
- **Deck ID**: Run `python main.py decks` to list all your decks with their IDs
- **OpenRouter API Key**: Sign up at [OpenRouter](https://openrouter.ai/) to get an API key

## Usage

### Sync-Based Workflow

The tool operates on a **local-first sync model**:

1. **Pull** cards from remote to `mochi_cards.md`
2. **Edit** locally (manually or via `grade` command)
3. **Push** changes back to Mochi

### Command Line Interface

All commands can be run directly or via the installed `mochi-cards` command.

#### List available decks (to find deck ID)
```bash
python main.py decks
# or
mochi-cards decks
```

This command only requires `MOCHI_API_KEY` and displays all your decks with their IDs.

#### Pull cards from remote
```bash
python main.py pull
# or
mochi-cards pull
```

Downloads all cards from the deck specified in your `.env` file to `mochi_cards.md`.

#### Show local changes
```bash
python main.py status
# or
mochi-cards status
```

Shows what cards have been added, modified, or deleted locally since the last sync.

#### Push changes to remote
```bash
python main.py push
# or
mochi-cards push
```

Uploads local changes to Mochi. Includes duplicate detection to prevent creating duplicate cards.

To skip duplicate detection:
```bash
python main.py push --force
```

#### Grade cards with AI
```bash
python main.py grade --batch-size 20
# or
mochi-cards grade --batch-size 20
```

Grades all cards in your local `mochi_cards.md` file using AI. Shows only cards scoring less than 10/10.

### Python API

You can also import and use the functions directly in your Python code:

```python
from main import (
    get_decks,
    get_cards,
    create_card,
    update_card,
    delete_card,
    pull,
    push,
    status,
    grade_local_cards
)

# Get all decks
decks = get_decks()

# Pull cards to local file
pull(deck_id)

# Push changes to remote
push(deck_id)

# Check status
status()

# Grade local cards
imperfect_cards, all_results = grade_local_cards(batch_size=20)

# Direct API operations
cards = get_cards(deck_id)
card = create_card(deck_id, content="What is Python?\n---\nA programming language.")
update_card(card['id'], content="Updated content\n---\nUpdated answer")
delete_card(card['id'])
```

## Card Format

### Internal API Format

Cards use markdown with `---` separator:
```
Question text
---
Answer text
```

### Local File Format (`mochi_cards.md`)

Cards are stored with frontmatter for metadata:

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

**Frontmatter Fields:**
- `card_id`: Mochi card ID (or `null` for new cards)
- `tags`: JSON array of tags (optional)
- `archived`: Boolean flag for archived cards (optional, only included if `true`)

**Sync Behavior:**
- Cards with valid IDs → updated on `push`
- Cards with `card_id: null` → created as new cards on `push`
- Cards removed from file → deleted on `push`
- Duplicate detection uses content hash (question + answer)

## API Functions

### `get_decks()`
Returns all decks in your Mochi account.

**Returns:** List of deck objects

### `get_cards(deck_id, limit=100)`
Fetches all cards from a specific deck with pagination support.

**Parameters:**
- `deck_id` (str): The ID of the deck
- `limit` (int): Number of cards per request (default: 100)

**Returns:** List of card objects

### `create_card(deck_id, content, **kwargs)`
Creates a new flashcard.

**Parameters:**
- `deck_id` (str): Deck ID to add the card to
- `content` (str): Markdown content of the card (format: "Question\n---\nAnswer")
- `**kwargs`: Optional fields like `tags`, `archived`

**Returns:** Created card data

### `update_card(card_id, **kwargs)`
Updates an existing card.

**Parameters:**
- `card_id` (str): ID of the card to update
- `**kwargs`: Fields to update (e.g., `content`, `tags`, `archived`)

**Returns:** Updated card data

### `delete_card(card_id)`
Deletes a card.

**Parameters:**
- `card_id` (str): ID of the card to delete

**Returns:** `True` if successful

### `pull(deck_id)`
Pull cards from remote and merge with local changes using three-way merge.

**Parameters:**
- `deck_id` (str): Deck ID to pull from

### `push(deck_id, force=False)`
Push local changes to remote with duplicate detection.

**Parameters:**
- `deck_id` (str): Deck ID to push to
- `force` (bool): If True, skip duplicate warnings

### `status()`
Show diff between local and last sync state.

### `grade_local_cards(batch_size=20)`
Grade cards from local file using AI.

**Parameters:**
- `batch_size` (int): Number of cards per API request (default: 20)

**Returns:** Tuple of `(imperfect_cards, all_results)`

**Grading Scale:**
- 10: Perfect answer, completely accurate
- 7-9: Mostly correct with minor issues
- 4-6: Partially correct but missing key information
- 0-3: Incorrect or severely incomplete

## Development & Testing

### Running Tests

The project includes a comprehensive test suite using pytest:

```bash
# Install with dev dependencies
uv sync --extra dev

# Run unit tests (no API required)
pytest -m "not integration"

# Run all tests including integration tests (requires TEST_DECK_ID)
TEST_DECK_ID=your_deck_id pytest

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=main --cov-report=term-missing
```

### Test Coverage

- **Unit tests** - Mocked tests for utilities, parsing, and CLI
- **Integration tests** - Live API tests (require `TEST_DECK_ID` environment variable)

Unit tests cover:
- Card parsing (question/answer separation)
- Deck finding utilities
- Markdown parsing and formatting
- CLI argument parsing

## Notes

- All operations work on the single deck specified by `DECK_ID` in your `.env` file
- The grading feature uses OpenRouter's Gemini 2.5 Flash model for evaluation
- Local file (`mochi_cards.md`) can be edited manually or committed to git
- The `.mochi_sync/` directory tracks sync state (automatically added to `.gitignore`)
- Three-way merge ensures local and remote changes merge correctly
- Card fetching handles pagination automatically

## License

See [LICENSE](LICENSE) file for details.

## Author

tsilva
