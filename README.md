# mochi-mochi

A Python tool for managing and grading Mochi flashcards via the Mochi API. This script provides functionality to list, create, update, delete, and automatically grade flashcards using AI-powered evaluation.

## Features

- 📚 **List Cards**: Fetch and display all cards from your Mochi decks
- ➕ **Create Cards**: Programmatically create new flashcards
- ✏️ **Update Cards**: Modify existing card content
- 🗑️ **Delete Cards**: Remove cards via API
- 🤖 **AI Grading**: Automatically grade flashcards using OpenRouter's Gemini 2.5 Flash LLM
- 📝 **Export to Markdown**: Export all cards to a markdown file for backup or review
- 📤 **Upload from Markdown**: Import cards from markdown files (supports both create and update)
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
- **Deck ID**: You can find your deck ID in the Mochi web app URL when viewing a deck (e.g., `https://app.mochi.cards/decks/abc123` - the ID is `abc123`)
- **OpenRouter API Key**: Sign up at [OpenRouter](https://openrouter.ai/) to get an API key

## Usage

### Command Line Interface

The script can be run directly or via the installed `mochi-cards` command. All commands operate on the deck specified in your `.env` file.

#### List available decks (to find deck ID)
```bash
python main.py decks
# or
mochi-cards decks
```

This command only requires `MOCHI_API_KEY` and displays all your decks with their IDs.

#### List all cards
```bash
python main.py list
# or
mochi-cards list
```

#### Grade all cards using LLM (shows cards with score < 10)
```bash
python main.py grade
# or
mochi-cards grade
```

#### Export cards to markdown
```bash
python main.py dump --output cards.md
# or
mochi-cards dump --output cards.md
```

If no output file is specified, defaults to `mochi_cards.md`.

#### Upload cards from markdown
```bash
python main.py upload --input cards.md
# or
mochi-cards upload --input cards.md
```

Cards with valid `card_id` in frontmatter will be updated; cards with `card_id: null` will be created as new cards.

### Python API

You can also import and use the functions directly in your Python code:

```python
from main import (
    get_decks,
    get_cards,
    create_card,
    update_card,
    delete_card,
    grade_all_cards,
    dump_cards_to_markdown,
    upload_cards_from_markdown
)

# Get all decks
decks = get_decks()

# Get cards from a specific deck
cards = get_cards(deck_id)

# Create a new card
card = create_card(
    deck_id,
    content="What is Python?\n---\nPython is a high-level programming language."
)

# Update a card
update_card(card['id'], content="Updated content here")

# Delete a card
delete_card(card['id'])

# Grade all cards in a deck
imperfect_cards, all_results = grade_all_cards(deck_id)

# Export cards to markdown
dump_cards_to_markdown(deck_id, "my_cards.md")

# Upload cards from markdown
created_ids, updated_ids = upload_cards_from_markdown(deck_id, "my_cards.md")
```

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
- `**kwargs`: Optional fields like `template-id`, `review-reverse?`, `pos`, `manual-tags`, `fields`

**Returns:** Created card data

**Example:**
```python
card = create_card(
    deck_id,
    "What is recursion?\n---\nA programming technique where a function calls itself."
)
```

### `update_card(card_id, **kwargs)`
Updates an existing card.

**Parameters:**
- `card_id` (str): ID of the card to update
- `**kwargs`: Fields to update (e.g., `content`, `deck-id`, `archived?`, `trashed?`)

**Returns:** Updated card data

### `delete_card(card_id)`
Deletes a card.

**Parameters:**
- `card_id` (str): ID of the card to delete

**Returns:** `True` if successful

### `grade_all_cards(deck_id, batch_size=20)`
Grades all cards in a deck using AI, batching requests to minimize API calls.

**Parameters:**
- `deck_id` (str): Deck ID to grade cards from
- `batch_size` (int): Number of cards per API request (default: 20)

**Returns:** Tuple of `(imperfect_cards, all_results)`
- `imperfect_cards`: List of tuples `(card, score, justification)` for cards scoring < 10
- `all_results`: List of all grading results

**Grading Scale:**
- 10: Perfect answer, completely accurate
- 7-9: Mostly correct with minor issues
- 4-6: Partially correct but missing key information
- 0-3: Incorrect or severely incomplete

### `dump_cards_to_markdown(deck_id, output_file="mochi_cards.md")`
Exports all cards from a deck to a markdown file in compact format.

**Parameters:**
- `deck_id` (str): Deck ID to export cards from
- `output_file` (str): Output markdown file path (default: "mochi_cards.md")

**Returns:** Number of cards exported

**Format:** Cards are exported with `card_id` in frontmatter, all sections separated by `---`

### `upload_cards_from_markdown(deck_id, input_file)`
Imports cards from a markdown file. Cards with `card_id` frontmatter will be updated; cards without will be created.

**Parameters:**
- `deck_id` (str): Deck ID to add cards to
- `input_file` (str): Path to markdown file

**Returns:** Tuple of `(created_ids, updated_ids)`
- `created_ids`: List of IDs for newly created cards
- `updated_ids`: List of IDs for updated cards

**Example workflow:**
```python
# Export cards to markdown
dump_cards_to_markdown(deck_id, "cards.md")

# Edit the file (fix typos, improve answers, add new cards)
# Then re-import - existing cards are updated, new ones are created
created_ids, updated_ids = upload_cards_from_markdown(deck_id, "cards.md")
print(f"Created {len(created_ids)} cards, updated {len(updated_ids)} cards")
```

## Card Format

### Internal Format (API)
Cards in the Mochi API use markdown content separated by `---`:

```
Question text here
---
Answer text here
```

**Example:**
```
What is the time complexity of binary search?
---
O(log n) - logarithmic time complexity
```

### Markdown Export/Import Format
Exported markdown files use a compact format with `---` separators:

```markdown
---
card_id: abc123xyz
---
What is the time complexity of binary search?
---
O(log n) - logarithmic time complexity
---
card_id: def456ghi
---
What is a hash table?
---
A data structure that maps keys to values using a hash function.
```

**Format:**
- `---` separates all sections
- Every card has frontmatter with `card_id:`
- Exported cards have their actual card IDs
- To add new cards manually, use `card_id: null`
- Cards with valid IDs will be **updated** when uploaded
- Cards with `card_id: null` will be **created** as new cards

**Example with mixed create/update:**
```markdown
---
card_id: existing_id
---
Updated question?
---
Updated answer
---
card_id: null
---
New question without ID?
---
New answer (will be created)
```

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
```

See [TESTING.md](TESTING.md) for detailed testing documentation.

### Test Coverage

- **17 unit tests** - Mocked tests for utilities, parsing, and CLI
- **3 integration tests** - Live API tests (require `TEST_DECK_ID` environment variable)

Unit tests cover:
- Card parsing (question/answer separation)
- Deck finding utilities (legacy support)
- LLM grading response parsing
- Markdown export/import
- CLI argument parsing

## Notes

- All operations work on the single deck specified by `DECK_ID` in your `.env` file.
- The grading feature uses OpenRouter's Gemini 2.5 Flash model for evaluation.
- Card fetching handles pagination automatically, but there's a known API pagination bug that may cause premature termination with a 500 error after retrieving many cards. The script handles this gracefully.

## License

See [LICENSE](LICENSE) file for details.

## Author

tsilva
