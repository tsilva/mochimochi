#!/usr/bin/env python3
"""Mochi flashcard management script.

Usage:
    python main.py list                    # List all cards in a deck
    python main.py test                    # Test create/update/delete operations
    python main.py grade                   # Grade all cards using LLM
    python main.py dump                    # Dump all cards to markdown file
    python main.py decks                   # List all available decks

API Functions:
    get_decks()                         # List all decks
    get_cards(deck_id, limit=100)       # Get all cards in a deck
    create_card(deck_id, content, **kwargs)  # Create a new card
    update_card(card_id, **kwargs)      # Update an existing card
    delete_card(card_id)                # Delete a card
    grade_all_cards(deck_id, batch_size=20)  # Grade cards using LLM
    dump_cards_to_markdown(deck_id, output_file)  # Export cards to markdown

Example:
    from main import create_card, update_card, delete_card, grade_all_cards

    # Create a card
    card = create_card(deck_id, "What is X?\n---\nX is Y")

    # Update a card
    update_card(card['id'], content="Updated content")

    # Delete a card
    delete_card(card['id'])

    # Grade cards
    imperfect_cards, all_results = grade_all_cards(deck_id)
"""

import argparse
import json
import os
import sys
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
API_KEY = os.getenv("MOCHI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not API_KEY:
    raise ValueError("MOCHI_API_KEY not found in .env file")

BASE_URL = "https://app.mochi.cards/api"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def get_decks():
    """Fetch all decks."""
    response = requests.get(
        f"{BASE_URL}/decks/",
        auth=(API_KEY, ""),
        timeout=30
    )
    response.raise_for_status()
    data = response.json()
    return data["docs"]


def create_card(deck_id, content, **kwargs):
    """Create a new card.

    Args:
        deck_id: Deck ID to add the card to
        content: Markdown content of the card
        **kwargs: Optional fields like template-id, review-reverse?, pos, manual-tags, fields

    Returns:
        Created card data
    """
    data = {
        "content": content,
        "deck-id": deck_id,
        **kwargs
    }

    response = requests.post(
        f"{BASE_URL}/cards/",
        auth=(API_KEY, ""),
        json=data,
        timeout=30
    )
    response.raise_for_status()
    return response.json()


def update_card(card_id, **kwargs):
    """Update an existing card.

    Args:
        card_id: ID of the card to update
        **kwargs: Fields to update (content, deck-id, archived?, trashed?, etc.)

    Returns:
        Updated card data
    """
    response = requests.post(
        f"{BASE_URL}/cards/{card_id}",
        auth=(API_KEY, ""),
        json=kwargs,
        timeout=30
    )
    response.raise_for_status()
    return response.json()


def delete_card(card_id):
    """Delete a card.

    Args:
        card_id: ID of the card to delete

    Returns:
        True if successful
    """
    response = requests.delete(
        f"{BASE_URL}/cards/{card_id}",
        auth=(API_KEY, ""),
        timeout=30
    )
    response.raise_for_status()
    return True


def grade_cards_batch(cards_batch):
    """Grade a batch of cards using OpenRouter's Gemini 2.5 Flash.

    Args:
        cards_batch: List of card objects to grade

    Returns:
        List of tuples: (card, score, justification)
    """
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not found in .env file")

    # Build the prompt with all cards
    prompt = """You are grading flashcards for accuracy. For each card below, evaluate if the answer is correct and complete.

Score each card from 0-10:
- 10: Perfect answer, completely accurate
- 7-9: Mostly correct with minor issues
- 4-6: Partially correct but missing key information
- 0-3: Incorrect or severely incomplete

Format your response as JSON array:
[
  {"card_id": "id1", "score": 10, "justification": "explanation"},
  {"card_id": "id2", "score": 8, "justification": "explanation"}
]

Cards to grade:
"""

    for i, card in enumerate(cards_batch, 1):
        content = card.get('content', '')
        # Split on --- to get question and answer
        parts = content.split('---', 1)
        question = parts[0].strip() if len(parts) > 0 else ''
        answer = parts[1].strip() if len(parts) > 1 else ''

        prompt += f"\n{i}. Card ID: {card['id']}\n"
        prompt += f"   Question: {question}\n"
        prompt += f"   Answer: {answer}\n"

    # Call OpenRouter API
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "google/gemini-2.5-flash",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"}
    }

    response = requests.post(
        OPENROUTER_URL,
        headers=headers,
        json=data,
        timeout=60
    )
    response.raise_for_status()

    result = response.json()
    content = result["choices"][0]["message"]["content"]

    # Parse JSON response
    try:
        grades = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        print(f"Response content: {content[:500]}")
        raise

    # Handle both array and object with array
    if isinstance(grades, dict) and 'grades' in grades:
        grades = grades['grades']
    elif isinstance(grades, dict) and 'cards' in grades:
        grades = grades['cards']
    elif isinstance(grades, list):
        pass  # Already a list
    else:
        # Try to extract array from any key
        for key in grades.keys():
            if isinstance(grades[key], list):
                grades = grades[key]
                break

    # Match grades with cards
    results = []
    grade_map = {g['card_id']: (g['score'], g['justification']) for g in grades}

    for card in cards_batch:
        card_id = card['id']
        if card_id in grade_map:
            score, justification = grade_map[card_id]
            results.append((card, score, justification))
        else:
            # Card wasn't graded - add warning
            print(f"Warning: Card {card_id} was not graded by the LLM")

    return results


def grade_all_cards(deck_id, batch_size=20):
    """Grade all cards in a deck, batching requests to minimize API calls.

    Args:
        deck_id: Deck ID to grade cards from
        batch_size: Number of cards per API request (default: 20)

    Returns:
        List of tuples: (card, score, justification) for cards scoring < 10
    """
    print("\nFetching cards to grade...")
    cards = get_cards(deck_id)
    total_cards = len(cards)

    print(f"Grading {total_cards} cards in batches of {batch_size}...")

    all_results = []
    for i in range(0, total_cards, batch_size):
        batch = cards[i:i+batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_cards + batch_size - 1) // batch_size

        print(f"  Processing batch {batch_num}/{total_batches} ({len(batch)} cards)...", flush=True)

        try:
            results = grade_cards_batch(batch)
            all_results.extend(results)
        except Exception as e:
            print(f"  Error grading batch {batch_num}: {e}")
            continue

    # Filter cards with score < 10
    imperfect_cards = [(card, score, justification)
                       for card, score, justification in all_results
                       if score < 10]

    return imperfect_cards, all_results


def get_cards(deck_id, limit=100):
    """Fetch all cards for a given deck."""
    cards = []
    bookmark = None

    while True:
        params = {"deck-id": deck_id, "limit": limit}
        if bookmark:
            params["bookmark"] = bookmark

        try:
            response = requests.get(
                f"{BASE_URL}/cards/",
                auth=(API_KEY, ""),
                params=params,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            batch_size = len(data["docs"])
            if batch_size == 0:
                # No more cards to fetch
                break

            cards.extend(data["docs"])

            bookmark = data.get("bookmark")
            if not bookmark:
                break
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 500 and len(cards) > 0:
                # API pagination bug - return what we have
                print(f"Note: API error on pagination, showing {len(cards)} cards retrieved\n")
                break
            raise

    return cards


def test_card_operations(deck_id):
    """Test create, update, and delete operations with a temporary card."""
    print("\n" + "=" * 80)
    print("TESTING CARD OPERATIONS (creating temporary test card)")
    print("=" * 80)

    # Create a test card
    print("\n1. Creating test card...")
    test_content = """What is a **test card**?
---
This is a temporary test card created by the API. It will be deleted shortly."""

    created_card = create_card(deck_id, test_content)
    card_id = created_card["id"]
    print(f"   ✓ Created card with ID: {card_id}")
    print(f"   Content: {test_content.split('---')[0].strip()}")

    # Update the card
    print("\n2. Updating test card...")
    updated_content = """What is an **updated test card**?
---
This card has been updated via the API. It will be deleted shortly."""

    update_card(card_id, content=updated_content)
    print(f"   ✓ Updated card {card_id}")
    print(f"   New content: {updated_content.split('---')[0].strip()}")

    # Delete the card
    print("\n3. Deleting test card...")
    delete_card(card_id)
    print(f"   ✓ Deleted card {card_id}")

    print("\n" + "=" * 80)
    print("TEST COMPLETED SUCCESSFULLY")
    print("=" * 80)


def list_cards(deck_id, deck_name):
    """List all cards in a deck."""
    print(f"Found deck: {deck_name}\n")
    print("Fetching cards...")
    cards = get_cards(deck_id)

    print(f"\nTotal cards: {len(cards)}")
    print("=" * 80)

    for i, card in enumerate(cards, 1):
        print(f"\nCard {i}:")
        print(f"ID: {card['id']}")
        content = card.get('content', '')
        if len(content) > 200:
            print(f"Content:\n{content[:200]}...")
        else:
            print(f"Content:\n{content}")
        print("-" * 80)


def dump_cards_to_markdown(deck_id, output_file="mochi_cards.md"):
    """Dump all cards to a markdown file.

    Args:
        deck_id: Deck ID to export cards from
        output_file: Output markdown file path (default: mochi_cards.md)

    Returns:
        Number of cards exported
    """
    print("Fetching cards...")
    cards = get_cards(deck_id)

    print(f"Exporting {len(cards)} cards to {output_file}...")

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# Mochi Cards Export\n\n")
        f.write(f"Total cards: {len(cards)}\n\n")
        f.write("---\n\n")

        for i, card in enumerate(cards, 1):
            content = card.get('content', '')
            parts = content.split('---', 1)
            question = parts[0].strip() if len(parts) > 0 else ''
            answer = parts[1].strip() if len(parts) > 1 else ''

            # Write card with heading
            f.write(f"## Card {i}\n\n")
            f.write(f"<!-- Card ID: {card['id']} -->\n\n")

            # Write question
            f.write(f"**Question:**\n\n{question}\n\n")

            # Write answer
            f.write(f"**Answer:**\n\n{answer}\n\n")

            f.write("---\n\n")

    print(f"✓ Exported {len(cards)} cards to {output_file}")
    return len(cards)


def display_grading_results(imperfect_cards, all_results):
    """Display grading results."""
    print("\n" + "=" * 80)
    print("GRADING RESULTS")
    print("=" * 80)

    total_graded = len(all_results)
    perfect_count = total_graded - len(imperfect_cards)

    print(f"\nTotal cards graded: {total_graded}")
    print(f"Perfect scores (10/10): {perfect_count}")
    print(f"Cards needing review (< 10): {len(imperfect_cards)}")

    if imperfect_cards:
        print("\n" + "=" * 80)
        print("CARDS NEEDING REVIEW")
        print("=" * 80)

        # Sort by score (lowest first)
        imperfect_cards.sort(key=lambda x: x[1])

        for i, (card, score, justification) in enumerate(imperfect_cards, 1):
            content = card.get('content', '')
            parts = content.split('---', 1)
            question = parts[0].strip() if len(parts) > 0 else ''
            answer = parts[1].strip() if len(parts) > 1 else ''

            print(f"\n{i}. Score: {score}/10")
            print(f"   Card ID: {card['id']}")
            print(f"   Question: {question[:100]}{'...' if len(question) > 100 else ''}")
            print(f"   Answer: {answer[:150]}{'...' if len(answer) > 150 else ''}")
            print(f"   Issue: {justification}")
            print("-" * 80)
    else:
        print("\n🎉 All cards are perfect!")


def find_deck(decks, deck_name=None, deck_id=None):
    """Find a deck by name or ID.
    
    Args:
        decks: List of deck dictionaries
        deck_name: Name of the deck to find (partial match supported)
        deck_id: ID of the deck to find
        
    Returns:
        Deck dictionary or None
    """
    if deck_id:
        for deck in decks:
            if deck['id'] == deck_id:
                return deck
        return None
    
    if deck_name:
        # Try exact match first
        for deck in decks:
            if deck['name'] == deck_name:
                return deck
        
        # Try partial match
        for deck in decks:
            if deck_name.lower() in deck['name'].lower():
                return deck
        
        return None
    
    # Default: look for AI/ML deck
    for deck in decks:
        if "AI/ML" in deck["name"] or "AIML" in deck["name"]:
            return deck
    
    return None


def list_decks_command():
    """List all available decks."""
    print("Fetching decks...")
    decks = get_decks()
    
    print(f"\nAvailable decks ({len(decks)}):")
    print("=" * 80)
    for deck in decks:
        print(f"  {deck['name']}")
        print(f"    ID: {deck['id']}")
        print("-" * 80)


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Mochi flashcard management script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list                           # List cards in default deck (AI/ML)
  %(prog)s list --deck-name "My Deck"     # List cards in specific deck
  %(prog)s list --deck-id "abc123"        # List cards by deck ID
  %(prog)s test                           # Test card operations
  %(prog)s grade --batch-size 10          # Grade cards with custom batch size
  %(prog)s dump --output cards.md         # Export cards to markdown
  %(prog)s decks                          # List all available decks
        """
    )
    
    parser.add_argument(
        "--deck-name",
        help="Deck name to use (partial match supported)"
    )
    parser.add_argument(
        "--deck-id",
        help="Deck ID to use"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List all cards in a deck")
    
    # Test command
    test_parser = subparsers.add_parser("test", help="Test create/update/delete operations")
    
    # Grade command
    grade_parser = subparsers.add_parser("grade", help="Grade all cards using LLM")
    grade_parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Number of cards per batch (default: 20)"
    )
    
    # Dump command
    dump_parser = subparsers.add_parser("dump", help="Export cards to markdown file")
    dump_parser.add_argument(
        "--output",
        "-o",
        default="mochi_cards.md",
        help="Output markdown file (default: mochi_cards.md)"
    )
    
    # Decks command
    subparsers.add_parser("decks", help="List all available decks")
    
    return parser.parse_args()


def main():
    args = parse_args()
    
    # Handle decks command (doesn't need deck selection)
    if args.command == "decks":
        list_decks_command()
        return
    
    # For other commands, we need to find a deck
    print("Fetching decks...")
    decks = get_decks()
    
    deck = find_deck(decks, deck_name=args.deck_name, deck_id=args.deck_id)
    
    if not deck:
        print("\nAvailable decks:")
        for d in decks:
            print(f"  - {d['name']} (id: {d['id']})")
        
        if args.deck_name or args.deck_id:
            print(f"\nDeck not found.")
            if args.deck_name:
                print(f"  Searched for name: {args.deck_name}")
            if args.deck_id:
                print(f"  Searched for ID: {args.deck_id}")
        else:
            print("\nNo 'AI/ML' deck found. Please specify --deck-name or --deck-id")
        sys.exit(1)
    
    # Execute the requested command
    if args.command == "list" or args.command is None:
        list_cards(deck["id"], deck["name"])
    elif args.command == "test":
        test_card_operations(deck["id"])
    elif args.command == "grade":
        imperfect_cards, all_results = grade_all_cards(deck["id"], batch_size=args.batch_size)
        display_grading_results(imperfect_cards, all_results)
    elif args.command == "dump":
        dump_cards_to_markdown(deck["id"], args.output)
    else:
        print(f"Unknown command: {args.command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
