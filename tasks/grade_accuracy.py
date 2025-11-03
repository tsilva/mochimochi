"""
Grade the accuracy of flashcard answers on a scale of 0-10.

For each card, analyze the answer and provide:
- score: Integer from 0-10 (10 = perfectly accurate, 0 = completely wrong/misleading)
- reason: Brief explanation of the score

Consider:
- Correctness: Is the answer factually correct?
- Completeness: Does it fully answer the question?
- Clarity: Is it clear and understandable?

Return JSON format:
{
  "card_id": "...",
  "score": 8,
  "reason": "Accurate and clear, but missing edge cases"
}
"""

import json
from typing import Any, Dict

TYPE = "read_only"
BATCH_SIZE = 20
FIELD = "content"
OUTPUT_SCHEMA = {"score": "int (0-10)", "reason": "string"}


def parse_llm_response(response: str, card: Dict[str, Any]) -> Dict[str, Any]:
    """Parse the LLM response to extract score and reason."""
    try:
        # Try to parse as JSON
        data = json.loads(response)
        return {
            "card_id": card["id"],
            "score": data.get("score", 0),
            "reason": data.get("reason", "No reason provided"),
        }
    except json.JSONDecodeError:
        # Fallback: try to extract score from text
        import re

        score_match = re.search(r"score[:\s]+(\d+)", response, re.IGNORECASE)
        score = int(score_match.group(1)) if score_match else 0

        return {
            "card_id": card["id"],
            "score": score,
            "reason": response[:200],  # First 200 chars as reason
        }
