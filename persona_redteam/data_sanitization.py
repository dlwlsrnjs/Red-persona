"""Shared de-identification for experimental goal and persona text."""
from __future__ import annotations

import re


_PATTERNS = (
    re.compile(r"\b(?:i am|i'm|im)\s+\d{1,3}(?:\s*years?\s*old)?\s*[,;/]?\s*(?:female|male|woman|man|girl|boy)\b", re.I),
    re.compile(r"\b\d{1,3}\s*[,/]\s*(?:f|m|female|male)\b", re.I),
    re.compile(r"\b(?:i am|i'm|im)\s+(?:a\s+)?(?:female|male|woman|man|girl|boy)\b", re.I),
    re.compile(r"\b(?:female|male),?\s+aged?\s+\d{1,3}\b", re.I),
)


def strip_demographics(text: str) -> str:
    """Remove explicit age/gender self-identification without changing other facts."""
    value = str(text)
    for pattern in _PATTERNS:
        value = pattern.sub("", value)
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    value = re.sub(r"([,;])\s*([,;])", r"\1", value)
    value = re.sub(r"([.!?])(?:\s*[.!?])+", r"\1", value)
    value = re.sub(r"\s{2,}", " ", value)
    return value.strip(" ,;")
