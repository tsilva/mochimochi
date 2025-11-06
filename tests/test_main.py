#!/usr/bin/env python3
"""Test suite for mochi-mochi."""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock
import main


@pytest.fixture
def mock_env():
    """Mock environment variables."""
    with patch.dict(os.environ, {
        'MOCHI_API_KEY': 'test_api_key'
    }):
        yield


@pytest.fixture
def sample_decks():
    """Sample deck data."""
    return [
        {'id': 'deck1', 'name': 'AI/ML Deck'},
        {'id': 'deck2', 'name': 'Python Programming'},
        {'id': 'deck3', 'name': 'General Knowledge'}
    ]


@pytest.fixture
def sample_cards():
    """Sample card data."""
    return [
        {
            'id': 'card1',
            'content': 'What is Python?\n---\nA programming language'
        },
        {
            'id': 'card2',
            'content': 'What is ML?\n---\nMachine Learning'
        }
    ]


class TestParseCard:
    """Test card parsing utility."""

    def test_parse_card_with_separator(self):
        content = "What is Python?\n---\nA programming language"
        question, answer = main.parse_card(content)
        assert question == "What is Python?"
        assert answer == "A programming language"

    def test_parse_card_without_separator(self):
        content = "Just a question"
        question, answer = main.parse_card(content)
        assert question == "Just a question"
        assert answer == ""

    def test_parse_card_empty(self):
        question, answer = main.parse_card("")
        assert question == ""
        assert answer == ""

    def test_parse_card_with_extra_separators(self):
        content = "Question?\n---\nAnswer part 1\n---\nAnswer part 2"
        question, answer = main.parse_card(content)
        assert question == "Question?"
        assert answer == "Answer part 1\n---\nAnswer part 2"


class TestFindDeck:
    """Test deck finding logic."""

    def test_find_deck_by_id(self, sample_decks):
        deck = main.find_deck(sample_decks, deck_id='deck2')
        assert deck['id'] == 'deck2'
        assert deck['name'] == 'Python Programming'

    def test_find_deck_by_exact_name(self, sample_decks):
        deck = main.find_deck(sample_decks, deck_name='Python Programming')
        assert deck['id'] == 'deck2'

    def test_find_deck_by_partial_name(self, sample_decks):
        deck = main.find_deck(sample_decks, deck_name='python')
        assert deck['id'] == 'deck2'

    def test_find_deck_default_aiml(self, sample_decks):
        deck = main.find_deck(sample_decks)
        assert deck['id'] == 'deck1'
        assert 'AI/ML' in deck['name']

    def test_find_deck_not_found(self, sample_decks):
        deck = main.find_deck(sample_decks, deck_name='Nonexistent')
        assert deck is None

    def test_find_deck_id_not_found(self, sample_decks):
        deck = main.find_deck(sample_decks, deck_id='invalid')
        assert deck is None


class TestCRUDOperations:
    """Test CRUD operations against live API."""

    @pytest.fixture
    def test_deck_id(self):
        """Get a test deck ID from environment or skip test."""
        deck_id = os.getenv('TEST_DECK_ID')
        if not deck_id:
            pytest.skip("TEST_DECK_ID not set - skipping live API tests")
        return deck_id

    @pytest.mark.integration
    def test_card_lifecycle(self, test_deck_id):
        """Test create, update, delete card lifecycle."""
        # Create
        test_content = "Test question?\n---\nTest answer"
        card = main.create_card(test_deck_id, test_content)
        assert 'id' in card
        card_id = card['id']

        try:
            # Update
            updated_content = "Updated question?\n---\nUpdated answer"
            updated_card = main.update_card(card_id, content=updated_content)
            assert updated_card['id'] == card_id

            # Delete
            result = main.delete_card(card_id)
            assert result is True
        except Exception as e:
            # Cleanup on failure
            try:
                main.delete_card(card_id)
            except:
                pass
            raise e

    @pytest.mark.integration
    def test_get_decks(self):
        """Test fetching decks from API."""
        decks = main.get_decks()
        assert isinstance(decks, list)
        assert len(decks) > 0
        assert 'id' in decks[0]
        assert 'name' in decks[0]

    @pytest.mark.integration
    def test_get_cards(self, test_deck_id):
        """Test fetching cards from a deck."""
        cards = main.get_cards(test_deck_id, limit=10)
        assert isinstance(cards, list)


class TestCLI:
    """Test CLI argument parsing."""

    def test_parse_args_pull(self):
        """Test pull command parsing."""
        with patch('sys.argv', ['main.py', 'pull', 'abc123']):
            args = main.parse_args()
            assert args.command == 'pull'
            assert args.deck_id == 'abc123'

    def test_parse_args_push_with_force(self):
        """Test push command with force flag."""
        with patch('sys.argv', ['main.py', 'push', 'deck-test-abc123.md', '--force']):
            args = main.parse_args()
            assert args.command == 'push'
            assert args.file_path == 'deck-test-abc123.md'
            assert args.force is True


class TestSyncFunctions:
    """Test sync-related utility functions."""

    def test_content_hash(self):
        """Test content hashing."""
        q1, a1 = "What is Python?", "A programming language"
        q2, a2 = "What is Python?", "A programming language"
        q3, a3 = "What is ML?", "Machine Learning"

        hash1 = main.content_hash(q1, a1)
        hash2 = main.content_hash(q2, a2)
        hash3 = main.content_hash(q3, a3)

        assert hash1 == hash2  # Same content = same hash
        assert hash1 != hash3  # Different content = different hash
        assert len(hash1) == 16  # Hash should be 16 chars

    def test_parse_markdown_cards(self):
        """Test parsing markdown cards with frontmatter."""
        markdown = """# Test Cards

---
card_id: abc123
tags: ["python", "basics"]
archived: false
---
What is Python?
---
A programming language
---
card_id: null
---
What is ML?
---
Machine Learning
"""
        cards = main.parse_markdown_cards(markdown)

        assert len(cards) == 2

        # First card with ID
        assert cards[0]['card_id'] == 'abc123'
        assert cards[0]['question'] == 'What is Python?'
        assert cards[0]['answer'] == 'A programming language'
        assert cards[0]['tags'] == ['python', 'basics']
        assert cards[0]['archived'] is False

        # Second card without ID
        assert cards[1]['card_id'] is None
        assert cards[1]['question'] == 'What is ML?'
        assert cards[1]['answer'] == 'Machine Learning'

    def test_format_card_to_markdown(self):
        """Test formatting card dict to markdown."""
        card = {
            'card_id': 'abc123',
            'question': 'What is Python?',
            'answer': 'A programming language',
            'tags': ['python', 'basics'],
            'archived': False
        }

        markdown = main.format_card_to_markdown(card)

        assert 'card_id: abc123' in markdown
        assert 'tags: ["python", "basics"]' in markdown
        assert 'What is Python?' in markdown
        assert 'A programming language' in markdown
        assert 'archived' not in markdown  # Should not include if False

    def test_format_card_to_markdown_archived(self):
        """Test formatting archived card."""
        card = {
            'card_id': 'xyz789',
            'question': 'Old question',
            'answer': 'Old answer',
            'tags': [],
            'archived': True
        }

        markdown = main.format_card_to_markdown(card)

        assert 'card_id: xyz789' in markdown
        assert 'archived: true' in markdown
        assert 'Old question' in markdown


class TestValidation:
    """Test deck file validation."""

    def test_validate_deck_file_valid(self, tmp_path):
        """Test validating a valid deck file."""
        deck_file = tmp_path / "deck-test-Abc12345.md"
        deck_file.write_text("""---
card_id: card1
tags: ["python"]
---
What is Python?
---
A programming language
---
card_id: null
---
What is ML?
---
Machine Learning
""")

        cards, deck_id = main.validate_deck_file(deck_file)
        assert len(cards) == 2
        assert cards[0]['question'] == 'What is Python?'
        assert cards[1]['question'] == 'What is ML?'
        assert deck_id == 'Abc12345'

    def test_validate_deck_file_not_found(self, tmp_path):
        """Test validation fails for non-existent file."""
        deck_file = tmp_path / "deck-nonexistent-abc123.md"

        with pytest.raises(FileNotFoundError) as exc_info:
            main.validate_deck_file(deck_file)
        assert "not found" in str(exc_info.value)

    def test_validate_deck_file_empty(self, tmp_path):
        """Test validation fails for empty file."""
        deck_file = tmp_path / "deck-empty-abc123.md"
        deck_file.write_text("")

        with pytest.raises(ValueError) as exc_info:
            main.validate_deck_file(deck_file)
        assert "empty" in str(exc_info.value).lower()

    def test_validate_deck_file_invalid_filename(self, tmp_path):
        """Test validation fails for invalid filename format."""
        deck_file = tmp_path / "invalid.md"
        deck_file.write_text("""---
card_id: card1
---
Question?
---
Answer
""")

        with pytest.raises(ValueError) as exc_info:
            main.validate_deck_file(deck_file)
        assert "filename format" in str(exc_info.value).lower()

    def test_validate_deck_file_no_cards(self, tmp_path):
        """Test validation fails when no cards found."""
        deck_file = tmp_path / "deck-nocards-abc123.md"
        deck_file.write_text("# Just a header\n\nSome text but no cards")

        with pytest.raises(ValueError) as exc_info:
            main.validate_deck_file(deck_file)
        assert "no cards" in str(exc_info.value).lower()

    def test_validate_deck_file_empty_question(self, tmp_path):
        """Test validation fails for card with empty question."""
        deck_file = tmp_path / "deck-badcard-abc123.md"
        deck_file.write_text("""---
card_id: card1
---

---
This has an answer but no question
""")

        # Parsing may fail to create cards with empty question, resulting in "no cards"
        with pytest.raises(ValueError) as exc_info:
            main.validate_deck_file(deck_file)
        # Accept either "no cards" or "empty question" error
        error_msg = str(exc_info.value).lower()
        assert "no cards" in error_msg or "empty question" in error_msg

    def test_validate_deck_file_empty_answer(self, tmp_path):
        """Test validation fails for card with empty answer."""
        deck_file = tmp_path / "deck-badcard-abc123.md"
        deck_file.write_text("""---
card_id: card1
---
This has a question
---

""")

        # Parsing may fail to create cards with empty answer, resulting in "no cards"
        with pytest.raises(ValueError) as exc_info:
            main.validate_deck_file(deck_file)
        # Accept either "no cards" or "empty answer" error
        error_msg = str(exc_info.value).lower()
        assert "no cards" in error_msg or "empty answer" in error_msg

    def test_validate_deck_file_whitespace_only(self, tmp_path):
        """Test validation fails for whitespace-only content."""
        deck_file = tmp_path / "deck-whitespace-abc123.md"
        deck_file.write_text("   \n\n  \n  ")

        with pytest.raises(ValueError) as exc_info:
            main.validate_deck_file(deck_file)
        assert "empty" in str(exc_info.value).lower()

    def test_validate_deck_file_multiple_cards(self, tmp_path):
        """Test validation succeeds with multiple valid cards."""
        deck_file = tmp_path / "deck-multi-Abc12345.md"
        deck_file.write_text("""---
card_id: card1
tags: ["tag1", "tag2"]
archived: false
---
Question 1?
---
Answer 1
---
card_id: card2
tags: []
---
Question 2?
---
Answer 2
---
card_id: null
---
Question 3?
---
Answer 3
""")

        cards, deck_id = main.validate_deck_file(deck_file)
        assert len(cards) == 3
        assert all('question' in card for card in cards)
        assert all('answer' in card for card in cards)
        assert deck_id == 'Abc12345'

    def test_validate_deck_file_new_deck(self, tmp_path):
        """Test validating a new deck file (without deck ID)."""
        deck_file = tmp_path / "deck-mynewdeck.md"
        deck_file.write_text("""---
card_id: null
tags: ["python"]
---
What is Python?
---
A programming language
---
card_id: null
---
What is ML?
---
Machine Learning
""")

        cards, deck_id = main.validate_deck_file(deck_file)
        assert len(cards) == 2
        assert cards[0]['question'] == 'What is Python?'
        assert cards[1]['question'] == 'What is ML?'
        assert deck_id is None  # New deck has no ID yet


class TestExtractDeckId:
    """Test deck ID extraction from filenames."""

    def test_extract_deck_id_valid(self, tmp_path):
        """Test extracting deck ID from valid filename."""
        deck_file = tmp_path / "deck-mytest-Abc12345.md"
        deck_file.touch()
        deck_id = main.extract_deck_id_from_filename(deck_file)
        assert deck_id == 'Abc12345'

    def test_extract_deck_id_new_deck(self, tmp_path):
        """Test extracting deck ID from new deck filename (no ID)."""
        deck_file = tmp_path / "deck-mynewdeck.md"
        deck_file.touch()
        deck_id = main.extract_deck_id_from_filename(deck_file)
        assert deck_id is None

    def test_extract_deck_id_hyphenated_name(self, tmp_path):
        """Test extracting deck ID from filename with hyphens in name."""
        deck_file = tmp_path / "deck-my-cool-deck-Xyz78901.md"
        deck_file.touch()
        deck_id = main.extract_deck_id_from_filename(deck_file)
        assert deck_id == 'Xyz78901'

    def test_extract_deck_id_invalid_no_prefix(self, tmp_path):
        """Test error for filename without deck- prefix."""
        deck_file = tmp_path / "mytest-abc123.md"
        deck_file.touch()
        with pytest.raises(ValueError) as exc_info:
            main.extract_deck_id_from_filename(deck_file)
        assert "Expected: deck-" in str(exc_info.value)

    def test_extract_deck_id_invalid_just_deck(self, tmp_path):
        """Test error for filename that is just 'deck-.md'."""
        deck_file = tmp_path / "deck-.md"
        deck_file.touch()
        with pytest.raises(ValueError) as exc_info:
            main.extract_deck_id_from_filename(deck_file)
        assert "Expected: deck-" in str(exc_info.value)

    def test_extract_deck_id_multi_hyphen_new_deck(self, tmp_path):
        """Test multi-hyphenated name without valid deck ID is treated as new deck."""
        deck_file = tmp_path / "deck-aiml-fundamentals.md"
        deck_file.touch()
        deck_id = main.extract_deck_id_from_filename(deck_file)
        assert deck_id is None

    def test_extract_deck_id_lowercase_word_new_deck(self, tmp_path):
        """Test 8-letter lowercase word is treated as new deck (not a valid deck ID)."""
        deck_file = tmp_path / "deck-aiml-networks.md"
        deck_file.touch()
        deck_id = main.extract_deck_id_from_filename(deck_file)
        assert deck_id is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
