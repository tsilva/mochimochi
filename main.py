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
import importlib
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
DECK_ID = os.getenv("DECK_ID")

BASE_URL = "https://app.mochi.cards/api"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Sync-related constants
SYNC_DIR = Path(".mochi_sync")
LAST_SYNC_FILE = SYNC_DIR / "last_sync.md"
DELETED_FILE = SYNC_DIR / "deleted.txt"
LOCAL_FILE = Path("mochi_cards.md")


def parse_card(content):
    """Parse card content into question and answer."""
    q, _, a = content.partition('---')
    return q.strip(), a.strip()


def content_hash(question, answer):
    """Generate hash of card content for duplicate detection."""
    content = f"{question.strip()}\n---\n{answer.strip()}"
    return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]


def ensure_sync_dir():
    """Create .mochi_sync directory if it doesn't exist."""
    SYNC_DIR.mkdir(exist_ok=True)
    # Add to .gitignore if not already there
    gitignore = Path(".gitignore")
    if gitignore.exists():
        content = gitignore.read_text()
        if ".mochi_sync/" not in content:
            with gitignore.open("a") as f:
                f.write("\n.mochi_sync/\n")
    else:
        gitignore.write_text(".mochi_sync/\n")


def load_deleted_ids():
    """Load list of deleted card IDs."""
    if not DELETED_FILE.exists():
        return set()
    return set(line.strip() for line in DELETED_FILE.read_text().splitlines() if line.strip())


def save_deleted_ids(deleted_ids):
    """Save list of deleted card IDs."""
    ensure_sync_dir()
    DELETED_FILE.write_text('\n'.join(sorted(deleted_ids)))


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


def grade_local_cards(batch_size=20):
    """Grade cards from local file.

    Args:
        batch_size: Number of cards per API request (default: 20)

    Returns:
        List of tuples: (card_dict, score, justification) for cards scoring < 10
    """
    if not LOCAL_FILE.exists():
        print(f"Error: {LOCAL_FILE} not found. Run 'pull' first.")
        return [], []

    print(f"\nReading cards from {LOCAL_FILE}...")
    local_cards = parse_markdown_cards(LOCAL_FILE.read_text())

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
    """Pull cards from remote and merge with local changes.

    Performs three-way merge using last sync state as base.
    """
    print("Fetching remote cards...")
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

    # Check if this is first pull
    if not LAST_SYNC_FILE.exists():
        print("First sync - establishing baseline...")
        ensure_sync_dir()

        # Write to local file
        with LOCAL_FILE.open('w', encoding='utf-8') as f:
            for card in remote_dict_cards:
                f.write(format_card_to_markdown(card) + '\n')

        # Save as last sync state
        with LAST_SYNC_FILE.open('w', encoding='utf-8') as f:
            for card in remote_dict_cards:
                f.write(format_card_to_markdown(card) + '\n')

        print(f"✓ Pulled {len(remote_dict_cards)} cards to {LOCAL_FILE}")
        return

    # Load local and base states
    print("Loading local changes...")
    local_cards = []
    if LOCAL_FILE.exists():
        local_cards = parse_markdown_cards(LOCAL_FILE.read_text())

    base_cards = parse_markdown_cards(LAST_SYNC_FILE.read_text())

    # Build indices for three-way merge
    base_by_id = {c['card_id']: c for c in base_cards if c['card_id']}
    local_by_id = {c['card_id']: c for c in local_cards if c['card_id']}
    remote_by_id = {c['card_id']: c for c in remote_dict_cards}

    # Track changes
    merged_cards = []
    conflicts = []

    # Process remote cards
    for remote_card in remote_dict_cards:
        card_id = remote_card['card_id']
        base_card = base_by_id.get(card_id)
        local_card = local_by_id.get(card_id)

        if not base_card and not local_card:
            # New remote card
            merged_cards.append(remote_card)
        elif local_card and base_card:
            # Card exists in all three - check for conflicts
            local_changed = local_card['content_hash'] != base_card['content_hash']
            remote_changed = remote_card['content_hash'] != base_card['content_hash']

            if local_changed and remote_changed:
                # Conflict - local wins by default
                conflicts.append((card_id, local_card, remote_card))
                merged_cards.append(local_card)
            elif local_changed:
                # Only local changed
                merged_cards.append(local_card)
            else:
                # Remote changed or no change
                merged_cards.append(remote_card)
        elif local_card:
            # Exists locally but not in base - keep local (was added locally)
            merged_cards.append(local_card)
        else:
            # Exists in base and remote but not local - was deleted locally, respect deletion
            pass

    # Add local-only new cards (card_id: null)
    for local_card in local_cards:
        if not local_card['card_id']:
            merged_cards.append(local_card)

    # Write merged result
    with LOCAL_FILE.open('w', encoding='utf-8') as f:
        for card in merged_cards:
            f.write(format_card_to_markdown(card) + '\n')

    # Update last sync state to match remote
    with LAST_SYNC_FILE.open('w', encoding='utf-8') as f:
        for card in remote_dict_cards:
            f.write(format_card_to_markdown(card) + '\n')

    if conflicts:
        print(f"\n⚠ {len(conflicts)} conflict(s) detected - local changes kept:")
        for card_id, local, remote in conflicts:
            print(f"  - {card_id}: {local['question'][:50]}...")

    print(f"✓ Pulled and merged {len(remote_dict_cards)} remote cards")
    print(f"  Local file: {len(merged_cards)} cards")


def push(deck_id, force=False):
    """Push local changes to remote with duplicate detection.

    Args:
        deck_id: Deck ID to push to
        force: If True, skip duplicate warnings
    """
    if not LOCAL_FILE.exists():
        print(f"Error: {LOCAL_FILE} not found. Run 'pull' first.")
        return

    print("Loading local cards...")
    local_cards = parse_markdown_cards(LOCAL_FILE.read_text())

    # Fetch remote state
    print("Fetching remote cards...")
    remote_cards = get_cards(deck_id)
    remote_by_id = {c['id']: c for c in remote_cards}

    # Build content hash index for duplicate detection
    remote_hashes = {}
    for card in remote_cards:
        q, a = parse_card(card['content'])
        h = content_hash(q, a)
        remote_hashes[h] = card['id']

    # Load deleted IDs
    deleted_ids = load_deleted_ids()

    # Track operations
    to_create = []
    to_update = []
    to_delete = []
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
                print(f"⚠ Card {card_id} not found remotely - will skip")
        else:
            # Card has no ID - check for duplicates
            if local_card['content_hash'] in remote_hashes and not force:
                duplicates.append((local_card, remote_hashes[local_card['content_hash']]))
            else:
                to_create.append(local_card)

    # Find deletions
    local_ids = {c['card_id'] for c in local_cards if c['card_id']}
    if LAST_SYNC_FILE.exists():
        base_cards = parse_markdown_cards(LAST_SYNC_FILE.read_text())
        base_ids = {c['card_id'] for c in base_cards if c['card_id']}
        missing_ids = base_ids - local_ids
        to_delete = [cid for cid in missing_ids if cid in remote_by_id]

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

        # Update local file with new ID
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

    # Update local file with new IDs
    if created_count > 0:
        with LOCAL_FILE.open('w', encoding='utf-8') as f:
            for card in local_cards:
                f.write(format_card_to_markdown(card) + '\n')

    # Clear deleted IDs
    save_deleted_ids(set())

    # Update last sync state
    print("\nUpdating sync state...")
    remote_cards = get_cards(deck_id)
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

    with LAST_SYNC_FILE.open('w', encoding='utf-8') as f:
        for card in remote_dict_cards:
            f.write(format_card_to_markdown(card) + '\n')

    print(f"\n✓ Pushed changes: {created_count} created, {updated_count} updated, {deleted_count} deleted")


def status():
    """Show diff between local and remote."""
    if not LOCAL_FILE.exists():
        print(f"No local file found. Run 'pull' first.")
        return

    if not LAST_SYNC_FILE.exists():
        print(f"No sync state found. Run 'pull' first.")
        return

    local_cards = parse_markdown_cards(LOCAL_FILE.read_text())
    base_cards = parse_markdown_cards(LAST_SYNC_FILE.read_text())

    local_by_id = {c['card_id']: c for c in local_cards if c['card_id']}
    base_by_id = {c['card_id']: c for c in base_cards if c['card_id']}

    # Find changes
    new_cards = [c for c in local_cards if not c['card_id']]
    modified = []
    deleted = []

    for card_id, base_card in base_by_id.items():
        if card_id not in local_by_id:
            deleted.append(card_id)
        else:
            local_card = local_by_id[card_id]
            if local_card['content_hash'] != base_card['content_hash']:
                modified.append(card_id)

    # Display
    print("\nLocal changes (not yet pushed):")
    print(f"  New cards: {len(new_cards)}")
    print(f"  Modified: {len(modified)}")
    print(f"  Deleted: {len(deleted)}")

    if new_cards:
        print("\n  New cards:")
        for card in new_cards[:5]:
            print(f"    - {card['question'][:60]}...")
        if len(new_cards) > 5:
            print(f"    ... and {len(new_cards) - 5} more")

    if modified:
        print("\n  Modified:")
        for card_id in modified[:5]:
            print(f"    - {card_id}: {local_by_id[card_id]['question'][:60]}...")
        if len(modified) > 5:
            print(f"    ... and {len(modified) - 5} more")

    if deleted:
        print("\n  Deleted:")
        for card_id in deleted[:5]:
            print(f"    - {card_id}")
        if len(deleted) > 5:
            print(f"    ... and {len(deleted) - 5} more")

    if not (new_cards or modified or deleted):
        print("\n✓ Everything up to date")


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


def discover_tasks():
    """Discover all available task modules in the tasks/ directory."""
    tasks_dir = Path(__file__).parent / "tasks"
    if not tasks_dir.exists():
        return []

    task_files = [f.stem for f in tasks_dir.glob("*.py")
                  if f.stem != "__init__" and not f.stem.startswith("_")]
    return sorted(task_files)


def load_task(task_name):
    """Load a task module dynamically."""
    return importlib.import_module(f"tasks.{task_name}")


def call_llm_for_task(task_module, cards_batch):
    """Call LLM with task prompt and cards batch."""
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not found in .env file")

    task_type = getattr(task_module, "TYPE", "read_only")

    # Build prompt from task's docstring
    prompt = task_module.__doc__.strip() + "\n\nCards to process:\n"

    for i, card in enumerate(cards_batch, 1):
        question, answer = parse_card(card['content'])
        prompt += f"\n{i}. Card ID: {card['id']}\n"
        prompt += f"   Question: {question}\n"
        prompt += f"   Answer: {answer}\n"

    # For mutation tasks, add JSON format instruction
    if task_type == "mutate":
        prompt += "\n\nReturn results as JSON array with format:\n"
        prompt += '[{"card_id": "...", "new_value": "..."}]'

    # Call OpenRouter API
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "google/gemini-2.5-flash",
        "messages": [{"role": "user", "content": prompt}]
    }

    # Request JSON format for structured output
    if task_type in ("mutate", "read_only"):
        data["response_format"] = {"type": "json_object"}

    response = requests.post(
        OPENROUTER_URL,
        headers=headers,
        json=data,
        timeout=60
    )
    response.raise_for_status()

    result = response.json()
    return result["choices"][0]["message"]["content"]


def display_diff(original_content, new_content, card_id):
    """Display a simple before/after diff."""
    print(f"\n{'=' * 60}")
    print(f"Card ID: {card_id}")
    print(f"{'=' * 60}")

    orig_q, orig_a = parse_card(original_content)
    new_q, new_a = parse_card(new_content)

    print("\n[BEFORE]")
    print(f"Q: {orig_q[:100]}..." if len(orig_q) > 100 else f"Q: {orig_q}")
    print(f"A: {orig_a[:150]}..." if len(orig_a) > 150 else f"A: {orig_a}")

    print("\n[AFTER]")
    print(f"Q: {new_q[:100]}..." if len(new_q) > 100 else f"Q: {new_q}")
    print(f"A: {new_a[:150]}..." if len(new_a) > 150 else f"A: {new_a}")
    print(f"{'-' * 60}")


def confirm_mutation(prompt_text="Apply this change?"):
    """Prompt user for confirmation."""
    while True:
        response = input(f"\n{prompt_text} [y/n/q]: ").lower().strip()
        if response in ('y', 'yes'):
            return True
        elif response in ('n', 'no'):
            return False
        elif response in ('q', 'quit'):
            print("Aborting remaining changes.")
            return None
        print("Please enter 'y' (yes), 'n' (no), or 'q' (quit)")


def execute_task(task_name, deck_id, apply=False):
    """Execute a task on all cards in a deck.

    Args:
        task_name: Name of the task module to run
        deck_id: Deck ID to process
        apply: If True and task is mutation, apply changes after confirmation

    Returns:
        List of results
    """
    task_module = load_task(task_name)
    task_type = getattr(task_module, "TYPE", "read_only")
    batch_size = getattr(task_module, "BATCH_SIZE", 20)

    print(f"\nTask: {task_name}")
    print(f"Type: {task_type}")
    print(f"Batch size: {batch_size}\n")
    print("Fetching cards...")

    all_results = []

    for batch, batch_num, total_batches in batched_cards(deck_id, batch_size):
        print(f"Processing batch {batch_num}/{total_batches} ({len(batch)} cards)...", flush=True)

        # Call LLM with task prompt
        llm_response = call_llm_for_task(task_module, batch)

        # Parse response - both task types now expect JSON
        data = json.loads(llm_response)
        if isinstance(data, dict):
            # Extract array from dict wrapper
            data = next((v for v in data.values() if isinstance(v, list)), [])

        for item in data:
            card_id = item["card_id"]
            card = next(c for c in batch if c["id"] == card_id)
            if task_type == "mutate":
                # For mutations, extract new_value directly
                new_value = item["new_value"]
                all_results.append((card, new_value))
            else:
                # For read-only, use task's parser
                parsed = task_module.parse_llm_response(json.dumps(item), card)
                all_results.append((card, parsed))

    # Display results
    if task_type == "read_only":
        display_readonly_results(all_results)
    else:
        display_mutation_results(all_results, apply, task_module)

    return all_results


def display_readonly_results(results):
    """Display results from read-only tasks in a table."""
    if not results:
        print("\nNo results to display.")
        return

    # Filter out perfect scores (score == 10) if this is a scoring task
    filtered_results = []
    perfect_count = 0

    for card, result in results:
        if isinstance(result, dict) and "score" in result:
            if result["score"] < 10:
                filtered_results.append((card, result))
            else:
                perfect_count += 1
        else:
            filtered_results.append((card, result))

    total_count = len(results)

    print(f"\n{'=' * 60}")
    print("RESULTS")
    print(f"{'=' * 60}\n")

    if perfect_count > 0:
        print(f"Total: {total_count} | Perfect (10/10): {perfect_count} | Need review: {len(filtered_results)}\n")

    if not filtered_results:
        print("🎉 All cards are perfect!")
        return

    for card, result in filtered_results:
        question, _ = parse_card(card['content'])
        q_short = question[:80] + '...' if len(question) > 80 else question

        print(f"Card ID: {card['id']}")
        print(f"Q: {q_short}")

        if isinstance(result, dict):
            for key, value in result.items():
                if key != "card_id":
                    print(f"  {key}: {value}")
        else:
            print(f"  Result: {result}")

        print(f"{'-' * 60}")


def display_mutation_results(results, apply, task_module):
    """Display and optionally apply mutation results."""
    if not results:
        print("\nNo mutations to display.")
        return

    print(f"\n{'=' * 60}")
    print(f"PROPOSED CHANGES ({len(results)} cards)")
    print(f"{'=' * 60}")

    if not apply:
        print("\nDry-run mode: Changes will NOT be applied.")
        print("Run with --apply to apply changes interactively.\n")

        for card, new_value in results:
            updated_card = task_module.apply_mutation(card, new_value)
            display_diff(card['content'], updated_card['content'], card['id'])

        return

    # Interactive mode: show each change and ask for confirmation
    print("\nInteractive mode: Review each change")
    print("Commands: y=apply, n=skip, q=quit\n")

    applied_count = 0
    skipped_count = 0

    for card, new_value in results:
        updated_card = task_module.apply_mutation(card, new_value)
        display_diff(card['content'], updated_card['content'], card['id'])

        decision = confirm_mutation()

        if decision is None:  # User quit
            break
        elif decision:  # User approved
            update_card(card['id'], content=updated_card['content'])
            print("✓ Applied")
            applied_count += 1
        else:  # User rejected
            print("Skipped")
            skipped_count += 1

    print(f"\n{'=' * 60}")
    print(f"Applied: {applied_count} | Skipped: {skipped_count}")
    print(f"{'=' * 60}")


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

    # Discovery command (doesn't require DECK_ID)
    subparsers.add_parser("decks", help="List all available decks")

    # Sync commands
    subparsers.add_parser("pull", help="Pull cards from remote and merge with local")
    push_parser = subparsers.add_parser("push", help="Push local changes to remote")
    push_parser.add_argument("--force", action="store_true",
                            help="Skip duplicate detection")
    subparsers.add_parser("status", help="Show local changes not yet pushed")

    # Local operations
    grade_parser = subparsers.add_parser("grade", help="Grade cards in local file using LLM")
    grade_parser.add_argument("--batch-size", type=int, default=20,
                             help="Cards per batch (default: 20)")

    # Task command with subcommands
    task_parser = subparsers.add_parser("task", help="Run LLM tasks on cards")
    task_subparsers = task_parser.add_subparsers(dest="task_subcommand", help="Task subcommand")

    _ = task_subparsers.add_parser("list", help="List all available tasks")

    task_run_parser = task_subparsers.add_parser("run", help="Run a specific task")
    task_run_parser.add_argument("task_name", help="Name of the task to run")
    task_run_parser.add_argument("--apply", action="store_true",
                                help="Apply mutations interactively (for mutation tasks)")

    return parser.parse_args()


def main():
    args = parse_args()

    # Handle commands that don't require DECK_ID

    # List available tasks
    if args.command == "task" and args.task_subcommand == "list":
        tasks = discover_tasks()
        if not tasks:
            print("No tasks found in tasks/ directory")
            return

        print(f"\nAvailable tasks ({len(tasks)}):\n" + "=" * 60)
        for task_name in tasks:
            task_module = load_task(task_name)
            task_type = getattr(task_module, "TYPE", "read_only")
            doc_first_line = task_module.__doc__.strip().split('\n')[0]
            print(f"\n{task_name}")
            print(f"  Type: {task_type}")
            print(f"  Description: {doc_first_line}")
            print("-" * 60)
        return

    # List all decks (requires only API_KEY, not DECK_ID)
    if args.command == "decks":
        if not API_KEY:
            print("Error: MOCHI_API_KEY not found in .env file")
            sys.exit(1)

        print("Fetching decks...")
        decks = get_decks()
        print(f"\nAvailable decks ({len(decks)}):\n" + "=" * 60)
        for deck in decks:
            print(f"\n  {deck['name']}")
            print(f"  ID: {deck['id']}")
            print("-" * 60)
        print("\nTo use a deck, add its ID to your .env file:")
        print("DECK_ID=<deck_id>")
        return

    # All other commands require both API_KEY and DECK_ID
    if not API_KEY:
        print("Error: MOCHI_API_KEY not found in .env file")
        sys.exit(1)

    if not DECK_ID:
        print("Error: DECK_ID not found in .env file")
        print("\nRun 'python main.py decks' to see available decks and get their IDs")
        sys.exit(1)

    # Commands that work on the configured deck
    if args.command == "pull":
        pull(DECK_ID)
    elif args.command == "push":
        push(DECK_ID, force=args.force)
    elif args.command == "status":
        status()
    elif args.command == "grade":
        imperfect_cards, all_results = grade_local_cards(batch_size=args.batch_size)
        display_grading_results(imperfect_cards, all_results)
    elif args.command == "task" and args.task_subcommand == "run":
        execute_task(args.task_name, DECK_ID, apply=args.apply)
    elif args.command is None:
        print("No command specified. Use --help to see available commands.")
        print("\nQuick start:")
        print("  1. python main.py pull        # Download deck")
        print("  2. Edit mochi_cards.md")
        print("  3. python main.py push        # Upload changes")


if __name__ == "__main__":
    main()
