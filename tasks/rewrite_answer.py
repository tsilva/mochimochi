"""
Rewrite flashcard answers to be more concise while maintaining accuracy.

For each card, rewrite the answer section to be:
- Concise: Remove unnecessary words
- Clear: Use simple, direct language
- Complete: Keep all essential information

Return JSON array with rewritten answers:
[{"card_id": "...", "new_value": "rewritten answer text"}]
"""

from typing import Any, Dict

TYPE = "mutate"
BATCH_SIZE = 10  # Smaller batches for mutations
FIELD = "content"


def apply_mutation(card: Dict[str, Any], new_answer: str) -> Dict[str, Any]:
    """Apply the rewritten answer to the card content."""
    from main import parse_card  # Import from main module

    # Parse existing card
    question, old_answer = parse_card(card["content"])

    # Reconstruct card with new answer
    new_content = f"{question}\n---\n{new_answer}"

    # Return updated card dict
    updated_card = card.copy()
    updated_card["content"] = new_content

    return updated_card
