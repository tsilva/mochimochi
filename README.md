# mochi-mochi

A Python tool for managing and grading Mochi flashcards via the Mochi API. This script provides functionality to list, create, update, delete, and automatically grade flashcards using AI-powered evaluation.

## Features

- 📚 **List Cards**: Fetch and display all cards from your Mochi decks
- ➕ **Create Cards**: Programmatically create new flashcards
- ✏️ **Update Cards**: Modify existing card content
- 🗑️ **Delete Cards**: Remove cards via API
- 🤖 **AI Grading**: Automatically grade flashcards using OpenRouter's Gemini 2.5 Flash LLM
- 📝 **Export to Markdown**: Export all cards to a markdown file for backup or review
- 🧪 **Test Operations**: Built-in test mode to verify API functionality

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

Create a `.env` file in the project root with your API keys:

```env
MOCHI_API_KEY=your_mochi_api_key_here
OPENROUTER_API_KEY=your_openrouter_api_key_here
```

**Note**: The `OPENROUTER_API_KEY` is only required if you want to use the AI grading feature.

### Getting API Keys

- **Mochi API Key**: Obtain from your Mochi account settings
- **OpenRouter API Key**: Sign up at [OpenRouter](https://openrouter.ai/) to get an API key

## Usage

### Command Line Interface

The script can be run directly or via the installed `mochi-cards` command:

#### List all cards in AI/ML deck
```bash
python list_mochi_cards.py
# or
mochi-cards
```

#### Test create/update/delete operations
```bash
python list_mochi_cards.py test
# or
mochi-cards test
```

#### Grade all cards using LLM (shows cards with score < 10)
```bash
python list_mochi_cards.py grade
# or
mochi-cards grade
```

#### Export cards to markdown
```bash
python list_mochi_cards.py dump [output_file.md]
# or
mochi-cards dump [output_file.md]
```

If no output file is specified, defaults to `mochi_cards.md`.

### Python API

You can also import and use the functions directly in your Python code:

```python
from list_mochi_cards import (
    get_decks,
    get_cards,
    create_card,
    update_card,
    delete_card,
    grade_all_cards,
    dump_cards_to_markdown
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
Exports all cards from a deck to a markdown file.

**Parameters:**
- `deck_id` (str): Deck ID to export cards from
- `output_file` (str): Output markdown file path (default: "mochi_cards.md")

**Returns:** Number of cards exported

## Card Format

Cards should be formatted with markdown content separated by `---`:

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

## Notes

- The main script automatically looks for a deck containing "AI/ML" in the name. If you need to work with a different deck, modify the `main()` function or use the API functions directly.
- The grading feature uses OpenRouter's Gemini 2.5 Flash model for evaluation.
- Card fetching handles pagination automatically, but there's a known API pagination bug that may cause premature termination with a 500 error after retrieving many cards. The script handles this gracefully.

## License

See [LICENSE](LICENSE) file for details.

## Author

tsilva
