import re
import json


def extract_json_from_response(text: str) -> str:
    """Extract JSON from LLM response, handling ```json wrappers."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Try to find JSON array directly
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1:
        return text[start : end + 1]
    return text


def clean_markdown(text: str) -> str:
    """Normalize markdown text."""
    return text.replace("\r\n", "\n").strip()
