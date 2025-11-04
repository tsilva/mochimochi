# mochi-mochi

A Python CLI tool for managing Mochi flashcards via the Mochi API with a local-first sync workflow. Edit your flashcards in markdown, grade them with AI, and sync changes to Mochi.

## Features

- 🔄 **Local-First Sync**: Pull decks to local markdown files, edit, and push changes back
- 📝 **Multi-Deck Support**: Manage multiple decks as separate `<deck-name>-<deck_id>.md` files
- 🤖 **AI Grading**: Automatically grade flashcards using OpenRouter's Gemini 2.5 Flash LLM
- 🔍 **Duplicate Detection**: Prevent duplicate cards when pushing to remote
- 📂 **Version Control**: Track all decks in git with simple file-based workflow
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

Create a `.env` file in your working directory (or decks repository) with your API keys:

```env
MOCHI_API_KEY=your_mochi_api_key_here
OPENROUTER_API_KEY=your_openrouter_api_key_here
```

**Required:**
- `MOCHI_API_KEY`: Your Mochi API key (obtain from your Mochi account settings)

**Optional:**
- `OPENROUTER_API_KEY`: Only required for the AI grading feature (sign up at [OpenRouter](https://openrouter.ai/))

## Usage

### Local-First Workflow

The tool operates on a **local-first multi-deck model**:

1. **List** available decks with `decks` command
2. **Pull** a deck to `<deck-name>-<deck_id>.md`
3. **Edit** locally (manually or via `grade` command)
4. **Push** changes back to Mochi

### Command Line Interface

All commands can be run directly or via the installed `mochi-cards` command.

#### List available decks
```bash
python main.py decks
# or
mochi-cards decks
```

Displays all your decks with their IDs.

#### Pull deck from remote
```bash
python main.py pull <deck_id>
# or
mochi-cards pull <deck_id>
```

Downloads all cards from the specified deck to `<deck-name>-<deck_id>.md`.

#### Push changes to remote
```bash
python main.py push <deck-file>.md
# or
mochi-cards push <deck-file>.md
```

Uploads local changes to Mochi. Includes duplicate detection to prevent creating duplicate cards.

To skip duplicate detection:
```bash
python main.py push <deck-file>.md --force
```

#### Grade cards with AI
```bash
python main.py grade <deck-file>.md --batch-size 20
# or
mochi-cards grade <deck-file>.md --batch-size 20
```

Grades all cards in the specified deck file using AI. Shows only cards scoring less than 10/10.

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
    grade_local_cards
)

# Get all decks
decks = get_decks()

# Pull deck to local file
pull(deck_id)  # Creates <deck-name>-<deck_id>.md

# Push deck file to remote
push("python-basics-abc123.md")

# Grade local cards
imperfect_cards, all_results = grade_local_cards("python-basics-abc123.md", batch_size=20)

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

### Local File Format

Deck files (`<deck-name>-<deck_id>.md`) store cards with frontmatter for metadata:

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
Download cards from Mochi to `<deck-name>-<deck_id>.md` file.

**Parameters:**
- `deck_id` (str): Deck ID to pull from

### `push(file_path, force=False)`
Push local deck file to Mochi with duplicate detection.

**Parameters:**
- `file_path` (str): Path to deck file (e.g., "python-abc123.md")
- `force` (bool): If True, skip duplicate detection

### `grade_local_cards(file_path, batch_size=20)`
Grade cards from local deck file using AI.

**Parameters:**
- `file_path` (str): Path to deck file to grade
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

- Each deck is managed as a separate `<deck-name>-<deck_id>.md` file
- Deck ID is extracted from filename for sync operations
- The grading feature uses OpenRouter's Gemini 2.5 Flash model for evaluation
- Local deck files can be edited manually and tracked in git
- Card fetching handles pagination automatically
- One-way sync: local files are source of truth, Mochi is sync target

## License

See [LICENSE](LICENSE) file for details.

## Author

tsilva
