#!/usr/bin/env python3
"""Mochi flashcard management CLI with local-first multi-deck workflow.

Workflow:
    1. mochi-mochi decks                      # List available decks
    2. mochi-mochi pull <deck_id>             # Download to <name>-<deck_id>.md
    3. Edit <name>-<deck_id>.md locally
    4. mochi-mochi push <name>-<deck_id>.md   # Upload changes back to Mochi

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
from datetime import datetime
from openai import OpenAI

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
    """Find pairs of similar cards using embeddings.

    Args:
        cards: List of card dicts with embeddings
        threshold: Similarity threshold (0.0-1.0)

    Returns:
        List of tuples: (card1_idx, card2_idx, similarity_score)
    """
    pairs = []
    n = len(cards)

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


def dedupe(file_path, threshold=0.85):
    """Find and remove duplicate cards from deck file using semantic similarity.

    Args:
        file_path: Path to deck file (<deck-name>-<deck_id>.md)
        threshold: Similarity threshold for duplicates (default: 0.85)
    """
    local_file = Path(file_path)

    if not local_file.exists():
        print(f"Error: {local_file} not found")
        return

    print(f"Loading cards from {local_file}...")
    cards = parse_markdown_cards(local_file.read_text())

    if len(cards) < 2:
        print("Not enough cards to deduplicate (need at least 2)")
        return

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
            print(f"  • {q1_preview} ↔ {q2_preview}")
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
        print(f"\n[2] Card 2:")
        print(f"    Q: {card2['question'][:100]}{'...' if len(card2['question']) > 100 else ''}")
        print(f"    A: {card2['answer'][:100]}{'...' if len(card2['answer']) > 100 else ''}")
        if card2['card_id']:
            print(f"    ID: {card2['card_id']}")

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
        print(f"  - {card['question'][:60]}{'...' if len(card['question']) > 60 else ''}")

    response = input("\nProceed with removal? [y/N]: ").lower().strip()
    if response not in ('y', 'yes'):
        print("Aborted")
        return

    # Remove duplicates and write back to file
    cards_to_keep = [card for i, card in enumerate(cards) if i not in cards_to_remove]

    with local_file.open('w', encoding='utf-8') as f:
        for card in cards_to_keep:
            # Remove embedding before writing (not needed in file)
            card.pop('embedding', None)
            f.write(format_card_to_markdown(card) + '\n')

    print(f"\n✓ Removed {len(cards_to_remove)} duplicate(s)")
    print(f"✓ {len(cards_to_keep)} cards remaining in {local_file}")
    print(f"\nTip: Review changes with: git diff {local_file.name}")


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

    dedupe_parser = subparsers.add_parser("dedupe", help="Find and remove duplicate cards using semantic similarity")
    dedupe_parser.add_argument("file_path", help="Path to deck file (e.g., python-abc123.md)")
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
        push(args.file_path, force=args.force)

    elif args.command == "dedupe":
        # Load API key for dedupe command
        OPENROUTER_API_KEY = get_openrouter_api_key()
        dedupe(args.file_path, threshold=args.threshold)

    elif args.command is None:
        print("No command specified. Use --help to see available commands.")
        print("\nQuick start:")
        print("  1. mochi-mochi decks              # List decks")
        print("  2. mochi-mochi pull <deck_id>     # Download deck")
        print("  3. Edit <deck-name>-<deck_id>.md")
        print("  4. mochi-mochi push <deck-name>-<deck_id>.md  # Upload changes")


if __name__ == "__main__":
    main()
