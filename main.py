#!/usr/bin/env python3
"""Mochi flashcard management script.

Example usage:
    from main import create_card, update_card, delete_card, grade_all_cards
    card = create_card(deck_id, "What is X?\n---\nX is Y")
    update_card(card['id'], content="Updated")
    delete_card(card['id'])
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


def parse_card(content):
    """Parse card content into question and answer."""
    q, _, a = content.partition('---')
    return q.strip(), a.strip()


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
        question, answer = parse_card(card.get('content', ''))
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

    try:
        grades = json.loads(content)
        if isinstance(grades, dict):
            grades = next((v for v in grades.values() if isinstance(v, list)), [])
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}\nResponse: {content[:500]}")
        raise

    grade_map = {g['card_id']: (g['score'], g['justification']) for g in grades}
    results = []
    for card in cards_batch:
        if card['id'] in grade_map:
            results.append((card, *grade_map[card['id']]))
        else:
            print(f"Warning: Card {card['id']} was not graded by the LLM")
    return results


def batched_cards(deck_id, batch_size=20):
    """Iterator that yields batches of cards from a deck.

    Similar to ML data loaders with shuffling turned off.

    Args:
        deck_id: Deck ID to fetch cards from
        batch_size: Number of cards per batch (default: 20)

    Yields:
        Tuples of (batch, batch_num, total_batches) where batch is a list of cards
    """
    cards = get_cards(deck_id)
    total_cards = len(cards)
    total_batches = (total_cards + batch_size - 1) // batch_size

    for i in range(0, total_cards, batch_size):
        batch = cards[i:i+batch_size]
        batch_num = (i // batch_size) + 1
        yield batch, batch_num, total_batches


def grade_all_cards(deck_id, batch_size=20):
    """Grade all cards in a deck, batching requests to minimize API calls.

    Args:
        deck_id: Deck ID to grade cards from
        batch_size: Number of cards per API request (default: 20)

    Returns:
        List of tuples: (card, score, justification) for cards scoring < 10
    """
    print("\nFetching cards to grade...")
    all_results = []

    for batch, batch_num, total_batches in batched_cards(deck_id, batch_size):
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


def list_cards(deck_id, deck_name):
    """List all cards in a deck."""
    print(f"Found deck: {deck_name}\nFetching cards...")
    cards = get_cards(deck_id)
    print(f"\nTotal cards: {len(cards)}\n" + "=" * 60)

    for i, card in enumerate(cards, 1):
        content = card.get('content', '')
        truncated = content[:200] + '...' if len(content) > 200 else content
        print(f"\nCard {i} (ID: {card['id']}):\n{truncated}\n" + "-" * 60)


def dump_cards_to_markdown(deck_id, output_file="mochi_cards.md"):
    """Dump all cards to a markdown file."""
    print("Fetching cards...")
    cards = get_cards(deck_id)
    print(f"Exporting {len(cards)} cards to {output_file}...")

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"# Mochi Cards Export\n\nTotal cards: {len(cards)}\n\n---\n\n")
        for i, card in enumerate(cards, 1):
            question, answer = parse_card(card.get('content', ''))
            f.write(f"## Card {i}\n\n<!-- Card ID: {card['id']} -->\n\n")
            f.write(f"**Question:**\n\n{question}\n\n")
            f.write(f"**Answer:**\n\n{answer}\n\n---\n\n")

    print(f"✓ Exported {len(cards)} cards to {output_file}")
    return len(cards)


def upload_cards_from_markdown(deck_id, input_file):
    """Upload cards from a markdown file.

    Expected markdown format:
    **Question:**

    Question text

    **Answer:**

    Answer text

    ---

    Args:
        deck_id: Deck ID to add cards to
        input_file: Path to markdown file

    Returns:
        List of created card IDs
    """
    print(f"Reading cards from {input_file}...")

    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split by --- separator
    sections = content.split('---')
    created_ids = []

    for i, section in enumerate(sections, 1):
        section = section.strip()
        if not section:
            continue

        # Parse question and answer
        if '**Question:**' not in section or '**Answer:**' not in section:
            print(f"  Skipping section {i}: missing Question/Answer markers")
            continue

        # Extract question
        q_start = section.find('**Question:**') + len('**Question:**')
        q_end = section.find('**Answer:**')
        question = section[q_start:q_end].strip()

        # Extract answer
        a_start = section.find('**Answer:**') + len('**Answer:**')
        answer = section[a_start:].strip()

        if not question or not answer:
            print(f"  Skipping section {i}: empty question or answer")
            continue

        # Create card content in Mochi format
        card_content = f"{question}\n---\n{answer}"

        try:
            print(f"  Creating card {i}...", end=' ', flush=True)
            created_card = create_card(deck_id, card_content)
            created_ids.append(created_card['id'])
            print(f"✓ (ID: {created_card['id']})")
        except Exception as e:
            print(f"✗ Error: {e}")
            continue

    print(f"\n✓ Successfully created {len(created_ids)} cards")
    return created_ids


def display_grading_results(imperfect_cards, all_results):
    """Display grading results."""
    sep = "=" * 60
    print(f"\n{sep}\nGRADING RESULTS\n{sep}")

    total, perfect = len(all_results), len(all_results) - len(imperfect_cards)
    print(f"\nTotal: {total} | Perfect (10/10): {perfect} | Need review: {len(imperfect_cards)}")

    if not imperfect_cards:
        print("\n🎉 All cards are perfect!")
        return

    print(f"\n{sep}\nCARDS NEEDING REVIEW\n{sep}")
    for i, (card, score, justification) in enumerate(sorted(imperfect_cards, key=lambda x: x[1]), 1):
        question, answer = parse_card(card.get('content', ''))
        q_trunc = question[:100] + '...' if len(question) > 100 else question
        a_trunc = answer[:150] + '...' if len(answer) > 150 else answer
        print(f"\n{i}. Score: {score}/10 | ID: {card['id']}")
        print(f"   Q: {q_trunc}")
        print(f"   A: {a_trunc}")
        print(f"   Issue: {justification}")
        print("-" * 60)


def find_deck(decks, deck_name=None, deck_id=None):
    """Find a deck by name or ID (partial match supported)."""
    if deck_id:
        return next((d for d in decks if d['id'] == deck_id), None)
    if deck_name:
        return (next((d for d in decks if d['name'] == deck_name), None) or
                next((d for d in decks if deck_name.lower() in d['name'].lower()), None))
    return next((d for d in decks if "AI/ML" in d["name"] or "AIML" in d["name"]), None)


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Mochi flashcard management")
    parser.add_argument("--deck-name", help="Deck name (partial match supported)")
    parser.add_argument("--deck-id", help="Deck ID")

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    subparsers.add_parser("list", help="List all cards in a deck")

    grade_parser = subparsers.add_parser("grade", help="Grade all cards using LLM")
    grade_parser.add_argument("--batch-size", type=int, default=20,
                             help="Cards per batch (default: 20)")

    dump_parser = subparsers.add_parser("dump", help="Export cards to markdown")
    dump_parser.add_argument("--output", "-o", default="mochi_cards.md",
                            help="Output file (default: mochi_cards.md)")

    upload_parser = subparsers.add_parser("upload", help="Upload cards from markdown")
    upload_parser.add_argument("--input", "-i", required=True,
                              help="Input markdown file")

    subparsers.add_parser("decks", help="List all available decks")
    return parser.parse_args()


def main():
    args = parse_args()

    print("Fetching decks...")
    decks = get_decks()

    if args.command == "decks":
        print(f"\nAvailable decks ({len(decks)}):\n" + "=" * 60)
        for deck in decks:
            print(f"  {deck['name']}\n    ID: {deck['id']}\n" + "-" * 60)
        return

    deck = find_deck(decks, deck_name=args.deck_name, deck_id=args.deck_id)
    if not deck:
        print("\nAvailable decks:")
        for d in decks:
            print(f"  - {d['name']} (id: {d['id']})")
        search_info = f" (searched: {args.deck_name or args.deck_id})" if args.deck_name or args.deck_id else ""
        print(f"\nDeck not found{search_info}. Specify --deck-name or --deck-id")
        sys.exit(1)

    if args.command == "list" or args.command is None:
        list_cards(deck["id"], deck["name"])
    elif args.command == "grade":
        imperfect_cards, all_results = grade_all_cards(deck["id"], batch_size=args.batch_size)
        display_grading_results(imperfect_cards, all_results)
    elif args.command == "dump":
        dump_cards_to_markdown(deck["id"], args.output)
    elif args.command == "upload":
        upload_cards_from_markdown(deck["id"], args.input)


if __name__ == "__main__":
    main()
