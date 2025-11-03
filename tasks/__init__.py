"""
Base task structure for LLM operations on Mochi cards.

Task modules should define:
- __doc__: The prompt to send to the LLM (required)
- TYPE: "read_only" or "mutate" (default: "read_only")
- BATCH_SIZE: Number of cards to process per LLM call (default: 20)
- OUTPUT_SCHEMA: Description of expected output format (optional)
- FIELD: Which card field to analyze/modify (default: "content")

For mutation tasks:
- parse_llm_response(response, card): Extract new value from LLM response
- apply_mutation(card, new_value): Apply the change to the card dict

For read-only tasks:
- parse_llm_response(response, card): Extract result data from LLM response
"""

from typing import Protocol, Any, Dict, List


class Task(Protocol):
    """Protocol defining the task interface."""

    __doc__: str  # The LLM prompt
    TYPE: str  # "read_only" or "mutate"
    BATCH_SIZE: int
    FIELD: str

    def parse_llm_response(self, response: str, card: Dict[str, Any]) -> Any:
        """Parse the LLM response for this card."""
        ...

    def apply_mutation(self, card: Dict[str, Any], new_value: Any) -> Dict[str, Any]:
        """Apply mutation to card (only for mutate tasks)."""
        ...
