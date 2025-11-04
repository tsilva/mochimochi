#!/usr/bin/env python3
"""Mochi flashcard management CLI with sync-based workflow.

Workflow:
    1. python main.py pull              # Download deck to mochi_cards.md
    2. Edit mochi_cards.md manually or use: python main.py grade
    3. python main.py push              # Upload changes back to Mochi

API usage:
    from main import create_card, update_card, delete_card, pull, push
    card = create_card(deck_id, "What is X?\n---\nX is Y")
    update_card(card['id'], content="Updated")
    delete_card(card['id'])
"""

import argparse
import hashlib
import json
import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()
API_KEY = os.getenv("MOCHI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

BASE_URL = "https://app.mochi.cards/api"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def parse_card(content):
    """Parse card content into question and answer."""
    q, _, a = content.partition('---')
    return q.strip(), a.strip()


def content_hash(question, answer):
    """Generate hash of card content for duplicate detection."""
    content = f"{question.strip()}\n---\n{answer.strip()}"
    return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]


def sanitize_filename(name):
    """Sanitize deck name for use in filename."""
    # Replace spaces and special chars with hyphens
    import re
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'[-\s]+', '-', name)
    return name.strip('-').lower()


def extract_deck_id_from_filename(file_path):
    """Extract deck ID from filename format: <name>-<deck_id>.md"""
    path = Path(file_path)
    stem = path.stem  # Remove .md extension
    # Deck ID is the last part after the last hyphen
    parts = stem.split('-')
    if len(parts) < 2:
        raise ValueError(f"Invalid filename format. Expected: <name>-<deck_id>.md, got: {path.name}")
    return parts[-1]


def parse_markdown_cards(markdown_text):
    """Parse markdown file into list of card dictionaries.

    Returns:
        List of dicts with keys: card_id, question, answer, tags, archived, content_hash
    """
    sections = [s.strip() for s in markdown_text.split('---')]
    cards = []

    state = 'expect_frontmatter'
    card_id = None
    tags = []
    archived = False
    question = None

    for section in sections:
        if not section or section.startswith('#'):
            continue

        if state == 'expect_frontmatter':
            # Parse frontmatter
            frontmatter = {}
            for line in section.split('\n'):
                line = line.strip()
                if ':' in line:
                    key, value = line.split(':', 1)
                    frontmatter[key.strip()] = value.strip()

            card_id_value = frontmatter.get('card_id', 'null')
            if card_id_value.lower() in ('null', 'none', ''):
                card_id = None
            else:
                card_id = card_id_value

            tags_value = frontmatter.get('tags', '[]')
            try:
                tags = json.loads(tags_value) if tags_value else []
            except json.JSONDecodeError:
                tags = []

            archived = frontmatter.get('archived', 'false').lower() == 'true'
            state = 'expect_question'

        elif state == 'expect_question':
            question = section
            state = 'expect_answer'

        elif state == 'expect_answer':
            answer = section

            # Create card dict
            card = {
                'card_id': card_id,
                'question': question,
                'answer': answer,
                'tags': tags,
                'archived': archived,
                'content_hash': content_hash(question, answer)
            }
            cards.append(card)

            # Reset state
            card_id = None
            tags = []
            archived = False
            question = None
            state = 'expect_frontmatter'

    return cards


def format_card_to_markdown(card):
    """Format a card dict to markdown with frontmatter.

    Args:
        card: Dict with keys: card_id, question, answer, tags, archived

    Returns:
        Markdown string for the card
    """
    lines = ["---"]
    lines.append(f"card_id: {card.get('card_id', 'null')}")

    tags = card.get('tags', [])
    if tags:
        lines.append(f"tags: {json.dumps(tags)}")

    archived = card.get('archived', False)
    if archived:
        lines.append(f"archived: true")

    lines.append("---")
    lines.append(card['question'])
    lines.append("---")
    lines.append(card['answer'])

    return '\n'.join(lines)


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


def get_deck(deck_id):
    """Fetch a specific deck by ID."""
    response = requests.get(
        f"{BASE_URL}/decks/{deck_id}",
        auth=(API_KEY, ""),
        timeout=30
    )
    response.raise_for_status()
    return response.json()


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

IMPORTANT: You must grade ALL cards below. Return a JSON array with one entry per card.

Format your response as JSON array:
[
  {"card_id": "id1", "score": 10, "justification": "explanation"},
  {"card_id": "id2", "score": 8, "justification": "explanation"}
]

Cards to grade:
"""

    for i, card in enumerate(cards_batch, 1):
        question, answer = parse_card(card['content'])
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

    grades = json.loads(content)
    if isinstance(grades, dict):
        grades = next((v for v in grades.values() if isinstance(v, list)), [])

    grade_map = {g['card_id']: (g['score'], g['justification']) for g in grades}

    # Check for missing grades
    missing_ids = [card['id'] for card in cards_batch if card['id'] not in grade_map]
    if missing_ids:
        print(f"\n⚠ Warning: LLM didn't return grades for {len(missing_ids)} card(s): {', '.join(missing_ids[:3])}")
        if len(missing_ids) > 3:
            print(f"   ... and {len(missing_ids) - 3} more")

    # Only return results for cards that were graded
    results = [(card, *grade_map[card['id']]) for card in cards_batch if card['id'] in grade_map]
    return results


def grade_local_cards(file_path, batch_size=20):
    """Grade cards from local deck file.

    Args:
        file_path: Path to deck file to grade
        batch_size: Number of cards per API request (default: 20)

    Returns:
        List of tuples: (card_dict, score, justification) for cards scoring < 10
    """
    local_file = Path(file_path)

    if not local_file.exists():
        print(f"Error: {local_file} not found")
        return [], []

    print(f"\nReading cards from {local_file}...")
    local_cards = parse_markdown_cards(local_file.read_text())

    if not local_cards:
        print("No cards found in local file.")
        return [], []

    # Convert card dicts to API format for grading
    api_format_cards = []
    for card in local_cards:
        content = f"{card['question']}\n---\n{card['answer']}"
        api_format_cards.append({
            'id': card.get('card_id', 'local-' + card['content_hash']),
            'content': content
        })

    # Grade in batches
    print(f"Grading {len(api_format_cards)} cards...")
    all_results = []
    total_batches = (len(api_format_cards) + batch_size - 1) // batch_size

    for i in range(0, len(api_format_cards), batch_size):
        batch = api_format_cards[i:i+batch_size]
        batch_num = (i // batch_size) + 1
        print(f"  Processing batch {batch_num}/{total_batches} ({len(batch)} cards)...", flush=True)
        results = grade_cards_batch(batch)
        all_results.extend(results)

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
            break

        cards.extend(data["docs"])

        bookmark = data.get("bookmark")
        if not bookmark:
            break

    return cards


def pull(deck_id):
    """Download cards from Mochi to <deck-name>-<deck_id>.md file.

    Args:
        deck_id: The Mochi deck ID to pull from

    Creates a file named <deck-name>-<deck_id>.md with all cards from the deck.
    """
    print(f"Fetching deck info for {deck_id}...")
    deck_info = get_deck(deck_id)
    deck_name = sanitize_filename(deck_info['name'])

    # Create filename: <deck-name>-<deck_id>.md
    local_file = Path(f"{deck_name}-{deck_id}.md")

    # Warn if file exists
    if local_file.exists():
        print(f"⚠ Warning: {local_file} already exists")
        print("This will overwrite your local changes.")
        print("Tip: Use 'git diff' to see what you'll lose")
        response = input("\nProceed? [y/N]: ").lower().strip()
        if response not in ('y', 'yes'):
            print("Aborted")
            return

    print(f"Fetching cards from deck '{deck_info['name']}'...")
    remote_cards = get_cards(deck_id)

    # Convert API cards to dict format
    remote_dict_cards = []
    for card in remote_cards:
        question, answer = parse_card(card['content'])
        tags = card.get('tags', []) if isinstance(card.get('tags'), list) else []
        remote_dict_cards.append({
            'card_id': card['id'],
            'question': question,
            'answer': answer,
            'tags': tags,
            'archived': card.get('archived', False),
            'content_hash': content_hash(question, answer)
        })

    # Write to local file
    with local_file.open('w', encoding='utf-8') as f:
        for card in remote_dict_cards:
            f.write(format_card_to_markdown(card) + '\n')

    print(f"✓ Downloaded {len(remote_dict_cards)} cards to {local_file}")

    # First-time setup message
    if not Path('.git').exists():
        print("\nTip: Initialize git to track changes:")
        print("  git init")
        print(f"  git add {local_file}")
        print(f"  git commit -m 'Pull {deck_info['name']}'")


def push(file_path, force=False):
    """Push local deck file to Mochi (one-way sync: local → remote).

    Compares local file to remote and creates/updates/deletes to match.
    Local is source of truth.

    Args:
        file_path: Path to deck file (<deck-name>-<deck_id>.md)
        force: If True, skip duplicate detection for new cards
    """
    local_file = Path(file_path)

    if not local_file.exists():
        print(f"Error: {local_file} not found")
        return

    # Extract deck ID from filename
    try:
        deck_id = extract_deck_id_from_filename(local_file)
    except ValueError as e:
        print(f"Error: {e}")
        return

    print(f"Loading local cards from {local_file}...")
    local_cards = parse_markdown_cards(local_file.read_text())

    print("Fetching remote cards...")
    remote_cards = get_cards(deck_id)
    remote_by_id = {c['id']: c for c in remote_cards}

    # Build content hash index for duplicate detection
    remote_hashes = {}
    for card in remote_cards:
        q, a = parse_card(card['content'])
        h = content_hash(q, a)
        remote_hashes[h] = card['id']

    # Determine operations needed
    to_create = []
    to_update = []
    duplicates = []

    for local_card in local_cards:
        card_id = local_card['card_id']

        if card_id:
            # Card has ID - check if update needed
            if card_id in remote_by_id:
                remote_card = remote_by_id[card_id]
                remote_q, remote_a = parse_card(remote_card['content'])
                remote_hash = content_hash(remote_q, remote_a)

                if local_card['content_hash'] != remote_hash:
                    to_update.append(local_card)
            else:
                print(f"⚠ Warning: Card {card_id} not found remotely - will skip")
        else:
            # Card has no ID - check for duplicates before creating
            if local_card['content_hash'] in remote_hashes and not force:
                duplicates.append((local_card, remote_hashes[local_card['content_hash']]))
            else:
                to_create.append(local_card)

    # Find deletions: remote cards not in local
    local_ids = {c['card_id'] for c in local_cards if c['card_id']}
    remote_ids = set(remote_by_id.keys())
    to_delete = remote_ids - local_ids

    # Handle duplicates
    if duplicates and not force:
        print(f"\n⚠ Found {len(duplicates)} potential duplicate(s):")
        for local_card, remote_id in duplicates:
            print(f"  - {local_card['question'][:60]}... (matches {remote_id})")
        print("\nRun with --force to create anyway")
        return

    # Show summary
    print(f"\nChanges to push:")
    print(f"  Create: {len(to_create)}")
    print(f"  Update: {len(to_update)}")
    print(f"  Delete: {len(to_delete)}")

    if not (to_create or to_update or to_delete):
        print("\n✓ Everything up to date")
        return

    # Confirm
    response = input("\nProceed? [y/N]: ").lower().strip()
    if response not in ('y', 'yes'):
        print("Aborted")
        return

    # Apply changes
    created_count = 0
    updated_count = 0
    deleted_count = 0

    for card in to_create:
        content = f"{card['question']}\n---\n{card['answer']}"
        kwargs = {'content': content}
        if card['tags']:
            kwargs['tags'] = card['tags']
        if card['archived']:
            kwargs['archived'] = True

        created = create_card(deck_id, **kwargs)
        print(f"  ✓ Created {created['id']}: {card['question'][:50]}...")
        created_count += 1

        # Update card with new ID
        card['card_id'] = created['id']

    for card in to_update:
        content = f"{card['question']}\n---\n{card['answer']}"
        kwargs = {'content': content}
        if card['tags']:
            kwargs['tags'] = card['tags']
        if card.get('archived'):
            kwargs['archived'] = True

        update_card(card['card_id'], **kwargs)
        print(f"  ✓ Updated {card['card_id']}: {card['question'][:50]}...")
        updated_count += 1

    for card_id in to_delete:
        delete_card(card_id)
        print(f"  ✓ Deleted {card_id}")
        deleted_count += 1

    # Write back local file with new IDs from created cards
    if created_count > 0:
        with local_file.open('w', encoding='utf-8') as f:
            for card in local_cards:
                f.write(format_card_to_markdown(card) + '\n')
        print(f"\nℹ Updated {local_file} with new card IDs")
        print(f"Tip: Commit these changes: git add {local_file.name} && git commit -m 'Add card IDs'")

    print(f"\n✓ Pushed changes: {created_count} created, {updated_count} updated, {deleted_count} deleted")


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
        question, answer = parse_card(card['content'])
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

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Discovery command
    subparsers.add_parser("decks", help="List all available decks")

    # Sync commands
    pull_parser = subparsers.add_parser("pull", help="Download deck from Mochi")
    pull_parser.add_argument("deck_id", help="Deck ID to pull from Mochi")

    push_parser = subparsers.add_parser("push", help="Push local deck file to Mochi")
    push_parser.add_argument("file_path", help="Path to deck file (e.g., python-abc123.md)")
    push_parser.add_argument("--force", action="store_true",
                            help="Skip duplicate detection")

    # Local operations
    grade_parser = subparsers.add_parser("grade", help="Grade cards in deck file using LLM")
    grade_parser.add_argument("file_path", help="Path to deck file to grade")
    grade_parser.add_argument("--batch-size", type=int, default=20,
                             help="Cards per batch (default: 20)")

    return parser.parse_args()


def main():
    args = parse_args()

    # Check API key for all commands
    if not API_KEY:
        print("Error: MOCHI_API_KEY not found in .env file")
        print("\nCreate a .env file with:")
        print("MOCHI_API_KEY=your_api_key_here")
        sys.exit(1)

    # Handle commands
    if args.command == "decks":
        print("Fetching decks...")
        decks = get_decks()
        print(f"\nAvailable decks ({len(decks)}):\n" + "=" * 60)
        for deck in decks:
            print(f"\n  {deck['name']}")
            print(f"  ID: {deck['id']}")
            print("-" * 60)
        print("\nTo pull a deck:")
        print("  python main.py pull <deck_id>")
        return

    elif args.command == "pull":
        pull(args.deck_id)

    elif args.command == "push":
        push(args.file_path, force=args.force)

    elif args.command == "grade":
        imperfect_cards, all_results = grade_local_cards(
            args.file_path,
            batch_size=args.batch_size
        )
        display_grading_results(imperfect_cards, all_results)

    elif args.command is None:
        print("No command specified. Use --help to see available commands.")
        print("\nQuick start:")
        print("  1. python main.py decks              # List decks")
        print("  2. python main.py pull <deck_id>     # Download deck")
        print("  3. Edit <deck-name>-<deck_id>.md")
        print("  4. python main.py push <deck-name>-<deck_id>.md  # Upload changes")


if __name__ == "__main__":
    main()
