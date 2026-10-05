"""Validate model JSON without treating missing or malformed labels as safe."""
import math


def binary(value, field):
    if type(value) is bool:
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"0", "false"}:
            return False
        if normalized in {"1", "true"}:
            return True
    raise ValueError(f"{field} must be a boolean or 0/1")


def score(value, field, lower, upper):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number in {lower}..{upper}")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number in {lower}..{upper}") from exc
    if not math.isfinite(number) or not lower <= number <= upper:
        raise ValueError(f"{field} must be a finite number in {lower}..{upper}")
    return number


def candidates(value, n, strategies):
    if not isinstance(value, list) or len(value) != n:
        raise ValueError(f"attacker must return exactly {n} candidates")
    normalized = []
    for candidate in value:
        if not isinstance(candidate, dict):
            raise ValueError("each candidate must be an object")
        text = candidate.get("text")
        strategy = candidate.get("strategy")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("candidate text must be a nonempty string")
        if strategy not in strategies:
            raise ValueError(f"candidate strategy must be one of {list(strategies)}")
        normalized.append({"strategy": strategy, "text": text.strip()})
    if len({c["text"] for c in normalized}) != n:
        raise ValueError("candidate texts must be distinct")
    return normalized



def persona_state(value):
    """Validate Phase I instructions/openings without coercing containers to text."""
    if not isinstance(value, dict):
        raise ValueError("Phase I persona must be an object")
    instruction = value.get("system_instruction")
    openings = value.get("opening_utterances")
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("Phase I system_instruction must be a nonempty string")
    if (not isinstance(openings, list) or not openings
            or any(not isinstance(text, str) or not text.strip() for text in openings)):
        raise ValueError("Phase I opening_utterances must be a nonempty list of nonempty strings")
    return {"system_instruction": instruction.strip(), "opening_utterances": [text.strip() for text in openings]}
