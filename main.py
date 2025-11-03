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
import importlib
import json
import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
API_KEY = os.getenv("MOCHI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
DECK_ID = os.getenv("DECK_ID")

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
    results = [(card, *grade_map[card['id']]) for card in cards_batch]
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


def list_cards(deck_id):
    """List all cards in the deck."""
    print("Fetching cards...")
    cards = get_cards(deck_id)
    print(f"\nTotal cards: {len(cards)}\n" + "=" * 60)

    for i, card in enumerate(cards, 1):
        content = card['content']
        truncated = content[:200] + '...' if len(content) > 200 else content
        print(f"\nCard {i} (ID: {card['id']}):\n{truncated}\n" + "-" * 60)


def dump_cards_to_markdown(deck_id, output_file="mochi_cards.md"):
    """Dump all cards to a markdown file."""
    print("Fetching cards...")
    cards = get_cards(deck_id)
    print(f"Exporting {len(cards)} cards to {output_file}...")

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"# Mochi Cards Export\n\nTotal cards: {len(cards)}\n\n")
        for card in cards:
            question, answer = parse_card(card['content'])
            f.write(f"---\ncard_id: {card['id']}\n---\n")
            f.write(f"{question}\n")
            f.write(f"---\n")
            f.write(f"{answer}\n")

    print(f"✓ Exported {len(cards)} cards to {output_file}")
    return len(cards)


def upload_cards_from_markdown(deck_id, input_file):
    """Upload cards from a markdown file.

    Expected compact markdown format:
    ---
    card_id: abc123
    ---
    Question text
    ---
    Answer text
    ---
    card_id: null
    ---
    Next question
    ---
    Next answer

    Cards are separated by ---. All cards have frontmatter.
    If card_id is a valid ID, the card will be updated.
    If card_id is null/empty, a new card will be created.

    Args:
        deck_id: Deck ID to add cards to
        input_file: Path to markdown file

    Returns:
        Tuple of (created_ids, updated_ids)
    """
    print(f"Reading cards from {input_file}...")

    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split by --- separator
    sections = [s.strip() for s in content.split('---')]
    created_ids = []
    updated_ids = []

    # State machine parser
    state = 'expect_frontmatter'  # expect_frontmatter, expect_question, expect_answer
    card_id = None
    question = None
    card_num = 0

    for section in sections:
        if not section:
            continue

        # Skip headers
        if section.startswith('#'):
            continue

        if state == 'expect_frontmatter':
            # Check if this is a card_id frontmatter
            if section.strip().startswith('card_id:'):
                card_id_value = section.split('card_id:')[1].strip().split()[0]
                # Treat 'null', 'None', empty, or whitespace as no ID
                if card_id_value.lower() in ('null', 'none', '') or not card_id_value:
                    card_id = None
                else:
                    card_id = card_id_value
                state = 'expect_question'
            else:
                # Malformed - this should be frontmatter but isn't
                # Treat as question for backwards compatibility
                question = section
                state = 'expect_answer'

        elif state == 'expect_question':
            question = section
            state = 'expect_answer'

        elif state == 'expect_answer':
            answer = section
            card_num += 1

            # Create card content in Mochi format
            card_content = f"{question}\n---\n{answer}"

            if card_id:
                print(f"  Updating card {card_num} (ID: {card_id})...", end=' ', flush=True)
                update_card(card_id, content=card_content)
                updated_ids.append(card_id)
                print("✓")
            else:
                print(f"  Creating card {card_num}...", end=' ', flush=True)
                created_card = create_card(deck_id, card_content)
                created_ids.append(created_card['id'])
                print(f"✓ (ID: {created_card['id']})")

            # Reset state
            card_id = None
            question = None
            state = 'expect_frontmatter'

    print(f"\n✓ Successfully created {len(created_ids)} cards and updated {len(updated_ids)} cards")
    return created_ids, updated_ids


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
    subparsers.add_parser("decks", help="List all available decks")
    subparsers.add_parser("list", help="List all cards in the deck")

    grade_parser = subparsers.add_parser("grade", help="Grade all cards using LLM")
    grade_parser.add_argument("--batch-size", type=int, default=20,
                             help="Cards per batch (default: 20)")

    dump_parser = subparsers.add_parser("dump", help="Export cards to markdown")
    dump_parser.add_argument("--output", "-o", default="mochi_cards.md",
                            help="Output file (default: mochi_cards.md)")

    upload_parser = subparsers.add_parser("upload", help="Upload cards from markdown")
    upload_parser.add_argument("--input", "-i", required=True,
                              help="Input markdown file")

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
    if args.command == "list" or args.command is None:
        list_cards(DECK_ID)
    elif args.command == "grade":
        imperfect_cards, all_results = grade_all_cards(DECK_ID, batch_size=args.batch_size)
        display_grading_results(imperfect_cards, all_results)
    elif args.command == "dump":
        dump_cards_to_markdown(DECK_ID, args.output)
    elif args.command == "upload":
        upload_cards_from_markdown(DECK_ID, args.input)
    elif args.command == "task" and args.task_subcommand == "run":
        execute_task(args.task_name, DECK_ID, apply=args.apply)


if __name__ == "__main__":
    main()
