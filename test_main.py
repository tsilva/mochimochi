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

    def test_grade_cards_batch_missing_grades(self, sample_cards, mock_env):
        """Test grading when LLM doesn't return all grades."""
        # LLM only returns grade for card1, not card2
        partial_response = {
            "choices": [{
                "message": {
                    "content": '[{"card_id": "card1", "score": 10, "justification": "Perfect"}]'
                }
            }]
        }

        with patch('requests.post') as mock_post, \
             patch('builtins.print'):  # Suppress warning output
            mock_post.return_value.json.return_value = partial_response
            mock_post.return_value.raise_for_status = Mock()

            results = main.grade_cards_batch(sample_cards)  # 2 cards
            # Should only return result for card1
            assert len(results) == 1
            assert results[0][0]['id'] == 'card1'
            assert results[0][1] == 10


class TestCLI:
    """Test CLI argument parsing."""

    def test_parse_args_grade_with_batch_size(self):
        """Test grade command with batch size."""
        with patch('sys.argv', ['main.py', 'grade', '--batch-size', '10']):
            args = main.parse_args()
            assert args.command == 'grade'
            assert args.batch_size == 10

    def test_parse_args_pull(self):
        """Test pull command parsing."""
        with patch('sys.argv', ['main.py', 'pull']):
            args = main.parse_args()
            assert args.command == 'pull'

    def test_parse_args_push_with_force(self):
        """Test push command with force flag."""
        with patch('sys.argv', ['main.py', 'push', '--force']):
            args = main.parse_args()
            assert args.command == 'push'
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


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
