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
        'MOCHI_API_KEY': 'test_api_key',
        'OPENROUTER_API_KEY': 'test_openrouter_key',
        'DECK_ID': 'test_deck_id'
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


class TestGrading:
    """Test LLM grading functionality."""

    @pytest.fixture
    def mock_openrouter_response(self):
        """Mock OpenRouter API response."""
        return {
            "choices": [{
                "message": {
                    "content": '[{"card_id": "card1", "score": 10, "justification": "Perfect"}]'
                }
            }]
        }

    def test_grade_cards_batch_mock(self, sample_cards, mock_openrouter_response, mock_env):
        """Test grading with mocked API response."""
        with patch('requests.post') as mock_post:
            mock_post.return_value.json.return_value = mock_openrouter_response
            mock_post.return_value.raise_for_status = Mock()

            results = main.grade_cards_batch(sample_cards[:1])
            assert len(results) == 1
            assert results[0][1] == 10  # score
            assert results[0][2] == "Perfect"  # justification

    def test_grade_cards_batch_wrapped_response(self, sample_cards, mock_env):
        """Test grading with wrapped JSON response."""
        wrapped_response = {
            "choices": [{
                "message": {
                    "content": '{"grades": [{"card_id": "card1", "score": 8, "justification": "Good"}]}'
                }
            }]
        }

        with patch('requests.post') as mock_post:
            mock_post.return_value.json.return_value = wrapped_response
            mock_post.return_value.raise_for_status = Mock()

            results = main.grade_cards_batch(sample_cards[:1])
            assert len(results) == 1
            assert results[0][1] == 8


class TestMarkdownExport:
    """Test markdown export functionality."""

    def test_dump_cards_to_markdown(self, sample_cards, tmp_path):
        """Test exporting cards to markdown file."""
        output_file = tmp_path / "test_export.md"

        with patch('main.get_cards', return_value=sample_cards):
            count = main.dump_cards_to_markdown('deck1', str(output_file))

        assert count == 2
        assert output_file.exists()

        content = output_file.read_text()
        assert "# Mochi Cards Export" in content
        assert "Total cards: 2" in content
        assert "card_id: card1" in content
        assert "card_id: card2" in content
        assert "What is Python?" in content
        assert "A programming language" in content
        assert "What is ML?" in content

    def test_upload_cards_from_markdown_compact_format(self, tmp_path):
        """Test uploading cards with compact format."""
        input_file = tmp_path / "test_upload.md"
        input_file.write_text("""# Test Cards

---
card_id: existing123
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

        with patch('main.create_card') as mock_create, \
             patch('main.update_card') as mock_update:
            mock_create.return_value = {'id': 'new456'}

            created, updated = main.upload_cards_from_markdown('deck1', str(input_file))

        assert len(updated) == 1
        assert updated[0] == 'existing123'
        assert len(created) == 1
        assert created[0] == 'new456'

        # Verify update was called with correct content
        mock_update.assert_called_once()
        assert mock_update.call_args[0][0] == 'existing123'
        assert 'What is Python?' in mock_update.call_args[1]['content']

        # Verify create was called with correct content
        mock_create.assert_called_once()
        assert 'What is ML?' in mock_create.call_args[0][1]


class TestCLI:
    """Test CLI argument parsing."""

    def test_parse_args_list(self):
        """Test list command parsing."""
        with patch('sys.argv', ['main.py', 'list']):
            args = main.parse_args()
            assert args.command == 'list'

    def test_parse_args_grade_with_batch_size(self):
        """Test grade command with batch size."""
        with patch('sys.argv', ['main.py', 'grade', '--batch-size', '10']):
            args = main.parse_args()
            assert args.command == 'grade'
            assert args.batch_size == 10

    def test_parse_args_dump_with_output(self):
        """Test dump command with output file."""
        with patch('sys.argv', ['main.py', 'dump', '--output', 'cards.md']):
            args = main.parse_args()
            assert args.command == 'dump'
            assert args.output == 'cards.md'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
