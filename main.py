#!/usr/bin/env python3
"""Mochi flashcard management CLI with local-first multi-deck workflow.

Workflow:
    1. mochi-mochi decks                              # List available decks
    2. mochi-mochi pull <deck_id>                     # Download to deck-<name>-<deck_id>.md
    3. Edit deck-<name>-<deck_id>.md locally
    4. mochi-mochi push deck-<name>-<deck_id>.md      # Upload changes back to Mochi (local → remote)
       or: mochi-mochi sync deck-<name>-<deck_id>.md  # Bidirectional sync (handles remote deletions)
       or: mochi-mochi push                           # Upload all deck files in current directory
       or: mochi-mochi sync                           # Sync all deck files in current directory

    Or create a new deck:
    1. Create deck-<name>.md file locally
    2. mochi-mochi push deck-<name>.md                # Creates deck in Mochi, renames file

API usage:
    from main import create_card, update_card, delete_card, pull, push, sync, create_deck
    card = create_card(deck_id, "What is X?\n---\nX is Y")
    update_card(card['id'], content="Updated")
    delete_card(card['id'])
    deck = create_deck("My New Deck")
"""

import argparse
import hashlib
import json
import os
import sys
import requests
from pathlib import Path
from datetime import datetime
from openai import OpenAI

# Optional dependencies for deduplication
try:
    import numpy as np
    import faiss
    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False

BASE_URL = "https://app.mochi.cards/api"

# Config file location
CONFIG_PATH = Path.home() / ".mochi-mochi" / "config"

# Global API key (set in main())
API_KEY = None
OPENAI_API_KEY = None
OPENROUTER_API_KEY = None


def load_user_config():
    """Load configuration from user config file at ~/.mochi-mochi/config.

    Returns:
        dict: Configuration dictionary with keys like 'MOCHI_API_KEY'
    """
    config = {}

    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip()
        except Exception as e:
            print(f"Warning: Failed to load config from {CONFIG_PATH}: {e}")

    return config


def prompt_and_save_api_key():
    """Prompt user for API key and save to config file.

    Returns:
        str: The API key entered by the user
    """
    print("\nMochi API key not found.")
    print("You can get your API key from: https://app.mochi.cards/settings")
    print()

    api_key = input("Enter your Mochi API key: ").strip()

    if not api_key:
        print("Error: API key cannot be empty")
        sys.exit(1)

    # Create config directory if it doesn't exist
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Load existing config to preserve other values
    config = load_user_config()
    config['MOCHI_API_KEY'] = api_key

    # Save config
    try:
        with open(CONFIG_PATH, 'w') as f:
            for key, value in config.items():
                f.write(f"{key}={value}\n")
        print(f"\n✓ API key saved to {CONFIG_PATH}")
    except Exception as e:
        print(f"Warning: Failed to save config: {e}")
        print("Continuing with current session...")

    return api_key


def get_api_key():
    """Get API key from user config, prompting if not found.

    Returns:
        str: API key
    """
    config = load_user_config()

    if "MOCHI_API_KEY" in config:
        return config["MOCHI_API_KEY"]

    # Prompt user for API key and save it
    return prompt_and_save_api_key()


def get_openai_api_key():
    """Get OpenAI API key from user config, prompting if not found.

    Returns:
        str: OpenAI API key
    """
    config = load_user_config()

    if "OPENAI_API_KEY" in config:
        return config["OPENAI_API_KEY"]

    # Prompt user for API key
    print("\nOpenAI API key not found.")
    print("You can get your API key from: https://platform.openai.com/api-keys")
    print()

    api_key = input("Enter your OpenAI API key: ").strip()

    if not api_key:
        print("Error: API key cannot be empty")
        sys.exit(1)

    # Load existing config to preserve other values
    config['OPENAI_API_KEY'] = api_key

    # Save config
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, 'w') as f:
            for key, value in config.items():
                f.write(f"{key}={value}\n")
        print(f"\n✓ OpenAI API key saved to {CONFIG_PATH}")
    except Exception as e:
        print(f"Warning: Failed to save config: {e}")
        print("Continuing with current session...")

    return api_key


def get_openrouter_api_key():
    """Get OpenRouter API key from user config, prompting if not found.

    Returns:
        str: OpenRouter API key
    """
    config = load_user_config()

    if "OPENROUTER_API_KEY" in config:
        return config["OPENROUTER_API_KEY"]

    # Prompt user for API key
    print("\nOpenRouter API key not found.")
    print("You can get your API key from: https://openrouter.ai/keys")
    print()

    api_key = input("Enter your OpenRouter API key: ").strip()

    if not api_key:
        print("Error: API key cannot be empty")
        sys.exit(1)

    # Load existing config to preserve other values
    config['OPENROUTER_API_KEY'] = api_key

    # Save config
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, 'w') as f:
            for key, value in config.items():
                f.write(f"{key}={value}\n")
        print(f"\n✓ OpenRouter API key saved to {CONFIG_PATH}")
    except Exception as e:
        print(f"Warning: Failed to save config: {e}")
        print("Continuing with current session...")

    return api_key


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
    """Extract deck ID from filename format: deck-<name>-<deck_id>.md

    Returns None if filename is deck-<name>.md (new deck to be created).
    """
    path = Path(file_path)
    stem = path.stem  # Remove .md extension

    # Check that filename starts with 'deck-'
    if not stem.startswith('deck-'):
        raise ValueError(f"Invalid filename format. Expected: deck-<name>-<deck_id>.md or deck-<name>.md, got: {path.name}")

    # Remove 'deck-' prefix
    stem_without_prefix = stem[5:]  # Remove 'deck-'

    if not stem_without_prefix:
        raise ValueError(f"Invalid filename format. Expected: deck-<name>-<deck_id>.md or deck-<name>.md, got: {path.name}")

    # Split by hyphens to find deck ID
    parts = stem_without_prefix.split('-')

    # If only one part, it's a new deck (deck-<name>.md)
    if len(parts) == 1:
        return None

    # Check if last part looks like a valid deck ID:
    # - Must be exactly 8 alphanumeric characters
    # - Must have mixed case (real Mochi IDs use base62-like encoding with upper+lower case)
    potential_deck_id = parts[-1]
    if len(potential_deck_id) == 8 and potential_deck_id.isalnum():
        has_upper = any(c.isupper() for c in potential_deck_id)
        has_lower = any(c.islower() for c in potential_deck_id)
        if has_upper and has_lower:
            return potential_deck_id

    # Otherwise, it's part of the deck name (new deck)
    return None


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


def create_deck(name, **kwargs):
    """Create a new deck.

    Args:
        name: Name of the deck
        **kwargs: Optional fields like parent-id, sort, etc.

    Returns:
        Created deck data including 'id'
    """
    data = {
        "name": name,
        **kwargs
    }

    response = requests.post(
        f"{BASE_URL}/decks/",
        auth=(API_KEY, ""),
        json=data,
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


def find_deck_files(directory='.'):
    """Find all deck files in the specified directory.

    Args:
        directory: Directory to search (default: current directory)

    Returns:
        List of Path objects for deck files matching pattern deck-*.md
    """
    from glob import glob
    deck_files = glob(f"{directory}/deck-*.md")
    return sorted([Path(f) for f in deck_files])


def validate_deck_file(file_path):
    """Validate deck file structure before push operations.

    Args:
        file_path: Path to deck file to validate

    Raises:
        ValueError: If file structure is invalid
        FileNotFoundError: If file doesn't exist

    Returns:
        tuple: (cards, deck_id) where deck_id is None for new decks
    """
    local_file = Path(file_path)

    # Check file exists
    if not local_file.exists():
        raise FileNotFoundError(f"Deck file not found: {file_path}")

    # Check file is readable and has content
    try:
        content = local_file.read_text(encoding='utf-8')
    except Exception as e:
        raise ValueError(f"Cannot read file {file_path}: {e}")

    if not content.strip():
        raise ValueError(f"Deck file is empty: {file_path}")

    # Validate filename format (will raise ValueError if invalid)
    # Returns None for new decks (deck-<name>.md format)
    try:
        deck_id = extract_deck_id_from_filename(local_file)
    except ValueError as e:
        raise ValueError(f"Invalid filename format: {e}")

    # Parse cards - will fail if structure is invalid
    try:
        cards = parse_markdown_cards(content)
    except Exception as e:
        raise ValueError(f"Failed to parse deck file: {e}")

    if not cards:
        raise ValueError(f"No cards found in deck file: {file_path}")

    # Validate each card structure
    for idx, card in enumerate(cards, 1):
        # Check required fields exist
        if 'question' not in card or 'answer' not in card:
            raise ValueError(f"Card {idx}: Missing question or answer field")

        # Check question and answer are not empty
        question = card['question'].strip()
        answer = card['answer'].strip()

        if not question:
            raise ValueError(f"Card {idx}: Empty question")

        if not answer:
            raise ValueError(f"Card {idx}: Empty answer")

        # Validate card_id format if present
        card_id = card.get('card_id')
        if card_id and not isinstance(card_id, str):
            raise ValueError(f"Card {idx}: Invalid card_id type (must be string or None)")

        # Validate tags format
        tags = card.get('tags', [])
        if not isinstance(tags, list):
            raise ValueError(f"Card {idx}: Invalid tags format (must be list)")

        # Validate archived format
        archived = card.get('archived', False)
        if not isinstance(archived, bool):
            raise ValueError(f"Card {idx}: Invalid archived format (must be boolean)")

    return cards, deck_id


def pull(deck_id):
    """Download cards from Mochi to deck-<deck-name>-<deck_id>.md file.

    Args:
        deck_id: The Mochi deck ID to pull from

    Creates a file named deck-<deck-name>-<deck_id>.md with all cards from the deck.
    """
    print(f"Fetching deck info for {deck_id}...")
    deck_info = get_deck(deck_id)
    deck_name = sanitize_filename(deck_info['name'])

    # Create filename: deck-<deck-name>-<deck_id>.md
    local_file = Path(f"deck-{deck_name}-{deck_id}.md")

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
        file_path: Path to deck file (deck-<name>-<deck_id>.md or deck-<name>.md for new decks)
        force: If True, skip duplicate detection for new cards

    Raises:
        AssertionError: If local cards with IDs don't exist remotely (data inconsistency)
    """
    local_file = Path(file_path)

    # Validate deck file structure
    print(f"Validating {local_file}...")
    try:
        local_cards, deck_id = validate_deck_file(local_file)
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}")
        return

    print(f"✓ Validated {len(local_cards)} cards")

    # Check if this is a new deck (no deck ID in filename)
    if deck_id is None:
        # Extract deck name from filename: deck-<name>.md -> <name>
        stem = local_file.stem
        deck_name = stem[5:]  # Remove 'deck-' prefix

        print(f"\n→ Creating new deck '{deck_name}'...")
        try:
            new_deck = create_deck(deck_name)
            deck_id = new_deck['id']
            print(f"✓ Created deck with ID: {deck_id}")

            # Rename file to include deck ID
            sanitized_name = sanitize_filename(deck_name)
            new_filename = f"deck-{sanitized_name}-{deck_id}.md"
            new_file_path = local_file.parent / new_filename

            local_file.rename(new_file_path)
            local_file = new_file_path  # Update reference
            print(f"✓ Renamed file to: {new_filename}")

        except Exception as e:
            print(f"Error creating deck: {e}")
            return

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
    missing_remote = []

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
                # Card has ID but doesn't exist remotely - data inconsistency!
                missing_remote.append(local_card)
        else:
            # Card has no ID - check for duplicates before creating
            if local_card['content_hash'] in remote_hashes and not force:
                duplicates.append((local_card, remote_hashes[local_card['content_hash']]))
            else:
                to_create.append(local_card)

    # Check for data inconsistency: cards with IDs that don't exist remotely
    if missing_remote:
        print(f"\n❌ Error: Data inconsistency detected!")
        print(f"Found {len(missing_remote)} card(s) with IDs that don't exist remotely.")
        print("This indicates cards were deleted remotely but still exist locally.\n")
        print("Missing cards:")
        for card in missing_remote:
            q_preview = card['question'][:60] + '...' if len(card['question']) > 60 else card['question']
            print(f"  - {card['card_id']}: {q_preview}")
        print("\nTo fix this, use 'sync' command instead of 'push'.")
        print("The sync command will handle remotely-deleted cards.")
        raise AssertionError(f"Push failed: {len(missing_remote)} local cards not found remotely")

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
        kwargs = {}
        if card['tags']:
            kwargs['tags'] = card['tags']
        if card['archived']:
            kwargs['archived?'] = True

        created = create_card(deck_id, content, **kwargs)
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
            kwargs['archived?'] = True

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


def sync(file_path, force=False):
    """Sync local deck file with Mochi (bidirectional sync with deletion handling).

    Unlike push, sync handles the case where cards are deleted remotely:
    - Cards deleted remotely will be removed from local file (with user confirmation)
    - Local changes are pushed to remote (creates/updates)
    - Remote deletions are pulled to local

    Args:
        file_path: Path to deck file (deck-<name>-<deck_id>.md)
        force: If True, skip duplicate detection for new cards
    """
    local_file = Path(file_path)

    # Validate deck file structure
    print(f"Validating {local_file}...")
    try:
        local_cards, deck_id = validate_deck_file(local_file)
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}")
        return

    print(f"✓ Validated {len(local_cards)} cards")

    # Sync only works with existing decks (must have deck ID)
    if deck_id is None:
        print(f"\n❌ Error: Cannot sync new deck file (no deck ID in filename)")
        print("Use 'push' command to create the deck first, then use 'sync'")
        return

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
    to_delete_locally = []  # Cards deleted remotely, need to delete locally
    duplicates = []

    for local_card in local_cards:
        card_id = local_card['card_id']

        if card_id:
            # Card has ID - check if it exists remotely
            if card_id in remote_by_id:
                # Card exists remotely - check if update needed
                remote_card = remote_by_id[card_id]
                remote_q, remote_a = parse_card(remote_card['content'])
                remote_hash = content_hash(remote_q, remote_a)

                if local_card['content_hash'] != remote_hash:
                    to_update.append(local_card)
            else:
                # Card has ID but doesn't exist remotely - was deleted remotely
                to_delete_locally.append(local_card)
        else:
            # Card has no ID - check for duplicates before creating
            if local_card['content_hash'] in remote_hashes and not force:
                duplicates.append((local_card, remote_hashes[local_card['content_hash']]))
            else:
                to_create.append(local_card)

    # Find remote deletions to apply locally
    local_ids = {c['card_id'] for c in local_cards if c['card_id']}
    remote_ids = set(remote_by_id.keys())
    to_delete_remotely = remote_ids - local_ids  # Cards in remote but not local

    # Handle duplicates
    if duplicates and not force:
        print(f"\n⚠ Found {len(duplicates)} potential duplicate(s):")
        for local_card, remote_id in duplicates:
            print(f"  - {local_card['question'][:60]}... (matches {remote_id})")
        print("\nRun with --force to create anyway")
        return

    # Show summary
    print(f"\nSync summary:")
    print(f"  Create (local → remote): {len(to_create)}")
    print(f"  Update (local → remote): {len(to_update)}")
    print(f"  Delete remotely (local → remote): {len(to_delete_remotely)}")
    print(f"  Delete locally (remote → local): {len(to_delete_locally)}")

    # Show cards that will be deleted locally (most important for user to review)
    if to_delete_locally:
        print(f"\n⚠ Warning: {len(to_delete_locally)} card(s) will be DELETED LOCALLY:")
        print("These cards exist locally but were deleted remotely:\n")
        for card in to_delete_locally:
            q_preview = card['question'][:60] + '...' if len(card['question']) > 60 else card['question']
            print(f"  - {card['card_id']}: {q_preview}")

    if not (to_create or to_update or to_delete_locally or to_delete_remotely):
        print("\n✓ Everything in sync")
        return

    # Confirm
    print()
    response = input("Proceed with sync? [y/N]: ").lower().strip()
    if response not in ('y', 'yes'):
        print("Aborted")
        return

    # Apply changes
    created_count = 0
    updated_count = 0
    deleted_remotely_count = 0
    deleted_locally_count = 0

    # Create new cards remotely
    for card in to_create:
        content = f"{card['question']}\n---\n{card['answer']}"
        kwargs = {}
        if card['tags']:
            kwargs['tags'] = card['tags']
        if card['archived']:
            kwargs['archived?'] = True

        created = create_card(deck_id, content, **kwargs)
        print(f"  ✓ Created {created['id']}: {card['question'][:50]}...")
        created_count += 1

        # Update card with new ID
        card['card_id'] = created['id']

    # Update existing cards remotely
    for card in to_update:
        content = f"{card['question']}\n---\n{card['answer']}"
        kwargs = {'content': content}
        if card['tags']:
            kwargs['tags'] = card['tags']
        if card.get('archived'):
            kwargs['archived?'] = True

        update_card(card['card_id'], **kwargs)
        print(f"  ✓ Updated {card['card_id']}: {card['question'][:50]}...")
        updated_count += 1

    # Delete cards remotely that were removed locally
    for card_id in to_delete_remotely:
        delete_card(card_id)
        print(f"  ✓ Deleted remotely {card_id}")
        deleted_remotely_count += 1

    # Remove cards locally that were deleted remotely
    if to_delete_locally:
        cards_to_delete_ids = {card['card_id'] for card in to_delete_locally}
        local_cards = [card for card in local_cards if card['card_id'] not in cards_to_delete_ids]
        deleted_locally_count = len(cards_to_delete_ids)
        print(f"  ✓ Removed {deleted_locally_count} card(s) locally")

    # Write back local file with updates
    with local_file.open('w', encoding='utf-8') as f:
        for card in local_cards:
            f.write(format_card_to_markdown(card) + '\n')

    if created_count > 0 or deleted_locally_count > 0:
        print(f"\nℹ Updated {local_file}")
        print(f"Tip: Review changes with: git diff {local_file.name}")
        if created_count > 0:
            print(f"     Commit new IDs: git add {local_file.name} && git commit -m 'Sync: add card IDs'")

    print(f"\n✓ Sync completed: {created_count} created, {updated_count} updated, {deleted_remotely_count} deleted remotely, {deleted_locally_count} deleted locally")


def get_embedding(text, client):
    """Generate embedding for text using OpenRouter API.

    Args:
        text: Text to embed
        client: OpenAI client instance configured for OpenRouter

    Returns:
        List of floats representing the embedding vector
    """
    response = client.embeddings.create(
        model="openai/text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding


def get_embeddings_batch(texts, client, batch_size=100):
    """Generate embeddings for multiple texts using OpenRouter API.

    Args:
        texts: List of texts to embed
        client: OpenAI client instance configured for OpenRouter
        batch_size: Number of texts to process per API call (default: 100)

    Returns:
        List of embedding vectors (one per input text)
    """
    embeddings = []

    # Process in batches to respect API limits
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        response = client.embeddings.create(
            model="openai/text-embedding-3-small",
            input=batch
        )
        # Extract embeddings in the same order as input
        batch_embeddings = [item.embedding for item in response.data]
        embeddings.extend(batch_embeddings)

        # Progress indicator
        print(f"  {min(i + batch_size, len(texts))}/{len(texts)} ", end='\r')

    return embeddings


def cosine_similarity(vec1, vec2):
    """Calculate cosine similarity between two vectors.

    Args:
        vec1: First embedding vector
        vec2: Second embedding vector

    Returns:
        Float between 0 and 1 representing similarity
    """
    import math
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))
    return dot_product / (magnitude1 * magnitude2)


def find_duplicate_pairs(cards, threshold=0.85):
    """Find pairs of similar cards using FAISS for scalable similarity search.

    Uses GPU acceleration if available, falls back to CPU, then brute force.
    Complexity: O(n log n) with FAISS vs O(n²) with brute force.

    Args:
        cards: List of card dicts with embeddings
        threshold: Similarity threshold (0.0-1.0)

    Returns:
        List of tuples: (card1_idx, card2_idx, similarity_score)
    """
    n = len(cards)

    # Use FAISS if available, otherwise fall back to brute force
    if HAS_FAISS:
        # Convert embeddings to numpy array
        embeddings = np.array([card['embedding'] for card in cards]).astype('float32')
        d = embeddings.shape[1]  # Dimension of embeddings

        # Normalize for cosine similarity (so inner product = cosine similarity)
        faiss.normalize_L2(embeddings)

        # Try to use GPU if available
        use_gpu = False
        try:
            if faiss.get_num_gpus() > 0:
                # Move index to GPU
                res = faiss.StandardGpuResources()
                index = faiss.GpuIndexFlatIP(res, d)
                use_gpu = True
                print(f"  Using FAISS GPU for similarity search ({n} cards)")
            else:
                # CPU fallback
                index = faiss.IndexFlatIP(d)
                print(f"  Using FAISS CPU for similarity search ({n} cards)")
        except (AttributeError, RuntimeError):
            # GPU not available or not compiled with GPU support
            index = faiss.IndexFlatIP(d)
            print(f"  Using FAISS CPU for similarity search ({n} cards)")

        # Add vectors to index
        index.add(embeddings)

        # Search for similar cards
        # k = number of nearest neighbors to find per card (including self)
        # We search for top min(100, n) to avoid checking all n pairs for large datasets
        k = min(100, n)
        similarities, indices = index.search(embeddings, k)

        # Extract pairs above threshold
        pairs = []
        seen = set()

        for i in range(n):
            for j_idx in range(1, k):  # Skip j_idx=0 (self-match)
                if j_idx >= len(indices[i]):
                    break

                j = indices[i][j_idx]
                score = similarities[i][j_idx]

                # Only add if above threshold and i < j (avoid duplicates)
                if score >= threshold and i < j:
                    pair_key = (min(i, j), max(i, j))
                    if pair_key not in seen:
                        pairs.append((i, j, float(score)))
                        seen.add(pair_key)

    else:
        # Brute force fallback when FAISS not available (shouldn't happen in normal installs)
        print(f"  Using brute force similarity search ({n} cards)")
        pairs = []

        for i in range(n):
            for j in range(i + 1, n):
                similarity = cosine_similarity(cards[i]['embedding'], cards[j]['embedding'])
                if similarity >= threshold:
                    pairs.append((i, j, similarity))

    # Sort by similarity descending
    pairs.sort(key=lambda x: x[2], reverse=True)
    return pairs


def classify_duplicate_pair(card1, card2, client):
    """Use LLM to classify if cards are duplicates or complementary.

    Args:
        card1: First card dict with question and answer
        card2: Second card dict with question and answer
        client: OpenAI-compatible client (configured for OpenRouter)

    Returns:
        tuple: (classification, reasoning)
        classification: 'duplicate', 'complementary', 'unclear', or 'error'
        reasoning: Explanation from LLM or error message
    """
    prompt = f"""Compare these two flashcards and classify their relationship:

Card 1:
Q: {card1['question']}
A: {card1['answer']}

Card 2:
Q: {card2['question']}
A: {card2['answer']}

Classify as ONE of:
- "duplicate": Same concept, essentially redundant (one should be removed)
- "complementary": Related but covering different aspects/opposite scenarios (both should be kept)
- "unclear": Cannot determine confidently

IMPORTANT: If the cards are flipped versions of each other (where Q1 ≈ A2 and A1 ≈ Q2), classify as "complementary" because they engage the brain in different ways and are pedagogically valuable.

Respond with EXACTLY this format:
classification | reasoning (one line explanation)

Example: complementary | Card 1 asks about increasing X, Card 2 about decreasing X - opposite scenarios of same concept"""

    try:
        response = client.chat.completions.create(
            model="google/gemini-2.5-flash", 
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=1024
        )

        result = response.choices[0].message.content.strip()

        # Parse response
        if '|' not in result:
            return 'unclear', f"LLM response format invalid: {result[:50]}"

        classification, _, reasoning = result.partition('|')
        classification = classification.strip().lower()
        reasoning = reasoning.strip()

        # Validate classification
        if classification not in ('duplicate', 'complementary', 'unclear'):
            return 'unclear', f"Invalid classification '{classification}': {reasoning}"

        return classification, reasoning

    except Exception as e:
        return 'error', f"LLM request failed: {str(e)[:100]}"


def dedupe(file_path=None, threshold=0.85):
    """Find and remove duplicate cards from deck file(s) using semantic similarity.

    Args:
        file_path: Path to deck file (<deck-name>-<deck_id>.md). If None, dedupes across all deck files in current directory
        threshold: Similarity threshold for duplicates (default: 0.85)
    """
    # Load cards from single file or all files
    if file_path:
        local_file = Path(file_path)
        if not local_file.exists():
            print(f"Error: {local_file} not found")
            return

        print(f"Loading cards from {local_file}...")
        deck_files = [local_file]
    else:
        # Load all deck files
        deck_files = find_deck_files()
        if not deck_files:
            print("Error: No deck files found in current directory")
            print("Deck files must match pattern: deck-*.md")
            return

        print(f"Loading cards from {len(deck_files)} deck file(s)...")
        for deck_file in deck_files:
            print(f"  - {deck_file.name}")

    # Load all cards and track their source file
    all_cards = []
    for deck_file in deck_files:
        cards = parse_markdown_cards(deck_file.read_text())
        for card in cards:
            card['source_file'] = deck_file
        all_cards.extend(cards)

    if len(all_cards) < 2:
        print("Not enough cards to deduplicate (need at least 2)")
        return

    print(f"\nTotal cards loaded: {len(all_cards)}")
    cards = all_cards

    # Initialize OpenRouter client for embeddings
    embedding_client = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1"
    )

    # Initialize OpenRouter client for classification
    classification_client = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1"
    )

    print(f"Generating embeddings for {len(cards)} cards...")
    # Prepare all texts for batch processing
    texts = [f"{card['question']}\n{card['answer']}" for card in cards]

    # Get embeddings in batches (much faster than sequential)
    embeddings = get_embeddings_batch(texts, embedding_client)

    # Assign embeddings back to cards
    for card, embedding in zip(cards, embeddings):
        card['embedding'] = embedding

    print(f"\n✓ Generated {len(cards)} embeddings")

    print(f"\nFinding duplicate pairs (threshold: {threshold})...")
    pairs = find_duplicate_pairs(cards, threshold)

    if not pairs:
        print("✓ No duplicates found!")
        return

    print(f"\nFound {len(pairs)} potential duplicate pair(s)")
    print(f"Classifying with LLM...")

    # Classify pairs with LLM
    classified_pairs = []
    for idx, (i, j, score) in enumerate(pairs, 1):
        classification, reasoning = classify_duplicate_pair(
            cards[i], cards[j], classification_client
        )
        classified_pairs.append({
            'i': i,
            'j': j,
            'score': score,
            'classification': classification,
            'reasoning': reasoning
        })
        print(f"  {idx}/{len(pairs)} classified", end='\r')

    print()  # Newline after progress

    # Separate pairs by classification
    complementary_pairs = [p for p in classified_pairs if p['classification'] == 'complementary']
    needs_review = [p for p in classified_pairs if p['classification'] in ('duplicate', 'unclear', 'error')]

    # Report auto-skipped complementary pairs
    if complementary_pairs:
        print(f"\n✓ Auto-skipped {len(complementary_pairs)} complementary pair(s):")
        for p in complementary_pairs[:5]:  # Show first 5
            card1, card2 = cards[p['i']], cards[p['j']]
            q1_preview = card1['question'][:40] + '...' if len(card1['question']) > 40 else card1['question']
            q2_preview = card2['question'][:40] + '...' if len(card2['question']) > 40 else card2['question']
            file1 = f" [{card1['source_file'].name}]" if card1.get('source_file') else ""
            file2 = f" [{card2['source_file'].name}]" if card2.get('source_file') else ""
            print(f"  • {q1_preview}{file1} ↔ {q2_preview}{file2}")
            print(f"    Reason: {p['reasoning'][:70]}...")
        if len(complementary_pairs) > 5:
            print(f"  ... and {len(complementary_pairs) - 5} more")

    if not needs_review:
        print("\n✓ No duplicates found after LLM review!")
        return

    print(f"\n{len(needs_review)} pair(s) need manual review:\n")

    # Interactive resolution for unclear/duplicate/error pairs
    cards_to_remove = set()

    for idx, pair in enumerate(needs_review, 1):
        i, j = pair['i'], pair['j']
        card1 = cards[i]
        card2 = cards[j]

        # Skip if either card is already marked for removal
        if i in cards_to_remove or j in cards_to_remove:
            continue

        print("=" * 70)
        print(f"Pair {idx}/{len(needs_review)} - Similarity: {pair['score']:.3f}")
        print("-" * 70)

        # Show LLM classification
        classification_emoji = {
            'duplicate': '🔴',
            'unclear': '🟡',
            'error': '⚠️'
        }
        emoji = classification_emoji.get(pair['classification'], '❓')
        print(f"\n{emoji} LLM Classification: {pair['classification'].upper()}")
        print(f"   Reasoning: {pair['reasoning']}")

        print(f"\n[1] Card 1:")
        print(f"    Q: {card1['question'][:100]}{'...' if len(card1['question']) > 100 else ''}")
        print(f"    A: {card1['answer'][:100]}{'...' if len(card1['answer']) > 100 else ''}")
        if card1['card_id']:
            print(f"    ID: {card1['card_id']}")
        if card1.get('source_file'):
            print(f"    File: {card1['source_file'].name}")
        print(f"\n[2] Card 2:")
        print(f"    Q: {card2['question'][:100]}{'...' if len(card2['question']) > 100 else ''}")
        print(f"    A: {card2['answer'][:100]}{'...' if len(card2['answer']) > 100 else ''}")
        if card2['card_id']:
            print(f"    ID: {card2['card_id']}")
        if card2.get('source_file'):
            print(f"    File: {card2['source_file'].name}")

        print("\nOptions:")
        print("  1 - Keep card 1, remove card 2")
        print("  2 - Keep card 2, remove card 1")
        print("  b - Keep both (not duplicates)")
        print("  s - Skip to next pair")
        print("  q - Quit without saving")

        while True:
            choice = input("\nYour choice [1/2/b/s/q]: ").strip().lower()

            if choice == '1':
                cards_to_remove.add(j)
                print(f"  → Will remove card 2")
                break
            elif choice == '2':
                cards_to_remove.add(i)
                print(f"  → Will remove card 1")
                break
            elif choice == 'b':
                print(f"  → Keeping both cards")
                break
            elif choice == 's':
                print(f"  → Skipped")
                break
            elif choice == 'q':
                print("\nAborted - no changes made")
                return
            else:
                print("Invalid choice. Please enter 1, 2, b, s, or q")

    if not cards_to_remove:
        print("\n✓ No cards marked for removal")
        return

    # Show summary
    print("\n" + "=" * 70)
    print(f"\nSummary: Will remove {len(cards_to_remove)} card(s)")
    print("-" * 70)
    for idx in sorted(cards_to_remove):
        card = cards[idx]
        file_info = f" ({card['source_file'].name})" if card.get('source_file') else ""
        print(f"  - {card['question'][:60]}{'...' if len(card['question']) > 60 else ''}{file_info}")

    response = input("\nProceed with removal? [y/N]: ").lower().strip()
    if response not in ('y', 'yes'):
        print("Aborted")
        return

    # Group cards by source file for efficient writing
    cards_by_file = {}
    for i, card in enumerate(cards):
        if i not in cards_to_remove:
            source_file = card.get('source_file', deck_files[0])  # Fallback to first file for single-file mode
            if source_file not in cards_by_file:
                cards_by_file[source_file] = []
            cards_by_file[source_file].append(card)

    # Write back to each modified file
    files_modified = set()
    for deck_file in deck_files:
        cards_to_keep = cards_by_file.get(deck_file, [])

        # Check if any cards were removed from this file
        original_cards = [c for c in cards if c.get('source_file') == deck_file]
        if len(cards_to_keep) < len(original_cards):
            files_modified.add(deck_file)

            with deck_file.open('w', encoding='utf-8') as f:
                for card in cards_to_keep:
                    # Remove temporary fields before writing
                    card.pop('embedding', None)
                    card.pop('source_file', None)
                    f.write(format_card_to_markdown(card) + '\n')

    print(f"\n✓ Removed {len(cards_to_remove)} duplicate(s)")
    print(f"✓ Modified {len(files_modified)} file(s):")
    for deck_file in sorted(files_modified):
        remaining = len(cards_by_file.get(deck_file, []))
        print(f"   - {deck_file.name} ({remaining} cards remaining)")

    if len(deck_files) == 1:
        print(f"\nTip: Review changes with: git diff {deck_files[0].name}")
    else:
        print(f"\nTip: Review changes with: git diff")


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

    push_parser = subparsers.add_parser("push", help="Push local deck file(s) to Mochi (one-way: local → remote)")
    push_parser.add_argument("file_path", nargs='?', help="Path to deck file (e.g., deck-python-abc123.md or deck-mynewdeck.md). If omitted, pushes all deck-*.md files in current directory")
    push_parser.add_argument("--force", action="store_true",
                            help="Skip duplicate detection")

    sync_parser = subparsers.add_parser("sync", help="Bidirectional sync: handles remote deletions and local changes")
    sync_parser.add_argument("file_path", nargs='?', help="Path to deck file (e.g., deck-python-abc123.md). If omitted, syncs all deck-*.md files in current directory")
    sync_parser.add_argument("--force", action="store_true",
                            help="Skip duplicate detection")

    dedupe_parser = subparsers.add_parser("dedupe", help="Find and remove duplicate cards using semantic similarity")
    dedupe_parser.add_argument("file_path", nargs='?', help="Path to deck file (e.g., deck-python-abc123.md). If omitted, dedupes across all deck-*.md files in current directory")
    dedupe_parser.add_argument("--threshold", type=float, default=0.85,
                              help="Similarity threshold (0.0-1.0, default: 0.85)")

    return parser.parse_args()


def main():
    global API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY
    args = parse_args()

    # Load API key from config (prompts for MOCHI_API_KEY if not found)
    API_KEY = get_api_key()

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
        print("  mochi-mochi pull <deck_id>")
        return

    elif args.command == "pull":
        pull(args.deck_id)

    elif args.command == "push":
        # If no file specified, batch push all deck files in current directory
        if args.file_path is None:
            deck_files = find_deck_files()

            if not deck_files:
                print("Error: No deck files found in current directory")
                print("Deck files must match pattern: deck-*.md")
                return

            print(f"Found {len(deck_files)} deck file(s) to push:\n")
            for deck_file in deck_files:
                print(f"  - {deck_file.name}")

            response = input(f"\nProceed to push {len(deck_files)} deck file(s)? [y/N]: ").lower().strip()
            if response not in ('y', 'yes'):
                print("Aborted")
                return

            # Push each deck file
            for idx, deck_file in enumerate(deck_files, 1):
                print(f"\n{'=' * 70}")
                print(f"Pushing deck {idx}/{len(deck_files)}: {deck_file.name}")
                print('=' * 70)
                push(str(deck_file), force=args.force)

            print(f"\n✓ Batch push completed: {len(deck_files)} deck(s) processed")
        else:
            # Single file push
            push(args.file_path, force=args.force)

    elif args.command == "sync":
        # If no file specified, batch sync all deck files in current directory
        if args.file_path is None:
            deck_files = find_deck_files()

            if not deck_files:
                print("Error: No deck files found in current directory")
                print("Deck files must match pattern: deck-*.md")
                return

            print(f"Found {len(deck_files)} deck file(s) to sync:\n")
            for deck_file in deck_files:
                print(f"  - {deck_file.name}")

            response = input(f"\nProceed to sync {len(deck_files)} deck file(s)? [y/N]: ").lower().strip()
            if response not in ('y', 'yes'):
                print("Aborted")
                return

            # Sync each deck file
            for idx, deck_file in enumerate(deck_files, 1):
                print(f"\n{'=' * 70}")
                print(f"Syncing deck {idx}/{len(deck_files)}: {deck_file.name}")
                print('=' * 70)
                sync(str(deck_file), force=args.force)

            print(f"\n✓ Batch sync completed: {len(deck_files)} deck(s) processed")
        else:
            # Single file sync
            sync(args.file_path, force=args.force)

    elif args.command == "dedupe":
        # Load API key for dedupe command
        OPENROUTER_API_KEY = get_openrouter_api_key()
        dedupe(file_path=args.file_path, threshold=args.threshold)

    elif args.command is None:
        print("No command specified. Use --help to see available commands.")
        print("\nQuick start:")
        print("  1. mochi-mochi decks                          # List decks")
        print("  2. mochi-mochi pull <deck_id>                 # Download deck")
        print("  3. Edit deck-<deck-name>-<deck_id>.md")
        print("  4. mochi-mochi push deck-<deck-name>-<deck_id>.md  # Upload changes (one-way)")
        print("     or: mochi-mochi sync deck-<deck-name>-<deck_id>.md  # Bidirectional sync")
        print("     or: mochi-mochi push                       # Upload all deck files")
        print("     or: mochi-mochi sync                       # Sync all deck files")
        print("\nOr create a new deck:")
        print("  1. Create deck-<name>.md file")
        print("  2. mochi-mochi push deck-<name>.md            # Creates deck in Mochi")


if __name__ == "__main__":
    main()
